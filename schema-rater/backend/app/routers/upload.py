"""
Upload Router
=============
POST /api/upload  — accept an Excel rater, parse it, persist, return schema.
GET  /api/raters  — list all uploaded raters.
DELETE /api/raters/{rater_id} — remove a rater.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.config import ALLOWED_EXTENSIONS, UPLOAD_MAX_SIZE
from app.models.schemas import UploadResponse
from app.services.calculation_engine import engine
from app.services.rater_store import RaterStore
from app.services.schema_generator import SchemaGenerator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])
store = RaterStore()
generator = SchemaGenerator()


class SaveRaterRequest(BaseModel):
    upload_id: str = Field(alias="upload_id")
    slug: str = ""
    name: str = ""
    description: str = ""
    source: str = "raters"
    config: dict[str, Any] | None = None


@router.post("/upload", response_model=UploadResponse)
async def upload_rater(file: UploadFile = File(...)):
    """Upload an Excel rater workbook and receive its parsed schema.

    Returns immediately after fast heuristic parsing.  LLM analysis
    and model pre-loading happen in a background thread.
    """

    # ── Validate extension ────────────────────────────────────────────
    if not file.filename:
        raise HTTPException(400, "No filename provided")
    suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{suffix}'. Allowed: {ALLOWED_EXTENSIONS}")

    # ── Check for duplicate rater (same filename already uploaded) ──
    existing = store.find_by_filename(file.filename)
    if existing:
        existing_id = existing["rater_id"]
        if store.rater_exists(existing_id):
            return UploadResponse(
                rater_id=existing_id,
                rater_name=existing.get("rater_name", file.filename),
                rater_schema=store.load_schema(existing_id),
                duplicate=True,
            )

    # ── Read file bytes ───────────────────────────────────────────────
    contents = await file.read()
    if len(contents) > UPLOAD_MAX_SIZE:
        raise HTTPException(413, f"File too large ({len(contents)} bytes). Max: {UPLOAD_MAX_SIZE}")

    # ── Persist workbook ──────────────────────────────────────────────
    rater_id = str(uuid.uuid4())
    wb_path = store.save_rater(rater_id, contents, file.filename)

    # ── Parse & generate schema (fast — no LLM calls) ────────────────
    try:
        schema = generator.generate(wb_path, use_llm=False)
    except Exception as e:
        # Clean up on failure
        store.delete_rater(rater_id)
        raise HTTPException(422, f"Failed to parse rater: {e}") from e

    # ── Persist schema ────────────────────────────────────────────────
    store.save_schema(rater_id, schema)

    # ── Background: LLM enrichment + model pre-load ──────────────────
    def _background_work():
        # Pre-load the Excel model FIRST so calculations work immediately.
        # LLM enrichment is optional and should never block the model.
        try:
            engine.load_model(rater_id, wb_path)
            logger.info("Pre-loaded Excel model for rater %s", rater_id)
        except Exception as exc:
            logger.warning("Background model pre-load failed for %s: %s", rater_id, exc, exc_info=True)

        try:
            generator.run_llm_enrichment(schema, wb_path)
            # Re-save schema with LLM enrichments
            store.save_schema(rater_id, schema)
            logger.info("Background LLM enrichment done for rater %s", rater_id)
        except Exception as exc:
            logger.warning("Background LLM enrichment failed for %s: %s", rater_id, exc)

    threading.Thread(target=_background_work, daemon=True).start()

    return UploadResponse(
        rater_id=rater_id,
        rater_name=schema.rater_name,
        rater_schema=schema,
    )


@router.post("/admin/save")
def save_rater(payload: SaveRaterRequest):
    """Persist user-facing metadata for an uploaded schema rater."""
    if not store.rater_exists(payload.upload_id):
        raise HTTPException(404, f"Rater {payload.upload_id} not found")

    schema = store.load_schema(payload.upload_id)
    if payload.name.strip():
        schema.rater_name = payload.name.strip()
    store.save_schema(payload.upload_id, schema)

    meta = store.update_metadata(payload.upload_id, {
        "slug": payload.slug.strip() or payload.upload_id,
        "name": schema.rater_name,
        "description": payload.description.strip(),
        "source": payload.source or "raters",
    })

    return {
        "saved": True,
        "rater_id": payload.upload_id,
        "rater_name": schema.rater_name,
        "slug": meta.get("slug", payload.upload_id),
        "description": meta.get("description", ""),
        "source": meta.get("source", payload.source or "raters"),
    }


@router.get("/raters")
def list_raters():
    """List all uploaded raters."""
    return store.list_raters()


@router.delete("/raters/{rater_id}")
def delete_rater(rater_id: str):
    """Delete an uploaded rater and all related data."""
    engine.unload_model(rater_id)
    if store.delete_rater(rater_id):
        return {"deleted": True}
    raise HTTPException(404, f"Rater {rater_id} not found")
