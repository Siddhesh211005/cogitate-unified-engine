"""
Application configuration.
All paths/settings in one place for easy reference across sessions.
"""

import os
from pathlib import Path

# ── Load .env file if present ────────────────────────────────────────────
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# ── Project root (two levels up from this file) ──────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # …/Cogitate-project-v2

# ── Data storage ─────────────────────────────────────────────────────────
DATA_DIR = PROJECT_ROOT / "backend" / "data" / "raters"

# ── Upload limits ────────────────────────────────────────────────────────
UPLOAD_MAX_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {".xlsx", ".xls"}

# ── Calculation ──────────────────────────────────────────────────────────
CALCULATION_TIMEOUT = int(os.environ.get("CALCULATION_TIMEOUT", "30"))  # seconds

# ── LLM Chain (upload-time multi-step analysis) ──────────────────────
# Enable the 3-step LLM chain (output identification, dependency graph, formula translation)
CHAIN_ENABLED: bool = os.environ.get("CHAIN_ENABLED", "true").lower() in ("1", "true", "yes")
# Formula translation confidence threshold — translations below this are discarded
FORMULA_TRANSLATION_MIN_CONFIDENCE: float = float(os.environ.get("FORMULA_TRANSLATION_MIN_CONFIDENCE", "0.7"))
# Maximum tolerance for validation mismatch (1% default)
VALIDATION_TOLERANCE: float = float(os.environ.get("VALIDATION_TOLERANCE", "0.01"))

# ── LLM (parse-time analysis) ────────────────────────────────────────────
# Supported providers: "google" (Gemini, free tier) or "openai"
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "google")
LLM_API_KEY: str = os.environ.get("LLM_API_KEY", "")
# Model names — sensible free-tier defaults
LLM_MODEL_GOOGLE: str = os.environ.get("LLM_MODEL_GOOGLE", "gemini-2.0-flash")
LLM_MODEL_OPENAI: str = os.environ.get("LLM_MODEL_OPENAI", "gpt-4o-mini")
# Set to False to skip LLM analysis entirely (pure heuristic fallback)
LLM_ENABLED: bool = os.environ.get("LLM_ENABLED", "true").lower() in ("1", "true", "yes")

# ── CORS ─────────────────────────────────────────────────────────────────
CORS_ORIGINS = [
    "http://localhost:5173",   # Vite dev server
    "http://localhost:3000",   # CRA fallback
    "http://127.0.0.1:5173",
]

# ── Parser Heuristics (configurable, not hardcoded) ──────────────────────
# These are cross-rater patterns detected in Excel rater workbooks.
# They are NOT rater-specific — they identify common patterns that apply
# to any insurance rater workbook.

# Keywords in labels that indicate instruction text (not real inputs)
PARSER_INSTRUCTION_KEYWORDS: tuple[str, ...] = (
    "cell inputs are", "all inputs should", "inputs are in",
    "shaded gray", "shaded blue", "cell_inputs_are",
    "calculated premium", "leave cell blank",
)

# Keywords that identify final premium outputs (override DAG classification)
# If an output name contains any of these, it won't be marked as intermediate
PARSER_FINAL_OUTPUT_KEYWORDS: tuple[str, ...] = (
    "premium", "final", "total", "result", "net", "gross",
    "annual", "endorsement", "surcharge", "minimum",
)

# Minimum field name length (shorter names are likely garbage like "g", "hk")
PARSER_MIN_FIELD_NAME_LENGTH: int = 3

# ── Calculation engine ───────────────────────────────────────────────────────
# Sheets whose formula-cell count exceeds this threshold are "frozen" before
# loading into the formulas library — all formula strings replaced with their
# last-saved data values.  This prevents unbounded dependency-graph expansion
# from large iterative sheets (e.g. actuarial cashflow projections).
# The VLOOKUP outputs that reference those sheets still resolve correctly
# against the frozen data.  Set to 0 to disable.
HEAVY_SHEET_FORMULA_THRESHOLD: int = int(
    os.environ.get("HEAVY_SHEET_FORMULA_THRESHOLD", "500")
)

# ── Calculation engine ───────────────────────────────────────────────────
# Sheets whose formula cells exceed this count are "frozen" (formulas replaced
# with their last-saved data values) before loading into the formulas library.
# This prevents the dependency-graph explosion caused by large iterative sheets
# (e.g. actuarial cashflow projections).  The VLOOKUP outputs that reference
# those sheets still work correctly against the now-data cells.
# Set to 0 to disable freezing.  Tune higher to preserve more live formulas.
HEAVY_SHEET_FORMULA_THRESHOLD: int = int(os.environ.get("HEAVY_SHEET_FORMULA_THRESHOLD", "500"))
