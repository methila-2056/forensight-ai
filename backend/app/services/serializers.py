"""Response serializers (Phase 1)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Case,
    ChainOfCustody,
    Evidence,
    ForensicEvent,
    MlFinding,
    ProcessingRun,
    RuleFinding,
)
from app.schemas import (
    CaseResponse,
    CustodyEventResponse,
    EventDetailResponse,
    EventEvidenceRef,
    EventResponse,
    EvidenceResponse,
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
