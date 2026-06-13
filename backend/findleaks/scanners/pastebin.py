"""
Pastebin scanner — monitors public pastes for exam content.
If PASTEBIN_API_KEY is set, uses the scraping API endpoint (requires Pastebin Pro).
Falls back to polling the public archive HTML page (no key needed, slower).
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

import httpx
import structlog

from findleaks.config import get_settings
from findleaks.detector import compute_confidence, confidence_label, search_faiss_ranked
from findleaks.ingestion import clean_text
from findleaks.scanners.base import BaseScanner

logger = structlog.get_logger()

POLL_INTERVAL = 120         # seconds — be polite to Pastebin
SCRAPING_API_URL = "https://scrape.pastebin.com/api_scraping.php"
PUBLIC_ARCHIVE_URL = "https://pastebin.com/archive"
RAW_URL = "https://pastebin.com/raw/{key}"
PASTE_ID_RE = re.compile(r'href="/([A-Za-z0-9]{8})"')
MAX_PASTES = 20
BACKOFF_BASE = 180


class PastebinScanner(BaseScanner):
    name = "pastebin"

    def __init__(self, exam_id: int, exam_slug: str, keywords: list[str]):
        super().__init__(exam_id, exam_slug, keywords)
        self._seen_keys: set[str] = set()
        self._backoff = 0

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._poll_once()
                self._backoff = 0
            except Exception as exc:
                if "429" in str(exc) or "rate" in str(exc).lower():
                    self._backoff = min((self._backoff or BACKOFF_BASE) * 2, 7200)
                    logger.warning("pastebin_rate_limited", exam=self.exam_slug, backoff=self._backoff)
                    await asyncio.sleep(self._backoff)
                    continue
                logger.error("pastebin_poll_error", exam=self.exam_slug, error=str(exc))
            await asyncio.sleep(POLL_INTERVAL)

    async def _poll_once(self) -> None:
        settings = get_settings()
        paste_keys: list[str] = []

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            if settings.PASTEBIN_API_KEY:
                try:
                    paste_keys = await self._fetch_via_api(client, settings.PASTEBIN_API_KEY)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in (401, 403):
                        # API key invalid or not Pro — fall back to public archive
                        logger.warning(
                            "pastebin_api_forbidden_fallback_to_archive",
                            exam=self.exam_slug,
                            status=exc.response.status_code,
                        )
                        paste_keys = await self._fetch_via_archive(client)
                    else:
                        raise
            else:
                paste_keys = await self._fetch_via_archive(client)

            logger.info("pastebin_poll_keys", exam=self.exam_slug, count=len(paste_keys))
            for key in paste_keys[:MAX_PASTES]:
                if key in self._seen_keys:
                    continue
                self._seen_keys.add(key)
                if len(self._seen_keys) > 10_000:
                    self._seen_keys = set(list(self._seen_keys)[-5_000:])

                try:
                    raw_resp = await client.get(
                        RAW_URL.format(key=key),
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                        timeout=10,
                    )
                    if raw_resp.status_code == 200:
                        content = raw_resp.text
                        if self._is_relevant(content):
                            await self.scan_post(content[:3000], f"pastebin:{key}")
                except Exception as exc:
                    logger.warning("pastebin_fetch_error", key=key, error=str(exc))
                await asyncio.sleep(1)

    async def _fetch_via_api(self, client: httpx.AsyncClient, api_key: str) -> list[str]:
        resp = await client.get(
            SCRAPING_API_URL,
            params={"limit": MAX_PASTES},
            headers={"api_dev_key": api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["key"] for item in data if "key" in item]

    async def _fetch_via_archive(self, client: httpx.AsyncClient) -> list[str]:
        resp = await client.get(
            PUBLIC_ARCHIVE_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        resp.raise_for_status()
        keys = PASTE_ID_RE.findall(resp.text)[:MAX_PASTES]
        logger.info("pastebin_archive_fetched", exam=self.exam_slug, keys_found=len(keys))
        return keys

    def _is_relevant(self, content: str) -> bool:
        """Quick keyword pre-filter before expensive FAISS search."""
        if not self.keywords:
            return True
        content_lower = content.lower()
        return any(kw.lower() in content_lower for kw in self.keywords
                   if not kw.startswith("r/") and not kw.startswith("channel:"))

    async def scan_post(self, post_text: str, post_id: str) -> Optional[dict]:
        text = clean_text(post_text)
        matches = search_faiss_ranked(text, self.exam_slug)
        if not matches:
            return None

        scores = [s for _, s in matches]
        conf = compute_confidence(scores)
        label = confidence_label(conf)

        if label == "clean":
            return None

        matched_ids = [idx for idx, _ in matches]
        matched_excerpts = [{"question_id": idx, "score": s} for idx, s in matches]

        logger.info("pastebin_leak_detected", post_id=post_id, exam=self.exam_slug, confidence=conf)
        await self._persist_leak(
            platform="pastebin",
            post_id=post_id,
            ocr_text=post_text,
            confidence=conf,
            label=label,
            matched_ids=matched_ids,
            matched_excerpts=matched_excerpts,
            raw_payload={"text": post_text[:500]},
        )
        return {"platform": "pastebin", "post_id": post_id, "confidence": conf, "label": label}
