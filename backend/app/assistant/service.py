"""Assistant orchestration and history persistence (Phase 5).

Flow for every question:
1. normalize + cap the question length,
2. classify into the controlled intent catalog (deterministic),
3. build a case-scoped context (any invalid reference raises the standard
   structured 404),
4. compose the deterministic answer and a confidence level,
5. persist an append-only ``assistant_queries`` row (never rewritten),
6. return the response with the standing disclaimer.

Nothing here invokes a model, external service, or free-form generation.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, terminology
from app.assistant import retrieval
from app.assistant.answerer import answer
from app.assistant.context import AssistantContext, build_context
from app.assistant.intents import Intent, classify
from app.errors import ApiError
from app.models import AssistantQuery, Case


def answer_question(
    db: Session, *, case: Case, question: str, actor: str = "assistant"
) -> dict:
    question = (question or "").strip()
    if not question:
        raise ApiError(422, "EMPTY_QUESTION", "The question must not be empty.")
    if len(question) > config.ASSISTANT_MAX_QUESTION_LENGTH:
        raise ApiError(
            422,
            "QUESTION_TOO_LONG",
            f"Question must be at most {config.ASSISTANT_MAX_QUESTION_LENGTH} characters.",
        )

    classified = classify(question)
    intent = classified.intent

    if intent == Intent.CAPABILITIES:
        ctx = AssistantContext(case=case, classified=classified)
        ctx.meta = retrieval.case_meta(db, case)
        ctx.run_caps = retrieval.run_caps()
        parts = answer(ctx)
        row = _persist(db, case=case, question=question, classified=classified, parts=parts)
        return serialize(row, case_id=case.case_id, disclaimer=terminology.ASSISTANT_FOOTER)

    empty_case = not retrieval.case_has_evidence(db, case)
    ctx = build_context(db, case, classified)
    parts = answer(ctx, empty_case=empty_case)
    row = _persist(db, case=case, question=question, classified=classified, parts=parts)
    return serialize(row, case_id=case.case_id, disclaimer=terminology.ASSISTANT_FOOTER)


def _persist(db: Session, *, case: Case, question: str, classified, parts) -> AssistantQuery:
    row = AssistantQuery(
        case_id=case.id,
        question=question,
        intent=classified.intent.value,
        answer=parts.answer,
        evidence=list(parts.evidence or []),
        basis=list(parts.basis or []),
        confidence=parts.confidence,
        sources=list(parts.sources or []),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def serialize(row: AssistantQuery, *, case_id: str = "", disclaimer: str = "") -> dict:
    return {
        "query_id": row.id,
        "case_id": case_id,
        "question": row.question,
        "intent": row.intent,
        "answer": row.answer,
        "evidence": list(row.evidence or []),
        "basis": list(row.basis or []),
        "confidence": row.confidence,
        "sources": list(row.sources or []),
        "disclaimer": disclaimer,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def get_query(db: Session, case: Case, query_id: int) -> AssistantQuery:
    row = db.scalar(
        select(AssistantQuery).where(
            AssistantQuery.id == query_id, AssistantQuery.case_id == case.id
        )
    )
    if row is None:
        raise ApiError(
            404, "ASSISTANT_QUERY_NOT_FOUND", f"Assistant query {query_id} was not found."
        )
    return row


def history(db: Session, case: Case, *, limit: int = 100) -> list[AssistantQuery]:
    bounded = max(1, min(int(limit), 500))
    rows = db.scalars(
        select(AssistantQuery)
        .where(AssistantQuery.case_id == case.id)
        .order_by(AssistantQuery.id.desc())
        .limit(bounded)
    )
    return list(rows)