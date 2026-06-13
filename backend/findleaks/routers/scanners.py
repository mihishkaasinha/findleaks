from fastapi import APIRouter, Body, Depends, HTTPException, status
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
    _ALLOWED = ("twitter", "telegram", "telethon", "reddit", "discord", "pastebin")
    if body.platform not in _ALLOWED:
        raise HTTPException(status_code=400, detail={"error": "unsupported_platform", "allowed": list(_ALLOWED)})
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
    elif row.platform == "telethon":
        from findleaks.scanners.telethon_scanner import TelethonScanner
        scanner = TelethonScanner(exam_id=row.exam_id, exam_slug=exam.slug, keywords=keywords)
    elif row.platform == "reddit":
        from findleaks.scanners.reddit import RedditScanner
        scanner = RedditScanner(exam_id=row.exam_id, exam_slug=exam.slug, keywords=keywords)
    elif row.platform == "discord":
        from findleaks.scanners.discord_scanner import DiscordScanner
        scanner = DiscordScanner(exam_id=row.exam_id, exam_slug=exam.slug, keywords=keywords)
    elif row.platform == "pastebin":
        from findleaks.scanners.pastebin import PastebinScanner
        scanner = PastebinScanner(exam_id=row.exam_id, exam_slug=exam.slug, keywords=keywords)
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


import random as _random

_NOISE_TEMPLATES = [
    ("WhatsApp leak",       "seen this in a study group just now: {q} — anyone recognise this paper??"),
    ("Telegram forward",    "forwarded from premium channel 🔥📚 {q} 🔥 DM for full set"),
    ("Discord post",        "bro look what someone dropped in the server lmaooo {q} idk which paper tho"),
    ("Reddit thread",       "Guys my friend shared this snippet: {q}\nDoes anyone know the source exam?"),
    ("Paste dump header",   "===EXAM LEAK=== date:{ts}\n{q}\n===END==="),
]


def _demo_variant(question_text: str) -> tuple[str, str]:
    """Return (variant_label, transformed_content) for demo injection.

    Variants are cycled deterministically within a second so consecutive
    rapid clicks still vary, while repeated calls spread across confidence tiers.
    """
    import datetime, textwrap
    words = question_text.split()
    n = len(words)

    bucket = _random.randint(0, 4)

    if bucket == 0 or n < 8:
        return "verbatim", question_text

    if bucket == 1:
        chunk = " ".join(words[:max(6, int(n * 0.6))])
        return "truncated_60pct", chunk

    if bucket == 2:
        tmpl_label, tmpl = _NOISE_TEMPLATES[_random.randint(0, len(_NOISE_TEMPLATES) - 1)]
        ts = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        noisy = tmpl.format(q=question_text[:300], ts=ts)
        return f"forum_noise({tmpl_label})", noisy

    if bucket == 3:
        sparse = " ".join(words[i] for i in range(0, n, 2))
        return "every_other_word", sparse

    # bucket == 4 — first sentence / first 10 words
    first_sent = question_text.split(".")[0].split("?")[0]
    if len(first_sent.split()) < 5:
        first_sent = " ".join(words[:10])
    return "first_sentence", first_sent


@router.post("/{scanner_id}/inject-paste")
async def inject_paste(
    scanner_id: int,
    content: str = Body(None, embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Demo / test endpoint: run a text snippet directly through the Pastebin
    scanner pipeline without polling pastebin.com.  If `content` is omitted,
    the first question from the exam's question bank is used so a match is
    guaranteed.
    """
    from findleaks.models import Question
    from findleaks.scanners.pastebin import PastebinScanner
    import datetime

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

    variant_label = "custom"
    if not content:
        q_row = (await db.execute(
            select(Question.question_text)
            .where(Question.exam_id == row.exam_id)
            .limit(1)
        )).scalar_one_or_none()
        if not q_row:
            raise HTTPException(status_code=422, detail={"error": "no_questions_in_bank"})
        variant_label, content = _demo_variant(q_row)

    scanner = PastebinScanner(
        exam_id=row.exam_id, exam_slug=exam.slug, keywords=[]
    )
    post_id = f"demo:{datetime.datetime.utcnow().timestamp()}"
    result = await scanner.scan_post(content, post_id)

    logger.info("inject_paste_complete", scanner_id=scanner_id, variant=variant_label, matched=result is not None)
    return {
        "injected": True,
        "variant": variant_label,
        "post_id": post_id,
        "content_preview": content[:120],
        "leak_detected": result is not None,
        "result": result,
    }


@router.post("/{scanner_id}/inject-post")
async def inject_post(
    scanner_id: int,
    content: str = Body(None, embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Generic demo endpoint for Reddit/Discord/Twitter scanners.
    Injects a question-bank snippet directly through scan_post().
    """
    from findleaks.models import Question
    import datetime

    SCANNER_MAP = {
        "reddit": ("findleaks.scanners.reddit", "RedditScanner"),
        "discord": ("findleaks.scanners.discord_scanner", "DiscordScanner"),
        "twitter": ("findleaks.scanners.twitter", "TwitterScanner"),
        "telegram": ("findleaks.scanners.telegram", "TelegramScanner"),
    }

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

    variant_label = "custom"
    if not content:
        q_row = (await db.execute(
            select(Question.question_text)
            .where(Question.exam_id == row.exam_id)
            .limit(1)
        )).scalar_one_or_none()
        if not q_row:
            raise HTTPException(status_code=422, detail={"error": "no_questions_in_bank"})
        variant_label, content = _demo_variant(q_row)

    platform = row.platform
    if platform not in SCANNER_MAP:
        raise HTTPException(status_code=400, detail={"error": f"inject not supported for {platform}"})

    import importlib
    mod_path, cls_name = SCANNER_MAP[platform]
    mod = importlib.import_module(mod_path)
    ScannerCls = getattr(mod, cls_name)
    scanner = ScannerCls(exam_id=row.exam_id, exam_slug=exam.slug, keywords=[])

    post_id = f"demo:{datetime.datetime.utcnow().timestamp()}"
    result = await scanner.scan_post(content, post_id)

    logger.info("inject_post_complete", scanner_id=scanner_id, platform=platform, variant=variant_label, matched=result is not None)
    return {
        "injected": True,
        "platform": platform,
        "variant": variant_label,
        "post_id": post_id,
        "content_preview": content[:120],
        "leak_detected": result is not None,
        "result": result,
    }
