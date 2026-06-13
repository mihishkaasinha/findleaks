from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


APP_NAME = "FINDLEAKS"


# ---------------------------------------------------------------------------
# Shared / base
# ---------------------------------------------------------------------------

class AppBrandedModel(BaseModel):
    app: str = APP_NAME


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: list[Any]


class ErrorResponse(BaseModel):
    app: str = APP_NAME
    error: str
    message: str
    ref: str


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(AppBrandedModel):
    token: str
    token_type: str = "bearer"
    expires_in: int = 86400


class MeResponse(AppBrandedModel):
    username: str
    role: str


# ---------------------------------------------------------------------------
# Exams
# ---------------------------------------------------------------------------

class ExamCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    question_bank_path: Optional[str] = Field(None, max_length=500)
    keywords: Optional[list[str]] = Field(None, max_length=20)
    alert_recipients: list[EmailStr] = Field(..., min_length=1)
    alert_webhooks: Optional[list[str]] = Field(None)

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: list[str] | None) -> list[str] | None:
        if v and len(v) > 20:
            raise ValueError("Maximum 20 keywords allowed")
        return v

    @field_validator("alert_webhooks")
    @classmethod
    def validate_webhooks(cls, v: list[str] | None) -> list[str] | None:
        if v:
            for url in v:
                if not url.startswith(("http://", "https://")):
                    raise ValueError(f"Invalid webhook URL: {url}")
        return v


class ExamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    keywords: Optional[list[str]] = Field(None, max_length=20)
    alert_recipients: Optional[list[EmailStr]] = None
    alert_webhooks: Optional[list[str]] = None


class ExamResponse(AppBrandedModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    question_count: int
    last_indexed_at: Optional[datetime] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ExamListItem(BaseModel):
    id: int
    name: str
    slug: str
    question_count: int
    last_indexed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Question Bank / Ingestion
# ---------------------------------------------------------------------------

class UploadResponse(AppBrandedModel):
    task_id: str
    status: str
    exam_id: int


class IndexProgressEvent(BaseModel):
    type: str
    percent: Optional[int] = None
    message: Optional[str] = None
    question_count: Optional[int] = None


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

class MatchedExcerpt(BaseModel):
    question_id: int
    text: str
    score: float = Field(..., ge=0.0, le=1.0)


class ScanResponse(AppBrandedModel):
    status: str = "success"
    leak_detected: bool
    exam: str
    exam_id: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_label: str
    matched_questions: int
    matched_excerpts: list[MatchedExcerpt]
    ocr_text: Optional[str] = None
    leak_id: Optional[int] = None
    alert_sent: bool
    alert_recipients: list[str]
    timestamp: datetime


# ---------------------------------------------------------------------------
# Leaks
# ---------------------------------------------------------------------------

class LeakItem(BaseModel):
    id: int
    exam_id: int
    exam_name: Optional[str] = None
    platform: str
    platform_post_id: Optional[str] = None
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    ocr_text_preview: Optional[str] = None
    confidence: float
    confidence_label: str
    matched_question_count: int = 0
    timestamp: datetime
    status: str
    alert_sent: bool

    model_config = {"from_attributes": True}


class LeakListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: list[LeakItem]


class LeakExcerptDetail(BaseModel):
    question_id: int
    text: Optional[str] = None
    score: float


class LeakDetail(BaseModel):
    id: int
    exam_id: int
    exam_name: Optional[str] = None
    platform: str
    platform_post_id: Optional[str] = None
    ocr_text: Optional[str] = None
    confidence: float
    confidence_label: str
    matched_question_count: int = 0
    matched_excerpts: list[LeakExcerptDetail] = []
    timestamp: datetime
    status: str
    alert_sent: bool
    raw_payload: Optional[dict] = None

    model_config = {"from_attributes": True}


class LeakPatch(BaseModel):
    status: str = Field(..., pattern="^(acknowledged|false_positive)$")
    notes: Optional[str] = Field(None, max_length=1000)


class LeakPatchResponse(AppBrandedModel):
    id: int
    status: str
    updated_at: datetime


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class AlertObject(BaseModel):
    id: int
    leak_id: int
    sent_to: str
    method: str
    status: str
    sent_at: Optional[datetime] = None
    response_code: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: list[AlertObject]


class AlertSendResponse(AppBrandedModel):
    alert_ids: list[int]
    status: str = "queued"


class AlertAckResponse(AppBrandedModel):
    id: int
    status: str


class AlertRetryResponse(AppBrandedModel):
    id: int
    status: str = "retrying"


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------

class ScannerItem(BaseModel):
    id: int
    exam_id: int
    platform: str
    enabled: bool
    running: bool = False
    last_run: Optional[datetime] = None
    images_processed: int = 0
    leaks_detected: int = 0
    error_count: int = 0

    model_config = {"from_attributes": True}


class ScannerListResponse(AppBrandedModel):
    scanners: list[ScannerItem]


class ScannerPatch(BaseModel):
    enabled: Optional[bool] = None


class ScannerPatchResponse(AppBrandedModel):
    exam_id: int
    platform: str
    enabled: bool


class ScannerRunResponse(AppBrandedModel):
    message: str = "Scan queued"
    task_id: str


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(AppBrandedModel):
    status: str
    version: str = "1.0.0"
    last_scan: Optional[datetime] = None
    exams_monitored: int
    active_leaks: int
    db_status: str
    indexes_loaded: int
    model_loaded: bool = False
