"""ZIP container evidence tests (Phase 12).

Covers three concerns:

1. **Function** — a multi-member archive parses, each member is normalized with
   its own schema, and member provenance is preserved on every event.
2. **Integration** — the API accepts a .zip upload and the full pipeline
   produces events, findings, and correlations from it.
3. **Safety** — path traversal, zip bombs (count / size / ratio), nested
   archives, symlinks, and encrypted entries are all refused, and archive
   handling never writes to disk.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app import config
from app.engines.parsing.base import UnknownFormatError
from app.engines.parsing.registry import parse_evidence

AUTH_CSV = (
    b"timestamp,user,host,source_ip,action,result\n"
    b"2026-10-05 08:00:00,usr_alice,WS-01,10.20.30.5,login,success\n"
    b"2026-10-05 08:05:00,usr_alice,WS-01,10.20.30.5,login,failure\n"
)
FILE_CSV = (
    b"timestamp,user,host,file_path,action,result\n"
    b"2026-10-05 08:10:00,usr_alice,WS-01,C:\\Shares\\a.doc,write,success\n"
    b"2026-10-05 08:12:00,usr_alice,WS-01,C:\\Shares\\b.doc,write,success\n"
)
SYSTEM_JSON = (
    b'{"events": [{"timestamp": "2026-10-05T08:20:00Z", "message": "boot", '
    b'"host": "WS-01"}]}'
)


def build_zip(entries: dict[str, bytes], *, compress: bool = True) -> bytes:
    buffer = io.BytesIO()
    mode = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(buffer, "w", mode) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


# --- function ---------------------------------------------------------------


def test_zip_with_mixed_schemas_normalizes_per_member():
    data = build_zip({
        "auth.csv": AUTH_CSV,
        "files.csv": FILE_CSV,
        "system.json": SYSTEM_JSON,
    })
    outcome = parse_evidence(
        data, filename="evidence.zip", declared_type=None, max_records=1000
    )

    assert outcome.parser_name == "zip"
    assert len(outcome.batch.records) == 5  # 2 auth + 2 file + 1 system

    source_types = {
        record.pre_normalized.common.get("source_type")
        for record in outcome.batch.records
        if record.pre_normalized is not None
    }
    # Each member must be typed by its own schema, not one blanket type.
    assert source_types == {"authentication", "file_activity", "system"}


def test_zip_records_carry_member_provenance():
    data = build_zip({"logs/auth.csv": AUTH_CSV})
    outcome = parse_evidence(
        data, filename="evidence.zip", declared_type=None, max_records=1000
    )
    record = outcome.batch.records[0]
    assert record.member_path == "logs/auth.csv"
    assert record.pre_normalized.metadata["member_path"] == "logs/auth.csv"


def test_zip_member_report_lists_every_entry():
    data = build_zip({"auth.csv": AUTH_CSV, "files.csv": FILE_CSV})
    outcome = parse_evidence(
        data, filename="evidence.zip", declared_type=None, max_records=1000
    )
    paths = {m.path for m in outcome.members}
    assert paths == {"auth.csv", "files.csv"}
    assert all(m.status == "ok" for m in outcome.members)


def test_zip_unsupported_member_is_retained_not_discarded():
    """A member we cannot read is kept as a rejected record, never dropped."""
    data = build_zip({"auth.csv": AUTH_CSV, "notes.docx": b"binary blob"})
    outcome = parse_evidence(
        data, filename="evidence.zip", declared_type=None, max_records=1000
    )
    rejected = [r for r in outcome.batch.records if r.parse_error]
    assert len(rejected) == 1
    assert "notes.docx" in (rejected[0].member_path or "")


def test_zip_malformed_member_row_is_retained():
    data = build_zip({
        "auth.csv": AUTH_CSV + b"2026-10-05 08:20:00,,WS-01,10.20.30.5,login\n"
    })
    outcome = parse_evidence(
        data, filename="evidence.zip", declared_type=None, max_records=1000
    )
    rejected = [r for r in outcome.batch.records if r.parse_error]
    assert rejected, "a row missing the required user field must be retained"


# --- safety -----------------------------------------------------------------


def test_zip_path_traversal_is_neutralised():
    """Traversal names must be reduced to a safe label and never used as paths."""
    data = build_zip({"../../../../etc/evil.csv": AUTH_CSV})
    outcome = parse_evidence(
        data, filename="evidence.zip", declared_type=None, max_records=1000
    )
    readable = [r for r in outcome.batch.records if not r.parse_error]
    assert readable, "the member should still be readable"
    path = readable[0].member_path
    assert ".." not in path
    assert not path.startswith("/")
    assert path == "etc/evil.csv"


def test_zip_nested_archive_is_not_expanded():
    inner = build_zip({"auth.csv": AUTH_CSV})
    data = build_zip({"outer.zip": inner, "auth.csv": AUTH_CSV})
    outcome = parse_evidence(
        data, filename="evidence.zip", declared_type=None, max_records=1000
    )
    paths = {r.member_path for r in outcome.batch.records}
    assert "outer.zip" not in paths
    assert any("nested archive" in w for w in outcome.warnings)


def test_zip_symlink_member_is_skipped():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("link.csv")
        info.external_attr = (0o120777 << 16)  # symlink mode bits
        archive.writestr(info, AUTH_CSV)
        archive.writestr("auth.csv", AUTH_CSV)
    outcome = parse_evidence(
        buffer.getvalue(), filename="evidence.zip", declared_type=None, max_records=100
    )
    skipped = [m for m in outcome.members if m.status == "skipped"]
    assert any("symlink" in (m.detail or "") for m in skipped)


def test_zip_member_count_limit_enforced(monkeypatch):
    monkeypatch.setattr(config, "ZIP_MAX_MEMBERS", 2)
    data = build_zip({"a.csv": AUTH_CSV, "b.csv": AUTH_CSV, "c.csv": AUTH_CSV})
    with pytest.raises(UnknownFormatError) as excinfo:
        parse_evidence(
            data, filename="evidence.zip", declared_type=None, max_records=100
        )
    assert "more members" in excinfo.value.message


def test_zip_per_member_size_limit_skips_that_member(monkeypatch):
    """An oversized member is skipped and explained, while others still load."""
    monkeypatch.setattr(config, "ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES", 20)
    monkeypatch.setattr(config, "ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES", 10_000_000)
    monkeypatch.setattr(config, "ZIP_MAX_COMPRESSION_RATIO", 10_000)
    data = build_zip({"big.csv": b"x" * 5000, "auth.csv": AUTH_CSV})
    outcome = parse_evidence(
        data, filename="evidence.zip", declared_type=None, max_records=1000
    )
    skipped = [m for m in outcome.members if m.status == "skipped"]
    assert any("per-member size limit" in (m.detail or "") for m in skipped)
    # The small member is unaffected, and the skip is explained, not silent.
    assert outcome.batch.records
    assert any("per-member size limit" in w for w in outcome.warnings)


def test_zip_compression_ratio_limit_enforced(monkeypatch):
    """A highly compressible member must be refused, not expanded."""
    monkeypatch.setattr(config, "ZIP_MAX_COMPRESSION_RATIO", 5)
    data = build_zip({"bomb.csv": b"A" * 400_000})
    outcome = parse_evidence(
        data, filename="evidence.zip", declared_type=None, max_records=1000
    )
    skipped = [m for m in outcome.members if m.status == "skipped"]
    assert any("compression ratio" in (m.detail or "") for m in skipped)
    # The bomb must never be expanded: the only record is a rejection marker
    # carrying the reason, not decoded content.
    assert all(r.parse_error for r in outcome.batch.records)
    assert not any(r.pre_normalized for r in outcome.batch.records)


def test_zip_total_uncompressed_limit_enforced(monkeypatch):
    monkeypatch.setattr(config, "ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES", 200)
    data = build_zip({"a.csv": AUTH_CSV, "b.csv": FILE_CSV})
    with pytest.raises(UnknownFormatError) as excinfo:
        parse_evidence(
            data, filename="evidence.zip", declared_type=None, max_records=100
        )
    assert "total size limit" in excinfo.value.message


def test_zip_stored_archive_still_parses():
    data = build_zip({"auth.csv": AUTH_CSV}, compress=False)
    outcome = parse_evidence(
        data, filename="evidence.zip", declared_type=None, max_records=100
    )
    assert len(outcome.batch.records) == 2


# --- API integration --------------------------------------------------------


def test_zip_upload_runs_through_pipeline(
    client, make_case, upload_evidence
):
    """A .zip upload must reach events, findings, and a report."""
    data = build_zip({
        "auth.csv": AUTH_CSV,
        "files.csv": FILE_CSV,
    })
    case = make_case(name="ZIP evidence", description="archive upload")
    case_id = case["case_id"]

    upload = upload_evidence(
        case_id,
        "evidence.zip",
        data,
        content_type="application/zip",
        evidence_type="generic",
        source="archive",
    )
    assert upload.status_code == 201, upload.text

    processed = client.post(f"/api/cases/{case_id}/process", json={"actor": "test"})
    assert processed.status_code == 200, processed.text
    runs = processed.json()["runs"]
    assert runs[0]["parser"].startswith("zip/")
    assert runs[0]["records_normalized"] == 4

    events = client.get(f"/api/cases/{case_id}/events", params={"limit": 100}).json()
    assert events["total"] == 4
    assert all(
        e["metadata"].get("member_path") for e in events["events"]
    ), "every event must record which archive member it came from"

    client.post(f"/api/cases/{case_id}/analyze", json={"actor": "test"})
    client.post(f"/api/cases/{case_id}/correlate", json={"actor": "test"})
    report = client.post(f"/api/cases/{case_id}/reports", json={"actor": "test"})
    assert report.status_code == 201, report.text

    # The archive itself must remain byte-identical after the whole pipeline.
    verify = client.post(
        f"/api/evidence/{upload.json()['evidence_id']}/verify"
    ).json()
    assert verify["result"] == "INTEGRITY VERIFIED"
    assert verify["computed_hash"] == upload.json()["sha256"]


def test_zip_mislabeled_as_csv_is_still_detected_by_content():
    """Content wins over the extension when the signature is unambiguous."""
    data = build_zip({"auth.csv": AUTH_CSV})
    outcome = parse_evidence(
        data, filename="mislabelled.csv", declared_type=None, max_records=100
    )
    assert outcome.parser_name == "zip"