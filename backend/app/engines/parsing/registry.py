"""Parser detection and dispatch (Phase 2, Architecture v1.1 §8).

Detection considers, in order:

1. content structure (JSON-looking content routes to the JSON parser)
2. file extension
3. the available columns/fields (normalizer signatures)
4. the explicit evidence-type metadata as a tie-break hint — content wins

If the format cannot be identified (unsupported type, no header, no timestamp
field), :class:`UnknownFormatError` is raised so the pipeline records a
structured processing error instead of silently classifying the evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.engines.parsing.base import ParseBatch, UnknownFormatError
from app.engines.parsing.csv_parser import CsvParser, decode_text
from app.engines.parsing.json_parser import JsonParser, looks_like_json
from app.engines.parsing.normalizer import (
    GenericNormalizer,
    Normalizer,
    canonicalize,
    select_normalizer,
)

_CSV_EXTENSIONS = {".csv", ".txt", ".log"}
_SAMPLE_BYTES = 65_536


@dataclass
class ParseOutcome:
    parser_name: str
    normalizer: Normalizer
    source_type: str
    batch: ParseBatch
    warnings: list[str] = field(default_factory=list)


def _detect_parser(data: bytes, filename: str):
    sample_text = decode_text(data[:_SAMPLE_BYTES], warnings=[])
    extension = Path(filename or "").suffix.lower()
    first_line = sample_text.splitlines()[0] if sample_text else ""

    if looks_like_json(sample_text):
        return JsonParser()
    if extension in _CSV_EXTENSIONS or "," in first_line:
        return CsvParser()
    raise UnknownFormatError(
        f"unsupported evidence format for {extension or 'unknown'} file; "
        "expected CSV or JSON structured records",
        hints=[
            "supported inputs: CSV with a header row, or JSON records",
            "ZIP archives are processed in a later phase",
        ],
    )


def parse_evidence(
    data: bytes,
    *,
    filename: str,
    declared_type: str | None,
    max_records: int,
) -> ParseOutcome:
    """Decode evidence and select its normalizer. Never silently classifies."""
    if not data.strip():
        raise UnknownFormatError("evidence file is empty")

    parser = _detect_parser(data, filename)
    batch = parser.parse(data)
    warnings = list(batch.warnings)

    if not batch.columns:
        raise UnknownFormatError(
            "evidence header could not be read; no usable column names found"
        )

    columns = set(canonicalize({name: "" for name in batch.columns}))
    normalizer = select_normalizer(columns, declared_type)

    if len(batch.records) > max_records:
        dropped = len(batch.records) - max_records
        batch.records = batch.records[:max_records]
        warnings.append(
            f"record limit of {max_records} reached; {dropped} remaining "
            "records were not processed in this run"
        )

    if not batch.records:
        warnings.append("no records found in evidence file")

    return ParseOutcome(
        parser_name=parser.name,
        normalizer=normalizer,
        source_type=normalizer.source_type,
        batch=batch,
        warnings=warnings,
    )


__all__ = ["ParseOutcome", "parse_evidence", "UnknownFormatError", "GenericNormalizer"]
