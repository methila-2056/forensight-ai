/**
 * Canonical terminology constants — frontend mirror of backend/app/terminology.py.
 * Keep both files in sync. Wording here is the only approved product language.
 */

export const PRODUCT_NAME = "FORENSIGHT AI";

export const PRODUCT_SUBTITLE = "AI-Powered Digital Forensics Investigation Framework";

export const PRODUCT_CONCEPT =
  "FORENSIGHT AI is an AI-assisted digital forensic investigation prototype " +
  "that preserves uploaded evidence, verifies file integrity through SHA-256 " +
  "hashing, converts heterogeneous logs into normalized forensic events, " +
  "detects suspicious patterns using transparent rules and explainable machine " +
  "learning, correlates evidence across sources, reconstructs an " +
  "investigator-reviewable timeline, and maintains traceability from findings " +
  "back to source evidence, and produces immutable, evidence-backed " +
  "investigation reports.";

export const PROTOTYPE_DISCLAIMER =
  "Research/hackathon prototype - not a certified forensic or legal-admissibility system. " +
  "All findings require investigator validation.";

export const INTEGRITY_DISCLAIMER =
  "Integrity verification confirms the evidence file has not changed since its hash was " +
  "recorded. It does not establish who created or collected the evidence.";

export const INTEGRITY_VERIFIED = "INTEGRITY VERIFIED";
export const INTEGRITY_MISMATCH = "INTEGRITY MISMATCH";
export const INTEGRITY_TEST_LABEL = "Controlled Integrity Test - Demonstration Copy";
export const HASH_ALGORITHM = "SHA-256";

export const SCORE_LABEL = "Anomaly score";
export const THRESHOLD_LABEL = "Detection threshold";
export const FUSION_LABEL = "Composite Suspicion Score";

export const ANOMALY_DISCLAIMER =
  "The anomaly score indicates statistical deviation from this case's typical event " +
  "patterns. It is not proof of malicious activity and requires investigator review.";

export const FUSION_DISCLAIMER =
  "The Composite Suspicion Score is an uncalibrated heuristic composite - not a probability " +
  "and not proof of malicious activity. Requires investigator validation.";

export const SYNTHETIC_DATA_LABEL = "Trained and evaluated on synthetic demonstration data.";

// ---------------------------------------------------------------------------
// Automated analysis (Phase 3) — mirror of backend/app/terminology.py
// ---------------------------------------------------------------------------

export const ANALYSIS_RUN_LABEL = "Automated Analysis Run";

export const ANALYSIS_SCOPE_NOTE =
  "Analysis is limited to the normalized forensic events of this case. " +
  "Rule detections and ML anomaly scores are statistical observations that " +
  "require investigator review.";

export const ANALYSIS_NO_EVENTS = "No normalized forensic events available for analysis.";

export const ML_ABSTAIN_NOTE =
  "Too few event windows for a meaningful ML comparison - anomaly detection " +
  "abstained and no ML finding was created for this run.";

export const ANOMALY_SCORE_DESCRIPTION =
  "Normalized to [0, 1] over this case's event windows; a higher value " +
  "indicates greater statistical deviation from the case's typical pattern.";

export const RULE_CONFIDENCE_NOTE =
  "Rule confidence is a fixed deterministic indicator weight, not a probability.";

export const TIMELINE_LABEL = "Reconstructed Investigation Timeline";
export const TIMELINE_DISCLAIMER =
  "A reconstruction derived from the evidence available in this case. " +
  "It is not an established sequence of events.";

export const CORRELATION_DISCLAIMER =
  "Correlation indicates co-occurrence and shared context, not causation. " +
  "Requires investigator validation.";

// ---------------------------------------------------------------------------
// Correlation / activity groups / timeline (Phase 4) — mirrors backend/app/terminology.py
// ---------------------------------------------------------------------------

export const CORRELATION_RUN_LABEL = "Correlation Run";

export const CORRELATION_NO_EVENTS =
  "No normalized forensic events available for correlation.";

export const CORRELATION_GROUP_NOTE =
  "Activity groups are built from reason-tagged correlations between real " +
  "events of this case - no inferred or merged entities.";

export const INSUFFICIENT_EVIDENCE = "Insufficient evidence in the current case.";
export const PLANNED_LABEL = "Prototype / Planned";
export const DEMO_LABEL = "SYNTHETIC / DEMONSTRATION DATA";

// ---------------------------------------------------------------------------
// Dashboard (Phase 7) — read-only scenario statistics
// ---------------------------------------------------------------------------

export const DASHBOARD_LABEL = "Scenario Statistics";

export const DASHBOARD_NOTE =
  "Dashboard figures are read-only aggregates of the data already persisted " +
  "by the analysis phases. They are counts and sums of stored rows, not new " +
  "analysis, and require investigator review.";

export const DASHBOARD_KPI_LABEL = "Per-case overview";

export const ASSISTANT_FOOTER =
  "Answers are constructed only from processed case evidence. No generative model is enabled.";

export const ASSISTANT_INSUFFICIENT =
  "I could not find sufficient evidence in this case to answer that question.";

export const ASSISTANT_UNSUPPORTED =
  "This question is outside the currently supported investigation assistant capabilities.";

export const ASSISTANT_EMPTY_CASE =
  "No forensic evidence is currently available for this case.";

export const ASSISTANT_CAPABILITIES =
  "I can currently answer questions about:\n" +
  "• case summary\n" +
  "• suspicious findings\n" +
  "• finding explanations\n" +
  "• evidence support\n" +
  "• timeline activity\n" +
  "• correlations\n" +
  "• investigation groups\n" +
  "• ML anomaly reasoning\n" +
  "• evidence integrity\n" +
  "• processing status\n" +
  "• investigator review status";

export const TRACEABILITY_STEPS = [
  "Finding",
  "Reason",
  "Forensic Event",
  "Raw Record",
  "Evidence File",
  "Recorded SHA-256",
] as const;

// ---------------------------------------------------------------------------
// Forensic reports (Phase 6) — mirrors backend/app/terminology.py
// ---------------------------------------------------------------------------

export const REPORT_TITLE = "Digital Forensic Investigation Report";
export const REPORT_SCHEMA = "FORENSIGHT_REPORT_V1";
export const REPORT_VERSION = "1.0";
export const REPORT_STATUS = "Generated";
export const REPORT_NO_ANALYSIS = "No analysis result is currently available.";
export const REPORT_TRACE_UNAVAILABLE = "Trace unavailable for this finding.";
export const REPORT_SYSTEM_ENTRY = "system-generated finding";
export const REPORT_REVIEW_ENTRY = "investigator-entered assessment";

export const REPORT_INTEGRITY_VERIFIED_EXPLAIN =
  "The current evidence bytes matched the recorded SHA-256 reference during verification.";
export const REPORT_INTEGRITY_MISMATCH_EXPLAIN =
  "The current evidence bytes did not match the recorded SHA-256 reference during verification.";
export const REPORT_INTEGRITY_NOTE =
  "SHA-256 matching confirms byte-for-byte equivalence with the recorded reference " +
  "only; it does not establish who created or collected the evidence.";
export const REPORT_INTEGRITY_NOT_VERIFIED = "NOT VERIFIED";
export const REPORT_INTEGRITY_NO_CHECK = "NO CHECK AVAILABLE";

export const REPORT_CONCLUSION_NO_FINDINGS =
  "No suspicious findings were recorded by the configured forensic analysis pipeline.";
export const REPORT_CONCLUSION_NO_CORRELATION =
  "The investigation identified suspicious activity in the analyzed evidence, " +
  "but no cross-source correlations were recorded.";
export const REPORT_CONCLUSION_WITH_CORRELATION =
  "The investigation identified suspicious activity with supporting cross-source " +
  "relationships in the analyzed evidence.";
export const REPORT_CONCLUSION_INSUFFICIENT =
  "The available evidence does not support a definitive conclusion from the current " +
  "prototype analysis.";
export const REPORT_HIGH_SEVERITY_NOTE =
  "High-severity findings require investigator review and contextual interpretation.";

export const REPORT_LIMIT_PROTOTYPE =
  "FORENSIGHT AI is a research/hackathon prototype, not a certified forensic or " +
  "legal-admissibility system.";
export const REPORT_LIMIT_INTEGRITY =
  "SHA-256 verification only proves the current bytes match the recorded reference; " +
  "it does not authenticate origin, collection, or custody.";
export const REPORT_LIMIT_ML =
  "ML anomaly scores are statistical deviations from this case's typical event pattern; " +
  "they are not proof of malicious activity.";
export const REPORT_LIMIT_SCORES =
  "Composite Suspicion Scores are uncalibrated heuristic composites, not probabilities.";
export const REPORT_LIMIT_REVIEW =
  "All findings require investigator review and validation before any action is taken.";
export const REPORT_LIMIT_DATA =
  "This report reflects only the evidence ingested and processed in this case up to " +
  "the generation time.";

export const REPORT_ML_STATEMENT =
  "The ML component identified statistically unusual activity relative to the configured " +
  "detection strategy; anomaly scores are not proof of malicious activity.";
