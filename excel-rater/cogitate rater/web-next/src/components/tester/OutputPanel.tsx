"use client";

import type { RaterConfig } from "@/types/rater";

interface OutputPanelProps {
  config: RaterConfig | null;
  outputs: Record<string, string | number | null> | null;
}

export function OutputPanel({ config, outputs }: OutputPanelProps) {
  if (!config) return null;

  const primary = config.outputs.find((o) => o.primary) || config.outputs[0];
  const secondary = config.outputs.filter((o) => o !== primary);

  const primaryValue = outputs?.[primary.field];
  const displayPrimary =
    primaryValue !== null && primaryValue !== undefined && typeof primaryValue === "number"
      ? "$" + primaryValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : primaryValue ?? "—";

  return (
    <div className="space-y-4 rounded-lg border border-gray-200 bg-gradient-to-br from-blue-50 to-indigo-50 p-6">
      {/* Primary output */}
      <div className="rounded-lg bg-white p-6 shadow-sm">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-600">
          {primary.label}
        </div>
        <div className="text-4xl font-bold text-blue-600">{displayPrimary}</div>
      </div>

      {/* Breakdown table */}
      {secondary.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-gray-100">
                <th className="border border-gray-300 px-3 py-2 text-left font-semibold">Metric</th>
                <th className="border border-gray-300 px-3 py-2 text-right font-semibold">Value</th>
              </tr>
            </thead>
            <tbody>
              {secondary.map((out) => {
                const val = outputs?.[out.field];
                const displayVal =
                  val !== null && val !== undefined
                    ? typeof val === "number"
                      ? parseFloat(val.toFixed(4))
                      : val
                    : "—";

                return (
                  <tr key={out.field} className="hover:bg-gray-50">
                    <td className="border border-gray-300 px-3 py-2">{out.label}</td>
                    <td className="border border-gray-300 px-3 py-2 text-right font-mono">{displayVal}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
