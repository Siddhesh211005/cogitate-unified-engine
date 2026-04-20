import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import type { CalculationResult, RaterSchema } from "../types";
import { fetchSchema, calculateDefaults } from "../api";
import DynamicForm from "./DynamicForm";
import InputFieldSelector from "./InputFieldSelector";
import PremiumResults from "./PremiumResults";

export default function ClientRaterWorkspace() {
  const { raterId } = useParams<{ raterId: string }>();
  const navigate = useNavigate();
  const [schema, setSchema] = useState<RaterSchema | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Field selection state
  const [showFieldSelector, setShowFieldSelector] = useState(false);
  const [selectedFields, setSelectedFields] = useState<Set<string> | null>(
    null,
  );
  const [fieldSelectionConfirmed, setFieldSelectionConfirmed] = useState(false);

  // Initial premium
  const [initialResult, setInitialResult] = useState<CalculationResult | null>(
    null,
  );
  const [calcError, setCalcError] = useState<string | null>(null);
  const [calculating, setCalculating] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Fetch schema
  useEffect(() => {
    if (!raterId) return;
    setLoading(true);
    setError(null);
    setFieldSelectionConfirmed(false);
    setShowFieldSelector(false);

    fetchSchema(raterId)
      .then((s) => {
        setSchema(s);
        setSelectedFields(new Set(s.input_fields.map((f) => f.name)));
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [raterId]);

  // Calculate defaults once schema is loaded
  useEffect(() => {
    if (!raterId || !schema) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setCalculating(true);
    setCalcError(null);
    calculateDefaults(raterId, controller.signal)
      .then((r) => {
        if (!controller.signal.aborted) setInitialResult(r);
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          if (e instanceof DOMException && e.name === "AbortError") return;
          setCalcError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setCalculating(false);
      });

    return () => controller.abort();
  }, [raterId, schema]);

  const handleConfirmFieldSelection = useCallback(() => {
    setFieldSelectionConfirmed(true);
    setShowFieldSelector(false);
  }, []);

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
          onClick={() => navigate("/client")}
          className="text-sm text-blue-600 hover:text-blue-800 font-medium"
        >
          ← Back to Rater List
        </button>
      </div>
    );
  }

  // Determine visible fields for DynamicForm
  const visibleFields =
    fieldSelectionConfirmed && selectedFields
      ? selectedFields.size === schema.input_fields.length
        ? undefined
        : Array.from(selectedFields)
      : undefined;

  return (
    <div className="space-y-4">
      {/* Top bar: back + field selector toggle */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate("/client")}
          className="text-sm text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
        >
          ← Back to Rater List
        </button>
        <button
          onClick={() => setShowFieldSelector(!showFieldSelector)}
          className={`text-sm font-medium px-3 py-1.5 rounded-lg border transition-colors flex items-center gap-1.5 ${
            showFieldSelector
              ? "bg-blue-50 border-blue-300 text-blue-700"
              : "border-gray-200 text-gray-600 hover:border-blue-300 hover:text-blue-600"
          }`}
        >
          <span className="text-xs">⚙</span>
          Customize Fields
        </button>
      </div>

      {/* Rater info */}
      <div>
        <h2 className="text-xl font-bold text-gray-900">
          {schema.rater_name}
        </h2>
        <p className="text-sm text-gray-500">
          {schema.input_fields.length} inputs ·{" "}
          {schema.output_fields.length} outputs
        </p>
      </div>

      {/* Field selector panel (togglable) */}
      {showFieldSelector && selectedFields && (
        <div className="border border-blue-200 rounded-lg bg-blue-50/30 p-4">
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">
            <div className="lg:col-span-3">
              <InputFieldSelector
                fields={schema.input_fields}
                selectedFields={selectedFields}
                onSelectionChange={setSelectedFields}
                onConfirm={handleConfirmFieldSelection}
              />
            </div>
            <div className="lg:col-span-2 lg:sticky lg:top-6">
              <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
                  Initial Premium (Default Values)
                </h3>
                {initialResult ? (
                  <PremiumResults
                    outputs={initialResult.outputs}
                    outputFieldsMeta={initialResult.output_fields_meta ?? []}
                    warnings={initialResult.warnings}
                    refer={initialResult.refer}
                    calculating={calculating}
                  />
                ) : (
                  <div className="text-center py-8 text-gray-400 text-sm">
                    {calculating
                      ? "Computing initial premium…"
                      : calcError
                        ? `⚠ ${calcError}`
                        : "Could not compute initial premium"}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main form */}
      <DynamicForm
        raterId={raterId}
        schema={schema}
        visibleFields={visibleFields}
      />
    </div>
  );
}
