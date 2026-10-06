"""Case management endpoints (Phase 1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import CaseCreateRequest, CaseResponse, CaseUpdateRequest, CustodyEventResponse
from app.services import case_service, custody, serializers

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
