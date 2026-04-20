# Cogitate Rater Engine

> A configuration-driven system that accepts **any Excel-based insurance rater workbook**,
> automatically parses its structure, and generates a dynamic web form for premium calculation.

---

## Key Features

- **🏠 Splash Screen** — Animated "Welcome to Cogitate Rater AI" with orange+blue gradient, followed by Admin/Client pathway selection
- **🛠️ Admin Pathway** — Upload, manage, and delete rater workbooks. Persistent storage — raters survive server restarts. Duplicate upload detection (redirects to existing rater)
- **📊 Client Pathway** — Browse all admin-uploaded raters, calculate premiums with dynamic forms. Toggle field customization via ⚙ button. Auto-refreshes to pick up new raters
- **💾 Full Persistence** — Uploaded raters are stored permanently on disk. Server pre-loads all persisted raters on startup for fast first calculations
- **🔄 Robust Upload** — Parse and initial premium calculation are separate steps with independent error handling
- **🔍 Duplicate Detection** — Re-uploading a file with the same name redirects to the existing rater

---

## Quick Start

### Prerequisites
- Python 3.11+ (tested with 3.14)
- Node.js 18+
- Git

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

pip install fastapi uvicorn python-multipart openpyxl formulas pydantic numpy
pip install langchain-core langchain-google-genai  # optional, for LLM analysis
uvicorn app.main:app --reload --port 8000
```
API available at `http://localhost:8000` — Swagger docs at `http://localhost:8000/docs`

### Frontend
```bash
cd frontend
npm install
npm run dev
```
UI available at `http://localhost:5173`

---

## How It Works

1. **Splash Screen** → User chooses Admin or Client pathway
2. **Admin**: Upload Excel rater (.xlsx) → engine parses structure → persistent storage → dynamic form
3. **Client**: Browse uploaded raters → select one → fill form → calculate premiums in real-time
4. **Calculation**: Uses original Excel formulas — not hand-translated code — for accuracy

### User Flows

```
                    ┌─────────────────────┐
                    │   Splash Screen     │
                    │  "Welcome to        │
                    │  Cogitate Rater AI" │
                    └─────────┬───────────┘
                              │
                    ┌─────────┴───────────┐
                    │                     │
              ┌─────▼─────┐        ┌─────▼─────┐
              │   Admin   │        │  Client   │
              └─────┬─────┘        └─────┬─────┘
                    │                     │
         ┌──────────┴──────────┐    ┌────┴─────┐
         │ Upload / Manage     │    │ Rater    │
         │ Raters              │    │ List     │
         └──────────┬──────────┘    └────┬─────┘
                    │                     │
         ┌──────────▼──────────┐    ┌────▼──────────────┐
         │ Field Selection     │    │ Dynamic Form      │
         │ + Initial Premium   │    │ (+ ⚙ toggle for   │
         └──────────┬──────────┘    │  field selection)  │
                    │               └────┬──────────────┘
         ┌──────────▼──────────┐         │
         │ Dynamic Form       │    ┌────▼──────────┐
         │ + Live Calculation  │    │ Live Premium  │
         └─────────────────────┘    │ Calculation   │
                                    └───────────────┘
```

---

## Project Structure

```
├── docs/                              # Full documentation
│   ├── RATER_ANALYSIS.md              # Detailed analysis of sample rater files
│   ├── ARCHITECTURE.md                # System architecture & data flow
│   ├── IMPLEMENTATION_PLAN.md         # Phase-by-phase build plan
│   ├── SCHEMA_SPEC.md                 # JSON schema contract
│   ├── LANGCHAIN_INTEGRATION.md       # LLM integration design
│   └── sample rater inputs/           # 5 sample Excel rater files
│
├── backend/                           # Python FastAPI backend
│   ├── .env                           # Environment variables
│   ├── app/
│   │   ├── main.py                    # FastAPI app + startup pre-loading
│   │   ├── config.py                  # Configuration settings
│   │   ├── models/schemas.py          # Pydantic models (incl. UploadResponse.duplicate)
│   │   ├── services/
│   │   │   ├── rater_store.py         # File-based storage + duplicate detection
│   │   │   ├── excel_parser.py        # Excel parsing pipeline
│   │   │   ├── schema_generator.py    # Schema generation + LLM merge
│   │   │   ├── calculation_engine.py  # Premium calculation engine
│   │   │   ├── formula_runtime.py     # Safe formula evaluator
│   │   │   ├── llm_analyzer.py        # LLM field classification
│   │   │   ├── llm_chain.py           # 3-step LLM chain
│   │   │   └── guardrails.py          # LLM validation
│   │   └── routers/
│   │       ├── upload.py              # Upload + duplicate detection
│   │       ├── schema.py              # Schema retrieval
│   │       └── calculate.py           # Premium calculation
│   └── data/raters/                   # Persistent rater storage (per-UUID directories)
│
├── frontend/                          # React 19 + TypeScript + Tailwind CSS 4
│   └── src/
│       ├── App.tsx                    # React Router setup
│       ├── types.ts                   # TypeScript interfaces
│       ├── api.ts                     # Backend API client
│       └── components/
│           ├── SplashScreen.tsx       # Animated welcome + pathway selection
│           ├── Layout.tsx             # Shared header/footer (Admin/Client)
│           ├── AdminDashboard.tsx     # Admin: upload + rater list
│           ├── AdminRaterWorkspace.tsx # Admin: field selection + form
│           ├── ClientDashboard.tsx    # Client: rater list (auto-refresh)
│           ├── ClientRaterWorkspace.tsx # Client: form + ⚙ field toggle
│           ├── RaterWorkspace.tsx     # Shared: two-phase workflow
│           ├── DynamicForm.tsx        # Schema-driven form generator
│           ├── InputFieldSelector.tsx # Field checkbox selector
│           ├── FormField.tsx          # Individual field renderer
│           ├── PremiumResults.tsx     # Premium output display
│           └── FileUpload.tsx         # Drag-and-drop file upload
│
├── test_api.py                        # API integration tests
├── test_all_raters.py                 # Batch test all sample raters
└── bench_calc.py                      # Calculation benchmarking
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upload` | Upload Excel rater; returns existing rater if duplicate filename detected |
| GET | `/api/raters` | List all uploaded raters (persistent) |
| DELETE | `/api/raters/{rater_id}` | Delete rater and all related data |
| GET | `/api/schema/{rater_id}` | Get parsed schema for a rater |
| POST | `/api/calculate` | Calculate premiums with user inputs |
| POST | `/api/calculate/defaults` | Calculate with workbook defaults |
| GET | `/health` | Health check |

---

## Persistence Model

- Each rater gets a UUID directory under `backend/data/raters/`
- Contains: original `.xlsx`, `schema.json`, `metadata.json`
- Raters survive server restarts — all models pre-loaded on startup
- Admin can delete raters; deletion removes all data permanently
- Client pathway auto-refreshes every 15 seconds to pick up new raters

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.11+, FastAPI, openpyxl, formulas, numpy |
| Frontend | React 19, TypeScript ~5.9, Tailwind CSS 4, Vite 8, React Router |
| Data Models | Pydantic v2 |
| LLM Analysis (optional) | LangChain Core, Google Gemini / OpenAI (upload-time only) |

---

## Guardrails

- **Strict retrieval-only**: All rates/factors come from the uploaded Excel file
- **No external data**: No internet lookups or hardcoded rates
- **Formula accuracy**: Uses original Excel formulas via `formulas` library
- **LLM usage**: Upload-time only — no LLM calls during premium calculation

### LLM Analysis (Upload-Time Only)

| Layer | File | Purpose |
|-------|------|---------|
| Schema Analyzer | `llm_analyzer.py` | Field classification (rating-relevant vs informational) |
| 3-Step Chain | `llm_chain.py` | Output classification, dependency graphs, formula translation |

Environment variables (`.env` in `backend/`):

```env
LLM_PROVIDER=google
LLM_API_KEY=your-api-key
LLM_MODEL_GOOGLE=gemini-2.0-flash
LLM_ENABLED=true
CHAIN_ENABLED=true
```

---

## Sample Rater Files

Located in `docs/sample rater inputs/`:

| File | Domain | Complexity |
|------|--------|-----------|
| Homeowners Rater.xlsx | Property Insurance | Medium |
| MPL Rater v2 updated.xlsx | Professional Liability | Medium |
| PAR Model.xlsx | Life Insurance | High (13 sheets) |
| Rater - Excess Follow Form.xlsx | Excess D&O | High (27 sheets) |
| OAKBRIDGE - RATER - Test with AI.xlsx | General | Medium |

---

## License

Private / Internal Use
