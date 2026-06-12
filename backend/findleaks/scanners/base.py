"""
Base class for all social-media scanners.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger()


class BaseScanner(ABC):
    name: str = "base"

    def __init__(self, exam_id: int, exam_slug: str, keywords: list[str]):
        self.exam_id = exam_id
        self.exam_slug = exam_slug
        self.keywords = keywords
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("scanner_started", scanner=self.name, exam=self.exam_slug)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("scanner_stopped", scanner=self.name, exam=self.exam_slug)

    async def _persist_leak(
        self,
        platform: str,
        post_id: str,
        ocr_text: str,
        confidence: float,
        label: str,
        matched_ids: list[int],
        matched_excerpts: list[dict],
        raw_payload: Optional[dict] = None,
    ) -> Optional[int]:
        """
        Persist a detected leak to the database, fire alerts, push SSE notification.
        Returns the new leak_id, or None if deduped/error.
        """
        from findleaks.database import AsyncSessionLocal
        from findleaks.models import Exam, Leak, ScannerStatus
        from findleaks.alerts import dispatch_alerts
        from findleaks.routers.auth import push_notification
        from findleaks.config import get_settings
        from sqlalchemy import select

        settings = get_settings()
        try:
            async with AsyncSessionLocal() as session:
                exam = (await session.execute(
                    select(Exam).where(Exam.id == self.exam_id)
                )).scalar_one_or_none()
                if not exam:
                    return None

                existing = (await session.execute(
                    select(Leak).where(
                        Leak.exam_id == self.exam_id,
                        Leak.platform_post_id == post_id,
                    )
                )).scalar_one_or_none()
                if existing:
                    return existing.id

                leak = Leak(
                    exam_id=self.exam_id,
                    platform=platform,
                    platform_post_id=post_id,
                    ocr_text=ocr_text[:2000] if ocr_text else None,
                    confidence=confidence,
                    confidence_label=label,
                    matched_question_ids=matched_ids,
                    matched_excerpts=matched_excerpts,
                    status="new",
                    alert_sent=False,
                    raw_payload=raw_payload,
                )
                session.add(leak)
                await session.flush()
                await session.refresh(leak)
                leak_id = leak.id

                scanner_row = (await session.execute(
                    select(ScannerStatus).where(
                        ScannerStatus.exam_id == self.exam_id,
                        ScannerStatus.platform == platform,
                    )
                )).scalar_one_or_none()
                if scanner_row:
                    scanner_row.leaks_detected = (scanner_row.leaks_detected or 0) + 1
                    scanner_row.last_run = datetime.now(timezone.utc)

                await session.commit()

            if exam.alert_config and exam.alert_config.get("recipients"):
                asyncio.create_task(dispatch_alerts(
                    leak_id=leak_id,
                    exam_name=exam.name,
                    platform=platform,
                    confidence=confidence,
                    confidence_label=label,
                    matched_count=len(matched_ids),
                    ocr_text=ocr_text,
                    timestamp=datetime.now(timezone.utc),
                    alert_config=exam.alert_config,
                ))

            push_notification({
                "type": "new_leak",
                "leak_id": leak_id,
                "exam_id": self.exam_id,
                "exam_name": exam.name,
                "confidence": confidence,
                "confidence_label": label,
                "platform": platform,
                "ts": datetime.now(timezone.utc).isoformat(),
            })

            logger.info(
                "leak_persisted",
                scanner=self.name,
                leak_id=leak_id,
                confidence=confidence,
                platform=platform,
            )
            return leak_id

        except Exception as exc:
            logger.error("persist_leak_failed", scanner=self.name, error=str(exc))
            return None

    @abstractmethod
    async def _poll_loop(self) -> None:
        """Override in subclasses to implement the polling logic."""

    @abstractmethod
    async def scan_post(self, post_text: str, post_id: str) -> Optional[dict]:
        """
        Scan a single post against the FAISS index.
        Returns a leak dict if detected, else None.
        """
