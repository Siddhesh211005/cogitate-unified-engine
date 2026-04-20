import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { RaterMeta } from "../types";
import { listRaters, deleteRater } from "../api";
import FileUpload from "./FileUpload";

export default function AdminDashboard() {
  const navigate = useNavigate();
  const [raters, setRaters] = useState<RaterMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Fetch rater list on mount
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

  useEffect(() => {
    refreshRaters();
  }, [refreshRaters]);

  // Handle upload complete — check for duplicate redirect
  const handleUploaded = useCallback(
    async (raterId: string) => {
      await refreshRaters();
      navigate(`/admin/rater/${raterId}`);
    },
    [navigate, refreshRaters],
  );

  // Handle delete
  const handleDelete = useCallback(
    async (raterId: string, raterName: string) => {
      if (!confirm(`Delete "${raterName}"? This cannot be undone.`)) return;
      setDeleting(raterId);
      try {
        await deleteRater(raterId);
        setRaters((prev) => prev.filter((r) => r.rater_id !== raterId));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setDeleting(null);
      }
    },
    [],
  );

  return (
    <div className="space-y-8">
      {/* Upload section */}
      <div className="space-y-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900 mb-1">
            Upload a Rater
          </h2>
          <p className="text-sm text-gray-500">
            Upload any Excel-based insurance rater (.xlsx). The engine will
            parse its structure, detect inputs/outputs, and generate a dynamic
            form for premium calculation. If a rater with the same filename
            already exists, you'll be redirected to it.
          </p>
        </div>
        <FileUpload onUploaded={handleUploaded} />
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4">
          {error}
          <button
            onClick={() => setError(null)}
            className="ml-3 text-red-500 hover:text-red-700 font-medium"
          >
            ✕
          </button>
        </div>
      )}

      {/* Rater list */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900">
            Uploaded Raters
          </h3>
          <button
            onClick={refreshRaters}
            className="text-sm text-orange-600 hover:text-orange-800 font-medium"
          >
            ↻ Refresh
          </button>
        </div>

        {loading ? (
          <div className="text-center py-12 text-gray-400 animate-pulse">
            Loading raters…
          </div>
        ) : raters.length === 0 ? (
          <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-lg">
            <p className="text-gray-400">
              No raters uploaded yet. Upload your first rater above.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {raters.map((r) => (
              <div
                key={r.rater_id}
                className="bg-white border border-gray-200 rounded-lg shadow-sm hover:shadow-md transition-shadow overflow-hidden"
              >
                <div className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="min-w-0 flex-1">
                      <h4 className="font-semibold text-gray-900 truncate">
                        {r.rater_name || r.original_filename || r.rater_id}
                      </h4>
                      {r.original_filename && (
                        <p className="text-xs text-gray-400 truncate mt-0.5">
                          {r.original_filename}
                        </p>
                      )}
                      {r.uploaded_at && (
                        <p className="text-xs text-gray-400 mt-1">
                          Uploaded{" "}
                          {new Date(r.uploaded_at).toLocaleDateString()}
                        </p>
                      )}
                    </div>
                    <div className="w-2 h-2 rounded-full bg-green-400 flex-shrink-0 mt-2" />
                  </div>
                </div>
                <div className="border-t border-gray-100 px-4 py-3 bg-gray-50 flex items-center justify-between">
                  <button
                    onClick={() => navigate(`/admin/rater/${r.rater_id}`)}
                    className="text-sm text-orange-600 hover:text-orange-800 font-medium"
                  >
                    Open →
                  </button>
                  <button
                    onClick={() =>
                      handleDelete(
                        r.rater_id,
                        r.rater_name || r.original_filename || r.rater_id,
                      )
                    }
                    disabled={deleting === r.rater_id}
                    className="text-sm text-red-400 hover:text-red-600 font-medium disabled:opacity-50"
                  >
                    {deleting === r.rater_id ? "Deleting…" : "Delete"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
