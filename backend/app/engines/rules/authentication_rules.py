"""Authentication rules (Phase 3).

Input: normalized authentication ForensicEvent rows of one case.

AUTH-001  Repeated failed logins (followed by success / burst)  High|Medium
AUTH-002  Authentication events from an external source IP        Medium
AUTH-003  Rapid login sequence from two source addresses          Low
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from app import config
from app.engines.rules.base import BaseRule, RuleResult, join_actions, span
from app.engines.rules.utils import external_ip
from app.models import ForensicEvent, SeverityLevel, SourceType


def _is_login(event: ForensicEvent) -> bool:
    return event.event_type.lower() == "login" or (event.action or "").lower() == "login"


def _auth_events(events: list[ForensicEvent]) -> list[ForensicEvent]:
    return [e for e in events if e.source_type == SourceType.AUTH.value]


class FailedLoginThenSuccessRule(BaseRule):
    rule_id = "AUTH-001"
    title = "Repeated failed logins followed by a successful login"
    description = (
        "Multiple failed authentication attempts precede a successful login for one user "
        "within the configured window, or a standalone burst of failed attempts is observed."
    )
    severity = SeverityLevel.HIGH
    enabled = True

    def __init__(self) -> None:
        from app.engines.rules.base import status_failure, status_success

        super().__init__()
        self._sf = status_failure
        self._ss = status_success
        self.min_failures = config.RULE_AUTH001_MIN_FAILURES
        self.window_minutes = config.RULE_AUTH001_WINDOW_MINUTES
        self.config = {
            "min_failures": self.min_failures,
            "window_minutes": self.window_minutes,
        }

    def evaluate(self, events: list[ForensicEvent]) -> list[RuleResult]:
        return list(self.findings(_auth_events(events)))

    def findings(self, events: list[ForensicEvent]) -> list[RuleResult]:
        by_user: dict[str, list[ForensicEvent]] = defaultdict(list)
        for event in events:
            if event.user and _is_login(event):
                by_user[event.user].append(event)

        results: list[RuleResult] = []
        for user in sorted(by_user):
            logins = _sorted_by_time(by_user[user])
            failures = [e for e in logins if self._sf(e)]
            successes = [e for e in logins if self._ss(e)]
            if not failures:
                continue

            window = timedelta(minutes=self.window_minutes)
            best_success: tuple[int, object, list[ForensicEvent]] | None = None
            for success in successes:
                preceding = [
                    f for f in failures
                    if f.timestamp is not None and success.timestamp is not None
                    and 0 <= (success.timestamp - f.timestamp).total_seconds()
                    and success.timestamp - f.timestamp <= window
                ]
                if len(preceding) < self.min_failures:
                    continue
                if best_success is None or len(preceding) > best_success[0]:
                    best_success = (len(preceding), success.timestamp, preceding + [success])

            if best_success is not None:
                count, _when, involved = best_success
                involved = _sorted_by_time(involved)
                start, end = span(involved)
                results.append(
                    self.make_result(
                        events=involved,
                        severity=SeverityLevel.HIGH,
                        explanation=(
                            f"{user} had {count} failed login attempts before a successful "
                            f"login within {self.window_minutes} minutes. This pattern is "
                            "potentially suspicious and requires investigator review."
                        ),
                        reasons=[f"{count} failed login(s) followed by a successful login."],
                        timestamp_start=start,
                        timestamp_end=end,
                    )
                )
                continue

            burst = self._burst(failures, window)
            if burst and len(burst) >= self.min_failures:
                start, end = span(burst)
                results.append(
                    self.make_result(
                        events=_sorted_by_time(burst),
                        severity=SeverityLevel.MEDIUM,
                        explanation=(
                            f"{user} had {len(burst)} failed login attempts within "
                            f"{self.window_minutes} minutes and no subsequent success was "
                            f"observed in the case dataset. Requires investigator review."
                        ),
                        reasons=[
                            f"{len(burst)} failed login(s) in a single window without success."
                        ],
                        timestamp_start=start,
                        timestamp_end=end,
                    )
                )
        return results

    @staticmethod
    def _burst(failures: list[ForensicEvent], window: timedelta) -> list[ForensicEvent]:
        attempts = [e for e in failures if e.timestamp is not None]
        if not attempts:
            return []
        best: list[ForensicEvent] = []
        for anchor in attempts:
            chain = [
                e for e in attempts
                if 0 <= (e.timestamp - anchor.timestamp).total_seconds()
                and e.timestamp - anchor.timestamp <= window
            ]
            if len(chain) > len(best):
                best = chain
        return best


class UnusualSourceIpRule(BaseRule):
    rule_id = "AUTH-002"
    title = "Authentication events from an unusual external source IP"
    description = (
        "Several authentication events originate from a source address outside the "
        "documented internal range of this case."
    )
    severity = SeverityLevel.MEDIUM
    enabled = True

    def __init__(self) -> None:
        super().__init__()
        self.min_external_logins = config.RULE_AUTH002_MIN_EXTERNAL_LOGINS
        self.config = {"min_external_logins": self.min_external_logins}

    def evaluate(self, events: list[ForensicEvent]) -> list[RuleResult]:
        by_ip: dict[str, list[ForensicEvent]] = defaultdict(list)
        for event in _auth_events(events):
            if event.source_ip and external_ip(event.source_ip):
                by_ip[event.source_ip].append(event)

        results: list[RuleResult] = []
        for ip in sorted(by_ip):
            involved = _sorted_by_time(by_ip[ip])
            if len(involved) < self.min_external_logins:
                continue
            start, end = span(involved)
            results.append(
                self.make_result(
                    events=involved,
                    explanation=(
                        f"{len(involved)} authentication events originate from external source "
                        f"IP {ip}. 'External' is defined as an address outside RFC1918 private "
                        f"space that is otherwise unobserved as a source in this case's dataset. "
                        "This is a statistical observation, not a claim of malicious activity; "
                        "requires investigator review."
                    ),
                    reasons=[
                        f"{len(involved)} authentication event(s) from {ip} "
                        f"({join_actions(involved)})."
                    ],
                    timestamp_start=start,
                    timestamp_end=end,
                )
            )
        return results


class ImprobableLoginSequenceRule(BaseRule):
    rule_id = "AUTH-003"
    title = "Rapid login sequence from two distinct source addresses"
    description = (
        "A single user logs in twice within a very short interval from different "
        "source addresses — an improbable-but-unproven pattern."
    )
    severity = SeverityLevel.LOW
    enabled = True

    def __init__(self) -> None:
        super().__init__()
        self.window_seconds = config.RULE_AUTH003_WINDOW_SECONDS
        self.config = {"window_seconds": self.window_seconds}

    def evaluate(self, events: list[ForensicEvent]) -> list[RuleResult]:
        by_user: dict[str, list[ForensicEvent]] = defaultdict(list)
        for event in _auth_events(events):
            if event.user and event.source_ip and _is_login(event):
                by_user[event.user].append(event)

        results: list[RuleResult] = []
        for user in sorted(by_user):
            logins = _sorted_by_time(by_user[user])
            picked: list[ForensicEvent] | None = None
            for first, second in zip(logins, logins[1:]):
                if not (first.timestamp and second.timestamp):
                    continue
                gap = (second.timestamp - first.timestamp).total_seconds()
                if 0 <= gap <= self.window_seconds and first.source_ip != second.source_ip:
                    picked = [first, second]
                    break
            if picked is None:
                continue
            start, end = span(picked)
            results.append(
                self.make_result(
                    events=picked,
                    explanation=(
                        f"{user} performed two logins within {self.window_seconds} seconds "
                        f"from different source addresses ({picked[0].source_ip} and "
                        f"{picked[1].source_ip}). Rapid multi-origin logins are an "
                        "improbable pattern and require investigator review."
                    ),
                    reasons=[
                        "Login events from two different source addresses within "
                        f"{self.window_seconds} seconds."
                    ],
                    timestamp_start=start,
                    timestamp_end=end,
                )
            )
        return results


def _sorted_by_time(events: list[ForensicEvent]) -> list[ForensicEvent]:
    return sorted(events, key=lambda e: (e.timestamp, e.id))