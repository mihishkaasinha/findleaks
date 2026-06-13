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
    OpenCV pipeline:
    1. Decode from bytes
    2. Convert to grayscale
    3. Gaussian blur to reduce noise
    4. Adaptive threshold for binarisation (improves OCR accuracy)
    """
    import cv2

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("cv2.imdecode failed — invalid image bytes")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
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

        processed = preprocess_image(image_bytes)
        text = pytesseract.image_to_string(processed, config="--oem 3 --psm 6")
        return text.strip()
    except Exception as exc:
        logger.warning("ocr_failed", error=str(exc))
        return ""


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

    Calibration for all-MiniLM-L6-v2 after clean_text + OCR noise:
      >= 0.82  → near-certain match (identical question, clean image)
      0.72-0.82 → likely match (same question, OCR/encoding variation)
      <  0.72  → noise / different topic (same domain still scores 0.50-0.72)

    The old weighted-average formula diluted the top score with irrelevant
    matches, causing true positives to fall below the review threshold.
    """
    if not raw_scores:
        return 0.0
    top = raw_scores[0]
    high_matches = sum(1 for s in raw_scores[1:] if s >= 0.72)
    boost = min(high_matches * 0.025, 0.08)
    confidence = min(top + boost, 1.0)
    return round(confidence, 4)


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

    settings = get_settings()
    matches = search_faiss(ocr_text, exam_slug, top_k=top_k)

    # Filter out noise: FAISS always returns nearest neighbours even for unrelated text.
    # Only keep matches whose cosine similarity is at or above the review threshold.
    min_score = settings.ALERT_THRESHOLD_REVIEW  # 0.45 by default
    matches = [(idx, score) for idx, score in matches if score >= min_score]

    raw_scores = [score for _, score in matches]
    confidence = compute_confidence(raw_scores)
    label = confidence_label(confidence)

    matched_questions = []
    for idx, score in matches:
        text = question_texts[idx] if question_texts and idx < len(question_texts) else ""
        matched_questions.append(MatchedQuestion(question_id=idx, text=text, score=score))

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
