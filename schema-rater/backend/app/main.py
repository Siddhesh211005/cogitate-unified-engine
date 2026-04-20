"""
FastAPI application entry point.
Run with:  uvicorn app.main:app --reload
(from the backend/ directory)
"""

from __future__ import annotations

import logging
import os
import sys

# Force UTF-8 on Windows to avoid charmap codec errors with international chars
os.environ.setdefault("PYTHONUTF8", "1")
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(stream=open(os.devnull, "w") if False else sys.stderr),
    ],
)

app = FastAPI(
    title="Cogitate Rater Engine",
    description="Dynamic insurance rater UI — upload any Excel rater, get a web form, calculate premiums.",
    version="3.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────
from app.routers import upload, schema, calculate  # noqa: E402

app.include_router(upload.router, prefix="/api")
app.include_router(schema.router, prefix="/api")
app.include_router(calculate.router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ── Startup: pre-load models for all persisted raters ─────────────────────
@app.on_event("startup")
def preload_existing_raters():
    """Pre-load calculation models for all persisted raters so first
    calculation is fast after a server restart."""
    import threading
    from app.services.rater_store import RaterStore
    from app.services.calculation_engine import engine

    store = RaterStore()

    def _preload():
        raters = store.list_raters()
        if not raters:
            return
        logger = logging.getLogger(__name__)
        logger.info("Pre-loading %d persisted rater(s)…", len(raters))
        for meta in raters:
            rid = meta.get("rater_id")
            if not rid or not store.rater_exists(rid):
                continue
            try:
                wb_path = store.get_workbook_path(rid)
                engine.load_model(rid, wb_path)
                logger.info("  ✓ Pre-loaded %s (%s)", meta.get("rater_name", rid), rid)
            except Exception as exc:
                logger.warning("  ✗ Failed to pre-load %s: %s", rid, exc)

    threading.Thread(target=_preload, daemon=True).start()
