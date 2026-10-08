"""Pydantic request/response schemas (Phase 1: cases, evidence, integrity, custody;
Phase 2: processing, events; Phase 3: automated analysis, findings, review;
Phase 5: investigation assistant; Phase 6: forensic reports)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app import config
from app.models import (
    CaseStatus,
    CorrelationType,
    CustodyAction,
    EvidenceStatus,
    EvidenceType,
    FindingStatus,
    GroupKind,
    ProcessingStatus,
    RunStage,
    RunStatus,
    SeverityLevel,
    SourceType,
    TimelineSignificance,
)
from app.terminology import HASH_ALGORITHM, REPORT_SCHEMA, REPORT_STATUS, REPORT_VERSION

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
    anomaly_score: Optional[float] = Field(
        default=None,
        description="Anomaly score of this event's analysis window (Phase 3, null before analysis)",
    )
    is_anomalous: bool = False
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
# Automated analysis (Phase 3)
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    actor: str = Field(default="system", max_length=127)


class AnalysisRunResponse(BaseModel):
    run_id: str
    case_id: str
    stage: RunStage
    status: RunStatus
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    stats: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class FindingReviewRequest(BaseModel):
    status: FindingStatus
    note: Optional[str] = Field(default=None, max_length=4000)
    author: str = Field(default="investigator", max_length=127)


class FindingSummary(BaseModel):
    finding_id: str
    case_id: str
    kind: Literal["rule", "ml"]
    run_id: Optional[str] = None
    rule_id: Optional[str] = None
    model_name: Optional[str] = None
    title: str
    severity: SeverityLevel
    status: FindingStatus
    confidence: Optional[float] = None
    anomaly_score: Optional[float] = None
    threshold: Optional[float] = None
    composite_suspicion_score: Optional[float] = None
    event_count: int = 0
    evidence_count: int = 0
    created_at: datetime
    updated_at: datetime


class FindingListResponse(BaseModel):
    findings: list[FindingSummary]
    total: int
    limit: int
    offset: int


class FindingNoteResponse(BaseModel):
    author: str
    body: str
    created_at: datetime


class FindingEvidenceResponse(BaseModel):
    evidence_id: str
    original_filename: str
    evidence_type: EvidenceType
    file_size: int
    sha256: str
    uploaded_at: datetime


class FindingDetailResponse(BaseModel):
    finding_id: str
    case_id: str
    kind: Literal["rule", "ml"]
    run_id: Optional[str] = None
    rule_id: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    feature_version: Optional[str] = None
    title: str
    severity: SeverityLevel
    status: FindingStatus
    confidence: Optional[float] = None
    anomaly_score: Optional[float] = None
    threshold: Optional[float] = None
    composite_suspicion_score: Optional[float] = None
    components: Optional[dict[str, Any]] = None
    feature_snapshot: Optional[dict[str, Any]] = None
    explanation: Optional[Any] = None
    reasons: Optional[Any] = None
    timestamp_start: Optional[datetime] = None
    timestamp_end: Optional[datetime] = None
    event_ids: list[str] = []
    evidence_ids: list[str] = []
    supporting_events: list[EventResponse] = []
    evidence: list[FindingEvidenceResponse] = []
    notes: list[FindingNoteResponse] = []
    created_at: datetime
    updated_at: datetime


class MlMetricsResponse(BaseModel):
    case_id: str
    run_id: Optional[str] = None
    stats: dict[str, Any] = {}
    config: dict[str, Any] = {}
    scope_note: str


class FindingTraceResponse(BaseModel):
    finding_id: str
    case_id: str
    kind: Literal["rule", "ml"]
    events: list[EventDetailResponse] = []
    evidence: list[FindingEvidenceResponse] = []


# ---------------------------------------------------------------------------
# Correlation, activity groups, timeline, graph (Phase 4)
# ---------------------------------------------------------------------------

class CorrelateRequest(BaseModel):
    actor: str = Field(default="system", max_length=127)


class CorrelationRunResponse(BaseModel):
    run_id: str
    case_id: str
    status: RunStatus
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    stats: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class CorrelationEventSummary(BaseModel):
    """Compact event reference used in links, groups, and the timeline."""

    event_id: str
    timestamp: Optional[datetime] = None
    source_type: SourceType
    event_type: str = ""
    user: Optional[str] = None
    host: Optional[str] = None
    source_ip: Optional[str] = None
    destination_ip: Optional[str] = None
    process: Optional[str] = None
    file_path: Optional[str] = None
    action: Optional[str] = None
    anomaly_score: Optional[float] = None
    is_anomalous: bool = False
    evidence_id: str = ""


class CorrelationSummary(BaseModel):
    correlation_id: str
    case_id: str
    run_id: str
    correlation_type: CorrelationType
    event_a: CorrelationEventSummary
    event_b: CorrelationEventSummary
    time_delta_seconds: Optional[float] = None
    confidence: float
    confidence_band: str
    reason: str
    shared_entities: dict[str, str] = {}
    evidence_ids: list[str] = []
    created_at: datetime


class CorrelationDetailResponse(CorrelationSummary):
    disclaimer: str = ""
    event_a_detail: Optional[EventDetailResponse] = None
    event_b_detail: Optional[EventDetailResponse] = None


class CorrelationListResponse(BaseModel):
    correlations: list[CorrelationSummary] = []
    total: int = 0
    limit: int = 100
    offset: int = 0
    disclaimer: str = ""


class GroupSummary(BaseModel):
    group_id: str
    case_id: str
    run_id: str
    kind: GroupKind
    title: str
    severity: SeverityLevel
    explanation: str
    time_start: Optional[datetime] = None
    time_end: Optional[datetime] = None
    event_count: int = 0
    correlation_count: int = 0
    evidence_ids: list[str] = []
    correlation_uids: list[str] = []
    created_at: datetime


class GroupDetailResponse(GroupSummary):
    member_events: list[CorrelationEventSummary] = []
    disclaimer: str = ""


class GroupListResponse(BaseModel):
    groups: list[GroupSummary] = []
    total: int = 0
    limit: int = 100
    offset: int = 0
    disclaimer: str = ""


class TimelineEntry(BaseModel):
    timestamp: Optional[datetime] = None
    event_id: str
    source_type: SourceType
    event_type: str = ""
    user: Optional[str] = None
    host: Optional[str] = None
    process: Optional[str] = None
    file_path: Optional[str] = None
    action: Optional[str] = None
    anomaly_score: Optional[float] = None
    is_anomalous: bool = False
    significance: TimelineSignificance
    reasons: list[str] = []
    finding_ids: list[str] = []
    correlation_ids: list[str] = []
    evidence_id: str = ""
    context: bool = False


class TimelineResponse(BaseModel):
    case_id: str
    label: str
    disclaimer: str
    entries: list[TimelineEntry] = []
    total: int = 0
    truncated: bool = False
    note: Optional[str] = None


class GraphNode(BaseModel):
    id: str
    type: Literal["evidence", "finding", "event"]
    label: str
    detail: Optional[str] = None
    significance: Optional[TimelineSignificance] = None
    severity: Optional[SeverityLevel] = None


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: Literal["contains", "triggered", "correlated"]
    label: str
    correlation_type: Optional[CorrelationType] = None
    confidence: Optional[float] = None


class GraphTableRow(BaseModel):
    source: str
    relation: str
    target: str


class GraphResponse(BaseModel):
    case_id: str
    run_id: Optional[str] = None
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    table_rows: list[GraphTableRow] = []
    truncated: bool = False
    max_nodes: int = 0
    max_edges: int = 0
    disclaimer: str = ""
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Investigation assistant (Phase 5)
# ---------------------------------------------------------------------------

class AssistantQueryRequest(BaseModel):
    """A bounded free-text question to the investigation assistant."""

    question: str = Field(
        min_length=1,
        max_length=config.ASSISTANT_MAX_QUESTION_LENGTH,
        description="The question. Long or blank questions are rejected by the schema.",
    )
    actor: str = Field(default="investigator", max_length=127)


class AssistantSource(BaseModel):
    """A clickable, case-scoped reference cited by an answer."""

    type: Literal[
        "finding", "event", "evidence", "correlation", "group", "case", "run"
    ]
    id: str
    label: str = ""


class AssistantQueryResponse(BaseModel):
    """A persisted assistant question/answer pair (append-only history)."""

    query_id: int
    case_id: str
    question: str
    intent: str
    answer: str
    evidence: list[str] = []
    basis: list[str] = []
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    sources: list[AssistantSource] = []
    disclaimer: str = ""
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Forensic reports (Phase 6)
# ---------------------------------------------------------------------------

class ReportGenerateRequest(BaseModel):
    """Bounded request to generate one immutable, case-scoped report snapshot."""

    title: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional custom title; defaults to the canonical report title",
    )
    actor: str = Field(default="investigator", max_length=127)


class ReportSummary(BaseModel):
    """Identity of one report snapshot (list view)."""

    report_id: str
    case_id: str
    title: str
    report_version: str = REPORT_VERSION
    schema_: str = Field(default=REPORT_SCHEMA, alias="schema")
    status: str = REPORT_STATUS
    generated_at: datetime
    generated_by: str


class ReportResponse(ReportSummary):
    """Full report payload: identity fields plus the deterministic sections.

    ``sections`` is the deterministic report content (15 sections). Two
    generations from unchanged input data produce identical ``sections``;
    only the identity fields (report_id, generated_at, generated_by) differ.
    """

    sections: dict[str, Any]


# ---------------------------------------------------------------------------
# Dashboard (Phase 7) — read-only scenario statistics
# ---------------------------------------------------------------------------

class DashboardTotals(BaseModel):
    """Cross-case totals (aggregated persisted rows only; never inferred)."""

    cases: int
    evidence: int
    raw_records: int
    forensic_events: int
    processing_runs: int
    analysis_runs: int
    correlation_runs: int
    correlations: int
    investigation_groups: int
    integrity_checks: int
    custody_events: int
    rule_findings: int
    ml_findings: int
    assistant_queries: int
    investigation_reports: int
    investigator_notes: int


class FindingBreakdown(BaseModel):
    """Finding aggregates by kind, severity, and review status."""

    by_kind: dict[str, int]
    by_severity: dict[str, int]
    by_status: dict[str, int]
    total: int


class MlSummary(BaseModel):
    """Persisted ML run statistics (analyze-stage completed runs only)."""

    completed_runs: int
    windows_total: int
    windows_flagged: int
    abstained_runs: int
    ml_findings: int


class IntegritySummary(BaseModel):
    """Integrity-check outcomes across all evidence."""

    checks: int
    verified: int
    mismatch: int


class CustodySummary(BaseModel):
    """Chain-of-custody event totals by recorded action."""

    events: int
    by_action: dict[str, int]


class ProcessingSummary(BaseModel):
    """Processing-run totals and record counts, grouped by status."""

    runs: int
    records_received: int
    records_normalized: int
    records_rejected: int
    duplicates_detected: int
    by_status: dict[str, int]


class RunSummary(BaseModel):
    """Run-status groupings abstracted from persisted run rows."""

    analysis_by_status: dict[str, int]
    correlation_by_status: dict[str, int]


class CaseKpi(BaseModel):
    """Per-case key performance indicator summary (aggregated persisted data)."""

    case_id: str
    name: str
    investigator: str
    status: CaseStatus
    severity: SeverityLevel
    created_at: datetime
    last_activity: datetime
    demo: bool
    synthetic_label: Optional[str] = None
    evidence_count: int
    event_count: int
    anomalous_event_count: int
    processing_runs: int
    records_normalized: int
    records_rejected: int
    rule_findings: int
    ml_findings: int
    confirmed_findings: int
    correlations: int
    activity_groups: int
    integrity_checks: int
    integrity_verified: int
    integrity_mismatch: int
    reports: int
    custody_events: int
    assistant_queries: int


class DashboardResponse(BaseModel):
    """Read-only scenario statistics snapshot.

    Every figure is an aggregate (count, sum, or grouping) of rows already
    persisted by Phases 1–6. The dashboard performs no analysis and no writes,
    and absent data is reported as zero — no figure is ever fabricated.
    """

    generated_at: datetime
    totals: DashboardTotals
    findings: FindingBreakdown
    ml: MlSummary
    integrity: IntegritySummary
    custody: CustodySummary
    processing: ProcessingSummary
    runs: RunSummary
    cases: list[CaseKpi]


# ---------------------------------------------------------------------------
# Investigation workspace (Phase 8) — read-only analyst console
# ---------------------------------------------------------------------------

class WorkspaceCaseSummary(BaseModel):
    """Identity + headline counts of the case, all derived from persisted rows."""

    case_id: str
    name: str
    investigator: str
    status: CaseStatus
    severity: SeverityLevel
    description: str
    created_at: datetime
    last_activity: datetime
    demo: bool
    synthetic_label: Optional[str] = None
    processing_status: str
    integrity_status: str
    evidence_count: int
    event_count: int
    anomalous_event_count: int
    finding_count: int
    review_open_items: int
    correlation_count: int
    activity_group_count: int
    report_count: int


class WorkspaceProcessingStatus(BaseModel):
    """Rollup of the case's persisted processing runs (never re-processes)."""

    label: str
    runs: int
    by_status: dict[str, int]
    evidence_processed: int
    records_received: int
    records_parsed: int
    records_normalized: int
    records_rejected: int
    duplicates_detected: int


class WorkspaceEvidenceIntegrity(BaseModel):
    """Integrity-check outcomes for one evidence item (persisted rows only)."""

    checks: int = 0
    verified: int = 0
    mismatch: int = 0
    latest: Optional[Literal["VERIFIED", "MISMATCH"]] = None


class WorkspaceEvidenceItem(BaseModel):
    """One evidence item of the case with its persisted processing/integrity."""

    evidence_id: str
    original_filename: str
    evidence_type: EvidenceType
    status: EvidenceStatus
    source_description: str
    file_size: int
    sha256: str
    uploaded_at: datetime
    record_count: Optional[int] = None
    parse_ok: Optional[int] = None
    parse_rejected: Optional[int] = None
    integrity: WorkspaceEvidenceIntegrity
    latest_processing: Optional[str] = None
    event_count: int = 0


class WorkspaceEvidenceSummary(BaseModel):
    """Case-wide evidence aggregates (counts and sums only)."""

    total: int
    processed: int
    verified: int
    mismatch: int
    unverified: int
    failed: int
    total_bytes: int
    by_type: dict[str, int]
    by_status: dict[str, int]


class WorkspaceIntegritySummary(BaseModel):
    """Case-wide integrity-check totals across all evidence."""

    checks: int
    verified: int
    mismatch: int


class WorkspaceFindingItem(BaseModel):
    """Compact finding entry (rule or ML) for the workspace queue."""

    finding_id: str
    kind: Literal["rule", "ml"]
    rule_id: Optional[str] = None
    model_name: Optional[str] = None
    title: str
    severity: SeverityLevel
    status: FindingStatus
    confidence: Optional[float] = None
    anomaly_score: Optional[float] = None
    threshold: Optional[float] = None
    composite_suspicion_score: Optional[float] = None
    explanation: Optional[Any] = None
    reasons: Optional[list[str]] = None
    event_ids: list[str] = []
    evidence_ids: list[str] = []
    timestamp_start: Optional[datetime] = None
    timestamp_end: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WorkspaceFindingSummary(BaseModel):
    """Case-wide finding breakdowns (rule + ML merged)."""

    total: int
    high_severity: int
    by_kind: dict[str, int]
    by_severity: dict[str, int]
    by_status: dict[str, int]


class WorkspaceReviewSummary(BaseModel):
    """Investigator review state: open items and the review queue."""

    total: int
    open_items: int
    by_status: dict[str, int]
    queue: list[WorkspaceFindingItem] = []


class WorkspaceAssistantSummary(BaseModel):
    """Persisted assistant history for the case (append-only, bounded)."""

    query_count: int
    history: list[AssistantQueryResponse] = []


class WorkspaceReportSummary(BaseModel):
    """Latest report snapshot + bounded history (newest first)."""

    count: int
    latest: Optional[ReportSummary] = None
    reports: list[ReportSummary] = []


class WorkspaceResponse(BaseModel):
    """Read-only investigation workspace snapshot for one case.

    Every section reflects data already persisted by Phases 1–6. Building the
    workspace never runs parsing, analysis, correlation, the assistant, or
    report generation and never writes to the database — it only reads and
    re-shapes stored rows. Absent data is reported as an empty/negative state,
    never fabricated.
    """

    generated_at: datetime
    disclaimer: str
    case: WorkspaceCaseSummary
    evidence_summary: WorkspaceEvidenceSummary
    evidence: list[WorkspaceEvidenceItem] = []
    processing: WorkspaceProcessingStatus
    integrity_summary: WorkspaceIntegritySummary
    finding_summary: WorkspaceFindingSummary
    review_summary: WorkspaceReviewSummary
    timeline_summary: TimelineResponse
    correlation_summary: CorrelationListResponse
    group_summary: GroupListResponse
    graph_summary: GraphResponse
    assistant_summary: WorkspaceAssistantSummary
    report_summary: WorkspaceReportSummary


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
