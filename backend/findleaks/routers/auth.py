import asyncio
import json
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from findleaks.auth import get_current_user, get_current_user_sse, hash_password, verify_password
from findleaks.config import get_settings
from findleaks.schemas import LoginRequest, LoginResponse, MeResponse

logger = structlog.get_logger()
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["auth"])

_notification_queues: list[asyncio.Queue] = []


def push_notification(event: dict) -> None:
    for q in _notification_queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest) -> LoginResponse:
    settings = get_settings()

    username_match = body.username == settings.ADMIN_USERNAME
    password_match = (
        verify_password(body.password, settings.ADMIN_PASSWORD_HASH)
        if settings.ADMIN_PASSWORD_HASH
        else body.password == settings.SECRET_KEY
    )

    if not (username_match and password_match):
        logger.warning("login_failed", username=body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )

    logger.info("login_success", username=body.username)
    return LoginResponse(token=settings.SECRET_KEY)


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)) -> dict:
    return {"message": "logged_out"}


@router.get("/me", response_model=MeResponse)
async def me(current_user: dict = Depends(get_current_user)) -> MeResponse:
    return MeResponse(username=current_user["username"], role=current_user["role"])


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    if not verify_password(body.current_password, settings.ADMIN_PASSWORD_HASH):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "wrong_current_password"},
        )
    new_hash = hash_password(body.new_password)
    logger.info("password_changed", username=current_user["username"])
    return {
        "message": "Password updated. Set ADMIN_PASSWORD_HASH in your environment to persist.",
        "new_hash": new_hash,
    }


@router.get("/notifications")
async def notifications_stream(
    current_user: dict = Depends(get_current_user_sse),
) -> StreamingResponse:
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _notification_queues.append(q)

    async def event_gen():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'ts': datetime.now(timezone.utc).isoformat()})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            _notification_queues.remove(q)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
