/** Forensic report endpoints (Phase 6). Reports are immutable, case-scoped
 * snapshots built only from persisted case data. */

import { apiGet, apiPost } from "./client";
import type {
  ReportDetail,
  ReportGenerateRequest,
  ReportRawJson,
  ReportSummary,
} from "../types/models";

const encode = encodeURIComponent;

export const generateReport = (
  caseId: string,
  payload: ReportGenerateRequest = {},
): Promise<ReportDetail> =>
  apiPost(`/api/cases/${encode(caseId)}/reports`, {
    title: payload.title,
    actor: payload.actor,
  });

export const listReports = (caseId: string): Promise<ReportSummary[]> =>
  apiGet(`/api/cases/${encode(caseId)}/reports`);

export const getReport = (
  caseId: string,
  reportId: string,
): Promise<ReportDetail> =>
  apiGet(`/api/cases/${encode(caseId)}/reports/${encode(reportId)}`);

export const getReportRawJson = (
  caseId: string,
  reportId: string,
): Promise<ReportRawJson> =>
  apiGet(`/api/cases/${encode(caseId)}/reports/${encode(reportId)}/json`);