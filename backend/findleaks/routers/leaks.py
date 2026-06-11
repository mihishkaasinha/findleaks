from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from findleaks.auth import get_current_user
from findleaks.database import get_db
from findleaks.models import Exam, Leak
from findleaks.schemas import LeakItem, LeakListResponse, LeakPatch, LeakPatchResponse

router = APIRouter(prefix="/leaks", tags=["leaks"])


@router.get("", response_model=LeakListResponse)
async def list_leaks(
    exam_id: Optional[int] = Query(None),
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    confidence_label: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> LeakListResponse:
    q = select(Leak)
    if exam_id:
        q = q.where(Leak.exam_id == exam_id)
    if platform:
        q = q.where(Leak.platform == platform)
    if status:
        q = q.where(Leak.status == status)
    if confidence_label:
        q = q.where(Leak.confidence_label == confidence_label)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    q = q.order_by(Leak.timestamp.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    items = []
    for row in rows:
        exam_name = None
        if row.exam_id:
            exam_res = await db.execute(select(Exam.name).where(Exam.id == row.exam_id))
            exam_name = exam_res.scalar_one_or_none()
        items.append(LeakItem(
            id=row.id,
            exam_id=row.exam_id,
            exam_name=exam_name,
            platform=row.platform,
            platform_post_id=row.platform_post_id,
            ocr_text_preview=(row.ocr_text or "")[:300] if row.ocr_text else None,
            confidence=row.confidence,
            confidence_label=row.confidence_label,
            matched_question_count=len(row.matched_question_ids or []),
            timestamp=row.timestamp,
            status=row.status,
            alert_sent=row.alert_sent,
        ))

    return LeakListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, -(-total // page_size)),
        items=items,
    )


@router.patch("/{leak_id}", response_model=LeakPatchResponse)
async def patch_leak(
    leak_id: int,
    body: LeakPatch,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> LeakPatchResponse:
    row = (await db.execute(select(Leak).where(Leak.id == leak_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail={"error": "leak_not_found"})

    allowed = {"acknowledged", "false_positive"}
    if body.status not in allowed:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_status", "allowed": list(allowed)},
        )

    row.status = body.status
    if body.notes is not None:
        row.notes = body.notes

    return LeakPatchResponse(
        id=row.id,
        status=row.status,
        updated_at=datetime.now(timezone.utc),
    )
