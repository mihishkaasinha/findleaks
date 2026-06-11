"""
Telegram scanner using python-telegram-bot 20.x async.
Subscribes to channel/group messages via the Bot API (getUpdates polling).
Deduplicates by update_id.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from findleaks.config import get_settings
from findleaks.detector import compute_confidence, confidence_label, search_faiss
from findleaks.scanners.base import BaseScanner

logger = structlog.get_logger()

POLL_INTERVAL = 30          # seconds
POLL_TIMEOUT = 20           # long-poll timeout (seconds)


class TelegramScanner(BaseScanner):
    name = "telegram"

    def __init__(self, exam_id: int, exam_slug: str, keywords: list[str]):
        super().__init__(exam_id, exam_slug, keywords)
        self._last_update_id: int = 0

    def _get_application(self):
        settings = get_settings()
        if not settings.TELEGRAM_BOT_TOKEN:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
        try:
            from telegram import Bot
            return Bot(token=settings.TELEGRAM_BOT_TOKEN)
        except ImportError:
            raise RuntimeError("python-telegram-bot is not installed")

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._poll_once()
            except Exception as exc:
                logger.error("telegram_poll_error", exam=self.exam_slug, error=str(exc))
            await asyncio.sleep(POLL_INTERVAL)

    async def _poll_once(self) -> None:
        bot = self._get_application()
        kwargs: dict = {"timeout": POLL_TIMEOUT, "allowed_updates": ["message", "channel_post"]}
        if self._last_update_id:
            kwargs["offset"] = self._last_update_id + 1

        updates = await bot.get_updates(**kwargs)
        for update in updates:
            self._last_update_id = max(self._last_update_id, update.update_id)
            text = None
            if update.message and update.message.text:
                text = update.message.text
            elif update.channel_post and update.channel_post.text:
                text = update.channel_post.text

            if text:
                post_id = f"tg_{update.update_id}"
                await self.scan_post(text, post_id)

    async def scan_post(self, post_text: str, post_id: str) -> Optional[dict]:
        if not any(kw.lower() in post_text.lower() for kw in self.keywords):
            return None

        matches = search_faiss(post_text, self.exam_slug)
        if not matches:
            return None

        scores = [s for _, s in matches]
        conf = compute_confidence(scores)
        label = confidence_label(conf)

        if label == "clean":
            return None

        result = {
            "platform": "telegram",
            "post_id": post_id,
            "exam_id": self.exam_id,
            "exam_slug": self.exam_slug,
            "confidence": conf,
            "confidence_label": label,
            "text_preview": post_text[:500],
        }
        logger.info("telegram_leak_detected", **{k: v for k, v in result.items() if k != "text_preview"})
        return result
