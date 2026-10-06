"""Evidence processing endpoints (Phase 2).

Security notes:
* processing only reads stored evidence bytes (never executes them) and
  writes derived rows (raw_records, forensic_events, processing_runs)
* a fresh SHA-256 re-check runs before any parsing; mismatch aborts with a
  structured error and a FAILED run
* responses never expose server filesystem paths
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RawRecord
from app.schemas import (
    EvidenceProcessingResponse,
    ProcessCaseResponse,
    ProcessRequest,
    ProcessingRunResponse,
    RejectedRecordResponse,
)
from app.services import (
    case_service,
    evidence_service,
    processing_service,
    serializers,
)

router = APIRouter(tags=["processing"])


@router.post(
    "/cases/{case_id}/process",
    response_model=ProcessCaseResponse,
    summary="Process evidence of a case (parse, normalize, record processing runs)",
)
def process_case(
    case_id: str,
    payload: Optional[ProcessRequest] = None,
    db: Session = Depends(get_db),
) -> ProcessCaseResponse:
    case = case_service.get_case(db, case_id)
    request = payload or ProcessRequest()
    runs = processing_service.process_case(
        db,
        case=case,
        evidence_ids=request.evidence_ids,
        actor=request.actor or "system",
    )
    return ProcessCaseResponse(
        case_id=case.case_id,
        runs=[serializers.processing_run_response(db, run) for run in runs],
    )


@router.get(
    "/cases/{case_id}/processing-runs",
    response_model=list[ProcessingRunResponse],
    summary="Processing run history of a case (newest first)",
)
def list_processing_runs(case_id: str, db: Session = Depends(get_db)) -> list[ProcessingRunResponse]:
    case = case_service.get_case(db, case_id)
    return [
        serializers.processing_run_response(db, run)
        for run in processing_service.runs_for_case(db, case)
    ]


@router.get(
    "/evidence/{evidence_id}/processing",
    response_model=EvidenceProcessingResponse,
    summary="Processing runs and parse counts of one evidence item",
)
def evidence_processing(evidence_id: str, db: Session = Depends(get_db)) -> EvidenceProcessingResponse:
    case, evidence = evidence_service.get_evidence_any_case(db, evidence_id)
    return EvidenceProcessingResponse(
        evidence_id=evidence.evidence_id,
        original_filename=evidence.original_filename,
        sha256=evidence.sha256,
        status=evidence.status,
        record_count=evidence.record_count,
        parse_ok=evidence.parse_ok,
        parse_rejected=evidence.parse_rejected,
        runs=[
            serializers.processing_run_response(db, run)
            for run in processing_service.runs_for_evidence(db, evidence)
        ],
    )


@router.get(
    "/evidence/{evidence_id}/rejected-records",
    response_model=list[RejectedRecordResponse],
    summary="Malformed/rejected records retained for review (never discarded)",
)
def rejected_records(evidence_id: str, db: Session = Depends(get_db)) -> list[RejectedRecordResponse]:
    _, evidence = evidence_service.get_evidence_any_case(db, evidence_id)
    rows = list(
        db.scalars(
            select(RawRecord)
            .where(
                RawRecord.evidence_id == evidence.id,
                RawRecord.reject_reason.is_not(None),
            )
            .order_by(RawRecord.row_index)
        )
    )
    runs = processing_service.runs_for_evidence(db, evidence)
    latest = runs[0] if runs else None
    return [
        RejectedRecordResponse(
            evidence_id=evidence.evidence_id,
            row_index=row.row_index,
            parser=latest.parser if latest else "",
            reason=row.reject_reason,
            original_record=row.content,
            processed_at=latest.completed_at if latest else None,
        )
        for row in rows
    ]
