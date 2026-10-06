"""Phase 1 tests — evidence ingestion, validation, security."""

from __future__ import annotations

import hashlib
import json
import re

from fastapi.testclient import TestClient

from app import config
from app.storage.raw_store import RawEvidenceStore

EVIDENCE_ID_PATTERN = re.compile(r"^EV-\d{4}$")

CSV_BODY = b"timestamp,user,action\n2026-01-01T00:00:00Z,usr_demo,login\n"


def test_upload_csv_records_real_sha256(client, make_case, upload_evidence):
    case = make_case(name="Upload case")
    response = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY)
    assert response.status_code == 201, response.text
    body = response.json()

    assert EVIDENCE_ID_PATTERN.match(body["evidence_id"])
    assert body["case_id"] == case["case_id"]
    assert body["original_filename"] == "authentication.csv"
    assert body["evidence_type"] == "authentication"
    assert body["source_description"] == "unit test"
    assert body["file_size"] == len(CSV_BODY)
    assert body["mime_type"] == "text/csv"
    assert body["sha256"] == hashlib.sha256(CSV_BODY).hexdigest()
    assert body["status"] == "Verified"
    assert body["uploaded_at"]
    assert body["record_count"] is None  # parsing is Phase 2


def test_uploaded_bytes_are_stored_verbatim_in_raw_store(client, make_case, upload_evidence):
    case = make_case(name="Immutability")
    uploaded = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY).json()
    store = RawEvidenceStore(config.EVIDENCE_STORE_DIR)
    stored_bytes = store.read_bytes(case["case_id"], uploaded["evidence_id"])
    assert stored_bytes == CSV_BODY
    assert hashlib.sha256(stored_bytes).hexdigest() == uploaded["sha256"]


def test_case_evidence_listing_and_detail(client, make_case, upload_evidence):
    case = make_case(name="Listing")
    first = upload_evidence(case["case_id"], "a.csv", CSV_BODY).json()
    second = upload_evidence(
        case["case_id"], "b.log", b"2026-01-01 something happened\n", "text/plain", "system"
    ).json()

    listing = client.get(f"/api/cases/{case['case_id']}/evidence")
    assert listing.status_code == 200
    ids = {item["evidence_id"] for item in listing.json()}
    assert {first["evidence_id"], second["evidence_id"]} == ids

    detail = client.get(f"/api/evidence/{first['evidence_id']}")
    assert detail.status_code == 200
    assert detail.json()["sha256"] == first["sha256"]


def test_unsupported_extension_rejected(client, make_case, upload_evidence):
    case = make_case(name="Bad ext")
    response = upload_evidence(case["case_id"], "payload.exe", b"MZ\x90\x00rest", "application/octet-stream")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_binary_content_with_text_extension_rejected(client, make_case, upload_evidence):
    case = make_case(name="Bad content")
    response = upload_evidence(
        case["case_id"], "fake.csv", b"\x00\x01\x02binary\x00junk", "text/csv"
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "CONTENT_TYPE_MISMATCH"


def test_executable_magic_rejected_even_with_csv_name(client, make_case, upload_evidence):
    case = make_case(name="Exe magic")
    response = upload_evidence(
        case["case_id"], "sneaky.csv", b"MZ\x90\x00\x03\x00\x00\x00payload", "text/csv"
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "CONTENT_TYPE_MISMATCH"


def test_empty_file_rejected(client, make_case, upload_evidence):
    case = make_case(name="Empty")
    response = upload_evidence(case["case_id"], "empty.csv", b"", "text/csv")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_FILE"


def test_file_size_limit_enforced(client, make_case, upload_evidence, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 64)
    case = make_case(name="Too big")
    response = upload_evidence(case["case_id"], "big.csv", b"x" * 512, "text/csv")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_invalid_json_content_rejected(client, make_case, upload_evidence):
    case = make_case(name="Bad json")
    response = upload_evidence(
        case["case_id"], "events.json", b"this is {not json", "application/json", "generic"
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "CONTENT_TYPE_MISMATCH"


def test_valid_json_and_zip_accepted(client, make_case, upload_evidence):
    case = make_case(name="Json zip")
    payload = json.dumps({"events": [{"ts": "2026-01-01T00:00:00Z"}]}).encode()
    json_response = upload_evidence(
        case["case_id"], "events.json", payload, "application/json", "generic"
    )
    assert json_response.status_code == 201, json_response.text

    zip_bytes = b"PK\x03\x04" + b"\x00" * 40
    zip_response = upload_evidence(
        case["case_id"], "bundle.zip", zip_bytes, "application/zip", "generic"
    )
    assert zip_response.status_code == 201, zip_response.text
    assert zip_response.json()["mime_type"] == "application/zip"
    assert zip_response.json()["sha256"] == hashlib.sha256(zip_bytes).hexdigest()


def test_path_traversal_filename_sanitised(client, make_case, upload_evidence):
    case = make_case(name="Traversal")
    for hostile in ("../../evil.csv", "..\\..\\evil2.csv", "/etc/passwd.csv"):
        response = upload_evidence(case["case_id"], hostile, CSV_BODY)
        assert response.status_code == 201, response.text
        stored_name = response.json()["original_filename"]
        assert "/" not in stored_name
        assert "\\" not in stored_name
        assert ".." not in stored_name


def test_control_characters_removed_from_filename(client, make_case, upload_evidence):
    case = make_case(name="Control chars")
    response = upload_evidence(case["case_id"], "ev\r\nil.csv", CSV_BODY)
    assert response.status_code == 201, response.text
    name = response.json()["original_filename"]
    assert "\r" not in name and "\n" not in name


def test_no_server_paths_leak_in_responses(client, make_case, upload_evidence):
    case = make_case(name="No leak")
    upload = upload_evidence(case["case_id"], "authentication.csv", CSV_BODY)
    detail = client.get(f"/api/evidence/{upload.json()['evidence_id']}")
    listing = client.get(f"/api/cases/{case['case_id']}/evidence")
    combined = upload.text + detail.text + listing.text
    assert str(config.EVIDENCE_STORE_DIR) not in combined
    assert "evidence_store" not in combined


def test_upload_to_unknown_case_returns_404(client, upload_evidence):
    response = upload_evidence("CASE-1999-999", "authentication.csv", CSV_BODY)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_invalid_evidence_type_rejected(client, make_case, upload_evidence):
    case = make_case(name="Bad type")
    response = upload_evidence(
        case["case_id"], "a.csv", CSV_BODY, "text/csv", evidence_type="telepathy"
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_EVIDENCE_TYPE"


def test_get_unknown_evidence_returns_404_envelope(client):
    response = client.get("/api/evidence/EV-9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_upload_policy_endpoint(client):
    response = client.get("/api/policy")
    assert response.status_code == 200
    body = response.json()
    assert body["hash_algorithm"] == "SHA-256"
    assert "csv" in body["allowed_extensions"]
    assert body["max_upload_mb"] >= 1
    assert "does not establish" in body["integrity_note"]
