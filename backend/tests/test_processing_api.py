"""Processing and event API contract tests (Phase 2)."""

from __future__ import annotations

SYSTEM_JSON = (
    b'{"events": ['
    b'{"@timestamp": "2026-10-05T13:00:00Z", "level": "info", "hostname": "DC-01",'
    b' "service": "ntds", "message": "Directory service started"},'
    b'{"@timestamp": "2026-10-05T13:10:00Z", "level": "error", "hostname": "SRV-WEB01",'
    b' "service": "nginx", "message": "Connection refused"},'
    b'{"@timestamp": "2026-10-05T13:20:00Z", "level": "fatal", "hostname": "DC-01",'
    b' "service": "smbd", "message": "Disk full"},'
    b'{"@timestamp": "broken", "level": "info", "hostname": "DC-01", "message": "bad ts"}'
    b']}'
)

AUTH_CSV = (
    b"timestamp,user,host,source_ip,action,result\n"
    b"2026-10-05 08:15:00,usr_alice,WS-01,10.20.30.5,login,success\n"
    b"2026-10-05 08:16:00,usr_bob,WS-07,10.20.30.6,login,failure\n"
    b"2026-10-05 08:17:00,usr_alice,WS-01,10.20.30.5,logout,success\n"
    b"bad-time,usr_alice,WS-01,10.20.30.5,login,success\n"
)


def _setup(client, make_case, upload_evidence, *, csv_data=AUTH_CSV, filename="auth.csv",
            evidence_type="authentication"):
    case = make_case()
    upload = upload_evidence(case["case_id"], filename, csv_data, evidence_type=evidence_type)
    assert upload.status_code == 201, upload.text
    response = client.post(f"/api/cases/{case['case_id']}/process", json={"actor": "tester"})
    assert response.status_code == 200, response.text
    return case["case_id"], upload.json()["evidence_id"], response.json()


# ---------------------------------------------------------------------------
# POST /api/cases/{case_id}/process
# ---------------------------------------------------------------------------

def test_process_returns_case_and_run_shapes(client, make_case, upload_evidence):
    case_id, _, body = _setup(client, make_case, upload_evidence)
    assert body["case_id"] == case_id
    run = body["runs"][0]
    for field in (
        "run_id", "case_id", "evidence_id", "evidence_filename", "parser", "status",
        "started_at", "completed_at", "records_received", "records_parsed",
        "records_normalized", "records_rejected", "duplicates_detected", "warnings",
        "error_code", "error",
    ):
        assert field in run
    assert run["run_id"].startswith("RUN-")
    assert run["case_id"] == case_id
    assert run["evidence_filename"] == "auth.csv"


def test_process_without_evidence_is_structured_400(client, make_case):
    case = make_case()
    response = client.post(f"/api/cases/{case['case_id']}/process", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CASE_HAS_NO_EVIDENCE"


def test_process_unknown_evidence_id_is_404(client, make_case, upload_evidence):
    case = make_case()
    upload_evidence(case["case_id"], "auth.csv", AUTH_CSV)
    response = client.post(
        f"/api/cases/{case['case_id']}/process",
        json={"evidence_ids": ["EV-9999"]},
    )
    assert response.status_code == 404


def test_process_unknown_case_is_404(client):
    response = client.post("/api/cases/CASE-XXXX/process", json={})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET processing runs / evidence processing / rejected records
# ---------------------------------------------------------------------------

def test_processing_runs_list_newest_first(client, make_case, upload_evidence):
    case_id, evidence_id, first = _setup(client, make_case, upload_evidence)
    client.post(f"/api/cases/{case_id}/process", json={"evidence_ids": [evidence_id]})

    runs = client.get(f"/api/cases/{case_id}/processing-runs").json()
    assert len(runs) == 2
    assert runs[0]["run_id"] != runs[1]["run_id"]
    assert {run["evidence_id"] for run in runs} == {evidence_id}


def test_evidence_processing_endpoint(client, make_case, upload_evidence):
    _, evidence_id, _ = _setup(client, make_case, upload_evidence)
    body = client.get(f"/api/evidence/{evidence_id}/processing").json()

    assert body["evidence_id"] == evidence_id
    assert body["status"] == "Processed"
    assert body["sha256"]
    assert len(body["runs"]) == 1
    assert body["runs"][0]["status"] == "Partial"     # one rejected row
    assert body["parse_rejected"] == 1


def test_evidence_processing_unknown_evidence_404(client):
    assert client.get("/api/evidence/EV-9999/processing").status_code == 404


def test_rejected_records_endpoint_shape(client, make_case, upload_evidence):
    _, evidence_id, _ = _setup(client, make_case, upload_evidence)
    records = client.get(f"/api/evidence/{evidence_id}/rejected-records").json()
    assert len(records) == 1
    record = records[0]
    assert record["evidence_id"] == evidence_id
    assert record["row_index"] == 4
    assert record["status"] == "REJECTED"
    assert "bad-time" in record["reason"]
    assert record["original_record"]
    assert record["processed_at"] is not None


# ---------------------------------------------------------------------------
# GET case events + filters
# ---------------------------------------------------------------------------

def test_events_list_envelope_and_fields(client, make_case, upload_evidence):
    case_id, evidence_id, _ = _setup(client, make_case, upload_evidence)
    body = client.get(f"/api/cases/{case_id}/events").json()

    assert set(body) == {"events", "total", "limit", "offset"}
    assert body["total"] == 3
    event = body["events"][0]
    for field in (
        "event_id", "case_id", "evidence_id", "timestamp", "tz_note", "source_type",
        "event_type", "user", "host", "source_ip", "severity",
        "raw_record_reference", "duplicate", "metadata",
    ):
        assert field in event
    assert event["event_id"].startswith("EVT-")
    assert event["case_id"] == case_id
    assert event["evidence_id"] == evidence_id
    assert event["source_type"] == "authentication"
    assert event["metadata"]["normalizer"] == "authentication"


def test_events_ordered_by_timestamp_desc(client, make_case, upload_evidence):
    case_id, _, _ = _setup(client, make_case, upload_evidence)
    events = client.get(f"/api/cases/{case_id}/events").json()["events"]
    timestamps = [event["timestamp"] for event in events]
    assert timestamps == sorted(timestamps, reverse=True)


def test_filter_by_source_type(client, make_case, upload_evidence):
    case_id, _, _ = _setup(client, make_case, upload_evidence)
    assert client.get(
        f"/api/cases/{case_id}/events", params={"source_type": "authentication"}
    ).json()["total"] == 3
    assert client.get(
        f"/api/cases/{case_id}/events", params={"source_type": "network"}
    ).json()["total"] == 0


def test_filter_by_event_type(client, make_case, upload_evidence):
    case_id, _, _ = _setup(client, make_case, upload_evidence)
    body = client.get(
        f"/api/cases/{case_id}/events", params={"event_type": "login"}
    ).json()
    assert body["total"] == 2
    assert all(event["event_type"] == "login" for event in body["events"])


def test_filter_by_severity(client, make_case, upload_evidence):
    case_id, _, _ = _setup(
        client, make_case, upload_evidence,
        csv_data=SYSTEM_JSON, filename="system_logs.json", evidence_type="system",
    )
    high = client.get(
        f"/api/cases/{case_id}/events", params={"severity": "High"}
    ).json()
    assert high["total"] == 1
    critical = client.get(
        f"/api/cases/{case_id}/events", params={"severity": "Critical"}
    ).json()
    assert critical["total"] == 1


def test_filter_by_user_contains_case_insensitive(client, make_case, upload_evidence):
    case_id, _, _ = _setup(client, make_case, upload_evidence)
    body = client.get(
        f"/api/cases/{case_id}/events", params={"user": "ALICE"}
    ).json()
    assert body["total"] == 2
    assert all("alice" in event["user"].lower() for event in body["events"])


def test_filter_by_host_contains(client, make_case, upload_evidence):
    case_id, _, _ = _setup(client, make_case, upload_evidence)
    body = client.get(
        f"/api/cases/{case_id}/events", params={"host": "ws-01"}
    ).json()
    assert body["total"] == 2


def test_filter_by_timestamp_range(client, make_case, upload_evidence):
    case_id, _, _ = _setup(client, make_case, upload_evidence)
    params = {
        "timestamp_from": "2026-10-05T08:16:00",
        "timestamp_to": "2026-10-05T08:17:00",
    }
    body = client.get(f"/api/cases/{case_id}/events", params=params).json()
    assert body["total"] == 2
    narrow = client.get(
        f"/api/cases/{case_id}/events",
        params={"timestamp_from": "2026-10-05T09:00:00"},
    ).json()
    assert narrow["total"] == 0


def test_filter_by_evidence_id(client, make_case, upload_evidence):
    case_id, evidence_id, _ = _setup(client, make_case, upload_evidence)
    body = client.get(
        f"/api/cases/{case_id}/events", params={"evidence_id": evidence_id}
    ).json()
    assert body["total"] == 3
    assert client.get(
        f"/api/cases/{case_id}/events", params={"evidence_id": "EV-9999"}
    ).status_code == 404


def test_limit_and_offset_pagination(client, make_case, upload_evidence):
    case_id, _, _ = _setup(client, make_case, upload_evidence)
    page = client.get(
        f"/api/cases/{case_id}/events", params={"limit": 2, "offset": 0}
    ).json()
    assert page["total"] == 3
    assert len(page["events"]) == 2
    assert page["limit"] == 2 and page["offset"] == 0

    rest = client.get(
        f"/api/cases/{case_id}/events", params={"limit": 2, "offset": 2}
    ).json()
    assert len(rest["events"]) == 1
    ids = {e["event_id"] for e in page["events"]} | {e["event_id"] for e in rest["events"]}
    assert len(ids) == 3


def test_invalid_pagination_is_validated(client, make_case, upload_evidence):
    case_id, _, _ = _setup(client, make_case, upload_evidence)
    response = client.get(f"/api/cases/{case_id}/events", params={"limit": 0})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# GET event detail — traceability
# ---------------------------------------------------------------------------

def test_event_detail_traces_to_raw_record_and_evidence_hash(
    client, make_case, upload_evidence
):
    case_id, evidence_id, _ = _setup(client, make_case, upload_evidence)
    listing = client.get(f"/api/cases/{case_id}/events").json()
    target = next(event for event in listing["events"] if not event["duplicate"])

    detail = client.get(
        f"/api/cases/{case_id}/events/{target['event_id']}"
    ).json()

    assert detail["event_id"] == target["event_id"]
    assert detail["raw_record"] is not None
    assert detail["raw_record"]["content"]
    assert detail["raw_record"]["reject_reason"] is None
    assert detail["raw_record"]["row_index"] >= 1
    assert detail["evidence"]["evidence_id"] == evidence_id
    assert len(detail["evidence"]["sha256"]) == 64
    assert detail["evidence"]["original_filename"] == "auth.csv"


def test_event_detail_shows_duplicate_marker_with_origin(
    client, make_case, upload_evidence
):
    messy = (
        b"timestamp,user,host,source_ip,action,result\n"
        b"2026-10-05 08:15:00,usr_alice,WS-01,10.20.30.5,login,success\n"
        b"2026-10-05 08:15:00,usr_alice,WS-01,10.20.30.5,login,success\n"
    )
    case_id, _, _ = _setup(client, make_case, upload_evidence, csv_data=messy)
    events = client.get(f"/api/cases/{case_id}/events").json()["events"]
    duplicate = next(event for event in events if event["duplicate"])

    detail = client.get(f"/api/cases/{case_id}/events/{duplicate['event_id']}").json()
    assert detail["duplicate"] is True
    assert detail["duplicate_of"] in {e["event_id"] for e in events}
    assert detail["duplicate_of"] != detail["event_id"]
    assert "identical timestamp" in detail["metadata"].get("duplicate", {}).get("reason", "")


def test_unknown_event_is_structured_404(client, make_case, upload_evidence):
    case_id, _, _ = _setup(client, make_case, upload_evidence)
    response = client.get(f"/api/cases/{case_id}/events/EVT-999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVENT_NOT_FOUND"


def test_event_from_other_case_is_not_found(client, make_case, upload_evidence):
    case_id, _, _ = _setup(client, make_case, upload_evidence)
    other = make_case(name="Other case")
    event_id = client.get(f"/api/cases/{case_id}/events").json()["events"][0]["event_id"]
    response = client.get(f"/api/cases/{other['case_id']}/events/{event_id}")
    assert response.status_code == 404


def test_events_of_case_without_processing_are_empty(client, make_case):
    case = make_case()
    body = client.get(f"/api/cases/{case['case_id']}/events").json()
    assert body == {"events": [], "total": 0, "limit": 100, "offset": 0}
