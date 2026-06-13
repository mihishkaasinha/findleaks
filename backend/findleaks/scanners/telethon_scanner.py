"""
Telethon-based Telegram scanner.

Unlike the Bot API scanner (TelegramScanner), this logs in as a REAL user account
via Telegram's MTProto protocol. This allows:
  - Joining any public channel by search or invite link
  - Monitoring channels without being added as admin
  - Scanning channel history on startup
  - Much wider coverage than a bot

Required env vars:
  TELEGRAM_API_ID    — from https://my.telegram.org/apps
  TELEGRAM_API_HASH  — from https://my.telegram.org/apps
  TELEGRAM_PHONE     — real phone number, e.g. +919876543210
  TELEGRAM_CHANNELS  — comma-separated list of channel usernames/IDs to monitor
                       e.g. "JEE2025Leaks,t.me/examdrops,@neetstudy"
"""
from __future__ import annotations

import asyncio
import os
import re
from typing import Optional

import structlog

from findleaks.config import get_settings
from findleaks.detector import compute_confidence, confidence_label, search_faiss_ranked
from findleaks.scanners.base import BaseScanner

logger = structlog.get_logger()

HISTORY_SCAN_LIMIT = 100    # messages to backfill per channel on start
RECONNECT_DELAY    = 30     # seconds before reconnect on error


def _parse_channels(raw: str) -> list[str]:
    """Parse TELEGRAM_CHANNELS env var into a clean list of identifiers."""
    parts = [c.strip().lstrip("@") for c in raw.split(",") if c.strip()]
    cleaned = []
    for p in parts:
        m = re.match(r"(?:https?://)?t\.me/([a-zA-Z0-9_]+)", p)
        cleaned.append(m.group(1) if m else p)
    return cleaned


class TelethonScanner(BaseScanner):
    """
    Monitors Telegram channels as a real user account via Telethon (MTProto).

    Usage:
      1. Set TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE env vars
      2. Set TELEGRAM_CHANNELS to a comma-separated list of channel usernames
      3. First run will send an OTP to the phone — enter it in the Railway logs
         (Telethon stores the session file after first auth, so this is one-time)
    """
    name = "telethon"

    def __init__(self, exam_id: int, exam_slug: str, keywords: list[str]):
        super().__init__(exam_id, exam_slug, keywords)
        self._client = None
        self._session_path = f"/tmp/findleaks_tg_{exam_slug}.session"
        self._seen_ids: set[str] = set()

    def _get_client(self):
        settings = get_settings()
        api_id = settings.TELEGRAM_API_ID
        api_hash = settings.TELEGRAM_API_HASH
        phone = settings.TELEGRAM_PHONE
        if not api_id or not api_hash or not phone:
            raise RuntimeError(
                "TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_PHONE must all be set"
            )
        try:
            from telethon import TelegramClient
        except ImportError:
            raise RuntimeError("telethon is not installed — add it to requirements.txt")
        return TelegramClient(self._session_path, int(api_id), api_hash)

    async def _poll_loop(self) -> None:
        """
        Main loop:
          1. Connect & authenticate (OTP once, then session reused)
          2. Join monitored channels
          3. Scan recent history for each channel
          4. Register real-time event handler
          5. Run until stopped
        """
        settings = get_settings()
        raw_channels = settings.TELEGRAM_CHANNELS
        if not raw_channels:
            logger.warning("telethon_no_channels_configured", slug=self.exam_slug)
            return

        channels = _parse_channels(raw_channels)
        logger.info("telethon_starting", slug=self.exam_slug, channels=channels)

        while self._running:
            try:
                client = self._get_client()
                self._client = client

                await client.connect()

                if not await client.is_user_authorized():
                    phone = settings.TELEGRAM_PHONE
                    logger.warning(
                        "telethon_auth_required",
                        message="Send OTP to phone — check Railway logs",
                        phone=phone,
                    )
                    await client.send_code_request(phone)
                    code = os.environ.get("TELEGRAM_OTP", "")
                    if not code:
                        logger.error(
                            "telethon_otp_missing",
                            message="Set TELEGRAM_OTP env var in Railway with the code, then redeploy",
                        )
                        await client.disconnect()
                        return
                    await client.sign_in(phone, code)

                logger.info("telethon_connected", slug=self.exam_slug)

                await self._join_channels(client, channels)
                await self._scan_history(client, channels)
                await self._listen(client)

            except Exception as exc:
                logger.error("telethon_loop_error", slug=self.exam_slug, error=str(exc))
                if self._client:
                    try:
                        await self._client.disconnect()
                    except Exception:
                        pass
                await asyncio.sleep(RECONNECT_DELAY)

    async def _join_channels(self, client, channels: list[str]) -> None:
        """Attempt to join each channel (no-op if already a member)."""
        try:
            from telethon.tl.functions.channels import JoinChannelRequest
        except ImportError:
            return

        for username in channels:
            try:
                await client(JoinChannelRequest(username))
                logger.info("telethon_joined_channel", channel=username)
                await asyncio.sleep(1)
            except Exception as exc:
                logger.warning("telethon_join_failed", channel=username, error=str(exc))

    async def _scan_history(self, client, channels: list[str]) -> None:
        """Backfill recent messages from each channel on startup."""
        for username in channels:
            try:
                entity = await client.get_entity(username)
                messages = await client.get_messages(entity, limit=HISTORY_SCAN_LIMIT)
                for msg in messages:
                    if msg.text:
                        await self.scan_post(msg.text, f"tg_hist_{msg.id}")
                logger.info(
                    "telethon_history_scanned",
                    channel=username,
                    messages=len(messages),
                )
            except Exception as exc:
                logger.warning("telethon_history_failed", channel=username, error=str(exc))

    async def _listen(self, client) -> None:
        """Register real-time message handler (text + photos) and idle until stopped."""
        from telethon import events

        @client.on(events.NewMessage)
        async def handler(event):
            if not self._running:
                return
            msg = event.message
            post_id = f"tg_{msg.id}"

            if msg.text:
                await self.scan_post(msg.text, post_id)

            elif msg.photo:
                await self._scan_photo(client, msg, post_id)

        logger.info("telethon_listening", slug=self.exam_slug)
        while self._running:
            await asyncio.sleep(5)

        await client.disconnect()

    async def _scan_photo(self, client, message, post_id: str) -> None:
        """Download a Telegram photo, OCR it, run FAISS match, persist if leak."""
        try:
            from findleaks.detector import detect
            from findleaks.config import get_settings

            image_bytes: bytes = await client.download_media(message, bytes)
            if not image_bytes:
                return

            settings = get_settings()
            result = detect(image_bytes, self.exam_slug)

            if result.confidence < settings.ALERT_THRESHOLD_REVIEW:
                return

            matched_ids = [m.question_id for m in result.matched_questions]
            matched_excerpts = [
                {"question_id": m.question_id, "text": m.text, "score": m.score}
                for m in result.matched_questions
            ]
            logger.info(
                "telethon_photo_leak_detected",
                post_id=post_id,
                exam=self.exam_slug,
                confidence=result.confidence,
            )
            await self._persist_leak(
                platform="telethon",
                post_id=f"{post_id}_photo",
                ocr_text=result.ocr_text,
                confidence=result.confidence,
                label=result.confidence_label,
                matched_ids=matched_ids,
                matched_excerpts=matched_excerpts,
                raw_payload={"type": "photo", "message_id": message.id},
            )
        except Exception as exc:
            logger.warning("telethon_photo_scan_failed", post_id=post_id, error=str(exc))

    async def scan_post(self, post_text: str, post_id: str) -> Optional[dict]:
        if post_id in self._seen_ids:
            return None
        self._seen_ids.add(post_id)
        if len(self._seen_ids) > 50_000:
            self._seen_ids.clear()

        matches = search_faiss_ranked(post_text, self.exam_slug)
        if not matches:
            return None

        scores = [s for _, s in matches]
        conf = compute_confidence(scores)
        label = confidence_label(conf)

        if label == "clean":
            return None

        matched_ids = [idx for idx, _ in matches]
        matched_excerpts = [{"question_id": idx, "score": s} for idx, s in matches]

        logger.info("telethon_leak_detected", post_id=post_id, exam=self.exam_slug, confidence=conf)
        await self._persist_leak(
            platform="telethon",
            post_id=post_id,
            ocr_text=post_text,
            confidence=conf,
            label=label,
            matched_ids=matched_ids,
            matched_excerpts=matched_excerpts,
            raw_payload={"text": post_text[:500]},
        )
        return {"platform": "telethon", "post_id": post_id, "confidence": conf, "label": label}
