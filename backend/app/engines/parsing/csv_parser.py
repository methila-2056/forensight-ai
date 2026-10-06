"""CSV structure decoder (Phase 2).

Responsibilities (structure only — field mapping lives in normalizers):

* decode bytes with UTF-8 first and reasonable fallbacks (warnings recorded)
* detect and normalise the header row
* iterate rows with 1-based record numbers (header excluded)
* retain structurally malformed rows as records with ``parse_error`` set —
  malformed rows are never silently dropped
* treat blank lines as absent (not as records)

Evidence content is read as data only; nothing is executed or evaluated.
"""

from __future__ import annotations

import csv
import io
import json
import re

from app.engines.parsing.base import (
    EvidenceParser,
    ParsedRecord,
    ParseBatch,
    cap_text,
)

# Guard against pathological input fields (resource limit, not a data policy).
csv.field_size_limit(1_000_000)

_COLUMN_CLEAN = re.compile(r"[^a-z0-9]+")

_ENCODING_CHAIN: tuple[str, ...] = ("utf-8-sig", "cp1252", "latin-1")


def normalize_column(name: str) -> str:
    """Canonical column name: 'Source IP' -> 'source_ip', '@timestamp' -> 'timestamp'."""
    return _COLUMN_CLEAN.sub("_", (name or "").strip().lower()).strip("_")


def decode_text(data: bytes, warnings: list[str]) -> str:
    """Decode with UTF-8 first, then reasonable single-byte fallbacks."""
    for index, encoding in enumerate(_ENCODING_CHAIN):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if index > 0:
            warnings.append(
                f"file was not valid UTF-8; decoded using {encoding} fallback"
            )
        return text
    # latin-1 decodes any byte sequence; unreachable, kept for clarity.
    return data.decode("latin-1", errors="replace")  # pragma: no cover


class CsvParser(EvidenceParser):
    name = "csv"

    def parse(self, data: bytes) -> ParseBatch:
        batch = ParseBatch()
        text = decode_text(data, batch.warnings)
        reader = csv.reader(io.StringIO(text))

        try:
            header = next(reader)
        except StopIteration:
            batch.warnings.append("file contains no header row")
            return batch

        columns = [normalize_column(cell) for cell in header]
        if not any(columns):
            batch.warnings.append("header row contains no usable column names")
            return batch
        batch.columns = columns

        row_index = 0
        for raw_row in reader:
            if not raw_row or all(not cell.strip() for cell in raw_row):
                continue  # blank line: not a record
            row_index += 1

            if len(raw_row) != len(columns):
                batch.records.append(
                    ParsedRecord(
                        row_index=row_index,
                        fields={},
                        raw=cap_text(json.dumps(raw_row, ensure_ascii=False)),
                        parse_error=(
                            f"malformed row: expected {len(columns)} columns, "
                            f"got {len(raw_row)}"
                        ),
                    )
                )
                continue

            original = {
                columns[i] or f"column_{i}": raw_row[i].strip()
                for i in range(len(columns))
            }
            batch.records.append(
                ParsedRecord(
                    row_index=row_index,
                    fields=original,
                    raw=cap_text(
                        json.dumps(
                            dict(zip(header, raw_row)), ensure_ascii=False
                        )
                    ),
                )
            )
        return batch
