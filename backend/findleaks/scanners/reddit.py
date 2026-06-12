"""
Reddit scanner — polls new posts in configured subreddits every 60 s.
Uses Reddit's free public JSON API (no auth required for public subreddits).
If REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET are set, uses OAuth for higher rate limits.
"""
from __future__ import annotations

import asyncio
import base64
from typing import Optional

import httpx
import structlog

from findleaks.config import get_settings
from findleaks.detector import compute_confidence, confidence_label, search_faiss
from findleaks.ingestion import clean_text
from findleaks.scanners.base import BaseScanner

logger = structlog.get_logger()

POLL_INTERVAL = 90          # seconds between polls
MAX_POSTS_PER_POLL = 25
BACKOFF_BASE = 120          # seconds base for 429 backoff
DEFAULT_SUBREDDITS = ["JEEMains", "NEET", "JEEAdvanced", "competitiveexams", "Indian_Academia"]
USER_AGENT = "FindLeaks/1.0 (exam integrity monitoring)"


def _subreddits_from_keywords(keywords: list[str]) -> list[str]:
    """Extract subreddit hints from keywords like 'r/JEEMains', else use defaults."""
    subs = [kw[2:] for kw in keywords if kw.startswith("r/")]
    return subs if subs else DEFAULT_SUBREDDITS


class RedditScanner(BaseScanner):
    name = "reddit"

    def __init__(self, exam_id: int, exam_slug: str, keywords: list[str]):
        super().__init__(exam_id, exam_slug, keywords)
        self._seen_ids: set[str] = set()
        self._backoff = 0
        self._access_token: Optional[str] = None

    async def _get_headers(self) -> dict:
        settings = get_settings()
        if settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET:
            token = await self._get_oauth_token(settings.REDDIT_CLIENT_ID, settings.REDDIT_CLIENT_SECRET)
            return {"Authorization": f"bearer {token}", "User-Agent": USER_AGENT}
        return {"User-Agent": USER_AGENT}

    async def _get_oauth_token(self, client_id: str, client_secret: str) -> str:
        if self._access_token:
            return self._access_token
        creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://www.reddit.com/api/v1/access_token",
                headers={"Authorization": f"Basic {creds}", "User-Agent": USER_AGENT},
                data={"grant_type": "client_credentials"},
            )
            resp.raise_for_status()
            self._access_token = resp.json()["access_token"]
            return self._access_token

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._poll_once()
                self._backoff = 0
            except Exception as exc:
                if "429" in str(exc) or "rate" in str(exc).lower():
                    self._backoff = min((self._backoff or BACKOFF_BASE) * 2, 3600)
                    logger.warning("reddit_rate_limited", exam=self.exam_slug, backoff=self._backoff)
                    await asyncio.sleep(self._backoff)
                    continue
                logger.error("reddit_poll_error", exam=self.exam_slug, error=str(exc))
            await asyncio.sleep(POLL_INTERVAL)

    async def _poll_once(self) -> None:
        subreddits = _subreddits_from_keywords(self.keywords)
        headers = await self._get_headers()
        settings = get_settings()
        base = "https://oauth.reddit.com" if settings.REDDIT_CLIENT_ID else "https://www.reddit.com"

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for sub in subreddits[:5]:
                try:
                    url = f"{base}/r/{sub}/new.json?limit={MAX_POSTS_PER_POLL}"
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()
                    posts = data.get("data", {}).get("children", [])
                    for post in posts:
                        p = post.get("data", {})
                        post_id = p.get("id", "")
                        if post_id in self._seen_ids:
                            continue
                        self._seen_ids.add(post_id)
                        if len(self._seen_ids) > 10_000:
                            self._seen_ids = set(list(self._seen_ids)[-5_000:])

                        title = p.get("title", "")
                        body = p.get("selftext", "")
                        combined = f"{title}\n{body}".strip()
                        if combined:
                            await self.scan_post(combined, f"reddit:{sub}:{post_id}")
                except Exception as exc:
                    logger.warning("reddit_subreddit_error", subreddit=sub, error=str(exc))
                await asyncio.sleep(2)

    async def scan_post(self, post_text: str, post_id: str) -> Optional[dict]:
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

        logger.info("reddit_leak_detected", post_id=post_id, exam=self.exam_slug, confidence=conf)
        await self._persist_leak(
            platform="reddit",
            post_id=post_id,
            ocr_text=post_text,
            confidence=conf,
            label=label,
            matched_ids=matched_ids,
            matched_excerpts=matched_excerpts,
            raw_payload={"text": post_text[:500]},
        )
        return {"platform": "reddit", "post_id": post_id, "confidence": conf, "label": label}
