import type { OutputFieldMeta } from "../types";

interface Props {
  outputs: Record<string, unknown>;
  outputFieldsMeta: OutputFieldMeta[];
  warnings: string[];
  refer: boolean;
  calculating?: boolean;
}

// ── Helpers ──────────────────────────────────────────────────────────────

/** Values that represent formula evaluation errors. */
function isErrorValue(val: unknown): boolean {
  if (typeof val !== "string") return false;
  return /^#(NAME\?|REF!|VALUE!|N\/A|DIV\/0!|NULL!)$/i.test(val);
}

/** True if the value looks like an unresolved formula / cell reference string. */
function isFormulaString(val: unknown): boolean {
  if (typeof val !== "string") return false;
  const s = val.trim();
  if (
    /\b(VLOOKUP|HLOOKUP|INDEX|MATCH|IF|SUM|SUMIF|COUNTIF|AVERAGE|MIN|MAX|LEFT|RIGHT|MID|ROUND|IFERROR|AND|OR|NOT|TRIM|CONCATENATE|CHOOSE|OFFSET|INDIRECT|LOOKUP|TEXT|VALUE)\s*\(/i.test(
      s,
    )
  )
    return true;
  if (/^[A-Z]{1,3}\d{1,6}\s*[\*\+\-\/\^]\s*[A-Z]{1,3}\d{1,6}/i.test(s))
    return true;
  if (/[A-Za-z0-9_ ]+![A-Z]{1,3}\d{1,6}/i.test(s) && s.length < 80)
    return true;
  return false;
}

/** Values that are not useful for display. */
function isSkippableValue(val: unknown): boolean {
  if (val === null || val === undefined) return true;
  if (isFormulaString(val)) return true;
  if (typeof val === "string") {
    const s = val.trim();
    if (s === "" || s === "N/A") return true;
    if (/^v\d/i.test(s)) return true;
  }
  return false;
}

/** Format a label for display — strip numeric prefixes and clean up. */
function formatLabel(label: string): string {
  return label
    .replace(/^\d+[\s_]+/, "") // strip leading "01_", "02 ", etc.
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

/**
 * Format a numeric value with appropriate precision.
 * - Rates (small numbers): show 2-4 decimals, no currency symbol
 * - Dollar/currency amounts: show with 2 decimals and currency symbol
 * - Integers: show without decimals
 */
function formatValue(val: unknown): string {
  if (isErrorValue(val)) return String(val);
  if (typeof val === "number") {
    // Integer values (terms, ages, counts) — no decimals
    if (Number.isInteger(val) && Math.abs(val) < 1000) {
      return val.toLocaleString("en-US");
    }
    // Small decimal values likely rates/factors — show with precision
    if (Math.abs(val) < 100 && val !== Math.floor(val)) {
      return val.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 4,
      });
    }
    // Larger values — formatted number with 2 decimals (no currency symbol)
    return val.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  return String(val ?? "—");
}

/** Clean up group names for display. */
function formatGroupName(group: string): string {
  return group
    .replace(/^Xreport_/i, "")
    .replace(/_/g, " ");
}

/** True when the name/label looks like a primary premium output. */
function isPrimaryOutput(name: string, label: string): boolean {
  const lower = (name + " " + label).toLowerCase();
  return (
    lower.includes("premium") ||
    lower.includes("prem") ||
    lower.includes("annual") ||
    lower.includes("modal") ||
    lower.includes("rate") ||
    lower.includes("discount")
  );
}

// ── Component ────────────────────────────────────────────────────────────

export default function PremiumResults({
  outputs,
  outputFieldsMeta,
  warnings,
  refer,
  calculating,
}: Props) {
  // Build display entries using metadata for proper labels, grouping, ordering
  const metaByName = new Map(
    (outputFieldsMeta ?? []).map((m) => [m.name, m]),
  );

  type DisplayEntry = {
    key: string;
    label: string;
    value: unknown;
    group: string;
    order: number;
    isPrimary: boolean;
  };

  const entries: DisplayEntry[] = [];

  // First, add all outputs that have metadata (preserves schema ordering)
  for (const meta of outputFieldsMeta ?? []) {
    const val = outputs[meta.name];
    if (isSkippableValue(val)) continue;
    entries.push({
      key: meta.name,
      label: formatLabel(meta.label),
      value: val,
      group: meta.group,
      order: meta.order,
      isPrimary: isPrimaryOutput(meta.name, meta.label),
    });
  }

  // Then add any outputs NOT in metadata (legacy/extra outputs)
  for (const [key, val] of Object.entries(outputs)) {
    if (metaByName.has(key)) continue;
    if (isSkippableValue(val)) continue;
    entries.push({
      key,
      label: formatLabel(key.replace(/_/g, " ")),
      value: val,
      group: "Other",
      order: 999,
      isPrimary: isPrimaryOutput(key, key),
    });
  }

  // Sort by order
  entries.sort((a, b) => a.order - b.order);

  // Group entries by their group
  const groupedEntries = new Map<string, DisplayEntry[]>();
  for (const entry of entries) {
    if (!groupedEntries.has(entry.group)) {
      groupedEntries.set(entry.group, []);
    }
    groupedEntries.get(entry.group)!.push(entry);
  }

  const hasErrors = entries.some((e) => isErrorValue(e.value));
  const totalOutputs = Object.keys(outputs).length;
  const skippedCount = totalOutputs - entries.length;

  // Check if all premium-related outputs are zero
  const primaryEntries = entries.filter((e) => e.isPrimary);
  const allPremiumsZero =
    primaryEntries.length > 0 &&
    primaryEntries.every(
      (e) =>
        e.value === 0 ||
        e.value === "$0" ||
        e.value === "0" ||
        e.value === null,
    );

  if (entries.length === 0 && !calculating) {
    return (
      <p className="text-center py-6 text-gray-400 text-sm">
        No outputs available.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {calculating && (
        <div className="text-center py-3 text-blue-600 text-sm animate-pulse font-medium">
          Recalculating…
        </div>
      )}

      {/* ── Zero premium warning ────────────────────────────────────── */}
      {allPremiumsZero && !calculating && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-amber-800 text-xs">
          <p className="font-semibold mb-1">All premium outputs are $0</p>
          <p>
            This may indicate that required input fields are empty or that the
            calculation engine couldn't resolve some formula dependencies. Try
            filling in all required fields (marked with{" "}
            <span className="text-red-500">*</span>).
          </p>
        </div>
      )}

      {/* ── Skipped outputs notice ──────────────────────────────────── */}
      {skippedCount > 3 && !calculating && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-2 text-gray-500 text-xs">
          {skippedCount} outputs could not be computed (formula dependencies
          unresolved).
        </div>
      )}

      {/* ── Output groups ───────────────────────────────────────────── */}
      {Array.from(groupedEntries.entries()).map(([group, groupItems]) => (
        <div
          key={group}
          className="overflow-hidden rounded-lg border border-gray-200 shadow-sm"
        >
          {/* Group header */}
          {groupedEntries.size > 1 && (
            <div className="bg-gray-50 border-b border-gray-200 px-4 py-2">
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                {formatGroupName(group)}
              </h4>
            </div>
          )}

          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-4 py-2.5 font-semibold text-gray-600">
                  Output
                </th>
                <th className="text-right px-4 py-2.5 font-semibold text-gray-600">
                  Value
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {groupItems.map((entry) => {
                const err = isErrorValue(entry.value);
                return (
                  <tr
                    key={entry.key}
                    className={
                      entry.isPrimary
                        ? err
                          ? "bg-blue-50/40"
                          : "bg-blue-50/60 font-medium"
                        : err
                          ? "bg-red-50/40"
                          : "bg-white"
                    }
                  >
                    <td className="px-4 py-2.5 text-gray-700">
                      {entry.label}
                    </td>
                    <td
                      className={`px-4 py-2.5 text-right tabular-nums ${
                        err
                          ? "text-red-400 italic"
                          : entry.isPrimary
                            ? "text-gray-900 font-semibold"
                            : "text-gray-700"
                      }`}
                    >
                      {formatValue(entry.value)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}

      {hasErrors && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-amber-800 text-xs">
          Some outputs show formula errors (e.g.&nbsp;<code>#NAME?</code>).
          This means the workbook uses Excel functions not supported by the
          calculation engine. These values are correct in the original
          spreadsheet.
        </div>
      )}

      {refer && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-amber-800 text-sm font-medium">
          This risk requires manual referral.
        </div>
      )}

      {warnings.length > 0 && (
        <details className="text-xs">
          <summary className="text-gray-400 cursor-pointer hover:text-gray-600">
            {warnings.length} calculation note{warnings.length > 1 ? "s" : ""}
          </summary>
          <div className="mt-1 space-y-0.5 pl-3">
            {warnings.map((w, i) => (
              <p key={i} className="text-amber-500">
                {w}
              </p>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
