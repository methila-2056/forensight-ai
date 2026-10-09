"""Phase 9 tests — security, performance & reliability hardening.

This module captures the Phase 9 regression guarantees:

* bounded input: upload ``actor``/``source`` and ``verify``/``integrity-test``
  ``actor`` parameters are length-capped at the API so an oversized value
  returns a validation error (422) instead of surfacing a raw SQLAlchemy
  column-length failure as a generic 500 body.
* raw evidence immutability holds across the ENTIRE product lifecycle
  (upload → process → analyze → correlate → report → assistant → workspace →
  verify → controlled integrity test), not just the Phase 1 ingest flow.
* concurrent read-only requests observe consistent, case-scoped data.
* database initialisation is idempotent and foreign keys are enforced.
"""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import config, terminology
from app.db import engine, init_db
from app.storage import raw_store as raw_store_module
from app.storage.raw_store import RawEvidenceExistsError, RawEvidenceStore

# ---------------------------------------------------------------------------
# Deterministic synthetic evidence fixtures (same calibration as Phase 4/8)
# ---------------------------------------------------------------------------

_BASE = datetime(2026, 10, 5, 8, 0)


def _stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _auth_rows() -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    users = [
        ("usr_alice", "WS-01", "10.20.30.5"),
        ("usr_bob", "WS-02", "10.20.30.6"),
        ("usr_carol", "WS-03", "10.20.30.7"),
    ]
    for index in range(12):
        user, host, ip = users[index % 3]
        rows.append(
            (_stamp(_BASE + timedelta(minutes=4 * index)), user, host, ip, "login", "success")
        )
    for minute in (48, 49, 50):
        rows.append(
            (_stamp(_BASE + timedelta(minutes=minute)), "usr_dave", "WS-04",
             "10.20.30.8", "login", "failure")
        )
    rows.append(
        (_stamp(_BASE + timedelta(minutes=51)), "usr_dave", "WS-04",
         "10.20.30.8", "login", "success")
    )
    return rows


FILE_WRITES = [
    ("2026-10-05 09:00:00", "usr_dave", "FS-01", "C:\\Shares\\a.doc", "write"),
    ("2026-10-05 09:02:00", "usr_dave", "FS-01", "C:\\Shares\\b.doc", "write"),
    ("2026-10-05 09:04:00", "usr_dave", "FS-01", "C:\\Shares\\c.doc", "write"),
]

PROCESS_ROWS = [
    ("2026-10-05 09:30:00", "usr_dave", "SRV-01", "powershell.exe",
     "powershell.exe -enc SQBFAFgA", "start"),
]

NETWORK_ROWS = [
    ("2026-10-05 09:31:00", "SRV-01", "10.20.30.9", "93.184.216.34", "443", "tcp"),
]


def _csv(header: str, rows: list[tuple]) -> bytes:
    lines = [header.rstrip("\n")]
    lines.extend(",".join(str(cell) for cell in row) for row in rows)
    return ("\n".join(lines) + "\n").encode()


AUTH_CSV = _csv("timestamp,user,host,source_ip,action,result", _auth_rows())
FILE_CSV = _csv("timestamp,user,host,file_path,action", FILE_WRITES)
PROCESS_CSV = _csv("timestamp,user,host,process,command_line,action", PROCESS_ROWS)
NETWORK_CSV = _csv(
    "timestamp,host,source_ip,destination_ip,destination_port,protocol", NETWORK_ROWS
)

EVIDENCE_FILES = (
    ("auth.csv", AUTH_CSV, "authentication"),
    ("file.csv", FILE_CSV, "file_activity"),
    ("proc.csv", PROCESS_CSV, "process"),
    ("net.csv", NETWORK_CSV, "network"),
)


def _run_full_pipeline(client: TestClient, make_case, upload_evidence) -> dict:
    case = make_case(name="Phase 9 pipeline")
    uploads = []
    for filename, data, evidence_type in EVIDENCE_FILES:
        response = upload_evidence(
            case["case_id"], filename, data, evidence_type=evidence_type
        )
        assert response.status_code == 201, response.text
        uploads.append(response.json())
    assert client.post(f"/api/cases/{case['case_id']}/process", json={}).status_code == 200
    assert client.post(f"/api/cases/{case['case_id']}/analyze", json={}).status_code == 200
    assert client.post(f"/api/cases/{case['case_id']}/correlate", json={}).status_code == 200
    report = client.post(f"/api/cases/{case['case_id']}/reports", json={})
    assert report.status_code == 201, report.text
    return {"case": case, "uploads": uploads, "report": report.json()}


# ---------------------------------------------------------------------------
# Bounded input (Phase 9) — oversized actor/source must 422, never a 500
# ---------------------------------------------------------------------------

_ACTOR_LIMIT = 127
_SOURCE_LIMIT = 4000


def test_upload_actor_exceeding_column_cap_is_rejected_422(client, make_case, upload_evidence):
    case = make_case(name="Long actor")
    response = upload_evidence(
        case["case_id"], "auth.csv", AUTH_CSV, actor="x" * (_ACTOR_LIMIT + 1)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_upload_source_exceeding_api_cap_is_rejected_422(client, make_case, upload_evidence):
    case = make_case(name="Long source")
    response = upload_evidence(
        case["case_id"], "auth.csv", AUTH_CSV, source="x" * (_SOURCE_LIMIT + 1)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_verify_actor_exceeding_column_cap_is_rejected_422(client, make_case, upload_evidence):
    case = make_case(name="Verify actor")
    uploaded = upload_evidence(case["case_id"], "auth.csv", AUTH_CSV).json()
    response = client.post(
        f"/api/evidence/{uploaded['evidence_id']}/verify",
        params={"actor": "x" * (_ACTOR_LIMIT + 1)},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_integrity_test_actor_exceeding_column_cap_is_rejected_422(
    client, make_case, upload_evidence
):
    case = make_case(name="Test actor")
    uploaded = upload_evidence(case["case_id"], "auth.csv", AUTH_CSV).json()
    response = client.post(
        f"/api/evidence/{uploaded['evidence_id']}/integrity-test",
        params={"actor": "x" * (_ACTOR_LIMIT + 1)},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_boundary_lengths_are_accepted(client, make_case, upload_evidence):
    case = make_case(name="Boundary")
    response = upload_evidence(
        case["case_id"],
        "auth.csv",
        AUTH_CSV,
        actor="a" * _ACTOR_LIMIT,
        source="s" * _SOURCE_LIMIT,
    )
    assert response.status_code == 201, response.text
    evidence_id = response.json()["evidence_id"]

    verify = client.post(
        f"/api/evidence/{evidence_id}/verify",
        params={"actor": "b" * _ACTOR_LIMIT},
    )
    assert verify.status_code == 200, verify.text

    test = client.post(
        f"/api/evidence/{evidence_id}/integrity-test",
        params={"actor": "c" * _ACTOR_LIMIT},
    )
    assert test.status_code == 200, test.text


# ---------------------------------------------------------------------------
# Raw evidence immutability across the whole product lifecycle (Phase 9)
# ---------------------------------------------------------------------------

def test_raw_evidence_bytes_unchanged_across_full_product_lifecycle(
    client, make_case, upload_evidence
):
    result = _run_full_pipeline(client, make_case, upload_evidence)
    case_id = result["case"]["case_id"]
    first = result["uploads"][0]
    evidence_id, original_hash = first["evidence_id"], first["sha256"]

    store = RawEvidenceStore(config.EVIDENCE_STORE_DIR)
    original_bytes = store.read_bytes(case_id, evidence_id)

    # Every derived-data phase touches the case without touching raw storage.
    client.post(f"/api/evidence/{evidence_id}/verify")
    client.post(f"/api/evidence/{evidence_id}/integrity-test")
    client.post(f"/api/evidence/{evidence_id}/verify")
    client.get(f"/api/evidence/{evidence_id}/custody")
    client.get(f"/api/evidence/{evidence_id}/integrity-history")
    client.get(f"/api/cases/{case_id}/workspace")
    client.get(f"/api/cases/{case_id}/events")
    client.get(f"/api/cases/{case_id}/reports/{result['report']['report_id']}/json")
    client.post(
        f"/api/cases/{case_id}/assistant/query",
        json={"question": "Summarize the case", "actor": "investigator"},
    )

    stored_after = store.read_bytes(case_id, evidence_id)
    assert stored_after == original_bytes, "raw bytes drifted during the lifecycle"
    assert (
        hashlib.sha256(stored_after).hexdigest() == original_hash
    ), "raw SHA-256 drifted during the lifecycle"

    # The write-once store still refuses a second write for the same evidence.
    with pytest.raises(RawEvidenceExistsError):
        store.store_once(case_id, evidence_id, "auth.csv", b"tampered replacement bytes")

    final = client.post(f"/api/evidence/{evidence_id}/verify").json()
    assert final["result"] == terminology.INTEGRITY_VERIFIED
    assert final["computed_hash"] == original_hash


def test_raw_store_still_exposes_no_mutation_operations():
    store = RawEvidenceStore(config.EVIDENCE_STORE_DIR)
    mutation_names = {
        "write",
        "overwrite",
        "truncate",
        "replace",
        "update",
        "delete",
        "remove",
        "rewrite",
        "rename",
    }
    public_api = {name for name in dir(store) if not name.startswith("_")}
    assert not (public_api & mutation_names)
    assert not (set(dir(RawEvidenceStore)) & mutation_names)
    source = raw_store_module.__file__
    assert '"xb"' in open(source, encoding="utf-8").read()


# ---------------------------------------------------------------------------
# Concurrency smoke (Phase 9) — concurrent read-only requests stay consistent
# ---------------------------------------------------------------------------

def test_concurrent_reads_are_consistent(client, make_case, upload_evidence):
    result = _run_full_pipeline(client, make_case, upload_evidence)
    case_id = result["case"]["case_id"]

    def read_workspace(_):
        body = client.get(f"/api/cases/{case_id}/workspace")
        assert body.status_code == 200
        payload = body.json()
        assert payload["case"]["evidence_count"] == 4
        return payload["case"]["event_count"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        event_counts = list(pool.map(read_workspace, range(16)))

    assert len(event_counts) == 16
    # Repeated read-only rebuilds must not mutate the persisted row counts.
    assert len(set(event_counts)) == 1
    again = client.get(f"/api/cases/{case_id}/workspace").json()
    assert again["case"]["evidence_count"] == 4
    assert again["case"]["event_count"] == event_counts[0]


# ---------------------------------------------------------------------------
# Database reliability (Phase 9) — idempotent init + enforced foreign keys
# ---------------------------------------------------------------------------

def test_init_db_is_idempotent_and_foreign_keys_enforced():
    init_db()
    init_db()
    cases = (
        engine.execution_options()
        .connect()
        .execute(text("SELECT COUNT(*) FROM cases"))
        .scalar()
    )
    assert cases >= 0  # schema is queryable after repeated initialisation

    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
