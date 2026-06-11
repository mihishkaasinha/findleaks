"""
Base class for all social-media scanners.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
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

    @abstractmethod
    async def _poll_loop(self) -> None:
        """Override in subclasses to implement the polling logic."""

    @abstractmethod
    async def scan_post(self, post_text: str, post_id: str) -> Optional[dict]:
        """
        Scan a single post against the FAISS index.
        Returns a leak dict if detected, else None.
        """
