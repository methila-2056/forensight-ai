"""JSON structure decoder (Phase 2).

Supported shapes:

* a JSON array of objects
* a single JSON object (one record, or a wrapper holding the record list)
* common event-list wrappers: ``events``, ``records``, ``items``, ``data``,
  ``logs``

Elements that are not objects are retained as records with ``parse_error``
so they appear in the rejected-record log instead of disappearing.
Decoded values are converted to strings for uniform field mapping; no
deserialisation beyond ``json.loads`` is performed (no object construction,
no code execution).
"""

from __future__ import annotations

import json

from app.engines.parsing.base import (
    EvidenceParser,
    ParsedRecord,
    ParseBatch,
    UnknownFormatError,
    safe_record_repr,
)
from app.engines.parsing.csv_parser import decode_text, normalize_column

_LIST_KEYS = ("events", "records", "items", "data", "logs")


def looks_like_json(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _flatten(record: dict, prefix: str = "") -> dict[str, str]:
    """Flatten one level of nested objects into canonical dotted keys."""
    fields: dict[str, str] = {}
    for key, value in record.items():
        name = normalize_column(str(key))
        if isinstance(value, dict):
            for inner_key, inner_value in value.items():
                inner_name = normalize_column(str(inner_key))
                fields[f"{name}_{inner_name}"] = "" if inner_value is None else str(inner_value)
        elif isinstance(value, (list, tuple)):
            fields[name] = ", ".join(str(item) for item in value)
        elif value is None:
            fields[name] = ""
        elif isinstance(value, bool):
            fields[name] = "true" if value else "false"
        else:
            fields[name] = str(value)
    return fields


class JsonParser(EvidenceParser):
    name = "json"

    def parse(self, data: bytes) -> ParseBatch:
        batch = ParseBatch()
        text = decode_text(data, batch.warnings)
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise UnknownFormatError(
                f"file appears to be JSON but could not be decoded: {exc.msg} "
                f"at line {exc.lineno}"
            ) from exc

        if isinstance(document, dict):
            for key in _LIST_KEYS:
                if isinstance(document.get(key), list):
                    document = document[key]
                    break
            else:
                document = [document]
        elif not isinstance(document, list):
            raise UnknownFormatError(
                "JSON evidence must be an object, an array, or an object "
                "containing an event list"
            )

        if not document:
            batch.warnings.append("JSON document contains no records")
            return batch

        row_index = 0
        for element in document:
            row_index += 1
            if not isinstance(element, dict):
                batch.records.append(
                    ParsedRecord(
                        row_index=row_index,
                        fields={},
                        raw=safe_record_repr(element),
                        parse_error="record is not a JSON object",
                    )
                )
                continue
            record_fields = _flatten(element)
            if len(batch.columns) < 64:
                batch.columns.extend(
                    key for key in record_fields if key not in batch.columns
                )
            batch.records.append(
                ParsedRecord(
                    row_index=row_index,
                    fields=record_fields,
                    raw=safe_record_repr(element),
                )
            )
        return batch
