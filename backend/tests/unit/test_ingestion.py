import os
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from findleaks.ingestion import (
    IngestionProgress,
    build_faiss_index,
    build_index_for_exam,
    clean_text,
    compute_file_hash,
    detect_mime_type,
    ingest_file,
    is_allowed_file,
    split_questions,
)


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------

def test_clean_text_lowercases():
    assert clean_text("HELLO WORLD") == "hello world"


def test_clean_text_removes_stopwords():
    result = clean_text("What is the speed of light?")
    assert "is" not in result.split()
    assert "the" not in result.split()
    assert "of" not in result.split()


def test_clean_text_strips_special_chars():
    result = clean_text("Q1. What is 2+2? #test")
    assert "+" not in result
    assert "#" not in result


def test_clean_text_handles_empty():
    assert clean_text("") == ""


def test_clean_text_normalises_unicode():
    result = clean_text("café résumé")
    assert "caf" in result or "cafe" in result


# ---------------------------------------------------------------------------
# split_questions
# ---------------------------------------------------------------------------

def test_split_questions_by_q_marker():
    text = (
        "Q1. Explain the process of photosynthesis in detail.\n"
        "Q2. Describe osmosis and its biological significance.\n"
        "Q3. What is the structure of a DNA molecule?"
    )
    questions = split_questions(text)
    assert len(questions) == 3


def test_split_questions_by_numbered_list():
    text = (
        "1. Explain Newton's first law of motion with examples.\n"
        "2. Define acceleration and give its SI unit.\n"
        "3. What is the difference between speed and velocity?"
    )
    questions = split_questions(text)
    assert len(questions) == 3


def test_split_questions_by_paragraph_gaps():
    text = (
        "Explain the process of photosynthesis in detail.\n\n"
        "Describe the structure of a DNA molecule.\n\n"
        "What is the role of mitochondria in cellular respiration?"
    )
    questions = split_questions(text)
    assert len(questions) == 3


def test_split_questions_empty_input():
    assert split_questions("") == []


def test_split_questions_short_text():
    assert split_questions("Too short") == []


def test_split_questions_fallback_single_block():
    text = "Explain the entire process of photosynthesis with examples and diagrams."
    questions = split_questions(text)
    assert len(questions) == 1


# ---------------------------------------------------------------------------
# compute_file_hash
# ---------------------------------------------------------------------------

def test_compute_file_hash_is_deterministic():
    content = b"hello world"
    assert compute_file_hash(content) == compute_file_hash(content)


def test_compute_file_hash_different_for_different_content():
    assert compute_file_hash(b"abc") != compute_file_hash(b"xyz")


def test_compute_file_hash_returns_hex_string():
    h = compute_file_hash(b"test")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# detect_mime_type / is_allowed_file
# ---------------------------------------------------------------------------

def test_detect_pdf_magic():
    pdf_magic = b"%PDF-1.4 rest of content"
    assert detect_mime_type(pdf_magic) == "application/pdf"


def test_detect_png_magic():
    png_magic = b"\x89PNG\r\n\x1a\nrest"
    assert detect_mime_type(png_magic) == "image/png"


def test_detect_jpeg_magic():
    jpeg_magic = b"\xff\xd8\xff\xe0rest"
    assert detect_mime_type(jpeg_magic) == "image/jpeg"


def test_detect_unknown_returns_none():
    assert detect_mime_type(b"this is plain text") is None


def test_is_allowed_file_pdf():
    assert is_allowed_file(b"%PDF-1.4 ") is True


def test_is_allowed_file_rejects_unknown():
    assert is_allowed_file(b"<html>notallowed</html>") is False


def test_is_allowed_file_rejects_exe():
    assert is_allowed_file(b"MZ\x90\x00malware") is False


# ---------------------------------------------------------------------------
# IngestionProgress
# ---------------------------------------------------------------------------

def test_ingestion_progress_emits_events():
    p = IngestionProgress()
    p.emit("progress", percent=50, message="halfway")
    p.emit("complete", question_count=10)
    assert len(p.events) == 2
    assert p.events[0]["type"] == "progress"
    assert p.events[0]["percent"] == 50
    assert p.events[1]["type"] == "complete"
    assert p.events[1]["question_count"] == 10


# ---------------------------------------------------------------------------
# build_faiss_index (no model needed)
# ---------------------------------------------------------------------------

def test_build_faiss_index_creates_index():
    embeddings = np.random.randn(5, 384).astype(np.float32)
    index = build_faiss_index(embeddings)
    assert index.ntotal == 5


def test_build_faiss_index_dimension_matches():
    embeddings = np.random.randn(3, 384).astype(np.float32)
    index = build_faiss_index(embeddings)
    assert index.d == 384


def test_build_faiss_index_vectors_normalized():
    """After normalisation, inner product with itself ≈ 1.0."""
    embeddings = np.random.randn(4, 128).astype(np.float32)
    index = build_faiss_index(embeddings)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    normalized = embeddings / norms
    D, I = index.search(normalized[:1], 1)
    assert abs(D[0][0] - 1.0) < 1e-3


# ---------------------------------------------------------------------------
# ingest_file (mocked OCR/model)
# ---------------------------------------------------------------------------

def test_ingest_file_rejects_invalid_type():
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(ValueError, match="Unsupported"):
            ingest_file(b"<html>bad</html>", "page.html", "exam-1", tmp)


def test_ingest_file_with_mock_pdf(tmp_path):
    fake_pdf = b"%PDF-1.4 fake pdf content"
    with patch("findleaks.ingestion.extract_text_from_pdf") as mock_extract:
        mock_extract.return_value = (
            "Q1. What is photosynthesis?\n"
            "Q2. Describe osmosis.\n"
            "Q3. What is DNA replication?"
        )
        questions = ingest_file(fake_pdf, "exam.pdf", "exam-1", str(tmp_path))
    assert len(questions) == 3


# ---------------------------------------------------------------------------
# build_index_for_exam (mocked sentence model + FAISS)
# ---------------------------------------------------------------------------

def test_build_index_for_exam_empty_raises():
    with pytest.raises(ValueError, match="No questions"):
        build_index_for_exam([], "exam-slug", "/tmp/indexes")


def test_build_index_for_exam_all_empty_after_clean_raises():
    with pytest.raises(ValueError):
        build_index_for_exam(["a", "b", "c"], "exam-slug", "/tmp/indexes")


def test_build_index_for_exam_success(tmp_path):
    questions = [
        "What is the speed of light in vacuum?",
        "Describe the process of photosynthesis in plants.",
        "Explain Newton's second law of motion.",
        "What is the atomic number of carbon?",
    ]

    mock_index = MagicMock()
    mock_index.ntotal = len(questions)

    mock_embeddings = np.random.randn(len(questions), 384).astype(np.float32)

    progress = IngestionProgress()

    with (
        patch("findleaks.ingestion.embed_questions", return_value=mock_embeddings),
        patch("findleaks.ingestion.build_faiss_index", return_value=mock_index),
        patch("findleaks.ingestion.save_faiss_index", return_value=str(tmp_path / "exam.index")),
    ):
        count, path = build_index_for_exam(questions, "test-exam", str(tmp_path), progress)

    assert count == len(questions)
    complete_events = [e for e in progress.events if e["type"] == "complete"]
    assert len(complete_events) == 1
    assert complete_events[0]["question_count"] == len(questions)
