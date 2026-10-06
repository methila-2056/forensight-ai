"""Source-specific normalizers (Phase 2, Architecture v1.1 §8).

Responsibilities:

* detect which source type a set of columns represents (used by the registry
  together with the declared evidence type — content wins over declaration)
* map aliased source fields onto the common forensic event schema
* validate required fields and timestamps, returning a reject reason instead
  of guessing
* preserve source-specific fields (status, port, protocol, url, ...) in
  ``metadata``
* normalise severity vocabulary (``error`` -> High, ...); values that are not
  in the vocabulary become ``None`` — nothing is invented

Fields absent from the source evidence stay empty/None.
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.engines.parsing.base import NormalizationOutcome
from app.engines.parsing.timestamps import parse_timestamp

# ---------------------------------------------------------------------------
# Field aliases: canonical name -> alternative column names (already
# normalised: lowercase, non-alphanumerics collapsed to '_').
# ---------------------------------------------------------------------------

ALIAS_GROUPS: dict[str, set[str]] = {
    "timestamp": {
        "timestamp", "ts", "time", "datetime", "date", "event_time",
        "event_timestamp", "occurred_at", "log_time", "datetime_iso",
    },
    "user": {"user", "username", "user_name", "account", "account_name", "usr"},
    "host": {"host", "hostname", "host_name", "computer", "machine", "device", "node"},
    "source_ip": {
        "source_ip", "ip", "src_ip", "client_ip", "source_address",
        "src_address", "src_addr", "ip_address",
    },
    "destination_ip": {
        "destination_ip", "dst_ip", "dest_ip", "remote_ip", "daddr",
        "target_ip", "destination_address",
    },
    "destination_port": {"destination_port", "dst_port", "dest_port", "dport", "target_port", "port"},
    "protocol": {"protocol", "proto", "ip_protocol"},
    "process": {
        "process", "process_name", "processname", "image", "exe", "proc",
        "program", "process_path", "process_executable",
    },
    "parent_process": {"parent_process", "parent", "parent_name", "parent_image", "parent_process_name"},
    "command_line": {"command_line", "cmdline", "command", "cmd", "commandline", "process_command", "process_args"},
    "file_path": {"file_path", "path", "filepath", "file", "filename", "file_name", "target_file"},
    "action": {"action", "operation", "op", "activity", "event_action", "action_name", "act"},
    "status": {"status", "result", "outcome", "success", "disposition"},
    "event_type": {"event_type", "event", "event_name", "eventtype", "log_type", "type"},
    "message": {"message", "msg", "log_message", "description"},
    "severity": {"severity", "level", "priority", "sev", "log_level"},
    "url": {"url", "uri", "link", "page_url"},
    "domain": {"domain", "fqdn", "site"},
}

_CANONICAL_BY_ALIAS: dict[str, str] = {
    alias: canonical for canonical, aliases in ALIAS_GROUPS.items() for alias in aliases
}

# Canonical fields consumed by the common schema (never copied to metadata).
_COMMON_CONSUMED: frozenset[str] = frozenset(
    {"timestamp", "source_type", "event_type", "user", "host", "source_ip",
     "destination_ip", "process", "file_path", "action", "severity"}
)

# Deterministic severity vocabulary (documented; unknown values -> None).
SEVERITY_VOCABULARY: dict[str, str] = {
    "low": "Low",
    "info": "Low",
    "informational": "Low",
    "notice": "Low",
    "medium": "Medium",
    "moderate": "Medium",
    "warn": "Medium",
    "warning": "Medium",
    "high": "High",
    "error": "High",
    "err": "High",
    "critical": "Critical",
    "crit": "Critical",
    "fatal": "Critical",
    "severe": "Critical",
}


def canonicalize(fields: dict[str, str]) -> dict[str, str]:
    """Apply the alias map; first non-empty value wins on collisions."""
    out: dict[str, str] = {}
    for key, value in fields.items():
        canonical = _CANONICAL_BY_ALIAS.get(key, key)
        if canonical not in out or (not out[canonical] and value):
            out[canonical] = value
    return out


def map_severity(raw: str | None) -> str | None:
    if not raw:
        return None
    return SEVERITY_VOCABULARY.get(raw.strip().lower())


def _or_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


class Normalizer:
    """Maps canonicalised fields onto the common forensic event schema."""

    name: str = "generic"
    source_type: str = "generic"
    signature: frozenset[str] = frozenset()
    exclusive: frozenset[str] = frozenset()
    required_any: tuple[tuple[str, ...], ...] = ()
    order: int = 99

    def score(self, columns: set[str], declared: str | None) -> float:
        if not self.signature:
            return 0.0
        hits = len(self.signature & columns)
        value = 100.0 * hits / len(self.signature)
        if declared == self.source_type:
            value += 30.0
        value += 15.0 * len(self.exclusive & columns)
        return value

    def normalize(self, fields: dict[str, str], row_index: int) -> NormalizationOutcome:
        canon = canonicalize(fields)

        timestamp_raw = canon.get("timestamp", "")
        ts = parse_timestamp(timestamp_raw)
        if not ts.ok:
            return NormalizationOutcome(reject_reason=ts.reason or "invalid timestamp format")

        for group in self.required_any:
            if not any((canon.get(name) or "").strip() for name in group):
                return NormalizationOutcome(
                    reject_reason=f"missing required field: {' or '.join(group)}"
                )

        common: dict = {
            "timestamp": ts.value,
            "tz_note": ts.tz_note,
            "source_type": self.source_type,
            "event_type": (canon.get("event_type") or canon.get("action") or "").strip(),
            "user": _or_none(canon.get("user")),
            "host": _or_none(canon.get("host")),
            "source_ip": _or_none(canon.get("source_ip")),
            "destination_ip": _or_none(canon.get("destination_ip")),
            "process": _or_none(canon.get("process")),
            "file_path": _or_none(canon.get("file_path")),
            "action": _or_none(canon.get("action")),
            "severity": map_severity(canon.get("severity")),
        }

        # Every canonical field not consumed by the common schema is preserved
        # verbatim (status, port, protocol, url, service, pid, ...).
        metadata: dict = {"normalizer": self.name}
        for key, value in canon.items():
            if key in _COMMON_CONSUMED or key == "normalizer":
                continue
            text = _or_none(value)
            if text is not None:
                metadata[key] = text

        self._post_process(canon, common, metadata)
        return NormalizationOutcome(common=common, metadata=metadata)

    def _post_process(
        self,
        canon: dict[str, str],
        common: dict,
        metadata: dict,
    ) -> None:
        """Hook for source-specific refinements."""


class AuthenticationNormalizer(Normalizer):
    name = "authentication"
    source_type = "authentication"
    signature = frozenset({"timestamp", "user", "action", "status", "source_ip", "host"})
    exclusive = frozenset({"status"})
    required_any = (("user",),)
    order = 1


class FileActivityNormalizer(Normalizer):
    name = "file_activity"
    source_type = "file_activity"
    signature = frozenset({"timestamp", "user", "host", "file_path", "action", "process"})
    exclusive = frozenset({"file_path"})
    required_any = (("file_path",),)
    order = 2


class ProcessNormalizer(Normalizer):
    name = "process"
    source_type = "process"
    signature = frozenset({"timestamp", "user", "host", "process", "command_line", "action"})
    exclusive = frozenset({"command_line", "parent_process"})
    required_any = (("process",),)
    order = 3


class NetworkNormalizer(Normalizer):
    name = "network"
    source_type = "network"
    signature = frozenset(
        {"timestamp", "host", "process", "source_ip", "destination_ip",
         "destination_port", "protocol"}
    )
    exclusive = frozenset({"destination_ip", "destination_port", "protocol"})
    required_any = (("destination_ip", "destination_port"),)
    order = 4


class BrowserNormalizer(Normalizer):
    name = "browser"
    source_type = "browser"
    signature = frozenset({"timestamp", "user", "url", "domain", "action", "host"})
    exclusive = frozenset({"url", "domain"})
    required_any = (("url", "domain"),)
    order = 5

    def _post_process(self, canon, common, metadata) -> None:
        # Derive the domain from the URL when the source only provides a URL.
        if not metadata.get("domain") and metadata.get("url"):
            try:
                parsed = urlparse(metadata["url"])
                if parsed.netloc:
                    metadata["domain"] = parsed.netloc
            except ValueError:  # pragma: no cover - defensive
                pass


class SystemLogNormalizer(Normalizer):
    name = "system"
    source_type = "system"
    signature = frozenset({"timestamp", "event_type", "message", "severity", "host"})
    exclusive = frozenset({"message"})
    required_any = (("event_type", "message"),)
    order = 6


class GenericNormalizer(Normalizer):
    name = "generic"
    source_type = "generic"
    signature = frozenset({"timestamp"})
    exclusive = frozenset()
    required_any = ()
    order = 99


# Ordered list of specific (non-generic) normalizers; ties are broken by order.
SPECIFIC_NORMALIZERS: tuple[Normalizer, ...] = (
    AuthenticationNormalizer(),
    FileActivityNormalizer(),
    ProcessNormalizer(),
    NetworkNormalizer(),
    BrowserNormalizer(),
    SystemLogNormalizer(),
)

GENERIC_NORMALIZER = GenericNormalizer()

DETECTION_THRESHOLD = 50.0


def has_timestamp_column(columns: set[str]) -> bool:
    return bool(ALIAS_GROUPS["timestamp"] & columns)


def select_normalizer(columns: set[str], declared: str | None) -> Normalizer:
    """Pick the normalizer for a record set.

    Content structure wins; the declared evidence type breaks ties. If the
    evidence cannot be attributed to a specific source type with confidence,
    the generic normalizer maps whatever fields exist — the format itself
    (CSV/JSON with a timestamp) has already been identified by the registry.
    """
    if not has_timestamp_column(columns):
        from app.engines.parsing.base import UnknownFormatError

        raise UnknownFormatError(
            "evidence format not recognised: no timestamp field detected "
            "(expected one of: timestamp, time, datetime, date, ts, @timestamp)",
            hints=["rename the timestamp column to 'timestamp' or re-export the log with timestamps"],
        )

    ranked = sorted(
        SPECIFIC_NORMALIZERS,
        key=lambda normalizer: (normalizer.score(columns, declared), -normalizer.order),
        reverse=True,
    )
    best = ranked[0]
    best_score = best.score(columns, declared)
    if best_score < DETECTION_THRESHOLD:
        return GENERIC_NORMALIZER

    if len(ranked) > 1:
        runner_up = ranked[1]
        if (
            best_score == runner_up.score(columns, declared)
            and not (best.exclusive & columns)
            and not (runner_up.exclusive & columns)
            and declared not in (best.source_type, runner_up.source_type)
        ):
            # Ambiguous content without exclusive-column evidence: do not
            # pretend to know the source type.
            return GENERIC_NORMALIZER
    return best
