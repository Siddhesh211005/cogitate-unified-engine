"""
Schema Generator
================
Thin orchestrator that:
  1. Runs ExcelRaterParser (inspect → extract)
  2. Enriches the extracted RaterSchema with UI hints (better groups,
     dropdown options from lookup tables, boundary-condition validation).
  3. Marks which input fields actually impact calculation outputs.

See docs/IMPLEMENTATION_PLAN.md §1.4 and docs/SCHEMA_SPEC.md for design.
"""

from __future__ import annotations

import re
from pathlib import Path

import logging

from app.models.schemas import (
    CalculationMetadata,
    FieldOption,
    FieldType,
    LLMAnalysisResult,
    LLMFieldClassification,
    RaterField,
    RaterSchema,
    ValidationRule,
)
from app.services.excel_parser import ExcelRaterParser

logger = logging.getLogger(__name__)


# ── Keywords for non-impacting / informational fields ────────────────
# Only compound/specific phrases — standalone "state", "city", "zip"
# are omitted because they can be legitimate rating inputs.
_INFO_NAME_KEYWORDS = {
    "name_of_insured", "insured_name", "business_address", "mailing",
    "mailing_address", "mailing_city", "mailing_state", "mailing_zip",
    "business_phone", "business_fax", "business_email",
    "business_web", "web_address", "web_url",
    "contact_name", "agent_name", "broker_name", "producer_name",
    "customer_name", "location_address", "location_city", "location_county",
    "location_state", "location_zip", "mortgage", "loan_number",
    "property_manager", "name_of_first", "name_of_property",
    "cell_inputs_are", "cell_input", "all_inputs_should",
    "address_city", "address_state", "address_zip",
}

# Fields whose default values indicate they are descriptive / label headers
_DESCRIPTIVE_DEFAULTS = {
    "selection", "multiple", "description", "example", "n/a",
}

# Fields whose names suggest they are internal lookup result codes, not user inputs
_INTERNAL_NAME_PATTERNS = re.compile(
    r"^(\d[\d_]+\d)$"   # purely numeric slugs like 3_000_001_6_000_000
    r"|^class_[ivxlcdm]+$"  # Class_I, Class_II, …
    r"|^rating_codes$"
    r"|^rate$"
    r"|^selection$"
, re.IGNORECASE)

# ── Keywords for fields that are always rating inputs ────────────────
# These override Rule 5 (formula dependency analysis) because the simple
# regex-based dependency extraction often misses indirect references
# (cross-sheet lookups, VLOOKUP, INDEX/MATCH, etc.).
_RATING_INPUT_KEYWORDS = {
    "age", "sex", "smoking", "maturity_age", "maturity age",
    "sum_assured", "sum assured", "sum_insured", "sum insured",
    "premium_target", "premium target", "premium_mode", "premium mode",
    "issue_age", "issue age", "policy_term", "policy term",
    "benefit_term", "benefit term", "payment_term", "payment term",
    "coverage", "deductible", "limit", "territory",
}


class SchemaGenerator:
    """Produce an enriched RaterSchema from an Excel file."""

    def generate(self, file_path: str | Path, use_llm: bool = False) -> RaterSchema:
        """Fast pipeline: parse → heuristic enrich → return.

        LLM analysis is NO LONGER run here by default — call
        ``run_llm_enrichment()`` in a background thread instead so the
        upload HTTP response is not blocked by multiple LLM API calls.
        """
        parser = ExcelRaterParser(file_path)
        schema = parser.extract()   # inspect() is called internally if needed

        # ── Heuristic enrichment (always runs — fast) ─────────────────
        self._enrich_options(schema)
        self._apply_boundary_conditions(schema)
        self._ensure_yes_no_selects(schema)
        self._enrich_groups(schema)
        self._mark_impacts_output(schema)

        # ── Only run LLM inline if explicitly requested (legacy path) ──
        if use_llm:
            self._run_llm_inline(schema, Path(file_path))

        return schema

    # ── Background LLM enrichment (called from upload route) ──────────

    def run_llm_enrichment(self, schema: RaterSchema, file_path: str | Path) -> None:
        """Run LLM analysis + chain + smoke test.

        Intended to be called in a background thread so the upload
        response returns immediately after heuristic parsing.
        """
        self._run_llm_inline(schema, Path(file_path))

    def _run_llm_inline(self, schema: RaterSchema, file_path: Path) -> None:
        """Execute LLM analyzer + chain sequentially (slow)."""
        try:
            from app.services.llm_analyzer import llm_analyzer
            llm_result = llm_analyzer.analyze(schema)
            if llm_result:
                self._merge_llm_results(schema, llm_result)
                logger.info("LLM analysis merged into schema for %s", schema.rater_name)
            else:
                logger.info("LLM analysis unavailable — using heuristics only")
        except Exception as e:
            logger.warning("LLM analysis failed, using heuristics: %s", e)

        try:
            self._run_llm_chain(schema, file_path)
        except Exception as e:
            logger.warning("LLM chain failed, continuing without metadata: %s", e)

    # ── LLM Chain integration ────────────────────────────────────────

    def _run_llm_chain(self, schema: RaterSchema, file_path: Path) -> None:
        """
        Run the 3-step LLM chain and save CalculationMetadata.
        This enriches the schema with output classifications and
        saves formula translations + dependency graph for runtime use.
        """
        from app.services.llm_chain import llm_chain

        chain_result = llm_chain.run(schema, file_path)

        if not chain_result.chain_executed:
            logger.info("LLM chain was not executed (disabled or unavailable)")
            return

        # Build calculation metadata
        metadata = llm_chain.build_metadata(chain_result, schema, file_path.name)

        # Save metadata alongside the workbook
        meta_path = file_path.parent / "calculation_metadata.json"
        meta_path.write_text(
            metadata.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info(
            "Saved calculation metadata: %d final outputs, %d translations, %d dep maps",
            len(metadata.final_output_names),
            len(metadata.formula_translations),
            len(metadata.dependency_graph),
        )

        # Run default calculation smoke test
        self._validate_default_calculation(schema, file_path, metadata)

    def _validate_default_calculation(
        self,
        schema: RaterSchema,
        workbook_path: Path,
        metadata: CalculationMetadata,
    ) -> None:
        """
        Smoke test: do default inputs produce expected default outputs?
        Updates metadata with validation results.
        """
        from app.services.calculation_engine import engine

        rater_id = workbook_path.parent.name
        defaults = {f.name: f.default_value for f in schema.input_fields}

        try:
            result = engine.calculate(
                rater_id=rater_id,
                schema=schema,
                user_inputs=defaults,
                workbook_path=workbook_path,
            )
        except Exception as e:
            logger.warning("Default calculation smoke test failed: %s", e)
            metadata.default_validation_passed = False
            metadata.default_validation_mismatches.append(f"Calculation error: {e}")
            return

        mismatches = []
        for field in schema.output_fields:
            expected = field.default_value
            actual = result.outputs.get(field.name)

            if expected is None or actual is None:
                continue

            try:
                exp_float = float(expected)
                act_float = float(actual)
                if exp_float != 0:
                    error_pct = abs(exp_float - act_float) / abs(exp_float)
                else:
                    error_pct = abs(act_float)

                from app.config import VALIDATION_TOLERANCE
                if error_pct > VALIDATION_TOLERANCE:
                    mismatches.append(
                        f"{field.name}: expected={expected}, got={actual} (error={error_pct:.2%})"
                    )
            except (ValueError, TypeError):
                if str(expected).strip() != str(actual).strip():
                    mismatches.append(
                        f"{field.name}: expected='{expected}', got='{actual}'"
                    )

        metadata.default_validation_passed = len(mismatches) == 0
        metadata.default_validation_mismatches = mismatches

        if mismatches:
            logger.warning(
                "Default calculation validation found %d mismatches: %s",
                len(mismatches), mismatches,
            )
        else:
            logger.info("Default calculation validation PASSED for %s", schema.rater_name)

        # Re-save metadata with validation results
        meta_path = workbook_path.parent / "calculation_metadata.json"
        meta_path.write_text(
            metadata.model_dump_json(indent=2),
            encoding="utf-8",
        )

    # ── LLM result merging ────────────────────────────────────────────

    def _merge_llm_results(self, schema: RaterSchema, llm_result: dict) -> None:
        """
        Overlay LLM classifications onto the schema.
        LLM results override heuristics only when confidence >= 0.8.
        """
        from app.config import LLM_PROVIDER

        classifications = llm_result.get("field_classifications", [])
        clf_map: dict[str, dict] = {c["field_name"]: c for c in classifications}

        overrides_applied = 0
        for field in schema.input_fields:
            clf = clf_map.get(field.name)
            if not clf:
                continue

            confidence = clf.get("confidence", 0.0)

            # Override impacts_output if LLM is confident
            if confidence >= 0.8:
                new_val = clf.get("impacts_premium", field.impacts_output)
                if new_val != field.impacts_output:
                    logger.debug(
                        "LLM override: %s.impacts_output %s → %s (conf=%.2f)",
                        field.name, field.impacts_output, new_val, confidence,
                    )
                    field.impacts_output = new_val
                    overrides_applied += 1

            # Override group if LLM suggests one and is confident
            suggested_group = clf.get("suggested_group", "")
            if suggested_group and confidence >= 0.75:
                field.group = suggested_group

            # Override validation boundaries if LLM suggests them
            sv = clf.get("suggested_validation", {})
            if sv and confidence >= 0.8:
                lo = sv.get("min_value")
                hi = sv.get("max_value")
                if lo is not None or hi is not None:
                    if field.validation is None:
                        field.validation = ValidationRule(required=True)
                    if lo is not None:
                        field.validation.min_value = lo
                    if hi is not None:
                        field.validation.max_value = hi

        # Store the LLM analysis in the schema for transparency
        schema.llm_analysis = LLMAnalysisResult(
            field_classifications=[
                LLMFieldClassification(
                    field_name=c.get("field_name", ""),
                    impacts_premium=c.get("impacts_premium", True),
                    confidence=c.get("confidence", 0.5),
                    reasoning=c.get("reasoning", ""),
                    suggested_group=c.get("suggested_group", ""),
                )
                for c in classifications
            ],
            premium_logic_summary=llm_result.get("premium_logic_summary", {}),
            dependency_graph=llm_result.get("dependency_graph", {}),
            llm_provider=LLM_PROVIDER,
            analyzed=True,
        )

        logger.info(
            "LLM merge: %d classification overrides applied out of %d total",
            overrides_applied, len(classifications),
        )

    # ── Enrichment passes ────────────────────────────────────────────

    def _enrich_options(self, schema: RaterSchema) -> None:
        """
        For SELECT fields with no options yet, attempt to find matching values
        in the extracted lookup tables.
        """
        for field in schema.input_fields:
            if field.field_type == FieldType.SELECT and not field.options:
                # Try to match field name against a lookup table column
                for lt in schema.lookup_tables:
                    if not lt.columns:
                        continue
                    # Does the first column look like it matches this field?
                    first_col = lt.columns[0]
                    if self._columns_match(field.name, first_col):
                        seen = set()
                        for row in lt.rows:
                            val = row.get(first_col)
                            if val is not None and val not in seen:
                                seen.add(val)
                                field.options.append(
                                    FieldOption(label=str(val), value=val)
                                )
                        break

    def _apply_boundary_conditions(self, schema: RaterSchema) -> None:
        """
        Some raters (PAR Model) have explicit boundary-condition cells
        with min/max values.  We look for patterns in the schema itself.

        For the PAR Model specifically, boundary conditions are at cols J-M
        in the Inputs & Outputs sheet — these were already partially captured
        as named ranges (e.g. issue age 18–80, SA 50000–1B).  We embed
        those via generic heuristics.
        """
        # Heuristic min/max by field name patterns
        _bounds: dict[str, tuple[float | None, float | None]] = {
            "Age": (18, 80),
            "Prem_term": (1, 100),
            "mat_age": (50, 120),
            "SumAssured": (50000, 1_000_000_000),
            "SA": (50000, 1_000_000_000),
            "Building_limit": (100_000, 100_000_000),
            "Territory": (1, 50),
        }
        for field in schema.input_fields:
            if field.field_type == FieldType.NUMBER:
                for key, (lo, hi) in _bounds.items():
                    if key.lower() in field.name.lower():
                        field.validation = ValidationRule(
                            required=True, min_value=lo, max_value=hi,
                        )
                        break

    def _ensure_yes_no_selects(self, schema: RaterSchema) -> None:
        """Convert text fields with value 'Yes'/'No' to selects."""
        for field in schema.input_fields:
            if field.field_type == FieldType.TEXT and isinstance(field.default_value, str):
                if field.default_value.strip().lower() in ("yes", "no"):
                    field.field_type = FieldType.SELECT
                    if not field.options:
                        field.options = [
                            FieldOption(label="Yes", value="Yes"),
                            FieldOption(label="No", value="No"),
                        ]

    def _enrich_groups(self, schema: RaterSchema) -> None:
        """
        Re-assign groups using richer heuristics.  The parser already does
        a basic job; we refine here.
        """
        for field in schema.input_fields:
            label_lower = field.label.lower()

            # Insurance-specific groupings
            if any(k in label_lower for k in ("name", "address", "city", "state", "zip", "phone", "url", "web")):
                field.group = "Insured Information"
            elif any(k in label_lower for k in ("class", "revenue", "longevity", "experience", "risk management", "sub-contract")):
                field.group = "Rating Factors"
            elif any(k in label_lower for k in ("individual risk", "profile", "management credential", "disciplinary", "regulatory", "internal control")):
                field.group = "Individual Risk Assessment"
            elif any(k in label_lower for k in ("sex", "gender", "age", "smoking", "issue")):
                field.group = "Policyholder Info"
            elif any(k in label_lower for k in ("premium freq", "premium term", "prem_term", "prem_freq")):
                field.group = "Premium Details"
            elif any(k in label_lower for k in ("sum assured", "death benefit", "maturity", "rider", "benefit")):
                field.group = "Benefit Details"
            elif any(k in label_lower for k in ("underlying", "excess", "attachment", "falcon")):
                field.group = "Layer Structure"
            elif any(k in label_lower for k in ("side a", "run-off", "extended report", "terrorism", "endorsement")):
                field.group = "Modifiers"
            elif any(k in label_lower for k in ("financial condition", "nature of operation", "acquisition", "litigation", "time in business")):
                field.group = "Risk Factors"
            # else keep existing group from parser

    # ── Impact analysis ────────────────────────────────────────────────

    def _mark_impacts_output(self, schema: RaterSchema) -> None:
        """
        Determine which input fields actually impact calculation outputs.

        Uses a combination of:
          1. Formula dependency graph (direct + transitive references).
          2. Heuristic patterns for known non-impacting fields.
          3. Default value inspection (descriptive/label values).

        Fields that don't impact outputs get ``impacts_output = False``
        so the UI can hide or collapse them.
        """
        # --- Build dependency set: all field names any output depends on ---
        dep_names: set[str] = set()
        for fm in schema.formula_mappings:
            dep_names.update(fm.depends_on)

        # Build transitive closure: if field A is depended on by output O,
        # and field B's formula references A, then B also impacts output.
        changed = True
        while changed:
            changed = False
            for fm in schema.formula_mappings:
                if fm.output_name in dep_names:
                    for d in fm.depends_on:
                        if d not in dep_names:
                            dep_names.add(d)
                            changed = True

        # If the dependency analysis found a meaningful set of deps that covers
        # a reasonable portion of input fields, it's usable for exclusion.
        # Otherwise the regex-based extraction missed cross-sheet references
        # and we should NOT use it to disqualify fields.
        input_names = {f.name for f in schema.input_fields}
        coverage = len(dep_names & input_names)
        has_reliable_deps = (
            coverage >= 3
            and len(input_names) > 0
            and coverage / len(input_names) >= 0.25
        )

        for field in schema.input_fields:
            name_lower = field.name.lower()
            label_lower = field.label.lower()
            default_lower = str(field.default_value or "").lower().strip()

            # --- Rule 1: Known info/personal keywords in name or label ---
            if any(kw in name_lower or kw in label_lower for kw in _INFO_NAME_KEYWORDS):
                field.impacts_output = False
                continue

            # --- Rule 2: Internal lookup slugs / header labels ---
            if _INTERNAL_NAME_PATTERNS.match(field.name):
                field.impacts_output = False
                continue

            # --- Rule 3: Default value is a short descriptive label ---
            if default_lower in _DESCRIPTIVE_DEFAULTS:
                field.impacts_output = False
                continue

            # --- Rule 4: Default is a very long descriptive string ---
            if isinstance(field.default_value, str) and len(field.default_value) > 80:
                field.impacts_output = False
                continue

            # --- Rule 4b: Known rating-input keywords override Rule 5 ---
            # Fields like "age", "sex", "smoking" are almost always rating
            # inputs; the dependency regex often misses indirect refs.
            if any(kw in name_lower or kw in label_lower for kw in _RATING_INPUT_KEYWORDS):
                field.impacts_output = True
                continue

            # --- Rule 5: Formula dependency analysis (only if reliable) ---
            # If we have meaningful dependency data and this field is NOT
            # referenced by any output, it likely doesn't affect results.
            if has_reliable_deps and field.name not in dep_names:
                field.impacts_output = False
                continue

            # Passes all checks → impacts output
            field.impacts_output = True

    # ── Utilities ────────────────────────────────────────────────────

    @staticmethod
    def _columns_match(field_name: str, column_name: str) -> bool:
        """Fuzzy check if a field name likely corresponds to a table column."""
        fn = field_name.lower().replace("_", " ")
        cn = column_name.lower().replace("_", " ")
        return fn in cn or cn in fn
