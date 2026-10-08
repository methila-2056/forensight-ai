/** DTOs mirroring the backend Pydantic schemas (Phase 1). */

export type CaseStatus = "Draft" | "Active" | "Under Review" | "Closed";
export type Severity = "Low" | "Medium" | "High" | "Critical";

export type EvidenceType =
  | "authentication"
  | "process"
  | "file_activity"
  | "network"
  | "browser"
  | "system"
  | "generic";

export type EvidenceStatus = "Uploaded" | "Verified" | "Processing" | "Processed" | "Analyzed" | "Error";

export type SourceType =
  | "authentication"
  | "process"
  | "file_activity"
  | "network"
  | "browser"
  | "system"
  | "generic";

export type ProcessingStatus = "Pending" | "Processing" | "Completed" | "Partial" | "Failed";

export interface CaseSummary {
  case_id: string;
  name: string;
  investigator: string;
  description: string;
  status: CaseStatus;
  severity: Severity;
  created_at: string;
  last_activity: string;
  demo: boolean;
  evidence_count: number;
  finding_count: number;
}

export interface CaseCreatePayload {
  name: string;
  investigator: string;
  description?: string;
  severity: Severity;
}

export interface EvidenceItem {
  evidence_id: string;
  case_id: string;
  original_filename: string;
  evidence_type: EvidenceType;
  source_description: string;
  file_size: number;
  mime_type: string;
  sha256: string;
  uploaded_at: string;
  status: EvidenceStatus;
  record_count: number | null;
  parse_ok: number | null;
  parse_rejected: number | null;
}

export interface IntegrityVerifyResult {
  evidence_id: string;
  algorithm: string;
  result: string;
  computed_hash: string;
  expected_hash: string;
  verified_at: string;
  note: string;
}

export interface IntegrityTestResult {
  evidence_id: string;
  operation: string;
  result: string;
  recorded_hash: string;
  test_copy_hash: string;
  original_unchanged: boolean;
  note: string;
}

export interface CustodyEvent {
  id: number;
  case_id: string;
  evidence_id: string | null;
  timestamp: string;
  action: string;
  actor: string;
  details: Record<string, unknown> | null;
}

export interface UploadPolicy {
  max_upload_bytes: number;
  max_upload_mb: number;
  allowed_extensions: string[];
  hash_algorithm: string;
  integrity_note: string;
}

// ---------------------------------------------------------------------------
// Phase 2: processing runs + normalized events
// ---------------------------------------------------------------------------

export interface ProcessRequest {
  evidence_ids?: string[];
  actor?: string;
}

export interface ProcessingRun {
  run_id: string;
  case_id: string;
  evidence_id: string;
  evidence_filename: string;
  parser: string;
  status: ProcessingStatus;
  started_at: string | null;
  completed_at: string | null;
  records_received: number;
  records_parsed: number;
  records_normalized: number;
  records_rejected: number;
  duplicates_detected: number;
  warnings: string[];
  error_code: string | null;
  error: string | null;
}

export interface ProcessCaseResult {
  case_id: string;
  runs: ProcessingRun[];
}

export interface EvidenceProcessing {
  evidence_id: string;
  original_filename: string;
  sha256: string;
  status: EvidenceStatus;
  record_count: number | null;
  parse_ok: number | null;
  parse_rejected: number | null;
  runs: ProcessingRun[];
}

export interface RejectedRecord {
  evidence_id: string;
  row_index: number;
  parser: string;
  status: string;
  reason: string | null;
  original_record: string;
  processed_at: string | null;
}

export interface ForensicEvent {
  event_id: string;
  case_id: string;
  evidence_id: string;
  timestamp: string | null;
  tz_note: string | null;
  source_type: SourceType;
  event_type: string;
  user: string | null;
  host: string | null;
  source_ip: string | null;
  destination_ip: string | null;
  process: string | null;
  file_path: string | null;
  action: string | null;
  severity: Severity | null;
  anomaly_score: number | null;
  is_anomalous: boolean;
  raw_record_reference: number | null;
  duplicate: boolean;
  duplicate_of: string | null;
  metadata: Record<string, unknown> | null;
}

export interface EventListResult {
  events: ForensicEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface EventQuery {
  source_type?: SourceType | "";
  event_type?: string;
  severity?: Severity | "";
  user?: string;
  host?: string;
  timestamp_from?: string;
  timestamp_to?: string;
  evidence_id?: string;
  limit?: number;
  offset?: number;
}

export interface EventRawRecord {
  row_index: number;
  content: string;
  reject_reason: string | null;
}

export interface EventEvidenceRef {
  evidence_id: string;
  original_filename: string;
  sha256: string;
  uploaded_at: string;
}

export interface EventDetail extends ForensicEvent {
  raw_record: EventRawRecord | null;
  evidence: EventEvidenceRef | null;
}

export const SOURCE_TYPE_OPTIONS: Array<{ value: SourceType; label: string }> = [
  { value: "authentication", label: "Authentication" },
  { value: "process", label: "Process" },
  { value: "file_activity", label: "File activity" },
  { value: "network", label: "Network" },
  { value: "browser", label: "Browser" },
  { value: "system", label: "System" },
  { value: "generic", label: "Generic" },
];

export const PROCESSING_STATUS_OPTIONS: ProcessingStatus[] = [
  "Pending",
  "Processing",
  "Completed",
  "Partial",
  "Failed",
];

export const EVIDENCE_TYPE_OPTIONS: Array<{ value: EvidenceType; label: string }> = [
  { value: "authentication", label: "Authentication / login log" },
  { value: "process", label: "Process activity" },
  { value: "file_activity", label: "File activity" },
  { value: "network", label: "Network connections" },
  { value: "browser", label: "Browser activity" },
  { value: "system", label: "System log" },
  { value: "generic", label: "Generic / other" },
];

export const SEVERITY_OPTIONS: Severity[] = ["Low", "Medium", "High", "Critical"];
export const CASE_STATUS_OPTIONS: CaseStatus[] = ["Draft", "Active", "Under Review", "Closed"];

// ---------------------------------------------------------------------------
// Phase 3: automated analysis + findings
// ---------------------------------------------------------------------------

export type RunStage = "Process" | "Analyze" | "Correlate" | "Report";
export type AnalysisRunStatus = "Pending" | "Running" | "Completed" | "Failed";
export type FindingKind = "rule" | "ml";
export type FindingStatus = "New" | "Under Review" | "Confirmed" | "Dismissed";

export interface AnalysisRun {
  run_id: string;
  case_id: string;
  stage: RunStage;
  status: AnalysisRunStatus;
  started_at: string | null;
  finished_at: string | null;
  stats: Record<string, unknown> | null;
  error: string | null;
}

export interface FindingSummary {
  finding_id: string;
  case_id: string;
  kind: FindingKind;
  run_id: string | null;
  rule_id: string | null;
  model_name: string | null;
  title: string;
  severity: Severity;
  status: FindingStatus;
  confidence: number | null;
  anomaly_score: number | null;
  threshold: number | null;
  composite_suspicion_score: number | null;
  event_count: number;
  evidence_count: number;
  created_at: string;
  updated_at: string;
}

export interface FindingListResult {
  findings: FindingSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface FindingQuery {
  kind?: "" | FindingKind;
  severity?: "" | Severity;
  status?: "" | FindingStatus;
  run_id?: string;
  limit?: number;
  offset?: number;
}

export interface FindingNote {
  author: string;
  body: string;
  created_at: string;
}

export interface FindingEvidence {
  evidence_id: string;
  original_filename: string;
  evidence_type: EvidenceType;
  file_size: number;
  sha256: string;
  uploaded_at: string;
}

export interface FindingComponent {
  value: number;
  contribution: number;
  severity?: string | null;
  distinct_evidence?: number;
}

export interface FindingComponents {
  formula_version: string;
  formula: string;
  weights: Record<string, number>;
  components: {
    rule: FindingComponent;
    anomaly: FindingComponent;
    correlation: FindingComponent;
  };
  total: number;
  band: string;
  note: string;
}

export interface FindingDetail {
  finding_id: string;
  case_id: string;
  kind: FindingKind;
  run_id: string | null;
  rule_id: string | null;
  model_name: string | null;
  model_version: string | null;
  feature_version: string | null;
  title: string;
  severity: Severity;
  status: FindingStatus;
  confidence: number | null;
  anomaly_score: number | null;
  threshold: number | null;
  composite_suspicion_score: number | null;
  components: FindingComponents | null;
  feature_snapshot: Record<string, unknown> | null;
  explanation: unknown;
  reasons: string[] | null;
  timestamp_start: string | null;
  timestamp_end: string | null;
  event_ids: string[];
  evidence_ids: string[];
  supporting_events: ForensicEvent[];
  evidence: FindingEvidence[];
  notes: FindingNote[];
  created_at: string;
  updated_at: string;
}

export interface FindingTrace {
  finding_id: string;
  case_id: string;
  kind: FindingKind;
  events: EventDetail[];
  evidence: FindingEvidence[];
}

export interface MlMetrics {
  case_id: string;
  run_id: string | null;
  stats: Record<string, unknown>;
  config: Record<string, number>;
  scope_note: string;
}

export const FINDING_STATUS_OPTIONS: FindingStatus[] = [
  "New",
  "Under Review",
  "Confirmed",
  "Dismissed",
];

export const FINDING_KIND_OPTIONS: Array<{ value: "" | FindingKind; label: string }> = [
  { value: "", label: "All kinds" },
  { value: "rule", label: "Rule" },
  { value: "ml", label: "Machine learning" },
];

/** Mirrors the backend review workflow (analysis_service._ALLOWED_TRANSITIONS). */
export const ALLOWED_STATUS_TRANSITIONS: Record<FindingStatus, FindingStatus[]> = {
  New: ["Under Review"],
  "Under Review": ["Confirmed", "Dismissed"],
  Confirmed: ["Under Review", "Dismissed"],
  Dismissed: ["Under Review", "Confirmed"],
};

// ---------------------------------------------------------------------------
// Phase 4: cross-source correlation, groups, timeline, evidence graph
// ---------------------------------------------------------------------------

export type CorrelationType =
  | "CORR-001"
  | "CORR-002"
  | "CORR-003"
  | "CORR-004"
  | "CORR-005";

export type GroupKind =
  | "authentication"
  | "process"
  | "file_activity"
  | "network"
  | "cross_source";

export type TimelineSignificance = "NORMAL" | "NOTABLE" | "SUSPICIOUS";

export type ConfidenceBand = "Low" | "Medium" | "High";

export interface CorrelationRun {
  run_id: string;
  case_id: string;
  status: AnalysisRunStatus;
  started_at: string | null;
  finished_at: string | null;
  stats: Record<string, unknown> | null;
  error: string | null;
}

export interface CorrelationEventSummary {
  event_id: string;
  timestamp: string | null;
  source_type: SourceType;
  event_type: string;
  user: string | null;
  host: string | null;
  source_ip: string | null;
  destination_ip: string | null;
  process: string | null;
  file_path: string | null;
  action: string | null;
  anomaly_score: number | null;
  is_anomalous: boolean;
  evidence_id: string;
}

export interface CorrelationSummary {
  correlation_id: string;
  case_id: string;
  run_id: string;
  correlation_type: CorrelationType;
  event_a: CorrelationEventSummary;
  event_b: CorrelationEventSummary;
  time_delta_seconds: number | null;
  confidence: number;
  confidence_band: ConfidenceBand;
  reason: string;
  shared_entities: Record<string, string>;
  evidence_ids: string[];
  created_at: string;
}

export interface CorrelationDetail extends CorrelationSummary {
  disclaimer: string;
  event_a_detail: EventDetail | null;
  event_b_detail: EventDetail | null;
}

export interface CorrelationListResult {
  correlations: CorrelationSummary[];
  total: number;
  limit: number;
  offset: number;
  disclaimer: string;
}

export interface CorrelationQuery {
  type?: CorrelationType | "";
  run_id?: string;
  limit?: number;
  offset?: number;
}

export interface GroupSummary {
  group_id: string;
  case_id: string;
  run_id: string;
  kind: GroupKind;
  title: string;
  severity: Severity;
  explanation: string;
  time_start: string | null;
  time_end: string | null;
  event_count: number;
  correlation_count: number;
  evidence_ids: string[];
  correlation_uids: string[];
  created_at: string;
}

export interface GroupDetail extends GroupSummary {
  member_events: CorrelationEventSummary[];
  disclaimer: string;
}

export interface GroupListResult {
  groups: GroupSummary[];
  total: number;
  limit: number;
  offset: number;
  disclaimer: string;
}

export interface GroupQuery {
  kind?: GroupKind | "";
  run_id?: string;
  limit?: number;
  offset?: number;
}

export interface TimelineEntry {
  timestamp: string | null;
  event_id: string;
  source_type: SourceType;
  event_type: string;
  user: string | null;
  host: string | null;
  process: string | null;
  file_path: string | null;
  action: string | null;
  anomaly_score: number | null;
  is_anomalous: boolean;
  significance: TimelineSignificance;
  reasons: string[];
  finding_ids: string[];
  correlation_ids: string[];
  evidence_id: string;
  context: boolean;
}

export interface TimelineResult {
  case_id: string;
  label: string;
  disclaimer: string;
  entries: TimelineEntry[];
  total: number;
  truncated: boolean;
  note: string | null;
}

export interface GraphNode {
  id: string;
  type: "evidence" | "finding" | "event";
  label: string;
  detail: string | null;
  significance: TimelineSignificance | null;
  severity: Severity | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: "contains" | "triggered" | "correlated";
  label: string;
  correlation_type: CorrelationType | null;
  confidence: number | null;
}

export interface GraphTableRow {
  source: string;
  relation: string;
  target: string;
}

export interface GraphResult {
  case_id: string;
  run_id: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  table_rows: GraphTableRow[];
  truncated: boolean;
  max_nodes: number;
  max_edges: number;
  disclaimer: string;
  note: string | null;
}

export const CORRELATION_TYPE_OPTIONS: Array<{
  value: "" | CorrelationType;
  label: string;
}> = [
  { value: "", label: "All types" },
  { value: "CORR-001", label: "CORR-001 · Same host" },
  { value: "CORR-002", label: "CORR-002 · Same user" },
  { value: "CORR-003", label: "CORR-003 · Same source IP" },
  { value: "CORR-004", label: "CORR-004 · Process → file" },
  { value: "CORR-005", label: "CORR-005 · Process → external" },
];

export const CORRELATION_TYPE_LABELS: Record<CorrelationType, string> = {
  "CORR-001": "Same host",
  "CORR-002": "Same user",
  "CORR-003": "Same source IP",
  "CORR-004": "Process → file activity",
  "CORR-005": "Process → external connection",
};

export const GROUP_KIND_OPTIONS: Array<{ value: "" | GroupKind; label: string }> = [
  { value: "", label: "All kinds" },
  { value: "authentication", label: "Authentication" },
  { value: "process", label: "Process" },
  { value: "file_activity", label: "File activity" },
  { value: "network", label: "Network" },
  { value: "cross_source", label: "Cross-source" },
];

export const TIMELINE_SIGNIFICANCE_OPTIONS: Array<{
  value: "" | TimelineSignificance;
  label: string;
}> = [
  { value: "", label: "All entries" },
  { value: "SUSPICIOUS", label: "Suspicious (rule)" },
  { value: "NOTABLE", label: "Notable (ML / anomalous)" },
  { value: "NORMAL", label: "Normal (context / correlation)" },
];

// ---------------------------------------------------------------------------
// Investigation assistant (Phase 5)
// ---------------------------------------------------------------------------

export type AssistantIntent =
  | "CASE_SUMMARY"
  | "TOP_FINDINGS"
  | "FINDING_EXPLANATION"
  | "FINDING_TRACE"
  | "EVIDENCE_SUPPORT"
  | "TIMELINE_CONTEXT"
  | "CORRELATION_SUMMARY"
  | "GROUP_SUMMARY"
  | "ML_EXPLANATION"
  | "REVIEW_QUEUE"
  | "INTEGRITY_STATUS"
  | "PROCESSING_STATUS"
  | "CAPABILITIES"
  | "UNKNOWN";

export type AssistantConfidence = "HIGH" | "MEDIUM" | "LOW";

export interface AssistantSource {
  type: "finding" | "event" | "evidence" | "correlation" | "group" | "case" | "run";
  id: string;
  label: string;
}

export interface AssistantQueryResult {
  query_id: number;
  case_id: string;
  question: string;
  intent: AssistantIntent;
  answer: string;
  evidence: string[];
  basis: string[];
  confidence: AssistantConfidence;
  sources: AssistantSource[];
  disclaimer: string;
  created_at: string | null;
}

export const ASSISTANT_SUGGESTED_QUESTIONS = [
  "What suspicious activity was detected?",
  "Why was this activity considered suspicious?",
  "Which evidence files support this finding?",
  "What happened around the suspicious login?",
  "Which user account was involved?",
  "What correlations were detected?",
  "Which findings still need investigator review?",
  "Why did the ML model flag this activity?",
  "Have all evidence files been verified?",
  "What is the processing status?",
] as const;

// ---------------------------------------------------------------------------
// Forensic reports (Phase 6)
// ---------------------------------------------------------------------------

export const REPORT_SECTION_ORDER = [
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
] as const;

export type ReportSectionName = (typeof REPORT_SECTION_ORDER)[number];

export interface ReportSummary {
  report_id: string;
  case_id: string;
  title: string;
  report_version: string;
  schema: string;
  status: string;
  generated_at: string | null;
  generated_by: string;
}

export interface ReportDetail extends ReportSummary {
  sections: Record<ReportSectionName, Record<string, unknown>>;
}

export interface ReportGenerateRequest {
  title?: string;
  actor?: string;
}

export interface ReportRawJson {
  metadata: Record<string, unknown>;
  sections: Record<ReportSectionName, Record<string, unknown>>;
}
