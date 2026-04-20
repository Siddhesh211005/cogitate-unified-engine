import type { RaterField } from "../types";

interface Props {
  field: RaterField;
  value: unknown;
  onChange: (name: string, value: unknown) => void;
}

export default function FormField({ field, value, onChange }: Props) {
  const id = `field-${field.name}`;
  const strVal = value == null ? "" : String(value);

  const baseInput =
    "block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500";

  const renderInput = () => {
    switch (field.field_type) {
      case "select":
        return (
          <select
            id={id}
            className={baseInput}
            value={strVal}
            onChange={(e) => onChange(field.name, e.target.value)}
          >
            <option value="">— Select —</option>
            {field.options.map((o) => (
              <option key={String(o.value)} value={String(o.value)}>
                {o.label}
              </option>
            ))}
          </select>
        );

      case "number":
        return (
          <input
            id={id}
            type="number"
            className={baseInput}
            value={strVal}
            min={field.validation?.min_value ?? undefined}
            max={field.validation?.max_value ?? undefined}
            onChange={(e) =>
              onChange(
                field.name,
                e.target.value === "" ? "" : Number(e.target.value),
              )
            }
          />
        );

      case "boolean":
        return (
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              id={id}
              type="checkbox"
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              checked={
                value === true ||
                value === "Yes" ||
                value === "true" ||
                value === 1
              }
              onChange={(e) => onChange(field.name, e.target.checked)}
            />
            <span className="text-sm text-gray-700">{field.label}</span>
          </label>
        );

      case "date":
        return (
          <input
            id={id}
            type="date"
            className={baseInput}
            value={strVal}
            onChange={(e) => onChange(field.name, e.target.value)}
          />
        );

      default:
        // text
        return (
          <input
            id={id}
            type="text"
            className={baseInput}
            value={strVal}
            onChange={(e) => onChange(field.name, e.target.value)}
          />
        );
    }
  };

  return (
    <div>
      {field.field_type !== "boolean" && (
        <label htmlFor={id} className="block text-sm font-medium text-gray-700 mb-1">
          {field.label}
          {field.validation?.required && (
            <span className="text-red-500 ml-0.5">*</span>
          )}
        </label>
      )}
      {renderInput()}
      {field.validation && (
        <div className="mt-0.5 text-xs text-gray-400">
          {field.validation.min_value != null &&
            field.validation.max_value != null &&
            `Range: ${field.validation.min_value.toLocaleString()} – ${field.validation.max_value.toLocaleString()}`}
        </div>
      )}
    </div>
  );
}
