"""Investigation assistant endpoints (Phase 5).

Security notes:
* every question is resolved strictly within the URL ``case_id`` — there is no
  global search path and no cross-case retrieval
* question text is bounded by the request schema (ASSISTANT_MAX_QUESTION_LENGTH)
* answers are deterministic, evidence-traceable compositions over persisted
  Phase 0-4 data; no generative model is involved
* history is append-only and case-scoped; query ids are validated against the
  owning case before any data is returned
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import terminology
from app.assistant import service as assistant_service
from app.db import get_db
from app.schemas import AssistantQueryRequest, AssistantQueryResponse
from app.services import case_service

router = APIRouter(tags=["assistant"])


@router.post(
    "/cases/{case_id}/assistant/query",
    response_model=AssistantQueryResponse,
    status_code=201,
    summary="Ask the evidence-traceable investigation assistant",
    description=(
        "Answers a bounded, case-scoped question with a deterministic, "
        "evidence-traceable response composed only from this case's persisted "
        "pipeline output. "
        + terminology.ASSISTANT_FOOTER
    ),
)
def ask_assistant(
    case_id: str,
    payload: AssistantQueryRequest,
    db: Session = Depends(get_db),
):
    case = case_service.get_case(db, case_id)
    return assistant_service.answer_question(
        db, case=case, question=payload.question, actor=payload.actor or "investigator"
    )


@router.get(
    "/cases/{case_id}/assistant/history",
    response_model=list[AssistantQueryResponse],
    summary="Assistant question/answer history for a case",
    description=("Newest-first append-only history of assistant queries for this case."),
)
def assistant_history(
    case_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    case = case_service.get_case(db, case_id)
    rows = assistant_service.history(db, case, limit=limit)
    return [
        assistant_service.serialize(row, case_id=case.case_id, disclaimer=terminology.ASSISTANT_FOOTER)
        for row in rows
    ]


@router.get(
    "/cases/{case_id}/assistant/queries/{query_id}",
    response_model=AssistantQueryResponse,
    summary="A single assistant query detail",
    description=("Returns one assistant query that belongs to the given case."),
)
def assistant_query_detail(
    case_id: str,
    query_id: int,
    db: Session = Depends(get_db),
):
    case = case_service.get_case(db, case_id)
    row = assistant_service.get_query(db, case, query_id)
    return assistant_service.serialize(row, case_id=case.case_id, disclaimer=terminology.ASSISTANT_FOOTER)