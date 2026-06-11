import secrets
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
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
