"""Process activity rules (Phase 3).

Input: normalized process ForensicEvent rows of one case.

PROC-001  Scripting/interpreter process execution (e.g. PowerShell)   Medium|High
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.engines.rules.base import BaseRule, RuleResult, span
from app.engines.rules.utils import command_line, has_scripting_token, is_scripting_process
from app.models import ForensicEvent, SeverityLevel, SourceType

# Execution families that warrant review when observed in forensic evidence.
INTERPRETER_PROCESSES = frozenset({"python.exe", "python3", "perl.exe", "ruby.exe", "csharp"})


class ScriptingProcessRule(BaseRule):
    rule_id = "PROC-001"
    title = "Scripting or interpreter process execution"
    description = (
        "A scripting host or command interpreter (PowerShell, cmd, wscript, "
        "certutil, …) was executed. Severity rises when the command line carries "
        "evasion indicators (encoded commands, hidden windows, downloaders)."
    )
    severity = SeverityLevel.MEDIUM

    def __init__(self) -> None:
        super().__init__()
        self.config = {"indicator_source": "process name + command line tokens"}

    def evaluate(self, events: list[ForensicEvent]) -> list[RuleResult]:
        groups: dict[tuple[str, str], list[tuple[ForensicEvent, tuple[str, ...]]]] = defaultdict(list)
        for event in events:
            if event.source_type != SourceType.PROCESS.value:
                continue
            process = (event.process or "").strip()
            if not process:
                continue
            line = command_line(event)
            tokens = tuple(
                token
                for token in ("-nop", "-w hidden", "enc", "encodedcommand", "frombase64",
                              "downloadstring", "iex(", "invoke-expression")
                if token in line.lower()
            )
            if is_scripting_process(process) or process.lower() in INTERPRETER_PROCESSES or tokens:
                key = (event.host or "", event.user or "")
                groups[key].append((event, tokens))

        results: list[RuleResult] = []
        for key in sorted(groups):
            pairs = sorted(
                groups[key],
                key=lambda pair: (pair[0].timestamp or datetime.min, pair[0].id),
            )
            involved = [event for event, _ in pairs]
            token_hits = sorted({token for _, tokens in pairs for token in tokens})
            processes = sorted({(e.process or "").lower() for e in involved})
            high = bool(token_hits)
            severity = SeverityLevel.HIGH if high else SeverityLevel.MEDIUM
            host = key[0] or "unknown host"
            user = key[1] or "unknown user"
            start, end = span(involved)
            reasons = [f"Process(es) observed: {', '.join(processes)} on {host} (user {user})."]
            if token_hits:
                reasons.append(
                    "Command-line indicators present: "
                    + ", ".join(token_hits)
                    + " — elevated severity."
                )
            results.append(
                self.make_result(
                    events=involved,
                    severity=severity,
                    explanation=(
                        f"{len(involved)} scripting/interpreter process event(s) for user "
                        f"{user} on {host}"
                        + (
                            f" carrying evasion indicators ({', '.join(token_hits)})."
                            if token_hits
                            else "."
                        )
                        + " Script execution is common in administration but is also used to "
                        "evade controls — potentially suspicious and requires investigator "
                        "review."
                    ),
                    reasons=reasons,
                    timestamp_start=start,
                    timestamp_end=end,
                )
            )
        return results
