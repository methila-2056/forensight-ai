"""Phase 1 tests — case management APIs."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

CASE_ID_PATTERN = re.compile(r"^CASE-\d{4}-\d{3}$")


def test_create_case_returns_full_payload(client: TestClient, make_case):
    case = make_case(name="Ransomware review", investigator="Inv A", severity="Critical")
    assert CASE_ID_PATTERN.match(case["case_id"])
    assert case["name"] == "Ransomware review"
    assert case["investigator"] == "Inv A"
    assert case["description"] == "Phase 1 test case"
    assert case["status"] == "Active"
    assert case["severity"] == "Critical"
    assert case["evidence_count"] == 0
    assert case["finding_count"] == 0
    assert case["demo"] is False
    assert case["created_at"] and case["last_activity"]


def test_case_ids_are_stable_and_sequential(client: TestClient, make_case):
    first = make_case(name="First")
    second = make_case(name="Second")
    assert first["case_id"] != second["case_id"]
    first_seq = int(first["case_id"].split("-")[-1])
    second_seq = int(second["case_id"].split("-")[-1])
    assert second_seq == first_seq + 1


def test_create_case_validation_errors_are_enveloped(client: TestClient):
    missing_name = client.post("/api/cases", json={"investigator": "X"})
    assert missing_name.status_code == 422
    body = missing_name.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"]

    empty_name = client.post("/api/cases", json={"name": "", "investigator": "X"})
    assert empty_name.status_code == 422
    assert empty_name.json()["error"]["code"] == "VALIDATION_ERROR"

    blank_name = client.post("/api/cases", json={"name": "   ", "investigator": "X"})
    assert blank_name.status_code == 400
    assert blank_name.json()["error"]["code"] == "NAME_REQUIRED"


def test_list_cases_contains_created_cases(client: TestClient, make_case):
    created = make_case(name="Listed case")
    response = client.get("/api/cases")
    assert response.status_code == 200
    cases = response.json()
    assert any(item["case_id"] == created["case_id"] for item in cases)


def test_get_case_details(client: TestClient, make_case):
    created = make_case(name="Detail case")
    response = client.get(f"/api/cases/{created['case_id']}")
    assert response.status_code == 200
    assert response.json()["case_id"] == created["case_id"]


def test_get_unknown_case_returns_404_envelope(client: TestClient):
    response = client.get("/api/cases/CASE-1999-999")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "CASE_NOT_FOUND"
    assert "CASE-1999-999" in body["error"]["message"]


def test_update_case_status_and_severity(client: TestClient, make_case):
    created = make_case()
    response = client.patch(
        f"/api/cases/{created['case_id']}",
        json={"status": "Under Review", "severity": "Low"},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["status"] == "Under Review"
    assert updated["severity"] == "Low"


def test_update_case_empty_body_rejected(client: TestClient, make_case):
    created = make_case()
    response = client.patch(f"/api/cases/{created['case_id']}", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_UPDATE"


def test_update_case_invalid_enum_rejected(client: TestClient, make_case):
    created = make_case()
    response = client.patch(
        f"/api/cases/{created['case_id']}", json={"status": "Nonsense"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_case_detail_counts_evidence(client: TestClient, make_case, upload_evidence):
    case = make_case(name="Counted")
    assert case["evidence_count"] == 0
    upload_evidence(case["case_id"], "a.csv", b"ts,user\n2026-01-01T00:00:00Z,u1\n")
    detail = client.get(f"/api/cases/{case['case_id']}").json()
    assert detail["evidence_count"] == 1
    assert detail["finding_count"] == 0
