/** Case endpoints (Phase 1). */

import { apiGet, apiPatch, apiPost } from "./client";
import type { CaseCreatePayload, CaseSummary, CustodyEvent } from "../types/models";

export const listCases = (): Promise<CaseSummary[]> => apiGet("/api/cases");

export const getCase = (caseId: string): Promise<CaseSummary> =>
  apiGet(`/api/cases/${encodeURIComponent(caseId)}`);

export const createCase = (payload: CaseCreatePayload): Promise<CaseSummary> =>
  apiPost("/api/cases", payload);

export const updateCase = (
  caseId: string,
  payload: Partial<Pick<CaseSummary, "status" | "severity">>,
): Promise<CaseSummary> => apiPatch(`/api/cases/${encodeURIComponent(caseId)}`, payload);

export const getCaseCustody = (caseId: string): Promise<CustodyEvent[]> =>
  apiGet(`/api/cases/${encodeURIComponent(caseId)}/custody`);
