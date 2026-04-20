import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CalculationResult, RaterField, RaterSchema } from "../types";
import { calculate, calculateDefaults } from "../api";
import FormField from "./FormField";
import PremiumResults from "./PremiumResults";

interface Props {
  raterId: string;
  schema: RaterSchema;
  visibleFields?: string[];
}

/**
 * Determine if a field should be shown as a rating input.
 * Uses the backend-provided `impacts_output` flag (preferred),
 * with a fallback heuristic for older schemas.
 */
function isRatingInput(field: RaterField): boolean {
  // Backend marks fields that truly affect premium calculation
  return field.impacts_output !== false;
}

export default function DynamicForm({ raterId, schema, visibleFields }: Props) {
  // ── State ──────────────────────────────────────────────────────────
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [result, setResult] = useState<CalculationResult | null>(null);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // AbortController to cancel in-flight requests — prevents race conditions
  // where a slow response arrives after a newer request
  const abortRef = useRef<AbortController | null>(null);

  // ── Drag-and-drop: group overrides ─────────────────────────────────
  // Maps field name → overridden group name (only for fields the user moved)
  const [groupOverrides, setGroupOverrides] = useState<Record<string, string>>({});
  const [draggedField, setDraggedField] = useState<string | null>(null);
  const [dropTargetGroup, setDropTargetGroup] = useState<string | null>(null);

  // Reset overrides when schema/rater changes
  useEffect(() => {
    setGroupOverrides({});
  }, [raterId, schema]);

  // ── Split fields: rating inputs vs info-only ───────────────────────
  const { ratingFields, infoFields, grouped } = useMemo(() => {
    const rating: RaterField[] = [];
    const info: RaterField[] = [];
    for (const f of schema.input_fields) {
      // If visibleFields is set, skip fields not in the list
      if (visibleFields && !visibleFields.includes(f.name)) continue;
      if (isRatingInput(f)) rating.push(f);
      else info.push(f);
    }
    // Group rating fields — use overrides if user dragged a field
    const map = new Map<string, RaterField[]>();
    for (const f of rating) {
      const group = groupOverrides[f.name] || f.group || "Rating Inputs";
      if (!map.has(group)) map.set(group, []);
      map.get(group)!.push(f);
    }
    return {
      ratingFields: rating,
      infoFields: info,
      grouped: Array.from(map.entries()),
    };
  }, [schema, groupOverrides, visibleFields]);

  // ── Drag-and-drop handlers ─────────────────────────────────────────
  const handleDragStart = useCallback((fieldName: string) => {
    setDraggedField(fieldName);
  }, []);

  const handleDragEnd = useCallback(() => {
    setDraggedField(null);
    setDropTargetGroup(null);
  }, []);

  const handleDragOverGroup = useCallback(
    (e: React.DragEvent, groupName: string) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      setDropTargetGroup(groupName);
    },
    [],
  );

  const handleDragLeaveGroup = useCallback(() => {
    setDropTargetGroup(null);
  }, []);

  const handleDropOnGroup = useCallback(
    (e: React.DragEvent, groupName: string) => {
      e.preventDefault();
      setDropTargetGroup(null);
      if (draggedField) {
        setGroupOverrides((prev) => ({ ...prev, [draggedField]: groupName }));
        setDraggedField(null);
      }
    },
    [draggedField],
  );

  const handleResetLayout = useCallback(() => {
    setGroupOverrides({});
  }, []);

  // ── Initialise form values from defaults ───────────────────────────
  useEffect(() => {
    const defaults: Record<string, unknown> = {};
    for (const f of schema.input_fields) {
      defaults[f.name] = f.default_value ?? "";
    }
    setValues(defaults);
    setResult(null);

    // Cancel any in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    // Calculate with defaults to show initial premium
    setCalculating(true);
    calculateDefaults(raterId, controller.signal)
      .then((r) => {
        if (!controller.signal.aborted) {
          setResult(r);
          setError(null);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          if (e instanceof DOMException && e.name === "AbortError") return;
          setError(e.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setCalculating(false);
      });
  }, [raterId, schema]);

  // ── Auto-recalculate on input change (debounced) ───────────────────
  const doCalculate = useCallback(
    (vals: Record<string, unknown>) => {
      // Cancel any in-flight request
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setCalculating(true);
      setError(null);
      calculate({ rater_id: raterId, inputs: [vals] }, controller.signal)
        .then((r) => {
          if (!controller.signal.aborted) {
            setResult(r);
            setError(null);
          }
        })
        .catch((e: unknown) => {
          if (controller.signal.aborted) return;
          if (e instanceof DOMException && e.name === "AbortError") return;
          setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (!controller.signal.aborted) setCalculating(false);
        });
    },
    [raterId],
  );

  const handleChange = useCallback(
    (name: string, value: unknown) => {
      setValues((prev) => {
        const next = { ...prev, [name]: value };
        // Debounce recalculation
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => doCalculate(next), 600);
        return next;
      });
    },
    [doCalculate],
  );

  const handleCalculateNow = () => doCalculate(values);

  // ── Render ─────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">
            {schema.rater_name}
          </h2>
          <p className="text-sm text-gray-500">
            {ratingFields.length} rating inputs ·{" "}
            {schema.output_fields.length} outputs
            {infoFields.length > 0 &&
              ` · ${infoFields.length} info fields hidden`}
          </p>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
          {error}
        </div>
      )}

      {/* === SPLIT LAYOUT: Inputs LEFT | Outputs RIGHT === */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">
        {/* LEFT: Rating Inputs (3/5 width) */}
        <div className="lg:col-span-3 space-y-4">
          {/* Reset layout button (shown when any fields have been moved) */}
          {Object.keys(groupOverrides).length > 0 && (
            <div className="flex justify-end">
              <button
                className="text-xs text-gray-400 hover:text-blue-600 underline"
                onClick={handleResetLayout}
              >
                Reset field layout
              </button>
            </div>
          )}

          {grouped.map(([group, fields]) => (
            <fieldset
              key={group}
              className={`bg-white border rounded-lg p-4 shadow-sm transition-colors duration-150 ${
                dropTargetGroup === group && draggedField
                  ? "border-blue-400 bg-blue-50/40 ring-2 ring-blue-200"
                  : "border-gray-200"
              }`}
              onDragOver={(e) => handleDragOverGroup(e, group)}
              onDragLeave={handleDragLeaveGroup}
              onDrop={(e) => handleDropOnGroup(e, group)}
            >
              <legend className="px-2 text-sm font-semibold text-gray-600 uppercase tracking-wide">
                {group}
              </legend>
              {dropTargetGroup === group && draggedField && (
                <div className="text-xs text-blue-500 mb-2 font-medium">
                  Drop here to move field into this section
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-2">
                {fields.map((f) => (
                  <div
                    key={f.name}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.effectAllowed = "move";
                      e.dataTransfer.setData("text/plain", f.name);
                      handleDragStart(f.name);
                    }}
                    onDragEnd={handleDragEnd}
                    className={`cursor-grab active:cursor-grabbing rounded-md transition-all duration-150 ${
                      draggedField === f.name
                        ? "opacity-40 scale-95"
                        : "hover:ring-1 hover:ring-gray-300"
                    } ${
                      groupOverrides[f.name]
                        ? "ring-1 ring-blue-200 bg-blue-50/30"
                        : ""
                    }`}
                    title="Drag to move to another section"
                  >
                    <div className="flex items-start gap-1">
                      <span className="mt-2 text-gray-300 hover:text-gray-500 select-none text-xs flex-shrink-0">
                        ⠿
                      </span>
                      <div className="flex-1 min-w-0">
                        <FormField
                          field={f}
                          value={values[f.name]}
                          onChange={handleChange}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </fieldset>
          ))}

          {/* Calculate button */}
          <button
            className="w-full py-3 px-4 bg-blue-600 text-white font-semibold rounded-lg shadow hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            onClick={handleCalculateNow}
            disabled={calculating}
          >
            {calculating ? "Calculating…" : "Recalculate Premium"}
          </button>

          {/* Collapsed info fields section */}
          {infoFields.length > 0 && (
            <details className="bg-gray-50 border border-gray-200 rounded-lg p-3">
              <summary className="text-sm text-gray-500 cursor-pointer hover:text-gray-700 font-medium">
                {infoFields.length} informational fields (do not affect premium)
              </summary>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3 pt-3 border-t border-gray-200">
                {infoFields.map((f) => (
                  <FormField
                    key={f.name}
                    field={f}
                    value={values[f.name]}
                    onChange={handleChange}
                  />
                ))}
              </div>
            </details>
          )}
        </div>

        {/* RIGHT: Premium Output Panel (2/5 width, sticky) */}
        <div className="lg:col-span-2 lg:sticky lg:top-6">
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
              Calculated Premium
            </h3>

            {result ? (
              <PremiumResults
                outputs={result.outputs}
                outputFieldsMeta={result.output_fields_meta ?? []}
                warnings={result.warnings}
                refer={result.refer}
                calculating={calculating}
              />
            ) : (
              <div className="text-center py-8 text-gray-400 text-sm">
                {calculating
                  ? "Computing initial premium…"
                  : "Adjust inputs to calculate premium"}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
