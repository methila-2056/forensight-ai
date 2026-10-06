/** Processing + normalized event endpoints (Phase 2). */

import { apiGet, apiPost } from "./client";
import type {
  EventDetail,
  EventListResult,
  EventQuery,
  EvidenceProcessing,
  ProcessCaseResult,
  ProcessRequest,
  ProcessingRun,
  RejectedRecord,
} from "../types/models";

const encode = encodeURIComponent;

export const processCase = (
  caseId: string,
  payload: ProcessRequest = {},
): Promise<ProcessCaseResult> =>
  apiPost(`/api/cases/${encode(caseId)}/process`, payload);

export const listProcessingRuns = (caseId: string): Promise<ProcessingRun[]> =>
  apiGet(`/api/cases/${encode(caseId)}/processing-runs`);

export const getEvidenceProcessing = (evidenceId: string): Promise<EvidenceProcessing> =>
  apiGet(`/api/evidence/${encode(evidenceId)}/processing`);

export const getRejectedRecords = (evidenceId: string): Promise<RejectedRecord[]> =>
  apiGet(`/api/evidence/${encode(evidenceId)}/rejected-records`);

export const listEvents = (caseId: string, query: EventQuery = {}): Promise<EventListResult> => {
  const params = new URLSearchParams();
  const append = (key: string, value: string | number | undefined): void => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  };
  append("source_type", query.source_type);
  append("event_type", query.event_type);
  append("severity", query.severity);
  append("user", query.user);
  append("host", query.host);
  append("timestamp_from", query.timestamp_from);
  append("timestamp_to", query.timestamp_to);
  append("evidence_id", query.evidence_id);
  append("limit", query.limit);
  append("offset", query.offset);
  const queryString = params.toString();
  return apiGet(`/api/cases/${encode(caseId)}/events${queryString ? `?${queryString}` : ""}`);
};

export const getEvent = (caseId: string, eventId: string): Promise<EventDetail> =>
  apiGet(`/api/cases/${encode(caseId)}/events/${encode(eventId)}`);