"""Deterministic event-window feature builder (Phase 3, Architecture §9).

Input: normalized ForensicEvent rows of one case.
Output: fixed-length windows (ANALYSIS_WINDOW_MINUTES) with a deterministic
feature vector per window — FEATURE_VERSION "phase3-window-v1" (18 features).

Rules of determinism:

* timestamps are floored to the window boundary (no timezone shifts); a window
  exists only where at least one event with a timestamp is present, so the
  feature set never depends on analyst decisions
* feature values are plain counts/distinct counts — no floating point input
* events that share a window are counted once; duplicates are preserved as a
  separate ``duplicate_count`` feature rather than deleted
* all iteration orderings are driven by ``(timestamp, id)``

The feature vocabulary is the contract between this builder and the ML
detector; it is snapshotted into every ML finding for traceability.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app import config
from app.models import ForensicEvent, SourceType

WINDOW_MINUTES = config.ANALYSIS_WINDOW_MINUTES
FEATURE_VERSION = "phase3-window-v1"

_SOURCE_TYPES = tuple(item.value for item in SourceType)

FEATURE_NAMES: tuple[str, ...] = (
    "src_authentication",
    "src_process",
    "src_file_activity",
    "src_network",
    "src_browser",
    "src_system",
    "src_generic",
    "distinct_users",
    "distinct_hosts",
    "distinct_source_ips",
    "distinct_destination_ips",
    "distinct_processes",
    "distinct_file_paths",
    "distinct_evidence",
    "distinct_event_types",
    "high_severity_count",
    "critical_severity_count",
    "duplicate_count",
)

HIGH_SEVERITIES = {"High", "Critical"}


@dataclass
class FeatureWindow:
    window_start: datetime
    window_end: datetime
    features: dict[str, int] = field(default_factory=dict)
    events: list[ForensicEvent] = field(default_factory=list)

    def initials(self) -> dict[str, int]:
        return dict(self.features)


def _floor(value: datetime, minutes: int) -> datetime:
    bucket = (value.hour * 60 + value.minute) // minutes * minutes
    day_start = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start + timedelta(minutes=bucket)


class FeatureBuilder:
    """Groups normalized events into deterministic windows and counts features."""

    def __init__(self, window_minutes: int = WINDOW_MINUTES) -> None:
        self.window_minutes = window_minutes

    def build(self, events: list[ForensicEvent]) -> list[FeatureWindow]:
        """Return windows ordered chronologically; skips timestamp-less events."""
        buckets: dict[datetime, FeatureWindow] = {}
        for event in sorted(events, key=lambda e: (e.timestamp, e.id)):
            if event.timestamp is None:
                continue
            start = _floor(event.timestamp, self.window_minutes)
            window = buckets.setdefault(
                start,
                FeatureWindow(
                    window_start=start,
                    window_end=start + timedelta(minutes=self.window_minutes),
                ),
            )
            window.events.append(event)

        windows = [buckets[key] for key in sorted(buckets)]
        for window in windows:
            window.features = self._count_features(window.events)
        return windows

    @staticmethod
    def _count_features(events: list[ForensicEvent]) -> dict[str, int]:
        features: dict[str, int] = {name: 0 for name in FEATURE_NAMES}
        sources = Counter(event.source_type for event in events)
        for source in _SOURCE_TYPES:
            features[f"src_{source}"] = sources[source]
        features["distinct_users"] = len({e.user for e in events if e.user})
        features["distinct_hosts"] = len({e.host for e in events if e.host})
        features["distinct_source_ips"] = len({e.source_ip for e in events if e.source_ip})
        features["distinct_destination_ips"] = len(
            {e.destination_ip for e in events if e.destination_ip}
        )
        features["distinct_processes"] = len({e.process for e in events if e.process})
        features["distinct_file_paths"] = len({e.file_path for e in events if e.file_path})
        features["distinct_evidence"] = len({e.evidence_id for e in events})
        features["distinct_event_types"] = len(
            {e.event_type for e in events if e.event_type}
        )
        features["high_severity_count"] = sum(
            1 for e in events if e.severity in HIGH_SEVERITIES
        )
        features["critical_severity_count"] = sum(1 for e in events if e.severity == "Critical")
        features["duplicate_count"] = sum(
            1 for e in events if bool((e.extra or {}).get("duplicate"))
        )
        return features

    @staticmethod
    def feature_names() -> tuple[str, ...]:
        return FEATURE_NAMES