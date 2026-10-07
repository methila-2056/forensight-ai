"""Rule helpers (Phase 3): external-IP classification and scripting indicators.

The external-IP helper reflects IANA special-purpose allocations only — it is
a documented baseline for "unusual source/destination" wording, never a claim
that an address is malicious.
"""

from __future__ import annotations

import ipaddress

from app.models import ForensicEvent

SCRIPTING_PROCESSES: frozenset[str] = frozenset(
    {
        "powershell.exe", "powershell", "pwsh.exe", "cmd.exe", "wscript.exe",
        "cscript.exe", "mshta.exe", "regsvr32.exe", "rundll32.exe",
        "powershell_ise.exe", "bitsadmin.exe", "certutil.exe", "msbuild.exe",
    }
)

SCRIPTING_TOKENS: tuple[str, ...] = (
    "-nop", "-w hidden", "-enc ", " -e ", "encodedcommand", "frombase64",
    "downloadstring", "iex(", "invoke-expression", "/c ", "/k ",
)


def external_ip(value: str | None) -> bool:
    """True when an address is neither private nor special-purpose (IANA)."""
    if not value:
        return False
    try:
        parsed = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    return not (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    )


def command_line(event: ForensicEvent) -> str:
    return str((event.extra or {}).get("command_line", "") or "")


def is_scripting_process(process: str | None) -> bool:
    return bool(process and process.strip().lower() in SCRIPTING_PROCESSES)


def has_scripting_token(command_line: str) -> bool:
    low = command_line.lower()
    return any(token in low for token in SCRIPTING_TOKENS)