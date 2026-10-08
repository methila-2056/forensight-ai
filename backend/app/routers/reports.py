"""Investigation report endpoints (Phase 6).

Reports are immutable, case-scoped snapshots of data already persisted by
Phases 1–5. Generation performs no new analysis; every lookup is scoped by
case so reports cannot leak across cases.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import ReportGenerateRequest, ReportResponse, ReportSummary
from app.services import case_service, report_service

router = APIRouter(tags=["reports"])


@router.post(
    "/cases/{case_id}/reports",
    response_model=ReportResponse,
    status_code=201,
    summary="Generate one immutable forensic report snapshot",
    description=(
        "Builds a deterministic, evidence-backed report from the case's "
        "already-persisted Phase 1–5 data. Each call appends a new snapshot; "
        "existing reports are never modified."
    ),
)
def create_report(
    case_id: str,
    payload: Optional[ReportGenerateRequest] = None,
    db: Session = Depends(get_db),
) -> ReportResponse:
    case = case_service.get_case(db, case_id)
    request = payload or ReportGenerateRequest()
    report = report_service.generate_report(
        db, case=case, title=request.title, actor=request.actor or "investigator"
    )
    return report_service.serialize_report(report)


@router.get(
    "/cases/{case_id}/reports",
    response_model=list[ReportSummary],
    summary="Report history of a case (newest first)",
)
def list_reports(case_id: str, db: Session = Depends(get_db)) -> list[ReportSummary]:
    case = case_service.get_case(db, case_id)
    return [report_service.report_summary(row) for row in report_service.list_reports(db, case)]


@router.get(
    "/cases/{case_id}/reports/{report_id}",
    response_model=ReportResponse,
    summary="Full content of one report snapshot (identity + sections)",
)
def get_report(
    case_id: str, report_id: str, db: Session = Depends(get_db)
) -> ReportResponse:
    case = case_service.get_case(db, case_id)
    return report_service.serialize_report(report_service.get_report(db, case, report_id))


@router.get(
    "/cases/{case_id}/reports/{report_id}/json",
    response_model=dict[str, Any],
    summary="Raw stored payload of one report snapshot",
    description=(
        "Returns the stored JSON exactly as persisted: "
        '{"metadata": {...}, "sections": {...}}.'
    ),
)
def get_report_json(
    case_id: str, report_id: str, db: Session = Depends(get_db)
) -> dict[str, Any]:
    case = case_service.get_case(db, case_id)
    return report_service.raw_json(report_service.get_report(db, case, report_id))