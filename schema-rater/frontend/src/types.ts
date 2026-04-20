/** TypeScript types matching the backend Pydantic models. */

export type FieldType = "text" | "number" | "select" | "date" | "boolean";

export interface ValidationRule {
  min_value?: number | null;
  max_value?: number | null;
  required: boolean;
  pattern?: string | null;
}

export interface FieldOption {
  label: string;
  value: unknown;
}

export interface RaterField {
  name: string;
  label: string;
  field_type: FieldType;
  default_value: unknown;
  options: FieldOption[];
  validation?: ValidationRule | null;
  sheet: string;
  cell_ref: string;
  is_output: boolean;
  formula?: string | null;
  group: string;
  order: number;
  impacts_output: boolean;
}

export interface SheetInfo {
  sheet_name: string;
  role: string;
  row_count: number;
  col_count: number;
  description: string;
}

export interface LookupTable {
  name: string;
  sheet: string;
  columns: string[];
  rows: Record<string, unknown>[];
  cell_range: string;
}

export interface FormulaMapping {
  output_name: string;
  cell_ref: string;
  formula: string;
  depends_on: string[];
}

export interface LLMFieldClassification {
  field_name: string;
  impacts_premium: boolean;
  confidence: number;
  reasoning: string;
  suggested_group: string;
}

export interface LLMAnalysisResult {
  field_classifications: LLMFieldClassification[];
  premium_logic_summary: Record<string, unknown>;
  dependency_graph: Record<string, unknown>;
  llm_provider: string;
  analyzed: boolean;
}

export interface RaterSchema {
  rater_name: string;
  file_name: string;
  version: string;
  sheets: SheetInfo[];
  input_fields: RaterField[];
  output_fields: RaterField[];
  lookup_tables: LookupTable[];
  formula_mappings: FormulaMapping[];
  llm_analysis?: LLMAnalysisResult | null;
}

export interface UploadResponse {
  rater_id: string;
  rater_name: string;
  schema: RaterSchema;
  duplicate?: boolean;
}

export interface CalculationRequest {
  rater_id: string;
  inputs: Record<string, unknown>[];
}

export interface OutputFieldMeta {
  name: string;
  label: string;
  group: string;
  order: number;
  field_type: string;
}

export interface CalculationResult {
  rater_id: string;
  outputs: Record<string, unknown>;
  output_fields_meta: OutputFieldMeta[];
  warnings: string[];
  refer: boolean;
}

export interface RaterMeta {
  rater_id: string;
  rater_name?: string;
  original_filename?: string;
  uploaded_at?: string;
}
