"""
Alert delivery service.
Supports:  email (aiosmtplib + Jinja2), webhook (httpx), SMS (Twilio stub)
Rate limit: max 1 alert per leak_id per channel per ALERT_RATE_LIMIT_MINUTES minutes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import structlog
from jinja2 import Environment, BaseLoader

from findleaks.config import get_settings

logger = structlog.get_logger()

ALERT_RATE_LIMIT_MINUTES = 30
_SENT_CACHE: dict[str, datetime] = {}


# ---------------------------------------------------------------------------
# Rate limiter (in-memory, per leak+channel)
# ---------------------------------------------------------------------------

def _rate_limited(key: str) -> bool:
    last = _SENT_CACHE.get(key)
    if last and (datetime.now(timezone.utc) - last) < timedelta(minutes=ALERT_RATE_LIMIT_MINUTES):
        return True
    return False


def _mark_sent(key: str) -> None:
    _SENT_CACHE[key] = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Email template
# ---------------------------------------------------------------------------

_EMAIL_TEMPLATE = """\
Subject: [FINDLEAKS] 🚨 Leak Detected — {{ exam_name }} ({{ confidence_label|upper }})
Content-Type: text/plain

FINDLEAKS — Exam Integrity Alert
==================================
Exam    : {{ exam_name }}
Platform: {{ platform }}
Time    : {{ timestamp }}
Confidence: {{ "%.1f"|format(confidence * 100) }}% ({{ confidence_label|upper }})

Matched Questions: {{ matched_count }}

OCR Preview:
  {{ ocr_preview }}

Action Required: Review this leak at your FINDLEAKS dashboard.
"""

_jinja_env = Environment(loader=BaseLoader())
_email_tmpl = _jinja_env.from_string(_EMAIL_TEMPLATE)


def render_email_body(
    exam_name: str,
    platform: str,
    confidence: float,
    confidence_label: str,
    matched_count: int,
    ocr_preview: str,
    timestamp: datetime,
) -> str:
    return _email_tmpl.render(
        exam_name=exam_name,
        platform=platform,
        confidence=confidence,
        confidence_label=confidence_label,
        matched_count=matched_count,
        ocr_preview=ocr_preview[:300] if ocr_preview else "(no text extracted)",
        timestamp=timestamp.strftime("%Y-%m-%d %H:%M UTC"),
    )


# ---------------------------------------------------------------------------
# Email sender
# ---------------------------------------------------------------------------

async def send_email_alert(
    recipient: str,
    subject: str,
    body: str,
    leak_id: Optional[int] = None,
) -> dict:
    rate_key = f"email:{leak_id}:{recipient}"
    if leak_id and _rate_limited(rate_key):
        logger.info("alert_rate_limited", method="email", recipient=recipient, leak_id=leak_id)
        return {"status": "rate_limited", "recipient": recipient}

    settings = get_settings()
    try:
        import aiosmtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USER
        msg["To"] = recipient

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASS,
            timeout=10,
        )
        if leak_id:
            _mark_sent(rate_key)
        logger.info("email_alert_sent", recipient=recipient, leak_id=leak_id)
        return {"status": "sent", "recipient": recipient}
    except Exception as exc:
        logger.error("email_alert_failed", recipient=recipient, error=str(exc))
        return {"status": "failed", "recipient": recipient, "error": str(exc)}


# ---------------------------------------------------------------------------
# Webhook sender
# ---------------------------------------------------------------------------

async def send_webhook_alert(
    url: str,
    payload: dict,
    leak_id: Optional[int] = None,
    timeout: int = 10,
) -> dict:
    rate_key = f"webhook:{leak_id}:{url}"
    if leak_id and _rate_limited(rate_key):
        logger.info("alert_rate_limited", method="webhook", url=url, leak_id=leak_id)
        return {"status": "rate_limited", "url": url}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
        if leak_id:
            _mark_sent(rate_key)
        logger.info("webhook_alert_sent", url=url, status_code=resp.status_code)
        return {"status": "sent", "url": url, "response_code": resp.status_code}
    except Exception as exc:
        logger.error("webhook_alert_failed", url=url, error=str(exc))
        return {"status": "failed", "url": url, "error": str(exc)}


# ---------------------------------------------------------------------------
# SMS sender (Twilio stub — logs when creds missing)
# ---------------------------------------------------------------------------

async def send_sms_alert(
    to_number: str,
    message: str,
    leak_id: Optional[int] = None,
) -> dict:
    settings = get_settings()
    if not (settings.TWILIO_SID and settings.TWILIO_TOKEN and settings.TWILIO_NUMBER):
        logger.warning("sms_not_configured", to=to_number)
        return {"status": "not_configured", "to": to_number}

    rate_key = f"sms:{leak_id}:{to_number}"
    if leak_id and _rate_limited(rate_key):
        return {"status": "rate_limited", "to": to_number}

    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_SID, settings.TWILIO_TOKEN)
        msg = client.messages.create(
            body=message,
            from_=settings.TWILIO_NUMBER,
            to=to_number,
        )
        if leak_id:
            _mark_sent(rate_key)
        logger.info("sms_alert_sent", to=to_number, sid=msg.sid)
        return {"status": "sent", "to": to_number}
    except Exception as exc:
        logger.error("sms_alert_failed", to=to_number, error=str(exc))
        return {"status": "failed", "to": to_number, "error": str(exc)}


# ---------------------------------------------------------------------------
# Dispatch all alerts for a leak
# ---------------------------------------------------------------------------

async def dispatch_alerts(
    leak_id: int,
    exam_name: str,
    platform: str,
    confidence: float,
    confidence_label: str,
    matched_count: int,
    ocr_text: Optional[str],
    timestamp: datetime,
    alert_config: dict,
) -> list[dict]:
    """
    Fire-and-forget dispatch of all configured alerts for a detected leak.
    Returns list of results (for DB persistence).
    """
    results = []
    subject = f"[FINDLEAKS] Leak Detected — {exam_name} ({confidence_label.upper()})"
    body = render_email_body(
        exam_name=exam_name,
        platform=platform,
        confidence=confidence,
        confidence_label=confidence_label,
        matched_count=matched_count,
        ocr_preview=ocr_text or "",
        timestamp=timestamp,
    )

    webhook_payload = {
        "app": "FINDLEAKS",
        "event": "leak_detected",
        "leak_id": leak_id,
        "exam": exam_name,
        "platform": platform,
        "confidence": confidence,
        "confidence_label": confidence_label,
        "matched_questions": matched_count,
        "timestamp": timestamp.isoformat(),
    }

    tasks = []
    for email in alert_config.get("recipients", []):
        tasks.append(send_email_alert(email, subject, body, leak_id=leak_id))
    for url in alert_config.get("webhooks", []):
        tasks.append(send_webhook_alert(url, webhook_payload, leak_id=leak_id))
    for number in alert_config.get("sms", []):
        tasks.append(send_sms_alert(number, f"FINDLEAKS: Leak in {exam_name}", leak_id=leak_id))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=False)

    return list(results)
