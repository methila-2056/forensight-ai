/** Cross-source correlation, groups, timeline, and graph endpoints (Phase 4). */

import { apiGet, apiPost } from "./client";
import type {
  CorrelationDetail,
  CorrelationListResult,
  CorrelationQuery,
  CorrelationRun,
  GraphResult,
  GroupDetail,
  GroupListResult,
  GroupQuery,
  TimelineResult,
} from "../types/models";

const encode = encodeURIComponent;

const queryString = (params: Record<string, string | number | undefined>): string => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : "";
};

export const correlateCase = (caseId: string, actor = "ui"): Promise<CorrelationRun> =>
  apiPost(`/api/cases/${encode(caseId)}/correlate`, { actor });

export const listCorrelationRuns = (caseId: string): Promise<CorrelationRun[]> =>
  apiGet(`/api/cases/${encode(caseId)}/correlation-runs`);

export const listCorrelations = (
  caseId: string,
  query: CorrelationQuery = {},
): Promise<CorrelationListResult> =>
  apiGet(
    `/api/cases/${encode(caseId)}/correlations${queryString({
      type: query.type,
      run_id: query.run_id,
      limit: query.limit,
      offset: query.offset,
    })}`,
  );

export const getCorrelation = (correlationId: string): Promise<CorrelationDetail> =>
  apiGet(`/api/correlations/${encode(correlationId)}`);

export const listGroups = (
  caseId: string,
  query: GroupQuery = {},
): Promise<GroupListResult> =>
  apiGet(
    `/api/cases/${encode(caseId)}/groups${queryString({
      kind: query.kind,
      run_id: query.run_id,
      limit: query.limit,
      offset: query.offset,
    })}`,
  );

export const getGroup = (groupId: string): Promise<GroupDetail> =>
  apiGet(`/api/groups/${encode(groupId)}`);

export const getTimeline = (caseId: string, runId?: string): Promise<TimelineResult> =>
  apiGet(
    `/api/cases/${encode(caseId)}/timeline${queryString({ run_id: runId })}`,
  );

export const getGraph = (caseId: string, runId?: string): Promise<GraphResult> =>
  apiGet(`/api/cases/${encode(caseId)}/graph${queryString({ run_id: runId })}`);
