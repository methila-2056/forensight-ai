"""Read-only dashboard endpoint (Phase 7).

Serves a cross-case scenario-statistics snapshot. The response is built only
from rows already persisted by Phases 1–6; no analysis, inference, or writes
happen here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import DashboardResponse
from app.services import dashboard_service

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Cross-case scenario statistics (read-only dashboard)",
    description=(
        "Aggregates persisted investigation data into a dashboard snapshot: "
        "global totals, finding/processing/run breakdowns, ML run statistics, "
        "integrity outcomes, custody activity, and a per-case KPI table. "
        "Every figure counts rows already stored by Phases 1–6; no new "
        "analysis is performed and no figure is fabricated."
    ),
)
def get_dashboard(db: Session = Depends(get_db)) -> DashboardResponse:
    return dashboard_service.build_dashboard(db)