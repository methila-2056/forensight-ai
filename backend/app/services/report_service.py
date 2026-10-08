"""Forensic report & investigation presentation layer (Phase 6).

This module consumes ONLY data already persisted by Phases 1–5: evidence,
integrity checks, processing runs, findings (rule + ML), correlations,
activity groups, the reconstructed timeline, the evidence graph, and
investigator notes. Generating a report performs no new analysis, no ML
inference, no scoring, and no LLM calls; the same input data produces
identical ``sections`` (identity fields live in ``metadata``).

Guarantees:

* append-only: every generation writes a new immutable snapshot row in
  ``investigation_reports``; ``report_json`` is never rewritten
* case-scoped: every lookup is scoped by both report_id and case_id, so a
  report of one case can never be read through another case (404)
* deterministic: ``sections`` excludes identity fields (report_id,
  generated_at, generated_by), so two generations over unchanged input data
  produce identical ``sections``; sections are stored in a fixed order
* honest wording: SHA-256 matching only proves byte-equivalence with the
  recorded reference; ML anomaly scores are never presented as malicious
  intent; all disclaimers come from terminology (guard-scanned)
* bounded: output lists are capped by module-level constants (not environment
  variables — Architecture §48 adds no env vars without a real need)
* reporting never alters evidence hashes, findings, correlations, timeline,
  or assistant history — it only appends a ``Report Generated`` custody event
* empty cases produce an honest "No analysis result is currently available."
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app import terminology
from app.errors import ApiError
from app.models import (
    Case,
    CustodyAction,
    Evidence,
    ForensicEvent,
    IntegrityCheck,
    IntegrityResult,
    InvestigationReport,
    InvestigatorNote,
    MlFinding,
    RawRecord,
    RuleFinding,
    SeverityLevel,
    utcnow,
)
from app.services import analysis_service, correlate_service, custody, processing_service

# ---------------------------------------------------------------------------
# Bounded output caps (module-level constants; not environment variables).
# ---------------------------------------------------------------------------

_REPORT_MAX_FINDINGS = 200
_REPORT_MAX_TRACES = 50
_REPORT_MAX_CORRELATIONS = 200
_REPORT_MAX_GROUPS = 200
_REPORT_MAX_PROCESS_RUNS = 200
_REPORT_MAX_GRAPH_ROWS = 50

_REPORT_UID_PREFIX = "RPT-"

_SECTION_NAMES = (
    "header",
    "executive_summary",
    "evidence_inventory",
    "integrity_verification",
    "processing_summary",
    "key_findings",
    "finding_traceability",
    "cross_source_correlation",
    "activity_groups",
    "incident_timeline",
    "evidence_graph_summary",
    "investigator_review",
    "ai_ml_explanation",
    "investigation_conclusion",
    "limitations",
)


def _next_report_uid(db: Session) -> str:
    sequence = (
        db.scalar(select(func.count()).select_from(InvestigationReport)) or 0
    ) + 1
    candidate = f"{_REPORT_UID_PREFIX}{sequence:06d}"
    while (
        db.scalar(
            select(InvestigationReport.id).where(
                InvestigationReport.report_id == candidate
            )
        )
        is not None
    ):
        sequence += 1
        candidate = f"{_REPORT_UID_PREFIX}{sequence:06d}"
    return candidate


def _iso(value: Any) -> str | Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _jsonable(value: Any) -> Any:
    """Deep-convert datetimes so the payload is JSON-column safe."""
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return _iso(value)


def _case_evidence(db: Session, case: Case) -> list[Evidence]:
    return list(
        db.scalars(
            select(Evidence)
            .where(Evidence.case_id == case.id)
            .order_by(Evidence.evidence_id.asc())
        )
    )


def _event_count(db: Session, case: Case) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(ForensicEvent)
            .where(ForensicEvent.case_id == case.id)
        )
        or 0
    )


def _is_synthetic(db: Session, case: Case) -> bool:
    if case.demo:
        return True
    marker = db.scalar(
        select(
            exists().where(
                RawRecord.content.like(f"%{terminology.DEMO_LABEL}%"),
                RawRecord.evidence_id.in_(
                    select(Evidence.id).where(Evidence.case_id == case.id)
                ),
            )
        )
    )
    return bool(marker)


# ---------------------------------------------------------------------------
# Section builders — each returns JSON-column-safe plain data
# ---------------------------------------------------------------------------

def _integrity_section(
    db: Session, case: Case, evidence: list[Evidence]
) -> dict[str, Any]:
    latest: dict[int, IntegrityCheck] = {}
    if evidence:
        ids = [row.id for row in evidence]
        checks = db.scalars(
            select(IntegrityCheck)
            .where(IntegrityCheck.evidence_id.in_(ids))
            .order_by(
                IntegrityCheck.evidence_id,
                IntegrityCheck.checked_at.desc(),
                IntegrityCheck.id.desc(),
            )
        )
        for check in checks:
            latest.setdefault(check.evidence_id, check)

    items: list[dict[str, Any]] = []
    mismatches = 0
    verified = 0
    for row in evidence:
        check = latest.get(row.id)
        if check is None:
            result = terminology.REPORT_INTEGRITY_NOT_VERIFIED
        else:
            result = (
                terminology.INTEGRITY_VERIFIED
                if IntegrityResult(check.result) is IntegrityResult.VERIFIED
                else terminology.INTEGRITY_MISMATCH
            )
            if IntegrityResult(check.result) is IntegrityResult.VERIFIED:
                verified += 1
            else:
                mismatches += 1
        items.append(
            {
                "evidence_id": row.evidence_id,
                "original_filename": row.original_filename,
                "result": result,
                "computed_hash": check.computed_hash if check else None,
                "expected_hash": check.expected_hash if check else None,
                "checked_at": _iso(check.checked_at if check else None),
                "actor": check.actor if check else None,
            }
        )

    if not evidence or not latest:
        status = terminology.REPORT_INTEGRITY_NO_CHECK
    elif mismatches:
        status = terminology.INTEGRITY_MISMATCH
    elif verified == len(evidence):
        status = terminology.INTEGRITY_VERIFIED
    else:
        status = terminology.REPORT_INTEGRITY_NOT_VERIFIED

    explanation = (
        terminology.REPORT_INTEGRITY_VERIFIED_EXPLAIN
        if mismatches == 0
        else terminology.REPORT_INTEGRITY_MISMATCH_EXPLAIN
    )

    return {
        "status": status,
        "checked_items": len(items),
        "verified_items": verified,
        "mismatch_items": mismatches,
        "unverified_items": len(items) - verified - mismatches,
        "items": items,
        "explanation": explanation,
        "note": terminology.REPORT_INTEGRITY_NOTE,
    }


def _processing_section(db: Session, case: Case) -> dict[str, Any]:
    runs = processing_service.runs_for_case(db, case)[:_REPORT_MAX_PROCESS_RUNS]
    total = len(runs)
    received = sum(run.records_received for run in runs)
    normalized = sum(run.records_normalized for run in runs)
    rejected = sum(run.records_rejected for run in runs)
    return {
        "run_count": total,
        "records_received": received,
        "records_normalized": normalized,
        "records_rejected": rejected,
        "runs": [
            {
                "run_id": run.run_uid,
                "evidence_id": (evidence.evidence_id if evidence else ""),
                "evidence_filename": (evidence.original_filename if evidence else ""),
                "parser": run.parser,
                "status": run.status,
                "records_received": run.records_received,
                "records_normalized": run.records_normalized,
                "records_rejected": run.records_rejected,
                "duplicates_detected": run.duplicates_detected,
                "started_at": _iso(run.started_at),
                "completed_at": _iso(run.completed_at),
                "error": run.error,
            }
            for run in runs
            for evidence in [db.get(Evidence, run.evidence_id)]
        ],
    }


def _findings_section(db: Session, case: Case) -> dict[str, Any]:
    rows, total = analysis_service.list_findings(
        db, case, limit=_REPORT_MAX_FINDINGS
    )
    rule_count = sum(1 for kind, _ in rows if kind == "rule")
    ml_count = len(rows) - rule_count
    findings: list[dict[str, Any]] = []
    for kind, row in rows:
        entry: dict[str, Any] = {
            "finding_id": row.finding_uid,
            "kind": kind,
            "title": row.title,
            "severity": row.severity,
            "status": row.status,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
            "entry_type": terminology.REPORT_SYSTEM_ENTRY,
        }
        if kind == "rule":
            entry.update(
                {
                    "rule_id": row.rule_id,
                    "confidence": row.confidence,
                    "composite_suspicion_score": row.composite_suspicion_score,
                    "event_count": len(row.triggered_event_ids or []),
                    "evidence_count": len(row.evidence_ids or []),
                }
            )
        else:
            entry.update(
                {
                    "model_name": row.model_name,
                    "anomaly_score": row.score,
                    "composite_suspicion_score": row.composite_suspicion_score,
                    "event_count": len(row.event_ids or []),
                    "evidence_count": len(row.evidence_ids or []),
                }
            )
        findings.append(entry)

    note = terminology.REPORT_NO_ANALYSIS if total == 0 else terminology.ANALYSIS_SCOPE_NOTE
    return {
        "total": total,
        "rule_findings": rule_count,
        "ml_findings": ml_count,
        "findings": findings,
        "note": note,
    }


def _trace_for_finding(
    db: Session, kind: str, row: RuleFinding | MlFinding
) -> dict[str, Any]:
    if kind == "rule":
        reason: Any = row.reasons or [row.explanation]
    else:
        reason = row.explanation if isinstance(row.explanation, str) else row.explanation

    events = analysis_service.finding_events(db, kind, row)
    linked: list[dict[str, Any]] = []
    for event in events:
        raw_record: RawRecord | None = event.raw_record
        evidence: Evidence | None = event.evidence or db.get(Evidence, event.evidence_id)
        linked.append(
            {
                "event": {
                    "event_id": event.event_uid,
                    "timestamp": _iso(event.timestamp),
                    "source_type": event.source_type,
                    "event_type": event.event_type,
                    "user": event.user,
                    "host": event.host,
                    "action": event.action,
                },
                "raw_record": (
                    {"row_index": raw_record.row_index, "content": raw_record.content}
                    if raw_record
                    else None
                ),
                "evidence": (
                    {
                        "evidence_id": evidence.evidence_id,
                        "original_filename": evidence.original_filename,
                        "sha256": evidence.sha256,
                    }
                    if evidence
                    else None
                ),
                "recorded_sha256": evidence.sha256 if evidence else None,
            }
        )

    return {
        "finding_id": row.finding_uid,
        "kind": kind,
        "title": row.title,
        "severity": row.severity,
        "status": row.status,
        "unavailable": not events,
        "note": None if events else terminology.REPORT_TRACE_UNAVAILABLE,
        "reason": reason,
        "ladder": list(terminology.TRACEABILITY_STEPS),
        "linked_events": linked,
    }


def _traceability_section(db: Session, case: Case) -> dict[str, Any]:
    rows, _ = analysis_service.list_findings(
        db, case, limit=_REPORT_MAX_TRACES
    )
    return {
        "traced_findings": len(rows),
        "max_traces": _REPORT_MAX_TRACES,
        "traces": [_trace_for_finding(db, kind, row) for kind, row in rows],
    }


def _correlation_section(db: Session, case: Case) -> dict[str, Any]:
    rows, total, run = correlate_service.list_correlations(
        db, case, limit=_REPORT_MAX_CORRELATIONS
    )
    return {
        "run_id": run.run_uid if run else None,
        "total": total,
        "shown": len(rows),
        "truncated": total > _REPORT_MAX_CORRELATIONS,
        "disclaimer": terminology.CORRELATION_DISCLAIMER,
        "correlations": [
            {
                "correlation_id": row.correlation_uid,
                "correlation_type": row.correlation_type,
                "event_a": _event_compact(db, row.event_a) if row.event_a else None,
                "event_b": _event_compact(db, row.event_b) if row.event_b else None,
                "time_delta_seconds": row.time_delta_seconds,
                "confidence": row.confidence,
                "reason": row.reason,
                "evidence_ids": sorted(row.evidence_ids or []),
            }
            for row in rows
        ],
    }


def _event_compact(db: Session, event: ForensicEvent | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "event_id": event.event_uid,
        "timestamp": _iso(event.timestamp),
        "source_type": event.source_type,
        "event_type": event.event_type,
        "user": event.user,
        "host": event.host,
        "process": event.process,
        "file_path": event.file_path,
        "action": event.action,
    }


def _groups_section(db: Session, case: Case) -> dict[str, Any]:
    rows, total, _run = correlate_service.list_groups(db, case, limit=_REPORT_MAX_GROUPS)
    return {
        "total": total,
        "shown": len(rows),
        "truncated": total > _REPORT_MAX_GROUPS,
        "note": terminology.CORRELATION_GROUP_NOTE,
        "groups": [
            {
                "group_id": row.group_uid,
                "kind": row.kind,
                "title": row.title,
                "severity": row.severity,
                "explanation": row.explanation,
                "time_start": _iso(row.time_start),
                "time_end": _iso(row.time_end),
                "event_count": len(row.member_event_ids or []),
                "correlation_count": len(row.correlation_uids or []),
                "evidence_ids": sorted(row.evidence_ids or []),
            }
            for row in rows
        ],
    }


def _timeline_section(db: Session, case: Case) -> dict[str, Any]:
    timeline = correlate_service.timeline(db, case)
    return {
        "label": timeline.label,
        "disclaimer": timeline.disclaimer,
        "total": timeline.total,
        "shown": len(timeline.entries),
        "truncated": timeline.truncated,
        "note": timeline.note,
        "entries": [
            {
                "timestamp": _iso(entry.timestamp),
                "event_id": entry.event_id,
                "source_type": entry.source_type,
                "event_type": entry.event_type,
                "user": entry.user,
                "host": entry.host,
                "process": entry.process,
                "file_path": entry.file_path,
                "action": entry.action,
                "anomaly_score": entry.anomaly_score,
                "is_anomalous": entry.is_anomalous,
                "significance": entry.significance,
                "reasons": entry.reasons,
                "finding_ids": entry.finding_ids,
                "correlation_ids": entry.correlation_ids,
                "evidence_id": entry.evidence_id,
                "context": entry.context,
            }
            for entry in timeline.entries
        ],
    }


def _graph_section(db: Session, case: Case) -> dict[str, Any]:
    graph = correlate_service.graph(db, case)
    node_counts = Counter(node.type for node in graph.nodes)
    edge_counts = Counter(edge.relation for edge in graph.edges)
    return {
        "run_id": graph.run_id,
        "node_type_counts": {
            kind: node_counts.get(kind, 0)
            for kind in ("evidence", "finding", "event")
        },
        "edge_relation_counts": {
            rel: edge_counts.get(rel, 0)
            for rel in ("contains", "triggered", "correlated")
        },
        "truncated": graph.truncated,
        "note": graph.note,
        "disclaimer": graph.disclaimer,
        "max_nodes": graph.max_nodes,
        "max_edges": graph.max_edges,
        "table_rows": [
            {"source": row.source, "relation": row.relation, "target": row.target}
            for row in graph.table_rows[:_REPORT_MAX_GRAPH_ROWS]
        ],
    }


def _review_section(db: Session, case: Case) -> dict[str, Any]:
    notes = list(
        db.scalars(
            select(InvestigatorNote)
            .where(InvestigatorNote.case_id == case.id)
            .order_by(InvestigatorNote.created_at.asc(), InvestigatorNote.id.asc())
        )
    )
    rows, _ = analysis_service.list_findings(db, case, limit=_REPORT_MAX_FINDINGS)
    status_counts: dict[str, int] = {}
    for _kind, row in rows:
        key = str(row.status)
        status_counts[key] = status_counts.get(key, 0) + 1
    return {
        "notes": [
            {
                "finding_id": note.finding_uid,
                "author": note.author,
                "body": note.body,
                "created_at": _iso(note.created_at),
                "entry_type": terminology.REPORT_REVIEW_ENTRY,
            }
            for note in notes
        ],
        "finding_status_counts": status_counts,
    }


def _ml_section(db: Session, case: Case) -> dict[str, Any]:
    runs = analysis_service.runs_for_case(db, case)
    latest = next((run for run in runs if run.status == "Completed"), None)
    stats = (latest.stats or {}) if latest else {}
    return {
        "analysis_runs": len(runs),
        "latest_run_id": latest.run_uid if latest else None,
        "latest_run_status": latest.status.value if latest else None,
        "abstain_note": stats.get("abstain_note"),
        "abstain_reason": stats.get("abstain_reason"),
        "strategy": stats.get("strategy"),
        "ml_findings": stats.get("ml_findings", 0),
        "rule_findings": stats.get("rule_findings", 0),
        "statement": terminology.REPORT_ML_STATEMENT,
        "disclaimer": terminology.ANOMALY_DISCLAIMER,
    }


def _conclusion_section(
    db: Session, case: Case, *, evidence: list[Evidence], events_total: int, findings_total: int
) -> dict[str, Any]:
    if not evidence:
        statement = terminology.REPORT_NO_ANALYSIS
    elif events_total == 0 and findings_total == 0:
        statement = terminology.REPORT_CONCLUSION_INSUFFICIENT
    elif findings_total == 0:
        statement = terminology.REPORT_CONCLUSION_NO_FINDINGS
    else:
        _rows, correlations_total, _run = correlate_service.list_correlations(
            db, case, limit=1
        )
        statement = (
            terminology.REPORT_CONCLUSION_WITH_CORRELATION
            if correlations_total
            else terminology.REPORT_CONCLUSION_NO_CORRELATION
        )

    notes: list[str] = []
    if findings_total:
        rows, _ = analysis_service.list_findings(
            db, case, kind=None, limit=_REPORT_MAX_FINDINGS
        )
        high_critical = any(
            SeverityLevel(row.severity) in (SeverityLevel.HIGH, SeverityLevel.CRITICAL)
            for _kind, row in rows
        )
        if high_critical:
            notes.append(terminology.REPORT_HIGH_SEVERITY_NOTE)

    return {"statement": statement, "notes": notes}


def _limitations_section(synthetic: bool) -> dict[str, Any]:
    return {
        "notices": [
            terminology.REPORT_LIMIT_PROTOTYPE,
            terminology.REPORT_LIMIT_INTEGRITY,
            terminology.REPORT_LIMIT_ML,
            terminology.REPORT_LIMIT_SCORES,
            terminology.REPORT_LIMIT_REVIEW,
            terminology.REPORT_LIMIT_DATA,
        ],
        "synthetic": terminology.DEMO_LABEL if synthetic else None,
    }


def _sections(db: Session, case: Case) -> dict[str, Any]:
    """Deterministic, fixed-order report sections (identity fields excluded)."""
    evidence = _case_evidence(db, case)
    events_total = _event_count(db, case)
    synthetic = _is_synthetic(db, case)

    findings_total, rule_ml_total = 0, 0
    rows, findings_total = analysis_service.list_findings(
        db, case, limit=_REPORT_MAX_FINDINGS
    )
    rule_count = sum(1 for kind, _ in rows if kind == "rule")

    integrity = _integrity_section(db, case, evidence)
    processing = _processing_section(db, case)
    findings = _findings_section(db, case)
    correlations = _correlation_section(db, case)
    groups = _groups_section(db, case)

    overview_lines: list[str] = []
    overview_lines.append(
        f"This case contains {len(evidence)} evidence file(s), of which "
        f"{processing['run_count']} processing run(s) produced {events_total} "
        f"normalized forensic event(s)."
    )
    overview_lines.append(
        f"Automated analysis recorded {findings_total} finding(s) "
        f"({rule_count} rule, {findings_total - rule_count} ML)."
    )
    overview_lines.append(
        f"Cross-source correlation produced {correlations['total']} link(s) and "
        f"{groups['total']} activity group(s)."
    )
    overview_lines.append(
        f"Integrity verification status: {integrity['status']}."
    )
    if synthetic:
        overview_lines.append(terminology.DEMO_LABEL)

    timeline = _timeline_section(db, case)
    graph = _graph_section(db, case)
    conclusion = _conclusion_section(
        db,
        case,
        evidence=evidence,
        events_total=events_total,
        findings_total=findings_total,
    )

    return {
        "header": {
            "report_title": case.name + " — " + terminology.REPORT_TITLE,
            "case_id": case.case_id,
            "case_name": case.name,
            "case_status": case.status,
            "case_severity": case.severity,
            "investigator": case.investigator,
            "report_version": terminology.REPORT_VERSION,
            "schema": terminology.REPORT_SCHEMA,
            "status": terminology.REPORT_STATUS,
        },
        "executive_summary": {
            "overview": " ".join(overview_lines),
            "counts": {
                "evidence": len(evidence),
                "normalized_events": events_total,
                "processing_runs": processing["run_count"],
                "findings": findings_total,
                "rule_findings": rule_count,
                "ml_findings": findings_total - rule_count,
                "correlations": correlations["total"],
                "activity_groups": groups["total"],
                "timeline_entries": timeline["total"],
            },
            "integrity_status": integrity["status"],
            "note": findings["note"],
        },
        "evidence_inventory": {
            "count": len(evidence),
            "items": [
                {
                    "evidence_id": row.evidence_id,
                    "original_filename": row.original_filename,
                    "evidence_type": row.evidence_type,
                    "mime_type": row.mime_type,
                    "file_size": row.file_size,
                    "sha256": row.sha256,
                    "status": row.status,
                    "record_count": row.record_count,
                    "parse_ok": row.parse_ok,
                    "parse_rejected": row.parse_rejected,
                    "uploaded_at": _iso(row.uploaded_at),
                }
                for row in evidence
            ],
        },
        "integrity_verification": integrity,
        "processing_summary": processing,
        "key_findings": findings,
        "finding_traceability": _traceability_section(db, case),
        "cross_source_correlation": correlations,
        "activity_groups": groups,
        "incident_timeline": timeline,
        "evidence_graph_summary": graph,
        "investigator_review": _review_section(db, case),
        "ai_ml_explanation": _ml_section(db, case),
        "investigation_conclusion": conclusion,
        "limitations": _limitations_section(synthetic),
    }


# ---------------------------------------------------------------------------
# Public generation + queries
# ---------------------------------------------------------------------------

def generate_report(
    db: Session, *, case: Case, title: str | None = None, actor: str | None = None
) -> InvestigationReport:
    """Generate and persist one immutable report snapshot (append-only)."""
    clean_title = (title or "").strip() or terminology.REPORT_TITLE
    generated_by = (actor or "investigator").strip() or "investigator"
    report_id = _next_report_uid(db)
    now = utcnow()

    sections = _sections(db, case)
    report = InvestigationReport(
        report_id=report_id,
        case_id=case.id,
        title=clean_title[:255],
        generated_at=now,
        generated_by=generated_by[:127],
        report_version=terminology.REPORT_VERSION,
        schema=terminology.REPORT_SCHEMA,
        status=terminology.REPORT_STATUS,
        report_json={
            "metadata": {
                "report_id": report_id,
                "case_id": case.case_id,
                "title": clean_title[:255],
                "report_version": terminology.REPORT_VERSION,
                "schema": terminology.REPORT_SCHEMA,
                "status": terminology.REPORT_STATUS,
                "generated_at": now.isoformat(),
                "generated_by": generated_by[:127],
            },
            "sections": _jsonable(sections),
        },
        created_at=now,
    )
    db.add(report)
    db.flush()
    custody.record(
        db,
        case=case,
        action=CustodyAction.REPORT_GENERATED,
        actor=generated_by[:127],
        details={
            "report_id": report_id,
            "title": clean_title[:255],
            "report_version": terminology.REPORT_VERSION,
            "schema": terminology.REPORT_SCHEMA,
        },
    )
    case.last_activity = utcnow()
    db.commit()
    db.refresh(report)
    return report


def list_reports(db: Session, case: Case) -> list[InvestigationReport]:
    return list(
        db.scalars(
            select(InvestigationReport)
            .where(InvestigationReport.case_id == case.id)
            .order_by(
                InvestigationReport.generated_at.desc(), InvestigationReport.id.desc()
            )
        )
    )


def get_report(db: Session, case: Case, report_id: str) -> InvestigationReport:
    """Case-scoped lookup: a report of another case is never visible here."""
    row = db.scalar(
        select(InvestigationReport).where(
            InvestigationReport.report_id == report_id,
            InvestigationReport.case_id == case.id,
        )
    )
    if row is None:
        raise ApiError(
            404,
            "REPORT_NOT_FOUND",
            f"Report {report_id} was not found for case {case.case_id}.",
        )
    return row


def _metadata(row: InvestigationReport) -> dict[str, Any]:
    payload = row.report_json
    if isinstance(payload, dict):
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            return metadata
    return {}


def report_summary(row: InvestigationReport) -> dict[str, Any]:
    metadata = _metadata(row)
    return {
        "report_id": row.report_id,
        "case_id": metadata.get("case_id", ""),
        "title": row.title,
        "report_version": row.report_version,
        "schema": row.schema,
        "status": row.status,
        "generated_at": row.generated_at,
        "generated_by": row.generated_by,
    }


def serialize_report(row: InvestigationReport) -> dict[str, Any]:
    """Flattened identity + deterministic sections (used by POST and detail)."""
    metadata = _metadata(row)
    payload = row.report_json
    sections = payload.get("sections", {}) if isinstance(payload, dict) else {}
    return {
        **report_summary(row),
        "case_id": metadata.get("case_id", ""),
        "sections": sections,
    }


def raw_json(row: InvestigationReport) -> dict[str, Any]:
    """The stored payload as written: ``{"metadata": ..., "sections": ...}``."""
    return dict(row.report_json) if isinstance(row.report_json, dict) else {}