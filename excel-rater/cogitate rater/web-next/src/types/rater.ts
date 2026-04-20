/**
 * Rater Configuration Types
 * Defines the structure of rater configs loaded from API
 */

export type SourceType = "raters" | "templates";
export type InputType = "text" | "number" | "dropdown";

export interface InputField {
  field: string;
  label: string;
  type: InputType;
  default?: string | number | null;
  group?: string;
  cell?: string; // Excel cell reference
  options?: (string | number)[]; // For dropdowns
}

export interface OutputField {
  field: string;
  label: string;
  cell?: string; // Excel cell reference
  primary?: boolean;
}

export interface ScheduleColumn {
  field: string;
  label: string;
  type?: InputType;
  default?: string | number | null;
  options?: (string | number)[];
  column?: string; // Excel column letter(s)
}

export interface Schedule {
  key: string;
  title: string;
  rowStart: number;
  rowEnd: number;
  minActiveRows?: number;
  columns: ScheduleColumn[];
}

export interface RaterConfig {
  slug: string;
  name: string;
  description?: string;
  mode?: "flat" | "schedule"; // "flat" = simple inputs, "schedule" = repeating rows
  inputs: InputField[];
  outputs: OutputField[];
  schedules?: Schedule[]; // Only present if mode === "schedule"
}

export interface RaterInfo {
  slug: string;
  name: string;
  description?: string;
}

export interface CalculateRequest {
  [key: string]: string | number | null | Record<string, string | number | null>[] | Record<string, Record<string, string | number | null>[]>;
}

export interface CalculateResponse {
  outputs: Record<string, string | number | null>;
}

export type WarmState = "disabled" | "warming" | "ready" | "failed" | "expired" | "missing" | "unknown" | "fallback-cold";

export interface WarmStatus {
  state: WarmState;
  message?: string;
}

export interface AdminUploadResponse {
  upload_id: string;
  filename: string;
  config: RaterConfig;
  warm?: WarmStatus;
  warm_status?: WarmState;
  warm_message?: string;
}

export interface WarmStatusResponse {
  upload_id: string;
  state: WarmState;
  error?: string | null;
  active_operation?: string | null;
  created_at?: string | null;
  last_used_at?: string | null;
}

export interface AdminCalculateResponse extends CalculateResponse {
  status: "success";
  warm_used?: boolean;
  warm_state?: WarmState;
  timings?: Record<string, number>;
}
