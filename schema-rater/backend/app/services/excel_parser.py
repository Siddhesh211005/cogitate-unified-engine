"""
Excel Parsing Pipeline































































    print(f"    ... and {len(intermediate_outputs) - 10} more")if len(intermediate_outputs) > 10:    print(f"    {f.name:45s} group={f.group}  sheet={f.sheet}")for f in intermediate_outputs[:10]:print(f"\n  INTERMEDIATE outputs ({len(intermediate_outputs)}):")    print(f"    {f.name:45s} group={f.group}  sheet={f.sheet}")for f in final_outputs:print(f"\n  FINAL outputs ({len(final_outputs)}):")intermediate_outputs = [f for f in schema.output_fields if f.group == "intermediate"]final_outputs = [f for f in schema.output_fields if f.group != "intermediate"]print(f"\nOutputs: {len(schema.output_fields)} (was 87)")    print(f"  {f.name:45s} sheet={f.sheet}  default={str(f.default_value)[:40]}")for f in schema.input_fields:print(f"Inputs: {len(schema.input_fields)} (was 22)")print(f"\n=== RESULTS WITH FIXES ===")schema = parser.extract()# Now extract with fixes    print("\nAll sheets in one cluster (no filtering needed)")else:    print(f"\nPrimary cluster: {len(primary)} sheets")if primary:primary = parser._get_primary_cluster_sheets()        print(f"  [{role:12s}] {sh}")        role = next((si.role.value for si in parser._sheet_infos if si.sheet_name == sh), "?")    for sh in sorted(cluster):    print(f"\nCluster {i+1} ({len(cluster)} sheets):")for i, cluster in enumerate(clusters):clusters = parser._find_connected_sheet_clusters()print("=== SHEET CLUSTERS ===")# Test sheet clusteringparser.inspect()parser = ExcelRaterParser(excel_path)print()print(f"Parsing: {excel_path}")excel_path = os.path.join(rater_dir, excel_files[0])    sys.exit(1)    print("No Excel file found in", rater_dir)if not excel_files:excel_files = [f for f in os.listdir(rater_dir) if f.endswith((".xlsx", ".xlsm"))]import os# Find the Excel file        break        rater_dir = d.replace("schema.json", "")    if "excess" in s.get("rater_name", "").lower() or "follow" in s.get("rater_name", "").lower():        s = json.load(f)    with open(d) as f:for d in glob.glob("backend/data/raters/*/schema.json"):# Find the Excess Follow raterfrom app.services.excel_parser import ExcelRaterParsersys.path.insert(0, "backend")======================
Extracts inputs, outputs, lookup tables, and formula dependencies from
arbitrary insurance rater workbooks. Adapts to varying sheet layouts by
detecting naming conventions (Xinput_/Xoutput_ prefixed named ranges,
label+value cell pairs, and tabular regions).

Design principles:
  - Logical chunking: keep related rows together (tables stay intact).
  - Two-pass: first *inspect* (survey sheets, named ranges, tables),
              then *extract* (pull values, formulas, options).
  - Strict retrieval: only data present in the Excel is surfaced.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.cell.cell import Cell
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.models.schemas import (
    FieldOption,
    FieldType,
    FormulaMapping,
    LookupTable,
    RaterField,
    RaterSchema,
    SheetInfo,
    SheetRole,
    ValidationRule,
)
from app.config import (
    PARSER_INSTRUCTION_KEYWORDS,
    PARSER_FINAL_OUTPUT_KEYWORDS,
    PARSER_MIN_FIELD_NAME_LENGTH,
)


# ── helpers ──────────────────────────────────────────────────────────────

_XINPUT_RE = re.compile(r"^[Xx][Ii]nput_(\d+)_(.+)$")
_XINPUT_UNNUMBERED_RE = re.compile(r"^[Xx][Ii]nput_(.+)$")
_XOUTPUT_RE = re.compile(r"^[Xx][Oo]utput_(.+)$")
_LABEL_COL_OFFSET = {
    # (label_col, value_col) relative patterns observed in sample raters
    "Homeowners": ("A", "E"),
    "MPL": ("A", "B"),
    "PAR": ("B", "D"),
}


def _cell_value(cell: Cell) -> Any:
    """Return the raw value of a cell (formula string if present)."""
    return cell.value


def _is_formula(cell: Cell) -> bool:
    if cell.value is None:
        return False
    s = str(cell.value)
    if not s.startswith("="):
        return False
    # "= Calculated Premium" etc. are labels, not real formulas
    # Real formulas start with = followed by a function name, cell ref, or operator
    rest = s[1:].lstrip()
    if not rest:
        return False
    # Real formula: starts with letter (function/cell ref), digit, +, -, (, '
    if rest[0] in ('+', '-', '(', "'") or rest[0].isdigit():
        return True
    # Check if it starts with a function name or cell reference (A1, Sheet!A1, etc.)
    if re.match(r'^[A-Za-z]', rest):
        # If it looks like "= Some Label Text", it's not a formula
        # Real formulas have ( or ! or operators soon after the first word
        if re.match(r'^[A-Z]{1,3}\d{1,7}', rest, re.IGNORECASE):
            return True  # Cell reference like =A1
        if re.match(r'^[A-Za-z_]+\s*\(', rest):
            return True  # Function call like =SUM(
        if re.match(r'^[A-Za-z_]+\s*!', rest):
            return True  # Sheet reference like =Sheet1!
        if re.match(r'^[A-Za-z_\'"]+.*[+\-*/^&=<>]', rest):
            return True  # Expression with operators
        return False  # Likely just a label
    return False


def _clean_label(raw: str) -> str:
    """Turn an Excel label into a readable string, sanitizing encoding artifacts."""
    # Replace common Windows-1252 characters that may sneak through
    cleaned = raw.replace("\u0092", "\u2019").replace("\u0093", "\u201c").replace("\u0094", "\u201d")
    return cleaned.strip().rstrip(":").strip()


def _slugify(name: str) -> str:
    """Convert human label to a machine-safe key."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name)
    return s.strip("_")


# ── FIX 2: Garbage field rejection filter ────────────────────────────────
# Note: Keywords are now configurable via app.config (PARSER_INSTRUCTION_KEYWORDS)


def _is_garbage_field(slug: str, label: str, default_value: Any) -> bool:
    """
    Return True if a field is clearly not a real input (instruction text,
    single-char names, arrow-prefixed defaults, etc.).
    Uses configurable thresholds from app.config.
    """
    # Short slugs (configurable min length)
    if len(slug) < PARSER_MIN_FIELD_NAME_LENGTH:
        return True
    # Instruction / header text in the label (configurable keywords)
    label_lower = label.lower()
    if any(kw in label_lower for kw in PARSER_INSTRUCTION_KEYWORDS):
        return True
    # Default value starts with arrow instruction
    dv = str(default_value or "")
    if dv.startswith("<--") or dv.startswith("-->"):
        return True
    # Default value is long instruction text (not a real input value)
    if len(dv) > 80 and not isinstance(default_value, (int, float)):
        return True
    # Default value is clearly an instruction, not a value
    dv_lower = dv.lower()
    if any(kw in dv_lower for kw in ("all inputs should", "inputs are in",
                                      "leave cell blank")):
        return True
    # Default value looks like a label/header rather than a real value
    # (multi-word text with spaces that doesn't look like a dropdown option)
    if (isinstance(default_value, str) and " " in dv
            and not isinstance(default_value, (int, float))
            and len(dv) > 5
            and not any(c.isdigit() for c in dv)
            and dv_lower == slug.lower().replace("_", " ")):
        # Default value is just the slug reformatted — it's a header
        return True
    return False


def _guess_field_type(value: Any, options: list | None = None) -> FieldType:
    if options:
        return FieldType.SELECT
    if isinstance(value, bool):
        return FieldType.BOOLEAN
    if isinstance(value, (int, float)):
        return FieldType.NUMBER
    if value and re.match(r"^\d{4}-\d{2}-\d{2}", str(value)):
        return FieldType.DATE
    return FieldType.TEXT


def _detect_sheet_role(ws: Worksheet, sheet_name: str) -> SheetRole:
    """Heuristically tag a sheet's role."""
    name_lower = sheet_name.lower()
    if any(k in name_lower for k in ("input", "rater", "application", "rating step")):
        return SheetRole.INPUT
    if any(k in name_lower for k in ("pick list", "code", "rate table", "lookup", "index")):
        return SheetRole.LOOKUP
    if any(k in name_lower for k in ("output", "premium", "result", "final", "report", "illustration")):
        return SheetRole.OUTPUT
    if any(k in name_lower for k in ("calc", "solve", "cashflow", "formula", "factor", "endorsement")):
        return SheetRole.CALCULATION
    return SheetRole.UNKNOWN


# ── Main Parsing Class ───────────────────────────────────────────────────

class ExcelRaterParser:
    """
    Two-phase parser for insurance rater Excel workbooks.
    Phase 1 – Inspect: survey sheets, named ranges, detect tables.
    Phase 2 – Extract: pull input fields, output fields, lookup tables, formulas.
    """

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        # Use read_only mode for faster loading of large files
        self.wb: Workbook = openpyxl.load_workbook(
            str(self.file_path), data_only=False, read_only=True
        )
        self.wb_data: Workbook = openpyxl.load_workbook(
            str(self.file_path), data_only=True, read_only=True
        )
        self._named_ranges: dict[str, dict] = {}
        self._input_fields: list[RaterField] = []
        self._output_fields: list[RaterField] = []
        self._lookup_tables: list[LookupTable] = []
        self._formula_mappings: list[FormulaMapping] = []
        self._sheet_infos: list[SheetInfo] = []
        # Table structure detection (populated by _detect_table_structures)
        # {sheet_name: {row_num: {col_num: header_text}}}
        self._table_headers: dict[str, dict[int, dict[int, str]]] = {}
        # {sheet_name: set(row_nums in table body)}
        self._table_body_rows: dict[str, set[int]] = {}

    # ── Phase 1: Inspect ─────────────────────────────────────────────────

    def inspect(self) -> list[SheetInfo]:
        """Survey every sheet and catalogue named ranges."""
        for sn in self.wb.sheetnames:
            ws = self.wb[sn]
            role = _detect_sheet_role(ws, sn)
            self._sheet_infos.append(SheetInfo(
                sheet_name=sn,
                role=role,
                row_count=ws.max_row or 0,
                col_count=ws.max_column or 0,
            ))

        # Catalogue defined names
        for name, defn in self.wb.defined_names.items():
            try:
                for title, coord in defn.destinations:
                    ws = self.wb[title]
                    cell = ws[coord]
                    ws_data = self.wb_data[title]
                    cell_data = ws_data[coord]
                    self._named_ranges[name] = {
                        "sheet": title,
                        "coord": coord,
                        "formula_value": cell.value,
                        "computed_value": cell_data.value,
                        "is_formula": _is_formula(cell),
                    }
            except Exception:
                # Named range may reference a deleted or external sheet
                pass

        return self._sheet_infos

    # ── Sheet connectivity clustering (FIX 1) ────────────────────────────

    def _find_connected_sheet_clusters(self) -> list[set[str]]:
        """
        Build a formula-based connectivity graph between sheets and return
        connected components.  This lets us filter out unrelated sheets
        (e.g. D&O sheets embedded in an Excess Follow workbook).
        """
        all_sheets = {si.sheet_name for si in self._sheet_infos}
        graph: dict[str, set[str]] = {s: set() for s in all_sheets}

        for si in self._sheet_infos:
            ws = self.wb[si.sheet_name]
            max_row = min(si.row_count, 200)
            max_col = min(si.col_count, 20)
            for row in ws.iter_rows(min_row=1, max_row=max_row,
                                     min_col=1, max_col=max_col):
                for cell in row:
                    if _is_formula(cell):
                        formula_str = str(cell.value)
                        # Extract sheet references: 'Sheet Name'!A1 or SheetName!A1
                        refs = re.findall(r"'([^']+)'!", formula_str)
                        refs += re.findall(r"(?<!')([A-Za-z_][A-Za-z0-9_ ]*?)!", formula_str)
                        for ref in refs:
                            ref_clean = ref.strip("'").strip()
                            if ref_clean in all_sheets and ref_clean != si.sheet_name:
                                graph[si.sheet_name].add(ref_clean)
                                graph[ref_clean].add(si.sheet_name)

        # BFS to find connected components
        visited: set[str] = set()
        clusters: list[set[str]] = []
        for sheet in all_sheets:
            if sheet not in visited:
                cluster: set[str] = set()
                queue = [sheet]
                while queue:
                    s = queue.pop(0)
                    if s in visited:
                        continue
                    visited.add(s)
                    cluster.add(s)
                    queue.extend(graph[s] - visited)
                clusters.append(cluster)
        return clusters

    def _get_primary_cluster_sheets(self) -> set[str] | None:
        """
        Identify the primary sheet cluster (the one containing the most
        INPUT + OUTPUT role sheets for the main rater).  Returns None if
        there's only one cluster (no filtering needed).
        """
        clusters = self._find_connected_sheet_clusters()
        if len(clusters) <= 1:
            return None  # Only one cluster — all sheets are connected

        # Score each cluster: INPUT and OUTPUT sheets count more than others
        input_output_sheets = {
            si.sheet_name for si in self._sheet_infos
            if si.role in (SheetRole.INPUT, SheetRole.OUTPUT)
        }
        best_cluster = None
        best_score = -1
        for cluster in clusters:
            # Primary score: number of INPUT + OUTPUT sheets
            score = len(cluster & input_output_sheets)
            if score > best_score or (score == best_score and
                                       best_cluster is not None and
                                       len(cluster) > len(best_cluster)):
                best_score = score
                best_cluster = cluster

        return best_cluster

    # ── Phase 2: Extract ─────────────────────────────────────────────────

    def extract(self) -> RaterSchema:
        """
        Pull inputs, outputs, lookup tables, and formula mappings
        from the inspected workbook.
        """
        if not self._sheet_infos:
            self.inspect()

        self._extract_named_range_fields()
        self._detect_table_structures()         # FIX 4: detect tabular layouts
        self._extract_label_value_fields()
        self._extract_empty_input_cells()  # FIX 3: Detect empty cells referenced by formulas
        self._extract_lookup_tables()
        self._extract_formula_mappings()
        self._deduplicate_fields()
        self._classify_outputs_by_dag()

        rater_name = self.file_path.stem
        return RaterSchema(
            rater_name=rater_name,
            file_name=self.file_path.name,
            sheets=self._sheet_infos,
            input_fields=sorted(self._input_fields, key=lambda f: f.order),
            output_fields=sorted(self._output_fields, key=lambda f: f.order),
            lookup_tables=self._lookup_tables,
            formula_mappings=self._formula_mappings,
        )

    # ── Named range extraction ───────────────────────────────────────────

    @staticmethod
    def _clean_label(label: str) -> str:
        """Expand common abbreviations in a label produced by .title()."""
        label = label.replace(" W ", " with ")
        label = re.sub(r"\bAnnualprem\b", "Annualized Premium", label)
        label = re.sub(r"\bPremtarget\b", "Premium Target", label)
        label = re.sub(r"\bPrem Freq\b", "Premium Frequency", label)
        label = re.sub(r"\bPrem Term\b", "Premium Term", label)
        label = re.sub(r"\bBenterm\b", "Benefit Term", label)
        label = re.sub(r"\bPrem\b", "Premium", label)
        label = re.sub(r"\bSumassured\b", "Sum Assured", label)
        label = re.sub(r"\bSa\b", "Sum Assured", label)
        label = re.sub(r"\bMat Age\b", "Maturity Age", label)
        label = re.sub(r"\bDb Option\b", "DB Option", label)
        label = re.sub(r"\bDb Xtpp\b", "DB xTPP", label)
        label = re.sub(r"\bDod Int\b", "DoD Interest", label)
        label = re.sub(r"\bCalcby\b", "Calculate By", label)
        # Full-string overrides (must run after abbreviation expansion)
        label = re.sub(r"^Modal Premium with Discount$", "Premium After Discount", label)
        return label

    def _extract_named_range_fields(self):
        # Track max order for unnumbered inputs
        max_order = 0
        for name, info in self._named_ranges.items():
            m_in = _XINPUT_RE.match(name)
            m_out = _XOUTPUT_RE.match(name)

            if m_in:
                order = int(m_in.group(1))
                max_order = max(max_order, order)
                label = self._clean_label(m_in.group(2).replace("_", " ").title())
                slug = _slugify(m_in.group(2))
                value = info["computed_value"]
                options = self._find_options_for_cell(info["sheet"], info["coord"])
                ft = _guess_field_type(value, options)
                validation = self._find_validation(info["sheet"], info["coord"])

                self._input_fields.append(RaterField(
                    name=slug,
                    label=label,
                    field_type=ft,
                    default_value=value,
                    options=options,
                    validation=validation,
                    sheet=info["sheet"],
                    cell_ref=info["coord"],
                    is_output=False,
                    order=order,
                    group=self._guess_group(label, info["sheet"]),
                ))

            elif m_out:
                raw_suffix = m_out.group(1)
                # Strip leading numeric ordering prefix (e.g. "01_" or "05_")
                clean_suffix = re.sub(r"^\d+_", "", raw_suffix)
                label = self._clean_label(clean_suffix.replace("_", " ").title())
                slug = _slugify(m_out.group(1))
                value = info["computed_value"]
                formula = str(info["formula_value"]) if info["is_formula"] else None

                self._output_fields.append(RaterField(
                    name=slug,
                    label=label,
                    field_type=FieldType.NUMBER if isinstance(value, (int, float)) else FieldType.TEXT,
                    default_value=value,
                    sheet=info["sheet"],
                    cell_ref=info["coord"],
                    is_output=True,
                    formula=formula,
                    group="Premium Output",
                ))

            else:
                # Fallback: unnumbered xInput_ (e.g. xInput_Rider_Purchase)
                m_in_unnum = _XINPUT_UNNUMBERED_RE.match(name)
                if m_in_unnum:
                    max_order += 1
                    label = self._clean_label(m_in_unnum.group(1).replace("_", " ").title())
                    slug = _slugify(m_in_unnum.group(1))
                    value = info["computed_value"]
                    options = self._find_options_for_cell(info["sheet"], info["coord"])
                    ft = _guess_field_type(value, options)
                    validation = self._find_validation(info["sheet"], info["coord"])

                    self._input_fields.append(RaterField(
                        name=slug,
                        label=label,
                        field_type=ft,
                        default_value=value,
                        options=options,
                        validation=validation,
                        sheet=info["sheet"],
                        cell_ref=info["coord"],
                        is_output=False,
                        order=max_order,
                        group=self._guess_group(label, info["sheet"]),
                    ))

    # ── Table structure detection ─────────────────────────────────────────

    def _detect_table_structures(self):
        """
        Detect tabular structures (header row + data rows) in workbook sheets.

        A header row has 4+ text-only cells spanning 4+ columns — e.g. the
        Oakbridge rater row 8: "Coverage No | Coverage Type | Item Description
        | Location # | EXPIRING RISK LIMIT | …".

        Data rows (table body) follow the header until 2+ consecutive empty
        rows.  During label-value extraction, header rows are skipped entirely
        and text-valued pairs in body rows are rejected (they are descriptors
        like "Dwelling", not real inputs).

        Populates:
          self._table_headers  — {sheet: {row: {col: text}}}
          self._table_body_rows — {sheet: set(row_nums)}
        """
        primary_cluster = self._get_primary_cluster_sheets()
        _SCAN_ROLES = (SheetRole.INPUT, SheetRole.OUTPUT, SheetRole.CALCULATION)

        for si in self._sheet_infos:
            if si.role not in _SCAN_ROLES:
                continue
            if primary_cluster is not None and si.sheet_name not in primary_cluster:
                continue

            ws = self.wb[si.sheet_name]
            max_row = min(si.row_count, 200)
            max_col = min(si.col_count, 20)

            sheet_headers: dict[int, dict[int, str]] = {}
            sheet_body: set[int] = set()

            all_rows = list(ws.iter_rows(
                min_row=1, max_row=max_row,
                min_col=1, max_col=max_col,
            ))

            # Pass 1: detect header rows (4+ text cells spanning 4+ columns)
            # A real header row is MOSTLY text — at most 1 non-text cell.
            # Additionally, the text cells must have at least 4 CONSECUTIVE
            # columns to avoid false positives from data rows with scattered
            # text (e.g. "Coverage I" + "Medical Payments" + "Included" x 2).
            for r_idx, row in enumerate(all_rows, start=1):
                text_cells: dict[int, str] = {}
                non_text_count = 0
                for c_idx, cell in enumerate(row, start=1):
                    if cell.value is None:
                        continue
                    if (isinstance(cell.value, str)
                            and not _is_formula(cell)
                            and len(str(cell.value).strip()) > 1):
                        text_cells[c_idx] = str(cell.value).strip()
                    else:
                        non_text_count += 1
                if len(text_cells) >= 4 and non_text_count <= 1:
                    # Check for 4+ consecutive text columns
                    sorted_cols = sorted(text_cells.keys())
                    max_consec = 1
                    cur_consec = 1
                    for k in range(1, len(sorted_cols)):
                        if sorted_cols[k] == sorted_cols[k - 1] + 1:
                            cur_consec += 1
                            if cur_consec > max_consec:
                                max_consec = cur_consec
                        else:
                            cur_consec = 1
                    if max_consec >= 4:
                        sheet_headers[r_idx] = text_cells

            # Pass 2: mark table body rows (from header+1 until 2 empty rows)
            for hr in sorted(sheet_headers.keys()):
                empty_streak = 0
                for r_idx in range(hr + 1, len(all_rows) + 1):
                    row = all_rows[r_idx - 1]
                    non_empty = sum(1 for c in row if c.value is not None)
                    if non_empty == 0:
                        empty_streak += 1
                        if empty_streak >= 2:
                            break
                    else:
                        empty_streak = 0
                        sheet_body.add(r_idx)

            if sheet_headers:
                self._table_headers[si.sheet_name] = sheet_headers
            if sheet_body:
                self._table_body_rows[si.sheet_name] = sheet_body

    # ── Label/value pair extraction (fallback for sheets without Xinput) ──

    def _extract_label_value_fields(self):
        """
        Scan sheets tagged as INPUT, OUTPUT, or CALCULATION for label/value
        cell pairs.  INPUT sheets produce both input and output fields;
        OUTPUT / CALCULATION sheets only produce output fields (formula
        cells).  Sheets that already have Xinput_ named-range fields only
        get scanned for ADDITIONAL output fields (formula cells) that
        weren't captured by named range extraction.

        FIX 1: Only scans sheets in the *primary* formula-connected cluster,
               skipping unrelated embedded sheets (e.g. D&O in Excess Follow).
        FIX 2: Rejects garbage fields (single-char names, instruction text,
               arrow-prefixed defaults).
        """
        sheets_with_named_inputs = {f.sheet for f in self._input_fields}
        # Track which output cell_refs are already captured by named ranges
        existing_output_cells = set()
        for f in self._output_fields:
            if f.sheet and f.cell_ref:
                existing_output_cells.add(
                    f"{f.sheet}!{f.cell_ref.replace('$', '')}".upper()
                )

        # FIX 1: Determine which sheets belong to the primary cluster
        primary_cluster = self._get_primary_cluster_sheets()

        # Scan INPUT sheets for inputs+outputs,
        # and OUTPUT/CALCULATION sheets for formula-based outputs
        _SCAN_ROLES = (SheetRole.INPUT, SheetRole.OUTPUT, SheetRole.CALCULATION)

        for si in self._sheet_infos:
            if si.role not in _SCAN_ROLES:
                continue
            # For sheets with named inputs, only extract additional outputs
            has_named_inputs = si.sheet_name in sheets_with_named_inputs

            # FIX 1: Skip sheets not in the primary cluster
            if primary_cluster is not None and si.sheet_name not in primary_cluster:
                continue

            ws = self.wb[si.sheet_name]
            ws_data = self.wb_data[si.sheet_name]
            # For OUTPUT/CALCULATION sheets, or sheets with named inputs,
            # only extract formula cells as outputs (skip input extraction)
            output_only = (
                si.role in (SheetRole.OUTPUT, SheetRole.CALCULATION)
                or has_named_inputs
            )
            order = 0

            # Get table structure info for this sheet
            _sheet_headers = self._table_headers.get(si.sheet_name, {})
            _sheet_body = self._table_body_rows.get(si.sheet_name, set())

            for r_num, row in enumerate(
                ws.iter_rows(min_row=1, max_row=min(si.row_count, 200),
                             min_col=1, max_col=min(si.col_count, 12)),
                start=1,
            ):
                # Skip detected header rows entirely
                if r_num in _sheet_headers:
                    continue
                # Flag: is this row part of a table body?
                is_table_body_row = r_num in _sheet_body

                for i, cell in enumerate(row):
                    if cell.value is None or _is_formula(cell):
                        continue
                    label_text = str(cell.value).strip()
                    if not label_text or len(label_text) > 120:
                        continue
                    # Look for a value cell to the right
                    val_cell = None
                    val_cell_data = None
                    for j in range(i + 1, min(i + 4, len(row))):
                        candidate = row[j]
                        if candidate.value is not None:
                            val_cell = candidate
                            val_cell_data = ws_data[candidate.coordinate]
                            break
                    if val_cell is None:
                        continue
                    # Heuristic: labels usually end with ":" or are short text
                    if not (label_text.endswith(":") or label_text.endswith("?")
                            or (isinstance(cell.value, str) and not _is_formula(cell)
                                and len(label_text) < 80
                                and not label_text.startswith("="))):
                        continue

                    order += 1
                    slug = _slugify(_clean_label(label_text))
                    if not slug:
                        continue

                    computed_val = val_cell_data.value if val_cell_data else val_cell.value

                    # FIX 2: Reject garbage fields
                    if _is_garbage_field(slug, label_text, computed_val):
                        continue

                    # FIX 4: In table body rows, reject text→text pairs
                    # (descriptors like "Dwelling", "#1", not real inputs)
                    is_formula = _is_formula(val_cell)
                    if (is_table_body_row and not is_formula
                            and isinstance(computed_val, str)):
                        continue

                    options = self._find_options_for_cell(si.sheet_name, val_cell.coordinate)
                    ft = _guess_field_type(computed_val, options)

                    if is_formula:
                        # Skip if this output cell is already captured by a named range
                        out_key = f"{si.sheet_name}!{val_cell.coordinate}".upper().replace("$", "")
                        if out_key in existing_output_cells:
                            continue
                        self._output_fields.append(RaterField(
                            name=slug,
                            label=_clean_label(label_text),
                            field_type=ft,
                            default_value=computed_val,
                            sheet=si.sheet_name,
                            cell_ref=val_cell.coordinate,
                            is_output=True,
                            formula=str(val_cell.value),
                            group="Premium Output" if si.role == SheetRole.INPUT else si.sheet_name,
                            order=order,
                        ))
                    elif not output_only:
                        # Only add non-formula cells as inputs on INPUT sheets
                        # FIX 2: Ensure numeric inputs have non-null defaults
                        default_val = computed_val
                        if default_val is None and ft == FieldType.NUMBER:
                            default_val = 0

                        self._input_fields.append(RaterField(
                            name=slug,
                            label=_clean_label(label_text),
                            field_type=ft,
                            default_value=default_val,
                            options=options,
                            sheet=si.sheet_name,
                            cell_ref=val_cell.coordinate,
                            is_output=False,
                            group=si.sheet_name,
                            order=order,
                        ))

    # ── FIX 3: Empty input cell extraction ───────────────────────────────

    def _extract_empty_input_cells(self):
        """
        Detect empty cells in INPUT sheets that are referenced by output formulas.
        These are critical inputs that were missed because they have no default value.
        
        Strategy:
        1. Scan all output formulas to find cell references in INPUT sheets
        2. For each referenced cell NOT already in input_fields:
           - Check if it has an adjacent label (to the left)
           - Add it as an input field with None default
        
        This fixes the "Select Percentage Factor" (C38) problem where the cell
        is empty but the formula chain B20 = B6 × B15 × B10 depends on B10 = C38.
        """
        # Build set of already-extracted input cells (normalized to uppercase for comparison)
        existing_input_cells: set[str] = set()
        for f in self._input_fields:
            if f.sheet and f.cell_ref:
                key = f"{f.sheet}!{f.cell_ref}".upper().replace("$", "")
                existing_input_cells.add(key)
        
        # Get primary cluster sheets (for filtering)
        primary_cluster = self._get_primary_cluster_sheets()
        input_sheets = {
            si.sheet_name for si in self._sheet_infos
            if si.role == SheetRole.INPUT
            and (primary_cluster is None or si.sheet_name in primary_cluster)
        }
        # Build case-insensitive lookup for sheet names
        input_sheets_upper = {s.upper(): s for s in input_sheets}
        
        # Collect all cell references from output formulas
        # Store as tuple: (original_sheet_name, cell_ref, normalized_key)
        referenced_cells: dict[str, tuple[str, str, set[str]]] = {}
        
        for f in self._output_fields:
            if not f.formula:
                continue
            formula_str = str(f.formula)
            
            # Extract 'Sheet Name'!$A$1 references
            sheet_refs = re.findall(r"'([^']+)'!\$?([A-Z]+)\$?(\d+)", formula_str)
            for sheet_name, col, row_num in sheet_refs:
                if sheet_name in input_sheets:
                    norm_key = f"{sheet_name}!{col}{row_num}".upper()
                    if norm_key not in existing_input_cells:
                        if norm_key not in referenced_cells:
                            referenced_cells[norm_key] = (sheet_name, f"{col}{row_num}", set())
                        referenced_cells[norm_key][2].add(f.name)
            
            # Extract unquoted SheetName!A1 references
            unquoted_refs = re.findall(r"(?<!')([A-Za-z][A-Za-z0-9_ ]*?)!\$?([A-Z]+)\$?(\d+)", formula_str)
            for sheet_name, col, row_num in unquoted_refs:
                sheet_name_clean = sheet_name.strip()
                if sheet_name_clean in input_sheets:
                    norm_key = f"{sheet_name_clean}!{col}{row_num}".upper()
                    if norm_key not in existing_input_cells:
                        if norm_key not in referenced_cells:
                            referenced_cells[norm_key] = (sheet_name_clean, f"{col}{row_num}", set())
                        referenced_cells[norm_key][2].add(f.name)
            
            # Extract same-sheet bare cell references (e.g. C27 in VLOOKUP(C27,...))
            # These are refs on the same sheet as the output formula, without a Sheet! prefix.
            if f.sheet and f.sheet in input_sheets:
                # Match VLOOKUP(C27,...) or VLOOKUP($C$27,...)
                bare_vlookup_refs = re.findall(
                    r"(?:VLOOKUP|HLOOKUP|INDEX|MATCH)\s*\(\s*\$?([A-Z]+)\$?(\d+)\s*[,)]",
                    formula_str,
                    re.IGNORECASE,
                )
                for col, row_num in bare_vlookup_refs:
                    norm_key = f"{f.sheet}!{col}{row_num}".upper()
                    if norm_key not in existing_input_cells:
                        if norm_key not in referenced_cells:
                            referenced_cells[norm_key] = (f.sheet, f"{col}{row_num}", set())
                        referenced_cells[norm_key][2].add(f.name)

                # FIX 5: Also capture general bare cell references in
                # arithmetic expressions (e.g. E9 in =E9*103%).  Exclude
                # references that are range endpoints (A1:B2) by filtering
                # out matches adjacent to a colon.
                bare_arith_refs = re.findall(
                    r"(?<![\w:!])\$?([A-Z]{1,3})\$?(\d{1,7})(?![\w:])",
                    formula_str,
                )
                for col, row_num in bare_arith_refs:
                    norm_key = f"{f.sheet}!{col}{row_num}".upper()
                    if norm_key not in existing_input_cells:
                        if norm_key not in referenced_cells:
                            referenced_cells[norm_key] = (f.sheet, f"{col}{row_num}", set())
                        referenced_cells[norm_key][2].add(f.name)

        # FIX 5b: Scan formula cells in table body rows of INPUT sheets
        # that may not be in _output_fields (e.g., intermediate formulas
        # with garbage labels like F9 = "=E9*103%").
        for si in self._sheet_infos:
            if si.role != SheetRole.INPUT:
                continue
            if si.sheet_name not in input_sheets:
                continue
            body_rows = self._table_body_rows.get(si.sheet_name, set())
            if not body_rows:
                continue
            ws_scan = self.wb[si.sheet_name]
            for r_num, row in enumerate(
                ws_scan.iter_rows(
                    min_row=1, max_row=min(si.row_count, 200),
                    min_col=1, max_col=min(si.col_count, 20),
                ),
                start=1,
            ):
                if r_num not in body_rows:
                    continue
                for cell in row:
                    if not _is_formula(cell):
                        continue
                    formula_str = str(cell.value)
                    bare_refs = re.findall(
                        r"(?<![\w:!])\$?([A-Z]{1,3})\$?(\d{1,7})(?![\w:])",
                        formula_str,
                    )
                    for col, rn in bare_refs:
                        norm_key = f"{si.sheet_name}!{col}{rn}".upper()
                        if norm_key not in existing_input_cells:
                            if norm_key not in referenced_cells:
                                referenced_cells[norm_key] = (
                                    si.sheet_name, f"{col}{rn}", set()
                                )
                            referenced_cells[norm_key][2].add(
                                f"table_body_{r_num}"
                            )

        # For each referenced empty cell, try to create an input field
        order_offset = max((f.order for f in self._input_fields), default=0) + 1
        
        for norm_key, (sheet_name, cell_ref, referencing_outputs) in referenced_cells.items():
            
            try:
                ws = self.wb[sheet_name]
                ws_data = self.wb_data[sheet_name]
                cell = ws[cell_ref]
                cell_data = ws_data[cell_ref] if ws_data else None
                
                # Skip if the cell has a formula (it's an intermediate calculation)
                if _is_formula(cell):
                    continue
                
                # Get the cell's value (may be None/empty - that's OK)
                computed_val = cell_data.value
                
                # Look for a label — prefer column header for tabular data
                # Parse row/col from cell_ref for safety (read-only cells)
                _ref_match = re.match(r"([A-Z]+)(\d+)", cell_ref)
                if not _ref_match:
                    continue
                col_idx = sum(
                    (ord(c) - 64) * (26 ** i)
                    for i, c in enumerate(reversed(_ref_match.group(1)))
                )
                row_idx = int(_ref_match.group(2))
                label_text = None
                row_context = None   # extra context from structural columns

                # FIX 5: If the cell is in a table body, use the column
                # header as the primary label and row descriptor as context.
                sheet_headers = self._table_headers.get(sheet_name, {})
                sheet_body = self._table_body_rows.get(sheet_name, set())
                if row_idx in sheet_body and sheet_headers:
                    # Find the nearest header row above this cell
                    header_row = max(
                        (hr for hr in sheet_headers if hr < row_idx),
                        default=None,
                    )
                    if header_row and col_idx in sheet_headers[header_row]:
                        label_text = sheet_headers[header_row][col_idx]
                        # Gather row context from structural columns (A, B)
                        ctx_parts = []
                        for ctx_col in range(1, min(col_idx, 4)):
                            try:
                                ctx_cell = ws.cell(row=row_idx, column=ctx_col)
                                if ctx_cell.value and isinstance(ctx_cell.value, str):
                                    ctx_parts.append(str(ctx_cell.value).strip())
                            except Exception:
                                pass
                        if ctx_parts:
                            row_context = " ".join(ctx_parts)

                # Fallback: check up to 3 cells to the left for a label
                if not label_text:
                    for offset in range(1, 4):
                        check_col = col_idx - offset
                        if check_col < 1:
                            break
                        label_cell = ws.cell(row=row_idx, column=check_col)
                        if label_cell.value and isinstance(label_cell.value, str):
                            potential_label = str(label_cell.value).strip()
                            if (potential_label.endswith(":") or potential_label.endswith("?")
                                    or (len(potential_label) < 60
                                        and not potential_label.startswith("="))):
                                label_text = potential_label
                                break
                
                if not label_text:
                    # No label found - skip this cell
                    continue
                
                # Build final label with row context for uniqueness
                if row_context:
                    full_label = f"{row_context} - {_clean_label(label_text)}"
                else:
                    full_label = _clean_label(label_text)

                # Create a slug from the full label
                slug = _slugify(full_label)
                if not slug or len(slug) < 3:
                    continue
                
                # Skip if this name already exists
                if any(f.name == slug for f in self._input_fields):
                    # Append row number for repeating-group uniqueness
                    slug = f"{slug}_row_{row_idx}"
                    full_label = f"{full_label} (Row {row_idx})"
                    if any(f.name == slug for f in self._input_fields):
                        continue
                
                # Skip garbage fields
                if _is_garbage_field(slug, label_text, computed_val):
                    continue
                
                # Determine field type
                ft = _guess_field_type(computed_val, None)
                if ft == FieldType.TEXT and computed_val is None:
                    # Empty numeric input - guess NUMBER since it's likely a factor/rate
                    ft = FieldType.NUMBER
                
                # FIX 2: Ensure numeric inputs have non-null defaults
                default_val = computed_val
                if default_val is None and ft == FieldType.NUMBER:
                    default_val = 0

                # Add the input field
                self._input_fields.append(RaterField(
                    name=slug,
                    label=full_label,
                    field_type=ft,
                    default_value=default_val,
                    options=[],
                    sheet=sheet_name,
                    cell_ref=cell_ref,
                    is_output=False,
                    group=sheet_name,
                    order=order_offset,
                ))
                order_offset += 1
                
            except Exception as e:
                # Skip cells we can't process
                continue

    # ── Lookup table extraction ──────────────────────────────────────────

    def _extract_lookup_tables(self):
        """
        Detect rectangular data tables in sheets tagged as LOOKUP or UNKNOWN.
        A table is identified by a header row followed by >= 3 data rows.
        """
        for si in self._sheet_infos:
            if si.role not in (SheetRole.LOOKUP, SheetRole.UNKNOWN):
                continue
            ws = self.wb_data[si.sheet_name]
            tables = self._find_tables_in_sheet(ws, si)
            self._lookup_tables.extend(tables)

    def _find_tables_in_sheet(self, ws: Worksheet, si: SheetInfo) -> list[LookupTable]:
        tables: list[LookupTable] = []
        max_row = min(si.row_count, 500)
        max_col = min(si.col_count, 50)

        if ws is None:
            return []

        header_row = None
        headers: list[str] = []
        data_rows: list[dict[str, Any]] = []
        start_row = 0

        # Use iter_rows with values_only=True for efficient streaming
        # (ws.cell() random access is O(n²) in read_only mode)
        for r_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=max_row,
                                                  min_col=1, max_col=max_col,
                                                  values_only=True), start=1):
            row_vals = list(row)
            non_none = [v for v in row_vals if v is not None]

            if header_row is None:
                # Potential header: >=2 non-None string values
                str_vals = [v for v in non_none if isinstance(v, str)]
                if len(str_vals) >= 2:
                    header_row = r_idx
                    headers = []
                    for v in row_vals:
                        if v is not None:
                            headers.append(str(v).strip())
                        else:
                            break
                    start_row = r_idx
                    data_rows = []
            else:
                if len(non_none) >= len(headers) * 0.5 and len(non_none) > 0:
                    row_dict = {}
                    for idx, h in enumerate(headers):
                        cell_val = row_vals[idx] if idx < len(row_vals) else None
                        row_dict[h] = cell_val
                    data_rows.append(row_dict)
                else:
                    # End of this table
                    if len(data_rows) >= 2:
                        end_row = r_idx - 1
                        cell_range = f"A{start_row}:{chr(64 + len(headers))}{end_row}"
                        tables.append(LookupTable(
                            name=f"{si.sheet_name}_table_{len(tables) + 1}",
                            sheet=si.sheet_name,
                            columns=headers,
                            rows=data_rows,
                            cell_range=cell_range,
                        ))
                    header_row = None
                    headers = []
                    data_rows = []

        # Flush remaining
        if header_row and len(data_rows) >= 2:
            end_row = start_row + len(data_rows)
            cell_range = f"A{start_row}:{chr(64 + min(len(headers), 26))}{end_row}"
            tables.append(LookupTable(
                name=f"{si.sheet_name}_table_{len(tables) + 1}",
                sheet=si.sheet_name,
                columns=headers,
                rows=data_rows,
                cell_range=cell_range,
            ))

        return tables

    # ── Formula mapping ──────────────────────────────────────────────────

    def _extract_formula_mappings(self):
        """Build dependency graph: for each output formula, find which input cells it references."""
        input_cells = {}
        for f in self._input_fields:
            if f.cell_ref:
                # Normalise to sheet!cell
                key = f"{f.sheet}!{f.cell_ref}".replace("$", "")
                input_cells[key] = f.name
                input_cells[f.cell_ref.replace("$", "")] = f.name

        for f in self._output_fields:
            if f.formula:
                deps = []
                # Simple regex to find cell references in formula
                refs = re.findall(r"[A-Z]{1,3}\$?\d+", f.formula)
                for ref in refs:
                    clean_ref = ref.replace("$", "")
                    if clean_ref in input_cells:
                        deps.append(input_cells[clean_ref])
                self._formula_mappings.append(FormulaMapping(
                    output_name=f.name,
                    cell_ref=f.cell_ref,
                    formula=f.formula,
                    depends_on=deps,
                ))

    # ── FIX 3: Formula-DAG output classification ───────────────────────

    def _classify_outputs_by_dag(self):
        """
        Mark outputs as 'final' vs 'intermediate' using the formula reference
        graph.  An output is "final" if NO other output's formula references
        its cell.  Intermediate outputs get group="intermediate" so the
        frontend can hide them by default.

        Additionally, outputs whose name contains premium/final/total keywords
        are always kept as final.
        """
        if not self._output_fields:
            return

        # Keywords are configurable via app.config (PARSER_FINAL_OUTPUT_KEYWORDS)

        # Build lookup: "SheetName!CellRef" → field name
        output_cell_map: dict[str, str] = {}
        for f in self._output_fields:
            if f.sheet and f.cell_ref:
                key = f"{f.sheet}!{f.cell_ref.replace('$', '')}"
                output_cell_map[key] = f.name

        # Find which outputs are referenced by other outputs' formulas
        referenced_by_other: set[str] = set()
        for f in self._output_fields:
            if not f.formula:
                continue
            formula_str = str(f.formula)
            # Extract sheet-qualified references: 'Sheet Name'!A1
            sheet_refs = re.findall(r"'([^']+)'!\$?([A-Z]+)\$?(\d+)", formula_str)
            for sheet_ref, col, row_num in sheet_refs:
                clean_key = f"{sheet_ref}!{col}{row_num}"
                if clean_key in output_cell_map:
                    referenced_by_other.add(output_cell_map[clean_key])

            # Extract unquoted references: SheetName!A1
            unquoted_refs = re.findall(r"(?<!')([A-Za-z_]\w*?)!\$?([A-Z]+)\$?(\d+)", formula_str)
            for sheet_ref, col, row_num in unquoted_refs:
                clean_key = f"{sheet_ref}!{col}{row_num}"
                if clean_key in output_cell_map:
                    referenced_by_other.add(output_cell_map[clean_key])

            # Extract same-sheet references (just CellRef without sheet prefix)
            same_sheet_refs = re.findall(r"(?<![A-Za-z!])\$?([A-Z]{1,3})\$?(\d{1,7})(?!\w)", formula_str)
            for col, row_num in same_sheet_refs:
                same_key = f"{f.sheet}!{col}{row_num}"
                if same_key in output_cell_map:
                    referenced_by_other.add(output_cell_map[same_key])

        # Classify: not referenced by others = final, referenced = intermediate
        for f in self._output_fields:
            name_lower = f.name.lower()
            # Keyword override: always keep premium/final/total fields as final
            if any(kw in name_lower for kw in PARSER_FINAL_OUTPUT_KEYWORDS):
                if f.group == "intermediate":
                    f.group = f.sheet or "Premium Output"
                continue
            # DAG-based classification
            if f.name in referenced_by_other:
                f.group = "intermediate"

    # ── Helpers ──────────────────────────────────────────────────────────

    def _find_options_for_cell(self, sheet_name: str, coord: str) -> list[FieldOption]:
        """
        Try to find dropdown/validation options for a cell.
        Checks data validations and also scans matching pick-list columns.
        """
        options: list[FieldOption] = []
        try:
            ws = self.wb[sheet_name]
            # Check data validations
            if ws.data_validations and ws.data_validations.dataValidation:
                for dv in ws.data_validations.dataValidation:
                    coord_clean = coord.replace("$", "")
                    for cell_range in dv.sqref.ranges:
                        if coord_clean in str(cell_range):
                            if dv.type == "list" and dv.formula1:
                                formula = dv.formula1
                                if formula.startswith('"') and formula.endswith('"'):
                                    items = formula.strip('"').split(",")
                                    for item in items:
                                        options.append(FieldOption(label=item.strip(), value=item.strip()))
                                else:
                                    # Formula references a range — try to resolve
                                    resolved = self._resolve_range_values(formula)
                                    for v in resolved:
                                        options.append(FieldOption(label=str(v), value=v))
        except Exception:
            pass
        return options

    def _resolve_range_values(self, range_ref: str) -> list[Any]:
        """Resolve a named range or sheet!range to a list of values."""
        values = []
        try:
            # Try as sheet!range notation
            if "!" in range_ref:
                parts = range_ref.split("!")
                sname = parts[0].replace("'", "").replace("$", "")
                crange = parts[1].replace("$", "")
                ws = self._get_wb_data()
                if ws is None:
                    return values
                ws_sheet = ws[sname]
                for row in ws_sheet[crange]:
                    for cell in row:
                        if cell.value is not None:
                            values.append(cell.value)
        except Exception:
            pass
        return values

    def _find_validation(self, sheet_name: str, coord: str) -> ValidationRule | None:
        """Check named ranges like boundary conditions for min/max."""
        # Some raters (PAR Model) have boundary condition columns
        # For now return default required validation
        return ValidationRule(required=True)

    def _guess_group(self, label: str, sheet_name: str) -> str:
        """Assign a UI section/group based on the label or sheet name."""
        label_lower = label.lower()
        if any(k in label_lower for k in ("wildfire", "fire", "zone", "site")):
            return "Wildfire"
        if any(k in label_lower for k in ("deductible", "ded")):
            return "Deductible"
        if any(k in label_lower for k in ("coverage", "limit", "building")):
            return "Coverage"
        if any(k in label_lower for k in ("burglar", "alarm", "security", "lien")):
            return "Credits & Surcharges"
        if any(k in label_lower for k in ("renovation", "construction", "age", "year")):
            return "Property Details"
        if any(k in label_lower for k in ("premium", "rate")):
            return "Premium"
        return sheet_name if sheet_name else "General"

    def _deduplicate_fields(self):
        """
        Remove duplicate fields (same name) and resolve name collisions
        between inputs and outputs.

        FIX 1: When an input field and output field share the same name
        (e.g. Side_A_with_DIC_Coverage exists as both user input B9 and
        formula output C9), the output is renamed with a _calculated suffix
        to prevent the output from overwriting the user's input value in the
        calculation response.
        """
        # --- Step 1: Deduplicate inputs ---
        seen_inputs: set[str] = set()
        deduped_inputs: list[RaterField] = []
        for f in self._input_fields:
            if f.name not in seen_inputs:
                seen_inputs.add(f.name)
                deduped_inputs.append(f)
        self._input_fields = deduped_inputs

        # --- Step 2: Deduplicate outputs, resolving input/output collisions ---
        input_names = {f.name for f in self._input_fields}
        seen_outputs: set[str] = set()
        deduped_outputs: list[RaterField] = []
        for f in self._output_fields:
            original_name = f.name
            # FIX 1: If output name collides with an input, suffix it
            if f.name in input_names:
                new_name = f"{f.name}_calculated"
                f.name = new_name
                f.label = f"{f.label} (Calculated)"
                import logging as _log
                _log.getLogger(__name__).debug(
                    "Renamed output '%s' → '%s' to avoid input collision",
                    original_name, new_name,
                )
            if f.name not in seen_outputs:
                seen_outputs.add(f.name)
                deduped_outputs.append(f)
        self._output_fields = deduped_outputs
