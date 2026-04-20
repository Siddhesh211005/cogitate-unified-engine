# Canonical JSON Schema Specification

> **Purpose**: Defines the exact JSON structure that bridges the Excel parser (backend)  
> to the Dynamic Form (frontend). This is the API contract.

---

## Overview

The `RaterSchema` is the canonical JSON representation of a parsed Excel rater workbook.
It is produced by the backend's `ExcelRaterParser` → `SchemaGenerator` pipeline and consumed
by `DynamicForm`, `AdminRaterWorkspace`, and `ClientRaterWorkspace` to render the UI.

---

## Top-Level Schema

```json
{
  "rater_name": "Homeowners Rater",
  "file_name": "Homeowners Rater.xlsx",
  "version": "1.0.0",
  "sheets": [ ... SheetInfo ... ],
  "input_fields": [ ... RaterField ... ],
  "output_fields": [ ... RaterField ... ],
  "lookup_tables": [ ... LookupTable ... ],
  "formula_mappings": [ ... FormulaMapping ... ],
  "llm_analysis": { ... LLMAnalysisResult or null ... }
}
```

---

## Object Definitions

### SheetInfo
```json
{
  "sheet_name": "Homeowners",
  "role": "input",        // enum: "input" | "lookup" | "calculation" | "output" | "unknown"
  "row_count": 743,
  "col_count": 42,
  "description": ""
}
```

### RaterField (Input)
```json
{
  "name": "Year_Built",
  "label": "Year Built",
  "field_type": "number",   // enum: "text" | "number" | "select" | "date" | "boolean"
  "default_value": 1999,
  "options": [],             // populated for "select" type
  "validation": {
    "min_value": null,
    "max_value": null,
    "required": true,
    "pattern": null
  },
  "sheet": "Homeowners",
  "cell_ref": "$E$6",
  "is_output": false,
  "formula": null,
  "group": "Property Details",
  "order": 1,
  "impacts_output": true
}
```

### RaterField (Output)
```json
{
  "name": "Premium_Total",
  "label": "Premium Total",
  "field_type": "number",
  "default_value": 5678.90,
  "options": [],
  "validation": null,
  "sheet": "Homeowners",
  "cell_ref": "$J$11",
  "is_output": true,
  "formula": "=Y68",
  "group": "Premium Output",
  "order": 0,
  "impacts_output": true
}
```

### RaterField (Select with Options)
```json
{
  "name": "Coverage_type",
  "label": "Coverage Type",
  "field_type": "select",
  "default_value": "Deluxe house/deluxe contents",
  "options": [
    { "label": "Basic house/basic contents", "value": "Basic house/basic contents" },
    { "label": "Deluxe house/basic contents", "value": "Deluxe house/basic contents" },
    { "label": "Deluxe house/deluxe contents", "value": "Deluxe house/deluxe contents" }
  ],
  "validation": { "required": true },
  "sheet": "Homeowners",
  "cell_ref": "$E$10",
  "is_output": false,
  "formula": null,
  "group": "Coverage",
  "order": 3,
  "impacts_output": true
}
```

### LookupTable
```json
{
  "name": "Pick List_table_1",
  "sheet": "Pick List",
  "columns": ["CLASS", "RATE", "Examples"],
  "rows": [
    { "CLASS": "Class I", "RATE": 1, "Examples": "Management Consulting..." },
    { "CLASS": "Class II", "RATE": 1.5, "Examples": "IT Consulting..." },
    { "CLASS": "Class III", "RATE": 2, "Examples": "Medical Billing..." },
    { "CLASS": "Class IV", "RATE": 3, "Examples": "Surveyors..." }
  ],
  "cell_range": "A1:C6"
}
```

### FormulaMapping
```json
{
  "output_name": "Premium_Total",
  "cell_ref": "$J$11",
  "formula": "=Y68",
  "depends_on": []
}
```

```json
{
  "output_name": "Premium_Adjusted",
  "cell_ref": "$J$9",
  "formula": "=Y53",
  "depends_on": ["Year_Built", "Building_limit", "Coverage_type", "Territory"]
}
```

---

## Upload Response

### `POST /api/upload` Response
```json
{
  "rater_id": "a1b2c3d4-e5f6-...",
  "rater_name": "Homeowners Rater",
  "schema": { ... RaterSchema ... },
  "duplicate": false
}
```
`duplicate: true` when a file with the same original filename was already uploaded. `rater_id` points to the existing rater — the frontend navigates to it instead of treating it as new.

---

## Calculation Request/Response

### Request: `POST /api/calculate`
```json
{
  "rater_id": "a1b2c3d4-e5f6-...",
  "inputs": [
    {
      "Year_Built": 2005,
      "Building_limit": 750000,
      "Coverage_type": "Basic house/basic contents",
      "Territory": 5,
      "Base_deductible_factor": 2500,
      "Burglar_alarm": "Yes",
      "Lien_free": "No",
      "Security_protection": "No",
      "Renovation_or_Construction_surcharge": "None"
    }
  ]
}
```
`inputs` is an **array of objects** — most raters use a single object. Multiple objects are merged before calculation.

### Response
```json
{
  "rater_id": "a1b2c3d4-e5f6-...",
  "outputs": {
    "Premium_WindHail": 1456.23,
    "Premium_Wildfire": 892.10,
    "Premium_AllOther": 3421.56,
    "Premium_Adjusted": 5769.89,
    "Premium_Adjustments": -234.50,
    "Premium_Total": 5535.39,
    "Refer": 0,
    "V1": "V1.0.0"
  },
  "warnings": [],
  "refer": false
}
```

### Request: `POST /api/calculate/defaults`
Same as `/api/calculate` but with empty inputs — returns defaults from the workbook.
```json
{
  "rater_id": "a1b2c3d4-e5f6-...",
  "inputs": [{}]
}
```

---

## LLM Analysis Result (optional, stored in schema)

```json
{
  "llm_analysis": {
    "field_classifications": [
      {
        "field_name": "Territory",
        "impacts_premium": true,
        "confidence": 0.98,
        "reasoning": "Referenced by VLOOKUP in premium formula chain",
        "suggested_group": "Rating Factors"
      }
    ],
    "premium_logic_summary": {
      "primary_outputs": ["Premium_Total"],
      "key_drivers": ["Territory", "Building_limit", "Coverage_type"],
      "formula_chain_description": "Inputs feed VLOOKUP rate tables..."
    },
    "dependency_graph": {
      "Premium_Total": {
        "direct_inputs": ["Territory", "Building_limit"],
        "lookup_tables_used": ["rate_table_1"]
      }
    },
    "llm_provider": "google",
    "analyzed": true
  }
}
```

---

## Field Type Inference Rules

| Condition | Inferred Type |
|-----------|--------------|
| Value is `int` or `float` | `number` |
| Value is `bool` | `boolean` |
| Value matches date pattern `YYYY-MM-DD` | `date` |
| Field has `options` populated | `select` |
| Value is "Yes"/"No" only | `select` (with Yes/No options) |
| Everything else (strings) | `text` |

---

## Group Assignment Heuristics

| Label contains | Assigned Group |
|---------------|----------------|
| wildfire, fire, zone, site | Wildfire |
| deductible, ded | Deductible |
| coverage, limit, building | Coverage |
| burglar, alarm, security, lien | Credits & Surcharges |
| renovation, construction, age, year | Property Details |
| premium, rate | Premium |
| (otherwise) | Sheet name or "General" |
