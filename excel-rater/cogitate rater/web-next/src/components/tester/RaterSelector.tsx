"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api-client";
import type { RaterInfo, SourceType } from "@/types/rater";

interface RaterSelectorProps {
  source: SourceType;
  value: string;
  onChange: (slug: string) => void;
  onLoad: (raters: RaterInfo[]) => void;
  isLoading?: boolean;
}

export function RaterSelector({
  source,
  value,
  onChange,
  onLoad,
  isLoading = false,
}: RaterSelectorProps) {
  const [raters, setRaters] = useState<RaterInfo[]>([]);
  const [loading, setLoading] = useState(isLoading);
  const [error, setError] = useState<string | null>(null);

  // Load rater list when source changes
  useEffect(() => {
    async function fetchRaters() {
      setLoading(true);
      setError(null);
      try {
        const list = await apiGet<RaterInfo[]>(`/api/${source}`);
        setRaters(list || []);
        onLoad(list || []);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(`Failed to load ${source}: ${message}`);
        setRaters([]);
      } finally {
        setLoading(false);
      }
    }

    fetchRaters();
  }, [source, onLoad]);

  return (
    <div className="flex items-center gap-4">
      <label htmlFor="rater-select" className="font-medium">
        Rater
      </label>
      <select
        id="rater-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={loading}
        className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:bg-gray-100 disabled:text-gray-500"
      >
        <option value="">
          {loading ? "Loading..." : raters.length === 0 ? "No raters found" : "-- select a rater --"}
        </option>
        {raters.map((rater) => (
          <option key={rater.slug} value={rater.slug}>
            {rater.name || rater.slug}
          </option>
        ))}
      </select>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
