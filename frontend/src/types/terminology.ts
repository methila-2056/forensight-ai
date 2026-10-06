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

export const TIMELINE_LABEL = "Reconstructed Investigation Timeline";
export const TIMELINE_DISCLAIMER =
  "A reconstruction derived from the evidence available in this case. " +
  "It is not an established sequence of events.";

export const CORRELATION_DISCLAIMER =
  "Correlation indicates co-occurrence and shared context, not causation. " +
  "Requires investigator validation.";

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
