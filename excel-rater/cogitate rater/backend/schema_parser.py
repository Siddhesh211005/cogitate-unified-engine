 # backend/schema_parser.py
# Parses the _Schema sheet from an Excel file into a config dict

import openpyxl
from pathlib import Path
import re


def parse_schema(xlsx_path: Path) -> dict:
    """
    Read the _Schema sheet from an Excel file and return a config dict.

    Expected _Schema columns:
      A: field    B: cell    C: type    D: label
      E: direction (input/output)    F: group    G: options (;-separated)    H: default

    Returns:
        { "sheet": str, "inputs": [...], "outputs": [...] }

    Raises:
        ValueError: if _Schema sheet is not found or is empty
    """
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)

    if "_Schema" not in wb.sheetnames:
        wb.close()
        raise ValueError(
            "No '_Schema' sheet found in this Excel file. "
            "Each rater must have a '_Schema' sheet that declares its inputs and outputs."
        )

    ws = wb["_Schema"]

    # Detect the main rater sheet (first sheet that isn't _Schema)
    rater_sheet = None
    for name in wb.sheetnames:
        if name != "_Schema":
            rater_sheet = name
            break

    inputs = []
    outputs = []
    row_count = 0

    for row in ws.iter_rows(min_row=2, values_only=True):  # skip header
        # Unpack columns A-H
        field = row[0] if len(row) > 0 else None
        cell = row[1] if len(row) > 1 else None
        ftype = row[2] if len(row) > 2 else None
        label = row[3] if len(row) > 3 else None
        direction = row[4] if len(row) > 4 else None
        group = row[5] if len(row) > 5 else None
        options_raw = row[6] if len(row) > 6 else None
        default_raw = row[7] if len(row) > 7 else None

        # Skip empty rows
        if not field or not cell:
            continue

        row_count += 1
        field = str(field).strip()
        cell = str(cell).strip()
        ftype = str(ftype).strip() if ftype else "text"
        label = str(label).strip() if label else field
        direction = str(direction).strip().lower() if direction else "input"
        group = str(group).strip() if group else "General"

        # Parse options (semicolon-separated)
        options = []
        if options_raw and str(options_raw).strip():
            raw_parts = str(options_raw).split(";")
            for part in raw_parts:
                part = part.strip()
                if not part:
                    continue
                # Try to convert to number if all options look numeric
                try:
                    options.append(int(part))
                except ValueError:
                    try:
                        options.append(float(part))
                    except ValueError:
                        options.append(part)

        # Parse default value
        default = None
        if default_raw is not None and str(default_raw).strip():
            default = str(default_raw).strip()
            if ftype == "number":
                try:
                    default = float(default) if "." in default else int(default)
                except ValueError:
                    pass

        entry = {
            "field": field,
            "cell": cell,
            "type": ftype,
            "label": label,
            "group": group,
        }

        if direction == "output":
            entry["primary"] = (row_count == 1 and direction == "output") or field == "premium"
            outputs.append(entry)
        else:
            if options:
                entry["options"] = options
                entry["type"] = "dropdown"
            if default is not None:
                entry["default"] = default
            inputs.append(entry)

    wb.close()

    if row_count == 0:
        raise ValueError("_Schema sheet is empty — no field definitions found.")

    # Mark the first output as primary if none is marked
    if outputs and not any(o.get("primary") for o in outputs):
        outputs[0]["primary"] = True

    # Override rater_sheet with the _Schema data if we can find it from cell references
    # (all cells reference the same sheet implicitly)
    config = {
        "sheet": rater_sheet or "Sheet1",
        "inputs": inputs,
        "outputs": outputs,
    }

    _inject_schedule_mode(config)
    return config


def _inject_schedule_mode(config: dict) -> None:
    """
    Heuristically infer schedule/repeater blocks from parsed inputs.

    This enables admin-uploaded complex raters to return dynamic schedule
    metadata without hardcoded, file-specific rules.
    """
    inputs = config.get("inputs") or []
    if not inputs:
        return

    row_map = {}
    for inp in inputs:
        cell = str(inp.get("cell") or "").strip().upper()
        m = re.match(r"^([A-Z]+)(\d+)$", cell)
        if not m:
            continue
        col, row_txt = m.groups()
        row = int(row_txt)
        row_map.setdefault(row, {})[col] = inp

    # Primary schedule heuristic: contiguous ranges in column D.
    # Many schedule workbooks store location selectors in D and amount cells in E,
    # but E may be absent from schema rows when defaults are blank/formula-driven.
    schedule_rows = sorted(r for r, cols in row_map.items() if "D" in cols)
    if not schedule_rows:
        return

    blocks = []
    start = schedule_rows[0]
    prev = schedule_rows[0]
    for r in schedule_rows[1:]:
        if r == prev + 1:
            prev = r
            continue
        blocks.append((start, prev))
        start = r
        prev = r
    blocks.append((start, prev))

    schedules = []
    for idx, (row_start, row_end) in enumerate(blocks, 1):
        length = row_end - row_start + 1
        # Ignore tiny incidental ranges to avoid false positives on simple raters.
        if length < 3:
            continue

        d_meta = row_map[row_start].get("D", {})

        e_meta = {}
        for rr in range(row_start, row_end + 1):
            if "E" in row_map.get(rr, {}):
                e_meta = row_map[rr].get("E", {})
                break

        group_name = str(d_meta.get("group") or "Coverage")
        key_base = re.sub(r"[^a-z0-9]+", "_", group_name.lower()).strip("_")
        key = f"{key_base}_{row_start}_{row_end}" if key_base else f"schedule_{idx}"

        schedules.append(
            {
                "key": key,
                "title": f"{group_name} ({row_start}-{row_end})",
                "rowStart": row_start,
                "rowEnd": row_end,
                "allowBlankRows": True,
                "minActiveRows": 1,
                "columns": [
                    {
                        "field": "location",
                        "column": "D",
                        "type": d_meta.get("type", "text"),
                        "label": str(d_meta.get("label") or "Location #"),
                    },
                    {
                        "field": "expiring_risk_limit",
                        "column": "E",
                        "type": e_meta.get("type", "number"),
                        "label": str(e_meta.get("label") or "Risk Limit"),
                    },
                ],
            }
        )

    if not schedules:
        return

    config["mode"] = "schedule"
    config["writeRules"] = {
        "clearUnusedRows": True,
        "emptyCellWrite": "blank",
        "rowActivePolicy": "any-non-empty-cell",
    }
    config["schedules"] = schedules
