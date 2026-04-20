"""
Calculation Engine
==================
Evaluates Excel rater formulas in Python using the `formulas` library.
Loads an ExcelModel, maps user inputs to cell references, calculates,
and extracts output values.

Key discovery from testing:
  - formulas.ExcelModel().loads(path).finish() → compiled model
  - xl.calculate(inputs={key: value}) → Solution dict
  - Keys format: "'[filename]SHEETNAME'!CELL"
  - Values are Ranges objects: [[value]]

See docs/ARCHITECTURE.md §4 and docs/IMPLEMENTATION_PLAN.md §1.3.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import json
import logging
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import formulas
import numpy as np
import openpyxl

from app.models.schemas import (
    CalculationMetadata,
    CalculationResult,
    RaterField,
    RaterSchema,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ranges_to_value(val: Any) -> Any:
    """
    Extract a scalar from a formulas Ranges object.
    Ranges wraps values as numpy arrays, e.g. [[17199.0]].
    """
    if val is None:
        return None
    # If it's a Ranges object, get the underlying value
    if hasattr(val, "value"):
        inner = val.value
    else:
        inner = val

    # Unwrap numpy arrays
    if isinstance(inner, np.ndarray):
        if inner.size == 1:
            return _convert_numpy(inner.flat[0])
        return [_convert_numpy(x) for x in inner.flat]

    # Unwrap nested lists/tuples
    if isinstance(inner, (list, tuple)):
        flat = inner
        while isinstance(flat, (list, tuple)) and len(flat) == 1:
            flat = flat[0]
        return _convert_numpy(flat)

    return _convert_numpy(inner)


def _convert_numpy(val: Any) -> Any:
    """Convert numpy scalars and datetime to Python natives for JSON serialization."""
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, np.ndarray):
        if val.size == 1:
            return _convert_numpy(val.flat[0])
        return [_convert_numpy(x) for x in val.flat]
    if isinstance(val, datetime.datetime):
        return val.strftime("%m/%d/%Y")
    if isinstance(val, datetime.date):
        return val.strftime("%m/%d/%Y")
    return val


# ---------------------------------------------------------------------------
# OFFSET → INDEX rewriter  (formulas library does not implement OFFSET)
# ---------------------------------------------------------------------------

def _split_args_top_level(s: str) -> list[str]:
    """Split a comma-separated arg string honouring nested parentheses/brackets."""
    args: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in s:
        if ch in ('(', '['):
            depth += 1
            buf.append(ch)
        elif ch in (')', ']'):
            depth -= 1
            buf.append(ch)
        elif ch == ',' and depth == 0:
            args.append(''.join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        args.append(''.join(buf))
    return args


def _col_letters_to_num(col_letters: str) -> int:
    """Convert Excel column letters (A, B, AA, …) to 1-based column number."""
    col_letters = col_letters.upper().strip("$")
    n = 0
    for ch in col_letters:
        n = n * 26 + (ord(ch) - ord('A') + 1)
    return n


def _rewrite_offset_to_index(formula: str) -> tuple[str, int]:
    """
    Rewrite every OFFSET(ref, rows, cols) call in *formula* to an equivalent
    INDEX expression that the formulas library can evaluate.

    Strategy: anchor the INDEX array at the OFFSET reference cell itself, so
    that row/column expressions become 1-based offsets within the range — no
    absolute sheet-row/column arithmetic needed:

        OFFSET(Sheet!$B$4, rows_expr, cols_expr)
        → INDEX(Sheet!$B$4:$AD$500, rows_expr+1, cols_expr+1)

    Row 1 of the INDEX range equals the anchor cell ($B$4), row 2 is one
    row below, etc.  For the MATCH result convention the caller uses, adding
    1 to both expressions yields the correct relative index.

    Returns (new_formula, number_of_replacements).
    Only rewrites when the first argument is a concrete cell reference
    (e.g. Sheet!$B$4); complex expressions are left unchanged.
    """
    import re as _re
    _CELL_RE = _re.compile(
        r"^(?P<sheet>'[^']+'|[\w ]+)?!?\$?(?P<col>[A-Za-z]{1,3})\$?(?P<row>\d{1,7})$"
    )

    result: list[str] = []
    i = 0
    count = 0
    fu = formula.upper()

    while i < len(formula):
        idx = fu.find('OFFSET(', i)
        if idx == -1:
            result.append(formula[i:])
            break

        # Reject if preceded by a word character (e.g. "XOFFSET")
        if idx > 0 and (formula[idx - 1].isalpha() or formula[idx - 1] == '_'):
            result.append(formula[i:idx + 1])
            i = idx + 1
            continue

        result.append(formula[i:idx])   # text before OFFSET(
        paren_open = idx + 7            # skip 'OFFSET('

        # Find matching close-paren
        depth = 1
        j = paren_open
        while j < len(formula) and depth > 0:
            if formula[j] == '(':
                depth += 1
            elif formula[j] == ')':
                depth -= 1
            j += 1

        if depth != 0:                  # unbalanced — leave as-is
            result.append(formula[idx:j])
            i = j
            continue

        content = formula[paren_open:j - 1]
        args = _split_args_top_level(content)

        if len(args) < 3:
            result.append(formula[idx:j])
            i = j
            continue

        ref_arg  = args[0].strip()
        rows_arg = args[1].strip()
        cols_arg = args[2].strip()

        # Only rewrite when ref_arg is a concrete cell reference
        if not _CELL_RE.match(ref_arg):
            result.append(formula[idx:j])
            i = j
            continue

        # Build INDEX replacement:
        #   Array anchored at ref_arg through a reasonable extent ($AD$500).
        #   INDEX row 1 = ref_arg cell, so we add +1 to both offset expressions
        #   (converting 0-based OFFSET semantics to 1-based INDEX row/col).
        #   $AD$500 covers 30 columns × 500 rows — ample for typical rate tables.
        index_expr = (
            f"INDEX({ref_arg}:$AD$500,"
            f"({rows_arg})+1,"
            f"({cols_arg})+1)"
        )
        result.append(index_expr)
        count += 1
        i = j

    return ''.join(result), count


def _build_cell_key(filename: str, sheet: str, cell_ref: str) -> str:
    """
    Build the key format that formulas library expects:
      "'[filename]SHEETNAME'!CELL"
    formulas uppercases sheet names and strips dollar signs from cell refs.
    """
    clean_ref = cell_ref.replace("$", "")
    return f"'[{filename}]{sheet.upper()}'!{clean_ref}"


def _normalize_key(key: str) -> str:
    """Normalize a solution key for case-insensitive, dollar-sign-free comparison."""
    return key.upper().replace("$", "")


# Regex patterns that identify unresolved formula / cell-reference strings
import re as _re

_EXCEL_FUNC_RE = _re.compile(
    r"\b(VLOOKUP|HLOOKUP|INDEX|MATCH|IF|SUM|SUMIF|SUMIFS|COUNTIF|COUNTIFS|"
    r"AVERAGE|MIN|MAX|LEFT|RIGHT|MID|LEN|CONCATENATE|ROUND|IFERROR|AND|OR|"
    r"NOT|TRIM|UPPER|LOWER|CHOOSE|OFFSET|INDIRECT|LOOKUP|TEXT|VALUE|DATE|"
    r"YEAR|MONTH|DAY|TODAY|NOW|EOMONTH|DATEDIF|NETWORKDAYS|LARGE|SMALL|"
    r"RANK|PERCENTILE|STDEV|VAR|ABS|CEILING|FLOOR|MOD|POWER|SQRT|LOG|"
    r"EXP|SUBSTITUTE|REPLACE|FIND|SEARCH|EXACT|PROPER|REPT|CHAR|CODE|"
    r"ROWS|COLUMNS|COUNTA|COUNTBLANK|SUMPRODUCT|TRANSPOSE|HYPERLINK|"
    r"ISNUMBER|ISTEXT|ISBLANK|ISERROR|NA|TYPE)\s*\(",
    _re.IGNORECASE,
)
_CELL_REF_FORMULA_RE = _re.compile(
    r"^[A-Za-z_!',\[\]\s]*[A-Z]{1,3}\d{1,7}\s*[\*\+\-\/\^]\s*[A-Z]{1,3}\d{1,7}",
    _re.IGNORECASE,
)
_SHEET_REF_RE = _re.compile(
    r"[A-Za-z0-9_ ]+![A-Z]{1,3}\d{1,7}",
    _re.IGNORECASE,
)


def _is_unresolved_formula(val: Any) -> bool:
    """Return True if the value looks like a raw formula/cell-reference string
    that was NOT evaluated by the calculation engine."""
    if not isinstance(val, str):
        return False
    s = val.strip()
    if not s:
        return False
    # Excel function calls
    if _EXCEL_FUNC_RE.search(s):
        return True
    # Cell reference arithmetic like C36*B33*C23, B38*B13
    if _CELL_REF_FORMULA_RE.match(s):
        return True
    # Sheet!Cell references like Rater!B1, 'Pick List'!A44
    if _SHEET_REF_RE.search(s) and len(s) < 80:
        return True
    return False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CalculationEngine:
    """
    Manages loaded Excel models and performs formula-based calculations.

    Thread-safe model cache keeps loaded models in memory so we don't
    re-parse on every request.
    """

    def __init__(self) -> None:
        self._models: dict[str, Any] = {}  # rater_id → ExcelModel
        self._filenames: dict[str, str] = {}  # rater_id → original filename
        self._wb_paths: dict[str, Path] = {}  # rater_id → workbook path
        self._cached_values: dict[str, dict[str, Any]] = {}  # rater_id → {"Sheet!Cell": value}
        self._metadata: dict[str, CalculationMetadata] = {}  # rater_id → metadata
        self._lock = threading.Lock()
        # Per-rater loading events: prevent two threads from loading the same
        # model simultaneously. A threading.Event is set when loading finishes.
        self._loading_events: dict[str, threading.Event] = {}

    # ── Model loading ────────────────────────────────────────────────

    @staticmethod
    def _sanitize_workbook(workbook_path: Path) -> Path:
        """
        Create a sanitised copy of the workbook so that the formulas library
        can parse every cell.  Three-pass approach:

          Pass 0  — Freeze heavy sheets.  Any worksheet whose formula-cell
            count exceeds HEAVY_SHEET_FORMULA_THRESHOLD has every formula cell
            replaced with its last-saved (data_only) scalar value.  This
            collapses large iterative calculation sheets (e.g. actuarial
            cashflow projections) into plain data, preventing the formulas
            library from building an unbounded dependency graph.  VLOOKUP and
            other cross-sheet references that *read* those sheets still work
            correctly because the data values remain in place.

          Pass 1  — Unicode operator replacement (× → *, ÷ → /, etc.).

          Pass 2  — Formula validation; cells whose formulas the formulas
            parser cannot process have their leading '=' stripped so the model
            loader treats them as plain text instead of crashing.

        Returns the original path when no modification was needed, otherwise
        saves the modified workbook to a temp directory and returns that path.
        """
        from formulas.errors import FormulaError as _FE
        from app.config import HEAVY_SHEET_FORMULA_THRESHOLD

        wb = openpyxl.load_workbook(str(workbook_path))
        modified = False

        # ── Pass 0: freeze heavy sheets ──────────────────────────────────────
        if HEAVY_SHEET_FORMULA_THRESHOLD > 0:
            wb_data = openpyxl.load_workbook(str(workbook_path), data_only=True)
            for ws in wb.worksheets:
                ws_data = wb_data[ws.title]
                formula_count = sum(
                    1
                    for row in ws.iter_rows()
                    for cell in row
                    if cell.value and isinstance(cell.value, str)
                    and cell.value.startswith("=")
                )
                if formula_count > HEAVY_SHEET_FORMULA_THRESHOLD:
                    logger.info(
                        "Freezing sheet '%s' (%d formula cells > threshold %d) — "
                        "replacing formulas with cached data values",
                        ws.title, formula_count, HEAVY_SHEET_FORMULA_THRESHOLD,
                    )
                    frozen = 0
                    for row in ws.iter_rows():
                        for cell in row:
                            if (
                                cell.value
                                and isinstance(cell.value, str)
                                and cell.value.startswith("=")
                            ):
                                cached_val = ws_data.cell(
                                    row=cell.row, column=cell.column
                                ).value
                                cell.value = cached_val   # None is fine (empty)
                                frozen += 1
                    modified = True
                    logger.info("Sheet '%s': froze %d cells", ws.title, frozen)
            wb_data.close()

        # ── Pass 0.5: rewrite OFFSET() → INDEX() ─────────────────────────────
        # The `formulas` library does not implement OFFSET. Replace every
        # OFFSET(ref, rows, cols) call with the INDEX+ROW+COLUMN equivalent
        # so that lookup formulas (e.g. premium rate tables) evaluate correctly.
        offset_rewritten = 0
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if (
                        cell.value
                        and isinstance(cell.value, str)
                        and cell.value.startswith("=")
                        and "OFFSET(" in cell.value.upper()
                    ):
                        new_val, n = _rewrite_offset_to_index(cell.value)
                        if n > 0 and new_val != cell.value:
                            cell.value = new_val
                            modified = True
                            offset_rewritten += n
        if offset_rewritten:
            logger.info(
                "Rewrote %d OFFSET() call(s) to INDEX() equivalents",
                offset_rewritten,
            )

        # ── Pass 1 + 2: Unicode sanitation & formula validation ───────────────
        unicode_replacements = {
            "\u00d7": "*",   # ×  → *
            "\u00f7": "/",   # ÷  → /
            "\u2212": "-",   # −  → -
            "\u2018": "'",   # '  → '
            "\u2019": "'",   # '  → '
            "\u201c": '"',   # "  → "
            "\u201d": '"',   # "  → "
        }

        prs = None  # lazy-loaded parser

        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if (
                        cell.value
                        and isinstance(cell.value, str)
                        and cell.value.startswith("=")
                    ):
                        original = cell.value
                        sanitised = original
                        # Pass 1: Unicode operator replacements
                        for old_char, new_char in unicode_replacements.items():
                            sanitised = sanitised.replace(old_char, new_char)

                        # Pass 2: validate with the formulas parser
                        try:
                            if prs is None:
                                from formulas.parser import Parser
                                prs = Parser()
                            prs.ast(sanitised)
                        except (_FE, Exception):
                            # Not a valid formula — strip '=' so it's plain text
                            sanitised = sanitised[1:].strip()
                            logger.debug(
                                "Converted pseudo-formula to text: %s → %s",
                                original, sanitised,
                            )

                        if sanitised != original:
                            cell.value = sanitised
                            modified = True

        if modified:
            # Save to a temp dir, keeping the original filename so that
            # formulas cell-key generation stays consistent.
            tmp_dir = Path(tempfile.mkdtemp(prefix="rater_"))
            sanitised_path = tmp_dir / workbook_path.name
            wb.save(str(sanitised_path))
            wb.close()
            logger.info("Sanitised/frozen workbook saved to %s", sanitised_path)
            return sanitised_path
        wb.close()
        return workbook_path

    def load_model(self, rater_id: str, workbook_path: Path) -> None:
        """Load and compile an Excel model, caching it by rater_id.

        Thread-safe: if two threads call this simultaneously for the same
        rater_id, the second thread waits for the first to finish rather
        than starting a redundant (and expensive) parallel load.
        """
        # Fast path: model already loaded
        with self._lock:
            if rater_id in self._models:
                return
            # First caller: create an event and mark loading in progress
            if rater_id not in self._loading_events:
                event = threading.Event()
                self._loading_events[rater_id] = event
                first_caller = True
            else:
                event = self._loading_events[rater_id]
                first_caller = False

        if not first_caller:
            # Another thread is already loading — wait for it to finish
            logger.info(
                "Rater %s is already being loaded — waiting for pre-load to finish",
                rater_id,
            )
            event.wait(timeout=300)  # up to 5 min for very large workbooks
            # If the first loader failed, the model won't be present.
            # Retry as the new first caller instead of returning empty-handed.
            if rater_id not in self._models:
                logger.warning(
                    "Pre-load for rater %s failed — retrying load",
                    rater_id,
                )
                return self.load_model(rater_id, workbook_path)
            return  # model should now be in self._models

        # We are the first caller: perform the load
        logger.info("Loading Excel model for rater %s from %s", rater_id, workbook_path)

        try:
            # Sanitise non-standard Unicode in formulas before loading
            effective_path = self._sanitize_workbook(workbook_path)

            t0 = time.perf_counter()
            xl = formulas.ExcelModel().loads(str(effective_path)).finish()
            elapsed = time.perf_counter() - t0
            logger.info(
                "Model loaded for rater %s in %.2fs (%d nodes)",
                rater_id, elapsed, len(xl.dsp.nodes),
            )
            # Pre-load cached (last-calculated) values from Excel for #REF! fallback
            cached = self._load_cached_values(workbook_path)

            # Load calculation metadata if available
            metadata = self._load_metadata(workbook_path.parent)
        except Exception:
            # Release waiting threads even on failure
            with self._lock:
                self._loading_events.pop(rater_id, None)
            event.set()
            raise

        with self._lock:
            self._models[rater_id] = xl
            self._filenames[rater_id] = workbook_path.name
            self._wb_paths[rater_id] = workbook_path
            self._cached_values[rater_id] = cached
            if metadata:
                self._metadata[rater_id] = metadata
            # Clean up loading event now that the model is stored
            self._loading_events.pop(rater_id, None)

        # Unblock any threads that were waiting for this load to complete
        event.set()

    @staticmethod
    def _load_cached_values(workbook_path: Path) -> dict[str, Any]:
        """
        Load the last-calculated values from the workbook using openpyxl's
        data_only mode.  These serve as fallbacks when the formulas library
        can't resolve external workbook references ([1]Sheet!Cell → #REF!).
        Returns a dict of "Sheet!Cell" → cached_value.
        """
        cached: dict[str, Any] = {}
        try:
            wb = openpyxl.load_workbook(str(workbook_path), data_only=True)
            for ws in wb.worksheets:
                for row in ws.iter_rows():
                    for cell in row:
                        if cell.value is not None:
                            key = f"{ws.title}!{cell.coordinate}"
                            cached[key] = cell.value
            wb.close()
            logger.info(
                "Loaded %d cached values from %s",
                len(cached), workbook_path.name,
            )
        except Exception as e:
            logger.warning("Failed to load cached values: %s", e)
        return cached

    @staticmethod
    def _load_metadata(rater_dir: Path) -> CalculationMetadata | None:
        """Load calculation metadata if it exists."""
        meta_path = rater_dir / "calculation_metadata.json"
        if not meta_path.exists():
            return None
        try:
            return CalculationMetadata.model_validate_json(
                meta_path.read_text(encoding="utf-8")
            )
        except Exception as e:
            logger.warning("Failed to load calculation metadata: %s", e)
            return None

    def unload_model(self, rater_id: str) -> None:
        """Remove a cached model."""
        with self._lock:
            self._models.pop(rater_id, None)
            self._filenames.pop(rater_id, None)
            self._wb_paths.pop(rater_id, None)
            self._cached_values.pop(rater_id, None)
            self._metadata.pop(rater_id, None)
            # Clean up any stale loading events
            ev = self._loading_events.pop(rater_id, None)
        if ev:
            ev.set()  # release any stuck waiters

    def is_loaded(self, rater_id: str) -> bool:
        return rater_id in self._models

    # ── Calculation ──────────────────────────────────────────────────

    def calculate(
        self,
        rater_id: str,
        schema: RaterSchema,
        user_inputs: dict[str, Any],
        workbook_path: Path | None = None,
    ) -> CalculationResult:
        """
        Run the rater calculation with the given user inputs.

        Parameters
        ----------
        rater_id : str
            Identifier for the cached model.
        schema : RaterSchema
            The parsed schema (provides cell_ref mappings).
        user_inputs : dict[str, Any]
            Field name → value, as submitted from the UI form.
        workbook_path : Path, optional
            If the model hasn't been loaded yet, load from this path.

        Returns
        -------
        CalculationResult
            Computed output values plus any warnings.
        """
        # Ensure model is loaded
        if not self.is_loaded(rater_id) and workbook_path:
            self.load_model(rater_id, workbook_path)

        with self._lock:
            xl = self._models.get(rater_id)
            filename = self._filenames.get(rater_id)

        if xl is None:
            raise RuntimeError(f"Model not loaded for rater {rater_id}")

        warnings: list[str] = []

        # --- Load metadata for targeted outputs ---
        with self._lock:
            metadata = self._metadata.get(rater_id)

        # --- Build input overrides dict ---
        input_map = self._map_inputs(schema, user_inputs, filename, warnings)

        # --- Build targeted output keys from schema (authoritative source) ---
        # Always use the schema's output fields to build output keys.
        # The schema is regenerated from the workbook and may have more
        # or different outputs than stale metadata.
        output_keys = self._build_output_keys(schema, filename)
        logger.info(
            "Using %d output keys from schema for calculation",
            len(output_keys),
        )

        # --- Get cached values for fallback ---
        with self._lock:
            cached = self._cached_values.get(rater_id, {})

        # --- PRIMARY: Run calculation with timeout ---
        solution = None
        formulas_succeeded = False

        from app.config import CALCULATION_TIMEOUT

        try:
            solution = self._calculate_with_timeout(
                xl, input_map, output_keys, CALCULATION_TIMEOUT,
            )
            formulas_succeeded = True
            logger.info(
                "Primary calculation for rater %s completed (%d solution keys, %d targeted outputs)",
                rater_id, len(solution), len(output_keys),
            )
        except TimeoutError:
            warnings.append("Primary calculation timed out — using fallback methods")
            logger.warning("Calculation timed out for rater %s after %ds", rater_id, CALCULATION_TIMEOUT)
        except Exception as e:
            warnings.append(f"Primary calculation failed: {e} — using fallback methods")
            logger.warning("Primary calculation failed for rater %s: %s", rater_id, e)

        # --- Extract outputs from formulas solution ---
        outputs: dict[str, Any] = {}
        if solution and formulas_succeeded:
            outputs = self._extract_outputs(schema, solution, filename, warnings, cached)

        # --- FALLBACK 0.5: Python-based VLOOKUP for #N/A outputs ---
        # When the formulas library returns #N/A for VLOOKUP-dependent outputs,
        # attempt to resolve them using the schema's lookup tables + workbook data.
        na_outputs = {
            name for name, val in outputs.items()
            if val is None or (isinstance(val, str) and val.startswith("#"))
        }
        if na_outputs:
            wb_path_for_vlookup = workbook_path
            if wb_path_for_vlookup is None:
                with self._lock:
                    wb_path_for_vlookup = self._wb_paths.get(rater_id)
            vlookup_resolved = self._resolve_vlookups_python(
                schema, user_inputs, na_outputs, warnings,
                workbook_path=wb_path_for_vlookup,
            )
            for name, val in vlookup_resolved.items():
                outputs[name] = val
                logger.debug("Resolved output '%s' via Python VLOOKUP: %s", name, val)

        # --- FALLBACK 1: LLM-translated Python formulas ---
        missing_outputs = self._find_missing_outputs(schema, outputs)
        if missing_outputs and metadata and metadata.formula_translations:
            translated_outputs = self._calculate_with_translations(
                metadata, user_inputs, schema, warnings,
            )
            for name, val in translated_outputs.items():
                if name in missing_outputs:
                    outputs[name] = val
                    logger.debug("Used translated formula for output '%s': %s", name, val)

        # --- FALLBACK 2: Cached values from Excel ---
        missing_outputs = self._find_missing_outputs(schema, outputs)
        if missing_outputs and cached:
            for field in schema.output_fields:
                if field.group == "intermediate":
                    continue
                if field.name in missing_outputs:
                    cache_key = f"{field.sheet}!{field.cell_ref.replace('$', '')}"
                    cached_val = cached.get(cache_key)
                    if cached_val is not None:
                        val = _convert_numpy(cached_val)
                        if isinstance(val, float):
                            val = round(val, 2)
                        outputs[field.name] = val
                        warnings.append(
                            f"Output '{field.name}' uses cached default value (may not reflect input changes)"
                        )
                        logger.debug("Used cached fallback for '%s': %s", field.name, val)

        # --- Validate outputs (check for #REF!, NaN, formula strings) ---
        outputs = self._validate_outputs(outputs, warnings)

        # --- Build output fields metadata for frontend display ---
        from app.models.schemas import OutputFieldMeta
        output_fields_meta = []
        for field in schema.output_fields:
            if field.group == "intermediate":
                continue
            output_fields_meta.append(OutputFieldMeta(
                name=field.name,
                label=field.label,
                group=field.group,
                order=field.order,
                field_type=field.field_type.value if hasattr(field.field_type, 'value') else str(field.field_type),
            ))

        return CalculationResult(
            rater_id=rater_id,
            outputs=outputs,
            output_fields_meta=output_fields_meta,
            warnings=warnings,
            refer=False,
        )

    # ── Internal helpers ─────────────────────────────────────────────

    @staticmethod
    def _calculate_with_timeout(
        xl: Any,
        input_map: dict[str, Any],
        output_keys: list[str],
        timeout_seconds: int,
    ) -> dict:
        """
        Run xl.calculate() with a timeout.
        Raises TimeoutError if the calculation doesn't finish in time.
        """
        calc_kwargs: dict[str, Any] = {}
        if input_map:
            calc_kwargs["inputs"] = input_map
        if output_keys:
            calc_kwargs["outputs"] = output_keys

        t_start = time.perf_counter()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(xl.calculate, **calc_kwargs)
            try:
                solution = future.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError:
                future.cancel()
                raise TimeoutError(
                    f"Calculation timed out after {timeout_seconds}s"
                )

        t_elapsed = time.perf_counter() - t_start
        logger.info("Formula calculation completed in %.2fs", t_elapsed)
        return solution

    def _calculate_with_translations(
        self,
        metadata: CalculationMetadata,
        user_inputs: dict[str, Any],
        schema: RaterSchema,
        warnings: list[str],
    ) -> dict[str, Any]:
        """
        Use LLM-translated Python formulas to compute outputs.
        Only uses validated translations.
        """
        from app.services.formula_runtime import formula_runtime

        outputs: dict[str, Any] = {}

        # Build full input dict (user inputs + defaults for missing)
        full_inputs = {f.name: f.default_value for f in schema.input_fields}
        full_inputs.update(user_inputs)

        # Build lookup data from schema
        lookup_data: dict[str, Any] = {}
        for lt in schema.lookup_tables:
            lookup_data[lt.name] = {
                "columns": lt.columns,
                "rows": lt.rows,
            }

        for translation in metadata.formula_translations:
            if not translation.validated:
                continue  # Skip unvalidated translations

            try:
                result = formula_runtime.execute_expression(
                    translation.python_expression,
                    full_inputs,
                    lookup_data,
                )
                if result is not None:
                    if isinstance(result, float):
                        result = round(result, 2)
                    outputs[translation.output_name] = result
            except Exception as e:
                logger.warning(
                    "Translated formula execution failed for '%s': %s",
                    translation.output_name, e,
                )
                warnings.append(
                    f"Translated formula for '{translation.output_name}' failed: {e}"
                )

        return outputs

    @staticmethod
    def _resolve_vlookups_python(
        schema: RaterSchema,
        user_inputs: dict[str, Any],
        na_outputs: set[str],
        warnings: list[str],
        *,
        workbook_path: Path | None = None,
    ) -> dict[str, Any]:
        """
        Attempt to resolve #N/A outputs by performing Python-based VLOOKUP
        using the workbook data and current user inputs.

        Handles formulas like:
          =IF($C$6="Georgia","N/A",VLOOKUP(C27,'XS Rate Tables Sections A-F'!$H$41:$I$45,2,FALSE))
        Where:
          - The lookup_value ref can be same-sheet (C27) or cross-sheet ('Sheet'!$C$6)
          - The table_array is a cross-sheet range ('Sheet'!$H$41:$I$45)
          - We read the actual range from the workbook via openpyxl
        """
        import re as _re
        from openpyxl import load_workbook
        from openpyxl.utils import column_index_from_string

        resolved: dict[str, Any] = {}

        # Build full input dict (user inputs + defaults for missing)
        full_inputs = {f.name: f.default_value for f in schema.input_fields}
        full_inputs.update(user_inputs)

        # Build mapping: "SHEET!COL_ROW" → value  (for resolving cell refs)
        cell_values: dict[str, Any] = {}
        for f in schema.input_fields:
            if f.sheet and f.cell_ref:
                key = f"{f.sheet}!{f.cell_ref.replace('$', '')}".upper()
                cell_values[key] = full_inputs.get(f.name, f.default_value)
        for f in schema.output_fields:
            if f.sheet and f.cell_ref and f.default_value is not None:
                key = f"{f.sheet}!{f.cell_ref.replace('$', '')}".upper()
                if key not in cell_values:
                    cell_values[key] = f.default_value

        # Lazy-load workbook (read-only, data-only) for reading lookup ranges
        _wb = None
        _wb_sheets: dict[str, Any] = {}

        def get_wb_sheet(sheet_name: str):
            nonlocal _wb, _wb_sheets
            if sheet_name in _wb_sheets:
                return _wb_sheets[sheet_name]
            if _wb is None:
                if workbook_path is None:
                    return None
                try:
                    _wb = load_workbook(str(workbook_path), read_only=True, data_only=True)
                except Exception as exc:
                    logger.warning("Cannot open workbook for VLOOKUP fallback: %s", exc)
                    return None
            # Try exact name first, then case-insensitive
            ws = None
            if sheet_name in _wb.sheetnames:
                ws = _wb[sheet_name]
            else:
                for sn in _wb.sheetnames:
                    if sn.upper() == sheet_name.upper():
                        ws = _wb[sn]
                        break
            _wb_sheets[sheet_name] = ws
            return ws

        def read_cell(sheet_name: str, col: str, row: int):
            """Read a single cell value from the workbook."""
            ws = get_wb_sheet(sheet_name)
            if ws is None:
                return None
            try:
                return ws[f"{col}{row}"].value
            except Exception:
                return None

        def read_range(sheet_name: str, col1: str, row1: int, col2: str, row2: int):
            """Read a rectangular range from the workbook as list of row-lists."""
            ws = get_wb_sheet(sheet_name)
            if ws is None:
                return None
            try:
                c1 = column_index_from_string(col1)
                c2 = column_index_from_string(col2)
                rows_data = []
                for r in range(row1, row2 + 1):
                    row_vals = []
                    for c in range(c1, c2 + 1):
                        row_vals.append(ws.cell(row=r, column=c).value)
                    rows_data.append(row_vals)
                return rows_data
            except Exception as exc:
                logger.debug("Failed reading range %s!%s%d:%s%d: %s",
                             sheet_name, col1, row1, col2, row2, exc)
                return None

        def resolve_cell_ref(ref_str: str, default_sheet: str) -> Any:
            """
            Resolve a cell reference like C27 or 'Sheet'!$C$6 to its value.
            First checks cell_values map, then reads from workbook.
            """
            ref_clean = ref_str.replace("$", "").strip().strip("'")
            if "!" in ref_clean:
                parts = ref_clean.split("!", 1)
                sheet = parts[0].strip("'")
                cell = parts[1]
            else:
                sheet = default_sheet
                cell = ref_clean

            key = f"{sheet}!{cell}".upper()
            if key in cell_values:
                return cell_values[key]

            # Try reading from workbook
            m = _re.match(r"([A-Z]+)(\d+)", cell.upper())
            if m:
                val = read_cell(sheet, m.group(1), int(m.group(2)))
                if val is not None:
                    cell_values[key] = val
                return val
            return None

        def do_vlookup(lookup_val: Any, table_data: list[list], col_idx: int, exact: bool = True):
            """Perform a VLOOKUP on in-memory table data."""
            if not table_data or col_idx < 1:
                return None
            lookup_str = str(lookup_val).strip().upper()
            # Try numeric comparison first
            try:
                lookup_num = float(lookup_val)
                is_numeric = True
            except (ValueError, TypeError):
                lookup_num = None
                is_numeric = False

            for row in table_data:
                if not row:
                    continue
                first_val = row[0]
                if first_val is None:
                    continue
                # Exact match
                if exact:
                    if str(first_val).strip().upper() == lookup_str:
                        if col_idx <= len(row):
                            return row[col_idx - 1]
                    # Also try numeric comparison
                    if is_numeric:
                        try:
                            if float(first_val) == lookup_num:
                                if col_idx <= len(row):
                                    return row[col_idx - 1]
                        except (ValueError, TypeError):
                            pass
                else:
                    # Approximate match (sorted ascending) — find largest <= lookup
                    pass  # Not commonly needed, skip for now
            return None

        # -- Parse each VLOOKUP formula in each NA output --
        # Regex to find all VLOOKUP calls (handles nested IF-VLOOKUP patterns)
        vlookup_pattern = _re.compile(
            r"VLOOKUP\s*\(\s*"
            r"([^,]+?)\s*,\s*"             # group 1: lookup_value ref
            r"([^,]+?)\s*,\s*"             # group 2: table_array ref
            r"(\d+)\s*"                     # group 3: col_index
            r"(?:,\s*(TRUE|FALSE|0|1))?\s*\)",  # group 4: exact match flag
            _re.IGNORECASE,
        )

        # Regex to parse a range like 'Sheet Name'!$H$41:$I$45  or  A1:B10
        range_pattern = _re.compile(
            r"'?([^'!]+?)'?\s*!\s*\$?([A-Z]+)\$?(\d+)\s*:\s*\$?([A-Z]+)\$?(\d+)",
            _re.IGNORECASE,
        )
        # Same-sheet range like $H$41:$I$45
        local_range_pattern = _re.compile(
            r"^\$?([A-Z]+)\$?(\d+)\s*:\s*\$?([A-Z]+)\$?(\d+)$",
            _re.IGNORECASE,
        )

        # Cell ref pattern (with optional sheet)
        cell_ref_pattern = _re.compile(
            r"(?:'([^']+)'!\s*)?(\$?[A-Z]+\$?\d+)",
            _re.IGNORECASE,
        )

        for field in schema.output_fields:
            if field.name not in na_outputs:
                continue
            if not field.formula:
                continue

            formula = str(field.formula)
            output_sheet = field.sheet or ""

            # Check for IF wrapping to determine which VLOOKUP branch to use
            # Pattern: IF($C$6="Georgia", BRANCH_TRUE, BRANCH_FALSE)
            if_match = _re.match(
                r"=?\s*IF\s*\(\s*(.+?)\s*=\s*\"([^\"]+)\"\s*,\s*(.+)\)",
                formula,
                _re.IGNORECASE,
            )
            formula_to_eval = formula
            if if_match:
                condition_ref = if_match.group(1).replace("$", "").strip()
                condition_val = if_match.group(2)
                branches = if_match.group(3)

                # Resolve condition value
                cond_actual = resolve_cell_ref(condition_ref, output_sheet)
                cond_actual_str = str(cond_actual).strip().upper() if cond_actual else ""

                # Split branches (handling nested parentheses)
                depth = 0
                split_pos = None
                for i, ch in enumerate(branches):
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                    elif ch == "," and depth == 0:
                        split_pos = i
                        break

                if split_pos is not None:
                    true_branch = branches[:split_pos].strip()
                    false_branch = branches[split_pos + 1:].strip()
                else:
                    true_branch = branches
                    false_branch = ""

                if cond_actual_str == condition_val.upper():
                    formula_to_eval = true_branch
                else:
                    formula_to_eval = false_branch

            # Check if the selected branch is a literal (not a VLOOKUP)
            if not _re.search(r"VLOOKUP", formula_to_eval, _re.IGNORECASE):
                # It's a literal like "N/A - Leave cell blank"
                lit_match = _re.match(r'\s*"([^"]*)"\s*$', formula_to_eval)
                if lit_match:
                    resolved[field.name] = lit_match.group(1)
                continue

            # Find all VLOOKUP calls in the formula branch
            for vm in vlookup_pattern.finditer(formula_to_eval):
                lookup_ref = vm.group(1).strip()
                table_ref = vm.group(2).strip()
                col_index = int(vm.group(3))
                exact_flag = vm.group(4)
                exact = exact_flag is None or exact_flag.upper() in ("FALSE", "0")

                # Resolve lookup value
                lookup_value = resolve_cell_ref(lookup_ref, output_sheet)
                if lookup_value is None:
                    continue

                # Parse table range
                table_data = None
                rm = range_pattern.match(table_ref)
                lm = local_range_pattern.match(table_ref)

                if rm:
                    # Cross-sheet range
                    t_sheet = rm.group(1).strip("'")
                    c1, r1, c2, r2 = rm.group(2), int(rm.group(3)), rm.group(4), int(rm.group(5))
                    table_data = read_range(t_sheet, c1.upper(), r1, c2.upper(), r2)
                elif lm:
                    # Same-sheet range
                    c1, r1, c2, r2 = lm.group(1), int(lm.group(2)), lm.group(3), int(lm.group(4))
                    table_data = read_range(output_sheet, c1.upper(), r1, c2.upper(), r2)

                if not table_data:
                    continue

                result = do_vlookup(lookup_value, table_data, col_index, exact)
                if result is not None:
                    if isinstance(result, float):
                        result = round(result, 2)
                    resolved[field.name] = result
                    break

        # Close workbook if opened
        if _wb is not None:
            try:
                _wb.close()
            except Exception:
                pass

        if resolved:
            logger.info(
                "Python VLOOKUP resolved %d outputs: %s",
                len(resolved), list(resolved.keys()),
            )

        return resolved

    @staticmethod
    def _find_missing_outputs(
        schema: RaterSchema, outputs: dict[str, Any],
    ) -> set[str]:
        """Find output field names that are missing or None in the outputs dict.
        Skips intermediate outputs (marked by parser via formula-DAG)."""
        missing = set()
        for field in schema.output_fields:
            if field.group == "intermediate":
                continue
            if field.name not in outputs or outputs[field.name] is None:
                missing.add(field.name)
        return missing

    @staticmethod
    def _validate_outputs(
        outputs: dict[str, Any], warnings: list[str],
    ) -> dict[str, Any]:
        """
        Validate output values — replace #REF!, NaN, and unresolved formulas
        with None and add warnings.
        """
        cleaned = {}
        for name, val in outputs.items():
            if val is None:
                cleaned[name] = None
                continue

            # Check for error values
            if isinstance(val, str) and val.startswith("#"):
                warnings.append(f"Output '{name}' returned error: {val}")
                cleaned[name] = None
                continue

            # Check for unresolved formulas
            if _is_unresolved_formula(val):
                warnings.append(f"Output '{name}' returned unresolved formula")
                cleaned[name] = None
                continue

            # Check for NaN
            if isinstance(val, float) and (val != val):  # NaN check
                warnings.append(f"Output '{name}' returned NaN")
                cleaned[name] = None
                continue

            cleaned[name] = val
        return cleaned

    def _map_inputs(
        self,
        schema: RaterSchema,
        user_inputs: dict[str, Any],
        filename: str,
        warnings: list[str],
    ) -> dict[str, Any]:
        """
        Convert {field_name: value} to {cell_key: value} for formulas lib.
        """
        input_map: dict[str, Any] = {}

        # Build a lookup from field name → RaterField
        field_lookup: dict[str, RaterField] = {
            f.name: f for f in schema.input_fields
        }

        for field_name, value in user_inputs.items():
            field = field_lookup.get(field_name)
            if not field:
                warnings.append(f"Unknown input field: {field_name}")
                continue
            if not field.cell_ref or not field.sheet:
                warnings.append(f"Field '{field_name}' has no cell reference — skipped")
                continue

            # Convert value to the appropriate type
            coerced = self._coerce_value(field, value)

            # Inject via both cell-ref key and named-range key so the model
            # receives the value whichever key propagates through the DAG.
            cell_key = _build_cell_key(filename, field.sheet, field.cell_ref)
            input_map[cell_key] = coerced

            # Named-range key: '[filename]'!FIELDNAME  (field.name uppercased)
            named_key = f"'[{filename}]'!{field.name.upper()}"
            input_map[named_key] = coerced

        return input_map

    def _extract_outputs(
        self,
        schema: RaterSchema,
        solution: dict,
        filename: str,
        warnings: list[str],
        cached_values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Pull output field values from the calculation solution.
        Uses normalized key matching to handle case/dollar-sign differences.

        When the formulas library returns #REF! (due to unresolvable external
        workbook references like [1]Input!A17), falls back to the cached
        value that was last computed in Excel.
        """
        outputs: dict[str, Any] = {}
        cached_values = cached_values or {}

        # Build a normalized lookup of solution keys for O(1) matching
        norm_to_key: dict[str, str] = {}
        for sol_key in solution:
            norm_to_key[_normalize_key(sol_key)] = sol_key

        for field in schema.output_fields:
            if not field.cell_ref or not field.sheet:
                continue
            # Skip intermediate outputs (parser marks via formula-DAG)
            if field.group == "intermediate":
                continue

            cell_key = _build_cell_key(filename, field.sheet, field.cell_ref)
            norm = _normalize_key(cell_key)

            actual_key = norm_to_key.get(norm)
            if actual_key:
                raw = solution[actual_key]
                val = _ranges_to_value(raw)

                # --- #REF! / unresolved formula fallback ---
                # The formulas lib returns "#REF!" for unresolvable external
                # workbook references, and sometimes returns raw formula
                # strings (e.g. "VLOOKUP(...)", "B38*B13") when the formula
                # was stripped of its leading '=' during sanitization.
                # Fall back to the cached value from the Excel file.
                needs_fallback = (
                    val == "#REF!"
                    or (isinstance(val, str) and val.startswith("#"))
                    or _is_unresolved_formula(val)
                )
                if needs_fallback:
                    cache_key = f"{field.sheet}!{field.cell_ref.replace('$', '')}"
                    cached_val = cached_values.get(cache_key)
                    if cached_val is not None:
                        val = _convert_numpy(cached_val)
                        if isinstance(val, float):
                            val = round(val, 2)
                        logger.debug(
                            "Used cached value for %s (%s): %s",
                            field.name, cache_key, val,
                        )
                    else:
                        # No cached value either — keep original error but
                        # provide a friendlier representation
                        val = None
                        warnings.append(
                            f"Output '{field.name}' references external workbook — no cached value available"
                        )

                if isinstance(val, float):
                    val = round(val, 2)
                outputs[field.name] = val
            else:
                # Cell not in solution — try cached value
                cache_key = f"{field.sheet}!{field.cell_ref.replace('$', '')}"
                cached_val = cached_values.get(cache_key)
                if cached_val is not None:
                    val = _convert_numpy(cached_val)
                    if isinstance(val, float):
                        val = round(val, 2)
                    outputs[field.name] = val
                    logger.debug(
                        "Used cached value for missing output %s (%s): %s",
                        field.name, cache_key, val,
                    )
                else:
                    warnings.append(
                        f"Output '{field.name}' ({cell_key}) not found in solution"
                    )

        return outputs

    def _build_output_keys(
        self,
        schema: RaterSchema,
        filename: str,
    ) -> list[str]:
        """
        Build the list of cell keys for output fields so we can pass them
        to xl.calculate(outputs=...) for targeted (faster) computation.
        Instead of evaluating ALL 8000+ formula nodes in a large workbook,
        the library only follows dependency chains for these specific cells.

        Outputs with group="intermediate" are skipped — they are internal
        calculation cells that don't need to be returned to the user.
        """
        keys: list[str] = []
        for field in schema.output_fields:
            if not field.cell_ref or not field.sheet:
                continue
            # Skip intermediate outputs (parser marks them via formula-DAG)
            if field.group == "intermediate":
                continue
            keys.append(_build_cell_key(filename, field.sheet, field.cell_ref))
        return keys

    @staticmethod
    def _coerce_value(field: RaterField, value: Any) -> Any:
        """Coerce a user input to the type expected by formulas."""
        from app.models.schemas import FieldType

        if field.field_type == FieldType.NUMBER:
            try:
                return float(value)
            except (TypeError, ValueError):
                return value
        if field.field_type == FieldType.BOOLEAN:
            if isinstance(value, str):
                return value.lower() in ("true", "yes", "1")
            return bool(value)
        # TEXT and SELECT: pass through as-is
        return value


# ---------------------------------------------------------------------------
# Module-level singleton (imported by routers)
# ---------------------------------------------------------------------------
engine = CalculationEngine()
