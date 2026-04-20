import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { RaterMeta } from "../types";
import { listRaters } from "../api";

export default function ClientDashboard() {
  const navigate = useNavigate();
  const [raters, setRaters] = useState<RaterMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshRaters = useCallback(async () => {
    try {
      const list = await listRaters();
      setRaters(list);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    refreshRaters();
  }, [refreshRaters]);

  // Auto-refresh every 15 seconds to pick up admin-added raters
  useEffect(() => {
    const interval = setInterval(refreshRaters, 15000);
    return () => clearInterval(interval);
  }, [refreshRaters]);

  // Also refresh on window focus
  useEffect(() => {
    const onFocus = () => refreshRaters();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshRaters]);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-gray-900">
          Available Raters
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          Select a rater to calculate premiums. New raters added by admin will
          appear here automatically.
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4">
          {error}
        </div>
      )}

      {/* Rater list */}
      {loading ? (
        <div className="text-center py-16 text-gray-400 animate-pulse">
          Loading available raters…
        </div>
      ) : raters.length === 0 ? (
        <div className="text-center py-16 border-2 border-dashed border-gray-200 rounded-lg">
          <div className="text-4xl mb-4">📋</div>
          <p className="text-gray-500 font-medium">
            No raters available yet
          </p>
          <p className="text-sm text-gray-400 mt-1">
            Please ask your admin to upload rater workbooks.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {raters.map((r) => (
            <button
              key={r.rater_id}
              onClick={() => navigate(`/client/rater/${r.rater_id}`)}
              className="group text-left bg-white border border-gray-200 rounded-xl shadow-sm hover:shadow-lg hover:border-blue-300 transition-all duration-200 overflow-hidden"
            >
              <div className="p-5">
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">
                    <h4 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors truncate text-lg">
                      {r.rater_name || r.original_filename || r.rater_id}
                    </h4>
                    {r.original_filename && (
                      <p className="text-xs text-gray-400 truncate mt-1">
                        📄 {r.original_filename}
                      </p>
                    )}
                    {r.uploaded_at && (
                      <p className="text-xs text-gray-400 mt-1.5">
                        Added {new Date(r.uploaded_at).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                  <span className="text-blue-500 text-sm font-medium flex-shrink-0 ml-3 group-hover:translate-x-1 transition-transform">
                    Open →
                  </span>
                </div>
              </div>
              <div className="h-1 bg-gradient-to-r from-blue-500 to-blue-600 opacity-0 group-hover:opacity-100 transition-opacity" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
