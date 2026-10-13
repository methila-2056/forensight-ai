"""Case management endpoints (Phase 1, notes in Phase 10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    CaseCreateRequest,
    CaseResponse,
    CaseUpdateRequest,
    CustodyEventResponse,
    NoteCreateRequest,
    NoteListResponse,
    NoteResponse,
)
from app.services import case_service, custody, notes_service, serializers

router = APIRouter(tags=["cases"])


@router.post(
    "/cases",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an investigation case",
)
def create_case(payload: CaseCreateRequest, db: Session = Depends(get_db)) -> CaseResponse:
    case = case_service.create_case(
        db,
        name=payload.name,
        investigator=payload.investigator,
        description=payload.description,
        severity=payload.severity,
    )
    return serializers.case_response(db, case)


@router.get("/cases", response_model=list[CaseResponse], summary="List investigation cases")
def list_cases(db: Session = Depends(get_db)) -> list[CaseResponse]:
    return [serializers.case_response(db, case) for case in case_service.list_cases(db)]


@router.get("/cases/{case_id}", response_model=CaseResponse, summary="Get case details")
def get_case(case_id: str, db: Session = Depends(get_db)) -> CaseResponse:
    case = case_service.get_case(db, case_id)
    return serializers.case_response(db, case)


@router.patch("/cases/{case_id}", response_model=CaseResponse, summary="Update case status/severity")
def update_case(
    case_id: str, payload: CaseUpdateRequest, db: Session = Depends(get_db)
) -> CaseResponse:
    case = case_service.get_case(db, case_id)
    updated = case_service.update_case(
        db, case, status=payload.status, severity=payload.severity
    )
    return serializers.case_response(db, updated)


@router.get(
    "/cases/{case_id}/custody",
    response_model=list[CustodyEventResponse],
    summary="Chain-of-custody history for a case",
)
def case_custody(case_id: str, db: Session = Depends(get_db)) -> list[CustodyEventResponse]:
    case = case_service.get_case(db, case_id)
    return [serializers.custody_response(db, event) for event in custody.events_for_case(db, case)]


# --- Investigator notes (Phase 10) ------------------------------------------
# Notes are append-only by design: there is deliberately no update or delete
# route, so an annotation recorded during an investigation cannot be edited
# away or removed later.


@router.post(
    "/cases/{case_id}/notes",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an investigator note to a case",
)
def add_case_note(
    case_id: str,
    payload: NoteCreateRequest,
    db: Session = Depends(get_db),
) -> NoteResponse:
    case = case_service.get_case(db, case_id)
    note = notes_service.add_note(
        db,
        case=case,
        body=payload.body,
        author=payload.author,
        finding_uid=payload.finding_uid,
    )
    db.commit()
    return serializers.note_response(case, note)


@router.get(
    "/cases/{case_id}/notes",
    response_model=NoteListResponse,
    summary="List investigator notes for a case (newest first)",
)
def list_case_notes(
    case_id: str,
    finding_uid: str | None = Query(default=None, max_length=48),
    limit: int = Query(default=200, ge=1, le=notes_service.MAX_NOTES_PER_LIST),
    db: Session = Depends(get_db),
) -> NoteListResponse:
    case = case_service.get_case(db, case_id)
    notes = notes_service.list_notes(
        db, case=case, finding_uid=finding_uid, limit=limit
    )
    return serializers.note_list_response(case, notes, limit=limit)
