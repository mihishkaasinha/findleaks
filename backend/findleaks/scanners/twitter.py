"""
Twitter/X scanner using tweepy v2 API.
Polls every 60 s using the recent search endpoint.
Cursors are stored in memory to avoid re-processing.
Backs off on HTTP 429 (rate limit) with exponential delay.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from findleaks.config import get_settings
from findleaks.detector import search_faiss_ranked, compute_confidence, confidence_label
from findleaks.ingestion import clean_text
from findleaks.scanners.base import BaseScanner

logger = structlog.get_logger()

POLL_INTERVAL = 60          # seconds
MAX_RESULTS_PER_POLL = 100
BACKOFF_BASE = 60           # seconds base for 429 backoff


def _build_query(keywords: list[str]) -> str:
    terms = [f'"{kw}"' for kw in keywords[:10]]
    return " OR ".join(terms) + " -is:retweet lang:en"


class TwitterScanner(BaseScanner):
    name = "twitter"

    def __init__(self, exam_id: int, exam_slug: str, keywords: list[str]):
        super().__init__(exam_id, exam_slug, keywords)
        self._seen_ids: set[str] = set()
        self._next_token: Optional[str] = None
        self._backoff = 0

    def _get_client(self):
        settings = get_settings()
        if not settings.TWITTER_BEARER_TOKEN:
            raise RuntimeError("TWITTER_BEARER_TOKEN not configured")
        try:
            import tweepy
            return tweepy.AsyncClient(bearer_token=settings.TWITTER_BEARER_TOKEN)
        except ImportError:
            raise RuntimeError("tweepy is not installed")

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._poll_once()
                self._backoff = 0
            except Exception as exc:
                if "429" in str(exc) or "rate limit" in str(exc).lower():
                    self._backoff = min((self._backoff or BACKOFF_BASE) * 2, 3600)
                    logger.warning(
                        "twitter_rate_limited",
                        exam=self.exam_slug,
                        backoff=self._backoff,
                    )
                    await asyncio.sleep(self._backoff)
                    continue
                logger.error("twitter_poll_error", exam=self.exam_slug, error=str(exc))
            await asyncio.sleep(POLL_INTERVAL)

    async def _poll_once(self) -> None:
        if not self.keywords:
            return

        client = self._get_client()
        query = _build_query(self.keywords)

        kwargs = dict(
            query=query,
            max_results=MAX_RESULTS_PER_POLL,
            tweet_fields=["id", "text", "created_at"],
        )
        if self._next_token:
            kwargs["next_token"] = self._next_token

        resp = await client.search_recent_tweets(**kwargs)
        if not resp or not resp.data:
            return

        self._next_token = resp.meta.get("next_token") if resp.meta else None

        for tweet in resp.data:
            tweet_id = str(tweet.id)
            if tweet_id in self._seen_ids:
                continue
            self._seen_ids.add(tweet_id)
            if len(self._seen_ids) > 10_000:
                self._seen_ids = set(list(self._seen_ids)[-5_000:])

            await self.scan_post(tweet.text, tweet_id)

    async def scan_post(self, post_text: str, post_id: str) -> Optional[dict]:
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

        logger.info("twitter_leak_detected", post_id=post_id, exam=self.exam_slug, confidence=conf)
        await self._persist_leak(
            platform="twitter",
            post_id=post_id,
            ocr_text=post_text,
            confidence=conf,
            label=label,
            matched_ids=matched_ids,
            matched_excerpts=matched_excerpts,
            raw_payload={"text": post_text[:500]},
        )
        return {"platform": "twitter", "post_id": post_id, "confidence": conf, "label": label}
