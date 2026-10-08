"""Per-request assistant context: the evidence the answerer reasons over (Phase 5).

The context is assembled by case-scoped retrieval only. It carries the raw
rows plus their identifiers (finding UIDs, event UIDs, correlation/group UIDs,
evidence UIDs) so the answerer can emit evidence-backed, clickable sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app import config
from app.assistant import retrieval
from app.assistant.intents import ClassifiedIntent, Intent
from app.models import Case, FindingStatus
from app.services import analysis_service


@dataclass
class AssistantContext:
    case: Case
    classified: ClassifiedIntent = field(default_factory=lambda: ClassifiedIntent(Intent.UNKNOWN))
    meta: dict = field(default_factory=dict)
    run_caps: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    finding: dict | None = field(default=None)
    timeline: dict = field(default_factory=dict)
    correlations: list = field(default_factory=list)
    correlation_run: dict | None = field(default=None)
    groups: list = field(default_factory=list)
    group_run: dict | None = field(default=None)
    ml: dict = field(default_factory=dict)
    integrity: dict = field(default_factory=dict)
    processing: dict = field(default_factory=dict)
    review: dict = field(default_factory=dict)

    @property
    def intent(self) -> Intent:
        return self.classified.intent if self.classified else Intent.UNKNOWN


def _resolve_finding(db: Session, case: Case, ctx: AssistantContext, classified: ClassifiedIntent) -> None:
    finding_ref = classified.finding_ref
    if finding_ref:
        kind, row, events = retrieval.finding_detail(db, case, finding_ref)
        ctx.finding = {"kind": kind, "row": row, "events": events}
        return
    top = retrieval.top_finding(db, case)
    if top is None:
        return
    kind, row = top
    ctx.finding = {
        "kind": kind,
        "row": row,
        "events": analysis_service.finding_events(db, kind, row),
    }


def build_context(db: Session, case: Case, classified: ClassifiedIntent) -> AssistantContext:
    ctx = AssistantContext(case=case, classified=classified)
    ctx.meta = retrieval.case_meta(db, case)
    ctx.run_caps = retrieval.run_caps()

    intent = ctx.intent
    if not retrieval.case_has_evidence(db, case):
        return ctx

    ctx.evidence = retrieval.evidence_list(db, case, limit=100)

    if intent in (
        Intent.CASE_SUMMARY,
        Intent.TOP_FINDINGS,
        Intent.REVIEW_QUEUE,
        Intent.ML_EXPLANATION,
    ):
        ctx.findings = retrieval.findings(db, case)

    if intent in (Intent.FINDING_EXPLANATION, Intent.FINDING_TRACE, Intent.EVIDENCE_SUPPORT):
        _resolve_finding(db, case, ctx, classified)

    if intent == Intent.TIMELINE_CONTEXT:
        ctx.timeline = retrieval.timeline(db, case)

    if intent == Intent.CORRELATION_SUMMARY:
        correlation_uid = classified.correlation_ref
        if correlation_uid:
            row = retrieval.correlation_detail(db, case, correlation_uid)
            ctx.correlations = [row]
        else:
            rows, _total, run = retrieval.correlations(db, case)
            ctx.correlations = rows
            ctx.correlation_run = None if run is None else {"run_uid": run.run_uid}

    if intent == Intent.GROUP_SUMMARY:
        group_uid = classified.group_ref
        if group_uid:
            ctx.groups = [retrieval.group_detail(db, case, group_uid)]
        else:
            rows, _total, run = retrieval.groups(db, case)
            ctx.groups = rows
            ctx.group_run = None if run is None else {"run_uid": run.run_uid}

    if intent == Intent.ML_EXPLANATION:
        run = retrieval.analysis_latest(db, case)
        ml_findings = [row for kind, row in ctx.findings if kind == "ml"]
        stats = run.stats if run else {}
        ctx.ml = {
            "latest_run": None if run is None else dict(run.stats or {}),
            "ml_findings": ml_findings,
            "ml_count": len(ml_findings),
            "abstained": bool(stats.get("abstain_note")),
            "abstain_note": stats.get("abstain_note"),
            "abstain_reason": stats.get("abstain_reason"),
        }

    if intent == Intent.INTEGRITY_STATUS:
        ctx.integrity = retrieval.integrity(db, case)

    if intent == Intent.PROCESSING_STATUS:
        ctx.processing = retrieval.processing_summary(db, case)

    if intent == Intent.REVIEW_QUEUE:
        all_rows = retrieval.findings(db, case, limit=config.ASSISTANT_TOP_N * 3)
        counts = {}
        for _kind, row in all_rows:
            counts[row.status] = counts.get(row.status, 0) + 1
        ctx.review = {
            "new": [row for _kind, row in all_rows if row.status == FindingStatus.NEW.value],
            "status_counts": counts,
            "total": len(all_rows),
        }

    return ctx