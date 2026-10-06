"""Timestamp normalisation (Phase 2, Architecture v1.1 §8).

Supported formats, tried in order:

1. Unix epoch seconds (10 digits) or milliseconds (13 digits)
2. ``YYYY-MM-DD HH:MM:SS[.fff]`` (also with a space separator)
3. ``YYYY/MM/DD HH:MM:SS``
4. Apache access-log style ``DD/Mon/YYYY:HH:MM:SS`` with optional offset
5. US format ``MM/DD/YYYY HH:MM:SS``
6. Date-only ``YYYY-MM-DD`` (midnight assumed)
7. ISO 8601 (``T`` separator, optional fractional seconds, optional offset / ``Z``)

Timezone assumptions (documented): timestamps that carry an explicit offset are
converted to UTC and the source offset is recorded in ``tz_note``. Timestamps
without any timezone information are **assumed to be UTC** and flagged as such
in ``tz_note`` so an investigator can see the assumption. Values that cannot be
parsed are never repaired or guessed — the record is rejected with the exact
reason and the original value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

TZ_ASSUMED_UTC = "assumed UTC (no timezone in source)"
TZ_EPOCH_UTC = "UTC (epoch value)"
TZ_CONVERTED = "UTC (source offset converted)"

_EPOCH_SECONDS = re.compile(r"^\d{10}$")
_EPOCH_MILLIS = re.compile(r"^\d{13}$")
_APACHE = re.compile(
    r"^(?P<stamp>\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2})(?:\s*(?P<offset>[+-]\d{4}))?$"
)
_STRFTIME_PATTERNS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S.%f",
    "%Y/%m/%d %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%d",
)


@dataclass(frozen=True)
class TimestampResult:
    value: datetime | None      # naive UTC
    tz_note: str | None
    reason: str | None          # set only when the value could not be parsed

    @property
    def ok(self) -> bool:
        return self.value is not None


def _from_epoch(digits: str) -> datetime:
    seconds = int(digits) / 1000.0 if len(digits) == 13 else float(int(digits))
    return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)


def _assume_or_convert(parsed: datetime) -> tuple[datetime, str]:
    if parsed.tzinfo is not None:
        offset = parsed.strftime("%z")
        converted = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        if offset in ("+0000", ""):
            return converted, "UTC (source offset +0000)"
        return converted, f"{TZ_CONVERTED} from {offset}"
    return parsed, TZ_ASSUMED_UTC


def parse_timestamp(raw: object) -> TimestampResult:
    """Parse a timestamp value into naive UTC with a documented tz note."""
    if raw is None:
        return TimestampResult(None, None, "missing timestamp value")
    text = str(raw).strip()
    if not text:
        return TimestampResult(None, None, "missing timestamp value")

    # 1. Epoch seconds / milliseconds.
    if _EPOCH_SECONDS.match(text):
        return TimestampResult(_from_epoch(text), TZ_EPOCH_UTC, None)
    if _EPOCH_MILLIS.match(text):
        return TimestampResult(_from_epoch(text), TZ_EPOCH_UTC, None)

    # 2-5. Common textual formats.
    candidate = text.strip("[]") if text.startswith("[") and text.endswith("]") else text
    match = _APACHE.match(candidate)
    if match:
        # Apache access-log style: keep the explicit source offset.
        joined = f"{match.group('stamp')} {match.group('offset') or '+0000'}"
        try:
            parsed = datetime.strptime(joined, "%d/%b/%Y:%H:%M:%S %z")
        except ValueError:
            parsed = None
        if parsed is not None:
            value, note = _assume_or_convert(parsed)
            return TimestampResult(value, note, None)

    for pattern in _STRFTIME_PATTERNS:
        try:
            parsed = datetime.strptime(candidate, pattern)
        except ValueError:
            continue
        value, note = _assume_or_convert(parsed)
        return TimestampResult(value, note, None)

    # 7. ISO 8601 (handles 'T', fractional seconds, 'Z', numeric offsets).
    iso_text = text.replace("Z", "+00:00") if text.endswith(("Z", "z")) else text
    if " " in iso_text:
        iso_text = iso_text.replace(" ", "T", 1)
        iso_text = re.sub(r"\s+(?=[+-]\d{2}:\d{2}$)", "", iso_text)
    try:
        parsed = datetime.fromisoformat(iso_text)
    except ValueError:
        parsed = None
    if parsed is not None:
        value, note = _assume_or_convert(parsed)
        return TimestampResult(value, note, None)

    return TimestampResult(
        None,
        None,
        f"invalid timestamp format: {text[:64]!r}",
    )
