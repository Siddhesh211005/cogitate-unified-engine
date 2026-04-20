"""
Guardrails for LLM Schema Analysis
====================================
Validates inputs going TO the LLM and outputs coming FROM the LLM.
Ensures the LLM only sees structured rater data and never hallucinates
field names or numbers that don't exist in the parsed schema.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.schemas import RaterSchema

logger = logging.getLogger(__name__)

# ── Maximum tokens we'll send (truncate large lookup tables) ─────────────
_MAX_LOOKUP_ROWS = 10  # sample rows per table
_MAX_FIELDS = 200      # cap to avoid token explosion


class InputGuardrail:
    """Sanitize parsed schema data before sending to LLM."""

    def build_prompt_data(self, schema: RaterSchema) -> dict[str, Any]:
        """
        Convert RaterSchema into a compact dict safe for LLM consumption.
        Strips file paths, limits lookup table rows, caps field count.
        """
        sheets = [
            {
                "name": si.sheet_name,
                "role": si.role.value,
                "rows": si.row_count,
                "cols": si.col_count,
            }
            for si in schema.sheets
        ]

        raw_fields = []
        for f in (schema.input_fields + schema.output_fields)[:_MAX_FIELDS]:
            entry: dict[str, Any] = {
                "name": f.name,
                "label": f.label,
                "cell_ref": f.cell_ref,
                "sheet": f.sheet,
                "is_output": f.is_output,
                "field_type": f.field_type.value,
                "default_value": _safe_value(f.default_value),
                "has_formula": f.formula is not None,
            }
            if f.formula:
                entry["formula"] = f.formula
            if f.options:
                entry["options"] = [o.label for o in f.options[:20]]
            if f.validation:
                entry["validation"] = {
                    "min": f.validation.min_value,
                    "max": f.validation.max_value,
                }
            raw_fields.append(entry)

        formula_mappings = []
        for fm in schema.formula_mappings:
            formula_mappings.append({
                "output_name": fm.output_name,
                "cell_ref": fm.cell_ref,
                "formula": fm.formula,
                "depends_on": fm.depends_on,
            })

        lookup_summaries = []
        for lt in schema.lookup_tables:
            lookup_summaries.append({
                "name": lt.name,
                "sheet": lt.sheet,
                "columns": lt.columns,
                "sample_rows": lt.rows[:_MAX_LOOKUP_ROWS],
                "total_rows": len(lt.rows),
            })

        return {
            "rater_name": schema.rater_name,
            "sheets": sheets,
            "fields": raw_fields,
            "formula_mappings": formula_mappings,
            "lookup_tables": lookup_summaries,
        }


class OutputGuardrail:
    """Validate LLM analysis results against actual parsed schema."""

    def validate(
        self,
        llm_result: dict[str, Any],
        schema: RaterSchema,
    ) -> dict[str, Any]:
        """
        Filter LLM classifications to only include fields that actually
        exist in the schema. Downgrade confidence if claims don't match data.
        Returns a cleaned result dict.
        """
        known_input_names = {f.name for f in schema.input_fields}
        known_output_names = {f.name for f in schema.output_fields}
        all_known = known_input_names | known_output_names

        # Build a quick lookup: field_name → set of formulas referencing it
        formula_deps: set[str] = set()
        for fm in schema.formula_mappings:
            formula_deps.update(fm.depends_on)

        validated_classifications: list[dict[str, Any]] = []

        for clf in llm_result.get("field_classifications", []):
            field_name = clf.get("field_name", "")

            # Rule 1: field must actually exist
            if field_name not in all_known:
                logger.debug("LLM referenced unknown field '%s' — skipped", field_name)
                continue

            # Rule 2: only classify input fields
            if field_name not in known_input_names:
                continue

            confidence = clf.get("confidence", 0.5)

            # Rule 3: if LLM says impacts_premium=True but field has zero
            # formula references, reduce confidence
            if clf.get("impacts_premium", False) and field_name not in formula_deps:
                confidence = min(confidence, 0.6)
                clf["confidence"] = confidence

            # Rule 4: minimum confidence threshold
            if confidence < 0.5:
                logger.debug(
                    "LLM classification for '%s' below threshold (%.2f) — skipped",
                    field_name, confidence,
                )
                continue

            clf["confidence"] = confidence
            validated_classifications.append(clf)

        result = {
            "field_classifications": validated_classifications,
            "premium_logic_summary": llm_result.get("premium_logic_summary", {}),
            "dependency_graph": llm_result.get("dependency_graph", {}),
        }

        logger.info(
            "LLM output guardrail: %d/%d field classifications passed validation",
            len(validated_classifications),
            len(llm_result.get("field_classifications", [])),
        )
        return result


# ── Helpers ──────────────────────────────────────────────────────────────

def _safe_value(val: Any) -> Any:
    """Ensure a value is JSON-safe and not too large."""
    if val is None:
        return None
    if isinstance(val, (int, float, bool)):
        return val
    s = str(val)
    if len(s) > 200:
        return s[:200] + "…"
    return s
