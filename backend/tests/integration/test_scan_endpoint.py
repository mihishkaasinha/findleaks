import io
from unittest.mock import patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TOKEN = "test-secret-key"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PDF_MAGIC = b"%PDF-1.4 fake content for testing purposes only"
PNG_MAGIC = b"\x89PNG\r\n\x1a\nfake png content for testing"
BAD_FILE = b"<html>this is not an allowed file type</html>"

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def client():
    from app import create_app
    from findleaks.database import Base, get_db

    _engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with _session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    _app = create_app()
    _app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=_app), base_url="http://test"
    ) as ac:
        yield ac

    _app.dependency_overrides.clear()
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


# ---------------------------------------------------------------------------
# Exam CRUD
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_exam_success(client):
    resp = await client.post(
        "/api/exams",
        json={
            "name": "NEET 2025",
            "alert_recipients": ["admin@nta.ac.in"],
            "keywords": ["biology", "chemistry"],
        },
        headers=AUTH,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "neet-2025"
    assert data["name"] == "NEET 2025"


@pytest.mark.anyio
async def test_create_exam_requires_auth(client):
    resp = await client.post(
        "/api/exams",
        json={"name": "Unauthorized Exam", "alert_recipients": ["x@x.com"]},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_create_exam_duplicate_slug_returns_409(client):
    payload = {"name": "JEE 2025", "alert_recipients": ["admin@jeemain.ac.in"]}
    await client.post("/api/exams", json=payload, headers=AUTH)
    resp = await client.post("/api/exams", json=payload, headers=AUTH)
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_list_exams_returns_array(client):
    await client.post(
        "/api/exams",
        json={"name": "List Test Exam", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    resp = await client.get("/api/exams", headers=AUTH)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_get_exam_not_found(client):
    resp = await client.get("/api/exams/99999", headers=AUTH)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Upload questions — magic byte validation
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_upload_rejects_invalid_file_type(client):
    create_resp = await client.post(
        "/api/exams",
        json={"name": "Upload Reject Test", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    exam_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/exams/{exam_id}/upload-questions",
        files={"file": ("bad.html", io.BytesIO(BAD_FILE), "text/html")},
        headers=AUTH,
    )
    assert resp.status_code == 415


@pytest.mark.anyio
async def test_upload_accepts_valid_pdf(client):
    create_resp = await client.post(
        "/api/exams",
        json={"name": "PDF Upload Test", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    exam_id = create_resp.json()["id"]

    with (
        patch("findleaks.routers.exams.ingest_file", return_value=["Q1 question text here"]),
        patch("findleaks.routers.exams.build_index_for_exam", return_value=(1, "/tmp/x.index")),
    ):
        resp = await client.post(
            f"/api/exams/{exam_id}/upload-questions",
            files={"file": ("bank.pdf", io.BytesIO(PDF_MAGIC), "application/pdf")},
            headers=AUTH,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processing"
    assert "task_id" in data
    assert data["exam_id"] == exam_id


# ---------------------------------------------------------------------------
# Scan endpoint
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_scan_rejects_invalid_file(client):
    create_resp = await client.post(
        "/api/exams",
        json={"name": "Scan Reject Test", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    exam_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/exams/{exam_id}/scan",
        files={"file": ("bad.exe", io.BytesIO(BAD_FILE), "application/octet-stream")},
        headers=AUTH,
    )
    assert resp.status_code == 415


@pytest.mark.anyio
async def test_scan_returns_clean_result(client):
    create_resp = await client.post(
        "/api/exams",
        json={"name": "Clean Scan Exam", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    exam_id = create_resp.json()["id"]

    from findleaks.detector import DetectionResult
    mock_result = DetectionResult(
        ocr_text="unrelated text",
        confidence=0.1,
        confidence_label="clean",
    )

    with patch("findleaks.routers.exams.detect", return_value=mock_result):
        resp = await client.post(
            f"/api/exams/{exam_id}/scan",
            files={"file": ("image.png", io.BytesIO(PNG_MAGIC), "image/png")},
            headers=AUTH,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["app"] == "FINDLEAKS"
    assert data["leak_detected"] is False
    assert data["confidence_label"] == "clean"
    assert data["leak_id"] is None


@pytest.mark.anyio
async def test_scan_returns_high_confidence_leak(client):
    create_resp = await client.post(
        "/api/exams",
        json={"name": "High Leak Exam", "alert_recipients": ["admin@exam.com"]},
        headers=AUTH,
    )
    exam_id = create_resp.json()["id"]

    from findleaks.detector import DetectionResult, MatchedQuestion
    mock_result = DetectionResult(
        ocr_text="What is the velocity of light in vacuum?",
        confidence=0.91,
        confidence_label="high",
        matched_questions=[
            MatchedQuestion(question_id=0, text="Speed of light question", score=0.91),
        ],
        top_score=0.91,
    )

    with patch("findleaks.routers.exams.detect", return_value=mock_result):
        resp = await client.post(
            f"/api/exams/{exam_id}/scan",
            files={"file": ("leak.png", io.BytesIO(PNG_MAGIC), "image/png")},
            headers=AUTH,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["leak_detected"] is True
    assert data["confidence"] == 0.91
    assert data["confidence_label"] == "high"
    assert data["leak_id"] is not None
    assert len(data["matched_excerpts"]) == 1


@pytest.mark.anyio
async def test_scan_dedup_returns_existing(client):
    create_resp = await client.post(
        "/api/exams",
        json={"name": "Dedup Exam", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    exam_id = create_resp.json()["id"]

    from findleaks.detector import DetectionResult, MatchedQuestion
    mock_result = DetectionResult(
        ocr_text="leaked question text here",
        confidence=0.85,
        confidence_label="high",
        matched_questions=[MatchedQuestion(question_id=0, text="q", score=0.85)],
        top_score=0.85,
    )

    same_image = PNG_MAGIC + b"unique_content_for_dedup_test_1234567890"

    with patch("findleaks.routers.exams.detect", return_value=mock_result):
        r1 = await client.post(
            f"/api/exams/{exam_id}/scan",
            files={"file": ("img.png", io.BytesIO(same_image), "image/png")},
            headers=AUTH,
        )
        r2 = await client.post(
            f"/api/exams/{exam_id}/scan",
            files={"file": ("img.png", io.BytesIO(same_image), "image/png")},
            headers=AUTH,
        )

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"
    assert r2.json()["leak_id"] == r1.json()["leak_id"]


@pytest.mark.anyio
async def test_scan_exam_not_found(client):
    resp = await client.post(
        "/api/exams/99999/scan",
        files={"file": ("img.png", io.BytesIO(PNG_MAGIC), "image/png")},
        headers=AUTH,
    )
    assert resp.status_code == 404
