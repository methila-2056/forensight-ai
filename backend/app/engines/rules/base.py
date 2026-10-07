"""Rule wrappers shared by every forensic rule (Phase 3).

Deterministic contract:

* a rule reads only normalized ForensicEvent rows of its case
* a rule never returns duplicate RuleResults for the same (rule, user/ip/…) key
* exact wording lives in explanations/reasons and avoids any certainty claim
* ``confidence`` is a fixed deterministic indicator weight defined per severity —
  not a probability (see RULE_CONFIDENCE_NOTE)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from app.models import ForensicEvent, SeverityLevel

# Deterministic indicator weight per severity (not a probability).
SEVERITY_WEIGHTS: dict[str, float] = {
    SeverityLevel.LOW.value: 0.4,
    SeverityLevel.MEDIUM.value: 0.6,
    SeverityLevel.HIGH.value: 0.8,
    SeverityLevel.CRITICAL.value: 0.95,
}


def confidence_for(severity: SeverityLevel) -> float:
    return SEVERITY_WEIGHTS.get(severity.value, 0.6)


def rule_enabled(rule_id: str, default: bool = True) -> bool:
    value = os.getenv(f"RULE_{rule_id.replace('-', '')}_ENABLED")
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


@dataclass
class RuleResult:
    rule_id: str
    title: str
    description: str
    severity: SeverityLevel
    confidence: float
    explanation: str
    reasons: list[str]
    events: list[ForensicEvent] = field(default_factory=list)
    timestamp_start: Optional[datetime] = None
    timestamp_end: Optional[datetime] = None

    def event_uids(self) -> list[str]:
        return [e.event_uid for e in sorted(self.events, key=lambda e: (e.timestamp, e.id))]


def _sorted_events(events: list[ForensicEvent]) -> list[ForensicEvent]:
    return sorted(events, key=lambda e: (e.timestamp or datetime.min, e.id))


def events_in_window(
    events: list[ForensicEvent],
    minutes: int,
) -> list[ForensicEvent]:
    """Longest consecutive chain whose span fits inside ``minutes``.

    Deterministic tie-break: the chain that starts latest wins, then count.
    """
    candidates = sorted((e for e in events if e.timestamp is not None),
                        key=lambda e: (e.timestamp, e.id))
    best: list[ForensicEvent] = []
    for anchor in candidates:
        chain = [
            e for e in candidates
            if 0 <= (e.timestamp - anchor.timestamp).total_seconds() <= minutes * 60
            and e.timestamp >= anchor.timestamp
        ]
        if len(chain) > len(best) or (
            len(chain) == len(best) and chain and best and chain[0].timestamp >= best[0].timestamp
        ):
            best = _sorted_events(chain)
    return best


def span(events: list[ForensicEvent]) -> tuple[Optional[datetime], Optional[datetime]]:
    dated = [e for e in events if e.timestamp is not None]
    if not dated:
        return None, None
    return min(e.timestamp for e in dated), max(e.timestamp for e in dated)


def join_actions(events: list[ForensicEvent]) -> str:
    counts: dict[str, int] = {}
    for event in events:
        action = (event.action or "unknown").lower()
        counts[action] = counts.get(action, 0) + 1
    return ", ".join(f"{action}={count}" for action, count in sorted(counts.items()))


def status_field(event: ForensicEvent) -> Optional[str]:
    value = (event.extra or {}).get("status")
    return str(value).strip().lower() if value else None


def status_success(event: ForensicEvent) -> bool:
    return status_field(event) in {"success", "ok", "succeeded", "allowed", "yes"}


def status_failure(event: ForensicEvent) -> bool:
    return status_field(event) in {"failure", "fail", "failed", "denied", "locked", "no", "error"}


class BaseRule:
    rule_id: str = ""
    title: str = ""
    description: str = ""
    severity: SeverityLevel = SeverityLevel.MEDIUM

    def __init__(self) -> None:
        self.enabled: bool = rule_enabled(self.rule_id)
        self.config: dict[str, Any] = {}

    def evaluate(self, events: list[ForensicEvent]) -> list[RuleResult]:
        raise NotImplementedError

    def config_snapshot(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "report_severity": self.severity.value,
            "enabled": self.enabled,
            "description": self.description,
            "config": dict(self.config),
        }

    def make_result(
        self,
        *,
        events: list[ForensicEvent],
        explanation: str,
        reasons: list[str],
        severity: Optional[SeverityLevel] = None,
        timestamp_start: Optional[datetime] = None,
        timestamp_end: Optional[datetime] = None,
        description: Optional[str] = None,
    ) -> RuleResult:
        level = severity or self.severity
        start, end = span(events)
        return RuleResult(
            rule_id=self.rule_id,
            title=self.title,
            description=description or self.description,
            severity=level,
            confidence=confidence_for(level),
            explanation=explanation,
            reasons=reasons,
            events=_sorted_events(events),
            timestamp_start=timestamp_start or start,
            timestamp_end=timestamp_end or end,
        )


def window_delta(minutes: int) -> timedelta:
    return timedelta(minutes=minutes)