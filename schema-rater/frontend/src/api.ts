/** API client — all backend calls in one place. */

import type {
  CalculationRequest,
  CalculationResult,
  RaterMeta,
  RaterSchema,
  UploadResponse,
} from "./types";

const BASE = "/api";

/** Maximum retries for transient network errors (Failed to fetch). */
const MAX_RETRIES = 3;
const RETRY_DELAYS = [1000, 2000, 4000]; // ms — exponential backoff

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

/**
 * Wrapper around fetch with automatic retry on network-level failures
 * (e.g. "Failed to fetch" when the backend is still loading a model).
 */
async function fetchWithRetry(
  input: RequestInfo,
  init?: RequestInit,
  retries = MAX_RETRIES,
): Promise<Response> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(input, init);
      // Retry on 500/502/503/504 (server errors from model loading, gateway errors)
      if (res.status >= 500 && res.status <= 504 && attempt < retries) {
        await delay(RETRY_DELAYS[attempt] ?? 4000);
        continue;
      }
      return res;
    } catch (err) {
      // TypeError: Failed to fetch — network-level failure
      if (attempt < retries) {
        await delay(RETRY_DELAYS[attempt] ?? 4000);
        continue;
      }
      throw new Error(
        "Unable to reach the server. Please make sure the backend is running and try again.",
      );
    }
  }
  // Shouldn't reach here, but TypeScript needs it
  throw new Error("Unable to reach the server after multiple attempts.");
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Upload an Excel rater file. */
export async function uploadRater(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetchWithRetry(`${BASE}/upload`, { method: "POST", body: form });
  return handleResponse<UploadResponse>(res);
}

/** List all uploaded raters. */
export async function listRaters(): Promise<RaterMeta[]> {
  const res = await fetchWithRetry(`${BASE}/raters`);
  return handleResponse<RaterMeta[]>(res);
}

/** Fetch schema for a specific rater. */
export async function fetchSchema(raterId: string): Promise<RaterSchema> {
  const res = await fetchWithRetry(`${BASE}/schema/${raterId}`);
  return handleResponse<RaterSchema>(res);
}

/** Calculate premiums with user inputs. */
export async function calculate(
  req: CalculationRequest,
  signal?: AbortSignal,
): Promise<CalculationResult> {
  const res = await fetchWithRetry(`${BASE}/calculate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  return handleResponse<CalculationResult>(res);
}

/** Calculate premiums with defaults (no overrides). */
export async function calculateDefaults(
  raterId: string,
  signal?: AbortSignal,
): Promise<CalculationResult> {
  // Use more retries for defaults — first call triggers model loading which can be slow
  const res = await fetchWithRetry(
    `${BASE}/calculate/defaults`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rater_id: raterId, inputs: [{}] }),
      signal,
    },
    MAX_RETRIES + 1,
  );
  return handleResponse<CalculationResult>(res);
}

/** Delete a rater. */
export async function deleteRater(raterId: string): Promise<void> {
  const res = await fetchWithRetry(`${BASE}/raters/${raterId}`, { method: "DELETE" });
  await handleResponse<unknown>(res);
}
