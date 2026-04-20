import { useCallback, useEffect, useRef, useState } from "react";
import type { CalculationResult, RaterSchema } from "../types";
import { calculateDefaults } from "../api";
import DynamicForm from "./DynamicForm";
import InputFieldSelector from "./InputFieldSelector";
import PremiumResults from "./PremiumResults";

interface Props {
  raterId: string;
  schema: RaterSchema;
}

type Phase = "selecting" | "form";

/**
 * Orchestrates the two-phase rater workflow:
 *   1. "selecting" — show checkbox field selector + initial premium (defaults)
 *   2. "form"      — show DynamicForm with only selected fields + live results
 */
export default function RaterWorkspace({ raterId, schema }: Props) {
  const [phase, setPhase] = useState<Phase>("selecting");
  const [selectedFields, setSelectedFields] = useState<Set<string>>(
    () => new Set(schema.input_fields.map((f) => f.name)),
  );
  const [initialResult, setInitialResult] = useState<CalculationResult | null>(
    null,
  );
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Calculate with defaults on mount
  useEffect(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setCalculating(true);
    setError(null);
    calculateDefaults(raterId, controller.signal)
      .then((r) => {
        if (!controller.signal.aborted) {
          setInitialResult(r);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          if (e instanceof DOMException && e.name === "AbortError") return;
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setCalculating(false);
      });

    return () => controller.abort();
  }, [raterId]);

  // Reset phase when rater/schema changes
  useEffect(() => {
    setPhase("selecting");
    setSelectedFields(new Set(schema.input_fields.map((f) => f.name)));
  }, [raterId, schema]);

  const handleConfirmSelection = useCallback(() => {
    setPhase("form");
  }, []);

  const handleBackToSelection = useCallback(() => {
    setPhase("selecting");
  }, []);

  // ── Phase 1: Field selection + initial results ──
  if (phase === "selecting") {
    return (
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h2 className="text-xl font-bold text-gray-900">
            {schema.rater_name}
          </h2>
          <p className="text-sm text-gray-500">
            {schema.input_fields.length} inputs ·{" "}
            {schema.output_fields.length} outputs
          </p>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
            {error}
          </div>
        )}

        {/* Two-column: checkboxes left, initial results right */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">
          <div className="lg:col-span-3">
            <InputFieldSelector
              fields={schema.input_fields}
              selectedFields={selectedFields}
              onSelectionChange={setSelectedFields}
              onConfirm={handleConfirmSelection}
            />
          </div>

          <div className="lg:col-span-2 lg:sticky lg:top-6">
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 shadow-sm">
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
                    : "Could not compute initial premium"}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Phase 2: Form with selected fields ──
  return (
    <div className="space-y-4">
      <button
        onClick={handleBackToSelection}
        className="text-sm text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
      >
        ← Back to field selection
      </button>

      <DynamicForm
        raterId={raterId}
        schema={schema}
        visibleFields={
          selectedFields.size === schema.input_fields.length
            ? undefined
            : Array.from(selectedFields)
        }
      />
    </div>
  );
}
