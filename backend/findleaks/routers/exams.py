import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from findleaks.alerts import dispatch_alerts
from findleaks.routers.auth import push_notification
from findleaks.auth import get_current_user, get_current_user_sse
from findleaks.config import get_settings
from findleaks.database import get_db
from findleaks.detector import detect
from findleaks.ingestion import (
    IngestionProgress,
    build_index_for_exam,
    compute_file_hash,
    ingest_file,
    is_allowed_file,
)
from findleaks.models import Exam, Leak, Question
from findleaks.schemas import (
    ExamCreate,
    ExamListItem,
    ExamUpdate,
    ScanResponse,
    UploadResponse,
    MatchedExcerpt,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/exams", tags=["exams"])

_UPLOAD_TASKS: dict[str, IngestionProgress] = {}


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:80]


# ---------------------------------------------------------------------------
# GET /exams
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ExamListItem])
async def list_exams(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[ExamListItem]:
    result = await db.execute(select(Exam).order_by(Exam.created_at.desc()))
    exams = result.scalars().all()
    return [ExamListItem.model_validate(e) for e in exams]


# ---------------------------------------------------------------------------
# POST /exams
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_exam(
    body: ExamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    slug = _slugify(body.name)
    existing = await db.execute(select(Exam).where(Exam.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "slug_conflict", "message": f"Exam '{slug}' already exists"},
        )
    alert_config = {
        "recipients": [str(r) for r in body.alert_recipients],
        "webhooks": body.alert_webhooks or [],
        "sms": [],
    }
    exam = Exam(
        name=body.name,
        slug=slug,
        description=body.description,
        keywords=body.keywords or [],
        alert_config=alert_config,
    )
    db.add(exam)
    await db.flush()
    await db.refresh(exam)
    return {"id": exam.id, "slug": exam.slug, "name": exam.name}


# ---------------------------------------------------------------------------
# GET /exams/{exam_id}
# ---------------------------------------------------------------------------

@router.get("/{exam_id}")
async def get_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail={"error": "exam_not_found"})
    return {
        "id": exam.id, "name": exam.name, "slug": exam.slug,
        "description": exam.description, "question_count": exam.question_count,
        "keywords": exam.keywords, "last_indexed_at": exam.last_indexed_at,
        "created_at": exam.created_at,
    }


# ---------------------------------------------------------------------------
# PATCH /exams/{exam_id}
# ---------------------------------------------------------------------------

@router.patch("/{exam_id}")
async def update_exam(
    exam_id: int,
    body: ExamUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail={"error": "exam_not_found"})
    if body.name is not None:
        exam.name = body.name
    if body.description is not None:
        exam.description = body.description
    if body.keywords is not None:
        exam.keywords = body.keywords
    if body.alert_recipients is not None or body.alert_webhooks is not None:
        cfg = exam.alert_config or {"recipients": [], "webhooks": [], "sms": []}
        if body.alert_recipients is not None:
            cfg["recipients"] = [str(r) for r in body.alert_recipients]
        if body.alert_webhooks is not None:
            cfg["webhooks"] = body.alert_webhooks or []
        exam.alert_config = cfg
    return {"id": exam.id, "name": exam.name, "slug": exam.slug}


# ---------------------------------------------------------------------------
# DELETE /exams/{exam_id}
# ---------------------------------------------------------------------------

@router.delete("/{exam_id}", status_code=204)
async def delete_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> None:
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail={"error": "exam_not_found"})
    await db.delete(exam)


# ---------------------------------------------------------------------------
# GET /exams/{exam_id}/questions
# ---------------------------------------------------------------------------

@router.get("/{exam_id}/questions")
async def list_questions(
    exam_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail={"error": "exam_not_found"})
    from sqlalchemy import func as _func
    total = (await db.execute(select(_func.count(Question.id)).where(Question.exam_id == exam_id))).scalar() or 0
    rows = (await db.execute(
        select(Question).where(Question.exam_id == exam_id)
        .order_by(Question.id).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
        "items": [{"id": q.id, "question_text": q.question_text, "page_number": q.page_number} for q in rows],
    }


# ---------------------------------------------------------------------------
# POST /exams/{exam_id}/upload-questions  (multipart)
# ---------------------------------------------------------------------------

@router.post("/{exam_id}/upload-questions", response_model=UploadResponse)
async def upload_questions(
    exam_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> UploadResponse:
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail={"error": "exam_not_found"})

    content = await file.read()
    if not is_allowed_file(content):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"error": "unsupported_file_type"},
        )

    task_id = str(uuid.uuid4())
    progress = IngestionProgress()
    _UPLOAD_TASKS[task_id] = progress

    settings = get_settings()
    save_dir = f"{settings.UPLOAD_DIR}/{exam.slug}"
    exam_slug = exam.slug
    source_filename = file.filename

    async def run_ingestion():
        from findleaks.database import AsyncSessionLocal
        from findleaks.ingestion import clean_text as _clean
        import functools
        loop = asyncio.get_event_loop()
        try:
            questions = await loop.run_in_executor(
                None,
                functools.partial(
                    ingest_file,
                    content, source_filename or "upload", exam_slug, save_dir, progress,
                ),
            )
            count, _ = await loop.run_in_executor(
                None,
                functools.partial(
                    build_index_for_exam,
                    questions, exam_slug, settings.FAISS_INDEX_DIR, progress,
                ),
            )
            async with AsyncSessionLocal() as bg_session:
                _exam = (
                    await bg_session.execute(select(Exam).where(Exam.id == exam_id))
                ).scalar_one_or_none()
                if _exam:
                    for raw_q in questions:
                        bg_session.add(Question(
                            exam_id=exam_id,
                            question_text=raw_q,
                            cleaned_text=_clean(raw_q),
                            source_file=source_filename,
                        ))
                    _exam.question_count = (_exam.question_count or 0) + count
                    _exam.last_indexed_at = datetime.now(timezone.utc)
                    await bg_session.commit()
            logger.info("ingestion_done", exam_id=exam_id, count=count)
        except Exception as exc:
            progress.emit("error", message=str(exc))
            logger.error("ingestion_failed", exam_id=exam_id, error=str(exc))

    asyncio.create_task(run_ingestion())
    return UploadResponse(task_id=task_id, status="processing", exam_id=exam_id)


# ---------------------------------------------------------------------------
# GET /exams/{exam_id}/upload-status/{task_id}  (REST polling fallback)
# ---------------------------------------------------------------------------

@router.get("/{exam_id}/upload-status/{task_id}")
async def upload_status(
    exam_id: int,
    task_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    progress = _UPLOAD_TASKS.get(task_id)
    if not progress:
        return {"found": False, "done": False}
    events = progress.events
    complete = next((e for e in events if e["type"] == "complete"), None)
    error = next((e for e in events if e["type"] == "error"), None)
    latest_progress = next((e for e in reversed(events) if e["type"] == "progress"), None)
    return {
        "found": True,
        "done": bool(complete or error),
        "complete": complete,
        "error": error,
        "percent": latest_progress.get("percent", 0) if latest_progress else 0,
        "message": (complete or error or latest_progress or {}).get("message", ""),
    }


# ---------------------------------------------------------------------------
# GET /exams/{exam_id}/upload-progress/{task_id}  (SSE)
# ---------------------------------------------------------------------------

@router.get("/{exam_id}/upload-progress/{task_id}")
async def upload_progress(
    exam_id: int,
    task_id: str,
    current_user: dict = Depends(get_current_user_sse),
) -> StreamingResponse:
    progress = _UPLOAD_TASKS.get(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail={"error": "task_not_found"})

    async def event_stream():
        sent = 0
        elapsed = 0
        max_wait = 600  # 10-minute hard timeout
        while elapsed < max_wait:
            events = progress.events[sent:]
            for ev in events:
                yield f"data: {json.dumps(ev)}\n\n"
                sent += 1
            # Check terminal AFTER flushing so complete/error events are never missed
            if any(e["type"] in ("complete", "error") for e in progress.events[:sent]):
                break
            # Keepalive comment — prevents Railway/nginx from killing idle SSE connections
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)
            elapsed += 1
        if elapsed >= max_wait:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Processing timed out'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# POST /exams/{exam_id}/scan
# ---------------------------------------------------------------------------

@router.post("/{exam_id}/scan", response_model=ScanResponse)
async def scan_image(
    exam_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ScanResponse:
    settings = get_settings()

    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail={"error": "exam_not_found"})

    content = await file.read()
    if not is_allowed_file(content):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"error": "unsupported_file_type"},
        )

    file_hash = compute_file_hash(content)
    cutoff = datetime.now(timezone.utc).timestamp() - (settings.SCAN_DEDUP_MINUTES * 60)
    from sqlalchemy import and_
    dup_result = await db.execute(
        select(Leak).where(
            and_(
                Leak.exam_id == exam_id,
                Leak.platform_post_id == file_hash,
                Leak.timestamp >= datetime.fromtimestamp(cutoff, tz=timezone.utc),
            )
        )
    )
    dup = dup_result.scalar_one_or_none()
    if dup:
        return ScanResponse(
            status="duplicate",
            leak_detected=dup.confidence_label in ("high", "review"),
            exam=exam.name,
            exam_id=exam_id,
            confidence=dup.confidence,
            confidence_label=dup.confidence_label,
            matched_questions=len(dup.matched_question_ids or []),
            matched_excerpts=[],
            leak_id=dup.id,
            alert_sent=dup.alert_sent,
            alert_recipients=[],
            timestamp=dup.timestamp,
        )

    q_result = await db.execute(
        select(Question.question_text).where(Question.exam_id == exam_id)
    )
    question_texts = list(q_result.scalars().all())

    detection = detect(content, exam.slug, question_texts=question_texts)

    leak_id = None
    alert_sent = False
    recipients: list[str] = []

    if detection.confidence >= settings.ALERT_THRESHOLD_REVIEW:
        leak = Leak(
            exam_id=exam_id,
            platform="manual",
            platform_post_id=file_hash,
            confidence=detection.confidence,
            confidence_label=detection.confidence_label,
            ocr_text=detection.ocr_text[:2000] if detection.ocr_text else None,
            matched_question_ids=[m.question_id for m in detection.matched_questions],
            matched_excerpts=[
                {"question_id": m.question_id, "text": m.text, "score": m.score}
                for m in detection.matched_questions
            ],
            status="new",
            alert_sent=False,
        )
        db.add(leak)
        await db.flush()
        await db.refresh(leak)
        leak_id = leak.id

        if exam.alert_config and exam.alert_config.get("recipients"):
            recipients = exam.alert_config.get("recipients", [])
            asyncio.create_task(dispatch_alerts(
                leak_id=leak_id,
                exam_name=exam.name,
                platform="manual",
                confidence=detection.confidence,
                confidence_label=detection.confidence_label,
                matched_count=len(detection.matched_questions),
                ocr_text=detection.ocr_text,
                timestamp=datetime.now(timezone.utc),
                alert_config=exam.alert_config,
            ))
            leak.alert_sent = True

    if leak_id:
        push_notification({
            "type": "new_leak",
            "leak_id": leak_id,
            "exam_id": exam_id,
            "exam_name": exam.name,
            "confidence": detection.confidence,
            "confidence_label": detection.confidence_label,
            "platform": "manual",
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    return ScanResponse(
        status="success",
        leak_detected=detection.confidence_label in ("high", "review"),
        exam=exam.name,
        exam_id=exam_id,
        confidence=detection.confidence,
        confidence_label=detection.confidence_label,
        matched_questions=len(detection.matched_questions),
        matched_excerpts=[
            MatchedExcerpt(
                question_id=m.question_id,
                text=m.text,
                score=round(m.score, 4),
            )
            for m in detection.matched_questions
        ],
        ocr_text=detection.ocr_text,
        leak_id=leak_id,
        alert_sent=alert_sent,
        alert_recipients=recipients,
        timestamp=datetime.now(timezone.utc),
    )
