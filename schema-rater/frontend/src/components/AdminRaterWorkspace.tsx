import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import type { RaterSchema } from "../types";
import { fetchSchema, deleteRater } from "../api";
import RaterWorkspace from "./RaterWorkspace";

export default function AdminRaterWorkspace() {
  const { raterId } = useParams<{ raterId: string }>();
  const navigate = useNavigate();
  const [schema, setSchema] = useState<RaterSchema | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!raterId) return;
    setLoading(true);
    setError(null);
    fetchSchema(raterId)
      .then((s) => {
        setSchema(s);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setLoading(false));
  }, [raterId]);

  const handleDelete = async () => {
    if (!raterId || !schema) return;
    if (!confirm(`Delete "${schema.rater_name}"? This cannot be undone.`))
      return;
    try {
      await deleteRater(raterId);
      navigate("/admin");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (loading) {
    return (
      <div className="text-center py-12 text-gray-500 animate-pulse">
        Loading rater…
      </div>
    );
  }

  if (error || !schema || !raterId) {
    return (
      <div className="space-y-4">
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4">
          {error || "Rater not found"}
        </div>
        <button
          onClick={() => navigate("/admin")}
          className="text-sm text-orange-600 hover:text-orange-800 font-medium"
        >
          ← Back to Dashboard
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Admin controls bar */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate("/admin")}
          className="text-sm text-orange-600 hover:text-orange-800 font-medium flex items-center gap-1"
        >
          ← Back to Dashboard
        </button>
        <button
          onClick={handleDelete}
          className="text-sm text-red-500 hover:text-red-700 font-medium px-3 py-1.5 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
        >
          Delete Rater
        </button>
      </div>

      {/* Reuse existing RaterWorkspace for field selection + form */}
      <RaterWorkspace raterId={raterId} schema={schema} />
    </div>
  );
}
