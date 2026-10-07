"""Cross-source correlation, groups, timeline, and graph service (Phase 4).

    normalized ForensicEvents â†’ reason-tagged links (CORR-001â€¦005)
    â†’ activity groups â†’ Reconstructed Investigation Timeline â†’ evidence graph

Guarantees:

* correlation reads only normalized events; raw evidence bytes are untouched
* every link stores an explicit, evidence-backed ``reason`` and an additive
  confidence weight â€” temporal association is never presented as causation
* groups contain only real events from this case (no inferred entities)
* timeline significance is derived from Phase 3 findings and always shown
  with the reconstruction disclaimer; timestamps are the recorded values
* correlation runs are append-only: a new run adds links/groups, previous
  runs are never rewritten
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, terminology
from app.engines.correlation import (
    GroupDraft,
    LinkDraft,
    build_groups,
    build_links,
    confidence_band,
)
from app.engines.graph import build_graph
from app.engines.timeline import build_timeline
from app.errors import ApiError
from app.models import (
    Case,
    Correlation,
    CorrelationRun,
    CorrelationType,
    Evidence,
    ForensicEvent,
    GroupKind,
    InvestigationGroup,
    MlFinding,
    RuleFinding,
    RunStatus,
    SeverityLevel,
    utcnow,
)
from app.schemas import (
    CorrelationDetailResponse,
    CorrelationEventSummary,
    CorrelationListResponse,
    CorrelationRunResponse,
    CorrelationSummary,
    GraphResponse,
    GraphTableRow,
    GroupDetailResponse,
    GroupListResponse,
    GroupSummary,
    TimelineResponse,
)
from app.services import serializers

logger = logging.getLogger("forensight.correlation")

RUN_PREFIX = "CORR-"
LINK_PREFIX = "COR-"
GROUP_PREFIX = "GRP-"

_SEVERITY_ORDER = [
    SeverityLevel.LOW,
    SeverityLevel.MEDIUM,
    SeverityLevel.HIGH,
    SeverityLevel.CRITICAL,
]


def _next_run_uid(db: Session) -> str:
    last = db.scalar(
        select(CorrelationRun.run_uid).order_by(CorrelationRun.run_uid.desc()).limit(1)
    )
    number = int(last.split("-")[1]) + 1 if last else 1
    return f"{RUN_PREFIX}{number:06d}"


def _next_uid(db: Session, prefix: str, column) -> str:
    last = db.scalar(
        select(column).where(column.like(f"{prefix}%")).order_by(column.desc()).limit(1)
    )
    number = int(last.split("-")[1]) + 1 if last else 1
    return f"{prefix}{number:06d}"


def _bump_uid(uid: str) -> str:
    prefix, number = uid.rsplit("-", 1)
    return f"{prefix}-{int(number) + 1:06d}"


def _events_of_case(db: Session, case: Case) -> list[ForensicEvent]:
    return list(
        db.scalars(
            select(ForensicEvent)
            .where(ForensicEvent.case_id == case.id)
            .order_by(ForensicEvent.timestamp.asc().nulls_last(), ForensicEvent.id.asc())
        )
    )


def _evidence_uid_map(db: Session, case: Case) -> dict[int, str]:
    return {
        row.id: row.evidence_id
        for row in db.scalars(select(Evidence).where(Evidence.case_id == case.id))
    }


# ---------------------------------------------------------------------------
# Findings index (Phase 3 output, consumed by timeline/graph/group severity)
# ---------------------------------------------------------------------------

def _finding_index(
    db: Session, case: Case
) -> dict[str, list[dict]]:
    """event_uid â†’ Phase 3 finding tags covering that event."""
    index: dict[str, list[dict]] = {}

    for row in db.scalars(
        select(RuleFinding).where(RuleFinding.case_id == case.id)
    ):
        tag = {
            "finding_id": row.finding_uid,
            "kind": "rule",
            "rule_id": row.rule_id,
            "title": row.title,
            "severity": SeverityLevel(row.severity).value,
            "score": row.composite_suspicion_score,
            "status": str(row.status),
        }
        for uid in row.triggered_event_ids or []:
            index.setdefault(uid, []).append(tag)

    for row in db.scalars(select(MlFinding).where(MlFinding.case_id == case.id)):
        tag = {
            "finding_id": row.finding_uid,
            "kind": "ml",
            "rule_id": None,
            "title": row.title,
            "severity": SeverityLevel(row.severity).value,
            "score": row.score,
            "status": str(row.status),
        }
        for uid in row.event_ids or []:
            index.setdefault(uid, []).append(tag)
    return index


def _max_severity(tags: list[dict]) -> SeverityLevel:
    best = SeverityLevel.LOW
    for tag in tags:
        candidate = SeverityLevel(tag["severity"])
        if _SEVERITY_ORDER.index(candidate) > _SEVERITY_ORDER.index(best):
            best = candidate
    return best


# ---------------------------------------------------------------------------
# Correlate run
# ---------------------------------------------------------------------------

def correlate_case(db: Session, *, case: Case, actor: str = "system") -> CorrelationRun:
    """Run Phase 4 correlation for one case and persist links + groups."""
    events = _events_of_case(db, case)
    if not events:
        raise ApiError(
            400,
            "NO_NORMALIZED_EVENTS",
            terminology.CORRELATION_NO_EVENTS,
            detail={"case_id": case.case_id},
        )

    run = CorrelationRun(
        run_uid=_next_run_uid(db),
        case_id=case.id,
        status=RunStatus.RUNNING,
        started_at=utcnow(),
    )
    db.add(run)
    db.commit()
    run_id = run.id

    try:
        links, link_stats = build_links(events)
        groups = build_groups(links)

        evidence_map = _evidence_uid_map(db, case)
        finding_index = _finding_index(db, case)

        next_link_uid = _next_uid(db, LINK_PREFIX, Correlation.correlation_uid)
        for link in links:
            shared = link.shared_entities
            row = Correlation(
                correlation_uid=next_link_uid,
                case_id=case.id,
                run_id=run_id,
                correlation_type=link.correlation_type.value,
                event_a_id=link.event_a.id,
                event_b_id=link.event_b.id,
                time_delta_seconds=round(link.time_delta_seconds, 3),
                confidence=link.confidence,
                reason=link.reason,
                shared_entities=shared,
                evidence_ids=sorted(
                    {evidence_map[ref] for ref in link.evidence_refs if ref in evidence_map}
                ),
            )
            db.add(row)
            next_link_uid = _bump_uid(next_link_uid)
        db.flush()

        next_group_uid = _next_uid(db, GROUP_PREFIX, InvestigationGroup.group_uid)
        for draft in groups:
            member_uids = [event.event_uid for event in draft.member_events]
            tags = [
                tag
                for uid in member_uids
                for tag in finding_index.get(uid, [])
            ]
            severity = _max_severity(tags)
            if not tags and any(event.is_anomalous for event in draft.member_events):
                severity = SeverityLevel.MEDIUM
            row = InvestigationGroup(
                group_uid=next_group_uid,
                case_id=case.id,
                run_id=run_id,
                kind=draft.kind.value,
                title=draft.title,
                severity=severity.value,
                explanation=draft.explanation,
                time_start=draft.time_start,
                time_end=draft.time_end,
                member_event_ids=member_uids,
                correlation_uids=_group_link_uids(db, run_id, draft),
                evidence_ids=sorted(
                    {
                        evidence_map[event.evidence_id]
                        for event in draft.member_events
                        if event.evidence_id in evidence_map
                    }
                ),
            )
            db.add(row)
            next_group_uid = _bump_uid(next_group_uid)
        db.flush()

        stats = {
            **link_stats,
            "events_considered": len(events),
            "groups": len(groups),
            "group_severities": {
                severity.value: sum(
                    1 for draft in groups if _group_severity(draft, finding_index) == severity
                )
                for severity in _SEVERITY_ORDER
            },
            "actor": actor,
            "disclaimer": terminology.CORRELATION_DISCLAIMER,
            "caption": "Reason-tagged links from normalized events; temporal "
            "association is not causation.",
        }

        run = db.get(CorrelationRun, run_id)
        run.status = RunStatus.COMPLETED
        run.stats = stats
        run.finished_at = utcnow()
        case.last_activity = utcnow()
        db.commit()
        db.refresh(run)
        return run

    except ApiError:
        raise
    except Exception:  # noqa: BLE001 - recorded as a FAILED run, path not exposed
        logger.exception("Correlation failed for case %s", case.case_id)
        db.rollback()
        run = db.get(CorrelationRun, run_id)
        run.status = RunStatus.FAILED
        run.error = "Correlation failed unexpectedly; see server logs."
        run.finished_at = utcnow()
        db.commit()
        db.refresh(run)
        return run


def _group_severity(draft: GroupDraft, finding_index: dict[str, list[dict]]) -> SeverityLevel:
    tags = [
        tag
        for event in draft.member_events
        for tag in finding_index.get(event.event_uid, [])
    ]
    severity = _max_severity(tags)
    if not tags and any(event.is_anomalous for event in draft.member_events):
        return SeverityLevel.MEDIUM
    return severity


def _group_link_uids(db: Session, run_id: int, draft: GroupDraft) -> list[str]:
    """Correlation UIDs of a group's links (queried once per group is fine
    at demo scale; links are ordered deterministically)."""
    if not draft.links:
        return []
    member_ids = {event.id for event in draft.member_events}
    rows = db.scalars(
        select(Correlation.correlation_uid)
        .where(
            Correlation.run_id == run_id,
            Correlation.event_a_id.in_(member_ids),
            Correlation.event_b_id.in_(member_ids),
        )
        .order_by(Correlation.correlation_uid.asc())
    )
    return list(rows)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def runs_for_case(db: Session, case: Case) -> list[CorrelationRun]:
    return list(
        db.scalars(
            select(CorrelationRun)
            .where(CorrelationRun.case_id == case.id)
            .order_by(CorrelationRun.id.desc())
        )
    )


def _resolve_run(db: Session, case: Case, run_id: str | None) -> CorrelationRun | None:
    """Latest run by default (or a specific one); None when no run exists."""
    query = select(CorrelationRun).where(CorrelationRun.case_id == case.id)
    if run_id:
        query = query.where(CorrelationRun.run_uid == run_id)
    rows = list(db.scalars(query.order_by(CorrelationRun.id.desc())))
    if not rows:
        if run_id:
            raise ApiError(
                404, "CORRELATION_RUN_NOT_FOUND", f"Correlation run {run_id} was not found."
            )
        return None
    completed = next((row for row in rows if row.status == RunStatus.COMPLETED), None)
    return completed or rows[0]


def list_correlations(
    db: Session,
    case: Case,
    *,
    run_id: str | None = None,
    corr_type: CorrelationType | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Correlation], int, CorrelationRun | None]:
    run = _resolve_run(db, case, run_id)
    if run is None:
        return [], 0, None
    query = select(Correlation).where(Correlation.run_id == run.id)
    if corr_type is not None:
        query = query.where(Correlation.correlation_type == corr_type.value)
    rows = list(db.scalars(query.order_by(Correlation.correlation_uid.asc())))
    return rows[offset : offset + limit], len(rows), run


def get_correlation(db: Session, case: Case, correlation_uid: str) -> Correlation:
    row = db.scalar(
        select(Correlation).where(
            Correlation.correlation_uid == correlation_uid, Correlation.case_id == case.id
        )
    )
    if row is None:
        raise ApiError(
            404, "CORRELATION_NOT_FOUND", f"Correlation {correlation_uid} was not found."
        )
    return row


def get_correlation_any(db: Session, correlation_uid: str) -> tuple[Case, Correlation]:
    """Caseless lookup (the correlation UID is globally unique)."""
    row = db.scalar(select(Correlation).where(Correlation.correlation_uid == correlation_uid))
    if row is None:
        raise ApiError(
            404, "CORRELATION_NOT_FOUND", f"Correlation {correlation_uid} was not found."
        )
    case = db.get(Case, row.case_id)
    if case is None:
        raise ApiError(404, "CASE_NOT_FOUND", "The owning case was not found.")
    return case, row


def list_groups(
    db: Session,
    case: Case,
    *,
    run_id: str | None = None,
    kind: GroupKind | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[InvestigationGroup], int, CorrelationRun | None]:
    run = _resolve_run(db, case, run_id)
    if run is None:
        return [], 0, None
    query = select(InvestigationGroup).where(InvestigationGroup.run_id == run.id)
    if kind is not None:
        query = query.where(InvestigationGroup.kind == kind.value)
    rows = list(db.scalars(query.order_by(InvestigationGroup.group_uid.asc())))
    return rows[offset : offset + limit], len(rows), run


def get_group(db: Session, case: Case, group_uid: str) -> InvestigationGroup:
    row = db.scalar(
        select(InvestigationGroup).where(
            InvestigationGroup.group_uid == group_uid, InvestigationGroup.case_id == case.id
        )
    )
    if row is None:
        raise ApiError(404, "GROUP_NOT_FOUND", f"Activity group {group_uid} was not found.")
    return row


def get_group_any(db: Session, group_uid: str) -> tuple[Case, InvestigationGroup]:
    """Caseless lookup (the group UID is globally unique)."""
    row = db.scalar(
        select(InvestigationGroup).where(InvestigationGroup.group_uid == group_uid)
    )
    if row is None:
        raise ApiError(404, "GROUP_NOT_FOUND", f"Activity group {group_uid} was not found.")
    case = db.get(Case, row.case_id)
    if case is None:
        raise ApiError(404, "CASE_NOT_FOUND", "The owning case was not found.")
    return case, row


def _links_of_run(db: Session, run: CorrelationRun | None) -> list[Correlation]:
    if run is None:
        return []
    return list(
        db.scalars(
            select(Correlation)
            .where(Correlation.run_id == run.id)
            .order_by(Correlation.correlation_uid.asc())
        )
    )


def _event_summary(
    event: ForensicEvent, evidence_map: dict[int, str]
) -> CorrelationEventSummary:
    return CorrelationEventSummary(
        event_id=event.event_uid,
        timestamp=event.timestamp,
        source_type=event.source_type,  # type: ignore[arg-type]
        event_type=event.event_type,
        user=event.user,
        host=event.host,
        source_ip=event.source_ip,
        destination_ip=event.destination_ip,
        process=event.process,
        file_path=event.file_path,
        action=event.action,
        anomaly_score=event.anomaly_score,
        is_anomalous=bool(event.is_anomalous),
        evidence_id=evidence_map.get(event.evidence_id, ""),
    )


def correlation_summary(
    db: Session, case: Case, run: CorrelationRun, row: Correlation
) -> CorrelationSummary:
    evidence_map = _evidence_uid_map(db, case)
    event_a = db.get(ForensicEvent, row.event_a_id)
    event_b = db.get(ForensicEvent, row.event_b_id)
    if event_a is None or event_b is None:
        raise ApiError(409, "CORRELATION_EVENT_MISSING", "A linked event no longer exists.")
    return CorrelationSummary(
        correlation_id=row.correlation_uid,
        case_id=case.case_id,
        run_id=run.run_uid,
        correlation_type=CorrelationType(row.correlation_type),
        event_a=_event_summary(event_a, evidence_map),
        event_b=_event_summary(event_b, evidence_map),
        time_delta_seconds=row.time_delta_seconds,
        confidence=row.confidence,
        confidence_band=confidence_band(row.confidence),
        reason=row.reason,
        shared_entities=row.shared_entities or {},
        evidence_ids=row.evidence_ids or [],
        created_at=row.created_at,
    )


def correlation_detail(
    db: Session, case: Case, row: Correlation
) -> CorrelationDetailResponse:
    run = db.get(CorrelationRun, row.run_id)
    if run is None:
        raise ApiError(409, "CORRELATION_RUN_MISSING", "The correlation run no longer exists.")
    base = correlation_summary(db, case, run, row)
    event_a = db.get(ForensicEvent, row.event_a_id)
    event_b = db.get(ForensicEvent, row.event_b_id)
    return CorrelationDetailResponse(
        **base.model_dump(),
        disclaimer=terminology.CORRELATION_DISCLAIMER,
        event_a_detail=serializers.event_detail_response(db, event_a) if event_a else None,
        event_b_detail=serializers.event_detail_response(db, event_b) if event_b else None,
    )


def correlation_list_response(
    db: Session,
    case: Case,
    *,
    rows: list[Correlation],
    total: int,
    limit: int,
    offset: int,
    run: CorrelationRun | None,
) -> CorrelationListResponse:
    return CorrelationListResponse(
        correlations=[
            correlation_summary(db, case, run, row)
            for row in rows
            if run is not None
        ],
        total=total,
        limit=limit,
        offset=offset,
        disclaimer=terminology.CORRELATION_DISCLAIMER,
    )


def group_summary(db: Session, case: Case, row: InvestigationGroup) -> GroupSummary:
    members = row.member_event_ids or []
    run = db.get(CorrelationRun, row.run_id) if row.run_id else None
    return GroupSummary(
        group_id=row.group_uid,
        case_id=case.case_id,
        run_id=run.run_uid if run else "",
        kind=GroupKind(row.kind),
        title=row.title,
        severity=SeverityLevel(row.severity),
        explanation=row.explanation,
        time_start=row.time_start,
        time_end=row.time_end,
        event_count=len(members),
        correlation_count=len(row.correlation_uids or []),
        evidence_ids=row.evidence_ids or [],
        correlation_uids=row.correlation_uids or [],
        created_at=row.created_at,
    )


def group_detail(db: Session, case: Case, row: InvestigationGroup) -> GroupDetailResponse:
    base = group_summary(db, case, row)
    evidence_map = _evidence_uid_map(db, case)
    uids = row.member_event_ids or []
    events = db.scalars(select(ForensicEvent).where(ForensicEvent.event_uid.in_(uids))).all()
    order = {uid: index for index, uid in enumerate(uids)}
    events = sorted(events, key=lambda event: order.get(event.event_uid, 0))
    return GroupDetailResponse(
        **base.model_dump(),
        member_events=[_event_summary(event, evidence_map) for event in events],
        disclaimer=terminology.CORRELATION_DISCLAIMER,
    )


def group_list_response(
    db: Session,
    case: Case,
    *,
    rows: list[InvestigationGroup],
    total: int,
    limit: int,
    offset: int,
) -> GroupListResponse:
    return GroupListResponse(
        groups=[group_summary(db, case, row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        disclaimer=terminology.CORRELATION_DISCLAIMER,
    )


def correlation_run_response(case: Case, run: CorrelationRun) -> CorrelationRunResponse:
    return CorrelationRunResponse(
        run_id=run.run_uid,
        case_id=case.case_id,
        status=run.status,  # type: ignore[arg-type]
        started_at=run.started_at,
        finished_at=run.finished_at,
        stats=run.stats,
        error=run.error,
    )


# ---------------------------------------------------------------------------
# Reconstructed Investigation Timeline
# ---------------------------------------------------------------------------

def timeline(
    db: Session, case: Case, *, run_id: str | None = None
) -> TimelineResponse:
    all_events = _events_of_case(db, case)
    events = [event for event in all_events if event.timestamp is not None]
    finding_index = _finding_index(db, case)
    run = _resolve_run(db, case, run_id)
    links = _links_of_run(db, run)

    entries, total, truncated = build_timeline(
        events,
        finding_index=finding_index,
        links=links,
        events_by_id={event.id: event for event in all_events},
        evidence_map=_evidence_uid_map(db, case),
        context_minutes=config.TIMELINE_CONTEXT_MINUTES,
        max_entries=config.TIMELINE_MAX_ENTRIES,
    )

    excluded = len(all_events) - len(events)
    note: str | None = None
    if not all_events:
        note = terminology.CORRELATION_NO_EVENTS
    elif not entries:
        note = (
            "No flagged, correlated, or contextual events yet. Run automated "
            "analysis and correlation to reconstruct this timeline."
        )
    elif truncated:
        note = (
            f"Showing the first {config.TIMELINE_MAX_ENTRIES} of {total} "
            "entries (TIMELINE_MAX_ENTRIES)."
        )
    if excluded and entries:
        note = (note + " " if note else "") + (
            f"{excluded} event(s) without a recorded timestamp were excluded."
        )

    return TimelineResponse(
        case_id=case.case_id,
        label=terminology.TIMELINE_LABEL,
        disclaimer=terminology.TIMELINE_DISCLAIMER,
        entries=entries,
        total=total,
        truncated=truncated,
        note=note,
    )


# ---------------------------------------------------------------------------
# Evidence graph
# ---------------------------------------------------------------------------

def graph(db: Session, case: Case, *, run_id: str | None = None) -> GraphResponse:
    events = _events_of_case(db, case)
    run = _resolve_run(db, case, run_id)
    links = _links_of_run(db, run)
    finding_index = _finding_index(db, case)
    evidence_rows = list(
        db.scalars(
            select(Evidence).where(Evidence.case_id == case.id).order_by(Evidence.evidence_id)
        )
    )
    evidence_map = {row.id: row.evidence_id for row in evidence_rows}
    findings: list[RuleFinding | MlFinding] = list(
        db.scalars(select(RuleFinding).where(RuleFinding.case_id == case.id))
    ) + list(db.scalars(select(MlFinding).where(MlFinding.case_id == case.id)))

    nodes, edges, truncated = build_graph(
        events=events,
        findings=findings,
        links=links,
        evidence_rows=evidence_rows,
        finding_index=finding_index,
        events_by_id={event.id: event for event in events},
        evidence_map=evidence_map,
        max_nodes=config.MAX_GRAPH_NODES,
        max_edges=config.MAX_GRAPH_EDGES,
    )

    labels = {node.id: node.label for node in nodes}
    table_rows = [
        GraphTableRow(
            source=labels.get(edge.source, edge.source),
            relation=edge.relation,
            target=labels.get(edge.target, edge.target),
        )
        for edge in edges
    ]

    note: str | None = None
    if truncated:
        note = (
            f"Graph capped at {config.MAX_GRAPH_NODES} nodes / "
            f"{config.MAX_GRAPH_EDGES} edges (MAX_GRAPH_NODES, "
            "MAX_GRAPH_EDGES); use the table rows for the full listing."
        )
    elif run is None:
        note = "No correlation run yet — showing evidence, findings, and events only."

    return GraphResponse(
        case_id=case.case_id,
        run_id=run.run_uid if run else None,
        nodes=nodes,
        edges=edges,
        table_rows=table_rows,
        truncated=truncated,
        max_nodes=config.MAX_GRAPH_NODES,
        max_edges=config.MAX_GRAPH_EDGES,
        disclaimer=terminology.CORRELATION_DISCLAIMER,
        note=note,
    )


