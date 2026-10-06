"""Response serializers (Phase 1)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Case,
    ChainOfCustody,
    Evidence,
    MlFinding,
    RuleFinding,
)
from app.schemas import CaseResponse, CustodyEventResponse, EvidenceResponse


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
