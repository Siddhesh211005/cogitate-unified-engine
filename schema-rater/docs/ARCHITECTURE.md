# Architecture Document

> **Purpose**: Complete architecture reference for the Cogitate Rater Engine.

---

## 1. System Overview

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              USER BROWSER                                        │
│                                                                                  │
│  ┌──────────────┐     ┌────────────────────────────┐                            │
│  │ Splash Screen│     │  React Router (5 routes)   │                            │
│  │ (animated)   │ ──► │  /          SplashScreen   │                            │
│  └──────────────┘     │  /admin     AdminDashboard │                            │
│                        │  /admin/rater/:id  Admin  │                            │
│                        │  /client    ClientDashboard│                            │
│                        │  /client/rater/:id Client │                            │
│                        └────────────┬───────────────┘                            │
│                                     │                                            │
│  ┌──────────────────────────────────▼──────────────────────────────────┐        │
│  │ ADMIN PATHWAY                   │ CLIENT PATHWAY                    │        │
│  │  FileUpload (drag-drop)         │  RaterList (auto-refresh 15s)     │        │
│  │  RaterList (full CRUD)          │  DynamicForm + PremiumResults     │        │
│  │  InputFieldSelector (inline)    │  ⚙ toggle → InputFieldSelector   │        │
│  │  DynamicForm + PremiumResults   │                                   │        │
│  └──────────────────┬──────────────┴──────────────┬────────────────────┘        │
└─────────────────────┼────────────────────────────── ┼───────────────────────────┘
                      │   (fetch / REST)              │
                      ▼                               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              FastAPI BACKEND                                     │
│                                                                                  │
│  POST /api/upload (+ duplicate check)    GET /api/raters                        │
│  DELETE /api/raters/{id}                 GET /api/schema/{id}                   │
│  POST /api/calculate                     POST /api/calculate/defaults            │
│                                                                                  │
│  ┌──────────────┐  ┌───────────────────────┐  ┌──────────────────────────┐     │
│  │ Excel Parser │  │  Calculation Engine   │  │  Schema Registry         │     │
│  │ (openpyxl)   │  │  (formulas library)   │  │  (GET /api/schema/:id)  │     │
│  └──────┬───────┘  └──────────┬────────────┘  └─────────────┬────────────┘     │
│         │                     │                              │                  │
│         └──────────┬──────────┘──────────────────────────────┘                  │
│                    ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐       │
│  │          Rater Store  — data/raters/<uuid>/                          │       │
│  │          <original>.xlsx  |  schema.json  |  metadata.json           │       │
│  │          (+ optional calculation_metadata.json for LLM chain output) │       │
│  │          Survives server restarts. Models pre-loaded on startup.     │       │
│  └──────────────────────────────────────────────────────────────────────┘       │
│                                                                                  │
│  Optional (upload-time background thread only):                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐       │
│  │  LLM Layer 1 — llm_analyzer.py: field classification                │       │
│  │  LLM Layer 2 — llm_chain.py: output classification + deps + formulas │       │
│  └──────────────────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Frontend** | React 19 + TypeScript | Component-driven, dynamic form generation |
| **Routing** | React Router v6 | URL-based Admin/Client pathway separation |
| **Styling** | Tailwind CSS 4 | Utility-first, no custom CSS needed |
| **State** | React hooks (useState/useCallback) | Local state sufficient; no Redux needed |
| **Backend** | Python 3.11+ FastAPI | Async, auto-docs, Pydantic native |
| **Excel Parsing** | openpyxl | Named ranges, data validations, formulas |
| **Calculation Engine** | formulas library | Compile Excel model, recalculate, read outputs |
| **Data Models** | Pydantic v2 | JSON schema validation and serialization |
| **LLM Analysis** | LangChain Core + Google Gemini / OpenAI | Upload-time only: field classification, formula translation |
| **API Docs** | Auto-generated OpenAPI/Swagger | At `/docs` |

---

## 3. Directory Structure

```
Cogitate-project-v2/
├── README.md                          # Project overview, setup, usage
├── test_api.py                        # API integration tests
├── test_all_raters.py                 # Batch test all sample raters
├── bench_calc.py                      # Calculation benchmarking
├── docs/
│   ├── ARCHITECTURE.md                # This file
│   ├── SCHEMA_SPEC.md                 # JSON schema & API contract
│   └── LANGCHAIN_INTEGRATION.md       # LLM integration design
│   └── sample rater inputs/           # 5 sample Excel rater files
│
├── backend/
│   ├── .env                           # LLM_API_KEY, LLM_PROVIDER, etc.
│   ├── app/
│   │   ├── main.py                    # FastAPI app + startup model pre-loading
│   │   ├── config.py                  # All configuration constants
│   │   ├── models/schemas.py          # Pydantic models (UploadResponse.duplicate added)
│   │   ├── services/
│   │   │   ├── excel_parser.py        # 2-phase Excel parsing
│   │   │   ├── calculation_engine.py  # 5-stage premium calculation pipeline
│   │   │   ├── schema_generator.py    # Schema enrichment + LLM merge
│   │   │   ├── rater_store.py         # File-system storage (+ find_by_filename)
│   │   │   ├── llm_analyzer.py        # Upload-time LLM field classification
│   │   │   ├── llm_chain.py           # 3-step upload-time LLM chain
│   │   │   ├── formula_runtime.py     # AST-safe Python executor for translated formulas
│   │   │   └── guardrails.py          # LLM output validation
│   │   └── routers/
│   │       ├── upload.py              # POST /api/upload (+ duplicate detection)
│   │       ├── calculate.py           # POST /api/calculate, /defaults
│   │       └── schema.py              # GET /api/schema/{rater_id}
│   └── data/raters/                   # Persistent per-rater storage (UUID directories)
│       └── <rater_id>/
│           ├── <original>.xlsx
│           ├── schema.json
│           ├── metadata.json
│           └── calculation_metadata.json  # (optional, from LLM chain)
│
├── frontend/
│   ├── vite.config.ts                 # Vite config with /api proxy
│   └── src/
│       ├── main.tsx                   # React entry point
│       ├── App.tsx                    # React Router — 5 routes
│       ├── types.ts                   # TypeScript interfaces
│       ├── api.ts                     # fetch wrapper with retry logic
│       └── components/
│           ├── SplashScreen.tsx       # Animated welcome + Admin/Client buttons
│           ├── Layout.tsx             # Shared header/footer (orange=admin, blue=client)
│           ├── AdminDashboard.tsx     # Upload + persistent rater list + delete
│           ├── AdminRaterWorkspace.tsx# Field selection + form (admin view)
│           ├── ClientDashboard.tsx    # Auto-refreshing rater list (read-only)
│           ├── ClientRaterWorkspace.tsx # Form + ⚙ field customization toggle
│           ├── RaterWorkspace.tsx     # Shared 2-phase workflow (selecting → form)
│           ├── DynamicForm.tsx        # Schema-driven form with live calculation
│           ├── InputFieldSelector.tsx # Checkbox field picker (admin inline / client toggle)
│           ├── FormField.tsx          # Field renderer (text/number/select/date/boolean)
│           ├── PremiumResults.tsx     # Grouped premium output display
│           └── FileUpload.tsx         # Drag-and-drop Excel upload
│
└── .gitignore
```

---

## 4. User Pathways & Routing

### Splash Screen Flow
```
http://localhost:5173/
  → SplashScreen animates (2.5s)
  → "Welcome to Cogitate Rater AI" (orange+blue gradient, shimmer)
  → Fades out → "Choose your pathway"
  → [Admin] button  →  navigate /admin
  → [Client] button →  navigate /client
```

### Admin Pathway
```
/admin               → AdminDashboard
  ├── FileUpload widget (drag-drop .xlsx)
  │     └── POST /api/upload
  │           ├── If duplicate filename → returns existing rater_id (duplicate: true)
  │           │    → navigate /admin/rater/<existing_id>
  │           └── New rater → parse + store → navigate /admin/rater/<new_id>
  └── Persistent rater list (GET /api/raters on mount)
        ├── Open → navigate /admin/rater/:id
        └── Delete → DELETE /api/raters/:id → refresh list

/admin/rater/:id     → AdminRaterWorkspace
  ├── GET /api/schema/:id on mount
  ├── Phase 1 (selecting): InputFieldSelector + Initial Premium (defaults)
  ├── Phase 2 (form): DynamicForm + PremiumResults (live calc)
  └── Delete Rater button
```

### Client Pathway
```
/client              → ClientDashboard
  ├── GET /api/raters on mount
  ├── Auto-refresh every 15s + on window focus
  └── Click rater card → navigate /client/rater/:id

/client/rater/:id    → ClientRaterWorkspace
  ├── GET /api/schema/:id on mount
  ├── DynamicForm directly (no mandatory field selection step)
  ├── ⚙ "Customize Fields" toggle → shows InputFieldSelector overlay
  └── Full live calculation (POST /api/calculate)
```

---

## 5. Data Flow

### 5.1 Upload Flow
```
User drops .xlsx → POST /api/upload
  → Check extension + size
  → find_by_filename() — if same filename exists, return existing (duplicate: true)
  → Save file to data/raters/<uuid>/<filename>.xlsx
  → ExcelRaterParser: inspect() → extract() (fast, heuristic-only)
  → SchemaGenerator.generate(use_llm=False) → RaterSchema JSON
  → Save schema.json + metadata.json
  → Return { rater_id, rater_name, schema, duplicate: false }  ← immediate response

  [Background thread]
  → CalculationEngine.load_model()     ← pre-compile Excel model
  → LLMSchemaAnalyzer.analyze()        ← field classification (if LLM_ENABLED)
  → LLMChain.run()                     ← 3-step chain (if CHAIN_ENABLED)
  → Re-save enriched schema.json + calculation_metadata.json
```

### 5.2 Startup Pre-loading
```
FastAPI startup event (@app.on_event("startup"))
  → RaterStore.list_raters()
  → For each persisted rater:
      CalculationEngine.load_model(rater_id, wb_path)
  → Background thread (non-blocking)
  → First calculation after restart is fast (no cold-load delay)
```

### 5.3 Calculation Flow
```
User changes input → 600ms debounce → POST /api/calculate
  → Load schema from disk
  → Load (or cache-hit) Excel model
  → CalculationEngine 5-stage pipeline:
      Stage 1: Workbook sanitization (heavy-sheet freeze, OFFSET→INDEX rewrite)
      Stage 2: formulas library primary calculation
      Stage 3: Python VLOOKUP fallback (for #N/A results)
      Stage 4: LLM-translated formula fallback (formula_runtime.py, AST-safe)
      Stage 5: Cached workbook values fallback (with warning)
  → Return { outputs, output_fields_meta, warnings, refer }
  → Frontend updates PremiumResults
```

---

## 6. API Endpoints

### `POST /api/upload`
**Request**: `multipart/form-data` (file)  
**Response**:
```json
{
  "rater_id": "uuid-string",
  "rater_name": "Homeowners Rater",
  "schema": { ... RaterSchema ... },
  "duplicate": false
}
```
`duplicate: true` when the same filename was already uploaded — `rater_id` points to the existing rater.

### `GET /api/raters`
```json
[
  { "rater_id": "uuid1", "rater_name": "Homeowners Rater", "original_filename": "...", "uploaded_at": "..." }
]
```

### `DELETE /api/raters/{rater_id}`
`{ "deleted": true }`

### `GET /api/schema/{rater_id}`
Returns full `RaterSchema` JSON.

### `POST /api/calculate`
**Request**: `{ "rater_id": "...", "inputs": [{ "field_name": value }] }`  
**Response**: `{ "rater_id", "outputs", "output_fields_meta", "warnings", "refer" }`

### `POST /api/calculate/defaults`
Same as `/api/calculate` with empty inputs. Used to populate initial premium on load.

### `GET /health`
`{ "status": "ok" }`

---

## 7. Component Architecture (Frontend)

### 7.1 Route Layout
```
/                    SplashScreen (full-screen, no layout wrapper)
/admin               Layout (orange header) > AdminDashboard
/admin/rater/:id     Layout (orange header) > AdminRaterWorkspace
/client              Layout (blue header)   > ClientDashboard
/client/rater/:id    Layout (blue header)   > ClientRaterWorkspace
```

### 7.2 Component Tree
```
App.tsx  (BrowserRouter)
├── SplashScreen                     / route
├── Layout [mode=admin]
│   ├── AdminDashboard               /admin
│   │   ├── FileUpload
│   │   └── RaterCard × N (from GET /api/raters)
│   └── AdminRaterWorkspace          /admin/rater/:id
│       └── RaterWorkspace (shared)
│           ├── Phase 1: InputFieldSelector + PremiumResults (defaults)
│           └── Phase 2: DynamicForm
│               ├── FormField × N    (draggable, grouped)
│               └── PremiumResults   (live-updating)
└── Layout [mode=client]
    ├── ClientDashboard              /client
    │   └── RaterCard × N (from GET /api/raters, auto-refresh 15s)
    └── ClientRaterWorkspace         /client/rater/:id
        ├── ⚙ Toggle → InputFieldSelector (overlay panel)
        └── DynamicForm
            ├── FormField × N
            └── PremiumResults
```

### 7.3 Key Behavioural Differences: Admin vs Client

| Feature | Admin | Client |
|---------|-------|--------|
| Upload raters | ✅ FileUpload widget | ❌ No upload |
| Delete raters | ✅ Delete button on each card | ❌ No delete |
| Field selection | ✅ Always visible (Phase 1) | ✅ Behind ⚙ toggle |
| Header color | 🟠 Orange | 🔵 Blue |
| Rater list refresh | On mount + manual ↻ | Every 15s + on focus |

---

## 8. Persistence Model

```
backend/data/raters/
└── <rater_uuid>/
    ├── <original_filename>.xlsx      # Uploaded workbook (used for calculation)
    ├── schema.json                   # Parsed RaterSchema (re-saved after LLM enrichment)
    ├── metadata.json                 # { rater_id, rater_name, original_filename, uploaded_at }
    └── calculation_metadata.json     # LLM chain results (optional)
```

- Raters are permanent until explicitly deleted via `DELETE /api/raters/{id}`
- Server startup pre-loads all persisted models in a background thread
- `find_by_filename()` enables duplicate detection without scanning full schemas
- No database required — pure file system

---

## 9. LLM Integration (Upload-Time Only)

No LLM calls at runtime. Both layers run once per rater in a background thread after upload.

### Layer 1 — `llm_analyzer.py`
- Classifies inputs: rating-relevant vs informational
- Suggests semantic field groupings
- Traces formula dependency chains

### Layer 2 — `llm_chain.py` (3-step chain, if `CHAIN_ENABLED=true`)
- **Step 1**: Classify outputs as final / intermediate / display
- **Step 2**: Build input→output dependency graph
- **Step 3**: Translate unsupported formulas (OFFSET+MATCH) to validated Python expressions

Results saved to `calculation_metadata.json`. Used at runtime only by `formula_runtime.py` as a Stage 4 fallback.

See `docs/LANGCHAIN_INTEGRATION.md` for the full design.

---

## 10. Guardrails & Constraints

- **Strict retrieval-only**: All rates/factors come from the uploaded Excel — no hardcoded data
- **LLM is optional**: `LLM_ENABLED=false` → pure heuristic extraction, full functionality
- **Calculation accuracy**: 5-stage pipeline with explicit fallback logging; never silently wrong
- **Duplicate detection**: Re-uploading same filename → redirect to existing rater (no duplicate storage)
- **No auth boundary**: Admin/Client is a UI pathway choice, not a security control

---

## 11. Component Details

| Component | Status | Responsibility |
|------|--------|-----------|
| `backend/app/main.py` | ✅ | Fast API entry point & model pre-loading |
| `backend/app/config.py` | ✅ | Global configuration and environment variables |
| `backend/app/models/schemas.py` | ✅ | Core Pydantic definitions (inc. upload responses) |
| `backend/app/routers/upload.py` | ✅ | Handles upload routes & duplicate detection |
| `backend/app/routers/calculate.py` | ✅ | Handles premium calculation and defaults endpoints |
| `backend/app/routers/schema.py` | ✅ | Handles schema retrieval endpoints |
| `backend/app/services/rater_store.py` | ✅ | Persists logic and manages `find_by_filename()` |
| `backend/app/services/excel_parser.py` | ✅ | 2-phase Excel heuristic extraction |
| `backend/app/services/calculation_engine.py` | ✅ | 5-stage deterministic calculation pipeline |
| `backend/app/services/schema_generator.py` | ✅ | Schema enrichment & LLM result merging |
| `backend/app/services/llm_analyzer.py` | ✅ | Upload-time field classification |
| `backend/app/services/llm_chain.py` | ✅ | 3-step upload-time logic parsing chain |
| `backend/app/services/formula_runtime.py` | ✅ | AST-safe Python executor for LLM mapped formulas |
| `backend/app/services/guardrails.py` | ✅ | Input/output structural validation for LLM |
| `frontend/src/App.tsx` | ✅ | Route registry and layout rendering (5 routes) |
| `frontend/src/index.css` | ✅ | Tailwind imports and splash animations |
| `frontend/src/types.ts` | ✅ | Global Typescript interfaces |
| `frontend/src/components/SplashScreen.tsx` | ✅ | Animated welcome + pathway selection |
| `frontend/src/components/Layout.tsx` | ✅ | Shared header (admin/client styling) |
| `frontend/src/components/AdminDashboard.tsx` | ✅ | UI for rater uploads + deletion list |
| `frontend/src/components/AdminRaterWorkspace.tsx` | ✅ | Logic and form for administrative control |
| `frontend/src/components/ClientDashboard.tsx` | ✅ | Auto-refreshing directory list |
| `frontend/src/components/ClientRaterWorkspace.tsx` | ✅ | Dynamic form with hidden field options |

