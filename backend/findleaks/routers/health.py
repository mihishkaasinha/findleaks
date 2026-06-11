import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from findleaks.database import get_db
from findleaks.models import Exam, Leak
from findleaks.schemas import HealthResponse
from findleaks.state import faiss_indexes

logger = structlog.get_logger()
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    db_status = "error"
    exams_monitored = 0
    active_leaks = 0

    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
        exams_monitored = (await db.execute(select(func.count(Exam.id)))).scalar() or 0
        active_leaks = (
            await db.execute(
                select(func.count(Leak.id)).where(Leak.status.in_(["new", "acknowledged"]))
            )
        ).scalar() or 0
    except Exception as exc:
        logger.warning("health_check_db_error", error=str(exc))

    return HealthResponse(
        status="operational" if db_status == "connected" else "degraded",
        exams_monitored=exams_monitored,
        active_leaks=active_leaks,
        db_status=db_status,
        indexes_loaded=len(faiss_indexes),
    )
