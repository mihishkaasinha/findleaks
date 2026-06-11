from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from findleaks.schemas import (
    AlertObject,
    ExamCreate,
    ExamUpdate,
    HealthResponse,
    LeakItem,
    LeakPatch,
    LoginRequest,
    LoginResponse,
    MatchedExcerpt,
    MeResponse,
    ScannerItem,
    ScannerPatch,
    ScanResponse,
    UploadResponse,
)


# --- Auth Schemas ---

def test_login_request_valid():
    req = LoginRequest(username="admin", password="secret123")
    assert req.username == "admin"


def test_login_request_empty_username_fails():
    with pytest.raises(ValidationError):
        LoginRequest(username="", password="secret")


def test_login_response_has_app_branding():
    resp = LoginResponse(token="abc123")
    assert resp.app == "FINDLEAKS"
    assert resp.token_type == "bearer"
    assert resp.expires_in == 86400


def test_me_response_has_app_branding():
    resp = MeResponse(username="admin", role="admin")
    assert resp.app == "FINDLEAKS"


# --- Exam Schemas ---

def test_exam_create_valid():
    exam = ExamCreate(
        name="NEET 2024",
        alert_recipients=["admin@nta.ac.in"],
        keywords=["biology", "chemistry"],
    )
    assert exam.name == "NEET 2024"
    assert len(exam.alert_recipients) == 1


def test_exam_create_name_too_short():
    with pytest.raises(ValidationError):
        ExamCreate(name="AB", alert_recipients=["admin@nta.ac.in"])


def test_exam_create_name_too_long():
    with pytest.raises(ValidationError):
        ExamCreate(name="A" * 101, alert_recipients=["admin@nta.ac.in"])


def test_exam_create_invalid_email_recipient():
    with pytest.raises(ValidationError):
        ExamCreate(name="NEET 2024", alert_recipients=["not-an-email"])


def test_exam_create_no_recipients_fails():
    with pytest.raises(ValidationError):
        ExamCreate(name="NEET 2024", alert_recipients=[])


def test_exam_create_too_many_keywords():
    with pytest.raises(ValidationError):
        ExamCreate(
            name="NEET 2024",
            alert_recipients=["admin@nta.ac.in"],
            keywords=[f"kw{i}" for i in range(21)],
        )


def test_exam_create_invalid_webhook_url():
    with pytest.raises(ValidationError):
        ExamCreate(
            name="NEET 2024",
            alert_recipients=["admin@nta.ac.in"],
            alert_webhooks=["not-a-url"],
        )


def test_exam_create_valid_webhook():
    exam = ExamCreate(
        name="NEET 2024",
        alert_recipients=["admin@nta.ac.in"],
        alert_webhooks=["https://hooks.example.com/findleaks"],
    )
    assert exam.alert_webhooks[0].startswith("https://")


# --- Scan Schemas ---

def test_scan_response_confidence_out_of_range():
    with pytest.raises(ValidationError):
        ScanResponse(
            leak_detected=True,
            exam="NEET",
            exam_id=1,
            confidence=1.5,
            confidence_label="high",
            matched_questions=3,
            matched_excerpts=[],
            alert_sent=False,
            alert_recipients=[],
            timestamp=datetime.now(timezone.utc),
        )


def test_scan_response_valid():
    resp = ScanResponse(
        leak_detected=True,
        exam="NEET 2024",
        exam_id=1,
        confidence=0.92,
        confidence_label="high",
        matched_questions=5,
        matched_excerpts=[MatchedExcerpt(question_id=1, text="sample", score=0.9)],
        alert_sent=True,
        alert_recipients=["admin@nta.ac.in"],
        timestamp=datetime.now(timezone.utc),
    )
    assert resp.app == "FINDLEAKS"
    assert resp.confidence == 0.92


def test_matched_excerpt_score_out_of_range():
    with pytest.raises(ValidationError):
        MatchedExcerpt(question_id=1, text="test", score=1.5)


# --- Leak Schemas ---

def test_leak_patch_valid_acknowledged():
    patch = LeakPatch(status="acknowledged")
    assert patch.status == "acknowledged"


def test_leak_patch_valid_false_positive():
    patch = LeakPatch(status="false_positive")
    assert patch.status == "false_positive"


def test_leak_patch_invalid_status():
    with pytest.raises(ValidationError):
        LeakPatch(status="invalid_status")


# --- Health Schema ---

def test_health_response_has_branding():
    resp = HealthResponse(
        status="operational",
        exams_monitored=3,
        active_leaks=2,
        db_status="connected",
        indexes_loaded=3,
    )
    assert resp.app == "FINDLEAKS"
    assert resp.version == "1.0.0"


# --- Scanner Schemas ---

def test_scanner_patch_enable():
    patch = ScannerPatch(enabled=True)
    assert patch.enabled is True


def test_upload_response_has_branding():
    resp = UploadResponse(task_id="task-123", status="queued", exam_id=1)
    assert resp.app == "FINDLEAKS"
