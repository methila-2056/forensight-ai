"""Controlled assistant intent catalog and deterministic classifier (Phase 5).

Intents are a closed set; the classifier is keyword/pattern based and returns
the *first* matching rule. Anchors (finding/event/correlation/group ids and
``HH:MM`` timestamps) are extracted and passed on so retrieval can scope to
the referenced object — they never bypass the case scoping enforced by the
retrieval layer.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field


class Intent(str, enum.Enum):
    """Supported assistant question intents (and two control intents)."""

    CASE_SUMMARY = "CASE_SUMMARY"
    TOP_FINDINGS = "TOP_FINDINGS"
    FINDING_EXPLANATION = "FINDING_EXPLANATION"
    FINDING_TRACE = "FINDING_TRACE"
    EVIDENCE_SUPPORT = "EVIDENCE_SUPPORT"
    TIMELINE_CONTEXT = "TIMELINE_CONTEXT"
    CORRELATION_SUMMARY = "CORRELATION_SUMMARY"
    GROUP_SUMMARY = "GROUP_SUMMARY"
    ML_EXPLANATION = "ML_EXPLANATION"
    REVIEW_QUEUE = "REVIEW_QUEUE"
    INTEGRITY_STATUS = "INTEGRITY_STATUS"
    PROCESSING_STATUS = "PROCESSING_STATUS"
    CAPABILITIES = "CAPABILITIES"
    UNKNOWN = "UNKNOWN"


@dataclass
class ClassifiedIntent:
    intent: Intent
    # Recognized identifiers by type (finding/event/correlation/group) and an
    # optional wall-clock anchor "HH:MM".
    references: dict[str, str] = field(default_factory=dict)

    @property
    def finding_ref(self) -> str | None:
        return self.references.get("finding")

    @property
    def event_ref(self) -> str | None:
        return self.references.get("event")

    @property
    def correlation_ref(self) -> str | None:
        return self.references.get("correlation")

    @property
    def group_ref(self) -> str | None:
        return self.references.get("group")

    @property
    def time_ref(self) -> str | None:
        return self.references.get("time")


_FINDING_ID = re.compile(r"\b(RFND-\d{6}|MFND-\d{6})\b")
_EVENT_ID = re.compile(r"\b(EVT-\d{5,7})\b")
_CORRELATION_ID = re.compile(r"\b(COR-\d{6})\b")
_GROUP_ID = re.compile(r"\b(GRP-\d{6})\b")
_TIME = re.compile(r"\b(\d{1,2}:\d{2})\b")


def _extract_references(text: str) -> dict[str, str]:
    """Collect recognized identifiers (case-insensitive) from the question text."""
    references: dict[str, str] = {}
    for pattern, key in (
        (_FINDING_ID, "finding"),
        (_EVENT_ID, "event"),
        (_CORRELATION_ID, "correlation"),
        (_GROUP_ID, "group"),
    ):
        match = re.compile(pattern.pattern, re.IGNORECASE).search(text)
        if match:
            references[key] = match.group(1).upper()
    time = _TIME.search(text)
    if time and "time" not in references:
        references["time"] = time.group(1)
    return references


def _has(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def classify(question: str) -> ClassifiedIntent:
    """Map a free-text question to a controlled intent (deterministic)."""
    text = " ".join((question or "").lower().split())
    if not text:
        return ClassifiedIntent(Intent.UNKNOWN)

    references = _extract_references(text)
    finding = references.get("finding")
    event = references.get("event")

    # --- reference-anchored intents ----------------------------------------
    if event:
        return ClassifiedIntent(Intent.TIMELINE_CONTEXT, references)
    if finding:
        if _has(text, "trace", "where does", "come from", "provenance", "backing"):
            return ClassifiedIntent(Intent.FINDING_TRACE, references)
        if _has(text, "evidence", "support"):
            return ClassifiedIntent(Intent.EVIDENCE_SUPPORT, references)
        if _has(
            text,
            "why",
            "explain",
            "reason",
            "rule",
            "model",
            "suspicious",
            "flagged",
            "trigger",
        ):
            return ClassifiedIntent(Intent.FINDING_EXPLANATION, references)
        return ClassifiedIntent(Intent.FINDING_EXPLANATION, references)

    if "why was" in text and "finding" in text:
        return ClassifiedIntent(Intent.FINDING_EXPLANATION, references)
    if _has(text, "evidence") and _has(text, "support"):
        return ClassifiedIntent(Intent.EVIDENCE_SUPPORT, references)

    # --- keyword intents (priority order) -----------------------------------
    if _has(text, "need review", "needs review", "pending review", "to review",
            "unreviewed", "unresolved", "outstanding", "still new", "need to be reviewed",
            "need investigator review", "needs investigator review", "must be reviewed",
            "require review", "requires review", "awaiting review"):
        return ClassifiedIntent(Intent.REVIEW_QUEUE, references)

    if _has(text, "abstain", "abstention", "machine learning", "model flag",
            "anomaly", "statistical", "did the ml") or re.search(r"\bml\b", text):
        return ClassifiedIntent(Intent.ML_EXPLANATION, references)

    if _has(text, "integrity", "sha-256", "sha256", "sha 256", "hash", "unchanged",
            "not modified", "tamper", "verified", "verification", " verify"):
        return ClassifiedIntent(Intent.INTEGRITY_STATUS, references)

    if _has(text, "processing", "parse", "normaliz", "accepted records", "rejected",
            "duplicate", "ingest", "run status", "end-to-end"):
        return ClassifiedIntent(Intent.PROCESSING_STATUS, references)

    if _has(
        text,
        "correlat",
        "related activity",
        "related events",
        "same host",
        "same user",
        "same source ip",
        "involved the same",
        "link to each other",
        "related to each other",
        "which user",
        "what user",
        "which host",
        "which source ip",
        "account was involved",
        "who was involved",
        "what was involved",
    ) or (references.get("correlation") is not None):
        return ClassifiedIntent(Intent.CORRELATION_SUMMARY, references)

    if _has(text, "activity group", "groups", "cluster", "grouping"):
        return ClassifiedIntent(Intent.GROUP_SUMMARY, references)

    if (
        _has(text, "timeline", "what happened", "what occurred", "around ", "before the",
             "precede", "followed", "sequence of", "context around")
        or references.get("time") is not None
    ):
        return ClassifiedIntent(Intent.TIMELINE_CONTEXT, references)

    if _has(
        text,
        "suspicious",
        "finding",
        "detected",
        "alert",
        "threat",
        "important",
        "abnormal",
        "anomalous activity",
        "what was flagged",
    ):
        return ClassifiedIntent(Intent.TOP_FINDINGS, references)

    if _has(text, "summary", "overview", "about this case", "describe", "describe the case",
            "status of the case", "what is this case", "case status"):
        return ClassifiedIntent(Intent.CASE_SUMMARY, references)

    if _has(text, "what can you", "what do you do", "how can you help", "capabilit",
            "what questions", "help me"):
        return ClassifiedIntent(Intent.CAPABILITIES, references)

    return ClassifiedIntent(Intent.UNKNOWN, references)