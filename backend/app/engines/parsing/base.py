"""Parser and normalizer contracts (Phase 2).

Design: *structure decoding* (parsers) is separated from *field mapping*
(normalizers) so that new formats can be added without touching the
processing pipeline:

* **Parsers** turn raw bytes into :class:`ParsedRecord` objects (row index,
  canonicalised fields, safe original representation). They never discard a
  malformed row — a row that cannot be decoded is returned with
  ``parse_error`` set so the pipeline can retain it as a rejected record.
* **Normalizers** map a decoded record onto the common forensic event schema,
  preserving source-specific fields in ``metadata``. They either return a
  complete mapping or a ``reject_reason``.

Nothing here executes, interprets, or evaluates evidence content: evidence is
treated purely as data.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# Original record representations are stored for investigator review; they are
# capped so a single hostile row cannot bloat the database.
MAX_RAW_RECORD_CHARS = 64_000


class UnknownFormatError(Exception):
    """No parser could confidently identify the evidence format.

    Raised instead of silently classifying unknown evidence; the pipeline
    converts this into a FAILED processing run with a structured error.
    """

    def __init__(self, message: str, hints: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hints = hints or []


def cap_text(value: str, limit: int = MAX_RAW_RECORD_CHARS) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "…[truncated]"


def safe_record_repr(value: object) -> str:
    """JSON representation of the original record, capped and never executed."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        text = str(value)
    return cap_text(text)


@dataclass
class ParsedRecord:
    """One decoded record from the source evidence."""

    row_index: int                     # 1-based record number (header excluded)
    fields: dict[str, str] = field(default_factory=dict)  # canonical column -> raw value
    raw: str = ""                      # safe original representation
    parse_error: str | None = None     # structural failure (retained, never dropped)


@dataclass
class ParseBatch:
    records: list[ParsedRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)  # normalised header names


@dataclass
class NormalizationOutcome:
    """Result of mapping one record onto the common forensic event schema."""

    common: dict = field(default_factory=dict)   # common schema fields (timestamp, user, ...)
    metadata: dict = field(default_factory=dict) # source-specific preserved fields
    reject_reason: str | None = None


class EvidenceParser(ABC):
    """Structure decoder: bytes -> ParsedRecord list."""

    name: str = "parser"

    @abstractmethod
    def parse(self, data: bytes) -> ParseBatch:
        """Decode the evidence into records. Must not raise on bad rows."""
