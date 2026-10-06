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
