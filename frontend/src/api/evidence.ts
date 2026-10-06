/** Evidence + integrity endpoints (Phase 1). */

import { apiGet, apiPost, apiUpload } from "./client";
import type {
  CustodyEvent,
  EvidenceItem,
  EvidenceType,
  IntegrityTestResult,
  IntegrityVerifyResult,
  UploadPolicy,
} from "../types/models";

export const listEvidence = (caseId: string): Promise<EvidenceItem[]> =>
  apiGet(`/api/cases/${encodeURIComponent(caseId)}/evidence`);

export const getEvidence = (evidenceId: string): Promise<EvidenceItem> =>
  apiGet(`/api/evidence/${encodeURIComponent(evidenceId)}`);

export const uploadEvidenceFile = (
  caseId: string,
  file: File,
  evidenceType: EvidenceType,
  source: string,
): Promise<EvidenceItem> => {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("evidence_type", evidenceType);
  formData.append("source", source);
  return apiUpload(`/api/cases/${encodeURIComponent(caseId)}/evidence`, formData);
};

export const verifyEvidence = (evidenceId: string): Promise<IntegrityVerifyResult> =>
  apiPost(`/api/evidence/${encodeURIComponent(evidenceId)}/verify`);

export const controlledIntegrityTest = (evidenceId: string): Promise<IntegrityTestResult> =>
  apiPost(`/api/evidence/${encodeURIComponent(evidenceId)}/integrity-test`);

export const getEvidenceCustody = (evidenceId: string): Promise<CustodyEvent[]> =>
  apiGet(`/api/evidence/${encodeURIComponent(evidenceId)}/custody`);

export const getUploadPolicy = (): Promise<UploadPolicy> => apiGet("/api/policy");
