/** Read-only dashboard endpoints (Phase 7). Scenario statistics are
 * aggregates of persisted investigation rows — no analysis runs here. */

import { apiGet } from "./client";
import type { DashboardData } from "../types/models";

export const getDashboard = (): Promise<DashboardData> =>
  apiGet("/api/dashboard");