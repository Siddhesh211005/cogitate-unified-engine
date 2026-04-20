const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

if (typeof window !== 'undefined') {
  console.log('[API Client] Backend URL:', API_BASE);
}

export async function apiGet<T>(path: string): Promise<T> {
  const url = `${API_BASE}${path}`;
  console.log('[API] GET', url);
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Status ${res.status}: ${error}`);
    }
    return (await res.json()) as T;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error('[API] GET failed:', url, msg);
    throw new Error(`GET ${url} failed: ${msg}. Is backend running at ${API_BASE}?`);
  }
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const url = `${API_BASE}${path}`;
  console.log('[API] POST', url);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Status ${res.status}: ${error}`);
    }
    return (await res.json()) as T;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error('[API] POST failed:', url, msg);
    throw new Error(`POST ${url} failed: ${msg}. Is backend running at ${API_BASE}?`);
  }
}

/**
 * Upload file as FormData (for multipart/form-data requests)
 * Used for Excel uploads, image uploads, etc.
 */
export async function apiUploadFormData<T>(path: string, formData: FormData): Promise<T> {
  const url = `${API_BASE}${path}`;
  console.log('[API] UPLOAD', url);
  try {
    const res = await fetch(url, {
      method: "POST",
      body: formData,
      // Don't set Content-Type header - browser will set it with boundary
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Status ${res.status}: ${error}`);
    }
    return (await res.json()) as T;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error('[API] UPLOAD failed:', url, msg);
    throw new Error(`Upload to ${url} failed: ${msg}. Is backend running at ${API_BASE}?`);
  }
}
