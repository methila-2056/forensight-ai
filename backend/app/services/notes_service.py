"""Investigator notes (Phase 10).

Annotations an investigator writes by hand alongside the automated analysis.
Notes are **append-only**: there is no update and no delete path, so a note
recorded during an investigation cannot later be edited away or removed. That
matches the rest of the evidence model, where custody events, findings, and
reports are all recorded rather than revised.

A note may optionally be attached to a finding (``finding_uid``). Notes are
always case-scoped: a note written against another case is not readable through
this service, and the router resolves the case first so a foreign case yields
``404 CASE_NOT_FOUND`` rather than a note leak.

Notes record analyst judgement only. Nothing here is an automated conclusion,
and the wording of a note is never interpreted as a system finding.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Case, InvestigatorNote, MlFinding, RuleFinding, utcnow

# Bound so a single annotation cannot bloat the database. Mirrors the
# review-note limit already applied elsewhere.
MAX_BODY_CHARS = 4000
MAX_AUTHOR_CHARS = 127
MAX_NOTES_PER_LIST = 500


def add_note(
    db: Session,
    *,
    case: Case,
    body: str,
    author: str = "investigator",
    finding_uid: str | None = None,
) -> InvestigatorNote:
    """Append one note to a case. Raises 422 on an empty or oversized body."""
    text = (body or "").strip()
    if not text:
        raise ApiError(
            422, "VALIDATION_ERROR", "Note body must not be empty."
        )
    if len(text) > MAX_BODY_CHARS:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            f"Note body exceeds the {MAX_BODY_CHARS} character limit.",
            detail={"max_length": MAX_BODY_CHARS, "length": len(text)},
        )

    who = (author or "investigator").strip()[:MAX_AUTHOR_CHARS] or "investigator"

    # A note pinned to a finding must reference one that exists in this case,
    # so notes cannot point across the case boundary.
    if finding_uid:
        _assert_finding_in_case(db, case=case, finding_uid=finding_uid)

    note = InvestigatorNote(
        case_id=case.id,
        finding_uid=finding_uid or None,
        author=who,
        body=text,
    )
    db.add(note)
    db.flush()

    # Notes are investigator activity, so they advance the case clock the same
    # way other case-level actions do.
    case.last_activity = utcnow()
    return note


def _finding_model(finding_uid: str):
    """Rule and ML findings live in separate tables with distinct UID prefixes."""
    if finding_uid.startswith("RFND-"):
        return RuleFinding
    if finding_uid.startswith("MFND-"):
        return MlFinding
    return None


def _assert_finding_in_case(
    db: Session,
    *,
    case: Case,
    finding_uid: str,
) -> None:
    """Reject a note pinned to a finding that is not part of this case."""
    model = _finding_model(finding_uid)
    if model is None:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "finding_uid must be a RFND- or MFND- finding identifier.",
            detail={"finding_uid": finding_uid},
        )

    found = db.scalar(
        select(model.id)
        .where(model.finding_uid == finding_uid)
        .where(model.case_id == case.id)
    )
    if not found:
        raise ApiError(
            404,
            "FINDING_NOT_FOUND",
            f"Finding {finding_uid} does not exist in this case.",
            detail={"finding_uid": finding_uid},
        )


def list_notes(
    db: Session,
    *,
    case: Case,
    finding_uid: str | None = None,
    limit: int = 200,
) -> list[InvestigatorNote]:
    """Notes for a case, newest first. Optionally scoped to one finding."""
    bounded = max(1, min(int(limit or 200), MAX_NOTES_PER_LIST))
    statement = select(InvestigatorNote).where(InvestigatorNote.case_id == case.id)
    if finding_uid:
        statement = statement.where(InvestigatorNote.finding_uid == finding_uid)
    statement = statement.order_by(
        InvestigatorNote.created_at.desc(), InvestigatorNote.id.desc()
    ).limit(bounded)
    return list(db.scalars(statement))


def notes_for_finding(db: Session, finding_uid: str) -> list[InvestigatorNote]:
    """Notes pinned to a single finding (used by the finding detail view)."""
    return list(
        db.scalars(
            select(InvestigatorNote)
            .where(InvestigatorNote.finding_uid == finding_uid)
            .order_by(InvestigatorNote.created_at.desc(), InvestigatorNote.id.desc())
        )
    )


def note_count(db: Session, case: Case) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(InvestigatorNote)
            .where(InvestigatorNote.case_id == case.id)
        )
        or 0
    )


__all__ = [
    "add_note",
    "list_notes",
    "notes_for_finding",
    "note_count",
    "MAX_BODY_CHARS",
]