"""Raw evidence store tests (Phase 0 acceptance criterion 10)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.storage import raw_store as raw_store_module
from app.storage.raw_store import (
    RawEvidenceExistsError,
    RawEvidenceNotFoundError,
    RawEvidenceStore,
    sha256_bytes,
)
from app.terminology import INTEGRITY_MISMATCH, INTEGRITY_VERIFIED

CASE = "CASE-2026-P0"
EVIDENCE = "EV-P0-001"
PAYLOAD = b"timestamp,user,action\n2026-01-01T00:00:00Z,usr_demo,login\n"


def test_store_once_returns_matching_sha256(raw_store: RawEvidenceStore):
    stored = raw_store.store_once(CASE, EVIDENCE, "authentication.csv", PAYLOAD)
    assert stored.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert stored.size == len(PAYLOAD)
    assert stored.path.exists()
    assert stored.path.suffix == ".csv"


def test_store_once_refuses_second_write(raw_store: RawEvidenceStore):
    raw_store.store_once(CASE, EVIDENCE, "authentication.csv", PAYLOAD)
    with pytest.raises(RawEvidenceExistsError):
        raw_store.store_once(CASE, EVIDENCE, "authentication.csv", b"tampered bytes")


def test_read_bytes_returns_exact_original(raw_store: RawEvidenceStore):
    raw_store.store_once(CASE, EVIDENCE, "authentication.csv", PAYLOAD)
    assert raw_store.read_bytes(CASE, EVIDENCE) == PAYLOAD


def test_read_bytes_missing_evidence_raises(raw_store: RawEvidenceStore):
    with pytest.raises(RawEvidenceNotFoundError):
        raw_store.read_bytes(CASE, "EV-DOES-NOT-EXIST")


def test_verify_hash_verified_and_mismatch(raw_store: RawEvidenceStore):
    stored = raw_store.store_once(CASE, EVIDENCE, "authentication.csv", PAYLOAD)

    verified = raw_store.verify_hash(CASE, EVIDENCE, stored.sha256)
    assert verified.result == INTEGRITY_VERIFIED
    assert verified.verified is True
    assert verified.computed_hash == stored.sha256

    mismatch = raw_store.verify_hash(CASE, EVIDENCE, "0" * 64)
    assert mismatch.result == INTEGRITY_MISMATCH
    assert mismatch.verified is False
    assert mismatch.computed_hash == hashlib.sha256(PAYLOAD).hexdigest()


def test_raw_bytes_unchanged_after_reads_and_verifications(raw_store: RawEvidenceStore):
    stored = raw_store.store_once(CASE, EVIDENCE, "authentication.csv", PAYLOAD)
    before = sha256_bytes(raw_store.read_bytes(CASE, EVIDENCE))
    for _ in range(3):
        raw_store.read_bytes(CASE, EVIDENCE)
        raw_store.verify_hash(CASE, EVIDENCE, stored.sha256)
    after = sha256_bytes(raw_store.read_bytes(CASE, EVIDENCE))
    assert before == after == stored.sha256
    assert sha256_bytes(stored.path.read_bytes()) == stored.sha256


def test_store_exposes_no_overwrite_or_truncate_operations(raw_store: RawEvidenceStore):
    forbidden = {"overwrite", "truncate", "replace", "update", "delete", "remove", "rewrite"}
    public_api = {name for name in dir(raw_store) if not name.startswith("_")}
    assert not (public_api & forbidden), f"Forbidden operations present: {public_api & forbidden}"
    assert not (set(dir(RawEvidenceStore)) & forbidden)
    for name in ("store_once", "read_bytes", "verify_hash"):
        assert callable(getattr(raw_store, name))


def test_path_traversal_names_are_neutralised(raw_store: RawEvidenceStore):
    stored = raw_store.store_once("../evil", "../../EV-9", "..\\..\\auth.csv", PAYLOAD)
    root = raw_store.root.resolve()
    assert root in stored.path.resolve().parents
    assert stored.path.resolve().parent == root / "evil"


def test_module_documents_write_once_intent():
    source = Path(raw_store_module.__file__).read_text(encoding="utf-8")
    assert '"xb"' in source  # exclusive creation mode is the only write path
    assert "no overwrite" in source.casefold()
