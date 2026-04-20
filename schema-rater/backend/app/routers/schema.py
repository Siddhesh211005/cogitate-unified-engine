"""
Schema Router
=============
GET /api/schema/{rater_id}  — return the parsed JSON schema for a rater.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import RaterSchema
from app.services.rater_store import RaterStore

router = APIRouter(tags=["schema"])
store = RaterStore()


@router.get("/schema/{rater_id}", response_model=RaterSchema)
def get_schema(rater_id: str):
    """Retrieve the parsed schema for a previously uploaded rater."""
    try:
        return store.load_schema(rater_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Rater {rater_id} not found")
