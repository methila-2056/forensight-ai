/** Case endpoints (Phase 1, investigator notes in Phase 10). */

import { apiGet, apiPatch, apiPost } from "./client";
import type {
  CaseCreatePayload,
  CaseSummary,
  CustodyEvent,
  NoteList,
  NoteSummary,
} from "../types/models";

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

/* Investigator notes — append-only. There is deliberately no update or
   delete helper: a recorded annotation cannot be edited away. */

export const getCaseNotes = (caseId: string): Promise<NoteList> =>
  apiGet(`/api/cases/${encodeURIComponent(caseId)}/notes`);

export const getFindingNotes = (caseId: string, findingId: string): Promise<NoteList> =>
  apiGet(
    `/api/cases/${encodeURIComponent(caseId)}/notes?finding_uid=${encodeURIComponent(findingId)}`,
  );

export const addCaseNote = (
  caseId: string,
  payload: { body: string; author?: string; finding_uid?: string },
): Promise<NoteSummary> => apiPost(`/api/cases/${encodeURIComponent(caseId)}/notes`, payload);
