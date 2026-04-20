"""
LLM Chain — Upload-Time Multi-Step Analysis
=============================================
Orchestrates a 3-step LLM chain that runs ONCE at upload time:

  Step 1: Smart Output Identifier
    → Classify detected outputs as final premium, intermediate, or display
    → Reduces output bloat (e.g. Excess 63 → ~4 final outputs)

  Step 2: Dependency Graph Builder
    → Build precise input→output dependency mappings
    → Traces cross-sheet formula chains

  Step 3: Formula Translator
    → Convert unsupported Excel formulas (OFFSET+MATCH, deep VLOOKUPs)
      to equivalent Python expressions
    → Validated against known default outputs

Results are saved as calculation_metadata.json alongside schema.json.
NO LLM calls happen at runtime — only at upload time.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.models.schemas import (
    CalculationMetadata,
    ChainResult,
    DependencyInfo,
    FormulaTranslation,
    OutputClassification,
    RaterSchema,
)

logger = logging.getLogger(__name__)

# ── System prompts for each chain step ───────────────────────────────

_STEP1_SYSTEM = """\
You are an Excel workbook analyst specializing in insurance rater spreadsheets.
Your task is to classify detected output cells into three categories:

1. **final** — Terminal premium outputs (the actual premium numbers shown to users).
   These cells are NOT referenced by other formula cells. They are the end of the
   calculation chain.

2. **intermediate** — Cells used in premium calculation but not shown to users.
   These are factors, rates, subtotals that feed into final outputs.

3. **display** — Worth showing as premium breakdown components, but not the
   final total premium. E.g. "Base Premium", "Tax Amount", "Surcharge".

STRICT RULES:
- Base ALL classifications on the provided data ONLY.
- Every "final" output should be a terminal node — no other output formula references it.
- If uncertain, classify as "display" rather than "final".
- Return ONLY valid JSON — no markdown, no explanation outside JSON.
"""

_STEP1_USER = """\
Classify these detected output fields from the rater "{rater_name}".

SHEETS:
{sheets_json}

ALL DETECTED OUTPUTS ({output_count} total):
{outputs_json}

FORMULA MAPPINGS (showing which outputs reference other cells):
{formula_json}

Return a JSON object:
{{
  "classifications": [
    {{
      "name": "<exact field name>",
      "cell_ref": "<cell reference>",
      "sheet": "<sheet name>",
      "category": "final" | "intermediate" | "display",
      "reasoning": "<brief explanation>"
    }}
  ]
}}

Classify ALL {output_count} outputs listed above.
"""

_STEP2_SYSTEM = """\
You are an Excel formula dependency analyst. Given a set of final output cells and
all formula mappings from an insurance rater workbook, trace the complete dependency
chain from each final output back to the user input cells.

STRICT RULES:
- Only reference field names and cell references that exist in the provided data.
- Do NOT invent field names.
- Trace through intermediate formulas to find ALL input dependencies.
- Return ONLY valid JSON.
"""

_STEP2_USER = """\
Build the dependency graph for this rater "{rater_name}".

FINAL OUTPUTS:
{final_outputs_json}

ALL FORMULA MAPPINGS:
{formula_json}

INPUT FIELDS:
{inputs_json}

Return a JSON object:
{{
  "dependency_graph": {{
    "<output_field_name>": {{
      "direct_dependencies": ["<field names of direct formula inputs>"],
      "all_input_dependencies": ["<all input field names that affect this output>"],
      "formula_chain": ["<human-readable formula chain description>"]
    }}
  }}
}}

Map ALL final outputs listed above.
"""

_STEP3_SYSTEM = """\
You are an Excel-to-Python formula translator. You convert Excel formulas that
cannot be evaluated by the `formulas` Python library into equivalent Python
expressions.

The Python expressions will execute in a sandbox with these available variables:
- `inputs`: dict mapping field names to their values
- `lookup_data`: dict mapping sheet names to pandas DataFrames of lookup tables
- Standard math functions: round, abs, min, max, sum, int, float, str, len

STRICT RULES:
- The Python expression must be deterministic.
- Do NOT use exec, eval, __import__, or any dangerous functions.
- Use only the variables listed above.
- Return ONLY valid JSON.
- Include a confidence score (0.0-1.0) based on formula complexity.
"""

_STEP3_USER = """\
Translate these Excel formulas to Python for rater "{rater_name}".

FORMULAS TO TRANSLATE:
{formulas_json}

CONTEXT:
- Named ranges / input mappings:
{named_ranges_json}
- Lookup table headers (sample):
{lookup_headers_json}

Expected default results (for validation):
{defaults_json}

Return a JSON object:
{{
  "translations": [
    {{
      "output_name": "<field name>",
      "cell_ref": "<cell reference>",
      "original_formula": "<the Excel formula>",
      "python_expression": "<equivalent Python expression>",
      "dependencies": ["<input field names used>"],
      "confidence": 0.0-1.0
    }}
  ]
}}
"""


def _get_llm():
    """Get an LLM instance. Returns None if unavailable."""
    from app.config import LLM_API_KEY, LLM_MODEL_GOOGLE, LLM_MODEL_OPENAI, LLM_PROVIDER

    if not LLM_API_KEY:
        return None

    try:
        if LLM_PROVIDER == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=LLM_MODEL_GOOGLE,
                google_api_key=LLM_API_KEY,
                temperature=0.1,
            )
        elif LLM_PROVIDER == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=LLM_MODEL_OPENAI,
                api_key=LLM_API_KEY,
                temperature=0.1,
            )
    except Exception as e:
        logger.warning("Failed to initialize LLM for chain: %s", e)
    return None


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip().startswith("```"):
                end = i
                break
        text = "\n".join(lines[start:end])
    return json.loads(text)


class LLMChain:
    """
    3-step LLM chain for upload-time analysis.
    Called from SchemaGenerator after initial parse and enrichment.
    Results are saved as CalculationMetadata for runtime use.
    """

    def run(self, schema: RaterSchema, workbook_path: Path) -> ChainResult:
        """
        Execute the full 3-step chain.
        Returns ChainResult with classifications, dependency graph, and translations.
        Falls back gracefully if LLM is unavailable.
        """
        from app.config import CHAIN_ENABLED

        result = ChainResult()

        if not CHAIN_ENABLED:
            logger.info("LLM chain disabled via config")
            return result

        llm = _get_llm()
        if llm is None:
            logger.info("LLM unavailable — chain skipped")
            return result

        # Step 1: Classify outputs
        try:
            classifications = self._step1_identify_outputs(llm, schema)
            result.output_classifications = classifications
            logger.info(
                "Chain Step 1 complete: %d final, %d intermediate, %d display",
                sum(1 for c in classifications if c.category == "final"),
                sum(1 for c in classifications if c.category == "intermediate"),
                sum(1 for c in classifications if c.category == "display"),
            )
        except Exception as e:
            logger.warning("Chain Step 1 (output identification) failed: %s", e)
            result.chain_errors.append(f"Step 1 failed: {e}")

        # Step 2: Build dependency graph
        try:
            dep_graph = self._step2_build_dependencies(llm, schema, result.output_classifications)
            result.dependency_graph = dep_graph
            logger.info("Chain Step 2 complete: %d output dependency maps", len(dep_graph))
        except Exception as e:
            logger.warning("Chain Step 2 (dependency graph) failed: %s", e)
            result.chain_errors.append(f"Step 2 failed: {e}")

        # Step 3: Translate unsupported formulas
        try:
            translations = self._step3_translate_formulas(llm, schema, workbook_path)
            result.formula_translations = translations
            logger.info(
                "Chain Step 3 complete: %d formula translations (%d validated)",
                len(translations),
                sum(1 for t in translations if t.validated),
            )
        except Exception as e:
            logger.warning("Chain Step 3 (formula translation) failed: %s", e)
            result.chain_errors.append(f"Step 3 failed: {e}")

        result.chain_executed = True
        return result

    # ── Step 1: Smart Output Identifier ──────────────────────────────

    def _step1_identify_outputs(
        self, llm: Any, schema: RaterSchema,
    ) -> list[OutputClassification]:
        """Classify output fields as final/intermediate/display."""
        from langchain_core.messages import HumanMessage, SystemMessage

        # Build context
        sheets_json = json.dumps([
            {"name": s.sheet_name, "role": s.role.value, "rows": s.row_count}
            for s in schema.sheets
        ], indent=2)

        outputs_json = json.dumps([
            {
                "name": f.name,
                "label": f.label,
                "sheet": f.sheet,
                "cell_ref": f.cell_ref,
                "formula": f.formula or "(static value)",
                "default_value": str(f.default_value) if f.default_value is not None else "N/A",
            }
            for f in schema.output_fields
        ], indent=2, default=str)

        formula_json = json.dumps([
            {
                "output_name": fm.output_name,
                "cell_ref": fm.cell_ref,
                "formula": fm.formula,
                "depends_on": fm.depends_on,
            }
            for fm in schema.formula_mappings
        ], indent=2)

        user_prompt = _STEP1_USER.format(
            rater_name=schema.rater_name,
            sheets_json=sheets_json,
            output_count=len(schema.output_fields),
            outputs_json=outputs_json,
            formula_json=formula_json,
        )

        messages = [
            SystemMessage(content=_STEP1_SYSTEM),
            HumanMessage(content=user_prompt),
        ]

        logger.info("Chain Step 1: calling LLM to classify %d outputs…", len(schema.output_fields))
        response = llm.invoke(messages)
        parsed = _extract_json(response.content)

        # Validate and build OutputClassification objects
        valid_names = {f.name for f in schema.output_fields}
        classifications = []
        for item in parsed.get("classifications", []):
            name = item.get("name", "")
            if name not in valid_names:
                logger.debug("Step 1: LLM referenced unknown output '%s' — skipped", name)
                continue
            category = item.get("category", "display")
            if category not in ("final", "intermediate", "display"):
                category = "display"
            classifications.append(OutputClassification(
                name=name,
                cell_ref=item.get("cell_ref", ""),
                sheet=item.get("sheet", ""),
                category=category,
                reasoning=item.get("reasoning", ""),
            ))

        # If LLM didn't classify some outputs, default them to "display"
        classified_names = {c.name for c in classifications}
        for f in schema.output_fields:
            if f.name not in classified_names:
                classifications.append(OutputClassification(
                    name=f.name,
                    cell_ref=f.cell_ref,
                    sheet=f.sheet,
                    category="display",
                    reasoning="Not classified by LLM — defaulted to display",
                ))

        # Validation: ensure at least one "final" output exists
        final_count = sum(1 for c in classifications if c.category == "final")
        if final_count == 0 and classifications:
            # Promote all "display" to "final" — better to calculate all than none
            logger.warning("Step 1: No final outputs identified — promoting all display to final")
            for c in classifications:
                if c.category == "display":
                    c.category = "final"

        return classifications

    # ── Step 2: Dependency Graph Builder ─────────────────────────────

    def _step2_build_dependencies(
        self,
        llm: Any,
        schema: RaterSchema,
        classifications: list[OutputClassification],
    ) -> dict[str, DependencyInfo]:
        """Build dependency graph for final outputs."""
        from langchain_core.messages import HumanMessage, SystemMessage

        final_outputs = [c for c in classifications if c.category == "final"]
        if not final_outputs:
            # Fall back to all output fields
            final_outputs = [
                OutputClassification(name=f.name, cell_ref=f.cell_ref, sheet=f.sheet, category="final")
                for f in schema.output_fields
            ]

        final_outputs_json = json.dumps([
            {"name": fo.name, "cell_ref": fo.cell_ref, "sheet": fo.sheet}
            for fo in final_outputs
        ], indent=2)

        formula_json = json.dumps([
            {
                "output_name": fm.output_name,
                "cell_ref": fm.cell_ref,
                "formula": fm.formula,
                "depends_on": fm.depends_on,
            }
            for fm in schema.formula_mappings
        ], indent=2)

        inputs_json = json.dumps([
            {"name": f.name, "cell_ref": f.cell_ref, "sheet": f.sheet}
            for f in schema.input_fields
        ], indent=2)

        user_prompt = _STEP2_USER.format(
            rater_name=schema.rater_name,
            final_outputs_json=final_outputs_json,
            formula_json=formula_json,
            inputs_json=inputs_json,
        )

        messages = [
            SystemMessage(content=_STEP2_SYSTEM),
            HumanMessage(content=user_prompt),
        ]

        logger.info("Chain Step 2: calling LLM to build dependency graph for %d outputs…", len(final_outputs))
        response = llm.invoke(messages)
        parsed = _extract_json(response.content)

        # Validate: only keep fields that actually exist in schema
        known_input_names = {f.name for f in schema.input_fields}
        known_output_names = {f.name for f in schema.output_fields}

        dep_graph: dict[str, DependencyInfo] = {}
        for output_name, info in parsed.get("dependency_graph", {}).items():
            if output_name not in known_output_names:
                continue
            # Filter dependency lists to known fields only
            direct = [d for d in info.get("direct_dependencies", [])
                      if d in known_input_names or d in known_output_names]
            all_inputs = [d for d in info.get("all_input_dependencies", [])
                         if d in known_input_names]
            chain = info.get("formula_chain", [])

            dep_graph[output_name] = DependencyInfo(
                direct_dependencies=direct,
                all_input_dependencies=all_inputs,
                formula_chain=chain[:20],  # cap chain length
            )

        return dep_graph

    # ── Step 3: Formula Translator ───────────────────────────────────

    def _step3_translate_formulas(
        self,
        llm: Any,
        schema: RaterSchema,
        workbook_path: Path,
    ) -> list[FormulaTranslation]:
        """Translate unsupported Excel formulas to Python expressions."""
        from langchain_core.messages import HumanMessage, SystemMessage

        # Identify formulas that might need translation
        # (those containing OFFSET, INDIRECT, complex nested functions)
        _UNSUPPORTED_PATTERNS = [
            "OFFSET", "INDIRECT", "INDEX(", "MATCH(",
        ]
        formulas_to_translate = []
        for fm in schema.formula_mappings:
            formula_upper = fm.formula.upper()
            if any(pat in formula_upper for pat in _UNSUPPORTED_PATTERNS):
                # Find the corresponding output field for default value
                default_val = None
                for f in schema.output_fields:
                    if f.name == fm.output_name:
                        default_val = f.default_value
                        break
                formulas_to_translate.append({
                    "output_name": fm.output_name,
                    "cell_ref": fm.cell_ref,
                    "formula": fm.formula,
                    "depends_on": fm.depends_on,
                    "expected_default": str(default_val) if default_val is not None else None,
                })

        if not formulas_to_translate:
            logger.info("Chain Step 3: no unsupported formulas detected — skipping")
            return []

        # Build context for named ranges / inputs
        named_ranges_json = json.dumps({
            f.name: {"cell_ref": f.cell_ref, "sheet": f.sheet, "default": str(f.default_value)}
            for f in schema.input_fields
        }, indent=2, default=str)

        # Lookup table headers (sample)
        lookup_headers = {}
        for lt in schema.lookup_tables:
            lookup_headers[lt.name] = {
                "sheet": lt.sheet,
                "columns": lt.columns[:20],
                "sample_row": lt.rows[0] if lt.rows else {},
                "total_rows": len(lt.rows),
            }
        lookup_headers_json = json.dumps(lookup_headers, indent=2, default=str)

        defaults_json = json.dumps({
            ft["output_name"]: ft["expected_default"]
            for ft in formulas_to_translate
            if ft["expected_default"]
        }, indent=2)

        user_prompt = _STEP3_USER.format(
            rater_name=schema.rater_name,
            formulas_json=json.dumps(formulas_to_translate, indent=2),
            named_ranges_json=named_ranges_json,
            lookup_headers_json=lookup_headers_json,
            defaults_json=defaults_json,
        )

        messages = [
            SystemMessage(content=_STEP3_SYSTEM),
            HumanMessage(content=user_prompt),
        ]

        logger.info(
            "Chain Step 3: calling LLM to translate %d unsupported formulas…",
            len(formulas_to_translate),
        )
        response = llm.invoke(messages)
        parsed = _extract_json(response.content)

        from app.config import FORMULA_TRANSLATION_MIN_CONFIDENCE

        translations = []
        for item in parsed.get("translations", []):
            confidence = item.get("confidence", 0.0)
            if confidence < FORMULA_TRANSLATION_MIN_CONFIDENCE:
                logger.debug(
                    "Step 3: translation for '%s' below confidence threshold (%.2f) — skipped",
                    item.get("output_name"), confidence,
                )
                continue

            translation = FormulaTranslation(
                output_name=item.get("output_name", ""),
                cell_ref=item.get("cell_ref", ""),
                original_formula=item.get("original_formula", ""),
                python_expression=item.get("python_expression", ""),
                dependencies=item.get("dependencies", []),
                confidence=confidence,
                validated=False,
            )

            # Validate the translation against expected defaults
            translation = self._validate_translation(translation, schema)
            translations.append(translation)

        return translations

    def _validate_translation(
        self, translation: FormulaTranslation, schema: RaterSchema,
    ) -> FormulaTranslation:
        """
        Validate a translated formula by executing it with default inputs
        and comparing against the known default output value.
        """
        from app.config import VALIDATION_TOLERANCE

        # Find expected default value
        expected = None
        for f in schema.output_fields:
            if f.name == translation.output_name:
                expected = f.default_value
                break

        if expected is None or not translation.python_expression:
            translation.validation_error = "No default value to validate against"
            return translation

        # Build default inputs dict
        default_inputs = {
            f.name: f.default_value for f in schema.input_fields
        }

        try:
            from app.services.formula_runtime import FormulaRuntime
            runtime = FormulaRuntime()
            actual = runtime.execute_expression(
                translation.python_expression,
                default_inputs,
                {},  # no lookup data at validation time
            )

            if actual is not None and expected is not None:
                try:
                    exp_float = float(expected)
                    act_float = float(actual)
                    if exp_float != 0:
                        error_pct = abs(exp_float - act_float) / abs(exp_float)
                    else:
                        error_pct = abs(act_float)

                    if error_pct <= VALIDATION_TOLERANCE:
                        translation.validated = True
                        logger.info(
                            "Step 3 validation PASSED for '%s': expected=%s, got=%s (error=%.4f%%)",
                            translation.output_name, expected, actual, error_pct * 100,
                        )
                    else:
                        translation.validation_error = (
                            f"Mismatch: expected={expected}, got={actual} (error={error_pct:.2%})"
                        )
                        logger.warning(
                            "Step 3 validation FAILED for '%s': %s",
                            translation.output_name, translation.validation_error,
                        )
                except (ValueError, TypeError):
                    # Non-numeric comparison
                    if str(actual).strip() == str(expected).strip():
                        translation.validated = True
                    else:
                        translation.validation_error = (
                            f"Non-numeric mismatch: expected={expected}, got={actual}"
                        )
        except Exception as e:
            translation.validation_error = f"Execution error: {e}"
            logger.warning(
                "Step 3 validation ERROR for '%s': %s",
                translation.output_name, e,
            )

        return translation

    # ── Build CalculationMetadata from ChainResult ───────────────────

    @staticmethod
    def build_metadata(
        chain_result: ChainResult,
        schema: RaterSchema,
        filename: str,
    ) -> CalculationMetadata:
        """
        Convert ChainResult into CalculationMetadata for runtime use.
        """
        from app.services.calculation_engine import _build_cell_key

        final_names = []
        intermediate_names = []
        display_names = []
        final_keys = []

        for clf in chain_result.output_classifications:
            if clf.category == "final":
                final_names.append(clf.name)
                # Build cell key for formulas library
                if clf.cell_ref and clf.sheet:
                    final_keys.append(
                        _build_cell_key(filename, clf.sheet, clf.cell_ref)
                    )
            elif clf.category == "intermediate":
                intermediate_names.append(clf.name)
            else:
                display_names.append(clf.name)

        # If no final outputs from chain, use all output fields
        if not final_names:
            for f in schema.output_fields:
                final_names.append(f.name)
                if f.cell_ref and f.sheet:
                    final_keys.append(
                        _build_cell_key(filename, f.sheet, f.cell_ref)
                    )

        return CalculationMetadata(
            final_output_keys=final_keys,
            final_output_names=final_names,
            intermediate_output_names=intermediate_names,
            display_output_names=display_names,
            formula_translations=chain_result.formula_translations,
            dependency_graph=chain_result.dependency_graph,
        )


# ── Module-level singleton ───────────────────────────────────────────
llm_chain = LLMChain()
