"""Evidence processing pipeline (Phase 2).

    RAW EVIDENCE → integrity re-check → parser detection → validation
    → normalization → ForensicEvent / RawRecord → processing log

Guarantees:

* raw evidence bytes are only ever read; all outputs are derived rows that
  can be rebuilt by reprocessing
* malformed records are retained as RawRecord rows with reject reasons —
  nothing is silently discarded
* duplicate records are preserved and marked in derived data with an
  explanation; they are never deleted
* every normalized event links to its RawRecord and Evidence (SHA-256)
* run status never claims Completed when records were rejected (Partial)
  or processing failed (Failed)
* derived events that preserved history references (correlation links,
  finding/group event references) are never replaced: the rebuild is
  skipped for that evidence and the run carries an explanatory warning,
  so append-only history keeps pointing at real events

Evidence content is treated strictly as data — never executed, never
interpreted as instructions, never passed to a shell.
"""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app import config
from app.engines.parsing import UnknownFormatError, parse_evidence
from app.errors import ApiError
from app.models import (
    Case,
    Correlation,
    CustodyAction,
    Evidence,
    EvidenceStatus,
    ForensicEvent,
    InvestigationGroup,
    MlFinding,
    ProcessingRun,
    ProcessingStatus,
    RawRecord,
    RuleFinding,
    SeverityLevel,
    SourceType,
    utcnow,
)
from app.services import custody, evidence_service
from app.storage.raw_store import RawEvidenceStore, RawEvidenceStoreError

logger = logging.getLogger("forensight.processing")

# Fields that make up the duplicate fingerprint (canonical schema).
_DEDUPE_FIELDS = (
    "timestamp", "event_type", "user", "host", "action",
    "source_ip", "destination_ip", "process", "file_path",
)

_ERROR_STATUS = {
    "UNRECOGNIZED_EVIDENCE_FORMAT": 422,
    "EVIDENCE_INTEGRITY_MISMATCH": 409,
    "EVIDENCE_STORE_UNAVAILABLE": 409,
    "PROCESSING_FAILED": 500,
}


class _PipelineError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _next_run_uid(db: Session) -> str:
    last = db.scalar(select(ProcessingRun.run_uid).order_by(ProcessingRun.run_uid.desc()).limit(1))
    number = int(last.split("-")[1]) + 1 if last else 1
    return f"RUN-{number:06d}"


def _first_event_uid(db: Session) -> int:
    last = db.scalar(select(ForensicEvent.event_uid).order_by(ForensicEvent.event_uid.desc()).limit(1))
    return int(last.split("-")[1]) if last else 0


def _dedupe_hash(common: dict) -> str:
    parts: list[str] = []
    for key in _DEDUPE_FIELDS:
        value = common.get(key)
        if key == "timestamp" and value is not None:
            value = value.isoformat()
        parts.append("" if value is None else str(value))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _history_pins_events(db: Session, *, case: Case, evidence: Evidence) -> str | None:
    """Reason preserved history forbids replacing this evidence's events, or None.

    Reprocessing rebuilds derived rows, but downstream history is append-only
    and points at specific events: correlation links hold a foreign key to the
    event rows, and stored findings/groups hold event-uid lists used for
    traceability. Replacing those events would either violate the foreign key
    or silently break the recorded chain of references, so the rebuild must be
    skipped for evidence whose events are already referenced.
    """
    event_ids = list(
        db.scalars(
            select(ForensicEvent.id).where(ForensicEvent.evidence_id == evidence.id)
        )
    )
    if not event_ids:
        return None

    linked = db.scalar(
        select(func.count())
        .select_from(Correlation)
        .where(
            or_(
                Correlation.event_a_id.in_(event_ids),
                Correlation.event_b_id.in_(event_ids),
            )
        )
    )
    if linked:
        return (
            f"rebuild skipped: {linked} preserved correlation link(s) reference "
            "these events (append-only history keeps the existing rows)"
        )

    event_uids = set(
        db.scalars(
            select(ForensicEvent.event_uid).where(ForensicEvent.id.in_(event_ids))
        )
    )
    checks = (
        (
            db.scalars(
                select(RuleFinding.triggered_event_ids).where(
                    RuleFinding.case_id == case.id
                )
            ),
            "finding",
        ),
        (
            db.scalars(
                select(MlFinding.event_ids).where(MlFinding.case_id == case.id)
            ),
            "finding",
        ),
        (
            db.scalars(
                select(InvestigationGroup.member_event_ids).where(
                    InvestigationGroup.case_id == case.id
                )
            ),
            "activity group",
        ),
    )
    for stored_rows, label in checks:
        for stored in stored_rows:
            if event_uids & set(stored or []):
                return (
                    f"rebuild skipped: a preserved {label} references these events "
                    "(append-only history keeps the existing rows)"
                )
    return None


def process_evidence(
    db: Session,
    *,
    case: Case,
    evidence: Evidence,
    actor: str = "system",
) -> ProcessingRun:
    """Process one evidence item; failures are recorded on the returned run."""
    previous_status = evidence.status
    run = ProcessingRun(
        run_uid=_next_run_uid(db),
        case_id=case.id,
        evidence_id=evidence.id,
        parser="",
        status=ProcessingStatus.PENDING,
        started_at=utcnow(),
    )
    db.add(run)
    evidence.status = EvidenceStatus.PROCESSING
    custody.record(
        db,
        case=case,
        evidence=evidence,
        action=CustodyAction.PROCESSING_STARTED,
        actor=actor,
        details={
            "run_id": run.run_uid,
            "stage": "process",
            "filename": evidence.original_filename,
        },
    )
    db.commit()
    run_id = run.id

    warnings: list[str] = []
    counts = {
        "records_received": 0,
        "records_parsed": 0,
        "records_normalized": 0,
        "records_rejected": 0,
        "duplicates_detected": 0,
    }

    try:
        store = RawEvidenceStore(config.EVIDENCE_STORE_DIR)
        try:
            data = store.read_bytes(case.case_id, evidence.evidence_id)
        except RawEvidenceStoreError as exc:
            raise _PipelineError("EVIDENCE_STORE_UNAVAILABLE", str(exc)) from exc

        # Refuse to process evidence that no longer matches its recorded hash.
        verification = store.verify_hash(
            case.case_id, evidence.evidence_id, evidence.original_hash
        )
        if not verification.verified:
            raise _PipelineError(
                "EVIDENCE_INTEGRITY_MISMATCH",
                "Evidence integrity mismatch — processing aborted because the "
                "stored file no longer matches its recorded SHA-256.",
            )

        outcome = parse_evidence(
            data,
            filename=evidence.original_filename,
            declared_type=evidence.evidence_type.value,
            max_records=config.MAX_RECORDS_PER_RUN,
        )
        warnings.extend(outcome.warnings)
        run.parser = f"{outcome.parser_name}/{outcome.source_type}"

        # Reprocessing replaces derived rows for this evidence only — unless
        # preserved history still references the existing events, in which
        # case the rows are kept and the run explains why (see helper).
        pin_reason = _history_pins_events(db, case=case, evidence=evidence)
        rebuild = pin_reason is None
        if rebuild:
            db.execute(delete(ForensicEvent).where(ForensicEvent.evidence_id == evidence.id))
            db.execute(delete(RawRecord).where(RawRecord.evidence_id == evidence.id))
            db.flush()
        elif pin_reason:
            warnings.append(pin_reason)

        event_counter = _first_event_uid(db)
        seen: dict[str, str] = {}

        for record in outcome.batch.records:
            counts["records_received"] += 1

            if record.parse_error:
                counts["records_rejected"] += 1
                if rebuild:
                    db.add(
                        RawRecord(
                            evidence_id=evidence.id,
                            row_index=record.row_index,
                            content=record.raw,
                            reject_reason=record.parse_error,
                        )
                    )
                continue

            counts["records_parsed"] += 1
            mapped = outcome.normalizer.normalize(record.fields, record.row_index)
            if mapped.reject_reason:
                counts["records_rejected"] += 1
                if rebuild:
                    db.add(
                        RawRecord(
                            evidence_id=evidence.id,
                            row_index=record.row_index,
                            content=record.raw,
                            reject_reason=mapped.reject_reason,
                        )
                    )
                continue

            dedupe = _dedupe_hash(mapped.common)
            metadata = dict(mapped.metadata)
            if dedupe in seen:
                counts["duplicates_detected"] += 1
                metadata["duplicate"] = {
                    "of": seen[dedupe],
                    "reason": (
                        "identical timestamp and entity fields as an earlier "
                        "record in this evidence file"
                    ),
                }
            event_counter += 1
            event_uid = f"EVT-{event_counter:06d}"
            seen.setdefault(dedupe, event_uid)
            counts["records_normalized"] += 1

            if not rebuild:
                continue

            raw_record = RawRecord(
                evidence_id=evidence.id,
                row_index=record.row_index,
                content=record.raw,
                reject_reason=None,
            )
            db.add(raw_record)
            db.flush()

            severity = mapped.common.get("severity")
            db.add(
                ForensicEvent(
                    event_uid=event_uid,
                    case_id=case.id,
                    evidence_id=evidence.id,
                    raw_record_id=raw_record.id,
                    timestamp=mapped.common.get("timestamp"),
                    tz_note=mapped.common.get("tz_note"),
                    source_type=SourceType(mapped.common["source_type"]),
                    event_type=mapped.common.get("event_type") or "",
                    user=mapped.common.get("user"),
                    host=mapped.common.get("host"),
                    source_ip=mapped.common.get("source_ip"),
                    destination_ip=mapped.common.get("destination_ip"),
                    process=mapped.common.get("process"),
                    file_path=mapped.common.get("file_path"),
                    action=mapped.common.get("action"),
                    severity=SeverityLevel(severity) if severity else None,
                    extra=metadata or None,
                    dedupe_hash=dedupe,
                )
            )

        truncated = any(warning.startswith("record limit") for warning in warnings)
        if counts["records_rejected"] > 0 or counts["records_received"] == 0 or truncated:
            status = ProcessingStatus.PARTIAL
        else:
            status = ProcessingStatus.COMPLETED

        run = db.get(ProcessingRun, run_id)
        run.status = status
        run.completed_at = utcnow()
        run.warnings = warnings or None
        for key, value in counts.items():
            setattr(run, key, value)

        evidence.record_count = counts["records_received"]
        evidence.parse_ok = counts["records_normalized"]
        evidence.parse_rejected = counts["records_rejected"]
        evidence.status = EvidenceStatus.PROCESSED
        case.last_activity = utcnow()

        custody.record(
            db,
            case=case,
            evidence=evidence,
            action=CustodyAction.PROCESSING_COMPLETED,
            actor=actor,
            details={
                "run_id": run.run_uid,
                "status": status.value,
                "parser": run.parser,
                "records_received": counts["records_received"],
                "records_normalized": counts["records_normalized"],
                "records_rejected": counts["records_rejected"],
                "duplicates_detected": counts["duplicates_detected"],
            },
        )
        db.commit()
        db.refresh(run)
        return run

    except UnknownFormatError as exc:
        return _finalize_failed(
            db,
            run_id=run_id,
            evidence_id=evidence.id,
            previous_status=previous_status,
            code="UNRECOGNIZED_EVIDENCE_FORMAT",
            message=exc.message,
            warnings=warnings + exc.hints,
        )
    except _PipelineError as exc:
        return _finalize_failed(
            db,
            run_id=run_id,
            evidence_id=evidence.id,
            previous_status=previous_status,
            code=exc.code,
            message=exc.message,
            warnings=warnings,
        )
    except Exception:  # noqa: BLE001 - recorded as a FAILED run, path not exposed
        logger.exception("Unexpected processing failure for %s", evidence.evidence_id)
        return _finalize_failed(
            db,
            run_id=run_id,
            evidence_id=evidence.id,
            previous_status=previous_status,
            code="PROCESSING_FAILED",
            message="Evidence processing failed unexpectedly; see server logs.",
            warnings=warnings,
        )


def _finalize_failed(
    db: Session,
    *,
    run_id: int,
    evidence_id: int,
    previous_status: EvidenceStatus,
    code: str,
    message: str,
    warnings: list[str],
) -> ProcessingRun:
    db.rollback()
    run = db.get(ProcessingRun, run_id)
    evidence = db.get(Evidence, evidence_id)
    if evidence is not None:
        evidence.status = previous_status
    run.status = ProcessingStatus.FAILED
    run.error_code = code
    run.error = message
    run.completed_at = utcnow()
    run.warnings = warnings or None
    db.commit()
    db.refresh(run)
    return run


def process_case(
    db: Session,
    *,
    case: Case,
    evidence_ids: list[str] | None = None,
    actor: str = "system",
) -> list[ProcessingRun]:
    """Process selected (or all) evidence of a case.

    Failures are recorded as FAILED runs. A request whose runs all failed is
    answered with a structured error envelope that references the runs.
    """
    if evidence_ids:
        items = [evidence_service.get_evidence(db, case, eid) for eid in evidence_ids]
    else:
        items = evidence_service.list_evidence(db, case)
        if not items:
            raise ApiError(
                400,
                "CASE_HAS_NO_EVIDENCE",
                f"Case {case.case_id} has no evidence to process.",
            )

    runs = [
        process_evidence(db, case=case, evidence=evidence, actor=actor)
        for evidence in items
    ]

    if all(run.status == ProcessingStatus.FAILED for run in runs):
        first = runs[0]
        status_code = _ERROR_STATUS.get(first.error_code or "", 500)
        raise ApiError(
            status_code,
            first.error_code or "PROCESSING_FAILED",
            first.error or "Evidence processing failed.",
            detail={
                "runs": [
                    {"run_id": run.run_uid, "evidence_id": _evidence_uid(db, run)}
                    for run in runs
                ]
            },
        )
    return runs


def _evidence_uid(db: Session, run: ProcessingRun) -> str | None:
    evidence = db.get(Evidence, run.evidence_id)
    return evidence.evidence_id if evidence else None


def run_response_fields(run: ProcessingRun, db: Session) -> dict:
    """Shared mapping used by serializers (adds case/evidence identifiers)."""
    case = db.get(Case, run.case_id)
    evidence = db.get(Evidence, run.evidence_id)
    return {
        "run_id": run.run_uid,
        "case_id": case.case_id if case else "",
        "evidence_id": evidence.evidence_id if evidence else "",
        "evidence_filename": evidence.original_filename if evidence else "",
        "parser": run.parser,
        "status": run.status,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "records_received": run.records_received,
        "records_parsed": run.records_parsed,
        "records_normalized": run.records_normalized,
        "records_rejected": run.records_rejected,
        "duplicates_detected": run.duplicates_detected,
        "warnings": run.warnings or [],
        "error_code": run.error_code,
        "error": run.error,
    }


def runs_for_case(db: Session, case: Case) -> list[ProcessingRun]:
    return list(
        db.scalars(
            select(ProcessingRun)
            .where(ProcessingRun.case_id == case.id)
            .order_by(ProcessingRun.id.desc())
        )
    )


def runs_for_evidence(db: Session, evidence: Evidence) -> list[ProcessingRun]:
    return list(
        db.scalars(
            select(ProcessingRun)
            .where(ProcessingRun.evidence_id == evidence.id)
            .order_by(ProcessingRun.id.desc())
        )
    )
