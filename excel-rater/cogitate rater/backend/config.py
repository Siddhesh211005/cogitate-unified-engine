# backend/config.py
# Global config — NO hardcoded rater fields, only system paths

import os
import platform
from pathlib import Path

# ─── App/data root directory ──────────────────────────────────────────
APPS_DIR = Path(__file__).resolve().parent.parent
if not APPS_DIR.exists():
    APPS_DIR = Path(__file__).resolve().parent.parent.parent

# Backward compatibility: if data folders are still at repo root, keep working.
if not (APPS_DIR / "raters").exists() and (APPS_DIR.parent / "raters").exists():
    APPS_DIR = APPS_DIR.parent

# ─── Rater / template / upload directories ────────────────────────────
RATERS_DIR = APPS_DIR / "raters"
TEMPLATES_DIR = APPS_DIR / "templates"
RECORDS_DIR = APPS_DIR / "records"
UPLOADS_DIR = APPS_DIR / "dump" / "uploads"

RATERS_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
RECORDS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ─── LibreOffice binary — auto-detected by OS ────────────────────────
# Removed: Only Microsoft Excel COM via win32com is used. 

# ─── Warm-start toggles (local-first pilot) ──────────────────────────
WARM_START_ENABLED = True  # Mandatory in pure COM mode
WARM_SESSION_TTL_SEC = int(os.getenv("WARM_SESSION_TTL_SEC", "1800"))
WARM_FAIL_OPEN = False # Removed LibreOffice fallback, so fail-open evaluates to false.
