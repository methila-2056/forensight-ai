/** Investigation assistant endpoints (Phase 5). */

import { apiGet, apiPost } from "./client";
import type { AssistantQueryResult } from "../types/models";

const encode = encodeURIComponent;

export const askAssistant = (
  caseId: string,
  question: string,
  actor = "ui",
): Promise<AssistantQueryResult> =>
  apiPost(`/api/cases/${encode(caseId)}/assistant/query`, { question, actor });

export const listAssistantHistory = (
  caseId: string,
  limit = 100,
): Promise<AssistantQueryResult[]> =>
  apiGet(`/api/cases/${encode(caseId)}/assistant/history?limit=${limit}`);

export const getAssistantQuery = (
  caseId: string,
  queryId: number,
): Promise<AssistantQueryResult> =>
  apiGet(`/api/cases/${encode(caseId)}/assistant/queries/${queryId}`);