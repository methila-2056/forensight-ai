"""Segment classifier endpoints (Phase 9b).

Deliberately separate from the analysis router: Strategy A anomaly metrics
(`/ml-metrics`) and the supervised segment classifier (`/classifier/*`) answer
different questions and are never presented as the same number.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import ClassifierMetricsResponse, ClassifierResultsResponse
from app.services import case_service, classifier_service

router = APIRouter(tags=["classifier"])


@router.get(
    "/classifier/metrics",
    response_model=ClassifierMetricsResponse,
    summary=(
        "Segment classifier metrics. Synthetic-data figures only; abstains "
        "explicitly when the labelled set is too small or too imbalanced."
    ),
)
def classifier_metrics(db: Session = Depends(get_db)) -> ClassifierMetricsResponse:
    payload = classifier_service.metrics_payload(db)
    return ClassifierMetricsResponse.model_validate(payload)


@router.post(
    "/classifier/train",
    response_model=ClassifierMetricsResponse,
    summary=(
        "Train and evaluate the segment classifier on the shipped synthetic "
        "incident corpora, then persist metrics and per-window predictions."
    ),
)
def train_classifier(db: Session = Depends(get_db)) -> ClassifierMetricsResponse:
    classifier_service.train_and_store(db)
    payload = classifier_service.metrics_payload(db)
    return ClassifierMetricsResponse.model_validate(payload)


@router.get(
    "/cases/{case_id}/classifier-results",
    response_model=ClassifierResultsResponse,
    summary="Stored per-window segment classifications for a case",
)
def case_classifier_results(
    case_id: str,
    limit: int = Query(default=100, ge=1, le=classifier_service.MAX_RESULTS),
    db: Session = Depends(get_db),
) -> ClassifierResultsResponse:
    # Resolve the case first so a foreign case 404s rather than leaking rows.
    case = case_service.get_case(db, case_id)
    return ClassifierResultsResponse(
        case_id=case.case_id,
        results=classifier_service.classifier_results(db, case.case_id, limit=limit),
        total=len(classifier_service.classifier_results(db, case.case_id, limit=limit)),
        limit=limit,
    )