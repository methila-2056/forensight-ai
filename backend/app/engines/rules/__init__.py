"""Rule registry (Phase 3).

``all_rules()`` instantiates the full catalog in a fixed order; ``run_rules``
evaluates them against the case's normalized events, applying the per-rule
finding cap and collecting a configuration snapshot for the analysis run.
"""

from __future__ import annotations

from datetime import datetime

from app import config
from app.engines.rules.authentication_rules import (
    FailedLoginThenSuccessRule,
    ImprobableLoginSequenceRule,
    UnusualSourceIpRule,
)
from app.engines.rules.base import BaseRule, RuleResult
from app.engines.rules.file_rules import MassFileModificationRule, MassRenameRule
from app.engines.rules.network_rules import ExternalConnectionAfterProcessRule
from app.engines.rules.process_rules import ScriptingProcessRule
from app.models import ForensicEvent

RULE_CLASSES: tuple[type[BaseRule], ...] = (
    FailedLoginThenSuccessRule,      # AUTH-001
    UnusualSourceIpRule,             # AUTH-002
    ImprobableLoginSequenceRule,     # AUTH-003
    ScriptingProcessRule,            # PROC-001
    MassFileModificationRule,        # FILE-001
    MassRenameRule,                  # FILE-002
    ExternalConnectionAfterProcessRule,  # NET-001
)


def all_rules() -> list[BaseRule]:
    return [rule_class() for rule_class in RULE_CLASSES]


def run_rules(
    events: list[ForensicEvent],
    max_per_rule: int | None = None,
) -> tuple[list[RuleResult], list[dict]]:
    """Evaluate every enabled rule.

    Returns (results, config_snapshots). Results are capped at
    ``max_per_rule`` per rule and sorted chronologically for determinism.
    """
    cap = config.RULE_MAX_FINDINGS_PER_RULE if max_per_rule is None else max_per_rule
    results: list[RuleResult] = []
    snapshots: list[dict] = []
    for rule in all_rules():
        snapshots.append(rule.config_snapshot())
        if not rule.enabled:
            continue
        found = rule.evaluate(events)
        found.sort(key=lambda r: (r.timestamp_start or datetime.min, r.rule_id))
        results.extend(found[:cap])
    results.sort(key=lambda r: (r.timestamp_start or datetime.min, r.rule_id))
    return results, snapshots
