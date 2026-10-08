"""Evidence-traceable investigation assistant tests (Phase 5).

Covers: deterministic intent classification, empty-case handling, per-intent
answers with real retrieved content and citing source references, unsupported
questions, structured 404 for references that do not exist in the case,
cross-case isolation (mandatory), append-only case-scoped history, and the
question-length bound.
"""

from __future__ import annotations

from app import terminology
from tests.test_analysis import EVIDENCE_FILES

# ---------------------------------------------------------------------------
# Pipeline helpers (through the public API)
# ---------------------------------------------------------------------------

def _setup(client, make_case, upload_evidence) -> str:
    case = make_case(name="Assistant Test Case")
    for filename, data, evidence_type in EVIDENCE_FILES:
        response = upload_evidence(
            case["case_id"], filename, data, evidence_type=evidence_type
        )
        assert response.status_code == 201, response.text
    response = client.post(
        f"/api/cases/{case['case_id']}/process", json={"actor": "tester"}
    )
    assert response.status_code == 200, response.text
    response = client.post(
        f"/api/cases/{case['case_id']}/analyze", json={"actor": "investigator"}
    )
    assert response.status_code == 200, response.text
    response = client.post(
        f"/api/cases/{case['case_id']}/correlate", json={"actor": "investigator"}
    )
    assert response.status_code == 200, response.text
    return case["case_id"]


def _ask(client, case_id: str, question: str, **params) -> dict:
    payload = {"question": question, "actor": "investigator"}
    payload.update(params)
    response = client.post(
        f"/api/cases/{case_id}/assistant/query", json=payload
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["case_id"] == case_id
    assert body["disclaimer"] == terminology.ASSISTANT_FOOTER
    return body


def _history_map(client, case_id: str, limit: int = 500) -> dict[int, dict]:
    response = client.get(
        f"/api/cases/{case_id}/assistant/history", params={"limit": limit}
    )
    assert response.status_code == 200, response.text
    return {row["query_id"]: row for row in response.json()}


# ---------------------------------------------------------------------------
# Empty case
# ---------------------------------------------------------------------------

def test_assistant_empty_case(client, make_case):
    case = make_case()
    body = _ask(client, case["case_id"], "What suspicious activity was detected?")
    assert body["answer"] == terminology.ASSISTANT_EMPTY_CASE
    assert body["confidence"] == "LOW"


def test_assistant_unknown_case_is_404(client):
    response = client.post(
        "/api/cases/CASE-XXXX/assistant/query",
        json={"question": "What happened?", "actor": "investigator"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Schema bounds and unsupported questions
# ---------------------------------------------------------------------------

def test_assistant_rejects_blank_question(client, make_case):
    case = make_case()
    response = client.post(
        f"/api/cases/{case['case_id']}/assistant/query",
        json={"question": "   ", "actor": "investigator"},
    )
    assert response.status_code == 422


def test_assistant_rejects_overlong_question(client, make_case):
    case = make_case()
    response = client.post(
        f"/api/cases/{case['case_id']}/assistant/query",
        json={"question": "x" * 1001, "actor": "investigator"},
    )
    assert response.status_code == 422


def test_assistant_unsupported_question(client, make_case):
    case = make_case()
    body = _ask(client, case["case_id"], "How do I compile a kernel module?")
    assert body["intent"] == "UNKNOWN"
    assert body["answer"] == terminology.ASSISTANT_UNSUPPORTED
    assert body["confidence"] == "LOW"


def test_assistant_capabilities(client, make_case):
    case = make_case()
    body = _ask(client, case["case_id"], "What can you help me with?")
    assert body["intent"] == "CAPABILITIES"
    assert body["answer"] == terminology.ASSISTANT_CAPABILITIES
    assert body["confidence"] == "HIGH"


# ---------------------------------------------------------------------------
# Per-intent answers over processed real data
# ---------------------------------------------------------------------------

def test_assistant_case_summary(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = _ask(client, case_id, "Give me an overview of this case.")
    assert body["intent"] == "CASE_SUMMARY"
    assert case_id in body["answer"]
    assert "evidence file(s)" in body["answer"]
    assert any(src["type"] == "evidence" for src in body["sources"])
    assert body["confidence"] == "HIGH"


def test_assistant_top_findings(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = _ask(client, case_id, "What suspicious activity was detected?")
    assert body["intent"] == "TOP_FINDINGS"
    findings = [src for src in body["sources"] if src["type"] == "finding"]
    assert findings, body
    assert "Finding " in body["answer"] or "ML finding" in body["answer"]


def test_assistant_finding_explanation_by_id(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    findings = client.get(f"/api/cases/{case_id}/findings").json()["findings"]
    assert findings
    finding_id = findings[0]["finding_id"]
    body = _ask(client, case_id, f"Why was finding {finding_id} raised?")
    assert body["intent"] == "FINDING_EXPLANATION"
    assert finding_id in body["answer"]
    assert any(src["id"] == finding_id for src in body["sources"])


def test_assistant_finding_explanation_falls_back_to_top(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = _ask(client, case_id, "Why was the most severe finding raised?")
    assert body["intent"] == "FINDING_EXPLANATION"
    assert any(src["type"] == "finding" for src in body["sources"])


def test_assistant_missing_finding_reference_is_404(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    response = client.post(
        f"/api/cases/{case_id}/assistant/query",
        json={"question": "Why was finding RFND-999999 raised?", "actor": "investigator"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FINDING_NOT_FOUND"


def test_assistant_evidence_support(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = _ask(client, case_id, "Which evidence files support this finding?")
    assert body["intent"] == "EVIDENCE_SUPPORT"
    evidence_sources = [src for src in body["sources"] if src["type"] == "evidence"]
    assert evidence_sources, body


def test_assistant_timeline(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = _ask(client, case_id, "Show the timeline around the suspicious activity.")
    assert body["intent"] == "TIMELINE_CONTEXT"
    assert any(src["type"] == "event" for src in body["sources"]), body


def test_assistant_timeline_time_anchor(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = _ask(client, case_id, "What happened around 10:32?")
    assert body["intent"] == "TIMELINE_CONTEXT"


def test_assistant_correlations(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = _ask(client, case_id, "What correlations were detected?")
    assert body["intent"] == "CORRELATION_SUMMARY"
    assert any(src["type"] == "correlation" for src in body["sources"]), body


def test_assistant_related_same_host(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = _ask(client, case_id, "Which findings are related to the same host?")
    assert body["intent"] == "CORRELATION_SUMMARY"
    assert body["confidence"] == "HIGH"


def test_assistant_groups(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = _ask(client, case_id, "Summarize the activity groups.")
    assert body["intent"] == "GROUP_SUMMARY"
    assert any(src["type"] == "group" for src in body["sources"]), body


def test_assistant_ml_explanation(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = _ask(client, case_id, "Why did the ML model flag this activity?")
    assert body["intent"] == "ML_EXPLANATION"
    assert body["confidence"] in ("HIGH", "MEDIUM")


def test_assistant_review_queue(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = _ask(client, case_id, "Which findings still need investigator review?")
    assert body["intent"] == "REVIEW_QUEUE"
    assert any(src["type"] == "finding" for src in body["sources"]), body


def test_assistant_integrity_status(client, make_case):
    case = make_case()
    data = (b"timestamp,user,host,source_ip,action,result\n"
            b"2026-10-05 09:00:00,usr_a,WS-01,10.20.30.5,login,success\n")
    response = upload = None
    # upload one evidence file and verify it
    upload = client.post(
        f"/api/cases/{case['case_id']}/evidence",
        files={"file": ("auth.csv", data, "text/csv")},
        data={"evidence_type": "authentication", "source": "unit test", "actor": "tester"},
    )
    assert upload.status_code == 201, upload.text
    evidence_id = upload.json()["evidence_id"]
    verify = client.post(f"/api/evidence/{evidence_id}/verify")
    assert verify.status_code == 200, verify.text
    body = _ask(client, case["case_id"], "Have all evidence files been verified?")
    assert body["intent"] == "INTEGRITY_STATUS"
    assert "verified" in body["answer"]


def test_assistant_processing_status(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    body = _ask(client, case_id, "What is the processing status?")
    assert body["intent"] == "PROCESSING_STATUS"
    assert "Processing runs" in body["answer"]


# ---------------------------------------------------------------------------
# Cross-case isolation (mandatory) + history
# ---------------------------------------------------------------------------

def test_assistant_cross_case_isolation(client, make_case, upload_evidence):
    case_a = _setup(client, make_case, upload_evidence)
    case_b = _setup(client, make_case, upload_evidence)

    a_markers = _collect_markers(client, case_a)
    b_markers = _collect_markers(client, case_b)
    assert a_markers and b_markers

    for question in ("What suspicious activity was detected?", "Show the timeline around the suspicious activity."):
        body = _ask(client, case_a, question)
        joined = "\n".join(
            [body["answer"]]
            + list(body["evidence"] or [])
            + [src.get("id", "") for src in body["sources"]]
        )
        # case B findings must never appear in case A answers/sources
        for marker in b_markers:
            assert marker not in joined, f"case B marker leaked into case A: {marker}"

    # a finding that exists only in case B must be a 404 when asked from case A
    response = client.post(
        f"/api/cases/{case_a}/assistant/query",
        json={"question": f"Why was finding {sorted(b_markers)[0]} raised?", "actor": "investigator"},
    )
    assert response.status_code == 404, response.text


def _collect_markers(client, case_id: str) -> set[str]:
    findings = client.get(f"/api/cases/{case_id}/findings").json()["findings"]
    return {row["finding_id"] for row in findings}


def test_assistant_history_append_only_and_case_scoped(client, make_case, upload_evidence):
    case_a = _setup(client, make_case, upload_evidence)
    case_b = _setup(client, make_case, upload_evidence)

    first = _ask(client, case_a, "What suspicious activity was detected?")
    second = _ask(client, case_a, "Show the timeline around the suspicious activity.")
    assert first["query_id"] != second["query_id"]

    history_a = _history_map(client, case_a)
    history_b = _history_map(client, case_b)
    assert len(history_a) == 2
    # history is case-scoped
    assert all(qid not in history_b for qid in history_a)
    # repeated question appends a new row (append-only)
    third = _ask(client, case_a, "What suspicious activity was detected?")
    assert third["query_id"] != first["query_id"]
    assert len(_history_map(client, case_a)) == 3

    # detail endpoint serves only rows of the owning case
    detail = client.get(f"/api/cases/{case_a}/assistant/queries/{first['query_id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["query_id"] == first["query_id"]

    foreign = client.get(f"/api/cases/{case_b}/assistant/queries/{first['query_id']}")
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "ASSISTANT_QUERY_NOT_FOUND"


def test_assistant_repeatability(client, make_case, upload_evidence):
    case_id = _setup(client, make_case, upload_evidence)
    bundle = []
    for _ in range(2):
        response = client.post(
            f"/api/cases/{case_id}/assistant/query",
            json={"question": "What suspicious activity was detected?", "actor": "investigator"},
        )
        assert response.status_code == 201, response.text
        bundle.append(response.json())
    assert [row["answer"] for row in bundle] == [bundle[0]["answer"], bundle[0]["answer"]]
    assert [row["evidence"] for row in bundle] == [bundle[0]["evidence"]] * 2
    assert [row["sources"] for row in bundle] == [bundle[0]["sources"]] * 2