from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from findleaks.alerts import render_email_body, send_email_alert, send_webhook_alert
from findleaks.auth import get_current_user
from findleaks.database import get_db
from findleaks.models import Alert, Exam, Leak
from findleaks.schemas import AlertListResponse, AlertObject

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    leak_id: Optional[int] = Query(None),
    method: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AlertListResponse:
    q = select(Alert)
    if leak_id:
        q = q.where(Alert.leak_id == leak_id)
    if method:
        q = q.where(Alert.method == method)
    if status:
        q = q.where(Alert.status == status)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    q = q.order_by(Alert.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return AlertListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, -(-total // page_size)),
        items=[AlertObject.model_validate(row) for row in rows],
    )


@router.post("/{alert_id}/retry")
async def retry_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    row = (await db.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail={"error": "alert_not_found"})

    leak = (await db.execute(select(Leak).where(Leak.id == row.leak_id))).scalar_one_or_none()
    if not leak:
        raise HTTPException(status_code=404, detail={"error": "leak_not_found"})

    exam = (await db.execute(select(Exam).where(Exam.id == leak.exam_id))).scalar_one_or_none()

    exam_name = exam.name if exam else f"Exam #{leak.exam_id}"
    subject = f"[FINDLEAKS] Leak Detected — {exam_name} ({leak.confidence_label.upper()})"
    body = render_email_body(
        exam_name=exam_name,
        platform=leak.platform,
        confidence=leak.confidence,
        confidence_label=leak.confidence_label,
        matched_count=len(leak.matched_question_ids or []),
        ocr_preview=leak.ocr_text or "",
        timestamp=leak.timestamp,
    )

    if row.method == "email":
        result = await send_email_alert(row.sent_to, subject, body, leak_id=None)
    elif row.method == "webhook":
        result = await send_webhook_alert(row.sent_to, {
            "event": "leak_detected", "leak_id": leak.id,
            "exam": exam_name, "confidence": leak.confidence,
        }, leak_id=None)
    else:
        result = {"status": "unsupported_method"}

    row.status = result.get("status", "failed")
    row.sent_at = datetime.now(timezone.utc)

    return {"alert_id": alert_id, "status": row.status}
