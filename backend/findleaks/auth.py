import secrets
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from findleaks.config import get_settings

_bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def create_token() -> str:
    """Generate a cryptographically secure bearer token."""
    return secrets.token_urlsafe(48)


def validate_token(token: str) -> bool:
    settings = get_settings()
    expected = settings.SECRET_KEY
    return secrets.compare_digest(token, expected)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    if credentials is None or not validate_token(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = get_settings()
    return {"username": settings.ADMIN_USERNAME, "role": "admin"}


async def get_current_user_sse(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    token: Optional[str] = Query(default=None),
) -> dict:
    """Auth dependency for SSE endpoints — accepts token via query param as fallback.
    EventSource (browser) cannot set Authorization headers, so ?token=xxx is used instead.
    """
    raw = (credentials.credentials if credentials else None) or token
    if not raw or not validate_token(raw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = get_settings()
    return {"username": settings.ADMIN_USERNAME, "role": "admin"}
