import { useEffect, useState } from "react";
import type { RaterMeta } from "../types";
import { listRaters } from "../api";

interface Props {
  onSelect: (raterId: string) => void;
  refreshKey: number;
}

export default function RaterSelector({ onSelect, refreshKey }: Props) {
  const [raters, setRaters] = useState<RaterMeta[]>([]);

  useEffect(() => {
    listRaters().then(setRaters).catch(() => {});
  }, [refreshKey]);

  if (raters.length === 0) return null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4">
      <h3 className="text-sm font-semibold text-gray-600 mb-2">
        Previously Uploaded Raters
      </h3>
      <div className="space-y-2">
        {raters.map((r) => (
          <button
            key={r.rater_id}
            className="w-full text-left px-3 py-2 rounded-md text-sm hover:bg-blue-50 border border-gray-100 transition-colors"
            onClick={() => onSelect(r.rater_id)}
          >
            <span className="font-medium text-gray-800">
              {r.rater_name ?? r.original_filename ?? r.rater_id}
            </span>
            {r.uploaded_at && (
              <span className="text-xs text-gray-400 ml-2">
                {new Date(r.uploaded_at).toLocaleDateString()}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
