"""Network activity rules (Phase 3).

Input: normalized network ForensicEvent rows of one case (plus process events
for context).

NET-001  External connection shortly after process execution   Medium
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from app import config
from app.engines.rules.base import BaseRule, RuleResult, span
from app.engines.rules.utils import external_ip
from app.models import ForensicEvent, SeverityLevel, SourceType


class ExternalConnectionAfterProcessRule(BaseRule):
    rule_id = "NET-001"
    title = "External connection shortly after process execution"
    description = (
        "Network connections to addresses outside the documented internal range "
        "that follow process execution on the same host within the configured "
        "window. Temporal ordering is an observation, not proof of causation."
    )
    severity = SeverityLevel.MEDIUM

    def __init__(self) -> None:
        super().__init__()
        self.min_connections = config.RULE_NET001_MIN_CONNECTIONS
        self.window_minutes = config.RULE_NET001_WINDOW_MINUTES
        self.config = {
            "min_connections": self.min_connections,
            "window_minutes": self.window_minutes,
        }

    def evaluate(self, events: list[ForensicEvent]) -> list[RuleResult]:
        process_events = [
            e for e in events
            if e.source_type == SourceType.PROCESS.value and e.timestamp is not None
        ]
        by_host: dict[str, list[ForensicEvent]] = defaultdict(list)
        for event in events:
            if event.source_type == SourceType.NETWORK.value and external_ip(event.destination_ip):
                by_host[event.host or ""].append(event)

        results: list[RuleResult] = []
        for host in sorted(by_host):
            window = timedelta(minutes=self.window_minutes)
            linked_processes = [e for e in process_events if (e.host or "") == host]
            paired: list[ForensicEvent] = []
            paired_processes: list[ForensicEvent] = []
            for network in by_host[host]:
                if network.timestamp is None:
                    continue
                preceding = [
                    p for p in linked_processes
                    if p.timestamp is not None
                    and timedelta(0) <= (network.timestamp - p.timestamp) <= window
                ]
                if preceding:
                    paired.append(network)
                    paired_processes.append(min(preceding, key=lambda p: network.timestamp - p.timestamp))
            if len(paired) < self.min_connections:
                continue

            involved = sorted(
                paired + paired_processes,
                key=lambda e: (e.timestamp or datetime.min, e.id),
            )
            destinations = sorted({e.destination_ip for e in paired if e.destination_ip})
            processes = sorted({(p.process or "").lower() for p in paired_processes})
            users = sorted({e.user for e in paired if e.user} | {p.user for p in paired_processes if p.user})
            start, end = span(involved)
            results.append(
                self.make_result(
                    events=involved,
                    explanation=(
                        f"{len(paired)} external network connection(s) on host {host or 'unknown'} "
                        f"within {self.window_minutes} minutes of process execution "
                        f"({', '.join(processes) or 'process activity'}). "
                        "'External' means an address outside RFC1918 private space. "
                        "Temporal association is not causation — requires investigator review."
                    ),
                    reasons=[
                        f"{len(paired)} external connection(s) to "
                        f"{', '.join(destinations[:4])}{'…' if len(destinations) > 4 else ''} "
                        f"following process activity within {self.window_minutes} minutes."
                    ]
                    + ([f"Users involved: {', '.join(users)}."] if users else []),
                    timestamp_start=start,
                    timestamp_end=end,
                )
            )
        return results
