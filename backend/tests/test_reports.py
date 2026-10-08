"""Phase 6 tests — Forensic Report & Investigation Presentation Layer.

These tests prove that reports are immutable, case-scoped, deterministic
snapshots built only from persisted Phase 1–5 data, and that report wording
stays honest (no new analysis, no ML inference, no LLM, no admissibility or
probability claims).

Report contract under test:
* payload = identity fields + deterministic ``sections`` (15 sections)
* ``sections`` must be identical for two generations over unchanged data
* snapshots are append-only and never modified once written
* reports never leak across cases (404)
* integrity states are VERIFIED / MISMATCH / NOT VERIFIED / NO CHECK AVAILABLE
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app import terminology
from app.db import SessionLocal
from app.models import (
    Case,
    Evidence,
    MlFinding,
    RuleFinding,
    SeverityLevel,
    utcnow,
)
from app.services.report_service import _SECTION_NAMES

# ---------------------------------------------------------------------------
# Evidence fixtures (synthetic, deterministic — mirrors test_analysis.py)
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
        rows.append((_stamp(_BASE + timedelta(minutes=4 * index)), user, host, ip,
                     "login", "success"))
    for minute in (48, 49, 50):
        rows.append((_stamp(_BASE + timedelta(minutes=minute)), "usr_dave", "WS-04",
                     "10.20.30.8", "login", "failure"))
    rows.append((_stamp(_BASE + timedelta(minutes=51)), "usr_dave", "WS-04",
                 "10.20.30.8", "login", "success"))
    return rows


FILE_WRITES = [
    ("2026-10-05 09:00:00", "usr_dave", "FS-01", "C:\\Shares\\a.doc", "write"),
    ("2026-10-05 09:02:00", "usr_dave", "FS-01", "C:\\Shares\\b.doc", "write"),
    ("2026-10-05 09:04:00", "usr_dave", "FS-01", "C:\\Shares\\c.doc", "write"),
    ("2026-10-05 09:06:00", "usr_dave", "FS-01", "C:\\Shares\\d.doc", "write"),
    ("2026-10-05 09:08:00", "usr_dave", "FS-01", "C:\\Shares\\e.doc", "write"),
    ("2026-10-05 09:10:00", "usr_dave", "FS-01", "C:\\Shares\\f.doc", "write"),
    ("2026-10-05 09:12:00", "usr_dave", "FS-01", "C:\\Shares\\g.doc", "write"),
]
FILE_RENAMES = [
    ("2026-10-05 09:20:00", "usr_dave", "FS-01", "C:\\Shares\\a.doc.locked", "rename"),
    ("2026-10-05 09:22:00", "usr_dave", "FS-01", "C:\\Shares\\b.doc.locked", "rename"),
    ("2026-10-05 09:24:00", "usr_dave", "FS-01", "C:\\Shares\\c.doc.locked", "rename"),
]

PROCESS_ROWS = [
    ("2026-10-05 09:30:00", "usr_dave", "SRV-01", "powershell.exe",
     "powershell.exe -enc SQBFAFgA", "start"),
]

NETWORK_ROWS = [
    ("2026-10-05 09:31:00", "SRV-01", "10.20.30.9", "93.184.216.34", "443", "tcp"),
    ("2026-10-05 09:33:00", "SRV-01", "10.20.30.9", "93.184.216.34", "8080", "tcp"),
]


def _csv(header: str, rows: list[tuple]) -> bytes:
    lines = [header.rstrip("\n")]
    lines.extend(",".join(str(cell) for cell in row) for row in rows)
    return ("\n".join(lines) + "\n").encode()


AUTH_CSV = _csv("timestamp,user,host,source_ip,action,result", _auth_rows())
FILE_CSV = _csv("timestamp,user,host,file_path,action", FILE_WRITES + FILE_RENAMES)
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


def _generate(client, case_id: str, **payload) -> dict:
    response = client.post(f"/api/cases/{case_id}/reports", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _full_pipeline(client, make_case, upload_evidence) -> str:
    case = make_case()
    for filename, data, evidence_type in EVIDENCE_FILES:
        response = upload_evidence(
            case["case_id"], filename, data, evidence_type=evidence_type
        )
        assert response.status_code == 201, response.text
    assert client.post(f"/api/cases/{case['case_id']}/process", json={}).status_code == 200
    assert client.post(f"/api/cases/{case['case_id']}/analyze", json={}).status_code == 200
    assert client.post(f"/api/cases/{case['case_id']}/correlate", json={}).status_code == 200
    return case["case_id"]


# ---------------------------------------------------------------------------
# Creation & shape
# ---------------------------------------------------------------------------

def test_create_report_returns_full_snapshot_shape(client, make_case):
    case = make_case()
    body = _generate(client, case["case_id"])

    assert body["report_id"] == "RPT-000001"
    assert body["case_id"] == case["case_id"]
    assert body["title"] == terminology.REPORT_TITLE
    assert body["report_version"] == terminology.REPORT_VERSION
    assert body["schema"] == terminology.REPORT_SCHEMA
    assert body["status"] == terminology.REPORT_STATUS
    assert body["generated_by"] == "investigator"
    assert body["generated_at"]

    assert sorted(body["sections"].keys()) == sorted(_SECTION_NAMES)
    assert len(_SECTION_NAMES) == 15

    raw = client.get(
        f"/api/cases/{case['case_id']}/reports/{body['report_id']}/json"
    ).json()
    assert sorted(raw.keys()) == ["metadata", "sections"]
    assert raw["metadata"]["report_id"] == body["report_id"]
    assert raw["sections"] == body["sections"]


def test_create_report_honours_title_and_actor(client, make_case):
    case = make_case()
    body = _generate(client, case["case_id"], title="  Custom Title  ", actor="lead")

    assert body["title"] == "Custom Title"
    assert body["generated_by"] == "lead"

    custody_log = client.get(f"/api/cases/{case['case_id']}/custody").json()
    generated = [e for e in custody_log if e["action"] == "Report Generated"]
    assert len(generated) == 1
    assert generated[0]["actor"] == "lead"
    assert generated[0]["details"]["report_id"] == body["report_id"]


def test_create_report_title_and_actor_limits(client, make_case):
    case = make_case()
    too_long_title = client.post(
        f"/api/cases/{case['case_id']}/reports",
        json={"title": "x" * 256},
    )
    assert too_long_title.status_code == 422

    too_long_actor = client.post(
        f"/api/cases/{case['case_id']}/reports",
        json={"actor": "x" * 128},
    )
    assert too_long_actor.status_code == 422

    blank = _generate(client, case["case_id"], title="  ")
    assert blank["title"] == terminology.REPORT_TITLE

    empty_payload = client.post(f"/api/cases/{case['case_id']}/reports", json={})
    assert empty_payload.status_code == 201


def test_report_ids_are_global_sequence(client, make_case):
    first = make_case(name="Sequence A")
    second = make_case(name="Sequence B")
    a = _generate(client, first["case_id"])
    b = _generate(client, second["case_id"])
    # The test DB is shared across the suite, so compare relative positions:
    # consecutive generations must take the next slot of ONE global sequence.
    na = int(a["report_id"].split("-")[1])
    nb = int(b["report_id"].split("-")[1])
    assert nb == na + 1, "report IDs must come from a single global sequence"


def test_report_list_newest_first_with_summary_shape(client, make_case):
    case = make_case()
    ids = [_generate(client, case["case_id"])["report_id"] for _ in range(3)]

    response = client.get(f"/api/cases/{case['case_id']}/reports")
    assert response.status_code == 200, response.text
    reports = response.json()
    assert [r["report_id"] for r in reports] == list(reversed(ids))
    entry = reports[0]
    assert set(entry.keys()) == {
        "report_id", "case_id", "title", "report_version",
        "schema", "status", "generated_at", "generated_by",
    }
    assert "sections" not in entry


# ---------------------------------------------------------------------------
# Section content
# ---------------------------------------------------------------------------

def test_empty_case_report_is_honest_about_missing_analysis(client, make_case):
    case = make_case()
    body = _generate(client, case["case_id"])
    sections = body["sections"]

    assert sections["investigation_conclusion"]["statement"] == terminology.REPORT_NO_ANALYSIS
    assert sections["executive_summary"]["note"] == terminology.REPORT_NO_ANALYSIS
    assert sections["integrity_verification"]["status"] == terminology.REPORT_INTEGRITY_NO_CHECK
    assert sections["evidence_inventory"]["count"] == 0
    assert sections["key_findings"]["findings"] == []
    assert sections["finding_traceability"]["traces"] == []
    assert sections["activity_groups"]["groups"] == []
    assert len(sections["limitations"]["notices"]) == 6
    # Identity fields must NOT leak into the deterministic header.
    assert "report_id" not in sections["header"]
    assert "generated_at" not in sections["header"]


def test_full_pipeline_report_sections_correct(client, make_case, upload_evidence):
    case_id = _full_pipeline(client, make_case, upload_evidence)
    body = _generate(client, case_id)
    sections = body["sections"]

    inventory = sections["evidence_inventory"]
    assert inventory["count"] == 4
    assert {item["evidence_type"] for item in inventory["items"]} == {
        "authentication", "file_activity", "process", "network",
    }
    assert all(len(item["sha256"]) == 64 for item in inventory["items"])

    processing = sections["processing_summary"]
    assert processing["run_count"] == 4
    assert all(run["records_normalized"] > 0 for run in processing["runs"])

    findings = sections["key_findings"]
    assert findings["total"] >= 5
    rule_ids = {f["rule_id"] for f in findings["findings"] if f["kind"] == "rule"}
    assert {"AUTH-001", "FILE-001", "PROC-001", "NET-001"} <= rule_ids
    assert findings["note"] == terminology.ANALYSIS_SCOPE_NOTE

    traces = sections["finding_traceability"]
    assert traces["traced_findings"] >= 1
    first = traces["traces"][0]
    assert first["unavailable"] is False
    assert first["ladder"] == list(terminology.TRACEABILITY_STEPS)
    assert all(t["linked_events"] for t in traces["traces"])

    corr = sections["cross_source_correlation"]
    assert corr["total"] > 0
    assert corr["disclaimer"] == terminology.CORRELATION_DISCLAIMER

    groups = sections["activity_groups"]
    assert groups["total"] > 0
    assert groups["note"] == terminology.CORRELATION_GROUP_NOTE

    timeline = sections["incident_timeline"]
    assert timeline["total"] > 0
    assert timeline["disclaimer"] == terminology.TIMELINE_DISCLAIMER
    assert any(entry["significance"] in ("NOTABLE", "SUSPICIOUS") for entry in timeline["entries"])

    graph = sections["evidence_graph_summary"]
    assert graph["node_type_counts"]["evidence"] == 4
    assert graph["node_type_counts"]["finding"] >= 1
    assert graph["edge_relation_counts"]["contains"] >= 4
    assert graph["disclaimer"] == terminology.CORRELATION_DISCLAIMER

    ml = sections["ai_ml_explanation"]
    assert ml["statement"] == terminology.REPORT_ML_STATEMENT
    assert ml["disclaimer"] == terminology.ANOMALY_DISCLAIMER
    assert ml["ml_findings"] is not None

    conclusion = sections["investigation_conclusion"]
    assert conclusion["statement"] == terminology.REPORT_CONCLUSION_WITH_CORRELATION

    review = sections["investigator_review"]
    assert "finding_status_counts" in review

    # Every claims-bearing string must stay guard-safe (no admissibility claims).
    blobs = " ".join(
        str(sections[name]) for name in ("executive_summary", "investigation_conclusion", "limitations")
    )
    assert "admissible" not in blobs.lower()


def test_report_integrity_verified_section(client, make_case, upload_evidence):
    case = make_case()
    uploaded = upload_evidence(
        case["case_id"], "auth.csv", b"timestamp,user,action\n2026-01-01T00:00:00Z,alice,login\n"
    ).json()
    response = client.post(f"/api/evidence/{uploaded['evidence_id']}/verify")
    assert response.status_code == 200, response.text

    body = _generate(client, case["case_id"])
    integrity = body["sections"]["integrity_verification"]
    assert integrity["status"] == terminology.INTEGRITY_VERIFIED
    assert integrity["verified_items"] == 1
    item = integrity["items"][0]
    assert item["result"] == terminology.INTEGRITY_VERIFIED
    assert item["computed_hash"] == item["expected_hash"] == uploaded["sha256"]
    assert integrity["explanation"] == terminology.REPORT_INTEGRITY_VERIFIED_EXPLAIN


def test_report_integrity_mismatch_section(client, make_case, upload_evidence):
    case = make_case()
    uploaded = upload_evidence(
        case["case_id"], "auth.csv", b"timestamp,user,action\n2026-01-01T00:00:00Z,alice,login\n"
    ).json()

    db = SessionLocal()
    try:
        evidence = db.scalar(select(Evidence).where(Evidence.evidence_id == uploaded["evidence_id"]))
        evidence.original_hash = "0" * 64
        db.commit()
    finally:
        db.close()

    response = client.post(f"/api/evidence/{uploaded['evidence_id']}/verify")
    assert response.status_code == 200, response.text

    body = _generate(client, case["case_id"])
    integrity = body["sections"]["integrity_verification"]
    assert integrity["status"] == terminology.INTEGRITY_MISMATCH
    assert integrity["mismatch_items"] == 1
    assert integrity["items"][0]["expected_hash"] == "0" * 64
    assert integrity["explanation"] == terminology.REPORT_INTEGRITY_MISMATCH_EXPLAIN


def test_report_integrity_no_check_without_verification(client, make_case):
    case = make_case()
    # Evidence with no IntegrityCheck on record (upload always writes an
    # ingest-time check, so this state is constructed directly).
    db = SessionLocal()
    try:
        case_row = db.scalar(select(Case).where(Case.case_id == case["case_id"]))
        db.add(
            Evidence(
                evidence_id="EVD-NOCHECK-0001",
                case_id=case_row.id,
                original_filename="unverified.csv",
                stored_filename="unverified.csv",
                source_description="",
                file_size=16,
                mime_type="text/csv",
                sha256="a" * 64,
                original_hash="a" * 64,
                uploaded_at=utcnow(),
            )
        )
        db.commit()
    finally:
        db.close()

    body = _generate(client, case["case_id"])
    integrity = body["sections"]["integrity_verification"]
    assert integrity["status"] == terminology.REPORT_INTEGRITY_NO_CHECK


def test_report_high_severity_note_appended_to_conclusion(client, make_case, upload_evidence):
    case_id = _full_pipeline(client, make_case, upload_evidence)
    body = _generate(client, case_id)
    conclusion = body["sections"]["investigation_conclusion"]
    assert terminology.REPORT_HIGH_SEVERITY_NOTE in conclusion["notes"]


# ---------------------------------------------------------------------------
# Traceability
# ---------------------------------------------------------------------------

def test_trace_is_unavailable_for_finding_without_events(client, make_case):
    case = make_case()
    db = SessionLocal()
    try:
        case_row = db.scalar(select(Case).where(Case.case_id == case["case_id"]))
        # Continue the global numeric sequence so later analyze runs can still
        # parse the max finding_uid (analysis_service relies on 'RFND-NNNNNN').
        last = db.scalar(select(func.max(RuleFinding.finding_uid)))
        finding_uid = (
            f"RFND-{int(last.split('-')[1]) + 1:06d}" if last else "RFND-000001"
        )
        db.add(
            RuleFinding(
                finding_uid=finding_uid,
                case_id=case_row.id,
                run_id=None,
                rule_id="AUTH-001",
                title="Finding without events",
                description="",
                severity=SeverityLevel.MEDIUM.value,
                confidence=0.5,
                explanation="",
                reasons=None,
                composite_suspicion_score=None,
                components=None,
                triggered_event_ids=[],
                evidence_ids=[],
                status="New",
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        db.commit()
    finally:
        db.close()

    body = _generate(client, case["case_id"])
    trace = body["sections"]["finding_traceability"]["traces"][0]
    assert trace["finding_id"] == finding_uid
    assert trace["unavailable"] is True
    assert trace["note"] == terminology.REPORT_TRACE_UNAVAILABLE
    assert trace["linked_events"] == []


def test_trace_ladder_reaches_recorded_sha256(client, make_case, upload_evidence):
    case_id = _full_pipeline(client, make_case, upload_evidence)
    body = _generate(client, case_id)
    trace = body["sections"]["finding_traceability"]["traces"][0]
    hashes = {
        item["recorded_sha256"]
        for item in trace["linked_events"]
        if item.get("recorded_sha256")
    }
    assert hashes, "every traced event must reach a recorded SHA-256"
    assert all(len(h) == 64 for h in hashes)


# ---------------------------------------------------------------------------
# Determinism & snapshot immutability
# ---------------------------------------------------------------------------

def test_determinism_two_generations_identical_sections(client, make_case, upload_evidence):
    case_id = _full_pipeline(client, make_case, upload_evidence)
    first = _generate(client, case_id)
    second = _generate(client, case_id, title="Different title", actor="different")

    # Identity fields differ; deterministic content must not.
    assert first["report_id"] != second["report_id"]
    assert first["generated_at"] != second["generated_at"]
    assert first["title"] != second["title"]
    assert first["sections"] == second["sections"]


def test_snapshot_is_immutable_and_later_report_reflects_new_state(
    client, make_case, upload_evidence
):
    case = make_case()
    upload_evidence(
        case["case_id"], "auth.csv", b"timestamp,user,action\n2026-01-01T00:00:00Z,alice,login\n"
    )

    before = _generate(client, case["case_id"])
    before_sections = before["sections"]
    assert before_sections["evidence_inventory"]["count"] == 1
    # upload records an ingest-time integrity check, so it is VERIFIED at once.
    assert before_sections["integrity_verification"]["status"] == terminology.INTEGRITY_VERIFIED

    upload_evidence(
        case["case_id"], "auth2.csv", b"timestamp,user,action\n2026-01-01T01:00:00Z,bob,login\n"
    )
    after = _generate(client, case["case_id"])

    # Snapshot A must be unchanged even though the case state moved on.
    stored = client.get(
        f"/api/cases/{case['case_id']}/reports/{before['report_id']}"
    ).json()
    assert stored["sections"] == before_sections
    assert stored["sections"]["evidence_inventory"]["count"] == 1

    # Snapshot B reflects the new state.
    assert after["sections"]["evidence_inventory"]["count"] == 2
    assert after["sections"] != before_sections


# ---------------------------------------------------------------------------
# Cross-case isolation
# ---------------------------------------------------------------------------

def test_report_is_case_scoped_never_leaks_across_cases(client, make_case):
    case_a = make_case(name="Isolation A")
    case_b = make_case(name="Isolation B")
    report = _generate(client, case_a["case_id"])

    for endpoint in (
        f"/api/cases/{case_b['case_id']}/reports/{report['report_id']}",
        f"/api/cases/{case_b['case_id']}/reports/{report['report_id']}/json",
    ):
        response = client.get(endpoint)
        assert response.status_code == 404, endpoint
        assert response.json()["error"]["code"] == "REPORT_NOT_FOUND"

    # The case's own report remains reachable.
    assert client.get(
        f"/api/cases/{case_a['case_id']}/reports/{report['report_id']}"
    ).status_code == 200
    # Case B sees only its own (empty) history.
    assert client.get(f"/api/cases/{case_b['case_id']}/reports").json() == []


def test_unknown_case_and_unknown_report_return_404(client, make_case):
    case = make_case()
    assert client.post("/api/cases/CASE-NOPE/reports", json={}).status_code == 404
    assert client.get(f"/api/cases/{case['case_id']}/reports/RPT-999999").status_code == 404
    assert (
        client.get(f"/api/cases/{case['case_id']}/reports/RPT-999999/json").status_code
        == 404
    )


def test_malformed_report_ids_never_match(client, make_case):
    case = make_case()
    for report_id in ("RPT-ABC", "..%2F..%2Fetc%2Fpasswd", "RPT-000001/../../etc"):
        response = client.get(f"/api/cases/{case['case_id']}/reports/{report_id}")
        assert response.status_code in (404, 422), report_id


# ---------------------------------------------------------------------------
# Reporting is read-only over pipeline data
# ---------------------------------------------------------------------------

def test_generation_does_not_alter_pipeline_data(client, make_case, upload_evidence):
    case_id = _full_pipeline(client, make_case, upload_evidence)

    db = SessionLocal()
    try:
        before = {
            "sha256": sorted(db.scalars(select(Evidence.sha256)).all()),
            "rule_findings": db.scalar(select(func.count()).select_from(RuleFinding)),
            "ml_findings": db.scalar(select(func.count()).select_from(MlFinding)),
            "evidence_count": db.scalar(select(func.count()).select_from(Evidence)),
        }
    finally:
        db.close()

    _generate(client, case_id)
    _generate(client, case_id)

    db = SessionLocal()
    try:
        after = {
            "sha256": sorted(db.scalars(select(Evidence.sha256)).all()),
            "rule_findings": db.scalar(select(func.count()).select_from(RuleFinding)),
            "ml_findings": db.scalar(select(func.count()).select_from(MlFinding)),
            "evidence_count": db.scalar(select(func.count()).select_from(Evidence)),
        }
    finally:
        db.close()

    assert before == after, "report generation must not mutate pipeline data"


# ---------------------------------------------------------------------------
# ML abstention honesty
# ---------------------------------------------------------------------------

def test_ml_abstention_is_reported_honestly(client, make_case, upload_evidence):
    case = make_case()
    upload_evidence(
        case["case_id"],
        "auth.csv",
        b"timestamp,user,action\n2026-01-01T00:00:00Z,alice,login\n",
    )
    assert client.post(f"/api/cases/{case['case_id']}/process", json={}).status_code == 200
    assert client.post(f"/api/cases/{case['case_id']}/analyze", json={}).status_code == 200

    body = _generate(client, case["case_id"])
    ml = body["sections"]["ai_ml_explanation"]
    assert ml["statement"] == terminology.REPORT_ML_STATEMENT
    # Whatever the engine decided, the report must reference the abstention
    # wording when the analysis run recorded an abstention.
    assert ml["abstain_note"] in (None, terminology.ML_ABSTAIN_NOTE)


def test_ml_abstain_note_from_latest_run_is_included(client, make_case, upload_evidence):
    case = make_case()
    upload_evidence(
        case["case_id"],
        "auth.csv",
        b"timestamp,user,action\n2026-01-01T00:00:00Z,alice,login\n",
    )
    client.post(f"/api/cases/{case['case_id']}/process", json={})
    client.post(f"/api/cases/{case['case_id']}/analyze", json={})

    db = SessionLocal()
    try:
        from app.models import InvestigationRun, RunStage

        case_row = db.scalar(select(Case).where(Case.case_id == case["case_id"]))
        row = (
            db.query(InvestigationRun)
            .filter_by(case_id=case_row.id, stage=RunStage.ANALYZE.value)
            .first()
        )
        stats = dict(row.stats or {})
        stats["abstain_note"] = terminology.ML_ABSTAIN_NOTE
        stats["abstain_reason"] = "fewer than the minimum number of windows"
        row.stats = stats
        db.commit()
    finally:
        db.close()

    body = _generate(client, case["case_id"])
    ml = body["sections"]["ai_ml_explanation"]
    assert ml["abstain_note"] == terminology.ML_ABSTAIN_NOTE
    assert ml["abstain_reason"] == "fewer than the minimum number of windows"


# ---------------------------------------------------------------------------
# Synthetic / demonstration data detection
# ---------------------------------------------------------------------------

def test_synthetic_marker_only_from_ingested_data(client, make_case, upload_evidence):
    case = make_case()
    upload_evidence(
        case["case_id"],
        "auth.csv",
        b"timestamp,user,action\n2026-01-01T00:00:00Z,alice,login\n",
    )
    body = _generate(client, case["case_id"])
    assert body["sections"]["limitations"]["synthetic"] is None

    upload_evidence(
        case["case_id"],
        "demo.csv",
        b"timestamp,user,action,note\n"
        b"2026-01-01T00:00:00Z,bob,login,SYNTHETIC / DEMONSTRATION DATA\n",
    )
    client.post(f"/api/cases/{case['case_id']}/process", json={})
    body = _generate(client, case["case_id"])
    assert body["sections"]["limitations"]["synthetic"] == terminology.DEMO_LABEL
    assert terminology.DEMO_LABEL in body["sections"]["executive_summary"]["overview"]


# ---------------------------------------------------------------------------
# Report content never claims authenticity or probability
# ---------------------------------------------------------------------------

def test_report_wording_never_claims_authenticity_or_probability(client, make_case):
    case = make_case()
    body = _generate(client, case["case_id"])
    data = str(body["sections"])
    lowered = data.lower()
    for banned in (
        "authentic evidence",
        "authenticated",
        "proves malicious activity",
        "proves an attacker",
        "100%",
    ):
        assert banned not in lowered