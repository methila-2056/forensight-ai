/**
 * Minimal typed API client (Phase 0 scaffolding).
 * Only the health endpoint is implemented; later phases add typed endpoint modules.
 */

const BASE_URL: string = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export interface HealthResponse {
  status: string;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new ApiError(response.status, `Request failed: GET ${path} -> ${response.status}`);
  }
  return (await response.json()) as T;
}

export const getHealth = (): Promise<HealthResponse> => apiGet<HealthResponse>("/api/health");
