"""Automated analysis service (Phase 3).

    normalized ForensicEvents → feature windows → Strategy A anomaly scoring
    → rule engine → fusion (Composite Suspicion Score) → RuleFinding/MlFinding

Guarantees:

* analysis reads only normalized events; raw evidence bytes are untouched
* every finding links to the triggering events and the evidence files that
  produced them (traceability ladder Finding → Event → Raw Record → Evidence)
* the run records the full methodology snapshot (model, seed, feature list,
  threshold, fusion weights, per-rule configuration)
* findings start in status ``New`` — the system never confirms or dismisses
  anything; every review transition is an investigator action recorded in the
  chain of custody
* append-only: a new run adds findings; previous findings are never deleted
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, terminology
from app.engines.features import FEATURE_VERSION, FeatureBuilder
from app.engines.ml import anomaly as anomaly_engine
from app.engines.ml.fusion import (
    FUSION_VERSION,
    WEIGHTS as FUSION_WEIGHTS,
    composite_suspicion_score,
)
from app.engines.rules import run_rules
from app.errors import ApiError
from app.models import (
    Case,
    CustodyAction,
    Evidence,
    EvidenceStatus,
    FindingStatus,
    ForensicEvent,
    InvestigationRun,
    InvestigatorNote,
    MlFinding,
    RunStage,
    RunStatus,
    RuleFinding,
    SeverityLevel,
    utcnow,
)
from app.services import custody

logger = logging.getLogger("forensight.analysis")

RULE_PREFIX = "RFND-"
ML_PREFIX = "MFND-"

_ALLOWED_TRANSITIONS: dict[FindingStatus, set[FindingStatus]] = {
    FindingStatus.NEW: {FindingStatus.UNDER_REVIEW},
    FindingStatus.UNDER_REVIEW: {FindingStatus.CONFIRMED, FindingStatus.DISMISSED},
    FindingStatus.CONFIRMED: {FindingStatus.UNDER_REVIEW, FindingStatus.DISMISSED},
    FindingStatus.DISMISSED: {FindingStatus.UNDER_REVIEW, FindingStatus.CONFIRMED},
}

ML_HIGH_SCORE = 0.9


class _AnalysisError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _next_run_uid(db: Session) -> str:
    last = db.scalar(
        select(InvestigationRun.run_uid).order_by(InvestigationRun.run_uid.desc()).limit(1)
    )
    number = int(last.split("-")[1]) + 1 if last else 1
    return f"IRUN-{number:06d}"


def _next_finding_uid(db: Session, prefix: str) -> str:
    table = RuleFinding if prefix == RULE_PREFIX else MlFinding
    last = db.scalar(
        select(table.finding_uid)
        .where(table.finding_uid.like(f"{prefix}%"))
        .order_by(table.finding_uid.desc())
        .limit(1)
    )
    number = int(last.split("-")[1]) + 1 if last else 1
    return f"{prefix}{number:06d}"


def _bump_uid(uid: str) -> str:
    prefix, number = uid.rsplit("-", 1)
    return f"{prefix}-{int(number) + 1:06d}"


def _evidence_uids(db: Session, events: list[ForensicEvent]) -> list[str]:
    ids = sorted({event.evidence_id for event in events})
    if not ids:
        return []
    rows = db.scalars(select(Evidence).where(Evidence.id.in_(ids)))
    return sorted(row.evidence_id for row in rows)


def _anchor_anomaly(events: list[ForensicEvent]) -> float | None:
    scores = [event.anomaly_score for event in events if event.anomaly_score is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 6)


def analyze_case(db: Session, *, case: Case, actor: str = "system") -> InvestigationRun:
    """Run the full Phase 3 analysis for one case and persist the findings."""
    events = list(
        db.scalars(
            select(ForensicEvent)
            .where(ForensicEvent.case_id == case.id)
            .order_by(ForensicEvent.timestamp.asc().nulls_last(), ForensicEvent.id.asc())
        )
    )
    if not events:
        raise ApiError(
            400,
            "NO_NORMALIZED_EVENTS",
            terminology.ANALYSIS_NO_EVENTS,
            detail={"case_id": case.case_id},
        )

    run = InvestigationRun(
        run_uid=_next_run_uid(db),
        case_id=case.id,
        stage=RunStage.ANALYZE,
        status=RunStatus.RUNNING,
        started_at=utcnow(),
    )
    db.add(run)
    custody.record(
        db,
        case=case,
        action=CustodyAction.ANALYZE_STARTED,
        actor=actor,
        details={"run_id": run.run_uid, "stage": "analyze", "events": len(events)},
    )
    db.commit()
    run_id = run.id

    try:
        windows = FeatureBuilder().build(events)
        outcome = anomaly_engine.score_windows(windows)

        # Annotate every event with its window's anomaly score.
        for window_score in outcome.window_scores:
            for event in window_score.window.events:
                event.anomaly_score = round(window_score.score, 6)
                event.is_anomalous = window_score.flagged

        results, rule_snapshots = run_rules(events)

        rule_findings: list[RuleFinding] = []
        next_rule_uid = _next_finding_uid(db, RULE_PREFIX)
        for result in results:
            evidence_ids = _evidence_uids(db, result.events)
            css, components = composite_suspicion_score(
                rule_severity=result.severity.value,
                anomaly_score=_anchor_anomaly(result.events),
                distinct_evidence=len(evidence_ids),
            )
            row = RuleFinding(
                finding_uid=next_rule_uid,
                case_id=case.id,
                run_id=run.id,
                rule_id=result.rule_id,
                title=result.title,
                description=result.description,
                severity=result.severity.value,
                confidence=result.confidence,
                timestamp_start=result.timestamp_start,
                timestamp_end=result.timestamp_end,
                explanation=result.explanation,
                reasons=result.reasons,
                composite_suspicion_score=css,
                components=components,
                triggered_event_ids=result.event_uids(),
                evidence_ids=evidence_ids,
                status=FindingStatus.NEW.value,
            )
            db.add(row)
            rule_findings.append(row)
            next_rule_uid = _bump_uid(next_rule_uid)
        db.flush()

        ml_findings: list[MlFinding] = []
        next_ml_uid = _next_finding_uid(db, ML_PREFIX)
        for window_score in outcome.flagged[: config.RULE_MAX_FINDINGS_PER_RULE]:
            involved = sorted(
                window_score.window.events,
                key=lambda e: (e.timestamp or datetime.min, e.id),
            )
            evidence_ids = _evidence_uids(db, involved)
            css, components = composite_suspicion_score(
                rule_severity=None,
                anomaly_score=window_score.score,
                distinct_evidence=len(evidence_ids),
            )
            severity = (
                SeverityLevel.HIGH if window_score.score >= ML_HIGH_SCORE else SeverityLevel.MEDIUM
            )
            window = window_score.window
            ml_row = MlFinding(
                finding_uid=next_ml_uid,
                    case_id=case.id,
                    run_id=run.id,
                    model_name=anomaly_engine.MODEL_NAME,
                    model_version=anomaly_engine.MODEL_VERSION,
                    title=f"Anomalous activity window {window.window_start:%H:%M}–{window.window_end:%H:%M}",
                    severity=severity.value,
                    score=round(window_score.score, 6),
                    threshold=outcome.threshold,
                    composite_suspicion_score=css,
                    components=components,
                    explanation={
                        "summary": (
                            f"Window {window.window_start:%Y-%m-%d %H:%M}–{window.window_end:%H:%M} "
                            f"has an anomaly score of {window_score.score:.3f} against a detection "
                            f"threshold of {outcome.threshold:.2f}; the raw model score also sits "
                            f"below the case reference gate "
                            f"(mean - {config.ML_Z_SIGMAS:g}·std)."
                        ),
                        "anomaly_score": round(window_score.score, 6),
                        "detection_threshold": outcome.threshold,
                        "raw_decision_score": round(window_score.raw_score, 6),
                        "score_description": terminology.ANOMALY_SCORE_DESCRIPTION,
                        "disclaimer": terminology.ANOMALY_DISCLAIMER,
                        "window_start": window.window_start.isoformat(),
                        "window_end": window.window_end.isoformat(),
                    },
                    feature_snapshot={
                        "feature_version": FEATURE_VERSION,
                        "window_start": window.window_start.isoformat(),
                        "window_end": window.window_end.isoformat(),
                        "features": dict(window.features),
                    },
                    event_ids=[event.event_uid for event in involved],
                    evidence_ids=evidence_ids,
                    status=FindingStatus.NEW.value,
            )
            db.add(ml_row)
            ml_findings.append(ml_row)
            next_ml_uid = _bump_uid(next_ml_uid)
        db.flush()

        stats = {
            **outcome.stats,
            "events_considered": len(events),
            "windows_flagged": len(outcome.flagged),
            "rule_findings": len(rule_findings),
            "ml_findings": len(ml_findings),
            "rules": rule_snapshots,
            "fusion_formula_version": FUSION_VERSION,
            "fusion_weights": dict(FUSION_WEIGHTS),
            "scope_note": terminology.ANALYSIS_SCOPE_NOTE,
            "rule_confidence_note": terminology.RULE_CONFIDENCE_NOTE,
            "abstain_note": terminology.ML_ABSTAIN_NOTE if outcome.abstained else None,
            "abstain_reason": outcome.reason or None,
            "strategy": "A (window-level, dual gate)",
        }

        run = db.get(InvestigationRun, run_id)
        run.status = RunStatus.COMPLETED
        run.stats = stats
        run.finished_at = utcnow()

        for evidence in db.scalars(select(Evidence).where(Evidence.case_id == case.id)):
            if evidence.status in (EvidenceStatus.PROCESSED, EvidenceStatus.ANALYZED):
                evidence.status = EvidenceStatus.ANALYZED

        custody.record(
            db,
            case=case,
            action=CustodyAction.ANALYZE_COMPLETED,
            actor=actor,
            details={
                "run_id": run.run_uid,
                "status": RunStatus.COMPLETED.value,
                "rule_findings": len(rule_findings),
                "ml_findings": len(ml_findings),
                "events_considered": len(events),
                "windows_total": len(windows),
                "windows_flagged": len(outcome.flagged),
            },
        )
        case.last_activity = utcnow()
        db.commit()
        db.refresh(run)
        return run

    except ApiError:
        raise
    except Exception:  # noqa: BLE001 - recorded as a FAILED run, path not exposed
        logger.exception("Analysis failed for case %s", case.case_id)
        db.rollback()
        run = db.get(InvestigationRun, run_id)
        run.status = RunStatus.FAILED
        run.error = "Automated analysis failed unexpectedly; see server logs."
        run.finished_at = utcnow()
        db.commit()
        db.refresh(run)
        return run


def runs_for_case(db: Session, case: Case) -> list[InvestigationRun]:
    return list(
        db.scalars(
            select(InvestigationRun)
            .where(InvestigationRun.case_id == case.id, InvestigationRun.stage == RunStage.ANALYZE)
            .order_by(InvestigationRun.id.desc())
        )
    )


# ---------------------------------------------------------------------------
# Finding queries (rule + ML findings are distinct tables, one merged view)
# ---------------------------------------------------------------------------

def _rows_for_case(
    db: Session,
    case: Case,
    *,
    kind: str | None = None,
    severity: SeverityLevel | None = None,
    status: FindingStatus | None = None,
    run_id: str | None = None,
) -> list[tuple[str, RuleFinding | MlFinding]]:
    rows: list[tuple[str, RuleFinding | MlFinding]] = []
    if kind in (None, "rule"):
        query = select(RuleFinding).where(RuleFinding.case_id == case.id)
        if severity is not None:
            query = query.where(RuleFinding.severity == severity.value)
        if status is not None:
            query = query.where(RuleFinding.status == status.value)
        if run_id:
            ids = _run_ids(db, case, run_id)
            query = query.where(RuleFinding.run_id.in_(ids))
        rows.extend(("rule", row) for row in db.scalars(query.order_by(RuleFinding.id.desc())))
    if kind in (None, "ml"):
        query = select(MlFinding).where(MlFinding.case_id == case.id)
        if severity is not None:
            query = query.where(MlFinding.severity == severity.value)
        if status is not None:
            query = query.where(MlFinding.status == status.value)
        if run_id:
            ids = _run_ids(db, case, run_id)
            query = query.where(MlFinding.run_id.in_(ids))
        rows.extend(("ml", row) for row in db.scalars(query.order_by(MlFinding.id.desc())))
    rows.sort(key=lambda pair: (pair[1].created_at, pair[1].finding_uid), reverse=True)
    return rows


def _run_ids(db: Session, case: Case, run_uid: str) -> list[int]:
    ids = list(
        db.scalars(
            select(InvestigationRun.id).where(
                InvestigationRun.case_id == case.id, InvestigationRun.run_uid == run_uid
            )
        )
    )
    return ids or [-1]


def list_findings(
    db: Session,
    case: Case,
    *,
    kind: str | None = None,
    severity: SeverityLevel | None = None,
    status: FindingStatus | None = None,
    run_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[tuple[str, RuleFinding | MlFinding]], int]:
    rows = _rows_for_case(
        db, case, kind=kind, severity=severity, status=status, run_id=run_id
    )
    return rows[offset : offset + limit], len(rows)


def get_finding(db: Session, case: Case, finding_id: str) -> tuple[str, RuleFinding | MlFinding]:
    if finding_id.startswith(RULE_PREFIX):
        row = db.scalar(
            select(RuleFinding).where(
                RuleFinding.finding_uid == finding_id, RuleFinding.case_id == case.id
            )
        )
        kind = "rule"
    elif finding_id.startswith(ML_PREFIX):
        row = db.scalar(
            select(MlFinding).where(
                MlFinding.finding_uid == finding_id, MlFinding.case_id == case.id
            )
        )
        kind = "ml"
    else:
        row = None
        kind = "rule"
    if row is None:
        raise ApiError(404, "FINDING_NOT_FOUND", f"Finding {finding_id} was not found.")
    return kind, row


def finding_event_uids(kind: str, row: RuleFinding | MlFinding) -> list[str]:
    if kind == "rule":
        return list(row.triggered_event_ids or [])
    return list(row.event_ids or [])


def finding_events(db: Session, kind: str, row: RuleFinding | MlFinding) -> list[ForensicEvent]:
    uids = finding_event_uids(kind, row)
    if not uids:
        return []
    events = db.scalars(
        select(ForensicEvent).where(ForensicEvent.event_uid.in_(uids))
    ).all()
    order = {uid: index for index, uid in enumerate(uids)}
    return sorted(events, key=lambda e: order.get(e.event_uid, 0))


def review_finding(
    db: Session,
    *,
    case: Case,
    finding_id: str,
    status: FindingStatus,
    note: str | None,
    author: str,
) -> tuple[str, RuleFinding | MlFinding]:
    """Apply an investigator review transition and record it in custody."""
    kind, row = get_finding(db, case, finding_id)
    current = FindingStatus(row.status)
    if status == current:
        raise ApiError(
            409,
            "FINDING_STATUS_UNCHANGED",
            f"Finding {finding_id} is already in status {current.value}.",
        )
    if status not in _ALLOWED_TRANSITIONS[current]:
        raise ApiError(
            409,
            "FINDING_STATUS_TRANSITION",
            f"Cannot move finding {finding_id} from {current.value} to {status.value}.",
        )

    row.status = status.value
    row.updated_at = utcnow()
    custody.record(
        db,
        case=case,
        action=CustodyAction.INVESTIGATOR_REVIEWED,
        actor=author,
        details={
            "finding_id": finding_id,
            "kind": kind,
            "from_status": current.value,
            "to_status": status.value,
            "note": (note or "").strip() or None,
        },
    )
    if note and note.strip():
        db.add(
            InvestigatorNote(
                case_id=case.id,
                finding_uid=finding_id,
                author=author or "investigator",
                body=note.strip(),
            )
        )
    case.last_activity = utcnow()
    db.commit()
    db.refresh(row)
    return kind, row


def finding_notes(db: Session, finding_id: str) -> list[InvestigatorNote]:
    return list(
        db.scalars(
            select(InvestigatorNote)
            .where(InvestigatorNote.finding_uid == finding_id)
            .order_by(InvestigatorNote.created_at.desc(), InvestigatorNote.id.desc())
        )
    )
