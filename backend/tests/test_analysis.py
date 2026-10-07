"""Automated analysis tests (Phase 3).

Covers the rule registry and per-rule finding cap, Strategy A anomaly
scoring (abstain path, dual gate, determinism), fusion (CSS formula and
bands), and the analysis API contract (run stats, findings, filters,
traceability, review workflow, custody).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest

from app import config, terminology
from app.engines.features import FeatureBuilder
from app.engines.ml import anomaly as anomaly_engine
from app.engines.ml.fusion import WEIGHTS, band, composite_suspicion_score
from app.engines.rules import RULE_CLASSES, run_rules
from app.models import ForensicEvent, SourceType

# ---------------------------------------------------------------------------
# Evidence fixtures (synthetic, deterministic)
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

EXPECTED_RULE_IDS = {"AUTH-001", "FILE-001", "FILE-002", "PROC-001", "NET-001"}


def _setup(client, make_case, upload_evidence) -> str:
    """Create a case, upload all four sources, and process them."""
    case = make_case()
    for filename, data, evidence_type in EVIDENCE_FILES:
        response = upload_evidence(
            case["case_id"], filename, data, evidence_type=evidence_type
        )
        assert response.status_code == 201, response.text
    response = client.post(f"/api/cases/{case['case_id']}/process", json={"actor": "tester"})
    assert response.status_code == 200, response.text
    assert response.json()["runs"], response.text
    return case["case_id"]


def _analyze(client, case_id: str) -> dict:
    response = client.post(
        f"/api/cases/{case_id}/analyze", json={"actor": "investigator"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _findings(client, case_id: str, **params) -> dict:
    response = client.get(f"/api/cases/{case_id}/findings", params=params)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# POST /api/cases/{case_id}/analyze
# ---------------------------------------------------------------------------

def test_analyze_without_events_is_structured_400(client, make_case):
    case = make_case()
    response = client.post(f"/api/cases/{case['case_id']}/analyze", json={})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "NO_NORMALIZED_EVENTS"
    assert body["error"]["message"] == terminology.ANALYSIS_NO_EVENTS


def test_analyze_unknown_case_is_404(client):
    response = client.post("/api/cases/CASE-XXXX/analyze", json={})
    assert response.status_code == 404


def test_analyze_run_shape_and_stats(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    run = _analyze(client, case_id)

    for field in ("run_id", "case_id", "stage", "status", "started_at", "finished_at",
                  "stats", "error"):
        assert field in run
    assert re.fullmatch(r"IRUN-\d{6}", run["run_id"]), run["run_id"]
    assert run["case_id"] == case_id
    assert run["status"] == "Completed"
    assert run["error"] is None

    stats = run["stats"]
    for key in (
        "model_name", "model_version", "random_state", "feature_version",
        "feature_list", "threshold_value", "threshold_method", "threshold_gate",
        "z_sigmas", "min_windows", "windows_total", "abstained",
        "events_considered", "windows_flagged", "rule_findings", "ml_findings",
        "rules", "fusion_formula_version", "fusion_weights", "scope_note",
        "strategy",
    ):
        assert key in stats, key
    assert stats["model_name"] == anomaly_engine.MODEL_NAME
    assert stats["fusion_formula_version"] == "fusion_v1"
    assert stats["fusion_weights"] == dict(WEIGHTS)
    assert stats["strategy"].startswith("A")
    assert stats["scope_note"] == terminology.ANALYSIS_SCOPE_NOTE

    snapshots = stats["rules"]
    assert [snapshot["rule_id"] for snapshot in snapshots] == [
        "AUTH-001", "AUTH-002", "AUTH-003", "PROC-001",
        "FILE-001", "FILE-002", "NET-001",
    ]
    assert all("config" in snapshot and "enabled" in snapshot for snapshot in snapshots)

    # the dual gate is documented in the run snapshot
    assert stats["threshold_method"] == "fixed_constant"
    assert "ANOMALY_THRESHOLD" not in stats["threshold_gate"]
    assert str(config.ANOMALY_THRESHOLD) in str(stats["threshold_value"])


def test_analyze_annotates_events_and_marks_evidence(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    _analyze(client, case_id)

    events = client.get(f"/api/cases/{case_id}/events", params={"limit": 500}).json()
    assert events["total"] > 10
    scored = [event for event in events["events"] if event["anomaly_score"] is not None]
    assert scored, "analysis should annotate events with a window anomaly score"
    assert all(0.0 <= event["anomaly_score"] <= 1.0 for event in scored)

    evidence = client.get(f"/api/cases/{case_id}/evidence").json()
    assert [item["status"] for item in evidence] == ["Analyzed"] * len(evidence)

    custody = client.get(f"/api/cases/{case_id}/custody").json()
    actions = [entry["action"] for entry in custody]
    assert "Automated Analysis Started" in actions
    assert "Automated Analysis Completed" in actions


# ---------------------------------------------------------------------------
# Findings list, filters, pagination
# ---------------------------------------------------------------------------

def test_rule_findings_from_full_catalog(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    run = _analyze(client, case_id)
    body = _findings(client, case_id)

    rule_rows = [row for row in body["findings"] if row["kind"] == "rule"]
    assert body["total"] == len(body["findings"])
    assert run["stats"]["rule_findings"] == len(rule_rows)
    assert {row["rule_id"] for row in rule_rows} >= EXPECTED_RULE_IDS
    assert all(re.fullmatch(r"RFND-\d{6}", row["finding_id"]) for row in rule_rows)
    assert all(row["status"] == "New" for row in rule_rows)
    assert all(row["run_id"] == run["run_id"] for row in rule_rows)
    assert all(row["event_count"] > 0 for row in rule_rows)
    assert all(row["evidence_count"] >= 1 for row in rule_rows)
    for row in rule_rows:
        assert row["composite_suspicion_score"] is not None
        assert 0.0 <= row["composite_suspicion_score"] <= 1.0
        assert row["confidence"] > 0.0

    severities = {row["rule_id"]: row["severity"] for row in rule_rows}
    assert severities["AUTH-001"] == "High"
    assert severities["FILE-001"] == "Medium"
    assert severities["FILE-002"] == "High"
    assert severities["PROC-001"] == "High"
    assert severities["NET-001"] == "Medium"


def test_findings_filters_and_pagination(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    run = _analyze(client, case_id)

    everything = _findings(client, case_id)
    total = everything["total"]
    assert total >= 5

    rule_only = _findings(client, case_id, kind="rule")
    assert {row["kind"] for row in rule_only["findings"]} == {"rule"}
    assert rule_only["total"] == len(rule_only["findings"])

    high = _findings(client, case_id, severity="High")
    assert high["total"] >= 3
    assert {row["severity"] for row in high["findings"]} == {"High"}

    new_only = _findings(client, case_id, status="New")
    assert new_only["total"] == total

    by_run = _findings(client, case_id, run_id=run["run_id"])
    assert by_run["total"] == total

    page = _findings(client, case_id, limit=2, offset=0)
    assert len(page["findings"]) == 2
    assert page["total"] == total
    assert page["limit"] == 2 and page["offset"] == 0
    page_two = _findings(client, case_id, limit=2, offset=2)
    first_ids = {row["finding_id"] for row in page["findings"]}
    second_ids = {row["finding_id"] for row in page_two["findings"]}
    assert not first_ids & second_ids

    unknown = client.get(
        f"/api/cases/{case_id}/findings", params={"severity": "Sky-High"}
    )
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "UNKNOWN_SEVERITY"


# ---------------------------------------------------------------------------
# Finding detail, traceability, review workflow
# ---------------------------------------------------------------------------

def _pick(client, case_id: str, rule_id: str) -> dict:
    rows = _findings(client, case_id, kind="rule")["findings"]
    match = next(row for row in rows if row["rule_id"] == rule_id)
    return match


def test_finding_detail_is_traceable(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    _analyze(client, case_id)
    finding = _pick(client, case_id, "FILE-001")

    response = client.get(f"/api/cases/{case_id}/findings/{finding['finding_id']}")
    assert response.status_code == 200, response.text
    detail = response.json()

    assert detail["kind"] == "rule"
    assert detail["rule_id"] == "FILE-001"
    assert detail["explanation"]
    assert detail["reasons"]
    assert detail["timestamp_start"] and detail["timestamp_end"]
    assert len(detail["event_ids"]) == finding["event_count"]
    assert detail["supporting_events"], "detail must include the triggering events"
    assert len(detail["evidence"]) == finding["evidence_count"]
    for item in detail["evidence"]:
        assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
    assert detail["components"]["formula_version"] == "fusion_v1"
    assert detail["components"]["band"] == band(detail["composite_suspicion_score"])
    assert detail["notes"] == []

    response = client.get(
        f"/api/cases/{case_id}/findings/{finding['finding_id']}/trace"
    )
    assert response.status_code == 200, response.text
    trace = response.json()
    assert trace["finding_id"] == finding["finding_id"]
    assert len(trace["events"]) == finding["event_count"]
    for event in trace["events"]:
        assert event["evidence"]["evidence_id"]
        assert event["raw_record"] is not None
    assert {item["evidence_id"] for item in trace["evidence"]} == {
        event["evidence"]["evidence_id"] for event in trace["events"]
    }

    missing = client.get(f"/api/cases/{case_id}/findings/RFND-999999")
    assert missing.status_code == 404
    foreign = client.get(f"/api/cases/{case_id}/findings/NOT-A-FINDING")
    assert foreign.status_code == 404


def test_ml_finding_detail_when_flagged(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    run = _analyze(client, case_id)
    ml_rows = _findings(client, case_id, kind="ml")["findings"]
    assert run["stats"]["ml_findings"] == len(ml_rows)
    if not ml_rows:
        pytest.skip("Strategy A flagged no window for this deterministic fixture")

    row = ml_rows[0]
    assert re.fullmatch(r"MFND-\d{6}", row["finding_id"])
    assert row["model_name"] == anomaly_engine.MODEL_NAME
    assert row["anomaly_score"] >= config.ANOMALY_THRESHOLD
    assert row["severity"] in ("Medium", "High")

    detail = client.get(
        f"/api/cases/{case_id}/findings/{row['finding_id']}"
    ).json()
    assert detail["model_version"] == anomaly_engine.MODEL_VERSION
    assert detail["feature_snapshot"]["feature_version"] == "phase3-window-v1"
    assert detail["threshold"] == config.ANOMALY_THRESHOLD
    assert detail["explanation"]["disclaimer"] == terminology.ANOMALY_DISCLAIMER
    assert detail["feature_snapshot"]["window_start"]
    assert detail["supporting_events"]


def test_review_workflow_records_custody(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    _analyze(client, case_id)
    finding = _pick(client, case_id, "AUTH-001")
    url = f"/api/cases/{case_id}/findings/{finding['finding_id']}"

    # New -> Under Review
    response = client.patch(
        url, json={"status": "Under Review", "note": "Triaging now",
                   "author": "investigator"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Under Review"
    assert response.json()["notes"][0]["body"] == "Triaging now"
    assert response.json()["notes"][0]["author"] == "investigator"

    # same status -> 409
    same = client.patch(url, json={"status": "Under Review", "author": "investigator"})
    assert same.status_code == 409
    assert same.json()["error"]["code"] == "FINDING_STATUS_UNCHANGED"

    # New -> Confirmed directly is not allowed (workflow must pass review)
    second = _pick(client, case_id, "FILE-002")
    second_url = f"/api/cases/{case_id}/findings/{second['finding_id']}"
    skip = client.patch(second_url, json={"status": "Confirmed", "author": "i"})
    assert skip.status_code == 409
    assert skip.json()["error"]["code"] == "FINDING_STATUS_TRANSITION"

    # Under Review -> Confirmed
    confirmed = client.patch(
        url, json={"status": "Confirmed", "note": "Matches investigation narrative",
                   "author": "lead"}
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "Confirmed"

    unknown = client.patch(
        f"/api/cases/{case_id}/findings/RFND-999999",
        json={"status": "Under Review", "author": "i"},
    )
    assert unknown.status_code == 404

    custody = client.get(f"/api/cases/{case_id}/custody").json()
    reviews = [entry for entry in custody if entry["action"] == "Investigator Reviewed"]
    assert len(reviews) == 2
    assert [entry["actor"] for entry in reviews] == ["lead", "investigator"]


# ---------------------------------------------------------------------------
# Re-analysis is append-only; run history; ML metrics
# ---------------------------------------------------------------------------

def test_reanalysis_appends_and_keeps_history(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    first = _analyze(client, case_id)
    first_total = _findings(client, case_id)["total"]

    second = _analyze(client, case_id)
    assert second["run_id"] != first["run_id"]
    assert re.fullmatch(r"IRUN-\d{6}", second["run_id"])

    runs = client.get(f"/api/cases/{case_id}/analysis-runs").json()
    assert [run["run_id"] for run in runs] == [second["run_id"], first["run_id"]]
    assert all(run["status"] == "Completed" for run in runs)

    after = _findings(client, case_id)
    assert after["total"] >= first_total  # append-only: nothing was deleted
    first_run_rows = _findings(client, case_id, run_id=first["run_id"])
    assert first_run_rows["total"] == first_total

    ids = [row["finding_id"] for row in after["findings"]]
    assert len(ids) == len(set(ids))


def test_analysis_runs_history_and_ml_metrics(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    assert client.get(f"/api/cases/{case_id}/analysis-runs").json() == []

    run = _analyze(client, case_id)

    metrics = client.get(f"/api/cases/{case_id}/ml-metrics")
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["case_id"] == case_id
    assert body["run_id"] == run["run_id"]
    assert body["config"]["threshold"] == config.ANOMALY_THRESHOLD
    assert body["config"]["min_windows"] == config.ML_MIN_WINDOWS
    assert body["config"]["window_minutes"] == config.ANALYSIS_WINDOW_MINUTES
    assert body["config"]["random_state"] == config.RANDOM_STATE
    assert body["stats"]["feature_version"] == "phase3-window-v1"
    assert body["scope_note"] == run["stats"]["scope_note"]


# ---------------------------------------------------------------------------
# Rule engine units
# ---------------------------------------------------------------------------

def _event(
    index: int,
    timestamp: datetime,
    *,
    source_type: str = SourceType.FILE.value,
    user: str | None = "usr_dave",
    host: str | None = "FS-01",
    source_ip: str | None = None,
    destination_ip: str | None = None,
    process: str | None = None,
    file_path: str | None = None,
    action: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    extra: dict | None = None,
) -> ForensicEvent:
    return ForensicEvent(
        id=index,
        event_uid=f"EV-UNIT-{index:05d}",
        case_id=1,
        evidence_id=1,
        timestamp=timestamp,
        source_type=source_type,
        event_type=event_type or action or "",
        user=user,
        host=host,
        source_ip=source_ip,
        destination_ip=destination_ip,
        process=process,
        file_path=file_path,
        action=action,
        severity=severity,
        extra=extra,
    )


def test_rule_catalog_and_snapshots_are_deterministic():
    base = datetime(2026, 10, 5, 10, 0)
    events = [
        _event(1, base, file_path="C:\\a.txt", action="write"),
        _event(2, base + timedelta(minutes=1), file_path="C:\\b.txt", action="write"),
    ]
    results, snapshots = run_rules(events)
    assert results == []
    assert [snapshot["rule_id"] for snapshot in snapshots] == [
        "AUTH-001", "AUTH-002", "AUTH-003", "PROC-001",
        "FILE-001", "FILE-002", "NET-001",
    ]
    assert [cls.rule_id for cls in RULE_CLASSES] == [
        snapshot["rule_id"] for snapshot in snapshots
    ]
    assert all("description" in snapshot and "report_severity" in snapshot
               for snapshot in snapshots)
    assert all(snapshot["enabled"] for snapshot in snapshots)


def test_file_rules_and_per_rule_cap(monkeypatch):
    base = datetime(2026, 10, 5, 10, 0)
    events: list[ForensicEvent] = []
    index = 1
    for user in ("usr_ann", "usr_bob"):
        for offset in range(3):
            events.append(
                _event(index, base + timedelta(minutes=2 * offset), user=user,
                       host="FS-01", file_path=f"C:\\data\\{user}-{offset}.dat",
                       action="rename")
            )
            index += 1

    results, _ = run_rules(events)
    file_two = [r for r in results if r.rule_id == "FILE-002"]
    assert len(file_two) == 2  # one per user, cap not reached yet

    monkeypatch.setattr(config, "RULE_MAX_FINDINGS_PER_RULE", 1)
    capped, snapshots = run_rules(events)
    per_rule: dict[str, int] = {}
    for result in capped:
        per_rule[result.rule_id] = per_rule.get(result.rule_id, 0) + 1
    assert per_rule.get("FILE-002", 0) == 1
    assert all(count <= 1 for count in per_rule.values())
    assert len(snapshots) == 7


def test_auth_rule_failed_burst_without_success_is_medium():
    base = datetime(2026, 10, 5, 10, 0)
    events = [
        _event(1, base, source_type=SourceType.AUTH.value, user="usr_eve",
               host="WS-09", source_ip="10.0.0.9", action="login",
               extra={"status": "failure"}),
        _event(2, base + timedelta(minutes=3), source_type=SourceType.AUTH.value,
               user="usr_eve", host="WS-09", source_ip="10.0.0.9", action="login",
               extra={"status": "failure"}),
        _event(3, base + timedelta(minutes=6), source_type=SourceType.AUTH.value,
               user="usr_eve", host="WS-09", source_ip="10.0.0.9", action="login",
               extra={"status": "failure"}),
    ]
    results, _ = run_rules(events)
    auth = [r for r in results if r.rule_id == "AUTH-001"]
    assert len(auth) == 1
    assert auth[0].severity.value == "Medium"
    assert "investigator review" in auth[0].explanation


# ---------------------------------------------------------------------------
# Strategy A (anomaly engine) units
# ---------------------------------------------------------------------------

def _synthetic_events(count: int = 48) -> list[ForensicEvent]:
    """Spread events over enough windows to exercise Strategy A."""
    base = datetime(2026, 10, 5, 6, 0)
    events: list[ForensicEvent] = []
    sources = [SourceType.AUTH.value, SourceType.FILE.value, SourceType.PROCESS.value,
               SourceType.NETWORK.value, SourceType.SYSTEM.value]
    for index in range(count):
        source = sources[index % len(sources)]
        timestamp = base + timedelta(minutes=4 * index)
        # one clearly busy stretch: a burst of file writes inside a single window
        if 20 <= index < 26:
            source = SourceType.FILE.value
            timestamp = base + timedelta(minutes=100) + timedelta(seconds=15 * index)
        events.append(
            _event(
                index + 1,
                timestamp,
                source_type=source,
                user=f"usr_{index % 4}",
                host=f"WS-{index % 3}",
                source_ip=f"10.0.{index % 5}.{index % 7}",
                file_path=f"C:\\share\\f{index}.txt" if source == SourceType.FILE.value else None,
                action="write" if source == SourceType.FILE.value else "start",
            )
        )
    return events


def test_strategy_a_abstains_below_min_windows():
    base = datetime(2026, 10, 5, 6, 0)
    events = [_event(i + 1, base + timedelta(minutes=6 * i)) for i in range(3)]
    windows = FeatureBuilder().build(events)
    assert len(windows) == 3

    outcome = anomaly_engine.score_windows(windows)
    assert outcome.abstained is True
    assert outcome.window_scores == []
    assert outcome.stats["abstained"] is True
    assert outcome.stats["windows_total"] == 3
    assert str(config.ML_MIN_WINDOWS) in outcome.reason
    assert outcome.reason  # the abstain path must explain itself


def test_strategy_a_is_deterministic_and_obeys_dual_gate():
    events = _synthetic_events()
    windows = FeatureBuilder().build(events)
    assert len(windows) >= config.ML_MIN_WINDOWS

    first = anomaly_engine.score_windows(windows)
    second = anomaly_engine.score_windows(windows)
    assert first.abstained is False
    assert [ws.score for ws in first.window_scores] == [
        ws.score for ws in second.window_scores
    ]
    assert [ws.flagged for ws in first.window_scores] == [
        ws.flagged for ws in second.window_scores
    ]

    stats = first.stats
    assert stats["random_state"] == config.RANDOM_STATE
    assert stats["training_scope"] == "case"
    assert stats["threshold_value"] == config.ANOMALY_THRESHOLD
    assert stats["threshold_method"] == "fixed_constant"

    gate = stats["reference_mean"] - stats["z_sigmas"] * stats["reference_std"]
    assert round(gate, 6) == stats["decision_gate"]
    for window_score in first.window_scores:
        expected = (
            window_score.score >= stats["threshold_value"]
            and window_score.raw_score < gate
        )
        assert window_score.flagged is expected
    assert stats["windows_flagged"] == len(first.flagged)
    assert all(0.0 <= ws.score <= 1.0 for ws in first.window_scores)


# ---------------------------------------------------------------------------
# Fusion (CSS) units
# ---------------------------------------------------------------------------

def test_fusion_formula_weights_and_bands():
    # High rule, no anomaly component, one evidence source
    css, payload = composite_suspicion_score(
        rule_severity="High", anomaly_score=None, distinct_evidence=1
    )
    expected = round(WEIGHTS["rule"] * (0.5 + 0.5 * 0.75) + WEIGHTS["correlation"] * 0.2, 4)
    assert css == expected
    assert payload["formula_version"] == "fusion_v1"
    assert payload["weights"] == dict(WEIGHTS)
    assert payload["total"] == css
    assert payload["band"] == band(css)
    assert payload["components"]["rule"]["contribution"] > 0
    assert payload["components"]["anomaly"]["value"] == 0.0
    assert "not a probability" in payload["note"]

    # ML-only finding with five distinct evidence sources
    css_two, payload_two = composite_suspicion_score(
        rule_severity=None, anomaly_score=1.0, distinct_evidence=9
    )
    assert css_two == round(WEIGHTS["anomaly"] + WEIGHTS["correlation"], 4)
    assert payload_two["components"]["correlation"]["value"] == 1.0  # capped
    assert payload_two["components"]["correlation"]["distinct_evidence"] == 9

    assert band(0.0) == "Informational"
    assert band(0.34) == "Informational"
    assert band(0.35) == "Low interest"
    assert band(0.55) == "Anomalous - review"
    assert band(0.75) == "Potentially suspicious - high priority"
    assert band(1.0) == "Potentially suspicious - high priority"

    # clamping: out-of-range anomaly input cannot exceed 1.0
    clamped, _ = composite_suspicion_score(
        rule_severity="Critical", anomaly_score=5.0, distinct_evidence=99
    )
    assert clamped <= 1.0
