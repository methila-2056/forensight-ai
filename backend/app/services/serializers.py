"""Response serializers (Phase 1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Case,
    ChainOfCustody,
    Evidence,
    FindingStatus,
    ForensicEvent,
    InvestigationRun,
    MlFinding,
    ProcessingRun,
    RuleFinding,
    SeverityLevel,
)
from app.schemas import (
    AnalysisRunResponse,
    CaseResponse,
    CustodyEventResponse,
    EventDetailResponse,
    EventEvidenceRef,
    EventResponse,
    EvidenceResponse,
    FindingDetailResponse,
    FindingEvidenceResponse,
    FindingNoteResponse,
    FindingSummary,
    ProcessingRunResponse,
    RawRecordResponse,
)


def case_response(db: Session, case: Case) -> CaseResponse:
    evidence_count = (
        db.scalar(select(func.count()).select_from(Evidence).where(Evidence.case_id == case.id)) or 0
    )
    rule_count = (
        db.scalar(
            select(func.count()).select_from(RuleFinding).where(RuleFinding.case_id == case.id)
        )
        or 0
    )
    ml_count = (
        db.scalar(select(func.count()).select_from(MlFinding).where(MlFinding.case_id == case.id))
        or 0
    )
    return CaseResponse(
        case_id=case.case_id,
        name=case.name,
        investigator=case.investigator,
        description=case.description,
        status=case.status,
        severity=case.severity,
        created_at=case.created_at,
        last_activity=case.last_activity,
        demo=case.demo,
        evidence_count=evidence_count,
        finding_count=rule_count + ml_count,
    )


def evidence_response(evidence: Evidence, case: Case) -> EvidenceResponse:
    return EvidenceResponse(
        evidence_id=evidence.evidence_id,
        case_id=case.case_id,
        original_filename=evidence.original_filename,
        evidence_type=evidence.evidence_type,
        source_description=evidence.source_description,
        file_size=evidence.file_size,
        mime_type=evidence.mime_type,
        sha256=evidence.sha256,
        uploaded_at=evidence.uploaded_at,
        status=evidence.status,
        record_count=evidence.record_count,
        parse_ok=evidence.parse_ok,
        parse_rejected=evidence.parse_rejected,
    )


def custody_response(db: Session, event: ChainOfCustody) -> CustodyEventResponse:
    case = db.get(Case, event.case_id)
    evidence = db.get(Evidence, event.evidence_id) if event.evidence_id else None
    return CustodyEventResponse(
        id=event.id,
        case_id=case.case_id if case else "",
        evidence_id=evidence.evidence_id if evidence else None,
        timestamp=event.timestamp,
        action=event.action,
        actor=event.actor,
        details=event.details,
    )


def processing_run_response(db: Session, run: ProcessingRun) -> ProcessingRunResponse:
    case = db.get(Case, run.case_id)
    evidence = db.get(Evidence, run.evidence_id)
    return ProcessingRunResponse(
        run_id=run.run_uid,
        case_id=case.case_id if case else "",
        evidence_id=evidence.evidence_id if evidence else "",
        evidence_filename=evidence.original_filename if evidence else "",
        parser=run.parser,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        records_received=run.records_received,
        records_parsed=run.records_parsed,
        records_normalized=run.records_normalized,
        records_rejected=run.records_rejected,
        duplicates_detected=run.duplicates_detected,
        warnings=run.warnings or [],
        error_code=run.error_code,
        error=run.error,
    )


def event_response(db: Session, event: ForensicEvent) -> EventResponse:
    case = db.get(Case, event.case_id)
    evidence = event.evidence or db.get(Evidence, event.evidence_id)
    raw_record = event.raw_record
    duplicate = (event.extra or {}).get("duplicate") or {}
    return EventResponse(
        event_id=event.event_uid,
        case_id=case.case_id if case else "",
        evidence_id=evidence.evidence_id if evidence else "",
        timestamp=event.timestamp,
        tz_note=event.tz_note,
        source_type=event.source_type,
        event_type=event.event_type,
        user=event.user,
        host=event.host,
        source_ip=event.source_ip,
        destination_ip=event.destination_ip,
        process=event.process,
        file_path=event.file_path,
        action=event.action,
        severity=event.severity,
        anomaly_score=event.anomaly_score,
        is_anomalous=bool(event.is_anomalous),
        raw_record_reference=raw_record.row_index if raw_record else None,
        duplicate=bool(duplicate),
        duplicate_of=duplicate.get("of"),
        metadata=event.extra or None,
    )


def event_detail_response(db: Session, event: ForensicEvent) -> EventDetailResponse:
    base = event_response(db, event)
    evidence = event.evidence or db.get(Evidence, event.evidence_id)
    raw_record = event.raw_record
    return EventDetailResponse(
        **base.model_dump(),
        raw_record=RawRecordResponse(
            row_index=raw_record.row_index,
            content=raw_record.content,
            reject_reason=raw_record.reject_reason,
        )
        if raw_record
        else None,
        evidence=EventEvidenceRef(
            evidence_id=evidence.evidence_id,
            original_filename=evidence.original_filename,
            sha256=evidence.sha256,
            uploaded_at=evidence.uploaded_at,
        )
        if evidence
        else None,
    )


def analysis_run_response(db: Session, run: InvestigationRun) -> AnalysisRunResponse:
    case = db.get(Case, run.case_id)
    return AnalysisRunResponse(
        run_id=run.run_uid,
        case_id=case.case_id if case else "",
        stage=run.stage,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        stats=run.stats,
        error=run.error,
    )


def _run_uid_for(db: Session, run_pk: int | None) -> str | None:
    if run_pk is None:
        return None
    run = db.get(InvestigationRun, run_pk)
    return run.run_uid if run else None


def finding_summary_response(
    db: Session, case: Case, kind: str, row: RuleFinding | MlFinding
) -> FindingSummary:
    if kind == "rule":
        event_ids = list(row.triggered_event_ids or [])
        return FindingSummary(
            finding_id=row.finding_uid,
            case_id=case.case_id,
            kind="rule",
            run_id=_run_uid_for(db, row.run_id),
            rule_id=row.rule_id,
            model_name=None,
            title=row.title,
            severity=SeverityLevel(row.severity),
            status=FindingStatus(row.status),
            confidence=row.confidence,
            anomaly_score=None,
            threshold=None,
            composite_suspicion_score=row.composite_suspicion_score,
            event_count=len(event_ids),
            evidence_count=len(row.evidence_ids or []),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
    return FindingSummary(
        finding_id=row.finding_uid,
        case_id=case.case_id,
        kind="ml",
        run_id=_run_uid_for(db, row.run_id),
        rule_id=None,
        model_name=row.model_name,
        title=row.title or f"ML finding {row.finding_uid}",
        severity=SeverityLevel(row.severity),
        status=FindingStatus(row.status),
        confidence=None,
        anomaly_score=row.score,
        threshold=row.threshold,
        composite_suspicion_score=row.composite_suspicion_score,
        event_count=len(row.event_ids or []),
        evidence_count=len(row.evidence_ids or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _iso_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def finding_detail_response(
    db: Session,
    case: Case,
    kind: str,
    row: RuleFinding | MlFinding,
    *,
    supporting_events: list[ForensicEvent],
    notes: list[Any] | None = None,
) -> FindingDetailResponse:
    if kind == "rule":
        event_ids = list(row.triggered_event_ids or [])
        evidence_ids = list(row.evidence_ids or [])
        anomaly_scores = [
            event.anomaly_score for event in supporting_events if event.anomaly_score is not None
        ]
        anomaly = round(sum(anomaly_scores) / len(anomaly_scores), 6) if anomaly_scores else None
        start, end = row.timestamp_start, row.timestamp_end
        explanation: Any = row.explanation
        reasons: Any = row.reasons
        feature_snapshot = None
        feature_version = None
        model_name = model_version = None
        rule_id = row.rule_id
        confidence: float | None = row.confidence
        score: float | None = None
        threshold: float | None = None
    else:
        event_ids = list(row.event_ids or [])
        evidence_ids = list(row.evidence_ids or [])
        anomaly = row.score
        feature_snapshot = row.feature_snapshot
        feature_version = (feature_snapshot or {}).get("feature_version")
        start = _iso_datetime((feature_snapshot or {}).get("window_start"))
        end = _iso_datetime((feature_snapshot or {}).get("window_end"))
        explanation = row.explanation
        reasons = None
        model_name = row.model_name
        model_version = row.model_version
        rule_id = None
        confidence = None
        score = row.score
        threshold = row.threshold

    evidence_rows = []
    if evidence_ids:
        evidence_rows = list(
            db.scalars(select(Evidence).where(Evidence.evidence_id.in_(evidence_ids)))
        )

    return FindingDetailResponse(
        finding_id=row.finding_uid,
        case_id=case.case_id,
        kind=kind,  # type: ignore[arg-type]
        run_id=_run_uid_for(db, row.run_id),
        rule_id=rule_id,
        model_name=model_name,
        model_version=model_version if kind == "ml" else None,
        feature_version=feature_version,
        title=row.title,
        severity=SeverityLevel(row.severity),
        status=FindingStatus(row.status),
        confidence=confidence,
        anomaly_score=anomaly,
        threshold=threshold,
        composite_suspicion_score=row.composite_suspicion_score,
        components=row.components,
        feature_snapshot=feature_snapshot,
        explanation=explanation,
        reasons=reasons,
        timestamp_start=start,
        timestamp_end=end,
        event_ids=event_ids,
        evidence_ids=evidence_ids,
        supporting_events=[event_response(db, event) for event in supporting_events],
        evidence=[
            FindingEvidenceResponse(
                evidence_id=item.evidence_id,
                original_filename=item.original_filename,
                evidence_type=item.evidence_type,
                file_size=item.file_size,
                sha256=item.sha256,
                uploaded_at=item.uploaded_at,
            )
            for item in sorted(evidence_rows, key=lambda item: item.evidence_id)
        ],
        notes=[
            FindingNoteResponse(
                author=note.author, body=note.body, created_at=note.created_at
            )
            for note in (notes or [])
        ],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
