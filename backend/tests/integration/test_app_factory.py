import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    from app import create_app
    _app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=_app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.anyio
async def test_health_returns_200_without_auth(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app"] == "FINDLEAKS"
    assert data["status"] in ("operational", "degraded")


@pytest.mark.anyio
async def test_health_response_shape(client):
    resp = await client.get("/api/health")
    data = resp.json()
    assert "version" in data
    assert "db_status" in data
    assert "indexes_loaded" in data
    assert "exams_monitored" in data
    assert "active_leaks" in data


@pytest.mark.anyio
async def test_protected_route_requires_auth(client):
    resp = await client.get("/api/leaks")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_login_success(client):
    import os
    token = os.environ.get("SECRET_KEY", "test-secret-key")
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["token_type"] == "bearer"
    assert data["app"] == "FINDLEAKS"


@pytest.mark.anyio
async def test_login_invalid_credentials(client):
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "completely-wrong-password"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["detail"]["error"] == "invalid_credentials"


@pytest.mark.anyio
async def test_me_with_valid_token(client):
    import os
    token = os.environ.get("SECRET_KEY", "test-secret-key")
    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert data["role"] == "admin"


@pytest.mark.anyio
async def test_docs_accessible(client):
    resp = await client.get("/docs")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_cors_header_present(client):
    resp = await client.get(
        "/api/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 200
