"""Read-only dashboard & per-case KPI aggregation (Phase 7).

This module consumes ONLY rows already persisted by Phases 1–6. Building a
dashboard performs no new analysis, no ML inference, no scoring, and no
writes; every figure is a count, sum, or grouping of stored rows. Absent data
is reported as zero — no figure is ever fabricated or extrapolated.

Per-case rows are flagged with the canonical synthetic marker when the case
was flagged ``demo`` or any of its raw records carries the demonstration
label, matching the report layer's synthetic detection.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import terminology
from app.models import (
    AssistantQuery,
    Case,
    CaseStatus,
    ChainOfCustody,
    Correlation,
    CorrelationRun,
    Evidence,
    FindingStatus,
    ForensicEvent,
    IntegrityCheck,
    InvestigationGroup,
    InvestigationReport,
    InvestigationRun,
    InvestigatorNote,
    MlFinding,
    ProcessingRun,
    ProcessingStatus,
    RawRecord,
    RuleFinding,
    RunStage,
    RunStatus,
    SeverityLevel,
    utcnow,
)
from app.schemas import (
    CaseKpi,
    CustodySummary,
    DashboardResponse,
    DashboardTotals,
    FindingBreakdown,
    IntegritySummary,
    MlSummary,
    ProcessingSummary,
    RunSummary,
)

_ANALYZE_STAGE = RunStage.ANALYZE.value
_VERIFIED = "VERIFIED"
_MISMATCH = "MISMATCH"
_CONFIRMED = "Confirmed"


def _scalar_int(db: Session, stmt) -> int:
    return db.scalar(stmt) or 0


def _count_by_case(db: Session, model, *, where=None) -> dict[int, int]:
    """Count rows per case (keyed by integer case PK)."""
    stmt = select(model.case_id, func.count()).group_by(model.case_id)
    if where is not None:
        stmt = stmt.where(where)
    return {pk: cnt for pk, cnt in db.execute(stmt).all()}


def _sum_by_case(db: Session, model, column) -> dict[int, int]:
    """Sum one integer column per case (keyed by integer case PK)."""
    stmt = select(model.case_id, func.coalesce(func.sum(column), 0)).group_by(model.case_id)
    return {pk: int(total) for pk, total in db.execute(stmt).all()}


def _value_counts(db: Session, model, column) -> Counter[str]:
    """Count occurrences of a string column per value across all rows."""
    rows = db.execute(select(column, func.count()).group_by(column)).all()
    return Counter({value: cnt for value, cnt in rows})


def _integrity_per_case(
    db: Session,
) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    """(total, verified, mismatch) integrity checks per case (PK-keyed)."""
    rows = db.execute(
        select(Evidence.case_id, IntegrityCheck.result, func.count())
        .select_from(IntegrityCheck)
        .join(Evidence, IntegrityCheck.evidence_id == Evidence.id)
        .group_by(Evidence.case_id, IntegrityCheck.result)
    ).all()
    total: dict[int, int] = {}
    verified: dict[int, int] = {}
    mismatch: dict[int, int] = {}
    for case_pk, result, cnt in rows:
        total[case_pk] = total.get(case_pk, 0) + cnt
        if result == _VERIFIED:
            verified[case_pk] = verified.get(case_pk, 0) + cnt
        elif result == _MISMATCH:
            mismatch[case_pk] = mismatch.get(case_pk, 0) + cnt
    return total, verified, mismatch


def _synthetic_case_ids(db: Session) -> set[int]:
    """Case PKs whose raw records carry the canonical demonstration marker."""
    evidence_map = dict(db.execute(select(Evidence.id, Evidence.case_id)).all())
    marker_rows = db.execute(
        select(RawRecord.evidence_id).where(
            RawRecord.content.like(f"%{terminology.DEMO_LABEL}%")
        )
    ).all()
    return {evidence_map[ev_id] for ev_id, in marker_rows if ev_id in evidence_map}


def _ml_summary(db: Session) -> MlSummary:
    """Aggregate persist ML run statistics from analyze-stage completed runs."""
    runs = db.scalars(
        select(InvestigationRun).where(
            InvestigationRun.stage == _ANALYZE_STAGE,
            InvestigationRun.status == RunStatus.COMPLETED.value,
        )
    ).all()
    windows_total = 0
    windows_flagged = 0
    abstained_runs = 0
    for run in runs:
        stats: dict[str, Any] = run.stats or {}
        windows_total += int(stats.get("windows_total") or 0)
        windows_flagged += int(stats.get("windows_flagged") or 0)
        if stats.get("abstained") is True or stats.get("abstain_reason"):
            abstained_runs += 1
    return MlSummary(
        completed_runs=len(runs),
        windows_total=windows_total,
        windows_flagged=windows_flagged,
        abstained_runs=abstained_runs,
        ml_findings=_scalar_int(db, select(func.count()).select_from(MlFinding)),
    )


def _build_per_case_kpis(db: Session) -> list[CaseKpi]:
    cases = list(db.scalars(select(Case).order_by(Case.created_at.desc(), Case.id.desc())))

    evidence_by_case = _count_by_case(db, Evidence)
    events_by_case = _count_by_case(db, ForensicEvent)
    anomalous_by_case = _count_by_case(
        db, ForensicEvent, where=ForensicEvent.is_anomalous.is_(True)
    )
    processing_by_case = _count_by_case(db, ProcessingRun)
    normalized_by_case = _sum_by_case(db, ProcessingRun, ProcessingRun.records_normalized)
    rejected_by_case = _sum_by_case(db, ProcessingRun, ProcessingRun.records_rejected)
    rule_by_case = _count_by_case(db, RuleFinding)
    ml_by_case = _count_by_case(db, MlFinding)
    confirmed_rule = _count_by_case(db, RuleFinding, where=RuleFinding.status == _CONFIRMED)
    confirmed_ml = _count_by_case(db, MlFinding, where=MlFinding.status == _CONFIRMED)
    correlations_by_case = _count_by_case(db, Correlation)
    groups_by_case = _count_by_case(db, InvestigationGroup)
    reports_by_case = _count_by_case(db, InvestigationReport)
    custody_by_case = _count_by_case(db, ChainOfCustody)
    queries_by_case = _count_by_case(db, AssistantQuery)
    integrity_total, integrity_verified, integrity_mismatch = _integrity_per_case(db)
    synthetic_cases = _synthetic_case_ids(db)

    return [
        CaseKpi(
            case_id=case.case_id,
            name=case.name,
            investigator=case.investigator,
            status=CaseStatus(case.status),
            severity=SeverityLevel(case.severity),
            created_at=case.created_at,
            last_activity=case.last_activity,
            demo=case.demo,
            synthetic_label=(
                terminology.DEMO_LABEL
                if case.demo or case.id in synthetic_cases
                else None
            ),
            evidence_count=evidence_by_case.get(case.id, 0),
            event_count=events_by_case.get(case.id, 0),
            anomalous_event_count=anomalous_by_case.get(case.id, 0),
            processing_runs=processing_by_case.get(case.id, 0),
            records_normalized=normalized_by_case.get(case.id, 0),
            records_rejected=rejected_by_case.get(case.id, 0),
            rule_findings=rule_by_case.get(case.id, 0),
            ml_findings=ml_by_case.get(case.id, 0),
            confirmed_findings=confirmed_rule.get(case.id, 0) + confirmed_ml.get(case.id, 0),
            correlations=correlations_by_case.get(case.id, 0),
            activity_groups=groups_by_case.get(case.id, 0),
            integrity_checks=integrity_total.get(case.id, 0),
            integrity_verified=integrity_verified.get(case.id, 0),
            integrity_mismatch=integrity_mismatch.get(case.id, 0),
            reports=reports_by_case.get(case.id, 0),
            custody_events=custody_by_case.get(case.id, 0),
            assistant_queries=queries_by_case.get(case.id, 0),
        )
        for case in cases
    ]


def build_dashboard(db: Session) -> DashboardResponse:
    """Aggregate persisted rows into a read-only dashboard snapshot."""
    rule_count = _scalar_int(db, select(func.count()).select_from(RuleFinding))
    ml_count = _scalar_int(db, select(func.count()).select_from(MlFinding))
    by_kind = {"rule": rule_count, "ml": ml_count}

    severity_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for model in (RuleFinding, MlFinding):
        severity_counts.update(_value_counts(db, model, model.severity))
        status_counts.update(_value_counts(db, model, model.status))

    analysis_status = dict(
        db.execute(
            select(InvestigationRun.status, func.count())
            .where(InvestigationRun.stage == _ANALYZE_STAGE)
            .group_by(InvestigationRun.status)
        ).all()
    )
    correlation_status = dict(
        db.execute(
            select(CorrelationRun.status, func.count()).group_by(CorrelationRun.status)
        ).all()
    )
    processing_status = dict(
        db.execute(
            select(ProcessingRun.status, func.count()).group_by(ProcessingRun.status)
        ).all()
    )
    custody_by_action = dict(
        db.execute(
            select(ChainOfCustody.action, func.count()).group_by(ChainOfCustody.action)
        ).all()
    )
    integrity_by_result = dict(
        db.execute(
            select(IntegrityCheck.result, func.count()).group_by(IntegrityCheck.result)
        ).all()
    )

    totals = DashboardTotals(
        cases=_scalar_int(db, select(func.count()).select_from(Case)),
        evidence=_scalar_int(db, select(func.count()).select_from(Evidence)),
        raw_records=_scalar_int(db, select(func.count()).select_from(RawRecord)),
        forensic_events=_scalar_int(db, select(func.count()).select_from(ForensicEvent)),
        processing_runs=_scalar_int(db, select(func.count()).select_from(ProcessingRun)),
        analysis_runs=_scalar_int(db, select(func.count()).select_from(InvestigationRun)),
        correlation_runs=_scalar_int(db, select(func.count()).select_from(CorrelationRun)),
        correlations=_scalar_int(db, select(func.count()).select_from(Correlation)),
        investigation_groups=_scalar_int(db, select(func.count()).select_from(InvestigationGroup)),
        integrity_checks=_scalar_int(db, select(func.count()).select_from(IntegrityCheck)),
        custody_events=_scalar_int(db, select(func.count()).select_from(ChainOfCustody)),
        rule_findings=rule_count,
        ml_findings=ml_count,
        assistant_queries=_scalar_int(db, select(func.count()).select_from(AssistantQuery)),
        investigation_reports=_scalar_int(
            db, select(func.count()).select_from(InvestigationReport)
        ),
        investigator_notes=_scalar_int(
            db, select(func.count()).select_from(InvestigatorNote)
        ),
    )

    received = _sum_by_case(db, ProcessingRun, ProcessingRun.records_received)
    normalized = _sum_by_case(db, ProcessingRun, ProcessingRun.records_normalized)
    rejected = _sum_by_case(db, ProcessingRun, ProcessingRun.records_rejected)
    duplicates = _sum_by_case(db, ProcessingRun, ProcessingRun.duplicates_detected)

    return DashboardResponse(
        generated_at=utcnow(),
        totals=totals,
        findings=FindingBreakdown(
            by_kind=by_kind,
            by_severity={
                value: severity_counts.get(value, 0) for value in SeverityLevel
            },
            by_status={
                value: status_counts.get(value, 0) for value in FindingStatus
            },
            total=rule_count + ml_count,
        ),
        ml=_ml_summary(db),
        integrity=IntegritySummary(
            checks=totals.integrity_checks,
            verified=integrity_by_result.get(_VERIFIED, 0),
            mismatch=integrity_by_result.get(_MISMATCH, 0),
        ),
        custody=CustodySummary(
            events=totals.custody_events,
            by_action=custody_by_action,
        ),
        processing=ProcessingSummary(
            runs=totals.processing_runs,
            records_received=sum(received.values()),
            records_normalized=sum(normalized.values()),
            records_rejected=sum(rejected.values()),
            duplicates_detected=sum(duplicates.values()),
            by_status={
                value: processing_status.get(value, 0) for value in ProcessingStatus
            },
        ),
        runs=RunSummary(
            analysis_by_status={
                value: analysis_status.get(value, 0) for value in RunStatus
            },
            correlation_by_status={
                value: correlation_status.get(value, 0) for value in RunStatus
            },
        ),
        cases=_build_per_case_kpis(db),
    )