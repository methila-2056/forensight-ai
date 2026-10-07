"""Evidence graph builder (Phase 4, Architecture v1.4 §5/§15).

Pure, deterministic logic — no database access:

* three node layers: evidence files → findings → events (events prioritized:
  rule-flagged → anomalous/ML → correlated → the rest)
* three edge relations: ``contains`` (evidence → event), ``triggered``
  (finding → event), ``correlated`` (event ↔ event, reason-tagged)
* hard caps on nodes and edges; the caller reports truncation and renders a
  table fallback so click-through traceability survives the cap
"""

from __future__ import annotations

from datetime import datetime

from app.models import (
    Correlation,
    Evidence,
    FindingStatus,
    ForensicEvent,
    MlFinding,
    RuleFinding,
    SeverityLevel,
    TimelineSignificance,
)
from app.schemas import GraphEdge, GraphNode


def _band(confidence: float) -> str:
    if confidence >= 0.85:
        return "High"
    if confidence >= 0.65:
        return "Medium"
    return "Low"


def build_graph(
    *,
    events: list[ForensicEvent],
    findings: list[RuleFinding | MlFinding],
    links: list[Correlation],
    evidence_rows: list[Evidence],
    finding_index: dict[str, list[dict]],
    events_by_id: dict[int, ForensicEvent],
    evidence_map: dict[int, str],
    max_nodes: int,
    max_edges: int,
) -> tuple[list[GraphNode], list[GraphEdge], bool]:
    """Return (nodes, edges, truncated) within the configured caps."""
    truncated = False
    nodes: list[GraphNode] = []
    node_ids: set[str] = set()

    def add_node(node: GraphNode) -> bool:
        nonlocal truncated
        if node.id in node_ids:
            return True
        if len(nodes) >= max_nodes:
            truncated = True
            return False
        nodes.append(node)
        node_ids.add(node.id)
        return True

    for row in evidence_rows:
        add_node(
            GraphNode(
                id=row.evidence_id,
                type="evidence",
                label=row.original_filename,
                detail=(
                    f"{row.evidence_type} · {row.file_size} bytes · "
                    f"SHA-256 {row.sha256[:16]}…"
                ),
            )
        )

    for row in findings:
        label = getattr(row, "rule_id", None) or row.model_name or "ML"
        add_node(
            GraphNode(
                id=row.finding_uid,
                type="finding",
                label=f"{label}: {row.title}",
                detail=FindingStatus(row.status).value,
                severity=SeverityLevel(row.severity),
            )
        )

    links_by_event: dict[int, list[Correlation]] = {}
    for link in links:
        links_by_event.setdefault(link.event_a_id, []).append(link)
        links_by_event.setdefault(link.event_b_id, []).append(link)

    def event_priority(event: ForensicEvent) -> tuple[int, datetime, int]:
        tags = finding_index.get(event.event_uid, [])
        if any(tag["kind"] == "rule" for tag in tags):
            rank = 0
        elif tags or event.is_anomalous:
            rank = 1
        elif links_by_event.get(event.id):
            rank = 2
        else:
            rank = 3
        return (rank, event.timestamp or datetime.max, event.id)

    for event in sorted(events, key=event_priority):
        tags = finding_index.get(event.event_uid, [])
        if any(tag["kind"] == "rule" for tag in tags):
            significance: TimelineSignificance | None = TimelineSignificance.SUSPICIOUS
        elif tags or event.is_anomalous:
            significance = TimelineSignificance.NOTABLE
        else:
            significance = None
        summary = " · ".join(
            part
            for part in (
                event.event_type or event.source_type,
                event.user,
                event.host,
                event.process,
                event.file_path,
            )
            if part
        )
        if not add_node(
            GraphNode(
                id=event.event_uid,
                type="event",
                label=summary or event.event_uid,
                detail=(event.timestamp.isoformat() if event.timestamp else "no timestamp"),
                significance=significance,
            )
        ):
            break

    edges: list[GraphEdge] = []
    edge_keys: set[tuple[str, str, str]] = set()

    def add_edge(edge: GraphEdge) -> bool:
        nonlocal truncated
        key = (edge.source, edge.target, edge.relation)
        if key in edge_keys:
            return True
        if len(edges) >= max_edges:
            truncated = True
            return False
        edge_keys.add(key)
        edges.append(edge)
        return True

    for row in findings:
        uids = row.triggered_event_ids if isinstance(row, RuleFinding) else row.event_ids
        for uid in uids or []:
            if uid in node_ids and row.finding_uid in node_ids:
                add_edge(
                    GraphEdge(
                        source=row.finding_uid,
                        target=uid,
                        relation="triggered",
                        label="triggered",
                    )
                )

    for event in events:
        evidence_uid = evidence_map.get(event.evidence_id)
        if evidence_uid and event.event_uid in node_ids and evidence_uid in node_ids:
            add_edge(
                GraphEdge(
                    source=evidence_uid,
                    target=event.event_uid,
                    relation="contains",
                    label="contains",
                )
            )

    for link in links:
        event_a = events_by_id.get(link.event_a_id)
        event_b = events_by_id.get(link.event_b_id)
        if not event_a or not event_b:
            continue
        if event_a.event_uid not in node_ids or event_b.event_uid not in node_ids:
            continue
        add_edge(
            GraphEdge(
                source=event_a.event_uid,
                target=event_b.event_uid,
                relation="correlated",
                label=(
                    f"{getattr(link.correlation_type, 'value', link.correlation_type)}"
                    f" · {_band(link.confidence)}"
                ),
                correlation_type=link.correlation_type,  # type: ignore[arg-type]
                confidence=link.confidence,
            )
        )

    return nodes, edges, truncated
