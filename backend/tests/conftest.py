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
# Defaults to a throwaway SQLite file, but an externally supplied DATABASE_URL
# wins so the same suite can be run against a real PostgreSQL server — which is
# how the Neon deployment path is verified before shipping.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(_TMP / 'test.db').as_posix()}")
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
def configured_store():
    """The evidence store the application is actually configured to use.

    Integration tests must assert against this rather than instantiating
    ``RawEvidenceStore`` directly, otherwise they silently pass against an
    empty filesystem when ``EVIDENCE_STORAGE_BACKEND=database`` is exercised
    (the managed-PostgreSQL deployment path, where bytes live in BYTEA and
    nothing is written to disk).
    """
    from app import config
    from app.db import SessionLocal
    from app.storage.factory import get_evidence_store

    if config.EVIDENCE_STORAGE_BACKEND == "database":
        session = SessionLocal()
        try:
            yield get_evidence_store(session)
        finally:
            session.close()
    else:
        yield RawEvidenceStore(config.EVIDENCE_STORE_DIR)


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
