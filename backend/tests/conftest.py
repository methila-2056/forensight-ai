"""Shared pytest fixtures — Phase 0.

Environment variables are set BEFORE any `app.*` import so that configuration
module-level values (database path, evidence store root) point at a temporary
location and never touch real application data.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="foresight_p0_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["EVIDENCE_STORE_DIR"] = str(_TMP / "evidence_store")
os.environ.setdefault("ANOMALY_THRESHOLD", "0.72")
os.environ.setdefault("RANDOM_STATE", "42")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.storage.raw_store import RawEvidenceStore  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def raw_store(tmp_path: Path) -> RawEvidenceStore:
    return RawEvidenceStore(tmp_path / "evidence_store")


@pytest.fixture()
def make_case(client: TestClient):
    """Create a case through the API and return its payload."""

    def _make(
        name: str = "Test Investigation",
        investigator: str = "Investigator A",
        description: str = "Phase 1 test case",
        severity: str = "High",
    ) -> dict:
        response = client.post(
            "/api/cases",
            json={
                "name": name,
                "investigator": investigator,
                "description": description,
                "severity": severity,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture()
def upload_evidence(client: TestClient):
    """Upload a file through the API and return the response."""

    def _upload(
        case_id: str,
        filename: str,
        data: bytes,
        content_type: str = "text/csv",
        evidence_type: str = "authentication",
        source: str = "unit test",
        actor: str = "tester",
    ):
        return client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": (filename, data, content_type)},
            data={
                "evidence_type": evidence_type,
                "source": source,
                "actor": actor,
            },
        )

    return _upload
