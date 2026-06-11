"""
Integration tests for /leaks and /alerts routers.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

AUTH = {"Authorization": "Bearer test-secret-key"}
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def client():
    from app import create_app
    from findleaks.database import Base, get_db

    _engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    _factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with _factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    _app = create_app()
    _app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as ac:
        yield ac

    _app.dependency_overrides.clear()
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


# ---------------------------------------------------------------------------
# Leaks
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_list_leaks_empty(client):
    resp = await client.get("/api/leaks", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.anyio
async def test_list_leaks_requires_auth(client):
    resp = await client.get("/api/leaks")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_list_leaks_filter_by_platform(client):
    resp = await client.get("/api/leaks?platform=twitter", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.anyio
async def test_list_leaks_filter_by_status(client):
    resp = await client.get("/api/leaks?status=new", headers=AUTH)
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_list_leaks_pagination_params(client):
    resp = await client.get("/api/leaks?page=1&page_size=5", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 1
    assert data["page_size"] == 5


@pytest.mark.anyio
async def test_patch_leak_not_found(client):
    resp = await client.patch("/api/leaks/99999", json={"status": "acknowledged"}, headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_patch_leak_invalid_status(client):
    from findleaks.models import Exam, Leak
    from datetime import datetime, timezone

    async with AsyncClient(transport=ASGITransport(app=(await client.__aenter__() if False else None)), base_url="http://test") as _:
        pass

    create_resp = await client.post(
        "/api/exams",
        json={"name": "Leak Test Exam", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    exam_id = create_resp.json()["id"]

    from unittest.mock import patch as mock_patch
    from findleaks.detector import DetectionResult, MatchedQuestion
    mock_result = DetectionResult(
        ocr_text="some leaked text",
        confidence=0.85,
        confidence_label="high",
        matched_questions=[MatchedQuestion(question_id=0, text="q", score=0.85)],
        top_score=0.85,
    )
    PNG_MAGIC = b"\x89PNG\r\n\x1a\nfake png"
    import io

    with mock_patch("findleaks.routers.exams.detect", return_value=mock_result):
        scan_resp = await client.post(
            f"/api/exams/{exam_id}/scan",
            files={"file": ("img.png", io.BytesIO(PNG_MAGIC), "image/png")},
            headers=AUTH,
        )
    leak_id = scan_resp.json()["leak_id"]

    resp = await client.patch(
        f"/api/leaks/{leak_id}",
        json={"status": "invalid_status_value"},
        headers=AUTH,
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_patch_leak_acknowledged(client):
    from unittest.mock import patch as mock_patch
    from findleaks.detector import DetectionResult, MatchedQuestion
    import io

    create_resp = await client.post(
        "/api/exams",
        json={"name": "Ack Exam", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    exam_id = create_resp.json()["id"]

    PNG_MAGIC = b"\x89PNG\r\n\x1a\nfake png content for ack test"
    mock_result = DetectionResult(
        ocr_text="leaked text",
        confidence=0.88,
        confidence_label="high",
        matched_questions=[MatchedQuestion(question_id=0, text="q", score=0.88)],
        top_score=0.88,
    )
    with mock_patch("findleaks.routers.exams.detect", return_value=mock_result):
        scan_resp = await client.post(
            f"/api/exams/{exam_id}/scan",
            files={"file": ("img.png", io.BytesIO(PNG_MAGIC), "image/png")},
            headers=AUTH,
        )
    leak_id = scan_resp.json()["leak_id"]

    patch_resp = await client.patch(
        f"/api/leaks/{leak_id}",
        json={"status": "acknowledged"},
        headers=AUTH,
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["status"] == "acknowledged"
    assert data["id"] == leak_id


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_list_alerts_empty(client):
    resp = await client.get("/api/alerts", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.anyio
async def test_list_alerts_requires_auth(client):
    resp = await client.get("/api/alerts")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_list_alerts_filter_by_method(client):
    resp = await client.get("/api/alerts?method=email", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.anyio
async def test_retry_alert_not_found(client):
    resp = await client.post("/api/alerts/99999/retry", headers=AUTH)
    assert resp.status_code == 404
