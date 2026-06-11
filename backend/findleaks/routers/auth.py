import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from findleaks.auth import get_current_user, verify_password
from findleaks.config import get_settings
from findleaks.schemas import LoginRequest, LoginResponse, MeResponse

logger = structlog.get_logger()
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["auth"])


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
