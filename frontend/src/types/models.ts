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
