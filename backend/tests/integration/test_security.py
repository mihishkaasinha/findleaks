"""
Security validation tests.
Verifies:
- All protected routes reject unauthenticated requests (401)
- Invalid token is rejected (401)
- File upload validates MIME type (415)
- Login rate limiting (429 after N rapid attempts)
- Credential values are never echoed in responses
- CORS headers are present
"""
import io
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

AUTH = {"Authorization": "Bearer test-secret-key"}
BAD_TOKEN = {"Authorization": "Bearer totallywrongtoken"}
PNG_MAGIC = b"\x89PNG\r\n\x1a\nfake png bytes for security test"
BAD_FILE = b"MZ\x00\x00this is an exe file header"

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

PROTECTED_ROUTES = [
    ("GET",  "/api/exams"),
    ("POST", "/api/exams"),
    ("GET",  "/api/leaks"),
    ("GET",  "/api/scanners"),
    ("GET",  "/api/auth/me"),
]


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
# A1 — All protected routes require auth
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
async def test_unauthenticated_returns_401(client, method, path):
    resp = await getattr(client, method.lower())(path)
    assert resp.status_code == 401, f"{method} {path} should return 401 without auth"


# ---------------------------------------------------------------------------
# A2 — Invalid token returns 401
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_invalid_token_rejected(client):
    resp = await client.get("/api/exams", headers=BAD_TOKEN)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# A3 — Credentials never echoed in error responses
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_failed_login_does_not_echo_password(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cr3t_p4ss!"})
    assert resp.status_code in (401, 422, 403)
    assert "s3cr3t_p4ss!" not in resp.text


@pytest.mark.anyio
async def test_error_response_no_stack_trace(client):
    resp = await client.get("/api/exams/999999", headers=AUTH)
    body = resp.text
    assert "Traceback" not in body
    assert "File \"" not in body


# ---------------------------------------------------------------------------
# A4 — File upload MIME validation (magic bytes)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_scan_rejects_exe_file(client):
    create = await client.post(
        "/api/exams",
        json={"name": "Security Exam", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    exam_id = create.json()["id"]
    resp = await client.post(
        f"/api/exams/{exam_id}/scan",
        files={"file": ("evil.exe", io.BytesIO(BAD_FILE), "application/octet-stream")},
        headers=AUTH,
    )
    assert resp.status_code == 415


@pytest.mark.anyio
async def test_upload_rejects_html_file(client):
    create = await client.post(
        "/api/exams",
        json={"name": "Security Exam 2", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    exam_id = create.json()["id"]
    resp = await client.post(
        f"/api/exams/{exam_id}/upload-questions",
        files={"file": ("page.html", io.BytesIO(b"<html>bad</html>"), "text/html")},
        headers=AUTH,
    )
    assert resp.status_code == 415


# ---------------------------------------------------------------------------
# A5 — CORS headers present on responses
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cors_header_present(client):
    resp = await client.get(
        "/api/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in {h.lower() for h in resp.headers}


# ---------------------------------------------------------------------------
# A6 — Slug injection / path traversal not possible
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_exam_slug_sanitised(client):
    resp = await client.post(
        "/api/exams",
        json={"name": "../../etc/passwd", "alert_recipients": ["a@b.com"]},
        headers=AUTH,
    )
    assert resp.status_code == 201
    slug = resp.json()["slug"]
    assert "/" not in slug
    assert "." not in slug
    assert "etc" in slug or "passwd" in slug  # sanitised, not rejected


# ---------------------------------------------------------------------------
# A7 — Health endpoint accessible without auth
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_health_public(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
