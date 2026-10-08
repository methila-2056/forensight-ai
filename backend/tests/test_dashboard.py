"""Phase 7 tests — read-only dashboard & per-case KPI aggregation.

The dashboard must only aggregate rows already persisted by Phases 1–6. These
tests prove:

* an empty deployment reports zero counts (never fabricated figures)
* a case with evidence but no pipeline activity still aggregates honestly
* the full pipeline (process → analyze → correlate) is reflected correctly
* per-case KPIs match the rows that exist per case
* demo-flagged cases and raw-record demonstration markers surface the
  canonical SYNTHETIC / DEMONSTRATION DATA label
* the endpoint is read-only: it never writes or mutates persisted data
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
# Synthetic, deterministic evidence fixtures (mirrors test_reports.py)
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


def _dashboard(client) -> dict:
    response = client.get("/api/dashboard")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Empty deployment — zeros, no fabricated figures
# ---------------------------------------------------------------------------

def _db_counts(db) -> dict:
    """Snapshot of persisted row counts for dashboard cross-checking."""
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


def test_dashboard_aggregates_only_persisted_rows(client):
    """Every reported figure equals the persisted row count — never fabricated."""
    with SessionLocal() as db:
        expected = _db_counts(db)
    body = _dashboard(client)

    assert body["generated_at"]
    assert body["totals"] == expected
    assert len(body["cases"]) == expected["cases"]
    assert body["findings"]["by_kind"] == {
        "rule": expected["rule_findings"],
        "ml": expected["ml_findings"],
    }
    assert body["findings"]["total"] == (
        expected["rule_findings"] + expected["ml_findings"]
    )
    assert body["ml"]["ml_findings"] == expected["ml_findings"]
    assert body["integrity"]["checks"] == expected["integrity_checks"]
    assert body["custody"]["events"] == expected["custody_events"]
    assert body["processing"]["runs"] == expected["processing_runs"]
    assert body["runs"]["analysis_by_status"]["Completed"] >= 0

    # Keys are the canonical enum values, zero-filled.
    assert set(body["findings"]["by_severity"]) == {
        "Low", "Medium", "High", "Critical",
    }
    assert set(body["findings"]["by_status"]) == {
        "New", "Under Review", "Confirmed", "Dismissed",
    }
    assert set(body["processing"]["by_status"]) == {
        "Pending", "Processing", "Completed", "Partial", "Failed",
    }
    assert set(body["runs"]["analysis_by_status"]) == {
        "Pending", "Running", "Completed", "Failed",
    }
    assert set(body["runs"]["correlation_by_status"]) == {
        "Pending", "Running", "Completed", "Failed",
    }


# ---------------------------------------------------------------------------
# Case-only activity (no pipeline) — honest per-case KPI
# ---------------------------------------------------------------------------

def test_dashboard_reflects_case_without_pipeline(client, make_case):
    case = make_case(name="Quiet Case", severity="Medium")
    body = _dashboard(client)

    with SessionLocal() as db:
        assert body["totals"]["cases"] == _db_counts(db)["cases"]

    kpi = next(item for item in body["cases"] if item["case_id"] == case["case_id"])
    assert kpi["name"] == "Quiet Case"
    assert kpi["status"] == "Active"
    assert kpi["severity"] == "Medium"
    assert kpi["demo"] is False
    assert kpi["synthetic_label"] is None
    assert kpi["evidence_count"] == 0
    assert kpi["event_count"] == 0
    assert kpi["anomalous_event_count"] == 0
    assert kpi["rule_findings"] == 0
    assert kpi["ml_findings"] == 0
    assert kpi["processing_runs"] == 0
    assert kpi["correlations"] == 0
    assert kpi["activity_groups"] == 0
    assert kpi["reports"] == 0
    assert kpi["assistant_queries"] == 0


# ---------------------------------------------------------------------------
# Full pipeline — aggregates reflect persisted rows exactly
# ---------------------------------------------------------------------------

def test_full_pipeline_matches_persisted_rows(client, make_case, upload_evidence):
    with SessionLocal() as db:
        before = _db_counts(db)

    case_id = _full_pipeline(client, make_case, upload_evidence)
    body = _dashboard(client)

    with SessionLocal() as db:
        after = _db_counts(db)

    assert after["cases"] == before["cases"] + 1
    assert after["evidence"] == before["evidence"] + 4
    assert after["processing_runs"] == before["processing_runs"] + 4
    assert after["analysis_runs"] == before["analysis_runs"] + 1
    assert after["correlation_runs"] == before["correlation_runs"] + 1
    assert after["rule_findings"] >= before["rule_findings"] + 1
    assert after["ml_findings"] >= before["ml_findings"]

    assert body["totals"] == after
    assert body["findings"]["total"] == (
        after["rule_findings"] + after["ml_findings"]
    )
    assert body["findings"]["by_kind"]["rule"] == after["rule_findings"]
    assert body["findings"]["by_kind"]["ml"] == after["ml_findings"]

    assert body["ml"]["completed_runs"] == after["analysis_runs"]
    assert body["ml"]["windows_total"] >= 1
    assert body["processing"]["runs"] == after["processing_runs"]
    assert body["processing"]["by_status"]["Completed"] == after["processing_runs"]
    assert body["processing"]["records_received"] >= 1
    assert body["processing"]["records_normalized"] >= 1
    assert body["runs"]["analysis_by_status"]["Completed"] >= 1
    assert body["runs"]["correlation_by_status"]["Completed"] >= 1

    # Per-case KPI matches the same persisted rows for this new case.
    kpi = next(item for item in body["cases"] if item["case_id"] == case_id)
    assert kpi["evidence_count"] == 4
    assert kpi["processing_runs"] == 4
    assert kpi["rule_findings"] == after["rule_findings"] - before["rule_findings"]
    assert kpi["ml_findings"] == after["ml_findings"] - before["ml_findings"]
    assert kpi["synthetic_label"] is None or kpi["synthetic_label"] == terminology.DEMO_LABEL


# ---------------------------------------------------------------------------
# Synthetic marking — demo flag and raw-record demonstration marker
# ---------------------------------------------------------------------------

def test_demo_case_is_labelled_synthetic(client, make_case):
    make_case(name="Demo Case", severity="High")
    body = _dashboard(client)
    with SessionLocal() as db:
        row = db.scalar(select(Case).where(Case.name == "Demo Case"))
        row.demo = True
        db.commit()
    body = _dashboard(client)

    kpi = body["cases"][0]
    assert kpi["demo"] is True
    assert kpi["synthetic_label"] == terminology.DEMO_LABEL


def test_raw_record_marker_labels_synthetic(client, make_case, upload_evidence):
    case = make_case(name="Marker Case")
    marker_line = (
        f"{_stamp(_BASE + timedelta(hours=1))},daemon,SVC-01,10.1.1.2,login,"
        f"success,{terminology.DEMO_LABEL}"
    )
    data = (
        "timestamp,user,host,source_ip,action,result\n"
        "2026-10-05 09:59:00,daemon,SVC-01,10.1.1.1,login,success\n"
        + marker_line + "\n"
    ).encode()
    response = upload_evidence(case["case_id"], "marker.csv", data, evidence_type="authentication")
    assert response.status_code == 201, response.text
    assert client.post(f"/api/cases/{case['case_id']}/process", json={}).status_code == 200

    body = _dashboard(client)
    kpi = next(item for item in body["cases"] if item["case_id"] == case["case_id"])
    assert kpi["demo"] is False
    assert kpi["synthetic_label"] == terminology.DEMO_LABEL


# ---------------------------------------------------------------------------
# Read-only guarantee
# ---------------------------------------------------------------------------

def test_dashboard_is_read_only(client, make_case):
    make_case()
    make_case()

    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(Case))

    body = _dashboard(client)
    with SessionLocal() as db:
        after_cases = db.scalar(select(func.count()).select_from(Case))
        after_findings = db.scalar(
            select(func.count()).select_from(RuleFinding)
        ) + db.scalar(select(func.count()).select_from(MlFinding))
        after_evidence = db.scalar(select(func.count()).select_from(Evidence))

    assert after_cases == before
    assert body["totals"]["cases"] == after_cases
    assert body["totals"]["evidence"] == after_evidence
    assert body["findings"]["total"] == after_findings