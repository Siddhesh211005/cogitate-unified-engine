/**
 * normalize.js — UI display helpers only.
 *
 * Structural normalization (field shapes, API response mapping) has moved
 * to proxy-gateway/adapters.js. This file contains only pure presentation
 * utilities used by React components to format values for display.
 */

// ── Value display helpers ─────────────────────────────────────────────────────

export function formatOutputValue(val) {
  if (val === null || val === undefined || val === "") return "—";
  if (typeof val === "number") {
    if (Number.isInteger(val) && Math.abs(val) < 10000)
      return val.toLocaleString("en-US");
    return val.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    });
  }
  return String(val);
}

export function isFormulaError(val) {
  if (typeof val !== "string") return false;
  return /^#(NAME\?|REF!|VALUE!|N\/A|DIV\/0!|NULL!)$/i.test(val);
}

export function isSkippable(val) {
  if (val === null || val === undefined) return true;
  if (typeof val === "string") {
    const s = val.trim();
    if (s === "" || s === "N/A") return true;
    if (/\b(VLOOKUP|HLOOKUP|INDEX|MATCH|IF|SUM)\s*\(/i.test(s)) return true;
    if (/[A-Za-z0-9_ ]+![A-Z]{1,3}\d{1,6}/i.test(s) && s.length < 80)
      return true;
  }
  return false;
}

export function isPrimaryOutput(name, label) {
  const lower = `${name} ${label}`.toLowerCase();
  return (
    lower.includes("premium") ||
    lower.includes("prem") ||
    lower.includes("annual") ||
    lower.includes("total") ||
    lower.includes("final") ||
    lower.includes("result")
  );
}

export function buildInitialValues(schema) {
  const vals = {};
  for (const inp of schema?.inputs || []) {
    vals[inp.field] = inp.default;
  }
  return vals;
}

/** Slugify a string for use as a rater ID */
export function slugify(str) {
  return String(str || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
