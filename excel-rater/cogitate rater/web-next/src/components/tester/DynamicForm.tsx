"use client";

import { useEffect, useState, type ChangeEvent } from "react";
import type { RaterConfig, InputField } from "@/types/rater";

interface DynamicFormProps {
  config: RaterConfig | null;
  onInputsChange: (inputs: Record<string, unknown>) => void;
}

interface ScheduleRowData {
  [key: string]: string | number | null;
}

export function DynamicForm({ config, onInputsChange }: DynamicFormProps) {
  const [visibleRows, setVisibleRows] = useState<Record<string, number>>({});

  // Initialize visible rows useEffect BEFORE early return (required for React hooks)
  useEffect(() => {
    if (!config) return;
    const isScheduleMode =
      config.mode === "schedule" &&
      Array.isArray(config.schedules) &&
      config.schedules.length > 0;

    const newVisibleRows: Record<string, number> = {};
    if (isScheduleMode && config.schedules) {
      for (const sched of config.schedules) {
        const minRows = Math.max(1, Number(sched.minActiveRows || 1));
        newVisibleRows[sched.key] = minRows;
      }
    }
    setVisibleRows(newVisibleRows);
  }, [config]);

  if (!config) return null;

  const isScheduleMode =
    config.mode === "schedule" &&
    Array.isArray(config.schedules) &&
    config.schedules.length > 0;

  // Build set of schedule cells to exclude
  const scheduleCells = new Set<string>();
  if (isScheduleMode && config.schedules) {
    for (const sched of config.schedules) {
      const rowStart = Number(sched.rowStart || 1);
      const rowEnd = Number(sched.rowEnd || rowStart);
      const cols = sched.columns || [];
      for (let row = rowStart; row <= rowEnd; row++) {
        for (const col of cols) {
          if (col.column) {
            scheduleCells.add(`${col.column}${row}`.toUpperCase());
          }
        }
      }
    }
  }

  // Group inputs by group
  const groups: Record<string, InputField[]> = {};
  for (const inp of config.inputs) {
    if (
      isScheduleMode &&
      inp.cell &&
      scheduleCells.has(String(inp.cell).toUpperCase())
    ) {
      continue;
    }
    const g = inp.group || "General";
    if (!groups[g]) groups[g] = [];
    groups[g].push(inp);
  }

  const collectAllInputs = (): Record<string, unknown> => {
    const data: Record<string, unknown> = {};

    for (const inp of config.inputs) {
      if (
        isScheduleMode &&
        inp.cell &&
        scheduleCells.has(String(inp.cell).toUpperCase())
      ) {
        continue;
      }
      const el = document.getElementById(
        `field-${inp.field}`
      ) as HTMLInputElement | HTMLSelectElement;
      if (!el) continue;
      const isDirty = el.dataset.dirty === "1";
      let val: string | number | null = el.value;
      if (inp.type === "number") {
        val = val === "" ? null : Number(val);
      }

      if (val === "" || val === null) {
        if (!isDirty) {
          continue;
        }
        data[inp.field] = null;
        continue;
      }

      data[inp.field] = val;
    }

    if (isScheduleMode && config.schedules) {
      const schedules: Record<string, ScheduleRowData[]> = {};
      for (const sched of config.schedules) {
        const rowStart = Number(sched.rowStart || 1);
        const rowEnd = Number(sched.rowEnd || rowStart);
        const cols = sched.columns || [];
        const rows: ScheduleRowData[] = [];

        for (let i = 0; i <= rowEnd - rowStart; i++) {
          const rowObj: ScheduleRowData = {};
          let hasAny = false;

          for (const col of cols) {
            const el = document.getElementById(
              `schedule-${sched.key}-${i}-${col.field}`
            ) as HTMLInputElement | HTMLSelectElement;
            if (!el) continue;
            let val: string | number | null = el.value;
            if (col.type === "number") {
              val = val === "" ? null : Number(val);
            }
            if (val !== null && val !== "") hasAny = true;
            rowObj[col.field] = val;
          }

          if (hasAny) {
            rows.push(rowObj);
          }
        }
        schedules[sched.key] = rows;
      }
      data.schedules = schedules;
    }

    return data;
  };

  const handleInputChange = (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    event.currentTarget.dataset.dirty = "1";
    onInputsChange(collectAllInputs());
  };

  return (
    <div className="space-y-6">
      {isScheduleMode && (
        <div className="rounded-md bg-blue-50 p-4 text-sm font-medium text-blue-900">
          Schedule mode enabled: {config.schedules?.length} coverage block(s)
        </div>
      )}

      {Object.entries(groups).map(([groupName, fields]) => (
        <div
          key={groupName}
          className="space-y-3 rounded-lg border border-gray-200 p-4"
        >
          <h3 className="border-b pb-2 text-base font-semibold text-gray-900">
            {groupName}
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
            {fields.map((field) => (
              <label
                key={field.field}
                className="flex flex-col gap-1 text-sm"
              >
                <span className="font-medium text-gray-700">
                  {field.label || field.field}
                </span>
                {field.type === "dropdown" && field.options ? (
                  <select
                    id={`field-${field.field}`}
                    defaultValue={field.default ?? ""}
                    onChange={handleInputChange}
                    className="rounded-md border border-gray-300 bg-white px-2 py-1 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                      <option value="" disabled>Select {field.label || field.field}</option>
                    {field.options.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : field.type === "number" ? (
                  <input
                    id={`field-${field.field}`}
                    type="number"
                    step="any"
                    defaultValue={field.default ?? ""}
                    onChange={handleInputChange}
                    className="rounded-md border border-gray-300 px-2 py-1 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                ) : (
                  <input
                    id={`field-${field.field}`}
                    type="text"
                    defaultValue={field.default ?? ""}
                    onChange={handleInputChange}
                    className="rounded-md border border-gray-300 px-2 py-1 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                )}
              </label>
            ))}
          </div>
        </div>
      ))}

      {isScheduleMode &&
        config.schedules?.map((sched) => {
          const rowStart = Number(sched.rowStart || 1);
          const rowEnd = Number(sched.rowEnd || rowStart);
          const totalRows = Math.max(0, rowEnd - rowStart + 1);
          const minRows = Math.max(1, Number(sched.minActiveRows || 1));
          const visible = visibleRows[sched.key] ?? minRows;

          return (
            <div
              key={sched.key}
              className="space-y-3 rounded-lg border border-gray-200 p-4"
            >
              <h3 className="border-b pb-2 text-base font-semibold text-gray-900">
                {sched.title || sched.key}
              </h3>

              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="bg-gray-50">
                      <th className="border border-gray-300 px-2 py-1 text-left font-semibold">
                        #
                      </th>
                      {sched.columns.map((col) => (
                        <th
                          key={col.field}
                          className="border border-gray-300 px-2 py-1 text-left font-semibold"
                        >
                          {col.label || col.field}{" "}
                          {col.type === "number" ? "($)" : ""}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Array.from({ length: totalRows }).map((_, i) => (
                      <tr
                        key={i}
                        id={`schedule-row-${sched.key}-${i}`}
                        style={{ display: i < visible ? "" : "none" }}
                      >
                        <td className="border border-gray-300 px-2 py-1 text-left">
                          {i + 1}
                        </td>
                        {sched.columns.map((col) => (
                          <td
                            key={col.field}
                            className="border border-gray-300 px-2 py-1"
                          >
                            {col.type === "dropdown" && col.options ? (
                              <select
                                id={`schedule-${sched.key}-${i}-${col.field}`}
                                defaultValue={col.default ?? ""}
                                className="w-full rounded border border-gray-300 px-1 py-0.5 text-sm"
                                onChange={handleInputChange}
                              >
                                <option value="" disabled>Select {col.label || col.field}</option>
                                {col.options.map((opt) => (
                                  <option key={opt} value={opt}>
                                    {opt}
                                  </option>
                                ))}
                              </select>
                            ) : col.type === "number" ? (
                              <input
                                id={`schedule-${sched.key}-${i}-${col.field}`}
                                type="number"
                                step="any"
                                defaultValue={col.default ?? ""}
                                className="w-full rounded border border-gray-300 px-1 py-0.5 text-sm"
                                onChange={handleInputChange}
                              />
                            ) : (
                              <input
                                id={`schedule-${sched.key}-${i}-${col.field}`}
                                type="text"
                                defaultValue={col.default ?? ""}
                                placeholder={`Row ${i + 1}`}
                                className="w-full rounded border border-gray-300 px-1 py-0.5 text-sm"
                                onChange={handleInputChange}
                              />
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setVisibleRows((prev) => ({
                      ...prev,
                      [sched.key]: Math.min(
                        totalRows,
                        (prev[sched.key] ?? minRows) + 1
                      ),
                    }));
                  }}
                  disabled={visible >= totalRows}
                  className="rounded-md bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-400"
                >
                  Add Row
                </button>
                <button
                  onClick={() => {
                    setVisibleRows((prev) => ({
                      ...prev,
                      [sched.key]: minRows,
                    }));
                    for (let i = minRows; i < totalRows; i++) {
                      sched.columns.forEach((col) => {
                        const el = document.getElementById(
                          `schedule-${sched.key}-${i}-${col.field}`
                        ) as HTMLInputElement | HTMLSelectElement;
                        if (el) el.value = "";
                      });
                    }
                  }}
                  disabled={visible <= minRows}
                  className="rounded-md bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-400"
                >
                  Reset Extra Rows
                </button>
              </div>
            </div>
          );
        })}
    </div>
  );
}
