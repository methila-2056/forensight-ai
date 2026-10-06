"""Chain-of-custody recorder (Phase 1).

Appends an auditable event for every important evidence lifecycle operation.
The log documents handling activity only — it makes no legal claim.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, ChainOfCustody, CustodyAction, Evidence


def record(
    db: Session,
    *,
    case: Case,
    action: CustodyAction,
    actor: str = "system",
    evidence: Optional[Evidence] = None,
    details: Optional[dict[str, Any]] = None,
) -> ChainOfCustody:
    event = ChainOfCustody(
        case_id=case.id,
        evidence_id=evidence.id if evidence else None,
        action=action,
        actor=actor or "system",
        details=details,
    )
    db.add(event)
    db.flush()
    return event


def events_for_case(db: Session, case: Case) -> list[ChainOfCustody]:
    return list(
        db.scalars(
            select(ChainOfCustody)
            .where(ChainOfCustody.case_id == case.id)
            .order_by(ChainOfCustody.timestamp.desc(), ChainOfCustody.id.desc())
        )
    )


def events_for_evidence(db: Session, evidence: Evidence) -> list[ChainOfCustody]:
    return list(
        db.scalars(
            select(ChainOfCustody)
            .where(ChainOfCustody.evidence_id == evidence.id)
            .order_by(ChainOfCustody.timestamp.desc(), ChainOfCustody.id.desc())
        )
    )
