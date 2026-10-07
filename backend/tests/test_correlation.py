"""Cross-source correlation, groups, timeline, and graph tests (Phase 4).

Covers the correlation API contract (run shape, links, filters, history),
activity groups, the reconstructed timeline (significance and context),
the evidence graph (caps and table fallback), engine units (pair
precedence, confidence bands, union-find grouping, determinism, caps),
and the Phase 4 wording rules (correlation is never causation).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest

from app import config, terminology
from app.engines.correlation import (
    CORRELATION_MAX_LINKS,
    MAX_GROUPS_PER_RUN,
    build_groups,
    build_links,
    confidence_band,
    evaluate_pair,
)
from app.engines.timeline import build_timeline
from app.models import (
    Correlation,
    CorrelationType,
    ForensicEvent,
    GroupKind,
    SourceType,
    TimelineSignificance,
)
from tests.test_analysis import (
    AUTH_CSV,
    FILE_CSV,
    NETWORK_CSV,
    PROCESS_CSV,
    _analyze,
    _setup,
)

# ---------------------------------------------------------------------------
# Evidence fixtures (same deterministic fixture as Phase 3)
# ---------------------------------------------------------------------------

EVIDENCE_FILES = (
    ("auth.csv", AUTH_CSV, "authentication"),
    ("file.csv", FILE_CSV, "file_activity"),
    ("proc.csv", PROCESS_CSV, "process"),
    ("net.csv", NETWORK_CSV, "network"),
)


def _correlate(client, case_id: str, **kwargs) -> dict:
    response = client.post(f"/api/cases/{case_id}/correlate", json=kwargs or {})
    assert response.status_code == 200, response.text
    return response.json()


def _setup_correlated(client, make_case, upload_evidence, *, analyze: bool = True):
    case_id = _setup(client, make_case, upload_evidence)
    if analyze:
        _analyze(client, case_id)
    run = _correlate(client, case_id)
    return case_id, run


def _correlations(client, case_id: str, **params) -> dict:
    response = client.get(f"/api/cases/{case_id}/correlations", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _groups(client, case_id: str, **params) -> dict:
    response = client.get(f"/api/cases/{case_id}/groups", params=params)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# POST /api/cases/{case_id}/correlate
# ---------------------------------------------------------------------------

def test_correlate_without_events_is_structured_400(client, make_case):
    case = make_case()
    response = client.post(f"/api/cases/{case['case_id']}/correlate", json={})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "NO_NORMALIZED_EVENTS"
    assert body["error"]["message"] == terminology.CORRELATION_NO_EVENTS


def test_correlate_unknown_case_is_404(client):
    response = client.post("/api/cases/CASE-XXXX/correlate", json={})
    assert response.status_code == 404


def test_correlate_run_shape_and_stats(client, make_case, upload_evidence):
    case_id, run = _setup_correlated(client, make_case, upload_evidence)

    for field in ("run_id", "case_id", "status", "started_at", "finished_at",
                  "stats", "error"):
        assert field in run
    assert re.fullmatch(r"CORR-\d{6}", run["run_id"]), run["run_id"]
    assert run["case_id"] == case_id
    assert run["status"] == "Completed"
    assert run["error"] is None

    stats = run["stats"]
    for key in (
        "window_seconds", "dated_events", "pairs_evaluated", "links",
        "links_truncated", "by_type", "by_band", "events_considered",
        "groups", "group_severities", "actor", "disclaimer", "caption",
    ):
        assert key in stats, key
    assert stats["window_seconds"] == config.CORRELATION_WINDOW_SECONDS
    assert stats["links"] > 0
    assert stats["groups"] > 0
    assert stats["links_truncated"] is False
    assert stats["dated_events"] <= stats["events_considered"]
    assert list(stats["by_type"]) == [kind.value for kind in CorrelationType]
    assert list(stats["by_band"]) == ["Low", "Medium", "High"]
    assert sum(stats["by_type"].values()) == stats["links"]
    assert sum(stats["by_band"].values()) == stats["links"]
    assert stats["disclaimer"] == terminology.CORRELATION_DISCLAIMER
    assert "not causation" in stats["caption"]


def test_correlations_list_shape_and_bands(client, make_case, upload_evidence):
    case_id, run = _setup_correlated(client, make_case, upload_evidence)
    body = _correlations(client, case_id)

    assert body["total"] > 0
    assert body["total"] == len(body["correlations"])
    assert body["disclaimer"] == terminology.CORRELATION_DISCLAIMER
    for row in body["correlations"]:
        assert re.fullmatch(r"COR-\d{6}", row["correlation_id"])
        assert row["run_id"] == run["run_id"]
        assert row["case_id"] == case_id
        assert row["correlation_type"].startswith("CORR-")
        assert 0.0 <= row["confidence"] <= 1.0
        assert row["confidence_band"] == confidence_band(row["confidence"])
        assert row["reason"]
        assert row["event_a"]["event_id"] and row["event_b"]["event_id"]
        assert row["time_delta_seconds"] is not None
        assert 0 <= row["time_delta_seconds"] <= config.CORRELATION_WINDOW_SECONDS

    page = _correlations(client, case_id, limit=3)
    assert len(page["correlations"]) == min(3, page["total"])
    page_two = _correlations(client, case_id, limit=3, offset=3)
    first_ids = {row["correlation_id"] for row in page["correlations"]}
    second_ids = {row["correlation_id"] for row in page_two["correlations"]}
    assert not first_ids & second_ids


def test_correlation_detail_is_traceable(client, make_case, upload_evidence):
    case_id, _ = _setup_correlated(client, make_case, upload_evidence)
    first = _correlations(client, case_id)["correlations"][0]

    response = client.get(f"/api/correlations/{first['correlation_id']}")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["disclaimer"] == terminology.CORRELATION_DISCLAIMER
    assert detail["event_a"]["evidence_id"].startswith("EV-")
    assert detail["event_b"]["evidence_id"].startswith("EV-")
    assert detail["event_a_detail"] and detail["event_b_detail"]
    assert detail["event_a_detail"]["event_id"] == detail["event_a"]["event_id"]
    assert detail["event_a_detail"]["raw_record"] is not None
    assert detail["event_a_detail"]["evidence"]["evidence_id"]
    assert detail["evidence_ids"] == sorted(set(detail["evidence_ids"]))

    missing = client.get("/api/correlations/COR-999999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CORRELATION_NOT_FOUND"


def test_correlation_filters_and_errors(client, make_case, upload_evidence):
    case_id, run = _setup_correlated(client, make_case, upload_evidence)

    by_type = _correlations(client, case_id, type="CORR-002")
    if by_type["total"]:
        assert {row["correlation_type"] for row in by_type["correlations"]} == {
            "CORR-002"
        }

    by_run = _correlations(client, case_id, run_id=run["run_id"])
    assert by_run["total"] == _correlations(client, case_id)["total"]

    unknown = client.get(
        f"/api/cases/{case_id}/correlations", params={"type": "CORR-999"}
    )
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "UNKNOWN_CORRELATION_TYPE"

    missing_run = client.get(
        f"/api/cases/{case_id}/correlations", params={"run_id": "CORR-999999"}
    )
    assert missing_run.status_code == 404
    assert missing_run.json()["error"]["code"] == "CORRELATION_RUN_NOT_FOUND"


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def test_groups_shape_detail_and_filters(client, make_case, upload_evidence):
    case_id, run = _setup_correlated(client, make_case, upload_evidence)
    body = _groups(client, case_id)

    assert body["total"] > 0
    assert body["disclaimer"] == terminology.CORRELATION_DISCLAIMER
    kinds = set()
    for row in body["groups"]:
        assert re.fullmatch(r"GRP-\d{6}", row["group_id"])
        assert row["run_id"] == run["run_id"]
        assert row["kind"] in {kind.value for kind in GroupKind}
        assert row["severity"] in {"Low", "Medium", "High", "Critical"}
        assert row["event_count"] >= 2
        assert row["correlation_count"] >= 1
        assert row["title"] and row["explanation"]
        assert row["time_start"] and row["time_end"]
        assert row["time_start"] <= row["time_end"]
        assert terminology.CORRELATION_DISCLAIMER in row["explanation"]
        kinds.add(row["kind"])

    detail = client.get(f"/api/groups/{body['groups'][0]['group_id']}")
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert len(payload["member_events"]) == payload["event_count"]
    assert payload["disclaimer"] == terminology.CORRELATION_DISCLAIMER
    assert payload["correlation_uids"]
    assert all(
        member["evidence_id"] for member in payload["member_events"]
    )

    filtered = _groups(client, case_id, kind="authentication")
    assert {row["kind"] for row in filtered["groups"]} <= {"authentication"}

    unknown_kind = client.get(
        f"/api/cases/{case_id}/groups", params={"kind": "zombies"}
    )
    assert unknown_kind.status_code == 422
    assert unknown_kind.json()["error"]["code"] == "UNKNOWN_GROUP_KIND"

    missing = client.get("/api/groups/GRP-999999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "GROUP_NOT_FOUND"


def test_groups_reflect_finding_severity(client, make_case, upload_evidence):
    case_id, _ = _setup_correlated(client, make_case, upload_evidence)
    findings = client.get(
        f"/api/cases/{case_id}/findings", params={"kind": "rule"}
    ).json()
    high_rules = {
        row["finding_id"] for row in findings["findings"] if row["severity"] == "High"
    }
    assert high_rules, "fixture must produce at least one High rule finding"

    body = _groups(client, case_id)
    severities = [row["severity"] for row in body["groups"]]
    assert "High" in severities  # a group containing FILE/PROC/AUTH-001 events
    assert set(severities) <= {"Low", "Medium", "High", "Critical"}


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def test_timeline_shape_significance_and_ordering(client, make_case, upload_evidence):
    case_id, run = _setup_correlated(client, make_case, upload_evidence)
    response = client.get(f"/api/cases/{case_id}/timeline")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["case_id"] == case_id
    assert body["label"] == terminology.TIMELINE_LABEL
    assert body["disclaimer"] == terminology.TIMELINE_DISCLAIMER
    assert body["total"] == len(body["entries"])
    assert body["truncated"] is False
    assert body["total"] > 0

    stamps = [entry["timestamp"] for entry in body["entries"]]
    assert stamps == sorted(stamps)

    flags = {entry["significance"] for entry in body["entries"]}
    assert flags <= {"NORMAL", "NOTABLE", "SUSPICIOUS"}
    assert "SUSPICIOUS" in flags  # rule-triggered events are in the fixture
    # NOTABLE is covered by the build_timeline unit test below; this fixture
    # folds its ML/anomalous windows into rule-covered events.

    for entry in body["entries"]:
        assert entry["reasons"], entry["event_id"]
        assert entry["event_id"].startswith("EVT-")
        if entry["significance"] == "SUSPICIOUS":
            assert entry["finding_ids"], entry["event_id"]
            assert any(
                reason.startswith("Rule ") for reason in entry["reasons"]
            )
        if entry["context"]:
            assert entry["significance"] == "NORMAL"
            assert entry["reasons"][0].startswith("Context: within")

    # context entries sit within +/- config.TIMELINE_CONTEXT_MINUTES of a tagged event
    context_entries = [entry for entry in body["entries"] if entry["context"]]
    if context_entries:
        delta = timedelta(minutes=config.TIMELINE_CONTEXT_MINUTES)
        tagged = [
            datetime.fromisoformat(entry["timestamp"])
            for entry in body["entries"]
            if not entry["context"] and entry["timestamp"]
        ]
        assert tagged
        for entry in context_entries:
            stamp = datetime.fromisoformat(entry["timestamp"])
            assert any(abs(stamp - other) <= delta for other in tagged)

    # correlation-only entries carry correlation ids
    linked = [entry for entry in body["entries"] if entry["correlation_ids"]]
    assert linked, "correlated events must appear on the timeline"


def test_timeline_without_run_returns_explanatory_note(
    client, make_case, upload_evidence
):
    case_id = _setup(client, make_case, upload_evidence)  # process only
    response = client.get(f"/api/cases/{case_id}/timeline")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["entries"] == []
    assert body["total"] == 0
    assert body["note"], "an empty timeline must explain itself"
    assert body["disclaimer"] == terminology.TIMELINE_DISCLAIMER


def test_timeline_run_filter_and_history(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    _analyze(client, case_id)
    first = _correlate(client, case_id)
    second = _correlate(client, case_id)
    assert second["run_id"] != first["run_id"]

    body = client.get(
        f"/api/cases/{case_id}/timeline", params={"run_id": first["run_id"]}
    ).json()
    assert body["total"] > 0  # the first run is still queryable (append-only)

    missing = client.get(
        f"/api/cases/{case_id}/timeline", params={"run_id": "CORR-999999"}
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CORRELATION_RUN_NOT_FOUND"


def test_timeline_undated_events_are_excluded(client, make_case, upload_evidence):
    case_id, _ = _setup_correlated(client, make_case, upload_evidence)
    body = client.get(f"/api/cases/{case_id}/timeline").json()
    assert all(entry["timestamp"] for entry in body["entries"])


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def test_graph_nodes_edges_and_table_fallback(client, make_case, upload_evidence):
    case_id, run = _setup_correlated(client, make_case, upload_evidence)
    response = client.get(f"/api/cases/{case_id}/graph")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["case_id"] == case_id
    assert body["run_id"] == run["run_id"]
    assert body["disclaimer"] == terminology.CORRELATION_DISCLAIMER
    assert body["max_nodes"] == config.MAX_GRAPH_NODES
    assert body["max_edges"] == config.MAX_GRAPH_EDGES
    assert body["truncated"] is False
    assert len(body["nodes"]) > 0
    assert len(body["table_rows"]) == len(body["edges"])

    node_types = {node["type"] for node in body["nodes"]}
    assert node_types == {"evidence", "finding", "event"}
    node_ids = [node["id"] for node in body["nodes"]]
    assert len(node_ids) == len(set(node_ids))

    relations = {edge["relation"] for edge in body["edges"]}
    assert relations == {"contains", "triggered", "correlated"}
    known = set(node_ids)
    for edge in body["edges"]:
        assert edge["source"] in known and edge["target"] in known
        assert edge["label"]
        if edge["relation"] == "correlated":
            assert edge["correlation_type"].startswith("CORR-")
            assert edge["confidence"] is not None

    finding_nodes = [node for node in body["nodes"] if node["type"] == "finding"]
    assert finding_nodes, "Phase 3 findings must anchor the graph"
    assert all(node["severity"] in {"Low", "Medium", "High", "Critical"}
               for node in finding_nodes)
    assert all(
        node["detail"] in {"New", "Under Review", "Confirmed", "Dismissed"}
        for node in finding_nodes
    )


def test_graph_without_run_uses_note(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = client.get(f"/api/cases/{case_id}/graph").json()
    assert body["run_id"] is None
    assert body["note"], "a run-less graph must say so"
    assert len(body["table_rows"]) == len(body["edges"])


def test_graph_truncation_is_reported(client, make_case, upload_evidence, monkeypatch):
    case_id, _ = _setup_correlated(client, make_case, upload_evidence)
    # 4 evidence + 6 findings consume 10 slots; the 11th node is the first
    # event, after which the cap must stop the graph and set `truncated`.
    monkeypatch.setattr(config, "MAX_GRAPH_NODES", 11)
    body = client.get(f"/api/cases/{case_id}/graph").json()
    assert body["truncated"] is True
    assert len(body["nodes"]) <= 11
    assert body["note"] and "MAX_GRAPH_NODES" in body["note"]
    assert len(body["table_rows"]) == len(body["edges"])
    assert body["table_rows"], "the table fallback must survive truncation"


# ---------------------------------------------------------------------------
# Append-only history, determinism, custody neutrality
# ---------------------------------------------------------------------------

def test_correlation_runs_are_append_only(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    assert client.get(f"/api/cases/{case_id}/correlation-runs").json() == []

    first = _correlate(client, case_id)
    second = _correlate(client, case_id)
    assert re.fullmatch(r"CORR-\d{6}", second["run_id"])

    runs = client.get(f"/api/cases/{case_id}/correlation-runs").json()
    assert [row["run_id"] for row in runs] == [second["run_id"], first["run_id"]]
    assert all(row["status"] == "Completed" for row in runs)

    first_links = _correlations(client, case_id, run_id=first["run_id"])
    second_links = _correlations(client, case_id, run_id=second["run_id"])
    assert first_links["total"] == second_links["total"] > 0

    # groups and graph of the first run remain addressable
    first_groups = _groups(client, case_id, run_id=first["run_id"])
    assert first_groups["total"] > 0
    first_timeline = client.get(
        f"/api/cases/{case_id}/timeline", params={"run_id": first["run_id"]}
    ).json()
    assert first_timeline["total"] > 0


def test_correlation_is_deterministic(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    first = _correlate(client, case_id)
    second = _correlate(client, case_id)

    assert first["stats"]["links"] == second["stats"]["links"]
    assert first["stats"]["by_type"] == second["stats"]["by_type"]
    assert first["stats"]["by_band"] == second["stats"]["by_band"]
    assert first["stats"]["groups"] == second["stats"]["groups"]

    def signatures(run_id: str) -> set[tuple]:
        rows = _correlations(client, case_id, run_id=run_id, limit=500)
        return {
            (
                row["correlation_type"],
                row["event_a"]["event_id"],
                row["event_b"]["event_id"],
                round(row["confidence"], 4),
            )
            for row in rows["correlations"]
        }

    assert signatures(first["run_id"]) == signatures(second["run_id"])


def test_correlate_records_no_custody_actions(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    before = client.get(f"/api/cases/{case_id}/custody").json()
    _correlate(client, case_id)
    after = client.get(f"/api/cases/{case_id}/custody").json()
    assert before == after, "correlation must not append custody entries"


# ---------------------------------------------------------------------------
# Engine units — pair classification and confidence
# ---------------------------------------------------------------------------

def _event(
    index: int,
    timestamp: datetime,
    *,
    source_type: str = SourceType.FILE.value,
    user: str | None = None,
    host: str | None = None,
    source_ip: str | None = None,
    destination_ip: str | None = None,
    process: str | None = None,
    file_path: str | None = None,
    action: str | None = None,
) -> ForensicEvent:
    return ForensicEvent(
        id=index,
        event_uid=f"EV-UNIT-{index:05d}",
        case_id=1,
        evidence_id=1,
        timestamp=timestamp,
        source_type=source_type,
        event_type=action or source_type,
        user=user,
        host=host,
        source_ip=source_ip,
        destination_ip=destination_ip,
        process=process,
        file_path=file_path,
        action=action,
    )


_BASE = datetime(2026, 10, 5, 10, 0)


def test_evaluate_pair_precedence_most_specific_first():
    window = config.CORRELATION_WINDOW_SECONDS

    proc = _event(1, _BASE, source_type=SourceType.PROCESS.value, host="WS-01",
                  user="usr_dave", process="powershell.exe")
    fil = _event(2, _BASE + timedelta(seconds=30), source_type=SourceType.FILE.value,
                 host="WS-01", user="usr_dave", file_path="C:\\a.doc", action="write")
    # process + file on the same host beats the shared-user shortcut (CORR-002)
    result = evaluate_pair(proc, fil, window)
    assert result is not None
    assert result[0] is CorrelationType.PROCESS_TO_FILE
    assert result[1]["host"] == "WS-01"
    assert result[1]["user"] == "usr_dave"

    net = _event(3, _BASE + timedelta(seconds=60), source_type=SourceType.NETWORK.value,
                 host="WS-01", user="usr_dave", source_ip="10.0.0.5",
                 destination_ip="8.8.8.8", action="connect")
    # process + external network beats process + file only when paired;
    # against a process event it is CORR-005 (also beats shared user)
    result = evaluate_pair(proc, net, window)
    assert result is not None
    assert result[0] is CorrelationType.PROCESS_TO_NETWORK

    other = _event(4, _BASE + timedelta(seconds=90), source_type=SourceType.AUTH.value,
                   user="usr_dave", host="WS-02", source_ip="10.0.0.5",
                   action="login")
    # shared user wins over shared IP and shared host
    result = evaluate_pair(other, _event(
        5, _BASE + timedelta(seconds=120), source_type=SourceType.NETWORK.value,
        user="someone_else", host="WS-03", source_ip="10.0.0.5",
        destination_ip="8.8.8.8"), window)
    assert result is not None
    assert result[0] is CorrelationType.SAME_SOURCE_IP  # different users

    same_user_auth = _event(6, _BASE + timedelta(seconds=150),
                            source_type=SourceType.AUTH.value, user="usr_dave",
                            host="WS-09", source_ip="10.9.9.9", action="login")
    result = evaluate_pair(other, same_user_auth, window)
    assert result is not None
    assert result[0] is CorrelationType.SAME_USER  # shared user beats shared IP/host

    host_only_a = _event(7, _BASE + timedelta(seconds=180),
                         source_type=SourceType.AUTH.value, user="usr_ann",
                         host="WS-07", action="login")
    host_only_b = _event(8, _BASE + timedelta(seconds=210),
                         source_type=SourceType.FILE.value, user="usr_bob",
                         host="WS-07", file_path="C:\\b.doc", action="write")
    result = evaluate_pair(host_only_a, host_only_b, window)
    assert result is not None
    assert result[0] is CorrelationType.SAME_HOST


def test_evaluate_pair_respects_window_and_order():
    window = config.CORRELATION_WINDOW_SECONDS
    a = _event(1, _BASE, source_type=SourceType.AUTH.value, user="u", host="H")
    inside = _event(2, _BASE + timedelta(seconds=window),
                    source_type=SourceType.AUTH.value, user="u", host="H")
    outside = _event(3, _BASE + timedelta(seconds=window + 1),
                     source_type=SourceType.AUTH.value, user="u", host="H")
    assert evaluate_pair(a, inside, window) is not None
    assert evaluate_pair(a, outside, window) is None
    assert evaluate_pair(inside, a, window) is None  # time only moves forward

    different = _event(4, _BASE + timedelta(seconds=10),
                       source_type=SourceType.AUTH.value, user="v", host="OTHER")
    assert evaluate_pair(a, different, window) is None  # nothing shared


def test_confidence_is_additive_and_banded():
    window = config.CORRELATION_WINDOW_SECONDS
    full = _event(1, _BASE, source_type=SourceType.AUTH.value, user="u", host="h",
                  source_ip="10.0.0.1", action="login")
    full_twin = _event(2, _BASE + timedelta(seconds=60),
                       source_type=SourceType.NETWORK.value, user="u", host="h",
                       source_ip="10.0.0.1", destination_ip="8.8.8.8")
    result = evaluate_pair(full, full_twin, window)
    assert result is not None
    assert result[2] == 1.0  # time + host + user + IP, capped
    assert confidence_band(result[2]) == "High"

    time_only_a = _event(3, _BASE, source_type=SourceType.AUTH.value, user="u1",
                         host="h1", source_ip="10.0.0.1", action="login")
    time_only_b = _event(4, _BASE + timedelta(seconds=60),
                         source_type=SourceType.NETWORK.value, user="u2", host="h2",
                         source_ip="10.0.0.2", destination_ip="8.8.8.8")
    # nothing shared at all -> no link; weaken until only host is shared
    host_a = _event(5, _BASE, source_type=SourceType.AUTH.value, user="u1", host="h9",
                    source_ip="10.0.0.1", action="login")
    host_b = _event(6, _BASE + timedelta(seconds=60),
                    source_type=SourceType.FILE.value, user="u2", host="h9",
                    file_path="C:\\x", action="write")
    result = evaluate_pair(host_a, host_b, window)
    assert result is not None
    assert result[2] == round(
        config.CORRELATION_WEIGHT_TIME_WINDOW + config.CORRELATION_WEIGHT_SAME_HOST, 4
    )
    assert confidence_band(result[2]) == "Low"

    assert confidence_band(0.84) == "Medium"
    assert confidence_band(0.85) == "High"
    assert confidence_band(0.64) == "Low"
    assert confidence_band(0.65) == "Medium"
    assert evaluate_pair(time_only_a, time_only_b, window) is None


def test_build_links_stats_sum_and_cap():
    events = [
        _event(index, _BASE + timedelta(seconds=90 * index),
               source_type=SourceType.AUTH.value, user="u", host="h",
               source_ip="10.0.0.1", action="login")
        for index in range(6)
    ]
    links, stats = build_links(events, window_seconds=1000)
    assert stats["dated_events"] == 6
    assert stats["links"] == len(links)
    assert sum(stats["by_type"].values()) == len(links)
    assert sum(stats["by_band"].values()) == len(links)
    assert stats["links_truncated"] is False
    assert stats["by_type"][CorrelationType.SAME_USER.value] == len(links)

    capped, cap_stats = build_links(events, window_seconds=1000, max_links=2)
    assert cap_stats["links"] == 2
    assert cap_stats["links_truncated"] is True

    undated = [_event(9, None)]
    assert build_links(undated)[1]["dated_events"] == 0


def test_build_groups_union_find_and_caps():
    events = [
        _event(index, _BASE + timedelta(seconds=index), host="h",
               source_type=SourceType.FILE.value, file_path=f"C:\\f{index}",
               action="write", user="u")
        for index in range(1, 6)
    ]
    links, _ = build_links(events, window_seconds=1000)
    assert links

    groups = build_groups(links)
    assert groups
    members = {event.id for group in groups for event in group.member_events}
    assert members == {event.id for link in links for event in (link.event_a, link.event_b)}
    for group in groups:
        assert len(group.member_events) >= 2
        assert group.links
        assert group.time_start is not None and group.time_end is not None
        assert group.time_start <= group.time_end
        assert terminology.CORRELATION_DISCLAIMER in group.explanation
        assert group.kind in set(GroupKind)

    assert build_groups([]) == []
    assert [g.title for g in build_groups(links)] == [g.title for g in build_groups(links)]
    assert len(build_groups(links, max_groups=1)) == 1


# ---------------------------------------------------------------------------
# Engine units — timeline builder
# ---------------------------------------------------------------------------

def test_build_timeline_significance_and_context():
    events = [
        _event(1, _BASE, source_type=SourceType.PROCESS.value, host="h",
               user="usr_dave", process="powershell.exe"),
        _event(2, _BASE + timedelta(seconds=30), source_type=SourceType.AUTH.value,
               host="h", user="usr_dave", action="login"),
        _event(3, _BASE + timedelta(minutes=4), source_type=SourceType.FILE.value,
               host="h", user="usr_dave", file_path="C:\\a", action="write"),
        _event(4, _BASE + timedelta(minutes=30), source_type=SourceType.FILE.value,
               host="other", user="usr_zoe", file_path="C:\\far", action="write"),
        _event(5, _BASE + timedelta(minutes=40), source_type=SourceType.FILE.value,
               host="other2", user="usr_zed", file_path="C:\\odd", action="write"),
        _event(6, _BASE + timedelta(minutes=10), source_type=SourceType.AUTH.value,
               host="h2", user="usr_fay", action="login"),
    ]
    events[4].is_anomalous = True
    events[4].anomaly_score = 0.91
    finding_index = {
        "EV-UNIT-00001": [{
            "finding_id": "RFND-000001", "kind": "rule", "rule_id": "PROC-001",
            "title": "Scripting process", "severity": "High", "score": 0.9,
            "status": "New",
        }],
        "EV-UNIT-00003": [{
            "finding_id": "MFND-000001", "kind": "ml", "rule_id": None,
            "title": "Unusual activity window", "severity": "Medium", "score": 0.83,
            "status": "New",
        }],
    }
    correlation = Correlation(
        id=1,
        correlation_uid="COR-UNIT-01",
        case_id=1,
        run_id=1,
        correlation_type=CorrelationType.SAME_USER,
        event_a_id=1,
        event_b_id=6,
        time_delta_seconds=600.0,
        confidence=0.85,
        reason="unit",
        shared_entities={"user": "usr_dave"},
        evidence_ids=["EV-0001"],
    )
    entries, total, truncated = build_timeline(
        events,
        finding_index=finding_index,
        links=[correlation],
        events_by_id={event.id: event for event in events},
        evidence_map={1: "EV-0001"},
        context_minutes=2,
        max_entries=500,
    )
    assert total == len(entries)
    assert truncated is False
    by_id = {entry.event_id: entry for entry in entries}

    # rule finding -> SUSPICIOUS
    assert by_id["EV-UNIT-00001"].significance is TimelineSignificance.SUSPICIOUS
    assert by_id["EV-UNIT-00001"].finding_ids == ["RFND-000001"]
    assert by_id["EV-UNIT-00001"].context is False
    # untagged neighbour inside +/-2 minutes -> NORMAL context entry
    assert by_id["EV-UNIT-00002"].context is True
    assert by_id["EV-UNIT-00002"].significance is TimelineSignificance.NORMAL
    # ML finding -> NOTABLE (no rule tag)
    assert by_id["EV-UNIT-00003"].significance is TimelineSignificance.NOTABLE
    assert by_id["EV-UNIT-00003"].finding_ids == ["MFND-000001"]
    # anomalous without a finding -> NOTABLE with an anomaly reason
    assert by_id["EV-UNIT-00005"].significance is TimelineSignificance.NOTABLE
    assert any("anomalous" in reason for reason in by_id["EV-UNIT-00005"].reasons)
    # correlation member without findings -> NORMAL, reason-tagged with .value
    assert by_id["EV-UNIT-00006"].significance is TimelineSignificance.NORMAL
    assert by_id["EV-UNIT-00006"].context is False
    assert by_id["EV-UNIT-00006"].correlation_ids == ["COR-UNIT-01"]
    assert any(
        "Correlation COR-UNIT-01 (CORR-002)" in reason
        for reason in by_id["EV-UNIT-00006"].reasons
    )
    # untagged and out of context -> excluded entirely
    assert "EV-UNIT-00004" not in by_id
    assert entries == sorted(entries, key=lambda e: (e.timestamp, e.event_id))

    capped, capped_total, capped_flag = build_timeline(
        events,
        finding_index=finding_index,
        links=[correlation],
        events_by_id={event.id: event for event in events},
        evidence_map={1: "EV-0001"},
        context_minutes=2,
        max_entries=1,
    )
    assert capped_total >= 4
    assert len(capped) == 1
    assert capped_flag is True

    empty, empty_total, empty_flag = build_timeline(
        [], finding_index={}, links=[], events_by_id={}, evidence_map={},
        context_minutes=2, max_entries=500,
    )
    assert empty == [] and empty_total == 0 and empty_flag is False


# ---------------------------------------------------------------------------
# Wording guards for Phase 4 artifacts
# ---------------------------------------------------------------------------

def test_phase4_wording_never_overclaims(client, make_case, upload_evidence):
    case_id, run = _setup_correlated(client, make_case, upload_evidence)
    banned = [
        "legally proven", "court admissible", "confirmed attacker",
        "confirmed ransomware", "guaranteed attack chain",
        "automatic attribution",
    ]

    payload = "\n".join(
        [
            run["stats"]["disclaimer"],
            run["stats"]["caption"],
            str(client.get(f"/api/cases/{case_id}/correlations").json()),
            str(client.get(f"/api/cases/{case_id}/groups").json()),
            str(client.get(f"/api/cases/{case_id}/timeline").json()),
            str(client.get(f"/api/cases/{case_id}/graph").json()),
        ]
    ).lower()
    for phrase in banned:
        assert phrase not in payload
    assert terminology.CORRELATION_DISCLAIMER.lower() in payload


def test_correlation_caps_constants_are_reported_in_stats(
    client, make_case, upload_evidence
):
    case_id, run = _setup_correlated(client, make_case, upload_evidence, analyze=False)
    assert CORRELATION_MAX_LINKS >= 5000
    assert MAX_GROUPS_PER_RUN == 50
    stats = run["stats"]
    assert stats["links"] <= CORRELATION_MAX_LINKS
    assert stats["groups"] <= MAX_GROUPS_PER_RUN
    assert stats["disclaimer"] == terminology.CORRELATION_DISCLAIMER
