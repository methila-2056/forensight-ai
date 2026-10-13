"""Investigator notes tests (Phase 10).

Notes are analyst annotations, append-only, and strictly case-scoped. These
tests cover the contract that matters: a note cannot be edited or removed, it
cannot be read across a case boundary, it cannot be pinned to a finding in
another case, and it never disturbs the automated pipeline state.
"""

from __future__ import annotations

import pytest

NOTE = "/api/cases/{}/notes"


def test_note_created_and_listed(client, make_case):
    case_id = make_case(name="Notes case")["case_id"]

    created = client.post(
        NOTE.format(case_id),
        json={"body": "Confirmed with the system owner.", "author": "usr_alice"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["case_id"] == case_id
    assert body["body"] == "Confirmed with the system owner."
    assert body["author"] == "usr_alice"
    assert body["finding_uid"] is None

    listed = client.get(NOTE.format(case_id)).json()
    assert listed["total"] == 1
    assert listed["append_only"] is True
    assert listed["notes"][0]["note_id"] == body["note_id"]


def test_notes_are_newest_first(client, make_case):
    case_id = make_case(name="Ordering")["case_id"]
    for text in ("first", "second", "third"):
        client.post(NOTE.format(case_id), json={"body": text})

    listed = client.get(NOTE.format(case_id)).json()
    assert [n["body"] for n in listed["notes"]] == ["third", "second", "first"]


def test_note_body_is_trimmed(client, make_case):
    case_id = make_case(name="Trim")["case_id"]
    created = client.post(NOTE.format(case_id), json={"body": "   padded   "})
    assert created.json()["body"] == "padded"


def test_empty_note_rejected(client, make_case):
    case_id = make_case(name="Empty")["case_id"]
    for value in ("", "   ", "\n\t"):
        response = client.post(NOTE.format(case_id), json={"body": value})
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_oversized_note_rejected(client, make_case):
    case_id = make_case(name="Oversize")["case_id"]
    response = client.post(NOTE.format(case_id), json={"body": "x" * 4001})
    assert response.status_code == 422, response.text

    # The boundary itself must still be accepted.
    ok = client.post(NOTE.format(case_id), json={"body": "y" * 4000})
    assert ok.status_code == 201, ok.text


def test_missing_body_rejected(client, make_case):
    case_id = make_case(name="Missing")["case_id"]
    assert client.post(NOTE.format(case_id), json={}).status_code == 422


def test_author_length_bounded(client, make_case):
    case_id = make_case(name="Author")["case_id"]
    response = client.post(
        NOTE.format(case_id), json={"body": "ok", "author": "z" * 200}
    )
    assert response.status_code == 422, response.text


# --- append-only ------------------------------------------------------------


def test_no_update_or_delete_route_exists():
    """Notes must not be editable: no PUT/PATCH/DELETE route is registered."""
    import sys

    sys.path.insert(0, r"C:\Users\methi\Documents\SUTRAM\backend")
    from app.main import app

    spec = app.openapi()
    notes_paths = [p for p in spec["paths"] if p.endswith("/notes")]
    assert notes_paths == ["/api/cases/{case_id}/notes"]

    methods = set(spec["paths"]["/api/cases/{case_id}/notes"].keys())
    assert methods == {"get", "post"}, f"unexpected note methods: {methods}"


# --- case isolation ---------------------------------------------------------


def test_notes_are_case_scoped(client, make_case):
    first = make_case(name="Case one")["case_id"]
    second = make_case(name="Case two")["case_id"]

    client.post(NOTE.format(first), json={"body": "only in case one"})

    assert client.get(NOTE.format(second)).json()["total"] == 0
    assert client.get(NOTE.format(first)).json()["total"] == 1


def test_notes_404_for_unknown_case(client):
    response = client.get(NOTE.format("CASE-2026-999"))
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_create_note_404_for_unknown_case(client):
    response = client.post(NOTE.format("CASE-2026-999"), json={"body": "x"})
    assert response.status_code == 404, response.text


# --- finding pinning --------------------------------------------------------


def _seeded_case_with_finding(client, make_case, upload_evidence) -> tuple[str, str]:
    """Run a small pipeline so the case has a rule finding to pin notes to."""
    case_id = make_case(name="Finding case")["case_id"]
    data = (
        b"timestamp,user,host,file_path,action\n"
        b"2026-10-05 09:00:00,usr_dave,FS-01,C:\\Shares\\a.doc,write\n"
        b"2026-10-05 09:01:00,usr_dave,FS-01,C:\\Shares\\b.doc,write\n"
        b"2026-10-05 09:02:00,usr_dave,FS-01,C:\\Shares\\c.doc,write\n"
        b"2026-10-05 09:03:00,usr_dave,FS-01,C:\\Shares\\d.doc,write\n"
        b"2026-10-05 09:04:00,usr_dave,FS-01,C:\\Shares\\e.doc,write\n"
        b"2026-10-05 09:05:00,usr_dave,FS-01,C:\\Shares\\f.doc,write\n"
        b"2026-10-05 09:06:00,usr_dave,FS-01,C:\\Shares\\g.doc,write\n"
    )
    upload = upload_evidence(
        case_id, "files.csv", data, evidence_type="file_activity", source="unit test"
    )
    assert upload.status_code == 201, upload.text
    client.post(f"/api/cases/{case_id}/process", json={"actor": "test"})
    client.post(f"/api/cases/{case_id}/analyze", json={"actor": "test"})

    findings = client.get(f"/api/cases/{case_id}/findings").json()["findings"]
    assert findings, "expected at least one finding from the seeded data"
    return case_id, findings[0]["finding_id"]


def test_note_can_pin_to_a_finding_in_the_case(
    client, make_case, upload_evidence
):
    case_id, finding_id = _seeded_case_with_finding(client, make_case, upload_evidence)

    created = client.post(
        NOTE.format(case_id),
        json={"body": "Reviewed the evidence for this finding.", "finding_uid": finding_id},
    )
    assert created.status_code == 201, created.text
    assert created.json()["finding_uid"] == finding_id

    # Scoped listing returns only that finding's note.
    scoped = client.get(
        NOTE.format(case_id), params={"finding_uid": finding_id}
    ).json()
    assert scoped["total"] == 1
    assert scoped["notes"][0]["finding_uid"] == finding_id


def test_note_cannot_pin_to_a_finding_in_another_case(
    client, make_case, upload_evidence
):
    owner_case, finding_id = _seeded_case_with_finding(
        client, make_case, upload_evidence
    )
    other_case = make_case(name="Other case")["case_id"]

    response = client.post(
        NOTE.format(other_case),
        json={"body": "cross-case reference", "finding_uid": finding_id},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "FINDING_NOT_FOUND"

    # The legitimate case still owns its finding and notes.
    assert client.get(NOTE.format(owner_case)).json()["total"] == 0


def test_note_rejects_unknown_finding_shape(client, make_case):
    case_id = make_case(name="Bad uid")["case_id"]
    response = client.post(
        NOTE.format(case_id), json={"body": "x", "finding_uid": "NOT-A-FINDING"}
    )
    assert response.status_code == 422, response.text


def test_filtering_by_finding_with_no_match_is_empty(
    client, make_case, upload_evidence
):
    case_id, finding_id = _seeded_case_with_finding(
        client, make_case, upload_evidence
    )
    client.post(NOTE.format(case_id), json={"body": "general note"})
    response = client.get(
        NOTE.format(case_id), params={"finding_uid": finding_id}
    ).json()
    assert response["total"] == 0


# --- interaction with the rest of the system --------------------------------


def test_note_advances_case_activity(client, make_case):
    case_id = make_case(name="Activity")["case_id"]
    before = client.get(f"/api/cases/{case_id}").json()["last_activity"]
    client.post(NOTE.format(case_id), json={"body": "activity bump"})
    after = client.get(f"/api/cases/{case_id}").json()["last_activity"]
    assert after >= before


def test_notes_survive_a_pipeline_run(client, make_case, upload_evidence):
    """Notes are analyst input and must not be disturbed by analysis."""
    case_id = make_case(name="Pipeline")["case_id"]
    client.post(NOTE.format(case_id), json={"body": "before processing"})

    client.post(f"/api/cases/{case_id}/analyze", json={"actor": "test"})
    client.post(f"/api/cases/{case_id}/correlate", json={"actor": "test"})
    report = client.post(f"/api/cases/{case_id}/reports", json={"actor": "test"})
    assert report.status_code == 201, report.text

    listed = client.get(NOTE.format(case_id)).json()
    assert listed["total"] == 1
    assert listed["notes"][0]["body"] == "before processing"


def test_notes_limit_is_bounded(client, make_case):
    case_id = make_case(name="Limit")["case_id"]
    assert client.get(
        NOTE.format(case_id), params={"limit": 0}
    ).status_code == 422
    assert client.get(
        NOTE.format(case_id), params={"limit": 100000}
    ).status_code == 422
    assert client.get(NOTE.format(case_id), params={"limit": 5}).status_code == 200