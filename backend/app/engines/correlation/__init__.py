"""Cross-source correlation engine (Phase 4, Architecture v1.4 §11).

Pure, deterministic logic — no database access, no randomness:

* ``build_links`` sweeps time-sorted events and emits one reason-tagged link
  per event pair that sits inside ``CORRELATION_WINDOW_SECONDS`` and shares a
  real attribute (host / user / source IP) or a typed process relation
* confidence is an explicit additive weight of the shared attributes —
  never a probability — and every link carries a human-readable reason
* ``build_groups`` clusters linked events into activity groups with
  union-find; groups contain only real, evidence-backed events

Temporal association is never causation: every consumer surfaces
``terminology.CORRELATION_DISCLAIMER`` alongside these results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from app import config, terminology
from app.engines.rules.utils import external_ip
from app.models import CorrelationType, ForensicEvent, GroupKind, SourceType

# Safety caps (deterministic early stops, reported in run stats).
CORRELATION_MAX_LINKS = 5000
MAX_GROUPS_PER_RUN = 50
MAX_GROUP_MEMBERS = 200

SOURCE_LABELS: dict[str, str] = {
    SourceType.AUTH.value: "authentication",
    SourceType.PROCESS.value: "process",
    SourceType.FILE.value: "file-activity",
    SourceType.NETWORK.value: "network",
    SourceType.BROWSER.value: "browser",
    SourceType.SYSTEM.value: "system",
    SourceType.GENERIC.value: "generic",
}

_GROUP_KIND_BY_SOURCE: dict[str, GroupKind] = {
    SourceType.AUTH.value: GroupKind.AUTHENTICATION,
    SourceType.PROCESS.value: GroupKind.PROCESS,
    SourceType.FILE.value: GroupKind.FILE,
    SourceType.NETWORK.value: GroupKind.NETWORK,
}


@dataclass
class LinkDraft:
    event_a: ForensicEvent
    event_b: ForensicEvent
    correlation_type: CorrelationType
    time_delta_seconds: float
    confidence: float
    shared_entities: dict[str, str]
    reason: str
    evidence_refs: tuple[int, ...] = ()


@dataclass
class GroupDraft:
    kind: GroupKind
    title: str
    explanation: str
    member_events: list[ForensicEvent]
    links: list[LinkDraft] = field(default_factory=list)
    time_start: Optional[datetime] = None
    time_end: Optional[datetime] = None


def confidence_band(confidence: float) -> str:
    """Low / Medium / High presentation band for an additive confidence."""
    if confidence >= 0.85:
        return "High"
    if confidence >= 0.65:
        return "Medium"
    return "Low"


def _shared(a: ForensicEvent, b: ForensicEvent) -> tuple[dict[str, str], float]:
    shared: dict[str, str] = {}
    confidence = config.CORRELATION_WEIGHT_TIME_WINDOW
    if a.host and b.host and a.host == b.host:
        shared["host"] = a.host
        confidence += config.CORRELATION_WEIGHT_SAME_HOST
    if a.user and b.user and a.user == b.user:
        shared["user"] = a.user
        confidence += config.CORRELATION_WEIGHT_SAME_USER
    if a.source_ip and b.source_ip and a.source_ip == b.source_ip:
        shared["source_ip"] = a.source_ip
        confidence += config.CORRELATION_WEIGHT_SAME_SOURCE_IP
    return shared, round(min(confidence, 1.0), 4)


def _delta_seconds(a: ForensicEvent, b: ForensicEvent) -> float:
    assert a.timestamp is not None and b.timestamp is not None
    return (b.timestamp - a.timestamp).total_seconds()


def _reason(
    corr_type: CorrelationType,
    a: ForensicEvent,
    b: ForensicEvent,
    delta: float,
    shared: dict[str, str],
    window: int,
) -> str:
    order = "follows" if (a.timestamp and b.timestamp and b.timestamp >= a.timestamp) else "precedes"
    when = f"{delta:.0f} seconds apart (window {window}s)"
    if corr_type is CorrelationType.SAME_HOST:
        return (
            f"Both events occurred on host {shared['host']} and {when}. "
            "Shared host is co-occurrence, not causation."
        )
    if corr_type is CorrelationType.SAME_USER:
        return (
            f"Both events involve user {shared['user']} and {when}. "
            "Shared user is co-occurrence, not causation."
        )
    if corr_type is CorrelationType.SAME_SOURCE_IP:
        label = "at least one event is authentication or network activity"
        return (
            f"Both events carry source IP {shared['source_ip']} and {when} "
            f"({label})."
        )
    if corr_type is CorrelationType.PROCESS_TO_FILE:
        process = (a.process or b.process or "").strip() or "a process"
        path = (a.file_path or b.file_path or "").strip() or "file activity"
        return (
            f"Process '{process}' {order} file activity ({path}) on the same "
            f"host ({shared.get('host', 'unknown')}) and {when}. Temporal "
            "association is not causation."
        )
    # CORR-005
    process = (a.process or b.process or "").strip() or "a process"
    destination = (a.destination_ip or b.destination_ip or "").strip() or "an external address"
    return (
        f"Process '{process}' {order} an external connection to {destination} "
        f"on the same host ({shared.get('host', 'unknown')}) and {when}. "
        "Temporal association is not causation."
    )


def evaluate_pair(
    a: ForensicEvent, b: ForensicEvent, window_seconds: int
) -> Optional[tuple[CorrelationType, dict[str, str], float, float, str]]:
    """Classify one ordered event pair, or return None when it does not link.

    Precedence is most-specific-first: typed process relations, then shared
    identity, then shared network attribute, then shared host.
    """
    delta = _delta_seconds(a, b)
    if delta < 0 or delta > window_seconds:
        return None
    shared, confidence = _shared(a, b)

    same_host = "host" in shared
    a_proc = a.source_type == SourceType.PROCESS.value
    b_proc = b.source_type == SourceType.PROCESS.value
    a_file = a.source_type == SourceType.FILE.value
    b_file = b.source_type == SourceType.FILE.value
    a_net = a.source_type == SourceType.NETWORK.value
    b_net = b.source_type == SourceType.NETWORK.value

    corr_type: CorrelationType | None = None
    if same_host and ((a_proc and b_file) or (b_proc and a_file)):
        corr_type = CorrelationType.PROCESS_TO_FILE
    elif same_host and (
        (a_proc and b_net and external_ip(b.destination_ip))
        or (b_proc and a_net and external_ip(a.destination_ip))
    ):
        corr_type = CorrelationType.PROCESS_TO_NETWORK
    elif a.user and b.user and a.user == b.user:
        corr_type = CorrelationType.SAME_USER
    elif (
        "source_ip" in shared
        and (
            a.source_type in (SourceType.AUTH.value, SourceType.NETWORK.value)
            or b.source_type in (SourceType.AUTH.value, SourceType.NETWORK.value)
        )
    ):
        corr_type = CorrelationType.SAME_SOURCE_IP
    elif same_host:
        corr_type = CorrelationType.SAME_HOST

    if corr_type is None:
        return None
    return corr_type, shared, confidence, delta, _reason(corr_type, a, b, delta, shared, window_seconds)


def build_links(
    events: list[ForensicEvent],
    *,
    window_seconds: int | None = None,
    max_links: int = CORRELATION_MAX_LINKS,
) -> tuple[list[LinkDraft], dict]:
    """Sweep time-sorted events and build every reason-tagged link."""
    window = window_seconds if window_seconds is not None else config.CORRELATION_WINDOW_SECONDS
    dated = sorted(
        (event for event in events if event.timestamp is not None),
        key=lambda event: (event.timestamp, event.id),
    )
    links: list[LinkDraft] = []
    pairs_evaluated = 0
    truncated = False
    for index, a in enumerate(dated):
        if truncated:
            break
        for b in dated[index + 1 :]:
            delta = (b.timestamp - a.timestamp).total_seconds()  # type: ignore[operator]
            if delta > window:
                break
            pairs_evaluated += 1
            result = evaluate_pair(a, b, window)
            if result is None:
                continue
            corr_type, shared, confidence, delta, reason = result
            evidence_refs = tuple(sorted({a.evidence_id, b.evidence_id}))
            links.append(
                LinkDraft(
                    event_a=a,
                    event_b=b,
                    correlation_type=corr_type,
                    time_delta_seconds=delta,
                    confidence=confidence,
                    shared_entities=shared,
                    reason=reason,
                    evidence_refs=evidence_refs,
                )
            )
            if len(links) >= max_links:
                truncated = True
                break

    stats = {
        "window_seconds": window,
        "dated_events": len(dated),
        "pairs_evaluated": pairs_evaluated,
        "links": len(links),
        "links_truncated": truncated,
        "by_type": {
            corr_type.value: sum(1 for link in links if link.correlation_type is corr_type)
            for corr_type in CorrelationType
        },
        "by_band": {
            band: sum(
                1 for link in links if confidence_band(link.confidence) == band
            )
            for band in ("Low", "Medium", "High")
        },
    }
    return links, stats


# ---------------------------------------------------------------------------
# Activity groups (union-find over links)
# ---------------------------------------------------------------------------

def _find(parents: dict[int, int], node: int) -> int:
    while parents[node] != node:
        parents[node] = parents[parents[node]]
        node = parents[node]
    return node


def _dominant(values: list[str]) -> Optional[str]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[0][0] if counts else None


def _group_kind(members: list[ForensicEvent]) -> GroupKind:
    kinds = {member.source_type for member in members}
    if len(kinds) == 1:
        only = next(iter(kinds))
        return _GROUP_KIND_BY_SOURCE.get(only, GroupKind.CROSS_SOURCE)
    return GroupKind.CROSS_SOURCE


def _group_title(kind: GroupKind, members: list[ForensicEvent]) -> str:
    if kind is GroupKind.AUTHENTICATION:
        subject = _dominant([m.user or m.host or m.source_ip or "unknown" for m in members])
        return f"Authentication cluster — {subject}"
    if kind is GroupKind.PROCESS:
        subject = _dominant([(m.process or "unknown process").lower() for m in members])
        return f"Process execution cluster — {subject}"
    if kind is GroupKind.FILE:
        subject = _dominant([m.host or m.user or "unattributed" for m in members])
        return f"File activity burst — {subject}"
    if kind is GroupKind.NETWORK:
        subject = _dominant([m.destination_ip or m.source_ip or "external" for m in members])
        return f"External connection cluster — {subject}"
    users = _dominant([m.user for m in members if m.user])
    return f"Cross-source activity group — {users or 'multiple sources'}"


def build_groups(
    links: list[LinkDraft],
    *,
    max_groups: int = MAX_GROUPS_PER_RUN,
    max_members: int = MAX_GROUP_MEMBERS,
) -> list[GroupDraft]:
    """Cluster linked events into activity groups (connected components)."""
    if not links:
        return []
    parents: dict[int, int] = {}
    for link in links:
        for event in (link.event_a, link.event_b):
            parents.setdefault(event.id, event.id)
    for link in links:
        root_a = _find(parents, link.event_a.id)
        root_b = _find(parents, link.event_b.id)
        if root_a != root_b:
            parents[root_b] = root_a

    components: dict[int, list[ForensicEvent]] = {}
    for event_id in parents:
        root = _find(parents, event_id)
        components.setdefault(root, []).append(event_id)
    by_id = {event.id: event for link in links for event in (link.event_a, link.event_b)}

    drafts: list[GroupDraft] = []
    for root, event_ids in components.items():
        members = sorted(
            (by_id[event_id] for event_id in event_ids),
            key=lambda event: (event.timestamp or datetime.min, event.id),
        )
        if len(members) < 2:
            continue
        members = members[:max_members]
        member_ids = {event.id for event in members}
        member_links = [
            link
            for link in links
            if link.event_a.id in member_ids and link.event_b.id in member_ids
        ]
        kind = _group_kind(members)
        dated = [event for event in members if event.timestamp is not None]
        time_start = min((event.timestamp for event in dated), default=None)
        time_end = max((event.timestamp for event in dated), default=None)
        corr_types = sorted({link.correlation_type.value for link in member_links})
        source_label = (
            SOURCE_LABELS[next(iter({m.source_type for m in members}))]
            if len({m.source_type for m in members}) == 1
            else "cross-source"
        )
        window = config.CORRELATION_WINDOW_SECONDS
        explanation = (
            f"{len(members)} {source_label} event(s) between "
            f"{time_start:%Y-%m-%d %H:%M:%S} and {time_end:%Y-%m-%d %H:%M:%S} "
            f"linked by {len(member_links)} correlation(s) "
            f"({', '.join(corr_types)}) inside the {window}-second window. "
            f"{terminology.CORRELATION_DISCLAIMER}"
        )
        drafts.append(
            GroupDraft(
                kind=kind,
                title=_group_title(kind, members),
                explanation=explanation,
                member_events=members,
                links=member_links,
                time_start=time_start,
                time_end=time_end,
            )
        )

    drafts.sort(
        key=lambda draft: (
            draft.time_start or datetime.min,
            -len(draft.member_events),
            draft.title,
        )
    )
    return drafts[:max_groups]
