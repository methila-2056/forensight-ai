"""Evidence ingestion, integrity verification, and custody endpoints (Phase 1).

Security notes:
* uploads are validated (extension, size, content sniff) and stored via the
  write-once RawEvidenceStore under generated names — original filenames are
  metadata only and can never influence storage paths.
* uploaded bytes are stored as data and never executed.
* responses never expose server filesystem paths.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, terminology
from app.db import get_db
from app.errors import ApiError
from app.models import IntegrityCheck, IntegrityResult
from app.schemas import (
    EvidenceResponse,
    IntegrityHistoryEntry,
    IntegrityTestResponse,
    IntegrityVerifyResponse,
    CustodyEventResponse,
)
from app.services import case_service, custody, evidence_service, integrity_service, serializers

router = APIRouter(tags=["evidence"])

_READ_CHUNK = 1024 * 1024


async def _read_limited(file: UploadFile) -> bytes:
    """Stream the upload while enforcing the configured size cap."""
    buffer = bytearray()
    while True:
        chunk = await file.read(_READ_CHUNK)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > config.MAX_UPLOAD_BYTES:
            raise ApiError(
                413,
                "FILE_TOO_LARGE",
                f"File exceeds the maximum allowed size of {config.MAX_UPLOAD_MB} MB.",
            )
    return bytes(buffer)


@router.post(
    "/cases/{case_id}/evidence",
    response_model=EvidenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an evidence file (write-once, SHA-256 recorded)",
)
async def upload_evidence(
    case_id: str,
    file: UploadFile = File(..., description="Evidence file (csv, json, txt, log, zip)"),
    evidence_type: str = Form(default="generic", description="authentication|process|file_activity|network|browser|system|generic"),
    source: str = Form(default="", description="Where the evidence came from"),
    actor: str = Form(default="system"),
    db: Session = Depends(get_db),
) -> EvidenceResponse:
    case = case_service.get_case(db, case_id)
    data = await _read_limited(file)
    evidence = evidence_service.upload_evidence(
        db,
        case=case,
        raw_filename=file.filename or "evidence",
        data=data,
        evidence_type=evidence_type,
        source=source,
        actor=actor or "system",
    )
    return serializers.evidence_response(evidence, case)


@router.get(
    "/cases/{case_id}/evidence",
    response_model=list[EvidenceResponse],
    summary="List evidence for a case",
)
def list_evidence(case_id: str, db: Session = Depends(get_db)) -> list[EvidenceResponse]:
    case = case_service.get_case(db, case_id)
    return [
        serializers.evidence_response(evidence, case)
        for evidence in evidence_service.list_evidence(db, case)
    ]


@router.get("/evidence/{evidence_id}", response_model=EvidenceResponse, summary="Get evidence details")
def get_evidence(evidence_id: str, db: Session = Depends(get_db)) -> EvidenceResponse:
    case, evidence = evidence_service.get_evidence_any_case(db, evidence_id)
    return serializers.evidence_response(evidence, case)


@router.post(
    "/evidence/{evidence_id}/verify",
    response_model=IntegrityVerifyResponse,
    summary="Evidence Integrity Verification (recompute SHA-256 and compare)",
)
def verify_evidence(
    evidence_id: str,
    actor: str = Query(default="system"),
    db: Session = Depends(get_db),
) -> IntegrityVerifyResponse:
    """Recomputes SHA-256 of the stored original and compares it with the
    reference hash recorded at ingest. Result is computed, never hardcoded."""
    case, evidence = evidence_service.get_evidence_any_case(db, evidence_id)
    return IntegrityVerifyResponse(**integrity_service.verify_evidence(db, case=case, evidence=evidence, actor=actor))


@router.post(
    "/evidence/{evidence_id}/integrity-test",
    response_model=IntegrityTestResponse,
    summary="Controlled Integrity Test - Demonstration Copy (original untouched)",
)
def controlled_integrity_test(
    evidence_id: str,
    actor: str = Query(default="system"),
    db: Session = Depends(get_db),
) -> IntegrityTestResponse:
    """Copies the evidence, modifies ONLY the copy, and hashes it to demonstrate
    INTEGRITY MISMATCH. The stored original is never modified."""
    case, evidence = evidence_service.get_evidence_any_case(db, evidence_id)
    return IntegrityTestResponse(
        **integrity_service.controlled_integrity_test(db, case=case, evidence=evidence, actor=actor)
    )


@router.get(
    "/evidence/{evidence_id}/custody",
    response_model=list[CustodyEventResponse],
    summary="Chain-of-custody history for an evidence item",
)
def evidence_custody(evidence_id: str, db: Session = Depends(get_db)) -> list[CustodyEventResponse]:
    case, evidence = evidence_service.get_evidence_any_case(db, evidence_id)
    events = custody.events_for_evidence(db, evidence)
    return [serializers.custody_response(db, event) for event in events]


_RESULT_LABELS = {
    IntegrityResult.VERIFIED: terminology.INTEGRITY_VERIFIED,
    IntegrityResult.MISMATCH: terminology.INTEGRITY_MISMATCH,
}


@router.get(
    "/evidence/{evidence_id}/integrity-history",
    response_model=list[IntegrityHistoryEntry],
    summary="History of integrity verification results",
)
def integrity_history(evidence_id: str, db: Session = Depends(get_db)) -> list[IntegrityHistoryEntry]:
    case, evidence = evidence_service.get_evidence_any_case(db, evidence_id)
    rows = list(
        db.scalars(
            select(IntegrityCheck)
            .where(IntegrityCheck.evidence_id == evidence.id)
            .order_by(IntegrityCheck.checked_at.desc(), IntegrityCheck.id.desc())
        )
    )
    return [
        IntegrityHistoryEntry(
            checked_at=row.checked_at,
            computed_hash=row.computed_hash,
            expected_hash=row.expected_hash,
            result=_RESULT_LABELS.get(row.result, str(row.result)),
            actor=row.actor,
        )
        for row in rows
    ]


@router.get(
    "/policy",
    summary="Upload policy (limits and allowed types) for the UI",
)
def upload_policy() -> dict:
    return {
        "max_upload_bytes": config.MAX_UPLOAD_BYTES,
        "max_upload_mb": config.MAX_UPLOAD_MB,
        "allowed_extensions": sorted(config.ALLOWED_EXTENSIONS),
        "hash_algorithm": terminology.HASH_ALGORITHM,
        "integrity_note": terminology.INTEGRITY_DISCLAIMER,
    }
