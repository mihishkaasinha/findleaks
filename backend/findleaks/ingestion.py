import hashlib
import os
import re
import unicodedata
from pathlib import Path
from typing import Generator

import numpy as np
import structlog

logger = structlog.get_logger()

_STOPWORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "could should may might shall can of in on at to for with by from and or but "
    "not no nor so yet both either neither each few more most other some such than "
    "too very just as if then there this that these those".split()
)

_SYMBOL_MAP = str.maketrans({
    "\u03bc": "u",   # μ (micro/mu) → u
    "\u00b5": "u",   # µ (micro sign) → u
    "\u03b1": "alpha",
    "\u03b2": "beta",
    "\u03b3": "gamma",
    "\u03b4": "delta",
    "\u03c0": "pi",
    "\u03c9": "omega",
    "\u03bb": "lambda",
    "\u03b8": "theta",
    "\u00b0": "deg",   # °
    "\u00b2": "2",     # ²
    "\u00b3": "3",     # ³
    "\u221a": "sqrt",  # √
    "\u221e": "inf",   # ∞
    "\u2248": "approx",
    "\u2260": "neq",
    "\u2265": "gte",
    "\u2264": "lte",
    "\u00d7": "x",     # × (cross/multiply)
    "\u00f7": "div",   # ÷
    "\u2212": "-",     # − (minus sign)
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
})

_ANSWER_STRIP_RE = re.compile(
    r"\b(?:answer|ans|sol(?:ution)?)\s*[\.\:\(]",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """Lowercase, normalise symbols, strip non-ASCII, collapse whitespace, remove stopwords."""
    text = text.translate(_SYMBOL_MAP)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [t for t in text.split() if t not in _STOPWORDS and len(t) > 2]
    return " ".join(tokens)


def strip_answer_section(text: str) -> str:
    """
    Remove answer/solution text that appears after question choices.
    e.g. strips "Answer (2) Sol. Potential difference…" from PDF-extracted questions.
    """
    match = _ANSWER_STRIP_RE.search(text)
    if match:
        return text[: match.start()].strip()
    return text


def split_questions(text: str) -> list[str]:
    """
    Split raw text into individual question units using:
    1. Explicit Q\\d+ pattern (Q1., Q2., etc.)
    2. Paragraph gaps (double newlines)
    3. Numbered list patterns (1., 2., etc.)
    """
    if not text or not text.strip():
        return []

    # Strategy 1: explicit Q\d+ markers
    parts = re.split(r"(?=\bQ\s*\d+[\.\):])", text, flags=re.IGNORECASE)
    if len(parts) > 1:
        questions = [p.strip() for p in parts if len(p.strip()) > 20]
        if questions:
            return questions

    # Strategy 2: numbered list (1. 2. etc.)
    parts = re.split(r"(?=^\s*\d{1,3}[\.\)]\s)", text, flags=re.MULTILINE)
    if len(parts) > 1:
        questions = [p.strip() for p in parts if len(p.strip()) > 20]
        if questions:
            return questions

    # Strategy 3: double newline paragraph breaks
    parts = re.split(r"\n\s*\n", text)
    questions = [p.strip() for p in parts if len(p.strip()) > 20]
    if questions:
        return questions

    # Fallback: treat entire text as one question
    if len(text.strip()) > 20:
        return [text.strip()]
    return []


def compute_file_hash(content: bytes) -> str:
    """SHA-256 hash of file content for deduplication."""
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# Embeddings + FAISS
# ---------------------------------------------------------------------------

def embed_questions(questions: list[str]) -> np.ndarray:
    """
    Embed questions using the singleton sentence-transformer model.
    Returns ndarray of shape (N, 384).
    """
    from findleaks.state import sentence_model
    if sentence_model is None:
        raise RuntimeError("Sentence model not loaded — call load_sentence_model() first")
    embeddings = sentence_model.encode(questions, convert_to_numpy=True, show_progress_bar=False)
    return embeddings.astype(np.float32)


def build_faiss_index(embeddings: np.ndarray):
    """
    Build a FAISS IndexFlatIP from embeddings.
    Vectors are L2-normalised before insertion (enables cosine similarity via inner product).
    """
    import faiss

    dim = embeddings.shape[1]
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-10, norms)
    normalized = (embeddings / norms).astype(np.float32)

    index = faiss.IndexFlatIP(dim)
    index.add(normalized)
    return index


def save_faiss_index(index, exam_slug: str, index_dir: str) -> str:
    """Save FAISS index to disk and register in global state."""
    import faiss
    from findleaks import state

    os.makedirs(index_dir, exist_ok=True)
    path = os.path.join(index_dir, f"{exam_slug}.index")
    faiss.write_index(index, path)
    state.faiss_indexes[exam_slug] = index
    logger.info("faiss_index_saved", slug=exam_slug, path=path)
    return path


# ---------------------------------------------------------------------------
# File ingestion
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF using pdfminer (fast, no rendering needed)."""
    try:
        from pdfminer.high_level import extract_text as pm_extract
        return pm_extract(pdf_path) or ""
    except Exception as exc:
        logger.warning("pdfminer_failed", path=pdf_path, error=str(exc))
        return _extract_text_from_pdf_via_images(pdf_path)


def _extract_text_from_pdf_via_images(pdf_path: str) -> str:
    """Fallback: render PDF pages to images then OCR each page."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
        pages = convert_from_path(pdf_path, dpi=200)
        texts = []
        for page in pages:
            texts.append(pytesseract.image_to_string(page, config="--oem 3 --psm 6"))
        return "\n\n".join(texts)
    except Exception as exc:
        logger.error("pdf_image_ocr_failed", path=pdf_path, error=str(exc))
        return ""


def extract_text_from_image(image_path: str) -> str:
    """OCR a single image file and return raw text."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        return pytesseract.image_to_string(img, config="--oem 3 --psm 6")
    except Exception as exc:
        logger.error("image_ocr_failed", path=image_path, error=str(exc))
        return ""


ALLOWED_MIME_MAGIC = {
    b"\x25\x50\x44\x46": "application/pdf",   # %PDF
    b"\x89\x50\x4e\x47": "image/png",          # PNG
    b"\xff\xd8\xff": "image/jpeg",             # JPEG
    b"\x52\x49\x46\x46": "image/webp",         # WEBP (RIFF header)
    b"\x47\x49\x46\x38": "image/gif",          # GIF
}


def detect_mime_type(content: bytes) -> str | None:
    """Detect MIME type by magic bytes (first 8 bytes)."""
    header = content[:8]
    for magic, mime in ALLOWED_MIME_MAGIC.items():
        if header[: len(magic)] == magic:
            return mime
    return None


def is_allowed_file(content: bytes) -> bool:
    return detect_mime_type(content) is not None


# ---------------------------------------------------------------------------
# Full ingestion pipeline
# ---------------------------------------------------------------------------

class IngestionProgress:
    """Tracks ingestion progress and emits SSE-compatible events."""

    def __init__(self):
        self.events: list[dict] = []

    def emit(self, event_type: str, **kwargs) -> dict:
        event = {"type": event_type, **kwargs}
        self.events.append(event)
        return event


def ingest_file(
    file_content: bytes,
    filename: str,
    exam_slug: str,
    save_dir: str,
    progress: IngestionProgress | None = None,
) -> list[str]:
    """
    Full ingestion for one file: validate → save → extract text → split questions.
    Returns list of raw question strings.
    """
    mime = detect_mime_type(file_content)
    if mime is None:
        raise ValueError(f"Unsupported file type: {filename}")

    os.makedirs(save_dir, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", os.path.basename(filename))
    save_path = os.path.join(save_dir, safe_name)

    with open(save_path, "wb") as f:
        f.write(file_content)

    if progress:
        progress.emit("progress", percent=20, message=f"Saved {safe_name}")

    if mime == "application/pdf":
        raw_text = extract_text_from_pdf(save_path)
    else:
        raw_text = extract_text_from_image(save_path)

    if progress:
        progress.emit("progress", percent=60, message="Extracting questions…")

    questions = split_questions(raw_text)
    questions = [strip_answer_section(q) for q in questions]
    questions = [q for q in questions if len(q.strip()) > 20]
    logger.info("questions_extracted", file=filename, count=len(questions))
    return questions


def build_index_for_exam(
    questions: list[str],
    exam_slug: str,
    index_dir: str,
    progress: IngestionProgress | None = None,
) -> tuple[int, str]:
    """
    Embed questions and merge into the existing FAISS index (or create new).
    Returns (new_question_count, index_path).
    Multiple uploads accumulate — existing vectors are preserved.
    """
    import faiss

    if not questions:
        raise ValueError("No questions to index")

    cleaned = [clean_text(q) for q in questions]
    non_empty = [c for c in cleaned if c.strip()]
    if not non_empty:
        raise ValueError("All questions empty after cleaning")

    if progress:
        progress.emit("progress", percent=75, message="Building embeddings…")

    embeddings = embed_questions(non_empty)

    if progress:
        progress.emit("progress", percent=90, message="Merging into FAISS index…")

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-10, norms)
    normalized = (embeddings / norms).astype(np.float32)

    existing_path = os.path.join(index_dir, f"{exam_slug}.index")
    if os.path.exists(existing_path):
        index = faiss.read_index(existing_path)
        index.add(normalized)
        logger.info("faiss_index_merged", slug=exam_slug, added=len(non_empty), total=index.ntotal)
    else:
        dim = normalized.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(normalized)
        logger.info("faiss_index_created", slug=exam_slug, total=index.ntotal)

    path = save_faiss_index(index, exam_slug, index_dir)

    if progress:
        progress.emit("progress", percent=100, message="Index ready")
        progress.emit("complete", question_count=len(non_empty))

    return len(non_empty), path
