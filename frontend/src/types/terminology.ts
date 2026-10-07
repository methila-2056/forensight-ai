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
  "back to source evidence.";

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

export const ASSISTANT_FOOTER =
  "Answers are constructed only from processed case evidence. No generative model is enabled.";

export const TRACEABILITY_STEPS = [
  "Finding",
  "Reason",
  "Forensic Event",
  "Raw Record",
  "Evidence File",
  "Recorded SHA-256",
] as const;
