"""Pydantic request/response schemas (Phase 1: cases, evidence, integrity, custody;
Phase 2: processing, events)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    CaseStatus,
    CustodyAction,
    EvidenceStatus,
    EvidenceType,
    ProcessingStatus,
    SeverityLevel,
    SourceType,
)
from app.terminology import HASH_ALGORITHM

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

class CaseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255, examples=["Suspicious login investigation"])
    investigator: str = Field(min_length=1, max_length=255, examples=["Investigator A"])
    description: str = Field(default="", max_length=4000)
    severity: SeverityLevel = SeverityLevel.MEDIUM


class CaseUpdateRequest(BaseModel):
    status: Optional[CaseStatus] = None
    severity: Optional[SeverityLevel] = None


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: str
    name: str
    investigator: str
    description: str
    status: CaseStatus
    severity: SeverityLevel
    created_at: datetime
    last_activity: datetime
    demo: bool
    evidence_count: int
    finding_count: int


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    case_id: str
    original_filename: str
    evidence_type: EvidenceType
    source_description: str
    file_size: int
    mime_type: str
    sha256: str
    uploaded_at: datetime
    status: EvidenceStatus
    record_count: Optional[int] = None
    parse_ok: Optional[int] = None
    parse_rejected: Optional[int] = None


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------

class IntegrityVerifyResponse(BaseModel):
    evidence_id: str
    algorithm: str = HASH_ALGORITHM
    result: str
    computed_hash: str
    expected_hash: str
    verified_at: datetime
    note: str


class IntegrityTestResponse(BaseModel):
    evidence_id: str
    operation: str
    result: str
    recorded_hash: str
    test_copy_hash: str
    original_unchanged: bool
    note: str


class IntegrityHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    checked_at: datetime
    computed_hash: str
    expected_hash: str
    result: str
    actor: str


# ---------------------------------------------------------------------------
# Chain of custody
# ---------------------------------------------------------------------------

class CustodyEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: str
    evidence_id: Optional[str]
    timestamp: datetime
    action: CustodyAction
    actor: str
    details: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Processing (Phase 2)
# ---------------------------------------------------------------------------

class ProcessRequest(BaseModel):
    evidence_ids: Optional[list[str]] = Field(
        default=None,
        description="Process only these evidence items; omit to process all evidence of the case",
        examples=[["EV-0001"]],
    )
    actor: str = Field(default="system", max_length=127)


class ProcessingRunResponse(BaseModel):
    run_id: str
    case_id: str
    evidence_id: str
    evidence_filename: str
    parser: str
    status: ProcessingStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    records_received: int
    records_parsed: int
    records_normalized: int
    records_rejected: int
    duplicates_detected: int
    warnings: list[str] = []
    error_code: Optional[str] = None
    error: Optional[str] = None


class ProcessCaseResponse(BaseModel):
    case_id: str
    runs: list[ProcessingRunResponse]


class EvidenceProcessingResponse(BaseModel):
    evidence_id: str
    original_filename: str
    sha256: str
    status: EvidenceStatus
    record_count: Optional[int] = None
    parse_ok: Optional[int] = None
    parse_rejected: Optional[int] = None
    runs: list[ProcessingRunResponse]


class RejectedRecordResponse(BaseModel):
    evidence_id: str
    row_index: int
    parser: str
    status: str = "REJECTED"
    reason: Optional[str] = None
    original_record: str
    processed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Normalized events (Phase 2)
# ---------------------------------------------------------------------------

class EventResponse(BaseModel):
    event_id: str
    case_id: str
    evidence_id: str
    timestamp: Optional[datetime] = None
    tz_note: Optional[str] = None
    source_type: SourceType
    event_type: str
    user: Optional[str] = None
    host: Optional[str] = None
    source_ip: Optional[str] = None
    destination_ip: Optional[str] = None
    process: Optional[str] = None
    file_path: Optional[str] = None
    action: Optional[str] = None
    severity: Optional[SeverityLevel] = None
    raw_record_reference: Optional[int] = Field(
        default=None, description="Row number in the original evidence file"
    )
    duplicate: bool = False
    duplicate_of: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class EventListResponse(BaseModel):
    events: list[EventResponse]
    total: int
    limit: int
    offset: int


class RawRecordResponse(BaseModel):
    row_index: int
    content: str
    reject_reason: Optional[str] = None


class EventEvidenceRef(BaseModel):
    evidence_id: str
    original_filename: str
    sha256: str
    uploaded_at: datetime


class EventDetailResponse(EventResponse):
    raw_record: Optional[RawRecordResponse] = None
    evidence: Optional[EventEvidenceRef] = None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ErrorBody(BaseModel):
    code: str
    message: str
    detail: Optional[Any] = None


class ErrorResponse(BaseModel):
    """Documented shape of every error response."""
    error: ErrorBody
