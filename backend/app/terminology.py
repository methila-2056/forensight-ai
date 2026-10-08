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
    "back to source evidence."
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
