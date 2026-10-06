"""Evidence parsing package (Phase 2).

Public entry point: :func:`app.engines.parsing.registry.parse_evidence`.
"""

from app.engines.parsing.base import (
    NormalizationOutcome,
    ParsedRecord,
    ParseBatch,
    UnknownFormatError,
)
from app.engines.parsing.registry import ParseOutcome, parse_evidence

__all__ = [
    "NormalizationOutcome",
    "ParsedRecord",
    "ParseBatch",
    "ParseOutcome",
    "UnknownFormatError",
    "parse_evidence",
]
