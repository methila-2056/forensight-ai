"""Normalized forensic event query endpoints (Phase 2).

Every event is traceable back to its raw record (original row) and its
evidence item (SHA-256 recorded at ingest).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.errors import ApiError
from app.models import ForensicEvent, SeverityLevel, SourceType
from app.schemas import EventDetailResponse, EventListResponse
from app.services import case_service, evidence_service, serializers

router = APIRouter(tags=["events"])


@router.get(
    "/cases/{case_id}/events",
    response_model=EventListResponse,
    summary="List normalized events with filters",
)
def list_events(
    case_id: str,
    source_type: Optional[SourceType] = Query(None),
    event_type: Optional[str] = Query(None, description="Exact event type, e.g. login"),
    severity: Optional[SeverityLevel] = Query(None),
    user: Optional[str] = Query(None, description="Case-insensitive contains match"),
    host: Optional[str] = Query(None, description="Case-insensitive contains match"),
    timestamp_from: Optional[datetime] = Query(None),
    timestamp_to: Optional[datetime] = Query(None),
    evidence_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> EventListResponse:
    case = case_service.get_case(db, case_id)

    conditions = [ForensicEvent.case_id == case.id]
    if source_type is not None:
        conditions.append(ForensicEvent.source_type == source_type)
    if event_type:
        conditions.append(ForensicEvent.event_type == event_type)
    if severity is not None:
        conditions.append(ForensicEvent.severity == severity)
    if user:
        conditions.append(ForensicEvent.user.ilike(f"%{user}%"))
    if host:
        conditions.append(ForensicEvent.host.ilike(f"%{host}%"))
    if timestamp_from is not None:
        conditions.append(ForensicEvent.timestamp >= timestamp_from)
    if timestamp_to is not None:
        conditions.append(ForensicEvent.timestamp <= timestamp_to)
    if evidence_id:
        evidence = evidence_service.get_evidence(db, case, evidence_id)
        conditions.append(ForensicEvent.evidence_id == evidence.id)

    total = (
        db.scalar(select(func.count()).select_from(ForensicEvent).where(*conditions)) or 0
    )
    events = list(
        db.scalars(
            select(ForensicEvent)
            .where(*conditions)
            .options(
                selectinload(ForensicEvent.raw_record),
                selectinload(ForensicEvent.evidence),
            )
            .order_by(ForensicEvent.timestamp.desc(), ForensicEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return EventListResponse(
        events=[serializers.event_response(db, event) for event in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/cases/{case_id}/events/{event_id}",
    response_model=EventDetailResponse,
    summary="Event detail including raw record and evidence (SHA-256) for traceability",
)
def get_event(
    case_id: str,
    event_id: str,
    db: Session = Depends(get_db),
) -> EventDetailResponse:
    case = case_service.get_case(db, case_id)
    event = db.scalar(
        select(ForensicEvent)
        .where(
            ForensicEvent.case_id == case.id,
            ForensicEvent.event_uid == event_id,
        )
        .options(
            selectinload(ForensicEvent.raw_record),
            selectinload(ForensicEvent.evidence),
        )
    )
    if event is None:
        raise ApiError(
            404,
            "EVENT_NOT_FOUND",
            f"Event {event_id} was not found in case {case.case_id}.",
        )
    return serializers.event_detail_response(db, event)
