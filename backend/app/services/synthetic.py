"""Canonical synthetic / demonstration data detection (single source of truth).

The report, workspace, and dashboard presentation layers all derive their
synthetic label from this module, so the three read-only surfaces can never
drift apart.

Signals — the exact canonical ``terminology.DEMO_LABEL`` substring only.
Never loose keywords such as "demo" or "synthetic", and never file names:

1. the ``Case.demo`` flag (set directly in the database; never via the API)
2. the marker inside ``Case.description``
3. the marker inside ``Evidence.source_description``
4. the marker inside ``RawRecord.content`` (ingested evidence rows)

Case-sensitivity follows production PostgreSQL semantics. Signals 2 and 3
are matched with Python's case-sensitive substring operator, which behaves
identically on SQLite (whose ``LIKE`` is case-insensitive for ASCII) and on
production PostgreSQL (whose ``LIKE`` is case-sensitive) — so these signals
can never be tested on SQLite yet ship with different behaviour on Postgres.
Signal 4 keeps the historical SQL ``LIKE`` implementation, which production
PostgreSQL also evaluates case-sensitively; its tests therefore assert the
exact-case marker only. A marker inside a file name alone never labels a
case (``/`` is not legal in file names, so the canonical marker cannot
appear there anyway).
"""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app import terminology
from app.models import Case, Evidence, RawRecord


def _carries_marker(value: str | None) -> bool:
    return bool(value) and terminology.DEMO_LABEL in value


def _raw_content_marker(db: Session, case_id: int) -> bool:
    """True when any ingested row of the case carries the canonical marker."""
    return bool(
        db.scalar(
            select(
                exists().where(
                    RawRecord.content.like(f"%{terminology.DEMO_LABEL}%"),
                    RawRecord.evidence_id.in_(
                        select(Evidence.id).where(Evidence.case_id == case_id)
                    ),
                )
            )
        )
    )


def _source_description_marker(db: Session, case_id: int) -> bool:
    """True when any evidence source description of the case carries the marker."""
    rows = db.scalars(
        select(Evidence.source_description).where(Evidence.case_id == case_id)
    )
    return any(_carries_marker(value) for value in rows)


def case_is_synthetic(db: Session, case: Case) -> bool:
    """True when the case carries any canonical demonstration signal."""
    if case.demo:
        return True
    if _carries_marker(case.description):
        return True
    if _raw_content_marker(db, case.id):
        return True
    return _source_description_marker(db, case.id)


def synthetic_case_ids(db: Session) -> set[int]:
    """Case primary keys carrying any signal, ``demo`` flag included.

    Bulk equivalent of :func:`case_is_synthetic` for the dashboard KPI loop:
    each signal is fetched once for the whole table instead of per case.
    """
    case_ids = set(db.scalars(select(Case.id).where(Case.demo.is_(True))))
    for case_id, description in db.execute(select(Case.id, Case.description)):
        if _carries_marker(description):
            case_ids.add(case_id)
    evidence_map: dict[int, int] = {}
    for evidence_id, case_id, source in db.execute(
        select(Evidence.id, Evidence.case_id, Evidence.source_description)
    ):
        evidence_map[evidence_id] = case_id
        if _carries_marker(source):
            case_ids.add(case_id)
    marker_rows = db.execute(
        select(RawRecord.evidence_id).where(
            RawRecord.content.like(f"%{terminology.DEMO_LABEL}%")
        )
    ).all()
    case_ids.update(
        evidence_map[ev_id] for ev_id, in marker_rows if ev_id in evidence_map
    )
    return case_ids
