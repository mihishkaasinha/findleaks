"""
Leak detection pipeline.
Steps:
  1. Preprocess image (OpenCV denoise + threshold)
  2. OCR the image (Tesseract)
  3. Search OCR text against loaded FAISS index
  4. Compute confidence score
  5. Return DetectionResult
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import structlog

from findleaks.config import get_settings
from findleaks.ingestion import clean_text

logger = structlog.get_logger()


@dataclass
class MatchedQuestion:
    question_id: int
    text: str
    score: float


@dataclass
class DetectionResult:
    ocr_text: str
    confidence: float
    confidence_label: str          # "high" | "review" | "clean"
    matched_questions: list[MatchedQuestion] = field(default_factory=list)
    top_score: float = 0.0


def preprocess_image(image_bytes: bytes) -> "np.ndarray":
    """
    OpenCV pipeline for phone-photo exam images:
    1. Decode + grayscale
    2. Upscale to >= 1200px wide (Tesseract needs high DPI for small text)
    3. Adaptive threshold (robust to uneven lighting in photos)
    """
    import cv2

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("cv2.imdecode failed — invalid image bytes")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Upscale if image is small — target >= 1200px wide
    h, w = gray.shape
    if w < 1200:
        scale = 1200.0 / w
        gray = cv2.resize(gray, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC)

    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    return thresh


def ocr_image(image_bytes: bytes) -> str:
    """
    Run Tesseract on raw image bytes.
    Preprocessing is applied before OCR.
    """
    try:
        import cv2
        import pytesseract

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return ""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Upscale if small — helps with subscripts and special chars
        h, w = gray.shape
        if w < 1200:
            scale = 1200.0 / w
            gray = cv2.resize(gray, None, fx=scale, fy=scale,
                              interpolation=cv2.INTER_CUBIC)

        blurred = cv2.GaussianBlur(gray, (3, 3), 0)

        # Attempt 1: adaptive threshold (handles uneven lighting well)
        thresh_adaptive = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        text1 = pytesseract.image_to_string(
            thresh_adaptive, config="--oem 3 --psm 6"
        ).strip()

        # Attempt 2: OTSU global threshold (better for uniform lighting / printed docs)
        _, thresh_otsu = cv2.threshold(blurred, 0, 255,
                                        cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text2 = pytesseract.image_to_string(
            thresh_otsu, config="--oem 3 --psm 6"
        ).strip()

        # Use whichever produced more text (more chars = fewer blanked regions)
        text = text1 if len(text1) >= len(text2) else text2

        # Last-resort fallback: raw grayscale
        if not text:
            text = pytesseract.image_to_string(
                gray, config="--oem 3 --psm 6"
            ).strip()

        return text
    except Exception as exc:
        logger.warning("ocr_failed", error=str(exc))
        return ""


def _jaccard(text_a: str, text_b: str) -> float:
    """Word-level Jaccard similarity between two pre-cleaned texts."""
    a = set(text_a.split())
    b = set(text_b.split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _char_ngram_jaccard(text_a: str, text_b: str, n: int = 3) -> float:
    """
    Character n-gram Jaccard similarity.
    Robust to OCR noise: 'chatecd' and 'charged' share 'cha','ate','ted','ged'
    even though the words differ. Spaces stripped before n-gram extraction.
    """
    a = text_a.replace(" ", "")
    b = text_b.replace(" ", "")
    if len(a) < n or len(b) < n:
        return 0.0
    a_grams = set(a[i:i + n] for i in range(len(a) - n + 1))
    b_grams = set(b[i:i + n] for i in range(len(b) - n + 1))
    union = len(a_grams | b_grams)
    return len(a_grams & b_grams) / union if union else 0.0


def _overlap_adjusted_score(faiss_score: float, wj: float, cj: float) -> float:
    """
    Multiplicative overlap gate: penalises matches with low word/char overlap.

    Formula: score * (0.30 + 0.70 * min(1, wj*6 + cj*2))

    Calibration:
      wj=0.00, cj=0.08 (exam header vs question) → gate=0.46 → 0.76*0.46=0.35  CLEAN
      wj=0.05, cj=0.25 (noisy OCR true positive)  → gate=0.80 → 0.76*0.80=0.61  REVIEW
      wj=0.20, cj=0.40 (clean scan true positive)  → gate=1.00 → 0.76*1.00=0.76  HIGH
    """
    gate = min(1.0, wj * 6 + cj * 2)
    return round(faiss_score * (0.30 + 0.70 * gate), 4)


def search_faiss(
    query_text: str,
    exam_slug: str,
    top_k: int = 5,
) -> list[tuple[int, float]]:
    """
    Search the FAISS index for `exam_slug` using `query_text`.
    Returns list of (question_index, cosine_score) sorted descending.
    Returns [] if index not loaded or text is empty.
    """
    from findleaks.state import faiss_indexes, sentence_model

    if not query_text.strip():
        return []

    index = faiss_indexes.get(exam_slug)
    if index is None:
        logger.warning("faiss_index_not_found", slug=exam_slug)
        return []

    if sentence_model is None:
        logger.warning("sentence_model_not_loaded")
        return []

    cleaned = clean_text(query_text)
    if not cleaned.strip():
        return []

    try:
        embedding = sentence_model.encode(
            [cleaned], convert_to_numpy=True, show_progress_bar=False
        ).astype(np.float32)

        norm = np.linalg.norm(embedding, axis=1, keepdims=True)
        norm = np.where(norm == 0, 1e-10, norm)
        embedding = embedding / norm

        actual_k = min(top_k, index.ntotal)
        D, I = index.search(embedding, actual_k)

        results = [
            (int(I[0][i]), float(D[0][i]))
            for i in range(actual_k)
            if I[0][i] >= 0
        ]
        return sorted(results, key=lambda x: x[1], reverse=True)
    except Exception as exc:
        logger.error("faiss_search_failed", slug=exam_slug, error=str(exc))
        return []


def compute_confidence(raw_scores: list[float]) -> float:
    """
    Confidence = top-1 cosine score + small multi-match boost.

    Calibration for all-MiniLM-L6-v2 after clean_text + phone-photo OCR:
      >= 0.68  → HIGH RISK: very likely same question (OCR noise reduces true score)
      0.52-0.68 → REVIEW: possibly same question, needs human check
      <  0.52  → CLEAN: different topic / unrelated content

    The old weighted-average formula diluted the top score with irrelevant
    matches, causing true positives to fall below the review threshold.
    """
    if not raw_scores:
        return 0.0
    top = raw_scores[0]
    high_matches = sum(1 for s in raw_scores[1:] if s >= 0.52)
    boost = min(high_matches * 0.025, 0.08)
    confidence = min(top + boost, 1.0)
    return round(confidence, 4)


def search_faiss_ranked(
    query_text: str,
    exam_slug: str,
    top_k: int = 5,
) -> list[tuple[int, float]]:
    """
    Like search_faiss but applies Jaccard overlap penalty using state.question_bank.
    Use this in scanner scan_post methods to filter false positives where FAISS
    semantic similarity is high but actual word overlap is very low (e.g. exam
    instruction/header text matching question embeddings due to shared domain vocab).
    Falls back to raw FAISS scores if question_bank is not yet populated.
    """
    from findleaks.state import question_bank

    matches = search_faiss(query_text, exam_slug, top_k=top_k)
    if not matches:
        return []

    q_bank = question_bank.get(exam_slug)
    if not q_bank:
        return matches

    query_clean = clean_text(query_text)
    rescored: list[tuple[int, float]] = []
    for idx, faiss_score in matches:
        q_text = q_bank[idx] if idx < len(q_bank) else ""
        q_clean = clean_text(q_text)
        wj = _jaccard(query_clean, q_clean)
        cj = _char_ngram_jaccard(query_clean, q_clean, n=3)
        adjusted = _overlap_adjusted_score(faiss_score, wj, cj)
        rescored.append((idx, adjusted))

    return sorted(rescored, key=lambda x: x[1], reverse=True)


def confidence_label(confidence: float) -> str:
    settings = get_settings()
    if confidence >= settings.ALERT_THRESHOLD_HIGH:
        return "high"
    if confidence >= settings.ALERT_THRESHOLD_REVIEW:
        return "review"
    return "clean"


def detect(
    image_bytes: bytes,
    exam_slug: str,
    question_texts: Optional[list[str]] = None,
    top_k: int = 5,
) -> DetectionResult:
    """
    Full detection pipeline for one image against one exam index.
    `question_texts`: optional list of raw question strings (for excerpt extraction).
    """
    ocr_text = ocr_image(image_bytes)
    if not ocr_text:
        return DetectionResult(
            ocr_text="",
            confidence=0.0,
            confidence_label="clean",
        )

    matches = search_faiss(ocr_text, exam_slug, top_k=top_k)

    # Re-rank: FAISS cosine score gated by multiplicative word/char overlap penalty.
    # Low word overlap (e.g. exam instruction header vs question) → score penalised.
    # char-trigram overlap is robust to OCR noise so noisy-but-genuine leaks survive.
    ocr_clean = clean_text(ocr_text)
    if question_texts:
        scored: list[tuple[int, float, float]] = []
        for idx, faiss_score in matches:
            q_text = question_texts[idx] if idx < len(question_texts) else ""
            q_clean = clean_text(q_text)
            wj = _jaccard(ocr_clean, q_clean)
            cj = _char_ngram_jaccard(ocr_clean, q_clean, n=3)
            adjusted = _overlap_adjusted_score(faiss_score, wj, cj)
            scored.append((idx, faiss_score, adjusted))
        scored.sort(key=lambda x: x[2], reverse=True)
        raw_scores = [s[2] for s in scored]
        confidence = compute_confidence(raw_scores)
        label = confidence_label(confidence)

        matched_questions = []
        for idx, faiss_score, adjusted in scored:
            q_text = question_texts[idx] if idx < len(question_texts) else ""
            matched_questions.append(MatchedQuestion(
                question_id=idx, text=q_text, score=adjusted
            ))
    else:
        raw_scores = [score for _, score in matches]
        confidence = compute_confidence(raw_scores)
        label = confidence_label(confidence)
        matched_questions = []
        for idx, score in matches:
            q_text = question_texts[idx] if question_texts and idx < len(question_texts) else ""
            matched_questions.append(MatchedQuestion(question_id=idx, text=q_text, score=score))

    top_score = raw_scores[0] if raw_scores else 0.0

    logger.info(
        "detection_complete",
        exam=exam_slug,
        confidence=confidence,
        label=label,
        matches=len(matched_questions),
    )

    return DetectionResult(
        ocr_text=ocr_text,
        confidence=confidence,
        confidence_label=label,
        matched_questions=matched_questions,
        top_score=top_score,
    )
