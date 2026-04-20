"use client";

import type { SourceType } from "@/types/rater";

export type { SourceType };

interface SourceSelectorProps {
  value: SourceType;
  onChange: (source: SourceType) => void;
}

export function SourceSelector({ value, onChange }: SourceSelectorProps) {
  return (
    <div className="flex flex-wrap items-center gap-4">
      <label htmlFor="source-select" className="font-medium">
        Source
      </label>
      <select
        id="source-select"
        value={value}
        onChange={(e) => onChange(e.target.value as SourceType)}
        className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
      >
        <option value="raters">apps/raters/</option>
        <option value="templates">apps/templates/</option>
      </select>
      <p className="text-xs text-gray-600">
        Tip: Newly approved raters are saved under <code>apps/raters/</code>
      </p>
    </div>
  );
}

