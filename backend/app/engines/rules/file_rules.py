"""File activity rules (Phase 3).

Input: normalized file_activity ForensicEvent rows of one case.

FILE-001  Mass file modifications in a short window   Medium|High
FILE-002  Rapid rename burst on one host/user         High
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from app import config
from app.engines.rules.base import BaseRule, RuleResult, events_in_window, span
from app.models import ForensicEvent, SeverityLevel, SourceType

# Actions that change file contents or presence (from the documented
# file_activity vocabulary: open/write/delete/rename/copy).
MODIFY_ACTIONS = frozenset({"write", "delete", "create", "modify", "copy", "append", "truncate"})
RENAME_ACTIONS = frozenset({"rename", "rename_file", "move"})


def _file_events(events: list[ForensicEvent]) -> list[ForensicEvent]:
    return [e for e in events if e.source_type == SourceType.FILE.value and e.file_path]


def _group_key(event: ForensicEvent) -> tuple[str, str]:
    return (event.host or "", event.user or "")


def _scope_label(key: tuple[str, str]) -> str:
    host, user = key
    parts = []
    if host:
        parts.append(f"host {host}")
    if user:
        parts.append(f"user {user}")
    return " / ".join(parts) if parts else "unattributed scope"


class MassFileModificationRule(BaseRule):
    rule_id = "FILE-001"
    title = "Mass file modifications in a short window"
    description = (
        "A high density of file-modifying operations (write/delete/copy) for one "
        "host and user inside the configured window."
    )
    severity = SeverityLevel.MEDIUM

    def __init__(self) -> None:
        super().__init__()
        self.min_modifications = config.RULE_FILE001_MIN_MODIFICATIONS
        self.window_minutes = config.RULE_FILE001_WINDOW_MINUTES
        self.high_min = config.RULE_FILE001_HIGH_MIN
        self.config = {
            "min_modifications": self.min_modifications,
            "window_minutes": self.window_minutes,
            "high_min": self.high_min,
        }

    def evaluate(self, events: list[ForensicEvent]) -> list[RuleResult]:
        groups: dict[tuple[str, str], list[ForensicEvent]] = defaultdict(list)
        for event in _file_events(events):
            if (event.action or "").lower() in MODIFY_ACTIONS:
                groups[_group_key(event)].append(event)

        results: list[RuleResult] = []
        for key in sorted(groups):
            chain = events_in_window(groups[key], self.window_minutes)
            if len(chain) < self.min_modifications:
                continue
            high = len(chain) >= self.high_min
            severity = SeverityLevel.HIGH if high else SeverityLevel.MEDIUM
            files = sorted({e.file_path for e in chain if e.file_path})
            start, end = span(chain)
            results.append(
                self.make_result(
                    events=chain,
                    severity=severity,
                    explanation=(
                        f"{len(chain)} file modification events for "
                        f"{_scope_label(key)} within {self.window_minutes} minutes, "
                        f"touching {len(files)} distinct file path(s). High-volume file "
                        "activity is a potentially suspicious pattern that requires "
                        "investigator review."
                    ),
                    reasons=[
                        f"{len(chain)} file modification(s) "
                        f"(>= {self.min_modifications}) in a "
                        f"{self.window_minutes}-minute window."
                    ]
                    + ([f"Volume reached the high threshold ({self.high_min})."] if high else [])
                    + [f"Files involved: {', '.join(files[:5])}{'…' if len(files) > 5 else ''}."],
                    timestamp_start=start,
                    timestamp_end=end,
                )
            )
        return results


class MassRenameRule(BaseRule):
    rule_id = "FILE-002"
    title = "Rapid file rename burst"
    description = (
        "Several file rename operations for one host and user inside the "
        "configured window — a pattern often seen in mass-rename activity."
    )
    severity = SeverityLevel.HIGH

    def __init__(self) -> None:
        super().__init__()
        self.min_renames = config.RULE_FILE002_MIN_RENAMES
        self.window_minutes = config.RULE_FILE002_WINDOW_MINUTES
        self.config = {
            "min_renames": self.min_renames,
            "window_minutes": self.window_minutes,
        }

    def evaluate(self, events: list[ForensicEvent]) -> list[RuleResult]:
        groups: dict[tuple[str, str], list[ForensicEvent]] = defaultdict(list)
        for event in _file_events(events):
            if (event.action or "").lower() in RENAME_ACTIONS:
                groups[_group_key(event)].append(event)

        results: list[RuleResult] = []
        for key in sorted(groups):
            chain = events_in_window(groups[key], self.window_minutes)
            if len(chain) < self.min_renames:
                continue
            files = sorted({e.file_path for e in chain if e.file_path})
            start, end = span(chain)
            results.append(
                self.make_result(
                    events=chain,
                    explanation=(
                        f"{len(chain)} file rename events for {_scope_label(key)} "
                        f"within {self.window_minutes} minutes, affecting "
                        f"{len(files)} distinct path(s). Rapid rename activity is "
                        "potentially suspicious and requires investigator review."
                    ),
                    reasons=[
                        f"{len(chain)} rename(s) (>= {self.min_renames}) within "
                        f"{self.window_minutes} minutes."
                    ]
                    + [f"Paths involved: {', '.join(files[:5])}{'…' if len(files) > 5 else ''}."],
                    timestamp_start=start,
                    timestamp_end=end,
                )
            )
        return results
