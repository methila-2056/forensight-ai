"""Evidence ingestion service (Phase 1).

Upload flow: validate → write-once store → re-read verification of the stored
bytes against the hash computed from the uploaded bytes → persist metadata →
chain-of-custody events.

The original bytes are never modified after this point. Parsing/derived data
belongs to later phases and lives outside the raw store.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, terminology
from app.errors import ApiError
from app.models import (
    Case,
    CustodyAction,
    Evidence,
    EvidenceStatus,
    EvidenceType,
    IntegrityCheck,
    IntegrityResult,
    utcnow,
)
from app.security.uploads import validate_evidence_file
from app.services import custody
from app.storage.raw_store import RawEvidenceExistsError, RawEvidenceStore


def _next_evidence_id(db: Session) -> str:
    sequence = (db.scalar(select(func.count()).select_from(Evidence)) or 0) + 1
    candidate = f"EV-{sequence:04d}"
    while db.scalar(select(Evidence.id).where(Evidence.evidence_id == candidate)) is not None:
        sequence += 1
        candidate = f"EV-{sequence:04d}"
    return candidate


def _parse_evidence_type(value: str) -> EvidenceType:
    try:
        return EvidenceType(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in EvidenceType)
        raise ApiError(
            400,
            "INVALID_EVIDENCE_TYPE",
            f"Unknown evidence type '{value}'. Allowed: {allowed}.",
        ) from exc


def upload_evidence(
    db: Session,
    *,
    case: Case,
    raw_filename: str,
    data: bytes,
    evidence_type: str = EvidenceType.GENERIC.value,
    source: str = "",
    actor: str = "system",
) -> Evidence:
    display_name, _ext, mime_type = validate_evidence_file(raw_filename, data)
    parsed_type = _parse_evidence_type(evidence_type)

    evidence_id = _next_evidence_id(db)
    store = RawEvidenceStore(config.EVIDENCE_STORE_DIR)
    try:
        stored = store.store_once(case.case_id, evidence_id, display_name, data)
    except RawEvidenceExistsError as exc:
        raise ApiError(409, "EVIDENCE_ALREADY_EXISTS", str(exc)) from exc

    # Genuine ingest-time check: re-read the stored file and compare its hash
    # with the hash computed from the uploaded bytes.
    ingest_check = store.verify_hash(case.case_id, evidence_id, stored.sha256)

    evidence = Evidence(
        evidence_id=evidence_id,
        case_id=case.id,
        original_filename=display_name,
        stored_filename=stored.stored_filename,
        evidence_type=parsed_type,
        source_description=(source or "").strip()[:255],
        file_size=stored.size,
        mime_type=mime_type,
        sha256=stored.sha256,
        original_hash=stored.sha256,
        uploaded_at=utcnow(),
        status=EvidenceStatus.VERIFIED
        if ingest_check.verified
        else EvidenceStatus.ERROR,
    )
    db.add(evidence)
    db.flush()

    db.add(
        IntegrityCheck(
            evidence_id=evidence.id,
            computed_hash=ingest_check.computed_hash,
            expected_hash=stored.sha256,
            result=IntegrityResult.VERIFIED
            if ingest_check.verified
            else IntegrityResult.MISMATCH,
            actor=actor or "system",
        )
    )

    custody.record(
        db,
        case=case,
        evidence=evidence,
        action=CustodyAction.EVIDENCE_ADDED,
        actor=actor,
        details={
            "filename": display_name,
            "file_size": stored.size,
            "mime_type": mime_type,
            "evidence_type": parsed_type.value,
            "source": (source or "").strip()[:255],
        },
    )
    custody.record(
        db,
        case=case,
        evidence=evidence,
        action=CustodyAction.HASH_GENERATED,
        actor=actor,
        details={
            "algorithm": terminology.HASH_ALGORITHM,
            "sha256": stored.sha256,
            "file_size": stored.size,
        },
    )
    custody.record(
        db,
        case=case,
        evidence=evidence,
        action=CustodyAction.INTEGRITY_VERIFIED
        if ingest_check.verified
        else CustodyAction.INTEGRITY_MISMATCH,
        actor=actor,
        details={
            "algorithm": terminology.HASH_ALGORITHM,
            "computed_hash": ingest_check.computed_hash,
            "expected_hash": stored.sha256,
            "stage": "ingest",
        },
    )

    case.last_activity = utcnow()
    db.commit()
    db.refresh(evidence)
    return evidence


def list_evidence(db: Session, case: Case) -> list[Evidence]:
    return list(
        db.scalars(
            select(Evidence)
            .where(Evidence.case_id == case.id)
            .order_by(Evidence.uploaded_at.desc(), Evidence.id.desc())
        )
    )


def get_evidence(db: Session, case: Case, evidence_id: str) -> Evidence:
    evidence = db.scalar(
        select(Evidence).where(
            Evidence.case_id == case.id, Evidence.evidence_id == evidence_id
        )
    )
    if evidence is None:
        raise ApiError(404, "EVIDENCE_NOT_FOUND", f"Evidence {evidence_id} was not found in this case.")
    return evidence


def get_evidence_any_case(db: Session, evidence_id: str) -> tuple[Case, Evidence]:
    evidence = db.scalar(select(Evidence).where(Evidence.evidence_id == evidence_id))
    if evidence is None:
        raise ApiError(404, "EVIDENCE_NOT_FOUND", f"Evidence {evidence_id} was not found.")
    case = db.get(Case, evidence.case_id)
    if case is None:  # pragma: no cover - referential integrity
        raise ApiError(404, "CASE_NOT_FOUND", "Owning case not found.")
    return case, evidence
