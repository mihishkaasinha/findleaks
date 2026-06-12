"""
Discord scanner — monitors configured guild channels for exam-related content.
Requires DISCORD_BOT_TOKEN. The bot must be added to target servers with
Message Content Intent enabled in Discord Developer Portal.
Channel IDs to monitor can be passed as keywords: "channel:1234567890"
"""
from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from findleaks.config import get_settings
from findleaks.detector import compute_confidence, confidence_label, search_faiss
from findleaks.ingestion import clean_text
from findleaks.scanners.base import BaseScanner

logger = structlog.get_logger()

RECONNECT_DELAY = 30


def _channel_ids_from_keywords(keywords: list[str]) -> list[int]:
    """Extract Discord channel IDs from keywords like 'channel:1234567890'."""
    ids = []
    for kw in keywords:
        if kw.startswith("channel:"):
            try:
                ids.append(int(kw.split(":", 1)[1]))
            except ValueError:
                pass
    return ids


class DiscordScanner(BaseScanner):
    name = "discord"

    def __init__(self, exam_id: int, exam_slug: str, keywords: list[str]):
        super().__init__(exam_id, exam_slug, keywords)
        self._client = None
        self._seen_ids: set[int] = set()

    def _get_client(self):
        settings = get_settings()
        if not settings.DISCORD_BOT_TOKEN:
            raise RuntimeError("DISCORD_BOT_TOKEN not configured")
        try:
            import discord

            intents = discord.Intents.default()
            intents.message_content = True
            client = discord.Client(intents=intents)
            return client, settings.DISCORD_BOT_TOKEN
        except ImportError:
            raise RuntimeError("discord.py is not installed — run: pip install discord.py")

    async def _poll_loop(self) -> None:
        settings = get_settings()
        if not settings.DISCORD_BOT_TOKEN:
            logger.warning("discord_no_token", exam=self.exam_slug)
            return

        while self._running:
            try:
                await self._run_client()
            except Exception as exc:
                logger.error("discord_client_error", exam=self.exam_slug, error=str(exc))
                if self._running:
                    await asyncio.sleep(RECONNECT_DELAY)

    async def _run_client(self) -> None:
        import discord

        client, token = self._get_client()
        channel_ids = _channel_ids_from_keywords(self.keywords)
        scanner_ref = self

        @client.event
        async def on_ready():
            logger.info("discord_connected", guilds=len(client.guilds), exam=scanner_ref.exam_slug)
            if channel_ids:
                for channel_id in channel_ids:
                    channel = client.get_channel(channel_id)
                    if channel:
                        async for msg in channel.history(limit=50):
                            if msg.id not in scanner_ref._seen_ids:
                                scanner_ref._seen_ids.add(msg.id)
                                await scanner_ref.scan_post(msg.content, f"discord:{channel_id}:{msg.id}")

        @client.event
        async def on_message(message):
            if message.author == client.user:
                return
            if channel_ids and message.channel.id not in channel_ids:
                return
            if message.id in scanner_ref._seen_ids:
                return
            scanner_ref._seen_ids.add(message.id)
            if len(scanner_ref._seen_ids) > 10_000:
                scanner_ref._seen_ids = set(list(scanner_ref._seen_ids)[-5_000:])
            await scanner_ref.scan_post(message.content, f"discord:{message.channel.id}:{message.id}")

        self._client = client
        try:
            await client.start(token)
        finally:
            if not client.is_closed():
                await client.close()
            self._client = None

    async def stop(self) -> None:
        self._running = False
        if self._client and not self._client.is_closed():
            await self._client.close()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("scanner_stopped", scanner=self.name, exam=self.exam_slug)

    async def scan_post(self, post_text: str, post_id: str) -> Optional[dict]:
        if not post_text.strip():
            return None
        text = clean_text(post_text)
        matches = search_faiss(text, self.exam_slug)
        if not matches:
            return None

        scores = [s for _, s in matches]
        conf = compute_confidence(scores)
        label = confidence_label(conf)

        if label == "clean":
            return None

        matched_ids = [idx for idx, _ in matches]
        matched_excerpts = [{"question_id": idx, "score": s} for idx, s in matches]

        logger.info("discord_leak_detected", post_id=post_id, exam=self.exam_slug, confidence=conf)
        await self._persist_leak(
            platform="discord",
            post_id=post_id,
            ocr_text=post_text,
            confidence=conf,
            label=label,
            matched_ids=matched_ids,
            matched_excerpts=matched_excerpts,
            raw_payload={"text": post_text[:500]},
        )
        return {"platform": "discord", "post_id": post_id, "confidence": conf, "label": label}
