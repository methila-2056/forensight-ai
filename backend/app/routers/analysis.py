"""Automated analysis endpoints (Phase 3).

Security notes:
* analysis only reads normalized forensic events (never raw evidence bytes)
* findings are produced with status ``New``; only investigators move them
  through the review workflow, and every transition is recorded in custody
* responses never expose server filesystem paths
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import config, terminology
from app.db import get_db
from app.models import FindingStatus, RunStatus, SeverityLevel
from app.schemas import (
    AnalysisRunResponse,
    AnalyzeRequest,
    FindingDetailResponse,
    FindingListResponse,
    FindingReviewRequest,
    FindingTraceResponse,
    MlMetricsResponse,
)
from app.services import analysis_service, case_service, serializers
from app.services.analysis_service import finding_events, finding_notes

router = APIRouter(tags=["analysis"])


def _parse_enum(enum_cls, value: Optional[str], *, code: str, label: str):
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        from app.errors import ApiError

        raise ApiError(422, code, f"Unknown {label}: {value!r}.")


@router.post(
    "/cases/{case_id}/analyze",
    response_model=AnalysisRunResponse,
    summary="Run automated analysis (rules + Strategy A anomaly detection + fusion)",
)
def analyze_case(
    case_id: str,
    payload: Optional[AnalyzeRequest] = None,
    db: Session = Depends(get_db),
) -> AnalysisRunResponse:
    case = case_service.get_case(db, case_id)
    request = payload or AnalyzeRequest()
    run = analysis_service.analyze_case(db, case=case, actor=request.actor or "system")
    return serializers.analysis_run_response(db, run)


@router.get(
    "/cases/{case_id}/analysis-runs",
    response_model=list[AnalysisRunResponse],
    summary="Analysis run history of a case (newest first)",
)
def list_analysis_runs(case_id: str, db: Session = Depends(get_db)) -> list[AnalysisRunResponse]:
    case = case_service.get_case(db, case_id)
    return [
        serializers.analysis_run_response(db, run)
        for run in analysis_service.runs_for_case(db, case)
    ]


@router.get(
    "/cases/{case_id}/findings",
    response_model=FindingListResponse,
    summary="Findings of a case (rule + ML, merged, filterable)",
)
def list_findings(
    case_id: str,
    kind: Optional[str] = Query(default=None, pattern="^(rule|ml)$"),
    severity: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    run_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> FindingListResponse:
    case = case_service.get_case(db, case_id)
    severity_enum = _parse_enum(
        SeverityLevel, severity, code="UNKNOWN_SEVERITY", label="severity"
    )
    status_enum = _parse_enum(FindingStatus, status, code="UNKNOWN_STATUS", label="status")
    rows, total = analysis_service.list_findings(
        db,
        case,
        kind=kind,
        severity=severity_enum,
        status=status_enum,
        run_id=run_id,
        limit=limit,
        offset=offset,
    )
    return FindingListResponse(
        findings=[
            serializers.finding_summary_response(db, case, kind_value, row)
            for kind_value, row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/cases/{case_id}/findings/{finding_id}",
    response_model=FindingDetailResponse,
    summary="Full detail of one finding (explanation, features, traceability)",
)
def get_finding(
    case_id: str, finding_id: str, db: Session = Depends(get_db)
) -> FindingDetailResponse:
    case = case_service.get_case(db, case_id)
    kind, row = analysis_service.get_finding(db, case, finding_id)
    events = finding_events(db, kind, row)
    return serializers.finding_detail_response(
        db, case, kind, row, supporting_events=events, notes=finding_notes(db, finding_id)
    )


@router.patch(
    "/cases/{case_id}/findings/{finding_id}",
    response_model=FindingDetailResponse,
    summary="Review a finding (investigator status transition, recorded in custody)",
)
def review_finding(
    case_id: str,
    finding_id: str,
    payload: FindingReviewRequest,
    db: Session = Depends(get_db),
) -> FindingDetailResponse:
    case = case_service.get_case(db, case_id)
    kind, row = analysis_service.review_finding(
        db,
        case=case,
        finding_id=finding_id,
        status=payload.status,
        note=payload.note,
        author=payload.author or "investigator",
    )
    events = finding_events(db, kind, row)
    return serializers.finding_detail_response(
        db, case, kind, row, supporting_events=events, notes=finding_notes(db, finding_id)
    )


@router.get(
    "/cases/{case_id}/findings/{finding_id}/trace",
    response_model=FindingTraceResponse,
    summary="Traceability ladder: Finding → Event → Raw Record → Evidence",
)
def trace_finding(
    case_id: str, finding_id: str, db: Session = Depends(get_db)
) -> FindingTraceResponse:
    case = case_service.get_case(db, case_id)
    kind, row = analysis_service.get_finding(db, case, finding_id)
    events = finding_events(db, kind, row)
    detail = serializers.finding_detail_response(db, case, kind, row, supporting_events=events)
    return FindingTraceResponse(
        finding_id=finding_id,
        case_id=case.case_id,
        kind=kind,  # type: ignore[arg-type]
        events=[
            serializers.event_detail_response(db, event) for event in events
        ],
        evidence=detail.evidence,
    )


@router.get(
    "/cases/{case_id}/ml-metrics",
    response_model=MlMetricsResponse,
    summary="Model diagnostics of the latest analysis run (metrics + config snapshot)",
)
def ml_metrics(case_id: str, db: Session = Depends(get_db)) -> MlMetricsResponse:
    case = case_service.get_case(db, case_id)
    runs = analysis_service.runs_for_case(db, case)
    latest = next((run for run in runs if run.status == RunStatus.COMPLETED), None)
    stats = (latest.stats or {}) if latest else {}
    return MlMetricsResponse(
        case_id=case.case_id,
        run_id=latest.run_uid if latest else None,
        stats=stats,
        config={
            "window_minutes": config.ANALYSIS_WINDOW_MINUTES,
            "threshold": config.ANOMALY_THRESHOLD,
            "z_sigmas": config.ML_Z_SIGMAS,
            "min_windows": config.ML_MIN_WINDOWS,
            "n_estimators": config.ML_N_ESTIMATORS,
            "contamination": config.ML_CONTAMINATION,
            "random_state": config.RANDOM_STATE,
            "max_findings_per_rule": config.RULE_MAX_FINDINGS_PER_RULE,
        },
        scope_note=stats.get("scope_note") or terminology.ANALYSIS_SCOPE_NOTE,
    )
