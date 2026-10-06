/**
 * Typed API client with the structured error envelope:
 * { error: { code, message, detail? } }
 */

const BASE_URL: string = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the FORENSIGHT AI backend. Is it running?");
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const envelope = (body as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(
      response.status,
      envelope?.code ?? `HTTP_${response.status}`,
      envelope?.message ?? `Request failed with status ${response.status}.`,
    );
  }
  return body as T;
}

export const apiGet = <T,>(path: string): Promise<T> => request<T>(path);

export const apiPost = <T,>(path: string, payload?: unknown): Promise<T> =>
  request<T>(path, {
    method: "POST",
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });

export const apiPatch = <T,>(path: string, payload: unknown): Promise<T> =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(payload) });

export const apiUpload = <T,>(path: string, formData: FormData): Promise<T> =>
  request<T>(path, { method: "POST", body: formData });

export const getHealth = (): Promise<{ status: string }> => apiGet("/api/health");
