from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from findleaks.auth import get_current_user
from findleaks.database import get_db
from findleaks.models import Exam, ScannerStatus
from findleaks.schemas import ScannerItem, ScannerPatch
from findleaks import state

logger = structlog.get_logger()
router = APIRouter(prefix="/scanners", tags=["scanners"])


def _scanner_key(exam_id: int, platform: str) -> str:
    return f"{exam_id}:{platform}"


class ScannerCreate(BaseModel):
    exam_id: int
    platform: str  # "twitter" | "telegram"


@router.post("", status_code=201)
async def create_scanner(
    body: ScannerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    if body.platform not in ("twitter", "telegram"):
        raise HTTPException(status_code=400, detail={"error": "unsupported_platform", "allowed": ["twitter", "telegram"]})
    exam = (await db.execute(select(Exam).where(Exam.id == body.exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail={"error": "exam_not_found"})
    existing = (await db.execute(
        select(ScannerStatus).where(ScannerStatus.exam_id == body.exam_id, ScannerStatus.platform == body.platform)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail={"error": "scanner_already_exists"})
    row = ScannerStatus(exam_id=body.exam_id, platform=body.platform, enabled=False)
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return {"id": row.id, "exam_id": row.exam_id, "platform": row.platform, "enabled": row.enabled}


@router.get("", response_model=list[ScannerItem])
async def list_scanners(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[ScannerItem]:
    result = await db.execute(select(ScannerStatus))
    rows = result.scalars().all()
    items = []
    for row in rows:
        key = _scanner_key(row.exam_id, row.platform)
        scanner = state.scanner_threads.get(key)
        items.append(ScannerItem(
            id=row.id,
            exam_id=row.exam_id,
            platform=row.platform,
            enabled=row.enabled,
            running=scanner.is_running if scanner else False,
            last_run=row.last_run,
            images_processed=row.images_processed,
            leaks_detected=row.leaks_detected,
            error_count=row.error_count,
        ))
    return items


@router.post("/{scanner_id}/start")
async def start_scanner(
    scanner_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    row = (await db.execute(
        select(ScannerStatus).where(ScannerStatus.id == scanner_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail={"error": "scanner_not_found"})

    exam = (await db.execute(
        select(Exam).where(Exam.id == row.exam_id)
    )).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail={"error": "exam_not_found"})

    key = _scanner_key(row.exam_id, row.platform)
    if key in state.scanner_threads and state.scanner_threads[key].is_running:
        return {"status": "already_running", "scanner_id": scanner_id}

    keywords = exam.keywords or []
    if row.platform == "twitter":
        from findleaks.scanners.twitter import TwitterScanner
        scanner = TwitterScanner(exam_id=row.exam_id, exam_slug=exam.slug, keywords=keywords)
    elif row.platform == "telegram":
        from findleaks.scanners.telegram import TelegramScanner
        scanner = TelegramScanner(exam_id=row.exam_id, exam_slug=exam.slug, keywords=keywords)
    else:
        raise HTTPException(status_code=400, detail={"error": "unsupported_platform"})

    state.scanner_threads[key] = scanner
    await scanner.start()
    row.enabled = True
    logger.info("scanner_started_via_api", scanner_id=scanner_id, platform=row.platform)
    return {"status": "started", "scanner_id": scanner_id}


@router.post("/{scanner_id}/stop")
async def stop_scanner(
    scanner_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    row = (await db.execute(
        select(ScannerStatus).where(ScannerStatus.id == scanner_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail={"error": "scanner_not_found"})

    key = _scanner_key(row.exam_id, row.platform)
    scanner = state.scanner_threads.get(key)
    if scanner and scanner.is_running:
        await scanner.stop()
        del state.scanner_threads[key]
    row.enabled = False
    logger.info("scanner_stopped_via_api", scanner_id=scanner_id)
    return {"status": "stopped", "scanner_id": scanner_id}


@router.patch("/{scanner_id}", response_model=ScannerItem)
async def patch_scanner(
    scanner_id: int,
    body: ScannerPatch,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ScannerItem:
    row = (await db.execute(
        select(ScannerStatus).where(ScannerStatus.id == scanner_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail={"error": "scanner_not_found"})

    if body.enabled is not None:
        row.enabled = body.enabled

    key = _scanner_key(row.exam_id, row.platform)
    scanner = state.scanner_threads.get(key)
    return ScannerItem(
        id=row.id,
        exam_id=row.exam_id,
        platform=row.platform,
        enabled=row.enabled,
        running=scanner.is_running if scanner else False,
        last_run=row.last_run,
        images_processed=row.images_processed,
        leaks_detected=row.leaks_detected,
        error_count=row.error_count,
    )
