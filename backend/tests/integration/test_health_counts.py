"""
Regression test: health endpoint must return correct exams_monitored
and active_leaks counts (previously broken by invalid SQLAlchemy query).
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


@pytest.mark.anyio
async def test_health_counts_zero_initially(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["exams_monitored"] == 0
    assert data["active_leaks"] == 0


@pytest.mark.anyio
async def test_health_counts_increment_after_exam_created(client):
    await client.post(
        "/api/exams",
        json={"name": "Count Test Exam", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    await client.post(
        "/api/exams",
        json={"name": "Count Test Exam 2", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["exams_monitored"] == 2


@pytest.mark.anyio
async def test_health_active_leaks_counts_new_leaks(client):
    import io
    from unittest.mock import patch
    from findleaks.detector import DetectionResult, MatchedQuestion

    create = await client.post(
        "/api/exams",
        json={"name": "Leak Count Exam", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    exam_id = create.json()["id"]

    PNG = b"\x89PNG\r\n\x1a\nfake"
    mock_result = DetectionResult(
        ocr_text="leaked text here",
        confidence=0.85,
        confidence_label="high",
        matched_questions=[MatchedQuestion(question_id=0, text="q", score=0.85)],
        top_score=0.85,
    )
    with patch("findleaks.routers.exams.detect", return_value=mock_result):
        await client.post(
            f"/api/exams/{exam_id}/scan",
            files={"file": ("img.png", io.BytesIO(PNG), "image/png")},
            headers=AUTH,
        )

    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["active_leaks"] == 1
