import type { WorkspaceResponse } from "../types/models";
import { apiGet } from "./client";

export const fetchWorkspace = (caseId: string): Promise<WorkspaceResponse> =>
  apiGet<WorkspaceResponse>(`/api/cases/${encodeURIComponent(caseId)}/workspace`);