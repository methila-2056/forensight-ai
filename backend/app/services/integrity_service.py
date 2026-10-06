"""Evidence integrity verification (Phase 1).

What this module establishes: whether the current bytes of a stored evidence
file match the SHA-256 recorded as the reference hash at ingest.

It makes no claim about origin, provenance, ownership, or admissibility —
see terminology.INTEGRITY_DISCLAIMER.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app import config, terminology
from app.errors import ApiError
from app.models import (
    Case,
    CustodyAction,
    Evidence,
    EvidenceStatus,
    IntegrityCheck,
    IntegrityResult,
    utcnow,
)
from app.services import custody
from app.storage.raw_store import RawEvidenceStore, RawEvidenceStoreError, sha256_bytes


def _store() -> RawEvidenceStore:
    return RawEvidenceStore(config.EVIDENCE_STORE_DIR)


def _controlled_test_root() -> Path:
    return config.EVIDENCE_STORE_DIR / "controlled_tests"


def verify_evidence(
    db: Session,
    *,
    case: Case,
    evidence: Evidence,
    actor: str = "system",
) -> dict:
    """Recompute SHA-256 of the stored original and compare with the reference hash."""
    store = _store()
    try:
        verification = store.verify_hash(case.case_id, evidence.evidence_id, evidence.original_hash)
    except RawEvidenceStoreError as exc:
        raise ApiError(409, "EVIDENCE_STORE_UNAVAILABLE", str(exc)) from exc

    result_label = (
        terminology.INTEGRITY_VERIFIED
        if verification.verified
        else terminology.INTEGRITY_MISMATCH
    )

    check = IntegrityCheck(
        evidence_id=evidence.id,
        computed_hash=verification.computed_hash,
        expected_hash=verification.expected_hash,
        result=IntegrityResult.VERIFIED
        if verification.verified
        else IntegrityResult.MISMATCH,
        actor=actor or "system",
    )
    db.add(check)

    if verification.verified:
        evidence.status = EvidenceStatus.VERIFIED
        custody.record(
            db,
            case=case,
            evidence=evidence,
            action=CustodyAction.INTEGRITY_VERIFIED,
            actor=actor,
            details={
                "algorithm": terminology.HASH_ALGORITHM,
                "computed_hash": verification.computed_hash,
                "expected_hash": verification.expected_hash,
                "result": result_label,
            },
        )
    else:
        evidence.status = EvidenceStatus.ERROR
        custody.record(
            db,
            case=case,
            evidence=evidence,
            action=CustodyAction.INTEGRITY_MISMATCH,
            actor=actor,
            details={
                "algorithm": terminology.HASH_ALGORITHM,
                "computed_hash": verification.computed_hash,
                "expected_hash": verification.expected_hash,
                "result": result_label,
            },
        )

    case.last_activity = utcnow()
    db.commit()

    return {
        "evidence_id": evidence.evidence_id,
        "algorithm": terminology.HASH_ALGORITHM,
        "result": result_label,
        "computed_hash": verification.computed_hash,
        "expected_hash": verification.expected_hash,
        "verified_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "note": terminology.INTEGRITY_DISCLAIMER,
    }


def controlled_integrity_test(
    db: Session,
    *,
    case: Case,
    evidence: Evidence,
    actor: str = "system",
) -> dict:
    """Demonstrate a hash mismatch using a modified COPY. Original stays untouched."""
    store = _store()
    try:
        original_bytes = store.read_bytes(case.case_id, evidence.evidence_id)
    except RawEvidenceStoreError as exc:
        raise ApiError(409, "EVIDENCE_STORE_UNAVAILABLE", str(exc)) from exc

    original_hash_before = store.verify_hash(
        case.case_id, evidence.evidence_id, evidence.original_hash
    ).computed_hash

    # 1. Copy the original into a separate controlled-test area.
    test_root = _controlled_test_root() / case.case_id
    test_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    copy_path = test_root / f"{evidence.evidence_id}-{stamp}.copy"
    copy_path.write_bytes(original_bytes)

    # 2. Modify ONLY the copy.
    copy_path.write_bytes(copy_bytes := (copy_path.read_bytes() + b"\nCONTROLLED-TAMPER\n"))

    # 3. Hash the modified copy and compare against the recorded reference hash.
    copy_hash = sha256_bytes(copy_bytes)
    matches_reference = copy_hash == evidence.original_hash

    # 4. Prove the stored original was not affected.
    original_hash_after = store.verify_hash(
        case.case_id, evidence.evidence_id, evidence.original_hash
    ).computed_hash
    original_unchanged = (
        original_hash_before == original_hash_after == evidence.original_hash
    )

    result_label = terminology.INTEGRITY_MISMATCH if not matches_reference else terminology.INTEGRITY_VERIFIED

    custody.record(
        db,
        case=case,
        evidence=evidence,
        action=CustodyAction.INTEGRITY_TEST,
        actor=actor,
        details={
            "operation": terminology.INTEGRITY_TEST_LABEL,
            "algorithm": terminology.HASH_ALGORITHM,
            "recorded_hash": evidence.original_hash,
            "test_copy_hash": copy_hash,
            "result": result_label,
            "original_unchanged": original_unchanged,
            "note": "Only a demonstration copy was modified; the stored original was not written to.",
        },
    )
    case.last_activity = utcnow()
    db.commit()

    return {
        "evidence_id": evidence.evidence_id,
        "operation": terminology.INTEGRITY_TEST_LABEL,
        "result": result_label,
        "recorded_hash": evidence.original_hash,
        "test_copy_hash": copy_hash,
        "original_unchanged": original_unchanged,
        "note": (
            "A separate demonstration copy was modified and hashed; the stored original "
            "evidence was not altered. " + terminology.INTEGRITY_DISCLAIMER
        ),
    }
