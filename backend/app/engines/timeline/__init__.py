"""Reconstructed Investigation Timeline builder (Phase 4, Architecture v1.4 §12).

Pure, deterministic logic — no database access:

* union of anomalous events, finding-triggered events, and correlation
  members, plus ±context minutes of surrounding events as context
* ordered by the **recorded** timestamps (events without a timestamp are
  excluded by the caller — never invented)
* significance derives from Phase 3 findings:
  rule finding → SUSPICIOUS · ML finding / anomalous window → NOTABLE ·
  context and correlation-only observations → NORMAL
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models import Correlation, ForensicEvent, TimelineSignificance
from app.schemas import TimelineEntry


def build_timeline(
    events: list[ForensicEvent],
    *,
    finding_index: dict[str, list[dict]],
    links: list[Correlation],
    events_by_id: dict[int, ForensicEvent],
    evidence_map: dict[int, str],
    context_minutes: int,
    max_entries: int,
) -> tuple[list[TimelineEntry], int, bool]:
    """Return (entries, total, truncated). ``events`` must be timestamped."""
    links_by_event: dict[int, list[Correlation]] = {}
    for link in links:
        links_by_event.setdefault(link.event_a_id, []).append(link)
        links_by_event.setdefault(link.event_b_id, []).append(link)

    tagged_ids: set[int] = set()
    draft: list[tuple[datetime, ForensicEvent, TimelineEntry]] = []

    for event in events:
        tags = finding_index.get(event.event_uid, [])
        event_links = links_by_event.get(event.id, [])
        if not tags and not event.is_anomalous and not event_links:
            continue
        tagged_ids.add(event.id)

        reasons: list[str] = []
        finding_ids: list[str] = []
        rule_seen = False
        ml_seen = False
        for tag in tags:
            finding_ids.append(tag["finding_id"])
            if tag["kind"] == "rule":
                rule_seen = True
                reasons.append(
                    f"Rule {tag['rule_id']} triggered: {tag['title']} "
                    f"({tag['severity']} severity)"
                )
            else:
                ml_seen = True
                reasons.append(
                    f"ML finding {tag['finding_id']}: {tag['title']} "
                    f"(anomaly score {float(tag['score']):.3f})"
                )

        if rule_seen:
            significance = TimelineSignificance.SUSPICIOUS
        elif ml_seen or event.is_anomalous:
            significance = TimelineSignificance.NOTABLE
            if not ml_seen and event.anomaly_score is not None:
                reasons.append(
                    f"Flagged as anomalous in its event window "
                    f"(anomaly score {event.anomaly_score:.3f})"
                )
        else:
            significance = TimelineSignificance.NORMAL
            reasons.append("Linked to other case events by correlation only")

        correlation_ids: list[str] = []
        for link in event_links[:3]:
            correlation_ids.append(link.correlation_uid)
            other_id = link.event_b_id if link.event_a_id == event.id else link.event_a_id
            other = events_by_id.get(other_id)
            reasons.append(
                f"Correlation {link.correlation_uid} "
                f"({getattr(link.correlation_type, 'value', link.correlation_type)}) "
                f"with {other.event_uid if other else 'another event'} — "
                f"{_band(link.confidence)} confidence"
            )

        draft.append(
            (
                event.timestamp,  # type: ignore[arg-type]
                event,
                TimelineEntry(
                    timestamp=event.timestamp,
                    event_id=event.event_uid,
                    source_type=event.source_type,  # type: ignore[arg-type]
                    event_type=event.event_type,
                    user=event.user,
                    host=event.host,
                    process=event.process,
                    file_path=event.file_path,
                    action=event.action,
                    anomaly_score=event.anomaly_score,
                    is_anomalous=bool(event.is_anomalous),
                    significance=significance,
                    reasons=reasons,
                    finding_ids=finding_ids,
                    correlation_ids=correlation_ids,
                    evidence_id=evidence_map.get(event.evidence_id, ""),
                    context=False,
                ),
            )
        )

    # Context: untagged events within ±context_minutes of a tagged one.
    if tagged_ids:
        delta = timedelta(minutes=context_minutes)
        tagged_times = [event.timestamp for event in events if event.id in tagged_ids]
        for event in events:
            if event.id in tagged_ids:
                continue
            if any(abs(event.timestamp - other) <= delta for other in tagged_times):
                draft.append(
                    (
                        event.timestamp,  # type: ignore[arg-type]
                        event,
                        TimelineEntry(
                            timestamp=event.timestamp,
                            event_id=event.event_uid,
                            source_type=event.source_type,  # type: ignore[arg-type]
                            event_type=event.event_type,
                            user=event.user,
                            host=event.host,
                            process=event.process,
                            file_path=event.file_path,
                            action=event.action,
                            anomaly_score=event.anomaly_score,
                            is_anomalous=bool(event.is_anomalous),
                            significance=TimelineSignificance.NORMAL,
                            reasons=[
                                f"Context: within ±{context_minutes} minutes of a "
                                "flagged event"
                            ],
                            evidence_id=evidence_map.get(event.evidence_id, ""),
                            context=True,
                        ),
                    )
                )

    draft.sort(key=lambda item: (item[0], item[1].id))
    total = len(draft)
    entries = [entry for _, _, entry in draft[:max_entries]]
    return entries, total, total > max_entries


def _band(confidence: float) -> str:
    if confidence >= 0.85:
        return "High"
    if confidence >= 0.65:
        return "Medium"
    return "Low"
