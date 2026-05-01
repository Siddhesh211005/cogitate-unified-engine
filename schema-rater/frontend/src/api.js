/**
 * api.js — Unified API client for Cogitate Rater Engine
 * Supports excel-rater (port 8001) and schema-rater (port 8000) via the proxy gateway.
 * All requests go through the Vite dev proxy → gateway (8080) → correct backend.
 */

const MAX_RETRIES = 2
const RETRY_DELAYS_MS = [1000, 2500]

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function fetchWithRetry(url, init = {}, retries = MAX_RETRIES) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, init)
      if (res.status >= 500 && res.status <= 504 && attempt < retries) {
        await sleep(RETRY_DELAYS_MS[attempt] ?? 4000)
        continue
      }
      return res
    } catch {
      if (attempt < retries) {
        await sleep(RETRY_DELAYS_MS[attempt] ?? 4000)
        continue
      }
      throw new Error('Unable to reach the backend. Please ensure all services are running.')
    }
  }
}

async function handleResponse(res) {
  if (res.status === 204) return null
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = body?.detail || body?.message || `HTTP ${res.status}`
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return body
}

async function apiGet(path) {
  const res = await fetchWithRetry(`/api${path}`)
  return handleResponse(res)
}

async function apiPost(path, data) {
  const res = await fetchWithRetry(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

async function apiPostForm(path, formData) {
  const res = await fetchWithRetry(`/api${path}`, {
    method: 'POST',
    body: formData,
  })
  return handleResponse(res)
}

async function apiDelete(path) {
  const res = await fetchWithRetry(`/api${path}`, { method: 'DELETE' })
  return handleResponse(res)
}

// ── Engine detection ──────────────────────────────────────────────────────
let _engineCache = null

export async function getEngine() {
  if (_engineCache !== null) return _engineCache
  try {
    const res = await fetch('/gateway/current')
    if (!res.ok) { _engineCache = null; return null }
    const data = await res.json()
    _engineCache = data?.selected || null
    return _engineCache
  } catch {
    _engineCache = null
    return null
  }
}

export function clearEngineCache() {
  _engineCache = null
}

export function isSchemaEngine(engine) {
  return String(engine || '').toLowerCase() === 'schema'
}

// ── Health ────────────────────────────────────────────────────────────────
export function getHealth() {
  return apiGet('/health')
}

// ── Rater listing ─────────────────────────────────────────────────────────
export function listRaters() {
  return apiGet('/raters')
}

export function listTemplates(engine) {
  if (isSchemaEngine(engine)) return Promise.resolve([])
  return apiGet('/templates')
}

// ── Schema / Config ───────────────────────────────────────────────────────
export function getRaterConfig(id, engine) {
  if (isSchemaEngine(engine)) return apiGet(`/schema/${encodeURIComponent(id)}`)
  return apiGet(`/raters/${encodeURIComponent(id)}/config`)
}

export function getTemplateConfig(id, engine) {
  if (isSchemaEngine(engine)) return getRaterConfig(id, engine)
  return apiGet(`/templates/${encodeURIComponent(id)}/config`)
}

// ── Upload ────────────────────────────────────────────────────────────────
/**
 * Step 1: Upload file.
 * - Schema-rater: single step, returns { rater_id, rater_name, schema, duplicate }
 * - Excel-rater:  first of two steps, returns { upload_id, filename, config, warm_status }
 */
export function uploadFile(file, engine) {
  const form = new FormData()
  form.append('file', file)
  const path = isSchemaEngine(engine) ? '/upload' : '/admin/upload'
  return apiPostForm(path, form)
}

/**
 * Step 2: Persist the uploaded rater metadata.
 */
export function saveUploadedRater({ uploadId, config, slug, name, description, source = 'raters' }) {
  return apiPost('/admin/save', {
    upload_id: uploadId,
    config,
    slug,
    name,
    description,
    source,
  })
}

// ── Delete ────────────────────────────────────────────────────────────────
export function deleteRater(id, engine) {
  const path = isSchemaEngine(engine)
    ? `/raters/${encodeURIComponent(id)}`
    : `/admin/raters/${encodeURIComponent(id)}`
  return apiDelete(path)
}

// ── Calculate ─────────────────────────────────────────────────────────────
export function calculateRater(id, inputs, engine) {
  if (isSchemaEngine(engine)) {
    return apiPost('/calculate', { rater_id: id, inputs: [inputs] })
  }
  return apiPost(`/raters/${encodeURIComponent(id)}/calculate`, inputs)
}

export function calculateTemplate(id, inputs, engine) {
  if (isSchemaEngine(engine)) return calculateRater(id, inputs, engine)
  return apiPost(`/templates/${encodeURIComponent(id)}/calculate`, inputs)
}

export function calculateDefaults(id, engine) {
  return calculateRater(id, {}, engine)
}
