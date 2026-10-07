"""Correlation, activity-group, timeline, and graph endpoints (Phase 4).

Security notes:
* correlation only reads normalized forensic events (never raw evidence bytes)
* every response carries the correlation disclaimer — temporal association is
  never presented as causation
* responses never expose server filesystem paths
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CorrelationType, GroupKind
from app.schemas import (
    CorrelationDetailResponse,
    CorrelationListResponse,
    CorrelationRunResponse,
    CorrelateRequest,
    GraphResponse,
    GroupDetailResponse,
    GroupListResponse,
    TimelineResponse,
)
from app.services import case_service, correlate_service

router = APIRouter(tags=["correlation"])


def _parse_enum(enum_cls, value: Optional[str], *, code: str, label: str):
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        from app.errors import ApiError

        raise ApiError(422, code, f"Unknown {label}: {value!r}.")


@router.post(
    "/cases/{case_id}/correlate",
    response_model=CorrelationRunResponse,
    summary="Run cross-source correlation (reason-tagged links + activity groups)",
)
def correlate_case(
    case_id: str,
    payload: Optional[CorrelateRequest] = None,
    db: Session = Depends(get_db),
) -> CorrelationRunResponse:
    case = case_service.get_case(db, case_id)
    request = payload or CorrelateRequest()
    run = correlate_service.correlate_case(db, case=case, actor=request.actor or "system")
    return correlate_service.correlation_run_response(case, run)


@router.get(
    "/cases/{case_id}/correlation-runs",
    response_model=list[CorrelationRunResponse],
    summary="Correlation run history of a case (newest first)",
)
def list_correlation_runs(case_id: str, db: Session = Depends(get_db)) -> list[CorrelationRunResponse]:
    case = case_service.get_case(db, case_id)
    return [
        correlate_service.correlation_run_response(case, run)
        for run in correlate_service.runs_for_case(db, case)
    ]


@router.get(
    "/cases/{case_id}/correlations",
    response_model=CorrelationListResponse,
    summary="Reason-tagged correlations of a case (latest run by default)",
)
def list_correlations(
    case_id: str,
    type: Optional[str] = Query(default=None, alias="type"),
    run_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CorrelationListResponse:
    case = case_service.get_case(db, case_id)
    corr_type = _parse_enum(
        CorrelationType,
        type,
        code="UNKNOWN_CORRELATION_TYPE",
        label="correlation type",
    )
    rows, total, run = correlate_service.list_correlations(
        db, case, run_id=run_id, corr_type=corr_type, limit=limit, offset=offset
    )
    return correlate_service.correlation_list_response(
        db, case, rows=rows, total=total, limit=limit, offset=offset, run=run
    )


@router.get(
    "/correlations/{correlation_id}",
    response_model=CorrelationDetailResponse,
    summary="One correlation with both events and their traceability details",
)
def get_correlation(correlation_id: str, db: Session = Depends(get_db)) -> CorrelationDetailResponse:
    case, row = correlate_service.get_correlation_any(db, correlation_id)
    return correlate_service.correlation_detail(db, case, row)


@router.get(
    "/cases/{case_id}/groups",
    response_model=GroupListResponse,
    summary="Activity groups deduplicated from the correlations",
)
def list_groups(
    case_id: str,
    kind: Optional[str] = Query(default=None),
    run_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> GroupListResponse:
    case = case_service.get_case(db, case_id)
    group_kind = _parse_enum(GroupKind, kind, code="UNKNOWN_GROUP_KIND", label="group kind")
    rows, total, _run = correlate_service.list_groups(
        db, case, run_id=run_id, kind=group_kind, limit=limit, offset=offset
    )
    return correlate_service.group_list_response(
        db, case, rows=rows, total=total, limit=limit, offset=offset
    )


@router.get(
    "/groups/{group_id}",
    response_model=GroupDetailResponse,
    summary="One activity group with its member events",
)
def get_group(group_id: str, db: Session = Depends(get_db)) -> GroupDetailResponse:
    case, row = correlate_service.get_group_any(db, group_id)
    return correlate_service.group_detail(db, case, row)


@router.get(
    "/cases/{case_id}/timeline",
    response_model=TimelineResponse,
    summary="Reconstructed Investigation Timeline (significance from findings)",
)
def timeline(
    case_id: str,
    run_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> TimelineResponse:
    case = case_service.get_case(db, case_id)
    return correlate_service.timeline(db, case, run_id=run_id)


@router.get(
    "/cases/{case_id}/graph",
    response_model=GraphResponse,
    summary="Evidence graph (capped nodes/edges with a table fallback)",
)
def graph(
    case_id: str,
    run_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> GraphResponse:
    case = case_service.get_case(db, case_id)
    return correlate_service.graph(db, case, run_id=run_id)
