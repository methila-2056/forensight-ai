"""SQLAlchemy models — full schema from Architecture v1.1 §Data Model (Phase 0).

Table list:
cases, evidence, integrity_checks, chain_of_custody, raw_records,
forensic_events, rule_findings, ml_findings, classifier_results,
correlations, investigation_runs, investigator_notes, model_metrics.

Note: the normalized-event payload column is named "metadata" at the SQL level
and exposed as the attribute ``extra`` to avoid clashing with the SQLAlchemy
declarative base attribute of the same name.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Naive UTC timestamp (stored consistently; tz noted per-event separately)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


def _enum(column_type: type[enum.Enum], name: str) -> Enum:
    """String-backed enum storing the Python values (portable across dialects)."""
    return Enum(
        column_type,
        name=name,
        native_enum=False,
        values_callable=lambda e: [member.value for member in e],
    )


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class CaseStatus(str, enum.Enum):
    DRAFT = "Draft"
    ACTIVE = "Active"
    UNDER_REVIEW = "Under Review"
    CLOSED = "Closed"


class SeverityLevel(str, enum.Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class EvidenceType(str, enum.Enum):
    AUTH = "authentication"
    PROCESS = "process"
    FILE = "file_activity"
    NETWORK = "network"
    BROWSER = "browser"
    SYSTEM = "system"
    GENERIC = "generic"


class EvidenceStatus(str, enum.Enum):
    UPLOADED = "Uploaded"
    VERIFIED = "Verified"
    PROCESSING = "Processing"
    PROCESSED = "Processed"
    ANALYZED = "Analyzed"
    ERROR = "Error"


class IntegrityResult(str, enum.Enum):
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"


class CustodyAction(str, enum.Enum):
    EVIDENCE_ADDED = "Evidence Added"
    HASH_GENERATED = "Hash Generated"
    INTEGRITY_VERIFIED = "Integrity Verified"
    INTEGRITY_MISMATCH = "Integrity Mismatch"
    INTEGRITY_TEST = "Integrity Test"
    PROCESSING_STARTED = "Analysis Started"
    PROCESSING_COMPLETED = "Analysis Completed"
    INVESTIGATOR_REVIEWED = "Investigator Reviewed"
    REPORT_GENERATED = "Report Generated"


class FindingStatus(str, enum.Enum):
    OPEN = "Open"
    CONFIRMED = "Confirmed"
    DISMISSED = "Dismissed"


class RunStage(str, enum.Enum):
    PROCESS = "Process"
    ANALYZE = "Analyze"
    CORRELATE = "Correlate"
    REPORT = "Report"


class RunStatus(str, enum.Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"


class SourceType(str, enum.Enum):
    AUTH = "authentication"
    PROCESS = "process"
    FILE = "file_activity"
    NETWORK = "network"
    BROWSER = "browser"
    SYSTEM = "system"
    GENERIC = "generic"


# ---------------------------------------------------------------------------
# Cases & evidence
# ---------------------------------------------------------------------------

class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    investigator: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(_enum(CaseStatus, "case_status"),
                                         nullable=False, default=CaseStatus.DRAFT.value)
    severity: Mapped[str] = mapped_column(_enum(SeverityLevel, "severity_level"),
                                          nullable=False, default=SeverityLevel.MEDIUM.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_activity: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    evidence: Mapped[list["Evidence"]] = relationship("Evidence", back_populates="case")
    runs: Mapped[list["InvestigationRun"]] = relationship("InvestigationRun")
    notes: Mapped[list["InvestigatorNote"]] = relationship("InvestigatorNote")
    custody: Mapped[list["ChainOfCustody"]] = relationship("ChainOfCustody")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence_type: Mapped[str] = mapped_column(_enum(EvidenceType, "evidence_type"),
                                               nullable=False, default=EvidenceType.GENERIC.value)
    source_description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False, default="application/octet-stream")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    original_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    status: Mapped[str] = mapped_column(_enum(EvidenceStatus, "evidence_status"),
                                        nullable=False, default=EvidenceStatus.UPLOADED.value)
    record_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parse_ok: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parse_rejected: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="evidence")
    events: Mapped[list["ForensicEvent"]] = relationship("ForensicEvent")


class IntegrityCheck(Base):
    __tablename__ = "integrity_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), nullable=False, index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    computed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(_enum(IntegrityResult, "integrity_result"), nullable=False)
    actor: Mapped[str] = mapped_column(String(127), nullable=False, default="system")

    evidence: Mapped["Evidence"] = relationship("Evidence")


class ChainOfCustody(Base):
    __tablename__ = "chain_of_custody"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    evidence_id: Mapped[Optional[int]] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    action: Mapped[str] = mapped_column(_enum(CustodyAction, "custody_action"), nullable=False)
    actor: Mapped[str] = mapped_column(String(127), nullable=False, default="system")
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    evidence: Mapped[Optional["Evidence"]] = relationship("Evidence")


# ---------------------------------------------------------------------------
# Records & normalized events
# ---------------------------------------------------------------------------

class RawRecord(Base):
    __tablename__ = "raw_records"
    __table_args__ = (UniqueConstraint("evidence_id", "row_index", name="uq_raw_record_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), nullable=False, index=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    evidence: Mapped["Evidence"] = relationship("Evidence")


class ForensicEvent(Base):
    __tablename__ = "forensic_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_uid: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), nullable=False, index=True)
    raw_record_id: Mapped[Optional[int]] = mapped_column(ForeignKey("raw_records.id"), nullable=True)
    timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    tz_note: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_type: Mapped[str] = mapped_column(_enum(SourceType, "source_type"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user: Mapped[Optional[str]] = mapped_column(String(127), nullable=True, index=True)
    host: Mapped[Optional[str]] = mapped_column(String(127), nullable=True, index=True)
    source_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    destination_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    process: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1023), nullable=True)
    action: Mapped[Optional[str]] = mapped_column(String(127), nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(_enum(SeverityLevel, "severity_level_ev"), nullable=True)
    anomaly_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_anomalous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extra: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    dedupe_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    evidence: Mapped["Evidence"] = relationship("Evidence", overlaps="events")
    raw_record: Mapped[Optional["RawRecord"]] = relationship("RawRecord")


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

class RuleFinding(Base):
    __tablename__ = "rule_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_uid: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(_enum(SeverityLevel, "severity_level_rule"),
                                          nullable=False, default=SeverityLevel.MEDIUM.value)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    timestamp_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    timestamp_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reasons: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    triggered_event_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    evidence_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(_enum(FindingStatus, "finding_status"),
                                        nullable=False, default=FindingStatus.OPEN.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class MlFinding(Base):
    __tablename__ = "ml_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_uid: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    composite_suspicion_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    components: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    explanation: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    event_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    evidence_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(_enum(FindingStatus, "finding_status_ml"),
                                        nullable=False, default=FindingStatus.OPEN.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ClassifierResult(Base):
    __tablename__ = "classifier_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    window_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    predicted_label: Mapped[str] = mapped_column(String(64), nullable=False)
    class_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------------------
# Correlation, runs, notes, metrics
# ---------------------------------------------------------------------------

class Correlation(Base):
    __tablename__ = "correlations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    chain_uid: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_id: Mapped[int] = mapped_column(ForeignKey("forensic_events.id"), nullable=False)
    link_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    link_reason: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    event: Mapped["ForensicEvent"] = relationship("ForensicEvent")


class InvestigationRun(Base):
    __tablename__ = "investigation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(_enum(RunStage, "run_stage"), nullable=False)
    status: Mapped[str] = mapped_column(_enum(RunStatus, "run_status"),
                                        nullable=False, default=RunStatus.PENDING.value)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class InvestigatorNote(Base):
    __tablename__ = "investigator_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    finding_uid: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    author: Mapped[str] = mapped_column(String(127), nullable=False, default="investigator")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ModelMetric(Base):
    __tablename__ = "model_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    dataset_desc: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    split_desc: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    precision: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recall: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    f1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accuracy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feature_list: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
