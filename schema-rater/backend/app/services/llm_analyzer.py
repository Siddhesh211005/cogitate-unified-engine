"""
LLM Schema Analyzer — Parse-Time Only
=======================================
Uses an LLM (Google Gemini or OpenAI) at upload time to:
  1. Classify input fields as rating-inputs vs informational
  2. Trace formula dependency chains for premium calculation
  3. Suggest boundary conditions from actual lookup table data
  4. Assign semantic field groupings

Called ONCE per rater upload. Results are validated by guardrails
and merged into the RaterSchema. No LLM calls happen at runtime.

Guardrails:
  - Only parsed schema data is sent (no raw Excel, no file paths)
  - LLM output is validated against actual field names & formula refs
  - Falls back to heuristics if LLM is unavailable or returns garbage
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.models.schemas import RaterSchema
from app.services.guardrails import InputGuardrail, OutputGuardrail

logger = logging.getLogger(__name__)

# ── System prompt — strict data-only analysis ────────────────────────────

_SYSTEM_PROMPT = """\
You are an Excel workbook structure analyzer for insurance rater spreadsheets.

You will receive a JSON summary of fields, formulas, cell references, and
lookup tables extracted from an Excel-based insurance rating workbook.

YOUR TASK:
1. Classify each INPUT field: does it affect premium calculation or is it
   purely informational (e.g. insured name, address, agent info)?
2. Identify the primary premium output field(s) and trace which inputs
   drive them through the formula chain.
3. Suggest logical UI groupings for the input fields.
4. Where lookup tables reveal valid ranges (e.g. age 18-80), suggest
   boundary conditions.

STRICT RULES:
1. Base ALL classifications ONLY on the provided JSON data.
2. Do NOT use any external knowledge about insurance pricing or industry.
3. If a field's purpose is ambiguous from the data, set confidence below 0.6.
4. Every "impacts_premium" = true claim MUST trace back to a formula or
   cell reference in the provided data.
5. Do NOT invent field names that aren't in the input data.
6. Return ONLY valid JSON matching the required schema — no markdown, no
   explanation text outside the JSON.
"""

_USER_PROMPT_TEMPLATE = """\
Analyze this insurance rater workbook data and classify each input field.

WORKBOOK DATA:
{schema_json}

Return a JSON object with this exact structure:
{{
  "field_classifications": [
    {{
      "field_name": "<exact name from input data>",
      "impacts_premium": true/false,
      "confidence": 0.0-1.0,
      "reasoning": "<brief explanation referencing specific cells/formulas>",
      "suggested_group": "<UI group name>",
      "suggested_validation": {{
        "required": true/false,
        "min_value": <number or null>,
        "max_value": <number or null>
      }}
    }}
  ],
  "premium_logic_summary": {{
    "primary_outputs": ["<output field names that represent final premium>"],
    "key_drivers": ["<top input field names that most affect premium>"],
    "formula_chain_description": "<brief description of how inputs flow to premium>"
  }},
  "dependency_graph": {{
    "<output_field_name>": {{
      "direct_inputs": ["<field names>"],
      "lookup_tables_used": ["<table names>"]
    }}
  }}
}}

Classify ALL input fields listed in the data. Be precise with field_name
— use the exact "name" values from the fields array.
"""


def _get_llm():
    """
    Lazily construct the LLM instance based on config.
    Returns None if credentials are missing.
    """
    from app.config import LLM_API_KEY, LLM_MODEL_GOOGLE, LLM_MODEL_OPENAI, LLM_PROVIDER

    if not LLM_API_KEY:
        logger.warning("LLM_API_KEY not set — LLM analysis disabled")
        return None

    try:
        if LLM_PROVIDER == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=LLM_MODEL_GOOGLE,
                google_api_key=LLM_API_KEY,
                temperature=0.1,  # low temp for structured analysis
            )
        elif LLM_PROVIDER == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=LLM_MODEL_OPENAI,
                api_key=LLM_API_KEY,
                temperature=0.1,
            )
        else:
            logger.warning("Unknown LLM_PROVIDER '%s' — falling back", LLM_PROVIDER)
            return None
    except Exception as e:
        logger.warning("Failed to initialize LLM: %s", e)
        return None


class LLMSchemaAnalyzer:
    """
    One-shot LLM analysis of a parsed RaterSchema.
    Called during upload; results cached in schema JSON.
    """

    def __init__(self):
        self._input_guard = InputGuardrail()
        self._output_guard = OutputGuardrail()

    def analyze(self, schema: RaterSchema) -> dict[str, Any] | None:
        """
        Run LLM analysis on the parsed schema.

        Returns validated analysis dict, or None if LLM is unavailable
        or analysis fails (caller should fall back to heuristics).
        """
        from app.config import LLM_ENABLED

        if not LLM_ENABLED:
            logger.info("LLM analysis disabled via config")
            return None

        llm = _get_llm()
        if llm is None:
            return None

        # ── Build sanitized prompt data ──────────────────────────────
        prompt_data = self._input_guard.build_prompt_data(schema)
        schema_json = json.dumps(prompt_data, indent=2, default=str)

        # Guard against excessively large prompts (>100k chars ≈ 25k tokens)
        if len(schema_json) > 100_000:
            logger.warning(
                "Schema data too large for LLM (%d chars) — truncating lookup tables",
                len(schema_json),
            )
            # Remove lookup table rows to reduce size
            for lt in prompt_data.get("lookup_tables", []):
                lt["sample_rows"] = lt["sample_rows"][:3]
            schema_json = json.dumps(prompt_data, indent=2, default=str)

        user_prompt = _USER_PROMPT_TEMPLATE.format(schema_json=schema_json)

        # ── Call LLM ─────────────────────────────────────────────────
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]

            logger.info(
                "Calling LLM for schema analysis (%d input fields, %d output fields, %d chars)…",
                len(schema.input_fields),
                len(schema.output_fields),
                len(schema_json),
            )

            response = llm.invoke(messages)
            raw_text = response.content

            logger.info("LLM response received (%d chars)", len(raw_text))

        except Exception as e:
            logger.warning("LLM call failed: %s — falling back to heuristics", e)
            return None

        # ── Parse JSON from response ─────────────────────────────────
        try:
            parsed = self._extract_json(raw_text)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse LLM JSON output: %s", e)
            logger.debug("Raw LLM output:\n%s", raw_text[:2000])
            return None

        # ── Validate through output guardrails ───────────────────────
        validated = self._output_guard.validate(parsed, schema)

        if not validated.get("field_classifications"):
            logger.warning("LLM returned no valid field classifications")
            return None

        logger.info(
            "LLM analysis complete: %d valid classifications, key drivers: %s",
            len(validated["field_classifications"]),
            validated.get("premium_logic_summary", {}).get("key_drivers", []),
        )

        return validated

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON from LLM response, handling markdown code fences."""
        text = text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            # Remove first line (```json or ```)
            lines = text.split("\n")
            start = 1
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip().startswith("```"):
                    end = i
                    break
            text = "\n".join(lines[start:end])

        return json.loads(text)


# ── Module-level singleton ───────────────────────────────────────────────
llm_analyzer = LLMSchemaAnalyzer()
