# LangChain Integration — Design, Flow & Assessment

> **Purpose**: Full design document for integrating LangChain into the Cogitate Rater Engine.  
> Covers the proposed data flow, architecture, guardrails, benefits, and honest risks.
>
> **Architecture Strategy — Parse-Time-Only Approach**: LangChain is used **only at upload
> time** to extract accurate formulas, logic, and input fields. After that, all 
> runtime calculation and dynamic input/output handling uses plain deterministic
> API calls with zero LLM involvement.
**Implementation Summary**: Both LLM layers are fully integrated
and merged. Layer 1 (`llm_analyzer.py`) runs field classification. Layer 2
(`llm_chain.py`) runs the 3-step chain: output classification → dependency
graph → formula translation. Both run in a background thread after upload.
Runtime execution of translated formulas uses `formula_runtime.py` (AST-safe,
no `eval`/`exec`).
---

## 1. Heuristic Parsing System Flow

```
Excel Upload
    │
    ▼
ExcelRaterParser (openpyxl)          ← Regex + heuristic extraction
    │  - Named ranges (Xinput_/Xoutput_)
    │  - Label/value cell pairs
    │  - Lookup tables
    │  - Formula dependency graph
    ▼
SchemaGenerator                      ← Rule-based enrichment
    │  - Enrich options from lookup tables
    │  - Boundary conditions (hardcoded min/max)
    │  - Yes/No field detection
    │  - Group assignment (keyword matching)
    │  - Impact analysis (formula deps + heuristic exclusion)
    ▼
RaterSchema JSON                     ← Stored to disk
    │
    ▼
Frontend renders Dynamic Form
    │
    ▼ (user changes inputs)
CalculationEngine (formulas lib)     ← Deterministic Excel formula eval
    │
    ▼
Premium Outputs
```

### What heuristic extraction does well:
- **Deterministic extraction**: Regex + openpyxl reliably finds named ranges, data validations
- **Formula-based calculation**: The `formulas` library evaluates actual Excel formulas — no guessing
- **Impact analysis**: Formula dependency graph + heuristic keywords mark non-impacting fields

### Where heuristic extraction is limited:
- **Field classification is regex-only**: Keywords like "address", "phone" are hardcoded in
  `_INFO_NAME_KEYWORDS`. If a new rater uses different naming, fields get misclassified.
- **Sheet role detection is keyword-only**: `_detect_sheet_role()` checks for words like "input",
  "output", "calc" in sheet names. A sheet named "Pricing" or "Module 1" gets tagged UNKNOWN.
- **Formula dependency extraction is shallow**: `_extract_formula_mappings()` uses a simple
  regex `r"[A-Z]{1,3}\$?\d+"` to find cell refs in formulas. It misses cross-sheet refs
  like `'Rate Table'!B:B` and structured references.
- **No sensitivity data**: We know a field "impacts output" (boolean) but not HOW MUCH.
- **Boundary conditions are hardcoded**: Min/max for Age, SumAssured, etc. are literal
  dicts in `SchemaGenerator._apply_boundary_conditions()`.

---

## 2. LLM-Enhanced Approach — Parse-Time Only

### Core Insight

> **If the initial extraction of formulas, logic, and input fields is
> accurate, every downstream system is trivial.** The hard problem is
> parsing, not calculating.

The `formulas` library already does perfect deterministic calculation.
The `CalculationEngine` already handles runtime input → output. The
weakness is in the **extraction** step — knowing WHICH cells matter,
WHICH fields affect premium, and HOW they connect.

### Implemented Flow

```
Excel Upload
    │
    ▼
Phase 1: ExcelRaterParser (openpyxl)  — mechanical extraction
    │  Produces raw data:
    │  - All named ranges with values & formulas
    │  - All label/value cell pairs from input sheets
    │  - All data tables from lookup sheets
    │  - All formulas from output sheets
    │
    ▼
Phase 2: SchemaGenerator (heuristic enrichment)
    │  - Options from lookup tables
    │  - Yes/No field detection
    │  - Group assignment, impact analysis
    │
    ▼
Return { rater_id, schema } immediately  ← FAST RESPONSE

    [Background thread]
    │
    ▼
Phase 3: Layer 1 — LLMSchemaAnalyzer   — ONE-TIME at upload
    │  Receives the raw parsed data (NOT the Excel file directly)
    │  
    │  ┌─────────────────────────────────────────────────────┐
    │  │  GUARDRAILS                                         │
    │  │  • Input: only the parsed schema data               │
    │  │  • No internet, no external APIs, no web search     │
    │  │  • No arbitrary file access                         │
    │  │  • Structured JSON output (Pydantic-validated)      │
    │  └─────────────────────────────────────────────────────┘
    │
    │  LLM analyzes the raw data to produce:
    │  ✅ Accurate input field classification (rating vs informational)
    │  ✅ Correct formula dependency graph (cross-sheet aware)
    │  ✅ Validated boundary conditions from actual cell data
    │  ✅ Field groupings based on semantic understanding
    │  ✅ Confidence scores for each classification
    │
    ▼
Phase 4: Layer 2 — LLM Chain (if CHAIN_ENABLED)
    │  Step 1: Classify outputs as final/intermediate/display
    │  Step 2: Build input → output dependency graph
    │  Step 3: Translate unsupported formulas to Python expressions
    │          (validated against workbook defaults, stored in calculation_metadata.json)
    │
    ▼
RaterSchema JSON + calculation_metadata.json  ← Stored to disk (enriched)
    │
    ▼
═══════════════════════════════════════════════════════════════════
    FROM THIS POINT: NO LLM. Pure deterministic API calls.
═══════════════════════════════════════════════════════════════════
    │
    ▼
Frontend renders Dynamic Form
    │
    ▼ (user changes inputs)
CalculationEngine (formulas lib) → Python VLOOKUP fallback
    → LLM-translated formula fallback (formula_runtime.py, AST-safe)
    → Cached value fallback
    │
    ▼
Premium Outputs
```

---

## 3. What the LLM Does at Parse-Time (Detailed)

The LLM receives a **structured summary** of the raw parsed data and
returns **structured JSON**. It never sees the raw Excel binary.

### 3.1 Input: What Gets Sent to the LLM

```json
{
  "rater_name": "Homeowners Rater",
  "sheets": [
    { "name": "Rater", "role": "unknown", "rows": 150, "cols": 12 },
    { "name": "Pick Lists", "role": "lookup", "rows": 400, "cols": 8 }
  ],
  "raw_fields": [
    {
      "name": "Territory",
      "label": "Territory",
      "cell_ref": "E6",
      "sheet": "Rater",
      "default_value": 1,
      "has_formula": false,
      "has_data_validation": true,
      "validation_options": ["1","2","3","4","5"],
      "referenced_by_formulas": ["=VLOOKUP(E6,'Pick Lists'!A:B,2,0)"]
    },
    {
      "name": "Name_of_Insured",
      "label": "Name of Insured",
      "cell_ref": "E4",
      "sheet": "Rater",
      "default_value": "John Doe",
      "has_formula": false,
      "has_data_validation": false,
      "validation_options": [],
      "referenced_by_formulas": []
    }
  ],
  "output_formulas": [
    {
      "name": "Base_Premium",
      "cell_ref": "E50",
      "formula": "=E45*E46*(1+E47)",
      "computed_value": 12500
    }
  ],
  "formula_cell_references": {
    "E50": ["E45", "E46", "E47"],
    "E45": ["E6", "E8", "E10"]
  }
}
```

### 3.2 Output: What the LLM Returns

```json
{
  "field_classifications": [
    {
      "field_name": "Territory",
      "impacts_premium": true,
      "confidence": 0.98,
      "reasoning": "Referenced by VLOOKUP in E45 which feeds into Base_Premium formula. Territory directly determines the base rate multiplier.",
      "suggested_group": "Rating Factors",
      "suggested_validation": { "required": true, "min": 1, "max": 5 }
    },
    {
      "field_name": "Name_of_Insured",
      "impacts_premium": false,
      "confidence": 0.99,
      "reasoning": "Not referenced by any formula. Pure informational field for policy identification.",
      "suggested_group": "Insured Information",
      "suggested_validation": { "required": false }
    }
  ],
  "premium_logic_summary": {
    "primary_output": "Base_Premium (E50)",
    "formula_chain": "E50 = E45 * E46 * (1 + E47), where E45 = base rate from Territory lookup, E46 = building limit factor, E47 = deductible credit",
    "key_drivers": ["Territory", "Building_limit", "Deductible"]
  },
  "dependency_graph": {
    "Base_Premium": {
      "direct_inputs": ["Territory", "Building_limit", "Deductible"],
      "intermediate_cells": ["E45", "E46", "E47"],
      "lookup_tables_used": ["Pick Lists table 1 (Territory → Rate)"]
    }
  }
}
```

### 3.3 How LLM Results Are Applied

The upload router separates fast heuristic parsing (synchronous, returned immediately)
from LLM enrichment (background thread, non-blocking):

```python
# In routers/upload.py — actual implementation:

@router.post("/upload")
async def upload_rater(file):
    # Fast path — heuristics only, returned immediately
    schema = generator.generate(wb_path, use_llm=False)
    store.save_schema(rater_id, schema)
    
    # Background: LLM enrichment + model preload (non-blocking)
    def _background_work():
        generator.run_llm_enrichment(schema, wb_path)
        store.save_schema(rater_id, schema)   # re-save enriched
        engine.load_model(rater_id, wb_path)
    threading.Thread(target=_background_work, daemon=True).start()
    
    return UploadResponse(rater_id=rater_id, rater_name=..., rater_schema=schema)

# In SchemaGenerator.run_llm_enrichment():

def run_llm_enrichment(self, schema, wb_path):
    # Layer 1 — single structured LLM call
    if LLM_ENABLED:
        llm_results = llm_analyzer.analyze(schema)
        self._merge_llm_results(schema, llm_results)
        # LLM overrides heuristics only when confidence ≥ 0.8

    # Layer 2 — 3-step LLM chain
    if CHAIN_ENABLED:
        chain_result = llm_chain.run(schema, wb_path)
        metadata = _build_calculation_metadata(chain_result)
        _save_calculation_metadata(rater_id, metadata)
```

**Critical**: If the LLM is unavailable (no API key, network error, etc.),
the system falls back to the existing heuristic pipeline — zero degradation.

---

## 4. Why This Is Better Than Full LangChain Runtime

| Aspect | Full Runtime LLM | Parse-Time Only LLM |
|--------|-----------------|---------------------|
| **LLM calls per session** | Every calculation, every question | **Once per rater upload** |
| **Cost** | $0.01-0.05 per interaction | **$0.01-0.03 per upload, then $0** |
| **Latency** | 2-10s added to every request | **0ms added at runtime** |
| **Determinism** | Non-deterministic at runtime | **Fully deterministic at runtime** |
| **Hallucination risk** | Every response could hallucinate | **Only during parse; validated before storing** |
| **Offline capability** | Needs LLM access always | **Works offline after upload** |
| **Complexity** | Agent loop, tool orchestration | **Single structured LLM call** |
| **Failure mode** | LLM down = features broken | **LLM down = fallback to heuristics** |

---

## 5. Guardrail Architecture

### 5.1 Input Guardrails (What Goes TO the LLM)

```python
class InputGuardrail:
    """Ensure only parsed rater data reaches the LLM."""

    def sanitize(self, raw_schema: RaterSchema) -> dict:
        # Convert to structured summary (see §3.1)
        # Strip any file paths, user data, PII
        # Limit token count (truncate large lookup tables)
        # Never send raw Excel bytes
        return sanitized_summary
```

### 5.2 Output Guardrails (What Comes FROM the LLM)

```python
class OutputGuardrail:
    """Validate LLM classifications against actual rater data."""

    def validate(self, llm_result: dict, schema: RaterSchema) -> dict:
        validated = {}
        for classification in llm_result["field_classifications"]:
            field_name = classification["field_name"]

            # 1. Field must actually exist in the parsed schema
            if field_name not in known_fields:
                continue  # LLM hallucinated a field name

            # 2. If LLM says "impacts_premium=True", verify field IS
            #    referenced by at least one formula (trust but verify)
            if classification["impacts_premium"]:
                if not field_has_any_formula_reference(field_name):
                    classification["confidence"] *= 0.5  # downgrade

            # 3. Confidence threshold: only accept if > 0.8
            if classification["confidence"] < 0.8:
                continue  # fall back to heuristic

            validated[field_name] = classification

        return validated
```

### 5.3 System Prompt Guardrails

```python
PARSE_TIME_SYSTEM_PROMPT = """You are an Excel workbook structure analyzer
for insurance rater spreadsheets.

You will receive a structured JSON summary of fields, formulas, and cell
references extracted from an Excel workbook.

YOUR TASK: Classify each field and trace the premium calculation logic.

STRICT RULES:
1. Base ALL classifications on the provided data ONLY.
2. Do NOT use any external knowledge about insurance pricing.
3. If a field's purpose is ambiguous from the data, set confidence < 0.5.
4. Every claim must map to a specific cell reference or formula.
5. Return ONLY valid JSON matching the required output schema.
6. Do NOT invent field names that aren't in the input data.
"""
```

---

## 6. Process Flow — Complete Upload Pipeline

```
User uploads "Homeowners Rater.xlsx"
    │
    ▼
POST /api/upload
    │
    ├─► RaterStore.save_rater()           — save .xlsx to disk
    │
    ├─► ExcelRaterParser.extract()        — openpyxl extraction (fast, heuristic)
    │     → raw RaterSchema with fields, formulas, lookups
    │
    ├─► SchemaGenerator.generate(use_llm=False)  — heuristic enrichment
    │
    ├─► RaterStore.save_schema()          — persist initial schema
    │
    └─► Return { rater_id, rater_name, schema }   ← FAST RESPONSE HERE

    [Background thread — non-blocking]
    │
    ├─► Layer 1: LLMSchemaAnalyzer.analyze()   — ONE LLM call
    │     │
    │     ├─ InputGuardrail.sanitize()    — strip to structured summary
    │     ├─ LLM call (structured output) — classify fields, trace logic
    │     ├─ OutputGuardrail.validate()   — verify against raw schema
    │     └─ Merge into schema (confidence ≥ 0.8 only)
    │
    ├─► Layer 2: LLMChain.run() (if CHAIN_ENABLED)
    │     │
    │     ├─ Step 1: classify outputs → final/intermediate/display
    │     ├─ Step 2: build input→output dependency graph
    │     ├─ Step 3: translate unsupported formulas to Python
    │     └─ Save → calculation_metadata.json
    │
    ├─► RaterStore.save_schema()          — persist enriched schema
    │
    └─► CalculationEngine.load_model()    — precompile Excel model

═══════════════════════════════════════════════════════════════
    ALL SUBSEQUENT REQUESTS — NO LLM, PLAIN API CALLS:
═══════════════════════════════════════════════════════════════
    │
    ├─► GET  /api/schema/{id}           — return stored schema
    ├─► POST /api/calculate             — deterministic formula eval
    │         formulas library → if fails → formula_runtime.py (translated Python)
    └─► POST /api/calculate/defaults    — deterministic defaults
```

---

## 7. Runtime: No LLM, Just Better Data

Because the LLM produced a higher-quality schema at upload time, the
existing runtime systems automatically work better:

### 7.1 Better `impacts_output` Flags
- **Heuristic-only**: Heuristic keyword matching misses edge cases. A field named
  "Premium_Frequency" might be marked `impacts_output=False` because
  "frequency" isn't in the keyword list.
- **LLM-enhanced**: LLM traces formula refs and sees that `Premium_Frequency`
  feeds into cell E48 which feeds into `Final_Premium`. Correctly marked `True`.
- **Runtime benefit**: Form shows the right fields. Zero extra cost.

### 7.2 Better Field Groups
- **Heuristic-only**: `_enrich_groups()` uses keyword matching. "Falcon Score"
  → "Layer Structure" (because "falcon" matches). Might be wrong.
- **LLM-enhanced**: LLM sees this field feeds into a credit/debit modifier
  formula. Groups it under "Risk Modifiers" with confidence 0.92.
- **Runtime benefit**: Better organized UI. Zero extra cost.

### 7.3 Better Boundary Conditions
- **Heuristic-only**: Hardcoded dict: `"Age": (18, 80)`. Doesn't adapt to raters
  with different age ranges.
- **LLM-enhanced**: LLM reads the lookup table and sees the rate table covers
  ages 25-70. Sets `min=25, max=70`.
- **Runtime benefit**: Better form validation. Zero extra cost.

### 7.4 Dependency Graph for Sensitivity
- **Heuristic-only**: Shallow regex finds same-sheet refs only.
- **LLM-enhanced**: LLM traces full chain: `Territory → VLOOKUP → E45 → E50`.
  Stored as `premium_logic_summary` in schema JSON.
- **Runtime benefit**: Frontend can show "this field affects premium"
  tooltips. Sensitivity analysis can use the graph. Zero LLM cost.

---

## 8. New Files & Modules

```
backend/app/
├── services/
│   ├── llm_analyzer.py           # Layer 1: LLM-powered schema analysis (parse-time)
│   ├── llm_chain.py              # Layer 2: 3-step LLM chain (output classification → dependency graph → formula translation)
│   ├── formula_runtime.py        # AST-safe Python executor for LLM-translated formulas
│   └── guardrails.py             # Input/output validation for LLM calls
├── config.py                     # + LLM_PROVIDER, LLM_API_KEY, CHAIN_ENABLED, FORMULA_TRANSLATION_MIN_CONFIDENCE, VALIDATION_TOLERANCE, HEAVY_SHEET_FORMULA_THRESHOLD
└── models/
    └── schemas.py                # + LLMAnalysisResult, OutputClassification, FormulaTranslation, DependencyInfo, ChainResult, CalculationMetadata, OutputFieldMeta
```

**Per-rater storage** (in `backend/data/raters/<uuid>/`):
- `schema.json` — enriched RaterSchema (after both LLM layers)
- `calculation_metadata.json` — 3-step chain output (final output keys, formula translations)

### Layer 2: 3-Step LLM Chain (`llm_chain.py`)

The chain is controlled by `CHAIN_ENABLED` and runs after Layer 1 in the same background thread:

```
Step 1: SmartOutputIdentifier
  → Classify all detected outputs: final | intermediate | display
  → Terminal formula nodes (not referenced by any other output) = final
  → Intermediate nodes = hidden by default in PremiumResults

Step 2: DependencyGraphBuilder
  → Map each input field to the outputs it drives through formula chains
  → Informs which inputs are "key drivers" of the final premium

Step 3: FormulaTranslator
  → Convert unsupported Excel formulas (OFFSET+MATCH, deep VLOOKUPs)
    to equivalent Python expressions
  → Validated against workbook default outputs (must match within VALIDATION_TOLERANCE)
  → Translations below FORMULA_TRANSLATION_MIN_CONFIDENCE (default 0.7) are discarded
```

### Runtime fallback (`formula_runtime.py`)

When the `formulas` library cannot resolve a cell, `CalculationEngine` falls
back to the LLM-translated Python expression executed by `FormulaRuntime`:
- Uses Python `ast` module to parse the expression — never calls `eval()` or `exec()`
- Only allows whitelisted operations: arithmetic, comparisons, math functions, list indexing
- Provides lookup table data as in-memory dicts accessible from expressions
- Identical inputs always produce identical outputs (deterministic)

---

## 9. Dependency Requirements

```
langchain-core>=0.3              # Structured output, prompt templates
# Pick ONE (or both) LLM providers:
langchain-google-genai>=2.1      # Google Gemini (gemini-2.0-flash — default, fast & cheap)
langchain-openai>=0.2            # OpenAI (gpt-4o-mini — fallback option)
```

**Note**: We do NOT need full `langchain` or `langchain` agents. Just
`langchain-core` for structured output parsing + one provider package.
This is much lighter than the full agent framework.

The default provider is **Google Gemini** (`LLM_PROVIDER=google` in
`.env`). Set `LLM_PROVIDER=openai` to switch. Both are configured in
`backend/app/config.py` with sensible defaults.

---

## 10. Honest Assessment — Is This Approach Beneficial?

### ✅ YES — Clear Benefits

| Benefit | Impact |
|---------|--------|
| **Better field classification** | Fields that heuristics misclassify get caught. Directly improves form quality. |
| **Better dependency tracing** | LLM understands cross-sheet VLOOKUP chains that regex misses. |
| **Adaptive boundary conditions** | Min/max from actual data instead of hardcoded dicts. |
| **One-time cost** | Single LLM call per upload (~$0.01-0.03). Zero cost at runtime. |
| **Zero runtime impact** | No latency, no LLM dependency during calculations. |
| **Graceful degradation** | LLM unavailable? Falls back to current heuristics. Nothing breaks. |
| **Deterministic runtime** | All calculations remain 100% deterministic. No hallucination risk. |

### ⚠️ Remaining Risks (Much Reduced)

| Risk | Severity | Mitigation |
|------|----------|------------|
| **LLM misclassifies a field** | MEDIUM — but caught by output guardrails | Confidence threshold (0.8); human review; heuristic fallback |
| **Adds upload latency** | LOW — 2-5s one-time per rater | Can run async; user already waits for parsing |
| **Requires API key** | LOW — optional dependency | System works without it; just uses heuristics |
| **Token cost for large raters** | LOW — $0.01-0.05 per upload | Truncate lookup tables; summarize large schemas |

### 🎯 Bottom Line

> **This approach gets 90% of the value of LangChain integration at 10%
> of the complexity and cost.** The hard problem was always extraction
> accuracy. By using the LLM ONLY to nail the extraction, then letting
> deterministic systems handle everything else, we get:
>
> - Better forms (right fields shown, right groups, right validation)
> - Better calculations (right inputs mapped to right cells)
> - Zero runtime LLM dependency
> - Zero hallucination risk at calculation time
> - Minimal added complexity (one service file + one guardrail file)

---

## 11. What Does NOT Change

The entire runtime pipeline is **completely untouched**:
- `ExcelRaterParser` — same extraction logic (provides raw data to LLM)
- `CalculationEngine` — same formula evaluation
- `RaterStore` — same persistence
- All existing API endpoints — same behavior
- Frontend — same rendering, same form, same calculation flow
- `SchemaGenerator` — same enrichment PLUS optional LLM overlay

If LangChain is removed, the system works exactly as before — the
`generate()` method just skips the LLM merge step.
