"""Pydantic request/response schemas (Phase 1: cases, evidence, integrity, custody)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    CaseStatus,
    CustodyAction,
    EvidenceStatus,
    EvidenceType,
    SeverityLevel,
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
# Errors
# ---------------------------------------------------------------------------

class ErrorBody(BaseModel):
    code: str
    message: str
    detail: Optional[Any] = None


class ErrorResponse(BaseModel):
    """Documented shape of every error response."""
    error: ErrorBody
