"""Parser, detection, and normalizer tests (Phase 2)."""

import pytest

from app.engines.parsing import UnknownFormatError, parse_evidence
from app.engines.parsing.base import ParseBatch, ParsedRecord
from app.engines.parsing.csv_parser import CsvParser, normalize_column
from app.engines.parsing.json_parser import JsonParser, looks_like_json
from app.engines.parsing.normalizer import (
    AuthenticationNormalizer,
    GenericNormalizer,
    canonicalize,
    map_severity,
    select_normalizer,
)

AUTH_CSV = b"""timestamp,user,host,source_ip,action,result
2026-10-05 08:15:00,usr_alice,WS-01,10.20.30.5,login,success
2026-10-05 08:16:12,usr_bob,WS-07,10.20.30.6,login,failure

2026-10-05 08:17:00,usr_alice,WS-01,10.20.30.5,logout,success
bad-row,too,few
"""


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------

def test_csv_header_columns_are_normalised():
    batch = CsvParser().parse(
        b"Timestamp,User Name,Source IP,Event Type\n2026-10-05 08:00:00,alice,1.2.3.4,login\n"
    )
    assert batch.columns == ["timestamp", "user_name", "source_ip", "event_type"]


def test_csv_column_normalisation_rules():
    assert normalize_column("Source IP") == "source_ip"
    assert normalize_column("@timestamp") == "timestamp"
    assert normalize_column("  Result  ") == "result"
    assert normalize_column("CamelCase") == "camelcase"


def test_csv_rows_are_numbered_from_one_and_blank_lines_skipped():
    batch = CsvParser().parse(AUTH_CSV)
    assert [record.row_index for record in batch.records] == [1, 2, 3, 4]


def test_csv_structural_malformed_row_is_retained():
    batch = CsvParser().parse(AUTH_CSV)
    malformed = batch.records[-1]
    assert malformed.parse_error == "malformed row: expected 6 columns, got 3"
    assert "bad-row" in malformed.raw


def test_csv_header_only_file_yields_empty_batch_with_warning():
    batch = CsvParser().parse(b"timestamp,user\n")
    assert batch.records == []
    assert batch.columns == ["timestamp", "user"]


def test_csv_encoding_fallback_records_warning():
    data = "timestamp,user\n2026-10-05 08:00:00,caf\xe9\n".encode("cp1252")
    batch = CsvParser().parse(data)
    assert any("cp1252" in warning for warning in batch.warnings)
    assert batch.records[0].fields["user"] == "café"


def test_csv_raw_record_keeps_original_header_names():
    batch = CsvParser().parse(
        b"Timestamp,User Name\n2026-10-05 08:00:00,alice\n"
    )
    assert "User Name" in batch.records[0].raw


# ---------------------------------------------------------------------------
# JSON parser
# ---------------------------------------------------------------------------

def test_json_array_of_objects():
    batch = JsonParser().parse(
        b'[{"timestamp": "2026-10-05 08:00:00", "user": "alice"}, '
        b'{"timestamp": "2026-10-05 08:01:00", "user": "bob"}]'
    )
    assert len(batch.records) == 2
    assert batch.records[1].fields["user"] == "bob"


def test_json_event_list_wrapper_detected():
    batch = JsonParser().parse(
        b'{"events": [{"timestamp": "2026-10-05 08:00:00", "message": "hello"}]}'
    )
    assert len(batch.records) == 1
    assert batch.records[0].fields["message"] == "hello"


def test_json_single_object_becomes_one_record():
    batch = JsonParser().parse(b'{"timestamp": "2026-10-05 08:00:00", "msg": "x"}')
    assert len(batch.records) == 1


def test_json_nested_objects_lists_null_and_bool_flattened():
    batch = JsonParser().parse(
        b'{"timestamp": "2026-10-05 08:00:00", "remote": {"ip": "1.2.3.4"}, '
        b'"tags": ["a", "b"], "detail": null, "online": false}'
    )
    fields = batch.records[0].fields
    assert fields["remote_ip"] == "1.2.3.4"
    assert fields["tags"] == "a, b"
    assert fields["detail"] == ""
    assert fields["online"] == "false"


def test_json_non_object_element_retained_as_malformed():
    batch = JsonParser().parse(
        b'[{"timestamp": "2026-10-05 08:00:00"}, 42]'
    )
    assert batch.records[1].parse_error == "record is not a JSON object"
    assert batch.records[1].raw == "42"


def test_json_invalid_document_raises_structured_unknown_format():
    with pytest.raises(UnknownFormatError) as excinfo:
        JsonParser().parse(b"{not valid json")
    assert "could not be decoded" in excinfo.value.message


def test_json_scalar_document_rejected():
    with pytest.raises(UnknownFormatError):
        JsonParser().parse(b'"just a string"')


def test_looks_like_json():
    assert looks_like_json('  {"events": []}')
    assert looks_like_json("[{}]")
    assert not looks_like_json("timestamp,user\n")


# ---------------------------------------------------------------------------
# Format detection (registry)
# ---------------------------------------------------------------------------

def test_csv_detected_by_extension():
    outcome = parse_evidence(
        b"timestamp,user\n2026-10-05 08:00:00,alice\n",
        filename="auth.csv",
        declared_type="authentication",
        max_records=100,
    )
    assert outcome.parser_name == "csv"
    assert outcome.normalizer.name == "authentication"


def test_csv_detected_by_content_without_known_extension():
    outcome = parse_evidence(
        b"timestamp,user,action\n2026-10-05 08:00:00,alice,login\n",
        filename="export.data",
        declared_type=None,
        max_records=100,
    )
    assert outcome.parser_name == "csv"


def test_json_content_wins_over_extension():
    outcome = parse_evidence(
        b'[{"timestamp": "2026-10-05 08:00:00", "user": "alice"}]',
        filename="records.csv",
        declared_type="generic",
        max_records=100,
    )
    assert outcome.parser_name == "json"


def test_unsupported_extension_rejected_with_hints():
    with pytest.raises(UnknownFormatError) as excinfo:
        parse_evidence(
            b"PK\x03\x04 not really csv",
            filename="archive.zip",
            declared_type="generic",
            max_records=100,
        )
    assert "unsupported evidence format" in excinfo.value.message
    assert excinfo.value.hints


def test_text_without_timestamp_column_rejected():
    with pytest.raises(UnknownFormatError) as excinfo:
        parse_evidence(
            b"id,name\n1,alpha\n2,beta\n",
            filename="table.csv",
            declared_type="generic",
            max_records=100,
        )
    assert "no timestamp field" in excinfo.value.message


def test_empty_evidence_rejected():
    with pytest.raises(UnknownFormatError):
        parse_evidence(b"   \n  ", filename="blank.csv", declared_type=None, max_records=100)


def test_record_limit_truncates_with_warning():
    rows = b"timestamp,user\n" + b"".join(
        f"2026-10-05 08:00:0{index},u{index}\n".encode() for index in range(5)
    )
    outcome = parse_evidence(rows, filename="t.csv", declared_type=None, max_records=3)
    assert len(outcome.batch.records) == 3
    assert any("record limit" in warning for warning in outcome.warnings)


# ---------------------------------------------------------------------------
# Normalizer selection
# ---------------------------------------------------------------------------

def test_alias_canonicalisation():
    canon = canonicalize(
        {"user_name": "alice", "src_ip": "1.2.3.4", "ts": "2026-10-05 08:00:00", "username": "ignored"}
    )
    assert canon["user"] == "alice"          # first non-empty wins
    assert canon["source_ip"] == "1.2.3.4"
    assert canon["timestamp"] == "2026-10-05 08:00:00"


def test_authentication_columns_selected_by_content():
    columns = {"timestamp", "user", "action", "status", "source_ip", "host"}
    assert select_normalizer(columns, None).name == "authentication"


def test_browser_columns_beat_declared_authentication_type():
    columns = {"timestamp", "user", "url", "domain", "action", "host"}
    assert select_normalizer(columns, "authentication").name == "browser"


def test_declared_type_breaks_content_tie():
    columns = {"timestamp", "user", "host", "action"}
    assert select_normalizer(columns, "authentication").name == "authentication"
    assert select_normalizer(columns, "browser").name == "browser"


def test_ambiguous_content_without_exclusive_evidence_is_generic():
    columns = {"timestamp", "user", "host", "action"}
    assert isinstance(select_normalizer(columns, "network"), GenericNormalizer)


def test_missing_timestamp_column_is_structured_unknown_format():
    with pytest.raises(UnknownFormatError):
        select_normalizer({"user", "host", "action"}, "generic")


def test_severity_vocabulary_mapping_and_unknown_values():
    assert map_severity("error") == "High"
    assert map_severity("Warning") == "Medium"
    assert map_severity("fatal") == "Critical"
    assert map_severity("info") == "Low"
    assert map_severity("trace") is None      # not invented
    assert map_severity(None) is None


def test_normalizer_rejects_missing_required_field():
    outcome = AuthenticationNormalizer().normalize(
        {"timestamp": "2026-10-05 08:00:00", "host": "WS-01"}, row_index=1
    )
    assert outcome.reject_reason == "missing required field: user"


def test_normalizer_rejects_bad_timestamp_with_value():
    outcome = AuthenticationNormalizer().normalize(
        {"timestamp": "yesterday", "user": "alice"}, row_index=1
    )
    assert outcome.reject_reason is not None
    assert "yesterday" in outcome.reject_reason


def test_normalizer_maps_common_schema_fields():
    outcome = AuthenticationNormalizer().normalize(
        {
            "timestamp": "2026-10-05 08:00:00",
            "user": "alice",
            "host": "WS-01",
            "source_ip": "10.20.30.5",
            "action": "login",
            "result": "failure",
            "event": "auth_log",
        },
        row_index=1,
    )
    assert outcome.reject_reason is None
    assert outcome.common["event_type"] == "auth_log"
    assert outcome.common["action"] == "login"
    assert outcome.common["user"] == "alice"
    assert outcome.common["source_type"] == "authentication"
    assert outcome.common["tz_note"] is not None
    assert outcome.metadata["status"] == "failure"


def test_source_specific_fields_preserved_in_metadata():
    outcome = GenericNormalizer().normalize(
        {
            "timestamp": "2026-10-05 08:00:00",
            "service": "nginx",
            "pid": "1200",
            "duration_ms": "5000",
            "destination_port": "443",
        },
        row_index=1,
    )
    assert outcome.metadata["service"] == "nginx"
    assert outcome.metadata["pid"] == "1200"
    assert outcome.metadata["duration_ms"] == "5000"
    assert outcome.metadata["destination_port"] == "443"
    assert "timestamp" not in outcome.metadata
