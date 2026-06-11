from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from findleaks.detector import (
    DetectionResult,
    MatchedQuestion,
    compute_confidence,
    confidence_label,
    detect,
    search_faiss,
)


# ---------------------------------------------------------------------------
# compute_confidence
# ---------------------------------------------------------------------------

def test_confidence_empty_scores():
    assert compute_confidence([]) == 0.0


def test_confidence_single_score():
    assert compute_confidence([0.9]) == 0.9


def test_confidence_multiple_scores_weighted():
    scores = [0.9, 0.8, 0.7]
    result = compute_confidence(scores)
    assert 0.7 <= result <= 0.9


def test_confidence_capped_at_1():
    assert compute_confidence([1.0, 1.0, 1.0]) <= 1.0


def test_confidence_non_negative():
    assert compute_confidence([0.0, 0.0]) >= 0.0


def test_confidence_decreasing_weights():
    high_scores = [0.95, 0.1, 0.1]
    low_scores = [0.1, 0.95, 0.1]
    assert compute_confidence(high_scores) > compute_confidence(low_scores)


# ---------------------------------------------------------------------------
# confidence_label
# ---------------------------------------------------------------------------

def test_label_high(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("SMTP_HOST", "s")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASS", "p")
    from findleaks.config import get_settings
    get_settings.cache_clear()
    assert confidence_label(0.85) == "high"
    get_settings.cache_clear()


def test_label_review(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("SMTP_HOST", "s")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASS", "p")
    from findleaks.config import get_settings
    get_settings.cache_clear()
    assert confidence_label(0.65) == "review"
    get_settings.cache_clear()


def test_label_clean(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("SMTP_HOST", "s")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASS", "p")
    from findleaks.config import get_settings
    get_settings.cache_clear()
    assert confidence_label(0.3) == "clean"
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# search_faiss
# ---------------------------------------------------------------------------

def test_search_faiss_returns_empty_for_empty_text():
    result = search_faiss("", "exam-slug")
    assert result == []


def test_search_faiss_returns_empty_when_no_index():
    import findleaks.state as state
    state.faiss_indexes = {}
    result = search_faiss("What is photosynthesis?", "nonexistent-exam")
    assert result == []


def test_search_faiss_returns_empty_when_model_none():
    import findleaks.state as state
    state.sentence_model = None
    mock_index = MagicMock()
    mock_index.ntotal = 5
    state.faiss_indexes["test-exam"] = mock_index
    result = search_faiss("What is photosynthesis?", "test-exam")
    assert result == []
    state.faiss_indexes.pop("test-exam", None)


def test_search_faiss_returns_matches():
    import findleaks.state as state

    mock_model = MagicMock()
    mock_embedding = np.random.randn(1, 384).astype(np.float32)
    mock_model.encode.return_value = mock_embedding

    mock_index = MagicMock()
    mock_index.ntotal = 3
    mock_index.search.return_value = (
        np.array([[0.92, 0.85, 0.71]]),
        np.array([[0, 1, 2]]),
    )

    state.sentence_model = mock_model
    state.faiss_indexes["mock-exam"] = mock_index

    results = search_faiss("What is photosynthesis process?", "mock-exam", top_k=3)

    assert len(results) == 3
    assert results[0][1] >= results[1][1]  # sorted descending
    state.faiss_indexes.pop("mock-exam", None)
    state.sentence_model = None


# ---------------------------------------------------------------------------
# detect (full pipeline, mocked OCR + FAISS)
# ---------------------------------------------------------------------------

def test_detect_returns_clean_when_ocr_empty():
    with patch("findleaks.detector.ocr_image", return_value=""):
        result = detect(b"fake-image-bytes", "exam-slug")
    assert result.confidence == 0.0
    assert result.confidence_label == "clean"
    assert result.ocr_text == ""


def test_detect_returns_clean_when_no_faiss_matches():
    with patch("findleaks.detector.ocr_image", return_value="Some extracted text from image"):
        with patch("findleaks.detector.search_faiss", return_value=[]):
            result = detect(b"fake-image-bytes", "exam-slug")
    assert result.confidence == 0.0
    assert result.matched_questions == []


def test_detect_high_confidence_with_matches():
    with patch("findleaks.detector.ocr_image", return_value="What is the speed of light?"):
        with patch(
            "findleaks.detector.search_faiss",
            return_value=[(0, 0.93), (1, 0.88), (2, 0.81)],
        ):
            result = detect(
                b"fake",
                "exam-slug",
                question_texts=["Speed of light question", "Another question", "Third question"],
            )
    assert result.confidence > 0.80
    assert result.confidence_label == "high"
    assert len(result.matched_questions) == 3
    assert result.matched_questions[0].text == "Speed of light question"


def test_detect_populates_matched_questions_without_texts():
    with patch("findleaks.detector.ocr_image", return_value="Newton's first law of motion"):
        with patch(
            "findleaks.detector.search_faiss",
            return_value=[(2, 0.75)],
        ):
            result = detect(b"fake", "exam-slug")
    assert len(result.matched_questions) == 1
    assert result.matched_questions[0].text == ""
    assert result.matched_questions[0].question_id == 2


def test_detect_top_score_set_correctly():
    with patch("findleaks.detector.ocr_image", return_value="Some text from leaked paper"):
        with patch(
            "findleaks.detector.search_faiss",
            return_value=[(0, 0.91), (1, 0.72)],
        ):
            result = detect(b"fake", "exam-slug")
    assert result.top_score == 0.91
