"""Canonical terminology constants for FORENSIGHT AI (Architecture §1).

Every user-facing string that carries a claim about what the system does lives
here so that wording stays consistent across UI, API documentation, and report
output. A banned-term guard test (tests/test_terminology.py) asserts that no
banned phrase appears in the values of this module, in README.md, or in
ARCHITECTURE.md.

Scope of this module (Phase 0): wording only. No behaviour.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

PRODUCT_NAME = "FORENSIGHT AI"
PRODUCT_SUBTITLE = "AI-Powered Digital Forensics Investigation Framework"

PRODUCT_CONCEPT = (
    "FORENSIGHT AI is an AI-assisted digital forensic investigation prototype "
    "that preserves uploaded evidence, verifies file integrity through SHA-256 "
    "hashing, converts heterogeneous logs into normalized forensic events, "
    "detects suspicious patterns using transparent rules and explainable machine "
    "learning, correlates evidence across sources, reconstructs an "
    "investigator-reviewable timeline, and maintains traceability from findings "
    "back to source evidence, and produces immutable, evidence-backed "
    "investigation reports."
)

# ---------------------------------------------------------------------------
# Standing disclaimers (shown in UI, report cover, and API description)
# ---------------------------------------------------------------------------

PROTOTYPE_DISCLAIMER = (
    "Research/hackathon prototype - not a certified forensic or "
    "legal-admissibility system. All findings require investigator validation."
)

INTEGRITY_DISCLAIMER = (
    "Integrity verification confirms the evidence file has not changed since "
    "its hash was recorded. It does not establish who created or collected "
    "the evidence."
)

ANOMALY_DISCLAIMER = (
    "The anomaly score indicates statistical deviation from this case's typical "
    "event patterns. It is not proof of malicious activity and requires "
    "investigator review."
)

SCORE_FOOTNOTE = "Requires investigator validation."

SYNTHETIC_DATA_LABEL = "Trained and evaluated on synthetic demonstration data."

CORRELATION_DISCLAIMER = (
    "Correlation indicates co-occurrence and shared context, not causation. "
    "Requires investigator validation."
)

ASSISTANT_FOOTER = (
    "Answers are constructed only from processed case evidence. "
    "No generative model is enabled."
)

FUSION_DISCLAIMER = (
    "The Composite Suspicion Score is an uncalibrated heuristic composite - "
    "not a probability and not proof of malicious activity. "
    "Requires investigator validation."
)

# ---------------------------------------------------------------------------
# Automated analysis (Phase 3)
# ---------------------------------------------------------------------------

ANALYSIS_RUN_LABEL = "Automated Analysis Run"
ANALYSIS_SCOPE_NOTE = (
    "Analysis is limited to the normalized forensic events of this case. "
    "Rule detections and ML anomaly scores are statistical observations that "
    "require investigator review."
)
ANALYSIS_NO_EVENTS = "No normalized forensic events available for analysis."
ML_ABSTAIN_NOTE = (
    "Too few event windows for a meaningful ML comparison - anomaly detection "
    "abstained and no ML finding was created for this run."
)
ANOMALY_SCORE_DESCRIPTION = (
    "Normalized to [0, 1] over this case's event windows; a higher value "
    "indicates greater statistical deviation from the case's typical pattern."
)
RULE_CONFIDENCE_NOTE = (
    "Rule confidence is a fixed deterministic indicator weight, not a probability."
)

# ---------------------------------------------------------------------------
# Integrity verification labels
# ---------------------------------------------------------------------------

INTEGRITY_VERIFIED = "INTEGRITY VERIFIED"
INTEGRITY_MISMATCH = "INTEGRITY MISMATCH"
INTEGRITY_TEST_LABEL = "Controlled Integrity Test - Demonstration Copy"
HASH_ALGORITHM = "SHA-256"

# ---------------------------------------------------------------------------
# Scoring labels (score is always presented together with its threshold)
# ---------------------------------------------------------------------------

SCORE_LABEL = "Anomaly score"
THRESHOLD_LABEL = "Detection threshold"
FUSION_LABEL = "Composite Suspicion Score"
RULE_COMPONENT_LABEL = "Rule evidence"
ANOMALY_COMPONENT_LABEL = "Anomaly score"
CORRELATION_COMPONENT_LABEL = "Correlation support"

# Finding language: never assert certainty.
FINDING_TERMS = (
    "Potentially suspicious",
    "Anomalous",
    "Requires investigator review",
)

# ---------------------------------------------------------------------------
# Timeline / traceability
# ---------------------------------------------------------------------------

TIMELINE_LABEL = "Reconstructed Investigation Timeline"
TIMELINE_DISCLAIMER = (
    "A reconstruction derived from the evidence available in this case. "
    "It is not an established sequence of events."
)

# ---------------------------------------------------------------------------
# Correlation / activity groups (Phase 4)
# ---------------------------------------------------------------------------

CORRELATION_RUN_LABEL = "Correlation Run"
CORRELATION_NO_EVENTS = (
    "No normalized forensic events available for correlation."
)
CORRELATION_GROUP_NOTE = (
    "Activity groups are built from reason-tagged correlations between real "
    "events of this case - no inferred or merged entities."
)

TRACEABILITY_STEPS = (
    "Finding",
    "Reason",
    "Forensic Event",
    "Raw Record",
    "Evidence File",
    "Recorded SHA-256",
)

# ---------------------------------------------------------------------------
# Assistant (Phase 5) — deterministic answer wording
# ---------------------------------------------------------------------------

INSUFFICIENT_EVIDENCE = "Insufficient evidence in the current case."
ASSISTANT_INSUFFICIENT = (
    "I could not find sufficient evidence in this case to answer that question."
)
ASSISTANT_UNSUPPORTED = (
    "This question is outside the currently supported investigation assistant "
    "capabilities."
)
ASSISTANT_EMPTY_CASE = (
    "No forensic evidence is currently available for this case."
)
ASSISTANT_CAPABILITIES = (
    "I can currently answer questions about:\n"
    "• case summary\n"
    "• suspicious findings\n"
    "• finding explanations\n"
    "• evidence support\n"
    "• timeline activity\n"
    "• correlations\n"
    "• investigation groups\n"
    "• ML anomaly reasoning\n"
    "• evidence integrity\n"
    "• processing status\n"
    "• investigator review status"
)
ASSISTANT_FINDING_NOTE = (
    "Findings are evidence-backed analytical results produced by the "
    "automated analysis; they are not automatic legal conclusions and always "
    "require investigator review."
)
PLANNED_LABEL = "Prototype / Planned"
DEMO_LABEL = "SYNTHETIC / DEMONSTRATION DATA"

# ---------------------------------------------------------------------------
# Dashboard (Phase 7) — read-only scenario statistics
# ---------------------------------------------------------------------------

DASHBOARD_LABEL = "Scenario Statistics"
DASHBOARD_NOTE = (
    "Dashboard figures are read-only aggregates of the data already persisted "
    "by the analysis phases. They are counts and sums of stored rows, not new "
    "analysis, and require investigator review."
)
DASHBOARD_KPI_LABEL = "Per-case overview"

# ---------------------------------------------------------------------------
# Investigation workspace (Phase 8) — read-only analyst console
# ---------------------------------------------------------------------------

WORKSPACE_LABEL = "Investigation Workspace"
WORKSPACE_NOTE = (
    "Workspace figures are read-only aggregates of the data already persisted "
    "by the analysis phases and the assistant/report history of this case. "
    "They are counts and re-shaped views of stored rows, not new analysis, "
    "and require investigator review."
)
WORKSPACE_DISCLAIMER = (
    "Read-only working console: every figure is drawn from data already "
    "persisted for this case by Phases 1–7. No analysis is re-run and no "
    "write happens while viewing the workspace."
)

# Processing rollup labels (persisted processing-runs only, never re-run).
PROCESSING_NOT_PROCESSED = "Not processed"
PROCESSING_IN_PROGRESS = "In progress"
PROCESSING_PARTIAL = "Partial"
PROCESSING_FAILED = "Failed"
PROCESSING_COMPLETED = "Completed"

# Evidence integrity rollup labels (latest check per evidence item).
INTEGRITY_UNVERIFIED = "Unverified"
INTEGRITY_PARTIAL = "Partially verified"
INTEGRITY_LATEST_VERIFIED = "Verified"
INTEGRITY_LATEST_MISMATCH = "Mismatch"

# ---------------------------------------------------------------------------
# Forensic reports (Phase 6) — evidence-backed presentation layer
# ---------------------------------------------------------------------------

REPORT_TITLE = "Digital Forensic Investigation Report"
REPORT_SCHEMA = "FORENSIGHT_REPORT_V1"
REPORT_VERSION = "1.0"
REPORT_STATUS = "Generated"
REPORT_NO_ANALYSIS = "No analysis result is currently available."
REPORT_TRACE_UNAVAILABLE = "Trace unavailable for this finding."
REPORT_SYSTEM_ENTRY = "system-generated finding"
REPORT_REVIEW_ENTRY = "investigator-entered assessment"

REPORT_INTEGRITY_VERIFIED_EXPLAIN = (
    "The current evidence bytes matched the recorded SHA-256 reference "
    "during verification."
)
REPORT_INTEGRITY_MISMATCH_EXPLAIN = (
    "The current evidence bytes did not match the recorded SHA-256 reference "
    "during verification."
)
REPORT_INTEGRITY_NOTE = (
    "SHA-256 matching confirms byte-for-byte equivalence with the recorded "
    "reference only; it does not establish who created or collected the evidence."
)
REPORT_INTEGRITY_NOT_VERIFIED = "NOT VERIFIED"
REPORT_INTEGRITY_NO_CHECK = "NO CHECK AVAILABLE"

REPORT_CONCLUSION_NO_FINDINGS = (
    "No suspicious findings were recorded by the configured forensic analysis pipeline."
)
REPORT_CONCLUSION_NO_CORRELATION = (
    "The investigation identified suspicious activity in the analyzed evidence, "
    "but no cross-source correlations were recorded."
)
REPORT_CONCLUSION_WITH_CORRELATION = (
    "The investigation identified suspicious activity with supporting "
    "cross-source relationships in the analyzed evidence."
)
REPORT_CONCLUSION_INSUFFICIENT = (
    "The available evidence does not support a definitive conclusion from the "
    "current prototype analysis."
)
REPORT_HIGH_SEVERITY_NOTE = (
    "High-severity findings require investigator review and contextual "
    "interpretation."
)

REPORT_LIMIT_PROTOTYPE = (
    "FORENSIGHT AI is a research/hackathon prototype, not a certified forensic "
    "or legal-admissibility system."
)
REPORT_LIMIT_INTEGRITY = (
    "SHA-256 verification only proves the current bytes match the recorded "
    "reference; it does not authenticate origin, collection, or custody."
)
REPORT_LIMIT_ML = (
    "ML anomaly scores are statistical deviations from this case's typical "
    "event pattern; they are not proof of malicious activity."
)
REPORT_LIMIT_SCORES = (
    "Composite Suspicion Scores are uncalibrated heuristic composites, not "
    "probabilities."
)
REPORT_LIMIT_REVIEW = (
    "All findings require investigator review and validation before any action "
    "is taken."
)
REPORT_LIMIT_DATA = (
    "This report reflects only the evidence ingested and processed in this "
    "case up to the generation time."
)

REPORT_ML_STATEMENT = (
    "The ML component identified statistically unusual activity relative to "
    "the configured detection strategy; anomaly scores are not proof of "
    "malicious activity."
)

# ---------------------------------------------------------------------------
# Banned terms: phrases that must never appear in product wording.
# NOTE: this tuple itself is excluded from the self-check; only the values of
# the other constants, README.md and ARCHITECTURE.md are scanned.
# ---------------------------------------------------------------------------

BANNED_TERMS: tuple[str, ...] = (
    "court-explainable",
    "legally usable",
    "legally authenticated",
    "legally proven",
    "legally admissible",
    "proves criminal activity",
    "proof of criminal activity",
    "proves cybercrime",
    "proves ransomware",
    "evidence authentication",
    "authenticated evidence",
    "authentication of evidence",
    "provenance verified",
    "certified forensic tool",
    "certified forensic system",
    "autonomous forensic investigator",
    "fully autonomous forensic",
    "replaces forensic experts",
    "replacement for forensic experts",
)
