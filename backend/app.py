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
    import asyncio
    settings = get_settings()
    logger.info("startup_begin", app=settings.APP_NAME)

    # Fast sync work — done before accepting traffic
    await create_tables()
    logger.info("database_tables_ready")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.FAISS_INDEX_DIR, exist_ok=True)
    # Load any already-saved indexes from disk (fast — just reads files)
    _load_faiss_indexes(settings.FAISS_INDEX_DIR)

    # Yield immediately so /api/health can respond and Railway healthcheck passes.
    # Model loading + index rebuilding run in the background.
    async def _warm_up():
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _load_sentence_model)
        await _rebuild_missing_indexes(settings.FAISS_INDEX_DIR)
        await _load_question_banks()
        logger.info("startup_complete", app=settings.APP_NAME)

    asyncio.create_task(_warm_up())
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


async def _load_question_banks() -> None:
    """
    Populate state.question_bank for every FAISS index that was loaded from
    disk at startup (not rebuilt — those are handled by build_index_for_exam).
    """
    from findleaks import state
    from findleaks.database import AsyncSessionLocal
    from findleaks.models import Exam, Question
    from sqlalchemy import select

    slugs_missing = [s for s in state.faiss_indexes if s not in state.question_bank]
    if not slugs_missing:
        return
    try:
        async with AsyncSessionLocal() as session:
            exams = (await session.execute(
                select(Exam).where(Exam.slug.in_(slugs_missing))
            )).scalars().all()
            for exam in exams:
                rows = (await session.execute(
                    select(Question.question_text)
                    .where(Question.exam_id == exam.id)
                    .order_by(Question.id)
                )).scalars().all()
                state.question_bank[exam.slug] = list(rows)
                logger.info("question_bank_loaded", slug=exam.slug, questions=len(rows))
    except Exception as exc:
        logger.error("load_question_banks_failed", error=str(exc))


def _load_sentence_model() -> None:
    from findleaks import state
    try:
        from sentence_transformers import SentenceTransformer
        state.sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("sentence_model_loaded")
    except Exception as exc:
        logger.warning("sentence_model_load_failed", error=str(exc))


async def _rebuild_missing_indexes(index_dir: str) -> None:
    """
    For every exam in the DB that has questions but no FAISS index on disk,
    rebuild the index automatically so it survives redeployments.
    """
    import asyncio
    import functools
    from findleaks import state
    from findleaks.database import AsyncSessionLocal
    from findleaks.models import Exam, Question
    from findleaks.ingestion import build_index_for_exam, clean_text
    from sqlalchemy import select

    if state.sentence_model is None:
        logger.warning("rebuild_skipped_no_model")
        return

    try:
        async with AsyncSessionLocal() as session:
            exams = (await session.execute(select(Exam))).scalars().all()
            for exam in exams:
                index_path = os.path.join(index_dir, f"{exam.slug}.index")
                if exam.slug in state.faiss_indexes:
                    continue
                if os.path.exists(index_path):
                    continue
                rows = (await session.execute(
                    select(Question.question_text).where(Question.exam_id == exam.id)
                )).scalars().all()
                if not rows:
                    continue
                questions = list(rows)
                logger.info("rebuilding_faiss_index", slug=exam.slug, questions=len(questions))
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        functools.partial(
                            build_index_for_exam,
                            questions, exam.slug, index_dir,
                        ),
                    )
                    logger.info("faiss_index_rebuilt", slug=exam.slug)
                except Exception as exc:
                    logger.error("faiss_rebuild_failed", slug=exam.slug, error=str(exc))
    except Exception as exc:
        logger.error("rebuild_missing_indexes_failed", error=str(exc))


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
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        if request.method == "OPTIONS":
            from fastapi.responses import Response as _Resp
            r = _Resp(status_code=200)
            r.headers["Access-Control-Allow-Origin"] = "*"
            r.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
            r.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            r.headers["Access-Control-Max-Age"] = "86400"
            return r
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
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
