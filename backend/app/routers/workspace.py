"""Read-only investigation workspace endpoint (Phase 8).

Serves the per-case analyst workspace snapshot. The response is built only
from rows already persisted by Phases 1–6 and the assistant/report history of
the case; no parsing, analysis, correlation, assistant call, or report
generation happens here and nothing is written to the database.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import terminology
from app.db import get_db
from app.schemas import WorkspaceResponse
from app.services import case_service, workspace_service

router = APIRouter(tags=["workspace"])


@router.get(
    "/cases/{case_id}/workspace",
    response_model=WorkspaceResponse,
    summary="Investigation workspace for one case (read-only)",
    description=(
        "Builds a compact, case-scoped analyst workspace: case identity, "
        "evidence/processing/integrity rollups, findings and the review queue, "
        "the reconstructed timeline, correlations, activity groups, the "
        "evidence graph, assistant history, and report history. Every figure "
        "re-shapes rows already persisted by Phases 1–6; no analysis is "
        "re-run and no data is written. Absent data is reported honestly, "
        "never fabricated.\n\n"
        f"**Scope:** {terminology.WORKSPACE_NOTE}"
    ),
)
def get_workspace(case_id: str, db: Session = Depends(get_db)) -> WorkspaceResponse:
    case = case_service.get_case(db, case_id)
    return workspace_service.build_workspace(db, case)