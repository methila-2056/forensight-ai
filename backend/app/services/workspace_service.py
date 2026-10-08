"""Phase 8 investigation workspace — read-only aggregation of persisted rows.

The workspace is a presentation layer. Building it never runs the pipeline
(no parsing/normalization), never re-runs analysis, correlation, the assistant,
or report generation, and never writes or mutates rows. It reads and re-shapes
data already persisted by Phases 1–6, scoped strictly to one case.

Every query filters by ``case.id``; a workspace for a case can therefore never
expose rows of another case. Absent data is reported honestly (empty lists,
zero counts, "Not processed") — nothing is fabricated.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import terminology
from app.assistant import service as assistant_service
from app.models import (
    AssistantQuery,
    Case,
    Evidence,
    ForensicEvent,
    IntegrityCheck,
    MlFinding,
    ProcessingRun,
    RawRecord,
    RuleFinding,
)
from app.schemas import (
    AssistantQueryResponse,
    CorrelationListResponse,
    GraphResponse,
    GroupListResponse,
    ReportSummary,
    TimelineResponse,
    WorkspaceAssistantSummary,
    WorkspaceCaseSummary,
    WorkspaceEvidenceIntegrity,
    WorkspaceEvidenceItem,
    WorkspaceEvidenceSummary,
    WorkspaceFindingItem,
    WorkspaceFindingSummary,
    WorkspaceIntegritySummary,
    WorkspaceProcessingStatus,
    WorkspaceReportSummary,
    WorkspaceResponse,
    WorkspaceReviewSummary,
)
from app.services import correlate_service, report_service

# Bounded payload caps for the compact workspace view.
WORKSPACE_FINDINGS_LIMIT = 50
WORKSPACE_CORRELATIONS_LIMIT = 100
WORKSPACE_GROUPS_LIMIT = 100
WORKSPACE_HISTORY_LIMIT = 10
WORKSPACE_REPORTS_LIMIT = 20
WORKSPACE_ITEM_IDS_LIMIT = 50

_SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
_OPEN_STATUSES = {"New", "Under Review"}


def _scalar(db: Session, stmt) -> int:
    return db.scalar(stmt) or 0


def _synthetic(db: Session, case: Case) -> str | None:
    """Canonical demonstration label when the case carries it."""
    if case.demo:
        return terminology.DEMO_LABEL
    evidence = list(
        db.scalars(select(Evidence.id).where(Evidence.case_id == case.id))
    )
    if not evidence:
        return None
    marker = _scalar(
        db,
        select(func.count())
        .select_from(RawRecord)
        .where(
            RawRecord.evidence_id.in_(evidence),
            RawRecord.content.like(f"%{terminology.DEMO_LABEL}%"),
        ),
    )
    return terminology.DEMO_LABEL if marker else None


# ---------------------------------------------------------------------------
# Integrity + processing rollups (persisted rows only)
# ---------------------------------------------------------------------------

def _integrity_by_evidence(db: Session, case: Case) -> dict[int, WorkspaceEvidenceIntegrity]:
    """Per-evidence check counts + latest result (checked_at then id desc)."""
    rows = db.execute(
        select(IntegrityCheck.evidence_id, IntegrityCheck.result)
        .select_from(IntegrityCheck)
        .join(Evidence, IntegrityCheck.evidence_id == Evidence.id)
        .where(Evidence.case_id == case.id)
        .order_by(IntegrityCheck.checked_at.desc(), IntegrityCheck.id.desc())
    ).all()
    outcome: dict[int, WorkspaceEvidenceIntegrity] = {}
    latest_seen: set[int] = set()
    for evidence_pk, result in rows:
        item = outcome.setdefault(evidence_pk, WorkspaceEvidenceIntegrity())
        item.checks += 1
        if result == "VERIFIED":
            item.verified += 1
        elif result == "MISMATCH":
            item.mismatch += 1
        if evidence_pk not in latest_seen:
            item.latest = result  # type: ignore[assignment]
            latest_seen.add(evidence_pk)
    return outcome


def _processing_by_evidence(
    db: Session, case: Case
) -> tuple[dict[int, str], WorkspaceProcessingStatus]:
    """(latest run status per evidence, case rollup) from persisted runs."""
    runs = db.scalars(
        select(ProcessingRun)
        .where(ProcessingRun.case_id == case.id)
        .order_by(ProcessingRun.id.desc())
    ).all()

    by_status = Counter()
    evidence_processed: set[int] = set()
    latest_by_evidence: dict[int, str] = {}
    seen: set[int] = set()
    records_received = records_parsed = records_normalized = 0
    records_rejected = duplicates_detected = 0

    for run in runs:
        by_status[run.status] += 1
        records_received += run.records_received or 0
        records_parsed += run.records_parsed or 0
        records_normalized += run.records_normalized or 0
        records_rejected += run.records_rejected or 0
        duplicates_detected += run.duplicates_detected or 0
        evidence_processed.add(run.evidence_id)
        if run.evidence_id not in seen:
            latest_by_evidence[run.evidence_id] = run.status
            seen.add(run.evidence_id)

    if not runs:
        label = terminology.PROCESSING_NOT_PROCESSED
    elif any(status == "Failed" for status in by_status):
        label = terminology.PROCESSING_FAILED
    elif any(status == "Partial" for status in by_status):
        label = terminology.PROCESSING_PARTIAL
    elif any(status in ("Pending", "Processing") for status in by_status):
        label = terminology.PROCESSING_IN_PROGRESS
    else:
        label = terminology.PROCESSING_COMPLETED

    return latest_by_evidence, WorkspaceProcessingStatus(
        label=label,
        runs=len(runs),
        by_status=dict(by_status),
        evidence_processed=len(evidence_processed),
        records_received=records_received,
        records_parsed=records_parsed,
        records_normalized=records_normalized,
        records_rejected=records_rejected,
        duplicates_detected=duplicates_detected,
    )


# ---------------------------------------------------------------------------
# Evidence summary
# ---------------------------------------------------------------------------

def _evidence_items(
    db: Session,
    case: Case,
    integrity: dict[int, WorkspaceEvidenceIntegrity],
    latest_processing: dict[int, str],
    event_counts: dict[int, int],
) -> list[WorkspaceEvidenceItem]:
    rows = db.scalars(
        select(Evidence)
        .where(Evidence.case_id == case.id)
        .order_by(Evidence.evidence_id.asc())
    ).all()
    return [
        WorkspaceEvidenceItem(
            evidence_id=row.evidence_id,
            original_filename=row.original_filename,
            evidence_type=row.evidence_type,  # type: ignore[arg-type]
            status=row.status,  # type: ignore[arg-type]
            source_description=row.source_description,
            file_size=row.file_size,
            sha256=row.sha256,
            uploaded_at=row.uploaded_at,
            record_count=row.record_count,
            parse_ok=row.parse_ok,
            parse_rejected=row.parse_rejected,
            integrity=integrity.get(row.id, WorkspaceEvidenceIntegrity()),
            latest_processing=latest_processing.get(row.id),
            event_count=event_counts.get(row.id, 0),
        )
        for row in rows
    ]


def _evidence_summary(items: list[WorkspaceEvidenceItem]) -> WorkspaceEvidenceSummary:
    processed = verified = mismatch = unverified = failed = 0
    total_bytes = 0
    by_type: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    for item in items:
        by_type[item.evidence_type.value] += 1  # type: ignore[union-attr]
        by_status[item.status.value] += 1  # type: ignore[union-attr]
        total_bytes += item.file_size
        if item.status.value == "Processed":
            processed += 1
        if item.status.value == "Error":
            failed += 1
        latest = item.integrity.latest
        if latest == "VERIFIED":
            verified += 1
        elif latest == "MISMATCH":
            mismatch += 1
        else:
            unverified += 1
    return WorkspaceEvidenceSummary(
        total=len(items),
        processed=processed,
        verified=verified,
        mismatch=mismatch,
        unverified=unverified,
        failed=failed,
        total_bytes=total_bytes,
        by_type=dict(by_type),
        by_status=dict(by_status),
    )


def _integrity_summary(
    items: list[WorkspaceEvidenceItem],
) -> WorkspaceIntegritySummary:
    checks = verified = mismatch = 0
    for item in items:
        checks += item.integrity.checks
        verified += item.integrity.verified
        mismatch += item.integrity.mismatch
    return WorkspaceIntegritySummary(checks=checks, verified=verified, mismatch=mismatch)


# ---------------------------------------------------------------------------
# Findings + review queue
# ---------------------------------------------------------------------------

def _finding_items(db: Session, case: Case) -> list[WorkspaceFindingItem]:
    items: list[WorkspaceFindingItem] = []
    rule_rows = db.scalars(
        select(RuleFinding).where(RuleFinding.case_id == case.id)
    ).all()
    ml_rows = db.scalars(
        select(MlFinding).where(MlFinding.case_id == case.id)
    ).all()
    for row in rule_rows:
        items.append(
            WorkspaceFindingItem(
                finding_id=row.finding_uid,
                kind="rule",
                rule_id=row.rule_id,
                title=row.title,
                severity=row.severity,  # type: ignore[arg-type]
                status=row.status,  # type: ignore[arg-type]
                confidence=row.confidence,
                composite_suspicion_score=row.composite_suspicion_score,
                explanation=row.explanation,
                reasons=list(row.reasons or [])[:WORKSPACE_ITEM_IDS_LIMIT],
                event_ids=list(row.triggered_event_ids or [])[:WORKSPACE_ITEM_IDS_LIMIT],
                evidence_ids=list(row.evidence_ids or [])[:WORKSPACE_ITEM_IDS_LIMIT],
                timestamp_start=row.timestamp_start,
                timestamp_end=row.timestamp_end,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    for row in ml_rows:
        items.append(
            WorkspaceFindingItem(
                finding_id=row.finding_uid,
                kind="ml",
                model_name=row.model_name,
                title=row.title,
                severity=row.severity,  # type: ignore[arg-type]
                status=row.status,  # type: ignore[arg-type]
                anomaly_score=row.score,
                threshold=row.threshold,
                composite_suspicion_score=row.composite_suspicion_score,
                explanation=row.explanation,
                event_ids=list(row.event_ids or [])[:WORKSPACE_ITEM_IDS_LIMIT],
                evidence_ids=list(row.evidence_ids or [])[:WORKSPACE_ITEM_IDS_LIMIT],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    items.sort(
        key=lambda item: (
            _SEVERITY_ORDER.get(item.severity.value, 99),  # type: ignore[union-attr]
            item.created_at,
            item.finding_id,
        ),
        reverse=False,
    )
    return items


def _finding_summary(items: list[WorkspaceFindingItem]) -> WorkspaceFindingSummary:
    by_kind: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    high = 0
    for item in items:
        by_kind[item.kind] += 1
        by_severity[item.severity.value] += 1  # type: ignore[union-attr]
        by_status[item.status.value] += 1  # type: ignore[union-attr]
        if item.severity.value in ("Critical", "High"):  # type: ignore[union-attr]
            high += 1
    return WorkspaceFindingSummary(
        total=len(items),
        high_severity=high,
        by_kind=dict(by_kind),
        by_severity=dict(by_severity),
        by_status=dict(by_status),
    )


def _review_summary(items: list[WorkspaceFindingItem]) -> WorkspaceReviewSummary:
    by_status: Counter[str] = Counter()
    open_items = 0
    for item in items:
        by_status[item.status.value] += 1  # type: ignore[union-attr]
        if item.status.value in _OPEN_STATUSES:  # type: ignore[union-attr]
            open_items += 1
    queue = [item for item in items if item.status.value in _OPEN_STATUSES]
    queue.sort(
        key=lambda item: (_SEVERITY_ORDER.get(item.severity.value, 99), item.created_at)  # type: ignore[union-attr]
    )
    return WorkspaceReviewSummary(
        total=len(items),
        open_items=open_items,
        by_status=dict(by_status),
        queue=queue[:WORKSPACE_FINDINGS_LIMIT],
    )


# ---------------------------------------------------------------------------
# Case summary headline
# ---------------------------------------------------------------------------

def _case_summary(
    db: Session,
    case: Case,
    items: list[WorkspaceEvidenceItem],
    findings: list[WorkspaceFindingItem],
    processing: WorkspaceProcessingStatus,
    integrity: WorkspaceIntegritySummary,
    review: WorkspaceReviewSummary,
    corr_total: int,
    group_total: int,
    reports: list[WorkspaceReportSummary],
) -> WorkspaceCaseSummary:
    events = _scalar(
        db,
        select(func.count())
        .select_from(ForensicEvent)
        .where(ForensicEvent.case_id == case.id),
    )
    anomalous = _scalar(
        db,
        select(func.count())
        .select_from(ForensicEvent)
        .where(
            ForensicEvent.case_id == case.id,
            ForensicEvent.is_anomalous.is_(True),
        ),
    )

    if not items or integrity.checks == 0:
        integrity_status = terminology.INTEGRITY_UNVERIFIED
    elif integrity.mismatch > 0:
        integrity_status = terminology.INTEGRITY_LATEST_MISMATCH
    elif sum(1 for item in items if item.integrity.latest == "VERIFIED") < len(items):
        integrity_status = terminology.INTEGRITY_PARTIAL
    else:
        integrity_status = terminology.INTEGRITY_LATEST_VERIFIED

    return WorkspaceCaseSummary(
        case_id=case.case_id,
        name=case.name,
        investigator=case.investigator,
        status=case.status,  # type: ignore[arg-type]
        severity=case.severity,  # type: ignore[arg-type]
        description=case.description,
        created_at=case.created_at,
        last_activity=case.last_activity,
        demo=case.demo,
        synthetic_label=_synthetic(db, case),
        processing_status=processing.label,
        integrity_status=integrity_status,
        evidence_count=len(items),
        event_count=events,
        anomalous_event_count=anomalous,
        finding_count=len(findings),
        review_open_items=review.open_items,
        correlation_count=corr_total,
        activity_group_count=group_total,
        report_count=reports.count,
    )


# ---------------------------------------------------------------------------
# Workspace assembly
# ---------------------------------------------------------------------------

def build_workspace(db: Session, case: Case) -> WorkspaceResponse:
    """Assemble the read-only workspace snapshot for one case (no writes)."""
    integrity_by_evidence = _integrity_by_evidence(db, case)
    latest_processing, processing = _processing_by_evidence(db, case)
    event_counts = dict(
        db.execute(
            select(ForensicEvent.evidence_id, func.count())
            .where(ForensicEvent.case_id == case.id)
            .group_by(ForensicEvent.evidence_id)
        ).all()
    )

    evidence_items = _evidence_items(
        db, case, integrity_by_evidence, latest_processing, event_counts
    )
    evidence_summary = _evidence_summary(evidence_items)
    integrity_summary = _integrity_summary(evidence_items)

    finding_items = _finding_items(db, case)
    finding_summary = _finding_summary(finding_items)
    review_summary = _review_summary(finding_items)

    timeline_summary: TimelineResponse = correlate_service.timeline(db, case)
    corr_rows, corr_total, corr_run = correlate_service.list_correlations(
        db, case, limit=WORKSPACE_CORRELATIONS_LIMIT
    )
    correlation_summary: CorrelationListResponse = correlate_service.correlation_list_response(
        db,
        case,
        rows=corr_rows,
        total=corr_total,
        limit=WORKSPACE_CORRELATIONS_LIMIT,
        offset=0,
        run=corr_run,
    )
    group_rows, group_total, _ = correlate_service.list_groups(
        db, case, limit=WORKSPACE_GROUPS_LIMIT
    )
    group_summary: GroupListResponse = correlate_service.group_list_response(
        db,
        case,
        rows=group_rows,
        total=group_total,
        limit=WORKSPACE_GROUPS_LIMIT,
        offset=0,
    )
    graph_summary: GraphResponse = correlate_service.graph(db, case)

    reports = report_service.list_reports(db, case)
    latest_report = (
        report_service.report_summary(reports[0]) if reports else None
    )
    report_summary = WorkspaceReportSummary(
        count=len(reports),
        latest=ReportSummary(**latest_report) if latest_report else None,
        reports=[
            ReportSummary(**report_service.report_summary(row))
            for row in reports[:WORKSPACE_REPORTS_LIMIT]
        ],
    )

    queries = db.scalars(
        select(AssistantQuery)
        .where(AssistantQuery.case_id == case.id)
        .order_by(AssistantQuery.id.desc())
        .limit(WORKSPACE_HISTORY_LIMIT)
    ).all()
    query_count = _scalar(
        db,
        select(func.count())
        .select_from(AssistantQuery)
        .where(AssistantQuery.case_id == case.id),
    )

    assistant_summary = WorkspaceAssistantSummary(
        query_count=query_count,
        history=[
            AssistantQueryResponse(**assistant_service.serialize(row, case_id=case.case_id))
            for row in reversed(queries)
        ],
    )

    case_summary = _case_summary(
        db,
        case,
        evidence_items,
        finding_items,
        processing,
        integrity_summary,
        review_summary,
        corr_total,
        group_total,
        report_summary,
    )

    return WorkspaceResponse(
        generated_at=datetime.utcnow(),
        disclaimer=terminology.WORKSPACE_DISCLAIMER,
        case=case_summary,
        evidence_summary=evidence_summary,
        evidence=evidence_items,
        processing=processing,
        integrity_summary=integrity_summary,
        finding_summary=finding_summary,
        review_summary=review_summary,
        timeline_summary=timeline_summary,
        correlation_summary=correlation_summary,
        group_summary=group_summary,
        graph_summary=graph_summary,
        assistant_summary=assistant_summary,
        report_summary=report_summary,
    )