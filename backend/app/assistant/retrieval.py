"""Case-scoped retrieval for the assistant (Phase 5).

Every query path is forcibly scoped to a single ``Case`` — nothing is ever
retrieved globally. All limits are bounded by config caps (the pipeline's own
caps apply to timeline/graph; ``ASSISTANT_TOP_N`` bounds citations). Rows keep
their database identifiers so the answerer can emit evidence-backed, clickable
source references.

This module reuses the existing Phase 0-4 services; it does not add parsers,
models, or correlation logic.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.models import (
    Case,
    Correlation,
    CorrelationRun,
    Evidence,
    FindingStatus,
    ForensicEvent,
    IntegrityCheck,
    IntegrityResult,
    InvestigationGroup,
    InvestigationRun,
    MlFinding,
    ProcessingRun,
    RuleFinding,
)
from app.services import analysis_service, case_service, correlate_service, processing_service

SEVERITY_ORDER = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "Info": 0}


def case_has_evidence(db: Session, case: Case) -> bool:
    return case_service.evidence_count(db, case) > 0


def case_meta(db: Session, case: Case) -> dict:
    return {
        "case_id": case.case_id,
        "name": case.name,
        "description": case.description,
        "status": case.status,
        "severity": case.severity,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "evidence_count": case_service.evidence_count(db, case),
        "finding_count": case_service.finding_count(db, case),
    }


def evidence_list(db: Session, case: Case, *, limit: int = 100) -> list[Evidence]:
    rows = list(
        db.scalars(
            select(Evidence)
            .where(Evidence.case_id == case.id)
            .order_by(Evidence.evidence_id.asc())
        )
    )
    return rows[:limit]


def findings(
    db: Session,
    case: Case,
    *,
    kind: str | None = None,
    status: FindingStatus | None = None,
    limit: int | None = None,
) -> list[tuple[str, RuleFinding | MlFinding]]:
    rows, _ = analysis_service.list_findings(
        db, case, kind=kind, status=status, limit=limit or config.ASSISTANT_TOP_N
    )
    return rows


def top_finding(
    db: Session, case: Case
) -> tuple[str, RuleFinding | MlFinding] | None:
    """Highest-severity finding, newest first on ties (deterministic)."""
    rows = findings(db, case)
    if not rows:
        return None

    def _key(item: tuple[str, RuleFinding | MlFinding]) -> tuple:
        _kind, row = item
        return (
            SEVERITY_ORDER.get(row.severity, 0),
            row.created_at.isoformat() if row.created_at else "",
            row.finding_uid,
        )

    return max(rows, key=_key)


def finding_detail(
    db: Session, case: Case, finding_id: str
) -> tuple[str, RuleFinding | MlFinding, list[ForensicEvent]]:
    kind, row = analysis_service.get_finding(db, case, finding_id)
    events = analysis_service.finding_events(db, kind, row)
    return kind, row, events


def timeline(db: Session, case: Case) -> dict:
    response = correlate_service.timeline(db, case)
    entries = list(getattr(response, "entries", []) or [])
    return {
        "entries": entries,
        "total": getattr(response, "total", len(entries)),
        "truncated": bool(getattr(response, "truncated", False)),
        "note": getattr(response, "note", None),
    }


def correlations(
    db: Session, case: Case, *, limit: int | None = None
) -> tuple[list[Correlation], int, CorrelationRun | None]:
    rows, total, run = correlate_service.list_correlations(
        db, case, limit=limit or config.ASSISTANT_TOP_N
    )
    return rows, total, run


def correlation_detail(
    db: Session, case: Case, correlation_uid: str
) -> Correlation:
    return correlate_service.get_correlation(db, case, correlation_uid)


def groups(
    db: Session, case: Case, *, limit: int | None = None
) -> tuple[list[InvestigationGroup], int, CorrelationRun | None]:
    rows, total, run = correlate_service.list_groups(
        db, case, limit=limit or config.ASSISTANT_TOP_N
    )
    return rows, total, run


def group_detail(db: Session, case: Case, group_uid: str) -> InvestigationGroup:
    return correlate_service.get_group(db, case, group_uid)


def analysis_latest(db: Session, case: Case) -> InvestigationRun | None:
    completed = [
        run
        for run in analysis_service.runs_for_case(db, case)
        if run.status == "Completed"
    ]
    if not completed:
        return None
    return max(completed, key=lambda run: run.finished_at or run.created_at)


def integrity(db: Session, case: Case) -> dict:
    evidence_rows = evidence_list(db, case, limit=500)
    evidence_ids = [row.id for row in evidence_rows]
    latest: dict[int, IntegrityCheck] = {}
    if evidence_ids:
        checks = list(
            db.scalars(
                select(IntegrityCheck)
                .where(IntegrityCheck.evidence_id.in_(evidence_ids))
                .order_by(IntegrityCheck.id.asc())
            )
        )
        for check in checks:
            latest[check.evidence_id] = check
    verified, mismatch, pending = [], [], []
    for row in evidence_rows:
        check = latest.get(row.id)
        if check is None:
            pending.append(row)
        elif check.result == IntegrityResult.VERIFIED.value:
            verified.append((row, check))
        else:
            mismatch.append((row, check))
    return {
        "verified": verified,
        "mismatch": mismatch,
        "pending": pending,
    }


def processing_summary(db: Session, case: Case) -> dict:
    runs = processing_runs(db, case)
    by_status: dict[str, int] = {}
    total_parsed = total_normalized = total_rejected = total_duplicates = 0
    for run in runs:
        by_status[run.status] = by_status.get(run.status, 0) + 1
        total_parsed += run.records_parsed or 0
        total_normalized += run.records_normalized or 0
        total_rejected += run.records_rejected or 0
        total_duplicates += run.duplicates_detected or 0
    evidence_rows = evidence_list(db, case, limit=500)
    return {
        "runs": runs,
        "by_status": by_status,
        "total_parsed": total_parsed,
        "total_normalized": total_normalized,
        "total_rejected": total_rejected,
        "total_duplicates": total_duplicates,
        "evidence": evidence_rows,
    }


def processing_runs(db: Session, case: Case) -> list[ProcessingRun]:
    return processing_service.runs_for_case(db, case)


def run_caps() -> dict:
    return {
        "timeline_max_entries": config.TIMELINE_MAX_ENTRIES,
        "assistant_top_n": config.ASSISTANT_TOP_N,
    }