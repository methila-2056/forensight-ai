/** Automated analysis + findings endpoints (Phase 3). */

import { apiGet, apiPatch, apiPost } from "./client";
import type {
  AnalysisRun,
  FindingDetail,
  FindingListResult,
  FindingQuery,
  FindingStatus,
  FindingTrace,
  MlMetrics,
} from "../types/models";

const encode = encodeURIComponent;

export const analyzeCase = (caseId: string, actor = "ui"): Promise<AnalysisRun> =>
  apiPost(`/api/cases/${encode(caseId)}/analyze`, { actor });

export const listAnalysisRuns = (caseId: string): Promise<AnalysisRun[]> =>
  apiGet(`/api/cases/${encode(caseId)}/analysis-runs`);

export const listFindings = (
  caseId: string,
  query: FindingQuery = {},
): Promise<FindingListResult> => {
  const params = new URLSearchParams();
  const append = (key: string, value: string | number | undefined): void => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  };
  append("kind", query.kind);
  append("severity", query.severity);
  append("status", query.status);
  append("run_id", query.run_id);
  append("limit", query.limit);
  append("offset", query.offset);
  const queryString = params.toString();
  return apiGet(
    `/api/cases/${encode(caseId)}/findings${queryString ? `?${queryString}` : ""}`,
  );
};

export const getFinding = (caseId: string, findingId: string): Promise<FindingDetail> =>
  apiGet(`/api/cases/${encode(caseId)}/findings/${encode(findingId)}`);

export const getFindingTrace = (caseId: string, findingId: string): Promise<FindingTrace> =>
  apiGet(`/api/cases/${encode(caseId)}/findings/${encode(findingId)}/trace`);

export const reviewFinding = (
  caseId: string,
  findingId: string,
  payload: { status: FindingStatus; note?: string; author?: string },
): Promise<FindingDetail> =>
  apiPatch(`/api/cases/${encode(caseId)}/findings/${encode(findingId)}`, payload);

export const getMlMetrics = (caseId: string): Promise<MlMetrics> =>
  apiGet(`/api/cases/${encode(caseId)}/ml-metrics`);
