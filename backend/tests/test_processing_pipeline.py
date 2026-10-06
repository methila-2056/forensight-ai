"""Processing pipeline behaviour tests (Phase 2).

Covers status rules, count invariants, duplicate marking, malformed-record
retention, reprocessing semantics, integrity gating, and custody records.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import config

CLEAN_CSV = (
    b"timestamp,user,host,source_ip,action,result\n"
    b"2026-10-05 08:15:00,usr_alice,WS-01,10.20.30.5,login,success\n"
    b"2026-10-05 08:16:00,usr_bob,WS-07,10.20.30.6,login,success\n"
    b"2026-10-05 08:17:00,usr_alice,WS-01,10.20.30.5,logout,success\n"
)

MESSY_CSV = (
    b"timestamp,user,host,source_ip,action,result\n"
    b"2026-10-05 08:15:00,usr_alice,WS-01,10.20.30.5,login,success\n"
    b"bad-time,usr_bob,WS-07,10.20.30.6,login,failure\n"          # invalid ts
    b",usr_dana,WS-03,10.20.30.7,login,success\n"                  # missing ts
    b"2026-10-05 08:18:00,,WS-07,10.20.30.6,login,failure\n"       # missing user
    b"short,row\n"                                                 # structural
    b"2026-10-05 08:15:00,usr_alice,WS-01,10.20.30.5,login,success\n"  # duplicate
)


def _process(client, case_id: str, payload: dict | None = None):
    response = client.post(f"/api/cases/{case_id}/process", json=payload or {})
    assert response.status_code == 200, response.text
    return response.json()


def _events(client, case_id: str) -> dict:
    response = client.get(f"/api/cases/{case_id}/events")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Status rules and counts
# ---------------------------------------------------------------------------

def test_clean_evidence_completes_with_exact_counts(client, make_case, upload_evidence):
    case = make_case()
    upload = upload_evidence(case["case_id"], "clean.csv", CLEAN_CSV)
    assert upload.status_code == 201

    runs = _process(client, case["case_id"])["runs"]
    run = runs[0]

    assert run["status"] == "Completed"
    assert run["parser"] == "csv/authentication"
    assert run["records_received"] == 3
    assert run["records_parsed"] == 3
    assert run["records_normalized"] == 3
    assert run["records_rejected"] == 0
    assert run["duplicates_detected"] == 0
    assert run["error_code"] is None
    assert run["started_at"] is not None and run["completed_at"] is not None


def test_rejected_rows_yield_partial_never_completed(client, make_case, upload_evidence):
    case = make_case()
    upload_evidence(case["case_id"], "messy.csv", MESSY_CSV)

    run = _process(client, case["case_id"])["runs"][0]

    assert run["status"] == "Partial"
    assert run["records_received"] == 6
    assert run["records_rejected"] == 4
    assert run["records_parsed"] == 5          # 6 minus 1 structural reject
    assert run["records_normalized"] == 2
    assert run["duplicates_detected"] == 1
    # Invariant: received == normalized + rejected
    assert run["records_received"] == run["records_normalized"] + run["records_rejected"]


def test_header_only_evidence_yields_partial_with_warning(client, make_case, upload_evidence):
    case = make_case()
    upload_evidence(case["case_id"], "empty.csv", b"timestamp,user\n")

    run = _process(client, case["case_id"])["runs"][0]

    assert run["status"] == "Partial"
    assert run["records_received"] == 0
    assert any("no records" in warning for warning in run["warnings"])


def test_record_limit_marks_partial_with_truncation_warning(
    client, make_case, upload_evidence, monkeypatch
):
    monkeypatch.setattr(config, "MAX_RECORDS_PER_RUN", 2)
    case = make_case()
    upload_evidence(case["case_id"], "big.csv", CLEAN_CSV)

    run = _process(client, case["case_id"])["runs"][0]

    assert run["status"] == "Partial"
    assert run["records_received"] == 2
    assert any("record limit" in warning for warning in run["warnings"])
    assert any("remaining" in warning for warning in run["warnings"])


def test_unknown_format_failed_run_persisted_and_evidence_untouched(
    client, make_case, upload_evidence
):
    case = make_case()
    upload = upload_evidence(
        case["case_id"], "archive.zip", b"PK\x03\x04garbage", "application/zip",
        evidence_type="generic",
    )
    evidence_id = upload.json()["evidence_id"]

    response = client.post(
        f"/api/cases/{case['case_id']}/process",
        json={"evidence_ids": [evidence_id]},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "UNRECOGNIZED_EVIDENCE_FORMAT"
    assert error["detail"]["runs"]

    runs = client.get(f"/api/cases/{case['case_id']}/processing-runs").json()
    failed = next(run for run in runs if run["evidence_id"] == evidence_id)
    assert failed["status"] == "Failed"
    assert failed["error_code"] == "UNRECOGNIZED_EVIDENCE_FORMAT"
    assert failed["completed_at"] is not None

    evidence = client.get(f"/api/evidence/{evidence_id}").json()
    assert evidence["status"] == "Verified"          # restored, not claimed processed
    assert _events(client, case["case_id"])["total"] == 0


def test_integrity_mismatch_blocks_processing(client, make_case, upload_evidence):
    case = make_case()
    upload = upload_evidence(case["case_id"], "auth.csv", CLEAN_CSV)
    evidence_id = upload.json()["evidence_id"]

    # Tamper with the stored original (test-only: writes outside the API).
    store = Path(config.EVIDENCE_STORE_DIR) / case["case_id"]
    stored = next(store.glob(f"{evidence_id}.*"))
    stored.write_bytes(stored.read_bytes() + b"tampered")

    response = client.post(
        f"/api/cases/{case['case_id']}/process",
        json={"evidence_ids": [evidence_id]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVIDENCE_INTEGRITY_MISMATCH"

    runs = client.get(f"/api/cases/{case['case_id']}/processing-runs").json()
    failed = next(run for run in runs if run["evidence_id"] == evidence_id)
    assert failed["status"] == "Failed"
    assert failed["error_code"] == "EVIDENCE_INTEGRITY_MISMATCH"
    assert _events(client, case["case_id"])["total"] == 0


# ---------------------------------------------------------------------------
# Raw evidence immutability
# ---------------------------------------------------------------------------

def test_processing_never_modifies_raw_evidence(client, make_case, upload_evidence):
    case = make_case()
    upload = upload_evidence(case["case_id"], "auth.csv", CLEAN_CSV)
    evidence_id = upload.json()["evidence_id"]
    sha_before = upload.json()["sha256"]

    _process(client, case["case_id"])
    verify = client.post(f"/api/evidence/{evidence_id}/verify").json()
    assert verify["result"] == "INTEGRITY VERIFIED"
    assert verify["computed_hash"] == sha_before
    assert client.get(f"/api/evidence/{evidence_id}").json()["sha256"] == sha_before


def test_reprocessing_replaces_derived_rows_and_keeps_run_history(
    client, make_case, upload_evidence
):
    case = make_case()
    upload_evidence(case["case_id"], "messy.csv", MESSY_CSV)

    first = _process(client, case["case_id"])["runs"][0]
    events_after_first = _events(client, case["case_id"])["total"]
    assert events_after_first == 2

    second = _process(client, case["case_id"])["runs"][0]
    assert second["run_id"] != first["run_id"]

    # Run history preserved, derived events replaced (not appended).
    runs = client.get(f"/api/cases/{case['case_id']}/processing-runs").json()
    assert len(runs) == 2
    assert {run["run_id"] for run in runs} == {first["run_id"], second["run_id"]}
    assert _events(client, case["case_id"])["total"] == events_after_first

    rejected = client.get(f"/api/evidence/{second['evidence_id']}/rejected-records").json()
    assert len(rejected) == 4    # replaced, not doubled


# ---------------------------------------------------------------------------
# Duplicates, malformed retention, evidence counters
# ---------------------------------------------------------------------------

def test_duplicates_are_marked_and_never_deleted(client, make_case, upload_evidence):
    case = make_case()
    upload_evidence(case["case_id"], "messy.csv", MESSY_CSV)

    _process(client, case["case_id"])
    body = _events(client, case["case_id"])

    duplicates = [event for event in body["events"] if event["duplicate"]]
    assert len(duplicates) == 1
    marker = duplicates[0]
    assert marker["duplicate_of"] in {e["event_id"] for e in body["events"]}
    assert marker["duplicate_of"] != marker["event_id"]
    # The duplicated record itself still exists as an event.
    assert body["total"] == 2


def test_malformed_records_retained_with_reason_and_original_row(
    client, make_case, upload_evidence
):
    case = make_case()
    upload = upload_evidence(case["case_id"], "messy.csv", MESSY_CSV)
    evidence_id = upload.json()["evidence_id"]

    run = _process(client, case["case_id"])["runs"][0]
    rejected = client.get(f"/api/evidence/{evidence_id}/rejected-records").json()

    assert len(rejected) == run["records_rejected"]
    reasons = {record["row_index"]: record for record in rejected}
    assert "invalid timestamp format: 'bad-time'" in reasons[2]["reason"]
    assert "missing timestamp value" in reasons[3]["reason"]
    assert "missing required field: user" in reasons[4]["reason"]
    assert "malformed row" in reasons[5]["reason"]
    for record in rejected:
        assert record["status"] == "REJECTED"
        assert record["parser"] == "csv/authentication"
        assert record["original_record"]
        assert record["processed_at"] is not None


def test_evidence_parse_counters_updated(client, make_case, upload_evidence):
    case = make_case()
    upload = upload_evidence(case["case_id"], "messy.csv", MESSY_CSV)
    evidence_id = upload.json()["evidence_id"]

    _process(client, case["case_id"])
    evidence = client.get(f"/api/evidence/{evidence_id}").json()

    assert evidence["status"] == "Processed"
    assert evidence["record_count"] == 6
    assert evidence["parse_ok"] == 2
    assert evidence["parse_rejected"] == 4


# ---------------------------------------------------------------------------
# Custody and processing log
# ---------------------------------------------------------------------------

def test_processing_records_custody_actions(client, make_case, upload_evidence):
    case = make_case()
    upload = upload_evidence(case["case_id"], "auth.csv", CLEAN_CSV)
    evidence_id = upload.json()["evidence_id"]

    _process(client, case["case_id"])
    actions = [
        entry["action"]
        for entry in client.get(f"/api/evidence/{evidence_id}/custody").json()
    ]
    assert "Analysis Started" in actions
    assert "Analysis Completed" in actions

    completed = next(
        entry
        for entry in client.get(f"/api/evidence/{evidence_id}/custody").json()
        if entry["action"] == "Analysis Completed"
    )
    assert completed["details"]["status"] == "Completed"
    assert completed["details"]["records_normalized"] == 3


def test_processing_updates_case_last_activity(client, make_case, upload_evidence):
    case = make_case()
    before = client.get(f"/api/cases/{case['case_id']}").json()["last_activity"]
    upload_evidence(case["case_id"], "auth.csv", CLEAN_CSV)
    _process(client, case["case_id"])
    after = client.get(f"/api/cases/{case['case_id']}").json()["last_activity"]
    assert after >= before


# ---------------------------------------------------------------------------
# Batch semantics
# ---------------------------------------------------------------------------

def test_partial_batch_failure_returns_200_with_mixed_statuses(
    client, make_case, upload_evidence
):
    case = make_case()
    upload_evidence(case["case_id"], "auth.csv", CLEAN_CSV)
    upload_evidence(
        case["case_id"], "archive.zip", b"PK\x03\x04garbage", "application/zip",
        evidence_type="generic",
    )

    response = client.post(f"/api/cases/{case['case_id']}/process", json={})
    assert response.status_code == 200
    statuses = {run["evidence_filename"]: run["status"] for run in response.json()["runs"]}
    assert statuses["archive.zip"] == "Failed"
    assert statuses["auth.csv"] in ("Completed", "Partial")


def test_all_failed_batch_returns_structured_error(client, make_case, upload_evidence):
    case = make_case()
    upload_evidence(
        case["case_id"], "archive.zip", b"PK\x03\x04garbage", "application/zip",
        evidence_type="generic",
    )

    response = client.post(f"/api/cases/{case['case_id']}/process", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNRECOGNIZED_EVIDENCE_FORMAT"
    # The failed run is still persisted for inspection.
    runs = client.get(f"/api/cases/{case['case_id']}/processing-runs").json()
    assert runs and runs[0]["status"] == "Failed"


@pytest.mark.parametrize(
    "filename,data,evidence_type",
    [
        ("authentication.csv", CLEAN_CSV, "authentication"),
        ("archive.zip", b"PK\x03\x04garbage", "generic"),
    ],
)
def test_selected_evidence_processing_targets_only_requested(
    client, make_case, upload_evidence, filename, data, evidence_type
):
    case = make_case()
    upload_evidence(case["case_id"], "other.csv", CLEAN_CSV, evidence_type="authentication")
    content_type = "application/zip" if filename.endswith(".zip") else "text/csv"
    upload = upload_evidence(
        case["case_id"], filename, data, content_type, evidence_type=evidence_type
    )
    evidence_id = upload.json()["evidence_id"]

    response = client.post(
        f"/api/cases/{case['case_id']}/process",
        json={"evidence_ids": [evidence_id]},
    )
    # Single-item failures surface as a structured error; success returns the run.
    if filename.endswith(".zip"):
        assert response.status_code == 422
    else:
        assert response.status_code == 200, response.text

    runs = client.get(f"/api/cases/{case['case_id']}/processing-runs").json()
    processed_ids = {run["evidence_id"] for run in runs}
    assert processed_ids == {evidence_id}
