"""Case management service (Phase 1)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import (
    Case,
    CaseStatus,
    Evidence,
    MlFinding,
    RuleFinding,
    SeverityLevel,
    utcnow,
)


def _utc_year() -> int:
    return datetime.now(timezone.utc).year


def _next_case_id(db: Session, year: int) -> str:
    prefix = f"CASE-{year}-"
    sequence = (
        db.scalar(select(func.count()).select_from(Case).where(Case.case_id.like(f"{prefix}%"))) or 0
    ) + 1
    candidate = f"{prefix}{sequence:03d}"
    while db.scalar(select(Case.id).where(Case.case_id == candidate)) is not None:
        sequence += 1
        candidate = f"{prefix}{sequence:03d}"
    return candidate


def create_case(
    db: Session,
    *,
    name: str,
    investigator: str,
    description: str = "",
    severity: SeverityLevel = SeverityLevel.MEDIUM,
) -> Case:
    clean_name = name.strip()
    clean_investigator = investigator.strip()
    if not clean_name:
        raise ApiError(400, "NAME_REQUIRED", "Case name must not be blank.")
    if not clean_investigator:
        raise ApiError(400, "INVESTIGATOR_REQUIRED", "Investigator name must not be blank.")
    case = Case(
        case_id=_next_case_id(db, _utc_year()),
        name=clean_name,
        investigator=clean_investigator,
        description=description.strip(),
        status=CaseStatus.ACTIVE,
        severity=severity,
        created_at=utcnow(),
        last_activity=utcnow(),
        demo=False,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def list_cases(db: Session) -> list[Case]:
    return list(db.scalars(select(Case).order_by(Case.created_at.desc(), Case.id.desc())))


def get_case(db: Session, case_id: str) -> Case:
    case = db.scalar(select(Case).where(Case.case_id == case_id))
    if case is None:
        raise ApiError(404, "CASE_NOT_FOUND", f"Case {case_id} was not found.")
    return case


def update_case(
    db: Session,
    case: Case,
    *,
    status: CaseStatus | None = None,
    severity: SeverityLevel | None = None,
) -> Case:
    if status is None and severity is None:
        raise ApiError(400, "EMPTY_UPDATE", "Provide a status or a severity to update.")
    if status is not None:
        case.status = status
    if severity is not None:
        case.severity = severity
    case.last_activity = utcnow()
    db.commit()
    db.refresh(case)
    return case


def evidence_count(db: Session, case: Case) -> int:
    return (
        db.scalar(select(func.count()).select_from(Evidence).where(Evidence.case_id == case.id)) or 0
    )


def finding_count(db: Session, case: Case) -> int:
    rules = (
        db.scalar(select(func.count()).select_from(RuleFinding).where(RuleFinding.case_id == case.id))
        or 0
    )
    ml = (
        db.scalar(select(func.count()).select_from(MlFinding).where(MlFinding.case_id == case.id))
        or 0
    )
    return rules + ml


def touch(db: Session, case: Case) -> None:
    case.last_activity = utcnow()
    db.commit()
