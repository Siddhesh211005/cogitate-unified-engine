/**
 * api.js — Engine-agnostic API client.
 *
 * All calls go to /api/* or /gateway/* via the Vite proxy → gateway (port 4000).
 * Zero engine-specific branching here — the proxy handles all differences.
 */

const MAX_RETRIES = 2;
const RETRY_DELAYS_MS = [1000, 2500];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithRetry(url, init = {}, retries = MAX_RETRIES) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, init);
      if (res.status >= 500 && res.status <= 504 && attempt < retries) {
        await sleep(RETRY_DELAYS_MS[attempt] ?? 4000);
        continue;
      }
      return res;
    } catch {
      if (attempt < retries) {
        await sleep(RETRY_DELAYS_MS[attempt] ?? 4000);
        continue;
      }
      throw new Error(
        "Unable to reach the backend. Please ensure all services are running."
      );
    }
  }
}

async function handleResponse(res) {
  if (res.status === 204) return null;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      body?.detail || body?.message || body?.error || `HTTP ${res.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

async function apiGet(path) {
  const res = await fetchWithRetry(`/api${path}`);
  return handleResponse(res);
}

async function apiPost(path, data) {
  const res = await fetchWithRetry(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

async function apiPostForm(path, formData) {
  const res = await fetchWithRetry(`/api${path}`, {
    method: "POST",
    body: formData,
  });
  return handleResponse(res);
}

async function apiDelete(path) {
  const res = await fetchWithRetry(`/api${path}`, { method: "DELETE" });
  return handleResponse(res);
}

// ── Engine management ─────────────────────────────────────────────────────────

export async function getCurrentEngine() {
  try {
    const res = await fetch("/gateway/current");
    if (!res.ok) return null;
    const data = await res.json();
    return data?.selected || null;
  } catch {
    return null;
  }
}

export async function selectEngine(engine) {
  const res = await fetch(`/gateway/select/${engine}`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to select engine");
  return res.json();
}

export async function resetEngine() {
  const res = await fetch("/gateway/reset", { method: "POST" });
  return res.json();
}

// ── Health ────────────────────────────────────────────────────────────────────

export function getHealth() {
  return apiGet("/health");
}

// ── Rater listing ─────────────────────────────────────────────────────────────

export function listRaters() {
  return apiGet("/raters");
}

export function listTemplates() {
  return apiGet("/templates");
}

// ── Schema / Config ───────────────────────────────────────────────────────────

/** source: "raters" | "templates" */
export function getRaterConfig(id, source = "raters") {
  return apiGet(`/raters/${encodeURIComponent(id)}/config?source=${source}`);
}

// ── Upload ────────────────────────────────────────────────────────────────────

/**
 * Upload a rater file.
 * Returns { type: "complete", raterId, ... } or { type: "pending", uploadId, ... }
 * The proxy handles backend routing; the frontend reacts to `type`.
 */
export function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm("/upload", form);
}

// ── Save (excel two-step step 2) ──────────────────────────────────────────────

export function saveUploadedRater({ uploadId, config, slug, name, description, source = "raters" }) {
  return apiPost("/admin/save", {
    upload_id: uploadId,
    config,
    slug,
    name,
    description,
    source,
  });
}

// ── Delete ────────────────────────────────────────────────────────────────────

export function deleteRater(id) {
  return apiDelete(`/raters/${encodeURIComponent(id)}`);
}

// ── Calculate ─────────────────────────────────────────────────────────────────

/** source: "raters" | "templates" */
export function calculateRater(id, inputs, source = "raters") {
  return apiPost("/calculate", { modelId: id, inputs, source });
}

export function calculateTemplate(id, inputs) {
  return calculateRater(id, inputs, "templates");
}

export function calculateDefaults(id, source = "raters") {
  return calculateRater(id, {}, source);
}

// ── Admin test-calculate (excel two-step) ─────────────────────────────────────

export function testCalculate(uploadId, config, inputs = {}) {
  return apiPost("/admin/test-calculate", {
    upload_id: uploadId,
    config,
    inputs,
  });
}
