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
