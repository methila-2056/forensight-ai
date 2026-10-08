"""Phase 8 tests — read-only investigation workspace for one case.

The workspace must only re-shape rows already persisted by Phases 1–6. These
tests prove:

* an empty case is reported honestly (no fabricated figures)
* the full pipeline (process → analyze → correlate → report → assistant) is
  reflected correctly and matches persisted row counts
* per-evidence integrity and processing states come from persisted rows
* the review queue equals the open findings and moves only via the existing
  Phase 3 review endpoint (no Phase 8 review duplicate)
* the endpoint is read-only and deterministic (repeated GET is identical
  apart from the generated_at timestamp)
* workspace data is strictly case-scoped (one case never sees another's rows)
* viewing a workspace does not affect the Phase 7 dashboard
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select

from app import terminology
from app.db import SessionLocal
from app.models import (
    AssistantQuery,
    Case,
    ChainOfCustody,
    Correlation,
    CorrelationRun,
    Evidence,
    ForensicEvent,
    IntegrityCheck,
    IntegrityResult,
    InvestigationGroup,
    InvestigationReport,
    InvestigationRun,
    InvestigatorNote,
    MlFinding,
    ProcessingRun,
    RawRecord,
    RuleFinding,
)

# ---------------------------------------------------------------------------
# Synthetic, deterministic evidence fixtures (mirrors test_dashboard.py)
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


def _workspace(client, case_id: str) -> dict:
    response = client.get(f"/api/cases/{case_id}/workspace")
    assert response.status_code == 200, response.text
    return response.json()


def _db_counts(db) -> dict:
    """Snapshot of persisted row counts for read-only cross-checking."""
    base = select(func.count())
    return {
        "cases": db.scalar(base.select_from(Case)) or 0,
        "evidence": db.scalar(base.select_from(Evidence)) or 0,
        "raw_records": db.scalar(base.select_from(RawRecord)) or 0,
        "forensic_events": db.scalar(base.select_from(ForensicEvent)) or 0,
        "processing_runs": db.scalar(base.select_from(ProcessingRun)) or 0,
        "analysis_runs": db.scalar(base.select_from(InvestigationRun)) or 0,
        "correlation_runs": db.scalar(base.select_from(CorrelationRun)) or 0,
        "correlations": db.scalar(base.select_from(Correlation)) or 0,
        "investigation_groups": db.scalar(base.select_from(InvestigationGroup)) or 0,
        "integrity_checks": db.scalar(base.select_from(IntegrityCheck)) or 0,
        "custody_events": db.scalar(base.select_from(ChainOfCustody)) or 0,
        "rule_findings": db.scalar(base.select_from(RuleFinding)) or 0,
        "ml_findings": db.scalar(base.select_from(MlFinding)) or 0,
        "assistant_queries": db.scalar(base.select_from(AssistantQuery)) or 0,
        "investigation_reports": db.scalar(base.select_from(InvestigationReport)) or 0,
        "investigator_notes": db.scalar(base.select_from(InvestigatorNote)) or 0,
    }


# ---------------------------------------------------------------------------
# Empty case — honest, unpadded workspace state
# ---------------------------------------------------------------------------

def test_workspace_empty_case_is_honest(client, make_case):
    case = make_case(name="Empty Workspace Case")

    body = _workspace(client, case["case_id"])

    assert body["generated_at"]
    assert body["disclaimer"] == terminology.WORKSPACE_DISCLAIMER
    assert body["case"]["case_id"] == case["case_id"]
    assert body["case"]["processing_status"] == terminology.PROCESSING_NOT_PROCESSED
    assert body["case"]["integrity_status"] == terminology.INTEGRITY_UNVERIFIED
    assert body["case"]["evidence_count"] == 0
    assert body["case"]["event_count"] == 0
    assert body["case"]["anomalous_event_count"] == 0
    assert body["case"]["finding_count"] == 0
    assert body["case"]["review_open_items"] == 0
    assert body["case"]["correlation_count"] == 0
    assert body["case"]["activity_group_count"] == 0
    assert body["case"]["report_count"] == 0
    assert body["case"]["synthetic_label"] is None

    assert body["evidence"] == []
    assert body["evidence_summary"]["total"] == 0
    assert body["evidence_summary"]["total_bytes"] == 0
    assert body["processing"]["label"] == terminology.PROCESSING_NOT_PROCESSED
    assert body["processing"]["runs"] == 0
    assert body["integrity_summary"]["checks"] == 0
    assert body["finding_summary"]["total"] == 0
    assert body["review_summary"]["open_items"] == 0
    assert body["review_summary"]["queue"] == []
    assert body["timeline_summary"]["entries"] == []
    assert body["timeline_summary"]["total"] == 0
    assert body["correlation_summary"]["total"] == 0
    assert body["group_summary"]["total"] == 0
    assert body["graph_summary"]["nodes"] == []
    assert body["assistant_summary"]["query_count"] == 0
    assert body["assistant_summary"]["history"] == []
    assert body["report_summary"]["count"] == 0
    assert body["report_summary"]["latest"] is None


# ---------------------------------------------------------------------------
# Full pipeline — every section re-shapes persisted rows
# ---------------------------------------------------------------------------

def test_workspace_full_pipeline_reflects_persisted_rows(client, make_case, upload_evidence):
    case_id = _full_pipeline(client, make_case, upload_evidence)

    with SessionLocal() as db:
        case_pk = db.scalar(select(Case.id).where(Case.case_id == case_id))
        expected_evidence = db.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.case_id == case_pk)
        )
        expected_rules = db.scalar(
            select(func.count())
            .select_from(RuleFinding)
            .where(RuleFinding.case_id == case_pk)
        )
        expected_ml = db.scalar(
            select(func.count())
            .select_from(MlFinding)
            .where(MlFinding.case_id == case_pk)
        )
        expected_correlations = db.scalar(
            select(func.count())
            .select_from(Correlation)
            .where(Correlation.case_id == case_pk)
        )
        expected_groups = db.scalar(
            select(func.count())
            .select_from(InvestigationGroup)
            .where(InvestigationGroup.case_id == case_pk)
        )

    body = _workspace(client, case_id)

    assert body["case"]["processing_status"] == terminology.PROCESSING_COMPLETED
    assert body["processing"]["label"] == terminology.PROCESSING_COMPLETED
    assert body["processing"]["runs"] == expected_evidence
    assert body["processing"]["by_status"]["Completed"] == expected_evidence
    assert body["processing"]["evidence_processed"] == expected_evidence
    assert body["processing"]["records_received"] >= 1
    assert body["processing"]["records_normalized"] >= 1

    assert body["evidence_summary"]["total"] == expected_evidence == 4
    assert len(body["evidence"]) == expected_evidence
    assert body["evidence_summary"]["verified"] == expected_evidence
    assert body["integrity_summary"]["checks"] == expected_evidence
    assert body["integrity_summary"]["verified"] == expected_evidence
    assert body["case"]["integrity_status"] == terminology.INTEGRITY_LATEST_VERIFIED

    assert body["finding_summary"]["total"] == expected_rules + expected_ml
    assert body["finding_summary"]["by_kind"]["rule"] == expected_rules
    assert body["finding_summary"]["by_kind"]["ml"] == expected_ml
    assert body["finding_summary"]["total"] == body["case"]["finding_count"]
    assert body["review_summary"]["total"] == expected_rules + expected_ml
    assert body["review_summary"]["open_items"] == expected_rules + expected_ml
    assert body["review_summary"]["by_status"]["New"] == expected_rules + expected_ml
    assert len(body["review_summary"]["queue"]) == expected_rules + expected_ml

    assert body["timeline_summary"]["case_id"] == case_id
    assert len(body["timeline_summary"]["entries"]) >= 1
    assert body["timeline_summary"]["total"] >= 1

    assert body["correlation_summary"]["total"] == expected_correlations
    assert body["group_summary"]["total"] == expected_groups
    assert body["graph_summary"]["case_id"] == case_id
    assert len(body["graph_summary"]["nodes"]) >= 1
    assert body["case"]["correlation_count"] == expected_correlations
    assert body["case"]["activity_group_count"] == expected_groups

    assert body["assistant_summary"]["query_count"] == 0
    assert body["report_summary"]["count"] == 0
    assert body["case"]["report_count"] == 0


def test_workspace_includes_assistant_and_report_history(client, make_case, upload_evidence):
    case_id = _full_pipeline(client, make_case, upload_evidence)

    ask = client.post(
        f"/api/cases/{case_id}/assistant/query",
        json={"question": "Summarize suspicious findings.", "actor": "tester"},
    )
    assert ask.status_code == 201, ask.text
    report = client.post(f"/api/cases/{case_id}/reports", json={"actor": "tester"})
    assert report.status_code == 201, report.text
    report_id = report.json()["report_id"]

    body = _workspace(client, case_id)

    assert body["assistant_summary"]["query_count"] == 1
    assert len(body["assistant_summary"]["history"]) == 1
    assert body["assistant_summary"]["history"][0]["question"] == (
        "Summarize suspicious findings."
    )
    assert body["assistant_summary"]["history"][0]["case_id"] == case_id

    assert body["report_summary"]["count"] == 1
    assert body["report_summary"]["latest"]["report_id"] == report_id
    assert body["report_summary"]["reports"][0]["report_id"] == report_id
    assert body["case"]["report_count"] == 1


# ---------------------------------------------------------------------------
# Integrity state comes from persisted checks
# ---------------------------------------------------------------------------

def test_workspace_integrity_from_persisted_checks(client, make_case, upload_evidence):
    case_id = _full_pipeline(client, make_case, upload_evidence)

    with SessionLocal() as db:
        case_pk = db.scalar(select(Case.id).where(Case.case_id == case_id))
        evidence = db.scalars(
            select(Evidence).where(Evidence.case_id == case_pk).order_by(Evidence.id)
        ).all()
        target_pk = evidence[0].id
        target_uid = evidence[0].evidence_id

    verify = client.post(f"/api/evidence/{target_uid}/verify")
    assert verify.status_code == 200, verify.text

    body = _workspace(client, case_id)
    target = next(item for item in body["evidence"] if item["evidence_id"] == target_uid)
    # Ingest writes one VERIFIED check per evidence; the explicit verification
    # appends a second VERIFIED check to this evidence item.
    assert target["integrity"]["checks"] == 2
    assert target["integrity"]["verified"] == 2
    assert target["integrity"]["latest"] == "VERIFIED"
    assert body["integrity_summary"]["checks"] == 5
    assert body["integrity_summary"]["verified"] == 5
    assert body["integrity_summary"]["mismatch"] == 0
    assert body["evidence_summary"]["verified"] == 4
    assert body["evidence_summary"]["unverified"] == 0

    with SessionLocal() as db:
        db.add(
            IntegrityCheck(
                evidence_id=target_pk,
                computed_hash="a" * 64,
                expected_hash="b" * 64,
                result=IntegrityResult.MISMATCH,
                actor="test",
            )
        )
        db.commit()

    body = _workspace(client, case_id)
    target = next(item for item in body["evidence"] if item["evidence_id"] == target_uid)
    assert target["integrity"]["checks"] == 3
    assert target["integrity"]["mismatch"] == 1
    assert target["integrity"]["latest"] == "MISMATCH"
    assert body["integrity_summary"]["checks"] == 6
    assert body["integrity_summary"]["mismatch"] == 1
    assert body["case"]["integrity_status"] == terminology.INTEGRITY_LATEST_MISMATCH


# ---------------------------------------------------------------------------
# Review moves only through the existing Phase 3 endpoint, not a Phase 8 one
# ---------------------------------------------------------------------------

def test_workspace_review_tracks_existing_review_endpoint(client, make_case, upload_evidence):
    case_id = _full_pipeline(client, make_case, upload_evidence)

    listing = client.get(f"/api/cases/{case_id}/findings", params={"limit": 500})
    assert listing.status_code == 200, listing.text
    first = listing.json()["findings"][0]

    # The workspace has no review endpoint of its own: reviewers move findings
    # through the existing Phase 3 review flow, and the workspace reflects it.
    under = client.patch(
        f"/api/cases/{case_id}/findings/{first['finding_id']}",
        json={"status": "Under Review", "note": "Workspace test review.", "author": "tester"},
    )
    assert under.status_code == 200, under.text
    confirmed = client.patch(
        f"/api/cases/{case_id}/findings/{first['finding_id']}",
        json={"status": "Confirmed", "note": "Confirmed from the workspace.", "author": "tester"},
    )
    assert confirmed.status_code == 200, confirmed.text

    body = _workspace(client, case_id)
    assert body["review_summary"]["by_status"]["Confirmed"] == 1
    assert body["review_summary"]["open_items"] == (
        body["finding_summary"]["total"] - 1
    )
    assert body["case"]["review_open_items"] == body["review_summary"]["open_items"]
    assert all(
        item["status"] != "Confirmed" for item in body["review_summary"]["queue"]
    )


# ---------------------------------------------------------------------------
# Synthetic label from the demo flag
# ---------------------------------------------------------------------------

def test_workspace_demo_case_is_labelled_synthetic(client, make_case):
    case = make_case(name="Workspace Demo Case")
    with SessionLocal() as db:
        row = db.scalar(select(Case).where(Case.case_id == case["case_id"]))
        row.demo = True
        db.commit()

    body = _workspace(client, case["case_id"])
    assert body["case"]["demo"] is True
    assert body["case"]["synthetic_label"] == terminology.DEMO_LABEL


# ---------------------------------------------------------------------------
# Unknown case → documented 404
# ---------------------------------------------------------------------------

def test_workspace_unknown_case_returns_404(client):
    response = client.get("/api/cases/CASE-DOES-NOT-EXIST/workspace")
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"]["code"] == "CASE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Read-only guarantee
# ---------------------------------------------------------------------------

def test_workspace_is_read_only(client, make_case, upload_evidence):
    case_id = _full_pipeline(client, make_case, upload_evidence)

    with SessionLocal() as db:
        before = _db_counts(db)

    body = _workspace(client, case_id)

    with SessionLocal() as db:
        after = _db_counts(db)

    assert after == before
    assert body["case"]["evidence_count"] == 4


# ---------------------------------------------------------------------------
# Determinism — repeated GET identical apart from generated_at
# ---------------------------------------------------------------------------

def test_workspace_is_deterministic(client, make_case, upload_evidence):
    case_id = _full_pipeline(client, make_case, upload_evidence)
    client.post(
        f"/api/cases/{case_id}/assistant/query",
        json={"question": "Summarize suspicious findings.", "actor": "tester"},
    )
    client.post(f"/api/cases/{case_id}/reports", json={})

    first = _workspace(client, case_id)
    second = _workspace(client, case_id)

    first["generated_at"] = None
    second["generated_at"] = None
    assert first == second


# ---------------------------------------------------------------------------
# Case isolation — one case never sees another case's rows
# ---------------------------------------------------------------------------

def test_workspace_is_case_scoped(client, make_case, upload_evidence):
    case_a = _full_pipeline(client, make_case, upload_evidence)
    case_b = make_case(name="Isolated Case B")

    body_b = _workspace(client, case_b["case_id"])

    assert body_b["case"]["evidence_count"] == 0
    assert body_b["case"]["finding_count"] == 0
    assert body_b["case"]["event_count"] == 0
    assert body_b["evidence"] == []
    assert body_b["finding_summary"]["total"] == 0
    assert body_b["review_summary"]["queue"] == []
    assert body_b["timeline_summary"]["entries"] == []
    assert body_b["correlation_summary"]["total"] == 0
    assert body_b["group_summary"]["total"] == 0
    assert body_b["graph_summary"]["nodes"] == []
    assert body_b["assistant_summary"]["query_count"] == 0
    assert body_b["report_summary"]["count"] == 0

    body_a = _workspace(client, case_a)
    assert body_a["case"]["evidence_count"] == 4
    assert body_a["finding_summary"]["total"] >= 1


# ---------------------------------------------------------------------------
# Phase 7 dashboard unchanged by dialog
# ---------------------------------------------------------------------------

def test_workspace_does_not_affect_dashboard(client, make_case, upload_evidence):
    case_id = _full_pipeline(client, make_case, upload_evidence)

    first = client.get("/api/dashboard")
    assert first.status_code == 200, first.text

    _workspace(client, case_id)

    second = client.get("/api/dashboard")
    assert second.status_code == 200, second.text

    first_body = first.json()
    second_body = second.json()
    first_body["generated_at"] = None
    second_body["generated_at"] = None
    assert first_body == second_body