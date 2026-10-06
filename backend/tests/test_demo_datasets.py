"""Synthetic demo dataset tests (Phase 2).

Each shipped scenario must upload, process, and satisfy the documented
invariants: every input row/record is accounted for (nothing silently
discarded), malformed rows are retained, duplicates are marked, and every
event traces back to its evidence SHA-256.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DEMO_DIR = Path(__file__).resolve().parents[1] / "demo" / "scenarios"

DATASETS = [
    ("authentication.csv", "authentication"),
    ("file_activity.csv", "file_activity"),
    ("process.csv", "process"),
    ("network.csv", "network"),
    ("browser.csv", "browser"),
    ("system_logs.json", "system"),
]


def _expected_records(filename: str, data: bytes) -> int:
    if filename.endswith(".json"):
        return len(json.loads(data)["events"])
    lines = [line for line in data.decode("utf-8").splitlines() if line.strip()]
    return len(lines) - 1  # exclude header


@pytest.mark.parametrize("filename,evidence_type", DATASETS)
def test_demo_dataset_processes_with_full_accounting(
    client, make_case, upload_evidence, filename, evidence_type
):
    data = (DEMO_DIR / filename).read_bytes()
    expected_received = _expected_records(filename, data)

    case = make_case(name=f"Demo {filename}", description="Synthetic dataset test")
    upload = upload_evidence(
        case["case_id"],
        filename,
        data,
        content_type="application/json" if filename.endswith(".json") else "text/csv",
        evidence_type=evidence_type,
        source="synthetic demo dataset",
    )
    assert upload.status_code == 201, upload.text
    evidence_id = upload.json()["evidence_id"]

    response = client.post(f"/api/cases/{case['case_id']}/process", json={"actor": "demo"})
    assert response.status_code == 200, response.text
    run = response.json()["runs"][0]

    # Every input row/record is accounted for — nothing silently discarded.
    assert run["records_received"] == expected_received
    assert run["records_received"] == run["records_normalized"] + run["records_rejected"]
    assert run["status"] == "Partial"              # each dataset ships malformed rows
    assert run["records_rejected"] >= 1
    assert run["duplicates_detected"] >= 1
    assert run["records_normalized"] >= 6
    assert run["parser"].startswith(("csv/", "json/"))

    # Parser + normalizer: each demo file is designed to detect to its own
    # source type (regression: `str(Enum)` yields "EvidenceType.FILE" and
    # silently dropped the declared-type bonus, misclassifying file_activity).
    assert run["parser"] == f"{'json' if filename.endswith('.json') else 'csv'}/{evidence_type}"

    # Malformed rows are retained with exact reasons.
    rejected = client.get(f"/api/evidence/{evidence_id}/rejected-records").json()
    assert len(rejected) == run["records_rejected"]
    for record in rejected:
        assert record["status"] == "REJECTED"
        assert record["reason"]
        assert record["original_record"]

    # Events exist, duplicates are marked, and each event traces to evidence.
    events = client.get(f"/api/cases/{case['case_id']}/events").json()
    assert events["total"] == run["records_normalized"]
    duplicates = [event for event in events["events"] if event["duplicate"]]
    assert duplicates
    for duplicate in duplicates:
        assert duplicate["duplicate_of"]
        assert duplicate["duplicate_of"] != duplicate["event_id"]

    first = events["events"][0]
    detail = client.get(
        f"/api/cases/{case['case_id']}/events/{first['event_id']}"
    ).json()
    assert detail["evidence"]["evidence_id"] == evidence_id
    assert len(detail["evidence"]["sha256"]) == 64
    assert detail["raw_record"] is not None
    assert detail["raw_record"]["content"]
    assert detail["timestamp"] is not None
    assert detail["tz_note"] is not None

    # Raw evidence untouched by processing.
    verify = client.post(f"/api/evidence/{evidence_id}/verify").json()
    assert verify["result"] == "INTEGRITY VERIFIED"
    assert verify["computed_hash"] == upload.json()["sha256"]


def test_demo_readme_labels_datasets_as_synthetic():
    readme = (DEMO_DIR / "README.md").read_text(encoding="utf-8")
    assert "SYNTHETIC / DEMONSTRATION DATA" in readme
    assert "fictional" in readme.lower()
    for filename, _ in DATASETS:
        assert filename in readme


def test_demo_files_exist():
    for filename, _ in DATASETS:
        path = DEMO_DIR / filename
        assert path.is_file(), f"missing demo dataset: {filename}"
        assert path.stat().st_size > 0
