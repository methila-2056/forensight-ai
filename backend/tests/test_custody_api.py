"""Phase 1 tests — chain-of-custody events (handling record, no legal claim)."""

from __future__ import annotations

from fastapi.testclient import TestClient

CSV_BODY = b"timestamp,user,action\n2026-01-01T00:00:00Z,usr_demo,login\n"


def _actions(events: list[dict]) -> list[str]:
    return [event["action"] for event in sorted(events, key=lambda e: e["id"])]


def test_upload_records_required_custody_events(client, make_case, upload_evidence):
    case = make_case(name="Custody upload")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()

    response = client.get(f"/api/evidence/{uploaded['evidence_id']}/custody")
    assert response.status_code == 200
    events = response.json()

    actions = _actions(events)
    assert actions[:3] == ["Evidence Added", "Hash Generated", "Integrity Verified"]

    for event in events:
        assert event["case_id"] == case["case_id"]
        assert event["evidence_id"] == uploaded["evidence_id"]
        assert event["timestamp"]
        assert event["actor"] == "tester"

    hash_event = next(e for e in events if e["action"] == "Hash Generated")
    assert hash_event["details"]["algorithm"] == "SHA-256"
    assert hash_event["details"]["sha256"] == uploaded["sha256"]

    added_event = next(e for e in events if e["action"] == "Evidence Added")
    assert added_event["details"]["filename"] == "authentication.csv"
    assert added_event["details"]["file_size"] == len(CSV_BODY)


def test_verify_adds_integrity_custody_event(client, make_case, upload_evidence):
    case = make_case(name="Custody verify")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()
    client.post(f"/api/evidence/{uploaded['evidence_id']}/verify?actor=investigator_1")

    events = client.get(f"/api/evidence/{uploaded['evidence_id']}/custody").json()
    actions = _actions(events)
    assert actions.count("Integrity Verified") >= 2  # ingest + explicit verify

    explicit = [e for e in events if e["actor"] == "investigator_1"]
    assert explicit and explicit[0]["action"] == "Integrity Verified"
    assert explicit[0]["details"]["computed_hash"] == uploaded["sha256"]
    assert explicit[0]["details"]["expected_hash"] == uploaded["sha256"]


def test_controlled_test_records_custody_event(client, make_case, upload_evidence):
    case = make_case(name="Custody test")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()
    client.post(f"/api/evidence/{uploaded['evidence_id']}/integrity-test")

    events = client.get(f"/api/evidence/{uploaded['evidence_id']}/custody").json()
    test_events = [e for e in events if e["action"] == "Integrity Test"]
    assert len(test_events) == 1
    details = test_events[0]["details"]
    assert details["operation"] == "Controlled Integrity Test - Demonstration Copy"
    assert details["result"] == "INTEGRITY MISMATCH"
    assert details["original_unchanged"] is True


def test_case_level_custody_contains_all_evidence(client, make_case, upload_evidence):
    case = make_case(name="Custody case level")
    first = upload_evidence(case["case_id"], "a.csv", CSV_BODY).json()
    second = upload_evidence(
        case["case_id"], "b.log", b"line one\n", "text/plain", "system"
    ).json()

    response = client.get(f"/api/cases/{case['case_id']}/custody")
    assert response.status_code == 200
    events = response.json()
    evidence_ids = {e["evidence_id"] for e in events if e["evidence_id"]}
    assert {first["evidence_id"], second["evidence_id"]} == evidence_ids
    assert len(events) >= 6  # 3 events per evidence item
    for event in events:
        assert event["case_id"] == case["case_id"]
        assert event["actor"]
        assert event["timestamp"]


def test_mismatch_verify_records_mismatch_custody_event(
    client, make_case, upload_evidence
):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Evidence

    case = make_case(name="Custody mismatch")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()

    db = SessionLocal()
    try:
        evidence = db.scalar(
            select(Evidence).where(Evidence.evidence_id == uploaded["evidence_id"])
        )
        evidence.original_hash = "1" * 64
        db.commit()
    finally:
        db.close()

    client.post(f"/api/evidence/{uploaded['evidence_id']}/verify")
    events = client.get(f"/api/evidence/{uploaded['evidence_id']}/custody").json()
    mismatch = [e for e in events if e["action"] == "Integrity Mismatch"]
    assert len(mismatch) == 1
    assert mismatch[0]["details"]["result"] == "INTEGRITY MISMATCH"


def test_custody_unknown_case_and_evidence(client, make_case):
    case = make_case(name="Custody 404s")
    assert case

    case_404 = client.get("/api/cases/CASE-1999-999/custody")
    assert case_404.status_code == 404
    assert case_404.json()["error"]["code"] == "CASE_NOT_FOUND"

    evidence_404 = client.get("/api/evidence/EV-9999/custody")
    assert evidence_404.status_code == 404
    assert evidence_404.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"
