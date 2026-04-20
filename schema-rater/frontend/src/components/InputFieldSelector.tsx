import { useCallback, useMemo, useState } from "react";
import type { RaterField } from "../types";

interface Props {
  fields: RaterField[];
  selectedFields: Set<string>;
  onSelectionChange: (selected: Set<string>) => void;
  onConfirm: () => void;
}

export default function InputFieldSelector({
  fields,
  selectedFields,
  onSelectionChange,
  onConfirm,
}: Props) {
  const [search, setSearch] = useState("");

  // Group fields by their group property
  const grouped = useMemo(() => {
    const map = new Map<string, RaterField[]>();
    for (const f of fields) {
      const group = f.group || "Other";
      if (!map.has(group)) map.set(group, []);
      map.get(group)!.push(f);
    }
    return Array.from(map.entries());
  }, [fields]);

  // Filter by search term
  const filteredGrouped = useMemo(() => {
    if (!search.trim()) return grouped;
    const lower = search.toLowerCase();
    return grouped
      .map(
        ([group, gFields]) =>
          [
            group,
            gFields.filter(
              (f) =>
                f.label.toLowerCase().includes(lower) ||
                f.name.toLowerCase().includes(lower),
            ),
          ] as [string, RaterField[]],
      )
      .filter(([, gFields]) => gFields.length > 0);
  }, [grouped, search]);

  const toggleField = useCallback(
    (name: string) => {
      const next = new Set(selectedFields);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      onSelectionChange(next);
    },
    [selectedFields, onSelectionChange],
  );

  const selectAll = useCallback(() => {
    onSelectionChange(new Set(fields.map((f) => f.name)));
  }, [fields, onSelectionChange]);

  const deselectAll = useCallback(() => {
    onSelectionChange(new Set());
  }, [onSelectionChange]);

  const toggleGroup = useCallback(
    (groupFields: RaterField[]) => {
      const names = groupFields.map((f) => f.name);
      const allSelected = names.every((n) => selectedFields.has(n));
      const next = new Set(selectedFields);
      for (const n of names) {
        if (allSelected) next.delete(n);
        else next.add(n);
      }
      onSelectionChange(next);
    },
    [selectedFields, onSelectionChange],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">
          Select Input Fields to Display
        </h3>
        <span className="text-sm text-gray-500">
          {selectedFields.size} of {fields.length} selected
        </span>
      </div>

      <p className="text-sm text-gray-500">
        Choose which input fields you want to customize on the form. Unselected
        fields will use their default values for calculation.
      </p>

      {/* Search + global actions */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          placeholder="Search fields…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
        <button
          onClick={selectAll}
          className="text-sm text-blue-600 hover:text-blue-800 font-medium whitespace-nowrap"
        >
          Select All
        </button>
        <button
          onClick={deselectAll}
          className="text-sm text-gray-500 hover:text-gray-700 font-medium whitespace-nowrap"
        >
          Deselect All
        </button>
      </div>

      {/* Field groups with checkboxes */}
      <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
        {filteredGrouped.map(([group, gFields]) => {
          const allChecked = gFields.every((f) => selectedFields.has(f.name));
          const someChecked = gFields.some((f) => selectedFields.has(f.name));
          return (
            <fieldset
              key={group}
              className="bg-white border border-gray-200 rounded-lg p-3 shadow-sm"
            >
              <legend className="px-2 text-sm font-semibold text-gray-600 uppercase tracking-wide flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={allChecked}
                  ref={(el) => {
                    if (el) el.indeterminate = someChecked && !allChecked;
                  }}
                  onChange={() => toggleGroup(gFields)}
                  className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                {group}
                <span className="text-xs font-normal text-gray-400">
                  (
                  {gFields.filter((f) => selectedFields.has(f.name)).length}/
                  {gFields.length})
                </span>
              </legend>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 mt-2">
                {gFields.map((f) => (
                  <label
                    key={f.name}
                    className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-gray-50 cursor-pointer text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={selectedFields.has(f.name)}
                      onChange={() => toggleField(f.name)}
                      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-gray-700 truncate" title={f.label}>
                      {f.label}
                    </span>
                    {f.default_value != null &&
                      f.default_value !== "" &&
                      f.default_value !== 0 && (
                        <span className="text-xs text-gray-400 ml-auto flex-shrink-0">
                          = {String(f.default_value).substring(0, 15)}
                        </span>
                      )}
                  </label>
                ))}
              </div>
            </fieldset>
          );
        })}
      </div>

      {/* Confirm button */}
      <div className="flex items-center justify-between pt-2 border-t border-gray-200">
        <p className="text-xs text-gray-400">
          {selectedFields.size === 0
            ? "No fields selected — all fields will use defaults"
            : `${selectedFields.size} field${selectedFields.size !== 1 ? "s" : ""} will be shown on the form`}
        </p>
        <button
          onClick={onConfirm}
          className="px-6 py-2.5 bg-blue-600 text-white font-semibold rounded-lg shadow hover:bg-blue-700 transition-colors"
        >
          {selectedFields.size === 0
            ? "Calculate with Defaults"
            : "Show Form & Calculate"}
        </button>
      </div>
    </div>
  );
}
