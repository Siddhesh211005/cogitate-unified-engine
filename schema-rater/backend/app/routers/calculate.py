"""
Calculate Router
================
POST /api/calculate  — run premium calculation with user inputs.
POST /api/calculate/defaults  — return default outputs (no overrides).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.models.schemas import CalculationRequest, CalculationResult
from app.services.calculation_engine import engine
from app.services.rater_store import RaterStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["calculate"])
store = RaterStore()


@router.post("/calculate", response_model=CalculationResult)
def calculate(req: CalculationRequest):
    """
    Calculate premiums using the uploaded rater's formulas.
    Accepts field name → value pairs; maps them to cell references
    and recalculates.
    """
    # Load schema
    try:
        schema = store.load_schema(req.rater_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Rater {req.rater_id} not found")

    # Get workbook path (for lazy model loading)
    try:
        wb_path = store.get_workbook_path(req.rater_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Workbook not found for rater {req.rater_id}")

    # Merge the array-of-objects inputs into a single flat dict for the engine.
    merged_inputs: dict[str, Any] = {}
    for obj in req.inputs:
        merged_inputs.update(obj)

    # Calculate
    try:
        result = engine.calculate(
            rater_id=req.rater_id,
            schema=schema,
            user_inputs=merged_inputs,
            workbook_path=wb_path,
        )
    except Exception as e:
        logger.exception("Calculation failed for rater %s", req.rater_id)
        raise HTTPException(500, f"Calculation error: {e}") from e

    return result


@router.post("/calculate/defaults", response_model=CalculationResult)
def calculate_defaults(req: CalculationRequest):
    """
    Return the default calculation outputs (using workbook defaults,
    no user overrides). Useful for populating the form initially.
    """
    # Same as calculate but with empty inputs
    req.inputs = [{}]
    return calculate(req)
