"""Phase 1 tests — Evidence Integrity Verification + Controlled Integrity Test.

These tests prove results are computed from real bytes, never hardcoded, and
that the stored original is never modified.
"""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config, terminology
from app.db import SessionLocal
from app.models import Evidence, EvidenceStatus
from app.storage.raw_store import RawEvidenceStore

CSV_BODY = b"timestamp,user,action\n2026-01-01T00:00:00Z,usr_demo,login\n"


def test_verify_returns_computed_verified_result(client, make_case, upload_evidence):
    case = make_case(name="Verify")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()

    response = client.post(f"/api/evidence/{uploaded['evidence_id']}/verify")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["result"] == terminology.INTEGRITY_VERIFIED
    assert body["algorithm"] == "SHA-256"
    assert body["computed_hash"] == hashlib.sha256(CSV_BODY).hexdigest()
    assert body["expected_hash"] == uploaded["sha256"]
    assert body["computed_hash"] == body["expected_hash"]
    assert "does not establish who created or collected" in body["note"]
    assert body["verified_at"]


def test_verify_is_repeatable(client, make_case, upload_evidence):
    case = make_case(name="Repeat")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()
    first = client.post(f"/api/evidence/{uploaded['evidence_id']}/verify").json()
    second = client.post(f"/api/evidence/{uploaded['evidence_id']}/verify").json()
    assert first["result"] == second["result"] == terminology.INTEGRITY_VERIFIED
    assert first["computed_hash"] == second["computed_hash"]


def test_verify_detects_reference_hash_mismatch(client, make_case, upload_evidence):
    """If the recorded reference no longer matches the bytes, the API must
    report INTEGRITY MISMATCH — the result comes from real computation."""
    case = make_case(name="Mismatch")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()

    db = SessionLocal()
    try:
        evidence = db.scalar(
            select(Evidence).where(Evidence.evidence_id == uploaded["evidence_id"])
        )
        evidence.original_hash = "0" * 64
        db.commit()
    finally:
        db.close()

    response = client.post(f"/api/evidence/{uploaded['evidence_id']}/verify")
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == terminology.INTEGRITY_MISMATCH
    assert body["expected_hash"] == "0" * 64
    assert body["computed_hash"] == hashlib.sha256(CSV_BODY).hexdigest()

    detail = client.get(f"/api/evidence/{uploaded['evidence_id']}").json()
    assert detail["status"] == "Error"

    history = client.get(
        f"/api/evidence/{uploaded['evidence_id']}/integrity-history"
    ).json()
    assert terminology.INTEGRITY_MISMATCH in [entry["result"] for entry in history]

    custody_log = client.get(f"/api/evidence/{uploaded['evidence_id']}/custody").json()
    assert "Integrity Mismatch" in [event["action"] for event in custody_log]


def test_controlled_integrity_test_mismatch_and_original_untouched(
    client, make_case, upload_evidence
):
    case = make_case(name="Controlled test")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()
    evidence_id = uploaded["evidence_id"]

    response = client.post(f"/api/evidence/{evidence_id}/integrity-test")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["operation"] == terminology.INTEGRITY_TEST_LABEL
    assert body["result"] == terminology.INTEGRITY_MISMATCH
    assert body["recorded_hash"] == uploaded["sha256"]
    assert body["test_copy_hash"] != body["recorded_hash"]
    assert body["test_copy_hash"] == hashlib.sha256(
        CSV_BODY + b"\nCONTROLLED-TAMPER\n"
    ).hexdigest()
    assert body["original_unchanged"] is True
    assert "stored original" in body["note"]

    # Original evidence must still verify after the controlled test.
    verify = client.post(f"/api/evidence/{evidence_id}/verify").json()
    assert verify["result"] == terminology.INTEGRITY_VERIFIED
    assert verify["computed_hash"] == uploaded["sha256"]

    # Raw store bytes must be byte-for-byte identical to the upload.
    store = RawEvidenceStore(config.EVIDENCE_STORE_DIR)
    assert store.read_bytes(case["case_id"], evidence_id) == CSV_BODY


def test_controlled_test_does_not_create_raw_evidence_files(
    client, make_case, upload_evidence
):
    case = make_case(name="Copy isolation")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()
    store = RawEvidenceStore(config.EVIDENCE_STORE_DIR)
    case_dir = store.root / case["case_id"]
    before = sorted(p.name for p in case_dir.iterdir())

    client.post(f"/api/evidence/{uploaded['evidence_id']}/integrity-test")

    after = sorted(p.name for p in case_dir.iterdir())
    assert before == after, "Controlled test must not add/modify files in the raw store"

    controlled_root = config.EVIDENCE_STORE_DIR / "controlled_tests" / case["case_id"]
    assert controlled_root.is_dir()
    assert any(controlled_root.iterdir()), "A demonstration copy should exist outside raw storage"


def test_raw_evidence_immutable_across_full_phase1_flow(client, make_case, upload_evidence):
    case = make_case(name="Immutable")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()
    original_hash = uploaded["sha256"]

    client.post(f"/api/evidence/{uploaded['evidence_id']}/verify")
    client.post(f"/api/evidence/{uploaded['evidence_id']}/integrity-test")
    client.post(f"/api/evidence/{uploaded['evidence_id']}/verify")
    client.get(f"/api/cases/{case['case_id']}/evidence")

    store = RawEvidenceStore(config.EVIDENCE_STORE_DIR)
    stored = store.read_bytes(case["case_id"], uploaded["evidence_id"])
    assert stored == CSV_BODY
    assert hashlib.sha256(stored).hexdigest() == original_hash

    final = client.post(f"/api/evidence/{uploaded['evidence_id']}/verify").json()
    assert final["result"] == terminology.INTEGRITY_VERIFIED


def test_verify_unknown_evidence_returns_404(client):
    response = client.post("/api/evidence/EV-9999/verify")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_integrity_history_recorded(client, make_case, upload_evidence):
    case = make_case(name="History")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()
    client.post(f"/api/evidence/{uploaded['evidence_id']}/verify")

    response = client.get(f"/api/evidence/{uploaded['evidence_id']}/integrity-history")
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) >= 2  # ingest-time check + explicit verify
    assert all(entry["result"] == terminology.INTEGRITY_VERIFIED for entry in entries)
    assert all(entry["computed_hash"] == uploaded["sha256"] for entry in entries)


def test_evidence_status_transitions_on_upload_and_mismatch(
    client, make_case, upload_evidence
):
    case = make_case(name="Status")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()
    assert uploaded["status"] == "Verified"

    db = SessionLocal()
    try:
        evidence = db.scalar(
            select(Evidence).where(Evidence.evidence_id == uploaded["evidence_id"])
        )
        evidence.original_hash = "f" * 64
        db.commit()
    finally:
        db.close()

    client.post(f"/api/evidence/{uploaded['evidence_id']}/verify")
    detail = client.get(f"/api/evidence/{uploaded['evidence_id']}").json()
    assert detail["status"] == EvidenceStatus.ERROR.value
