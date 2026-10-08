"""Deterministic answer composition from the assistant context (Phase 5).

Every answer is a closed form, parameterized composition over the context —
no generative model, no free-form prose. When the retrieved rows are
insufficient, the answerer returns the fixed insufficient-evidence wording
(terminology) rather than inventing content. Confidence reflects whether the
answer is anchored in direct rows (HIGH), partial/fallback data (MEDIUM), or
nothing usable (LOW).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app import terminology
from app.assistant.context import AssistantContext
from app.assistant.intents import Intent


@dataclass
class AnswerParts:
    answer: str
    evidence: list[str] = field(default_factory=list)
    basis: list[str] = field(default_factory=list)
    confidence: str = "HIGH"
    sources: list[dict] = field(default_factory=list)


_INSUFFICIENT = terminology.ASSISTANT_INSUFFICIENT


def _source(entry_type: str, identifier: str, label: str = "") -> dict:
    return {"type": entry_type, "id": identifier, "label": label}


def _fmt_evidence(row) -> str:
    return (
        f"{row.evidence_id}: {row.original_filename} ({row.evidence_type}; "
        f"{row.record_count if row.record_count is not None else '?'} records)"
    )


def _finding_heading(kind: str, row) -> str:
    uid = row.finding_uid
    severity = getattr(row, "severity", "Medium")
    if kind == "ml":
        title = row.title or "ML anomaly finding"
        return f"ML finding {uid} (severity {severity}) - {title}"
    title = row.title or "rule finding"
    rule_id = getattr(row, "rule_id", "")
    return f"Finding {uid} (rule {rule_id}, severity {severity}) - {title}"


def _sort_findings(rows: list) -> list:
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
    return sorted(rows, key=lambda item: (order.get(item[1].severity, 9), item[1].finding_uid))


def _event_line(entry) -> str:
    when = ""
    if entry.timestamp is not None:
        when = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S") + " - "
    who = "@".join(p for p in (entry.user, entry.host) if p)
    tail = f" ({who})" if who else ""
    return f"{when}{entry.event_id} [{entry.source_type}/{entry.event_type}]{tail}"


# ---------------------------------------------------------------------------
# Intent builders
# ---------------------------------------------------------------------------

def _case_summary(ctx: AssistantContext) -> AnswerParts:
    meta = ctx.meta
    parts = [
        f"Case {meta['case_id']}: {meta['name']}.",
        f"Status: {meta['status']}; overall severity: {meta['severity']}.",
        (
            f"Contains {meta['evidence_count']} evidence file(s) and "
            f"{meta['finding_count']} finding(s) from the automated analysis."
        ),
    ]
    if meta["description"]:
        parts.append(f"Description: {meta['description']}")
    evidence = []
    sources: list[dict] = [_source("case", meta["case_id"], meta["name"])]
    for row in ctx.evidence[: ctx.run_caps.get("assistant_top_n", 10)]:
        evidence.append(_fmt_evidence(row))
        sources.append(_source("evidence", row.evidence_id, row.original_filename))
    return AnswerParts(
        answer="\n".join(parts),
        evidence=evidence,
        basis=[terminology.ANALYSIS_SCOPE_NOTE],
        confidence="HIGH" if ctx.evidence else "MEDIUM",
        sources=sources,
    )


def _top_findings(ctx: AssistantContext) -> AnswerParts:
    if not ctx.findings:
        return AnswerParts(
            answer=_INSUFFICIENT,
            evidence=[],
            basis=[terminology.ANALYSIS_SCOPE_NOTE],
            confidence="LOW",
            sources=[],
        )
    rows = _sort_findings(ctx.findings)[: ctx.run_caps.get("assistant_top_n", 10)]
    lines = ["The most important findings for this case are:"]
    sources: list[dict] = []
    for kind, row in rows:
        lines.append(f"- {_finding_heading(kind, row)}")
        sources.append(_source("finding", row.finding_uid, row.title))
    lines.append("")
    lines.append(terminology.FINDING_NOTE if hasattr(terminology, "FINDING_NOTE") else terminology.ASSISTANT_FINDING_NOTE)
    return AnswerParts(
        answer="\n".join(lines),
        evidence=[],
        basis=[terminology.ANALYSIS_SCOPE_NOTE, terminology.ASSISTANT_FINDING_NOTE],
        confidence="HIGH",
        sources=sources,
    )


def _finding_explanation(ctx: AssistantContext) -> AnswerParts:
    if ctx.finding is None:
        return AnswerParts(
            answer=_INSUFFICIENT,
            evidence=[],
            basis=[terminology.ANALYSIS_SCOPE_NOTE],
            confidence="LOW",
            sources=[],
        )
    kind, row, events = ctx.finding["kind"], ctx.finding["row"], ctx.finding["events"]
    lines = [_finding_heading(kind, row), ""]
    explanation = getattr(row, "explanation", "") or ""
    if kind == "ml":
        ml_expl = row.explanation if isinstance(row.explanation, dict) else {}
        if isinstance(ml_expl, dict) and ml_expl.get("summary"):
            explanation = ml_expl["summary"]
    if explanation:
        lines.append(f"Why: {explanation}")
    reasons = getattr(row, "reasons", None)
    if kind == "rule" and reasons:
        reasons_text = "; ".join(str(item) for item in reasons)
        lines.append(f"Reason(s): {reasons_text}")
    sources: list[dict] = [_source("finding", row.finding_uid, row.title)]
    evidence: list[str] = []
    for event in events:
        sources.append(_source("event", event.event_uid, event.event_type))
        evidence.append(f"{event.event_uid}: {event.source_type}/{event.event_type}")
    basis = [terminology.RULE_CONFIDENCE_NOTE] if kind == "rule" else [terminology.ANOMALY_DISCLAIMER]
    basis.append(terminology.ASSISTANT_FINDING_NOTE)
    return AnswerParts(
        answer="\n".join(lines),
        evidence=evidence,
        basis=basis,
        confidence="HIGH" if events or reasons else "MEDIUM",
        sources=sources,
    )


def _finding_trace(ctx: AssistantContext) -> AnswerParts:
    if ctx.finding is None:
        return AnswerParts(answer=_INSUFFICIENT, evidence=[], basis=[], confidence="LOW", sources=[])
    kind, row, events = ctx.finding["kind"], ctx.finding["row"], ctx.finding["events"]
    lines = [
        _finding_heading(kind, row),
        "",
        "Traceability chain: Finding -> Forensic Events -> Evidence File -> SHA-256.",
        "",
        "Triggered forensic events:",
    ]
    sources: list[dict] = [_source("finding", row.finding_uid, row.title)]
    evidence: list[str] = []
    if events:
        for event in events:
            lines.append(f"- {event.event_uid} ({event.source_type}/{event.event_type})")
            sources.append(_source("event", event.event_uid, event.event_type))
            evidence.append(f"{event.event_uid}: {event.source_type}/{event.event_type}")
    else:
        lines.append("- none recorded")
    evidence_ids = list(getattr(row, "evidence_ids", None) or [])
    if evidence_ids:
        lines.append("")
        lines.append("Source evidence:")
        for identifier in evidence_ids:
            lines.append(f"- {identifier}")
            sources.append(_source("evidence", identifier, identifier))
    # normalize with file labels where possible
    by_id = {ev.evidence_id: ev for ev in ctx.evidence}
    evidence = [f"{identifier}: {by_id[identifier].original_filename}" if identifier in by_id else identifier
                for identifier in evidence_ids]
    return AnswerParts(
        answer="\n".join(lines),
        evidence=evidence,
        basis=[terminology.TRACEABILITY_STEPS_AS_TEXT if hasattr(terminology, "TRACEABILITY_STEPS_AS_TEXT") else "Traceability: Finding, Reason, Forensic Event, Raw Record, Evidence File, Recorded SHA-256."],
        confidence="HIGH" if events else "MEDIUM",
        sources=sources,
    )


def _evidence_support(ctx: AssistantContext) -> AnswerParts:
    if ctx.finding is None:
        return AnswerParts(answer=_INSUFFICIENT, evidence=[], basis=[], confidence="LOW", sources=[])
    kind, row, events = ctx.finding["kind"], ctx.finding["row"], ctx.finding["events"]
    evidence_ids = list(getattr(row, "evidence_ids", None) or [])
    by_id = {ev.evidence_id: ev for ev in ctx.evidence}
    lines = [f"Evidence supporting {_finding_heading(kind, row)}:", ""]
    sources: list[dict] = [_source("finding", row.finding_uid, row.title)]
    evidence: list[str] = []
    if evidence_ids:
        for identifier in evidence_ids:
            row_ev = by_id.get(identifier)
            if row_ev is not None:
                lines.append(f"- {_fmt_evidence(row_ev)}")
                evidence.append(_fmt_evidence(row_ev))
                sources.append(_source("evidence", identifier, row_ev.original_filename))
            else:
                lines.append(f"- {identifier}")
                evidence.append(identifier)
    else:
        lines.append("- none recorded on the finding")
    if events:
        lines.append("")
        lines.append("Triggered events:")
        for event in events:
            lines.append(f"- {event.event_uid}")
            sources.append(_source("event", event.event_uid, event.event_type))
    return AnswerParts(
        answer="\n".join(lines),
        evidence=evidence,
        basis=[terminology.INTEGRITY_DISCLAIMER],
        confidence="HIGH" if evidence_ids else "MEDIUM",
        sources=sources,
    )


def _timeline_context(ctx: AssistantContext) -> AnswerParts:
    timeline = ctx.timeline
    entries = list(timeline.get("entries", []) or [])
    note = timeline.get("note")
    if not entries:
        return AnswerParts(
            answer=note or _INSUFFICIENT,
            evidence=[],
            basis=[terminology.TIMELINE_DISCLAIMER],
            confidence="LOW",
            sources=[],
        )
    time_ref = ctx.classified.time_ref if ctx.classified else None
    event_ref = ctx.classified.event_ref if ctx.classified else None
    selected = _select_timeline(entries, time_ref=time_ref, event_ref=event_ref, cap=10)
    lines = [terminology.TIMELINE_LABEL + ":", ""]
    sources: list[dict] = []
    for entry in selected:
        lines.append("- " + _event_line(entry))
        if getattr(entry, "finding_ids", None):
            for fid in entry.finding_ids[:3]:
                sources.append(_source("finding", fid, fid))
        if getattr(entry, "correlation_ids", None):
            for cid in entry.correlation_ids[:3]:
                sources.append(_source("correlation", cid, cid))
        sources.append(_source("event", entry.event_id, entry.event_type))
        sources.append(_source("evidence", entry.evidence_id, entry.evidence_id))
    if timeline.get("truncated"):
        lines.append("")
        lines.append(f"Showing the first {len(selected)} entries (TIMELINE_MAX_ENTRIES cap).")
    return AnswerParts(
        answer="\n".join(lines),
        evidence=[],
        basis=[terminology.TIMELINE_DISCLAIMER] + ([note] if note else []),
        confidence="HIGH" if selected else "LOW",
        sources=sources,
    )


def _select_timeline(entries: list, *, time_ref: str | None, event_ref: str | None, cap: int) -> list:
    if event_ref:
        for index, entry in enumerate(entries):
            if entry.event_id == event_ref:
                return entries[max(0, index - 2): index + 3][:cap]
    if time_ref:
        try:
            hour, minute = (int(p) for p in time_ref.split(":"))
        except ValueError:
            return entries[:cap]
        matched = [e for e in entries if e.timestamp is not None
                   and e.timestamp.hour == hour and e.timestamp.minute == minute]
        if matched:
            return matched[:cap]
    flagged = [
        e for e in entries
        if e.is_anomalous or getattr(e, "finding_ids", None) or getattr(e, "correlation_ids", None)
    ] or entries
    return flagged[:cap]


def _correlation_summary(ctx: AssistantContext) -> AnswerParts:
    if not ctx.correlations:
        return AnswerParts(
            answer="No correlations have been produced yet. Run the correlation stage over the processed evidence.",
            evidence=[],
            basis=[terminology.CORRELATION_DISCLAIMER],
            confidence="LOW",
            sources=[],
        )
    lines = ["Detected correlations (reason-tagged links between events):", ""]
    sources: list[dict] = []
    users, hosts, ips = set(), set(), set()
    for index, corr in enumerate(ctx.correlations[: ctx.run_caps.get("assistant_top_n", 10)]):
        band = _confidence_band(corr.confidence)
        reason = (corr.reason or "").strip()
        shared = corr.shared_entities or {}
        for key in ("user", "host", "source_ip"):
            value = shared.get(key)
            if value:
                (users if key == "user" else hosts if key == "host" else ips).add(str(value))
        a_uid = corr.event_a.event_uid if corr.event_a else "?"
        b_uid = corr.event_b.event_uid if corr.event_b else "?"
        lines.append(f"- {corr.correlation_uid}: {a_uid} <-> {b_uid} ({corr.correlation_type}, band {band})")
        if reason:
            lines.append(f"  reason: {reason}")
        if shared:
            lines.append(f"  shared: {', '.join(f'{k}={v}' for k, v in sorted(shared.items()))}")
        sources.append(_source("correlation", corr.correlation_uid, corr.reason))
        if corr.event_a:
            sources.append(_source("event", corr.event_a.event_uid, corr.event_a.event_type))
        if corr.event_b:
            sources.append(_source("event", corr.event_b.event_uid, corr.event_b.event_type))
    if ctx.correlation_run and ctx.correlation_run.get("run_uid"):
        lines.append("")
        lines.append(f"Correlation run: {ctx.correlation_run['run_uid']}.")
    else:
        anchored = bool(ctx.classified and ctx.classified.correlation_ref)
        if not anchored and (users or hosts or ips):
            lines.append("")
            observed = []
            if users:
                observed.append("users: " + ", ".join(sorted(users)))
            if hosts:
                observed.append("hosts: " + ", ".join(sorted(hosts)))
            if ips:
                observed.append("source IPs: " + ", ".join(sorted(ips)))
            lines.append("Distinct entities involved in correlated activity - " + "; ".join(observed) + ".")
    return AnswerParts(
        answer="\n".join(lines),
        evidence=[],
        basis=[terminology.CORRELATION_DISCLAIMER],
        confidence="HIGH",
        sources=sources,
    )


def _confidence_band(value: float) -> str:
    if value >= 0.85:
        return "High"
    if value >= 0.65:
        return "Medium"
    return "Low"


def _group_summary(ctx: AssistantContext) -> AnswerParts:
    if not ctx.groups:
        return AnswerParts(
            answer="No investigation groups have been produced yet. Run the correlation stage over the processed evidence.",
            evidence=[],
            basis=[terminology.CORRELATION_GROUP_NOTE],
            confidence="LOW",
            sources=[],
        )
    lines = ["Investigation activity groups (real events only):", ""]
    sources: list[dict] = []
    for group in ctx.groups[: ctx.run_caps.get("assistant_top_n", 10)]:
        lines.append(
            f"- {group.group_uid}: {group.title or ''} ({group.kind}, severity {group.severity})"
        )
        if group.explanation:
            lines.append(f"  {group.explanation}")
        lines.append(
            f"  members: {len(group.member_event_ids or [])} events, "
            f"{len(group.correlation_uids or [])} correlations"
        )
        sources.append(_source("group", group.group_uid, group.title))
        for cid in (group.correlation_uids or [])[:5]:
            sources.append(_source("correlation", cid, cid))
    if ctx.group_run and ctx.group_run.get("run_uid"):
        lines.append("")
        lines.append(f"Correlation run: {ctx.group_run['run_uid']}.")
    return AnswerParts(
        answer="\n".join(lines),
        evidence=[],
        basis=[terminology.CORRELATION_GROUP_NOTE, terminology.CORRELATION_DISCLAIMER],
        confidence="HIGH",
        sources=sources,
    )


def _ml_explanation(ctx: AssistantContext) -> AnswerParts:
    ml = ctx.ml
    count = ml.get("ml_count", 0)
    lines = []
    if not ml.get("latest_run"):
        lines.append("No automated analysis has been run yet for this case.")
        return AnswerParts(
            answer="\n".join(lines),
            evidence=[],
            basis=[terminology.ANOMALY_DISCLAIMER],
            confidence="LOW",
            sources=[],
        )
    run_stats = ml.get("latest_run") or {}
    lines.append(
        f"The latest automated analysis produced {run_stats.get('rule_findings', 0)} rule "
        f"finding(s) and {count} ML finding(s)."
    )
    if ml.get("abstained"):
        lines.append("")
        lines.append("The ML anomaly detector abstained for this run - no ML finding was created.")
        if ml.get("abstain_reason"):
            lines.append(f"Reason: {ml['abstain_reason']}.")
        lines.append(terminology.ML_ABSTAIN_NOTE if hasattr(terminology, "ML_ABSTAIN_NOTE") else "Too few event windows for a meaningful ML comparison.")
    elif count:
        lines.append("")
        lines.append(
            "ML detection compares each event window against the case's typical pattern; "
            "a window that deviates beyond the detection threshold is flagged. "
            "The anomaly score is a normalized statistical deviation - it is not proof "
            "of malicious activity and requires investigator review."
        )
        for idx, row in enumerate((ml.get("ml_findings") or [])[:10], start=1):
            score = getattr(row, "score", None)
            threshold = getattr(row, "threshold", None)
            score_txt = f"{score:.3f}" if isinstance(score, float) else str(score)
            threshold_txt = f"{threshold:.3f}" if isinstance(threshold, float) else str(threshold)
            lines.append(f"{idx}. {row.finding_uid} - {row.title or ''} (score {score_txt}, threshold {threshold_txt})")
    sources: list[dict] = []
    for row in (ml.get("ml_findings") or [])[:10]:
        sources.append(_source("finding", row.finding_uid, row.title))
    return AnswerParts(
        answer="\n".join(lines),
        evidence=[],
        basis=[terminology.ANOMALY_DISCLAIMER, terminology.ANOMALY_SCORE_DESCRIPTION],
        confidence="HIGH" if count else "MEDIUM",
        sources=sources,
    )


def _review_queue(ctx: AssistantContext) -> AnswerParts:
    new_findings = ctx.review.get("new") or []
    counts = ctx.review.get("status_counts") or {}
    if not ctx.review.get("total"):
        return AnswerParts(
            answer="No findings have been produced yet, so nothing requires review.",
            evidence=[],
            basis=[terminology.ASSISTANT_FINDING_NOTE],
            confidence="LOW",
            sources=[],
        )
    lines = [f"{len(new_findings)} finding(s) still need investigator review:", ""]
    sources: list[dict] = []
    for row in new_findings[: ctx.run_caps.get("assistant_top_n", 10)]:
        severity = getattr(row, "severity", "Medium")
        lines.append(f"- {row.finding_uid} ({severity}) - {row.title or ''} [{row.status}]")
        sources.append(_source("finding", row.finding_uid, row.title))
    if counts:
        labels = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        lines.append("")
        lines.append(f"Review status distribution: {labels}.")
    return AnswerParts(
        answer="\n".join(lines),
        evidence=[],
        basis=[terminology.ASSISTANT_FINDING_NOTE],
        confidence="HIGH" if new_findings else "MEDIUM",
        sources=sources,
    )


def _integrity_status(ctx: AssistantContext) -> AnswerParts:
    integrity = ctx.integrity
    verified = integrity.get("verified") or []
    mismatch = integrity.get("mismatch") or []
    pending = integrity.get("pending") or []
    if not ctx.evidence:
        return AnswerParts(answer=_INSUFFICIENT, evidence=[], basis=[], confidence="LOW", sources=[])
    lines = [f"Evidence integrity verification ({terminology.HASH_ALGORITHM}):", ""]
    lines.append(f"- verified: {len(verified)} file(s)")
    lines.append(f"- pending verification: {len(pending)} file(s)")
    lines.append(f"- hashes that did not match: {len(mismatch)} file(s)")
    sources: list[dict] = []
    for row, check in verified[:10]:
        lines.append(f"  verified {row.evidence_id}: {row.original_filename}")
        sources.append(_source("evidence", row.evidence_id, row.original_filename))
    for identifier in [f"{row.evidence_id} ({row.original_filename})" for row, _check in mismatch[:10]]:
        lines.append(f"  MISMATCH {identifier}")
    for row in pending[:10]:
        lines.append(f"  pending {row.evidence_id}: {row.original_filename}")
    return AnswerParts(
        answer="\n".join(lines),
        evidence=[],
        basis=[terminology.INTEGRITY_DISCLAIMER],
        confidence="HIGH" if verified or mismatch else "MEDIUM",
        sources=sources,
    )


def _processing_status(ctx: AssistantContext) -> AnswerParts:
    processing = ctx.processing
    runs = processing.get("runs") or []
    evidence_rows = processing.get("evidence") or []
    if not runs and not evidence_rows:
        return AnswerParts(answer=_INSUFFICIENT, evidence=[], basis=[], confidence="LOW", sources=[])
    by_status = processing.get("by_status") or {}
    status_text = ", ".join(f"{key}={value}" for key, value in sorted(by_status.items()))
    lines = [
        f"Processing runs: {len(runs)} ({status_text}); "
        f"{processing.get('total_parsed', 0)} records parsed, "
        f"{processing.get('total_normalized', 0)} normalized, "
        f"{processing.get('total_rejected', 0)} rejected, "
        f"{processing.get('total_duplicates', 0)} duplicates detected."
    ]
    if not runs:
        lines.append("")
        lines.append("No evidence has been processed yet for this case.")
        return AnswerParts(
            answer="\n".join(lines),
            evidence=[],
            basis=[],
            confidence="MEDIUM",
            sources=[],
        )
    lines.append("")
    lines.append("Per evidence file:")
    sources: list[dict] = []
    for row in evidence_rows[:10]:
        lines.append(
            f"- {_fmt_evidence(row)} processed rows: ok={row.parse_ok}, rejected={row.parse_rejected}"
        )
        sources.append(_source("evidence", row.evidence_id, row.original_filename))
    return AnswerParts(
        answer="\n".join(lines),
        evidence=[],
        basis=[],
        confidence="HIGH",
        sources=sources,
    )


def _capabilities(ctx: AssistantContext) -> AnswerParts:
    return AnswerParts(
        answer=terminology.ASSISTANT_CAPABILITIES,
        evidence=[],
        basis=[terminology.ASSISTANT_FOOTER],
        confidence="HIGH",
        sources=[],
    )


def _unknown(ctx: AssistantContext) -> AnswerParts:
    supported = ", ".join(intent.value for intent in Intent if intent not in (Intent.UNKNOWN, Intent.CAPABILITIES))
    return AnswerParts(
        answer=terminology.ASSISTANT_UNSUPPORTED,
        evidence=[],
        basis=[f"Supported intents: {supported}."],
        confidence="LOW",
        sources=[],
    )


_BUILDERS = {
    Intent.CASE_SUMMARY: _case_summary,
    Intent.TOP_FINDINGS: _top_findings,
    Intent.FINDING_EXPLANATION: _finding_explanation,
    Intent.FINDING_TRACE: _finding_trace,
    Intent.EVIDENCE_SUPPORT: _evidence_support,
    Intent.TIMELINE_CONTEXT: _timeline_context,
    Intent.CORRELATION_SUMMARY: _correlation_summary,
    Intent.GROUP_SUMMARY: _group_summary,
    Intent.ML_EXPLANATION: _ml_explanation,
    Intent.REVIEW_QUEUE: _review_queue,
    Intent.INTEGRITY_STATUS: _integrity_status,
    Intent.PROCESSING_STATUS: _processing_status,
    Intent.CAPABILITIES: _capabilities,
    Intent.UNKNOWN: _unknown,
}


def answer(ctx: AssistantContext, *, empty_case: bool = False) -> AnswerParts:
    """Compose the deterministic answer for the context."""
    if empty_case and ctx.intent not in (Intent.CAPABILITIES, Intent.UNKNOWN):
        return AnswerParts(
            answer=terminology.ASSISTANT_EMPTY_CASE,
            evidence=[],
            basis=[terminology.ASSISTANT_FOOTER],
            confidence="LOW",
            sources=[],
        )
    builder = _BUILDERS.get(ctx.intent, _unknown)
    parts = builder(ctx)
    if not parts.basis:
        parts.basis = [terminology.ASSISTANT_FOOTER]
    return parts