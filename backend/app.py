import os
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from findleaks.config import get_settings
from findleaks.database import create_tables, dispose_engine
from findleaks.routers import alerts, auth, exams, health, leaks, scanners

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("startup_begin", app=settings.APP_NAME)

    await create_tables()
    logger.info("database_tables_ready")

    _load_faiss_indexes(settings.FAISS_INDEX_DIR)
    _load_sentence_model()

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.FAISS_INDEX_DIR, exist_ok=True)

    logger.info("startup_complete", app=settings.APP_NAME)
    yield

    await dispose_engine()
    logger.info("shutdown_complete")


def _load_faiss_indexes(index_dir: str) -> None:
    import glob
    from findleaks import state

    try:
        import faiss  # noqa: F401
        pattern = os.path.join(index_dir, "*.index")
        for path in glob.glob(pattern):
            slug = os.path.splitext(os.path.basename(path))[0]
            try:
                import faiss as _faiss
                state.faiss_indexes[slug] = _faiss.read_index(path)
                logger.info("faiss_index_loaded", slug=slug)
            except Exception as exc:
                logger.warning("faiss_index_load_failed", slug=slug, error=str(exc))
    except ImportError:
        logger.warning("faiss_not_available")


def _load_sentence_model() -> None:
    from findleaks import state
    try:
        from sentence_transformers import SentenceTransformer
        state.sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("sentence_model_loaded")
    except Exception as exc:
        logger.warning("sentence_model_load_failed", error=str(exc))


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="FINDLEAKS API",
        description="Universal Exam Integrity Platform — Find Leaks. Protect Exams.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        ref = str(uuid.uuid4())
        logger.error(
            "unhandled_exception",
            ref=ref,
            path=str(request.url.path),
            error=type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"app": "FINDLEAKS", "error": "internal_error", "ref": ref},
        )

    api_prefix = "/api"
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(exams.router, prefix=api_prefix)
    app.include_router(leaks.router, prefix=api_prefix)
    app.include_router(alerts.router, prefix=api_prefix)
    app.include_router(scanners.router, prefix=api_prefix)

    return app


app = create_app()
