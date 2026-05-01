/**
 * adapters.js — Normalization layer for the proxy gateway.
 *
 * Converts raw responses from schema-rater (port 5002) and
 * excel-rater (port 5001) into a single canonical shape that the
 * unified frontend consumes.  The frontend never sees engine-specific
 * field names or API shapes.
 */

"use strict";

// ── Helpers ──────────────────────────────────────────────────────────────────

function isSchema(engine) {
  return String(engine || "").toLowerCase() === "schema";
}

function normalizeFieldType(raw) {
  const t = String(raw.field_type || raw.type || "text").toLowerCase();
  return (
    { select: "dropdown", dropdown: "dropdown", boolean: "boolean",
      number: "number", date: "date", text: "text" }[t] || "text"
  );
}

function normalizeOptions(raw) {
  if (!Array.isArray(raw.options)) return [];
  return raw.options.map((opt) => {
    if (opt && typeof opt === "object") {
      return {
        label: String(opt.label ?? opt.value ?? opt),
        value: opt.value ?? opt.label ?? opt,
      };
    }
    return { label: String(opt), value: opt };
  });
}

// ── Rater list ────────────────────────────────────────────────────────────────

function normalizeRaterMeta(raw, engine, source = "raters") {
  if (isSchema(engine)) {
    return {
      id: raw.rater_id || raw.id,
      name: raw.rater_name || raw.original_filename || raw.rater_id,
      filename: raw.original_filename || "",
      uploadedAt: raw.uploaded_at || null,
      status: raw.duplicate ? "duplicate" : "live",
      source,
    };
  }
  const id = raw.slug || raw.rater_id || raw.id || raw.name || "";
  return {
    id,
    name: raw.name || raw.rater_name || id,
    filename: raw.file_name || raw.filename || "",
    uploadedAt: null,
    status: source === "templates" ? "template" : raw.status || "live",
    source,
  };
}

function normalizeRaterList(rawList, engine, source = "raters") {
  if (!Array.isArray(rawList)) return [];
  return rawList.map((r) => normalizeRaterMeta(r, engine, source));
}

// ── Input / output field normalization ───────────────────────────────────────

function normalizeInputField(raw, engine) {
  const type = normalizeFieldType(raw);
  const options = normalizeOptions(raw);
  let defaultVal =
    raw.default_value !== undefined ? raw.default_value : raw.default;
  if (defaultVal == null) {
    if (type === "boolean") defaultVal = false;
    else if (type === "dropdown" && options.length) defaultVal = options[0].value;
    else defaultVal = "";
  }
  if (type === "number" && typeof defaultVal === "string") {
    const parsed = Number(defaultVal);
    if (!isNaN(parsed)) defaultVal = parsed;
  }
  return {
    field: raw.name || raw.field,
    label: raw.label || raw.name || raw.field,
    type,
    options,
    default: defaultVal,
    group: raw.group || "General",
    cellRef: raw.cell_ref || raw.cellRef || raw.cell || "",
    impactsOutput: isSchema(engine) ? raw.impacts_output !== false : true,
    order: typeof raw.order === "number" ? raw.order : 0,
  };
}

function normalizeOutputField(raw, index) {
  return {
    field: raw.name || raw.field,
    label: raw.label || raw.name || raw.field,
    cellRef: raw.cell_ref || raw.cellRef || raw.cell || "",
    isPrimary: Boolean(raw.is_output) || index === 0,
    group: raw.group || "Results",
    order: typeof raw.order === "number" ? raw.order : index,
  };
}

// ── Schema normalization ──────────────────────────────────────────────────────

function normalizeSchema(raw, engine, id) {
  if (!raw) return null;
  const inputSource = raw.input_fields || raw.inputs || [];
  const outputSource = raw.output_fields || raw.outputs || [];
  const inputs = inputSource
    .map((f) => normalizeInputField(f, engine))
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label));
  const outputs = outputSource.map((f, i) => normalizeOutputField(f, i));
  return {
    id: id || raw.rater_id || raw.slug || "",
    name: raw.rater_name || raw.name || id || "",
    filename: raw.file_name || raw.filename || "",
    inputs,
    outputs,
    sheets: raw.sheets || [],
  };
}

// ── Upload response normalization ─────────────────────────────────────────────

function normalizeUploadResponse(raw, engine) {
  if (isSchema(engine)) {
    const schemaRaw = raw.schema || raw.rater_schema || null;
    return {
      type: "complete",
      raterId: raw.rater_id,
      uploadId: raw.rater_id,
      raterName: raw.rater_name,
      filename: raw.original_filename || raw.rater_name || "",
      schema: normalizeSchema(schemaRaw, engine, raw.rater_id),
      duplicate: raw.duplicate || false,
    };
  }
  // Excel: two-step upload — return pending state
  return {
    type: "pending",
    uploadId: raw.upload_id,
    filename: raw.filename,
    schema: normalizeSchema(raw.config, engine, raw.upload_id),
    rawConfig: raw.config,
    warmStatus: raw.warm_status || "disabled",
  };
}

// ── Calculation normalization ─────────────────────────────────────────────────

function normalizeResult(raw, engine) {
  if (!raw) return null;
  const outputs =
    raw.outputs && typeof raw.outputs === "object" ? raw.outputs : {};
  if (isSchema(engine)) {
    return {
      outputs,
      outputMeta: (raw.output_fields_meta || []).map((m) => ({
        name: m.name,
        label: m.label || m.name,
        group: m.group || "Results",
        order: typeof m.order === "number" ? m.order : 0,
        fieldType: m.field_type || "number",
      })),
      warnings: raw.warnings || [],
      refer: raw.refer || false,
    };
  }
  return { outputs, outputMeta: [], warnings: [], refer: false };
}

// ── Request / path builders ───────────────────────────────────────────────────

/**
 * Build the backend URL path + request body for a calculate call.
 * normalizedReq = { modelId, inputs, source? }
 */
function buildCalculateRequest(normalizedReq, engine) {
  const { modelId, inputs = {}, source = "raters" } = normalizedReq;
  if (isSchema(engine)) {
    return {
      url: "/api/calculate",
      body: { rater_id: modelId, inputs: [inputs] },
    };
  }
  const base =
    source === "templates"
      ? `/api/templates/${encodeURIComponent(modelId)}/calculate`
      : `/api/raters/${encodeURIComponent(modelId)}/calculate`;
  return { url: base, body: inputs };
}

function getConfigPath(id, engine, source = "raters") {
  if (isSchema(engine)) return `/api/schema/${encodeURIComponent(id)}`;
  if (source === "templates")
    return `/api/templates/${encodeURIComponent(id)}/config`;
  return `/api/raters/${encodeURIComponent(id)}/config`;
}

function getDeletePath(id, engine) {
  if (isSchema(engine)) return `/api/raters/${encodeURIComponent(id)}`;
  return `/api/admin/raters/${encodeURIComponent(id)}`;
}

function getUploadPath(engine) {
  return isSchema(engine) ? "/api/upload" : "/api/admin/upload";
}

// ── Exports ───────────────────────────────────────────────────────────────────

module.exports = {
  isSchema,
  normalizeRaterList,
  normalizeSchema,
  normalizeResult,
  normalizeUploadResponse,
  buildCalculateRequest,
  getConfigPath,
  getDeletePath,
  getUploadPath,
};
