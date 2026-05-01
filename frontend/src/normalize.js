/**
 * normalize.js — Canonical data format layer
 * Converts raw API responses from excel-rater and schema-rater backends
 * into a single canonical format consumed by all UI components.
 * No engine-specific branching in the components themselves.
 */

export function isSchemaEngine(engine) {
  return String(engine || '').toLowerCase() === 'schema'
}

// ── Slug helper ───────────────────────────────────────────────────────────
export function slugify(str) {
  return String(str || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

// ── Rater Meta ────────────────────────────────────────────────────────────
/**
 * Canonical: { id, name, filename, uploadedAt, status, source, engine }
 * Excel raw: { slug, name, status, description, file_name }
 * Schema raw: { rater_id, rater_name, original_filename, uploaded_at }
 */
export function normalizeRaterMeta(raw, engine, source = 'raters') {
  if (!raw) return null
  if (isSchemaEngine(engine)) {
    return {
      id: raw.rater_id || raw.id,
      name: raw.rater_name || raw.original_filename || raw.rater_id,
      filename: raw.original_filename || '',
      uploadedAt: raw.uploaded_at || null,
      status: raw.duplicate ? 'duplicate' : 'live',
      source,
      engine,
    }
  }
  const id = raw.slug || raw.rater_id || raw.id || raw.name || ''
  return {
    id,
    name: raw.name || raw.rater_name || id,
    filename: raw.file_name || raw.filename || '',
    uploadedAt: null,
    status: source === 'templates' ? 'template' : (raw.status || 'live'),
    source,
    engine,
  }
}

// ── Input / Output Field Normalization ────────────────────────────────────
function normalizeFieldType(raw, engine) {
  const raw_type = String(raw.field_type || raw.type || 'text').toLowerCase()
  const map = {
    select: 'dropdown', dropdown: 'dropdown',
    boolean: 'boolean',
    number: 'number',
    date: 'date',
    text: 'text',
  }
  return map[raw_type] || 'text'
}

function normalizeOptions(raw) {
  if (!Array.isArray(raw.options)) return []
  return raw.options.map((opt) => {
    if (opt && typeof opt === 'object') {
      return { label: String(opt.label ?? opt.value ?? opt), value: opt.value ?? opt.label ?? opt }
    }
    return { label: String(opt), value: opt }
  })
}

/**
 * Canonical input field: { field, label, type, options, default, group, cellRef, impactsOutput, order }
 */
export function normalizeInputField(raw, engine) {
  const type = normalizeFieldType(raw, engine)
  const options = normalizeOptions(raw)
  let defaultVal = raw.default_value
  if (defaultVal === undefined || defaultVal === null) {
    if (raw.default !== undefined && raw.default !== null) defaultVal = raw.default
    if (type === 'boolean') defaultVal = false
    else if (type === 'dropdown' && options.length) defaultVal = options[0].value
    else defaultVal = ''
  }
  if (type === 'number' && typeof defaultVal === 'string') {
    const parsed = Number(defaultVal)
    if (!Number.isNaN(parsed)) defaultVal = parsed
  }
  if (type === 'dropdown' && options.length) {
    const match = options.find((opt) => String(opt.value) === String(defaultVal))
    if (match) defaultVal = match.value
  }
  return {
    field: raw.name || raw.field,
    label: raw.label || raw.name || raw.field,
    type,
    options,
    default: defaultVal,
    group: raw.group || 'General',
    cellRef: raw.cell_ref || raw.cellRef || raw.cell || '',
    impactsOutput: isSchemaEngine(engine) ? raw.impacts_output !== false : true,
    order: typeof raw.order === 'number' ? raw.order : 0,
  }
}

function normalizeOutputField(raw, index) {
  return {
    field: raw.name || raw.field,
    label: raw.label || raw.name || raw.field,
    cellRef: raw.cell_ref || raw.cellRef || raw.cell || '',
    isPrimary: Boolean(raw.is_output) || index === 0,
    group: raw.group || 'Results',
    order: typeof raw.order === 'number' ? raw.order : index,
  }
}

/**
 * Canonical schema: { id, name, filename, inputs, outputs, sheets, engine }
 * Excel config.json and Schema-rater RaterSchema both map to this.
 */
export function normalizeSchema(raw, engine, id) {
  if (!raw) return null
  const inputSource = raw.input_fields || raw.inputs || []
  const outputSource = raw.output_fields || raw.outputs || []
  const inputs = inputSource
    .map((f) => normalizeInputField(f, engine))
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label))
  const outputs = outputSource.map((f, i) => normalizeOutputField(f, i))
  return {
    id: id || raw.rater_id || raw.slug || '',
    name: raw.rater_name || raw.name || id || '',
    filename: raw.file_name || raw.filename || '',
    inputs,
    outputs,
    sheets: raw.sheets || [],
    engine,
  }
}

// ── Upload response normalization ─────────────────────────────────────────
/**
 * Canonical upload response:
 *   type='complete' → { raterId, raterName, schema, duplicate }   (schema-rater)
 *   type='pending'  → { uploadId, filename, schema, warmStatus }  (excel-rater, needs save step)
 */
export function normalizeUploadResponse(raw, engine) {
  if (isSchemaEngine(engine)) {
    const schemaRaw = raw.schema || raw.rater_schema || null
    return {
      type: 'complete',
      raterId: raw.rater_id,
      uploadId: raw.rater_id,
      raterName: raw.rater_name,
      filename: raw.original_filename || raw.file_name || schemaRaw?.filename || raw.rater_name || '',
      rawConfig: schemaRaw,
      schema: normalizeSchema(schemaRaw, engine, raw.rater_id),
      duplicate: raw.duplicate || false,
    }
  }
  return {
    type: 'pending',
    uploadId: raw.upload_id,
    filename: raw.filename,
    rawConfig: raw.config,
    schema: normalizeSchema(raw.config, engine, raw.upload_id),
    warmStatus: raw.warm_status || 'disabled',
  }
}

// ── Calculation result normalization ──────────────────────────────────────
/**
 * Canonical result: { outputs, outputMeta, warnings, refer }
 * Excel: { status, outputs: {field: value} }
 * Schema: { rater_id, outputs, output_fields_meta, warnings, refer }
 */
export function normalizeResult(raw, engine) {
  if (!raw) return null
  const outputs = (raw.outputs && typeof raw.outputs === 'object') ? raw.outputs : {}
  if (isSchemaEngine(engine)) {
    return {
      outputs,
      outputMeta: (raw.output_fields_meta || []).map((m) => ({
        name: m.name,
        label: m.label || m.name,
        group: m.group || 'Results',
        order: typeof m.order === 'number' ? m.order : 0,
        fieldType: m.field_type || 'number',
      })),
      warnings: raw.warnings || [],
      refer: raw.refer || false,
    }
  }
  return { outputs, outputMeta: [], warnings: [], refer: false }
}

// ── Value display helpers ─────────────────────────────────────────────────
export function formatOutputValue(val) {
  if (val === null || val === undefined || val === '') return '—'
  if (typeof val === 'number') {
    if (Number.isInteger(val) && Math.abs(val) < 10000) return val.toLocaleString('en-US')
    return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
  }
  return String(val)
}

export function isFormulaError(val) {
  if (typeof val !== 'string') return false
  return /^#(NAME\?|REF!|VALUE!|N\/A|DIV\/0!|NULL!)$/i.test(val)
}

export function isSkippable(val) {
  if (val === null || val === undefined) return true
  if (typeof val === 'string') {
    const s = val.trim()
    if (s === '' || s === 'N/A') return true
    if (/\b(VLOOKUP|HLOOKUP|INDEX|MATCH|IF|SUM)\s*\(/i.test(s)) return true
    if (/[A-Za-z0-9_ ]+![A-Z]{1,3}\d{1,6}/i.test(s) && s.length < 80) return true
  }
  return false
}

export function isPrimaryOutput(name, label) {
  const lower = `${name} ${label}`.toLowerCase()
  return (
    lower.includes('premium') || lower.includes('prem') ||
    lower.includes('annual') || lower.includes('total') ||
    lower.includes('final') || lower.includes('result')
  )
}

export function buildInitialValues(schema) {
  const vals = {}
  for (const inp of schema?.inputs || []) {
    vals[inp.field] = inp.default
  }
  return vals
}
