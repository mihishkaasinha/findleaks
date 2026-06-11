from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from findleaks.alerts import (
    ALERT_RATE_LIMIT_MINUTES,
    _SENT_CACHE,
    _mark_sent,
    _rate_limited,
    dispatch_alerts,
    render_email_body,
    send_email_alert,
    send_webhook_alert,
)


def _clear_cache():
    _SENT_CACHE.clear()


# ---------------------------------------------------------------------------
# render_email_body
# ---------------------------------------------------------------------------

def test_render_email_body_contains_exam_name():
    body = render_email_body(
        exam_name="NEET 2025",
        platform="twitter",
        confidence=0.91,
        confidence_label="high",
        matched_count=5,
        ocr_preview="What is photosynthesis?",
        timestamp=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
    )
    assert "NEET 2025" in body


def test_render_email_body_shows_confidence_percentage():
    body = render_email_body(
        exam_name="JEE 2025",
        platform="telegram",
        confidence=0.85,
        confidence_label="high",
        matched_count=3,
        ocr_preview="Newton's law",
        timestamp=datetime(2025, 6, 1, tzinfo=timezone.utc),
    )
    assert "85.0%" in body


def test_render_email_body_contains_platform():
    body = render_email_body(
        exam_name="UPSC",
        platform="telegram",
        confidence=0.72,
        confidence_label="review",
        matched_count=2,
        ocr_preview="some text",
        timestamp=datetime(2025, 6, 1, tzinfo=timezone.utc),
    )
    assert "telegram" in body


def test_render_email_body_truncates_long_ocr():
    long_text = "x" * 1000
    body = render_email_body(
        exam_name="Exam",
        platform="twitter",
        confidence=0.9,
        confidence_label="high",
        matched_count=1,
        ocr_preview=long_text,
        timestamp=datetime.now(timezone.utc),
    )
    assert "x" * 301 not in body


def test_render_email_body_no_ocr_uses_placeholder():
    body = render_email_body(
        exam_name="Exam",
        platform="twitter",
        confidence=0.9,
        confidence_label="high",
        matched_count=1,
        ocr_preview="",
        timestamp=datetime.now(timezone.utc),
    )
    assert "no text extracted" in body


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

def test_rate_limit_not_triggered_initially():
    _clear_cache()
    assert _rate_limited("test-key") is False


def test_rate_limit_triggered_after_mark():
    _clear_cache()
    _mark_sent("my-key")
    assert _rate_limited("my-key") is True


def test_rate_limit_different_keys_independent():
    _clear_cache()
    _mark_sent("key-a")
    assert _rate_limited("key-b") is False


def test_rate_limit_returns_false_for_none_leak():
    _clear_cache()
    assert _rate_limited("email:None:user@test.com") is False


# ---------------------------------------------------------------------------
# send_email_alert (mocked aiosmtplib)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_send_email_alert_success():
    _clear_cache()
    with patch("aiosmtplib.send", AsyncMock(return_value=(None, None))):
        result = await send_email_alert("x@example.com", "Subject", "Body", leak_id=1)
    assert result["status"] == "sent"
    assert result["recipient"] == "x@example.com"


@pytest.mark.anyio
async def test_send_email_alert_rate_limited():
    _clear_cache()
    _mark_sent("email:42:ratelimited@test.com")
    result = await send_email_alert(
        "ratelimited@test.com", "Subject", "Body", leak_id=42
    )
    assert result["status"] == "rate_limited"


@pytest.mark.anyio
async def test_send_email_alert_handles_smtp_error():
    _clear_cache()
    with patch("aiosmtplib.send", AsyncMock(side_effect=Exception("SMTP down"))):
        result = await send_email_alert("fail@test.com", "Subj", "Body", leak_id=99)
    assert result["status"] == "failed"
    assert "SMTP down" in result["error"]


# ---------------------------------------------------------------------------
# send_webhook_alert (mocked httpx)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_send_webhook_rate_limited():
    _clear_cache()
    _mark_sent("webhook:7:https://hooks.test.com")
    result = await send_webhook_alert("https://hooks.test.com", {}, leak_id=7)
    assert result["status"] == "rate_limited"


@pytest.mark.anyio
async def test_send_webhook_success():
    _clear_cache()
    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client
        result = await send_webhook_alert("https://hooks.example.com/test", {"event": "test"}, leak_id=99)
    assert result["status"] == "sent"
    assert result["response_code"] == 200


@pytest.mark.anyio
async def test_send_webhook_handles_connection_error():
    _clear_cache()
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_client_cls.return_value = mock_client
        result = await send_webhook_alert("https://dead.example.com", {}, leak_id=5)
    assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# dispatch_alerts
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_dispatch_alerts_calls_all_channels():
    _clear_cache()
    alert_config = {
        "recipients": ["admin@exam.com"],
        "webhooks": ["https://hooks.example.com/notify"],
        "sms": [],
    }

    email_result = {"status": "sent", "recipient": "admin@exam.com"}
    webhook_result = {"status": "sent", "url": "https://hooks.example.com/notify"}

    with (
        patch("findleaks.alerts.send_email_alert", AsyncMock(return_value=email_result)),
        patch("findleaks.alerts.send_webhook_alert", AsyncMock(return_value=webhook_result)),
    ):
        results = await dispatch_alerts(
            leak_id=1,
            exam_name="NEET 2025",
            platform="twitter",
            confidence=0.91,
            confidence_label="high",
            matched_count=3,
            ocr_text="leaked question text here",
            timestamp=datetime.now(timezone.utc),
            alert_config=alert_config,
        )
    assert len(results) == 2
    assert results[0]["status"] == "sent"
    assert results[1]["status"] == "sent"


@pytest.mark.anyio
async def test_dispatch_alerts_empty_config_returns_empty():
    _clear_cache()
    results = await dispatch_alerts(
        leak_id=1,
        exam_name="Exam",
        platform="manual",
        confidence=0.9,
        confidence_label="high",
        matched_count=1,
        ocr_text=None,
        timestamp=datetime.now(timezone.utc),
        alert_config={"recipients": [], "webhooks": [], "sms": []},
    )
    assert results == []
