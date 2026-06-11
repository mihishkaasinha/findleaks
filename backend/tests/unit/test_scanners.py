import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from findleaks.scanners.base import BaseScanner
from findleaks.scanners.twitter import TwitterScanner, _build_query
from findleaks.scanners.telegram import TelegramScanner


# ---------------------------------------------------------------------------
# BaseScanner (concrete stub)
# ---------------------------------------------------------------------------

class _ConcreteScanner(BaseScanner):
    name = "test"

    async def _poll_loop(self):
        while self._running:
            await asyncio.sleep(0.01)

    async def scan_post(self, post_text, post_id):
        return None


def test_scanner_starts_not_running():
    sc = _ConcreteScanner(exam_id=1, exam_slug="neet", keywords=["biology"])
    assert sc.is_running is False


@pytest.mark.anyio
async def test_scanner_start_sets_running():
    sc = _ConcreteScanner(exam_id=1, exam_slug="neet", keywords=["biology"])
    await sc.start()
    assert sc.is_running is True
    await sc.stop()


@pytest.mark.anyio
async def test_scanner_stop_clears_running():
    sc = _ConcreteScanner(exam_id=1, exam_slug="neet", keywords=["bio"])
    await sc.start()
    await sc.stop()
    assert sc.is_running is False


@pytest.mark.anyio
async def test_scanner_double_start_is_idempotent():
    sc = _ConcreteScanner(exam_id=1, exam_slug="neet", keywords=["bio"])
    await sc.start()
    await sc.start()
    assert sc.is_running is True
    await sc.stop()


# ---------------------------------------------------------------------------
# _build_query
# ---------------------------------------------------------------------------

def test_build_query_includes_keywords():
    q = _build_query(["NEET", "biology", "chemistry"])
    assert '"NEET"' in q
    assert '"biology"' in q


def test_build_query_excludes_retweets():
    q = _build_query(["exam"])
    assert "-is:retweet" in q


def test_build_query_limits_to_10_keywords():
    keywords = [f"kw{i}" for i in range(15)]
    q = _build_query(keywords)
    assert '"kw10"' not in q
    assert '"kw9"' in q


def test_build_query_empty_keywords():
    q = _build_query([])
    assert "-is:retweet" in q


# ---------------------------------------------------------------------------
# TwitterScanner.scan_post
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_twitter_scan_post_returns_none_no_matches():
    sc = TwitterScanner(exam_id=1, exam_slug="neet", keywords=["bio"])
    with patch("findleaks.scanners.twitter.search_faiss", return_value=[]):
        result = await sc.scan_post("Some unrelated text", "tweet-123")
    assert result is None


@pytest.mark.anyio
async def test_twitter_scan_post_returns_result_on_high_confidence():
    sc = TwitterScanner(exam_id=1, exam_slug="neet", keywords=["biology"])
    with (
        patch("findleaks.scanners.twitter.search_faiss", return_value=[(0, 0.92), (1, 0.88)]),
        patch("findleaks.scanners.twitter.compute_confidence", return_value=0.91),
        patch("findleaks.scanners.twitter.confidence_label", return_value="high"),
    ):
        result = await sc.scan_post("What is the speed of light in vacuum?", "tweet-456")
    assert result is not None
    assert result["platform"] == "twitter"
    assert result["confidence"] == 0.91
    assert result["confidence_label"] == "high"


@pytest.mark.anyio
async def test_twitter_scan_post_returns_none_for_clean():
    sc = TwitterScanner(exam_id=1, exam_slug="neet", keywords=["bio"])
    with (
        patch("findleaks.scanners.twitter.search_faiss", return_value=[(0, 0.25)]),
        patch("findleaks.scanners.twitter.compute_confidence", return_value=0.25),
        patch("findleaks.scanners.twitter.confidence_label", return_value="clean"),
    ):
        result = await sc.scan_post("Random tweet about biology class today", "tweet-789")
    assert result is None


# ---------------------------------------------------------------------------
# TelegramScanner.scan_post
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_telegram_scan_post_skips_without_keywords():
    sc = TelegramScanner(exam_id=2, exam_slug="jee", keywords=["physics", "chemistry"])
    result = await sc.scan_post("random unrelated message", "tg_001")
    assert result is None


@pytest.mark.anyio
async def test_telegram_scan_post_detects_leak():
    sc = TelegramScanner(exam_id=2, exam_slug="jee", keywords=["physics"])
    with (
        patch("findleaks.scanners.telegram.search_faiss", return_value=[(0, 0.89)]),
        patch("findleaks.scanners.telegram.compute_confidence", return_value=0.89),
        patch("findleaks.scanners.telegram.confidence_label", return_value="high"),
    ):
        result = await sc.scan_post("physics paper questions from JEE 2025", "tg_002")
    assert result is not None
    assert result["platform"] == "telegram"
    assert result["confidence_label"] == "high"


@pytest.mark.anyio
async def test_telegram_scan_post_returns_none_clean():
    sc = TelegramScanner(exam_id=2, exam_slug="jee", keywords=["physics"])
    with (
        patch("findleaks.scanners.telegram.search_faiss", return_value=[(0, 0.2)]),
        patch("findleaks.scanners.telegram.compute_confidence", return_value=0.2),
        patch("findleaks.scanners.telegram.confidence_label", return_value="clean"),
    ):
        result = await sc.scan_post("physics lesson today was great", "tg_003")
    assert result is None


# ---------------------------------------------------------------------------
# Seen ID deduplication in TwitterScanner
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_twitter_dedup_skips_seen_post():
    sc = TwitterScanner(exam_id=1, exam_slug="neet", keywords=["bio"])
    sc._seen_ids.add("tweet-dupe")
    # If tweet is in seen_ids, scan_post should never be called
    # We test _poll_once indirectly by injecting a mock client
    mock_tweet = MagicMock()
    mock_tweet.id = "tweet-dupe"
    mock_tweet.text = "some bio text"

    mock_resp = MagicMock()
    mock_resp.data = [mock_tweet]
    mock_resp.meta = {}

    mock_client = AsyncMock()
    mock_client.search_recent_tweets = AsyncMock(return_value=mock_resp)

    scan_called = []

    async def fake_scan(text, pid):
        scan_called.append(pid)
        return None

    sc.scan_post = fake_scan

    with patch.object(sc, "_get_client", return_value=mock_client):
        await sc._poll_once()

    assert "tweet-dupe" not in scan_called
