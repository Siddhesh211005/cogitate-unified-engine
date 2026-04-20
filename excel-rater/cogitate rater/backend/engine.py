# backend/engine.py
# Native Microsoft Excel COM calculation engine

import tempfile
import time
from pathlib import Path
from typing import Any

def _get_session_dirs() -> tuple[Path, Path]:
    base = Path(tempfile.gettempdir()) / "rater_sessions"
    input_dir = base / "input"
    output_dir = base / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return input_dir, output_dir

def _coerce_by_type(value: Any, value_type: str) -> Any:
    if value is None:
        return None
    if value_type != "number":
        return value
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return value

def _write_schedule_inputs(ws, config: dict[str, Any], input_data: dict[str, Any]) -> set[str]:
    schedule_defs = config.get("schedules") or []
    if not schedule_defs:
        return set()
    schedule_payload = input_data.get("schedules") or input_data.get("_schedules")
    if not isinstance(schedule_payload, dict):
        return set()
    write_rules = config.get("writeRules") or {}
    clear_unused = bool(write_rules.get("clearUnusedRows", True))
    controlled_cells: set[str] = set()
    for sched in schedule_defs:
        key = sched.get("key")
        if not key:
            continue
        row_start = sched.get("rowStart")
        row_end = sched.get("rowEnd")
        columns = sched.get("columns") or []
        if not isinstance(row_start, int) or not isinstance(row_end, int):
            continue
        if row_end < row_start:
            continue
        rows_data = schedule_payload.get(key) or []
        if not isinstance(rows_data, list):
            rows_data = []
        for idx, row_num in enumerate(range(row_start, row_end + 1)):
            row_data = rows_data[idx] if idx < len(rows_data) and isinstance(rows_data[idx], dict) else {}
            row_active = any(v not in (None, "") for v in row_data.values())
            for col_def in columns:
                col = col_def.get("column")
                field = col_def.get("field")
                value_type = col_def.get("type")
                if not col or not field:
                    continue
                cell_ref = f"{col}{row_num}"
                controlled_cells.add(cell_ref)
                if row_active and field in row_data:
                    ws[cell_ref] = _coerce_by_type(row_data.get(field), value_type)
                elif clear_unused:
                    ws[cell_ref] = None
    return controlled_cells

def _build_prime_inputs(config: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for item in config.get("inputs") or []:
        field = item.get("field")
        if not field:
            continue
        if "default" in item:
            payload[field] = item.get("default")
    return payload

def calculate(template_path: Path, config: dict[str, Any], input_data: dict[str, Any], keep_file: bool = False) -> dict:
    """
    Generic calculation cycle via ExcelWorker (win32com).
    """
    import warm_sessions
    worker = warm_sessions.get_template_worker(template_path, config)
    if not worker or not worker.is_ready or worker.error:
        raise RuntimeError(f"Excel COM worker unavailable. Error: {worker.error if worker else 'Worker None'}")
    
    outputs, _ = worker.calculate_sync(input_data, keep_file=keep_file)
    return outputs

def calculate_with_metrics(
    template_path: Path,
    config: dict[str, Any],
    input_data: dict[str, Any],
    keep_file: bool = False,
) -> tuple[dict[str, Any], dict[str, float]]:
    import warm_sessions
    worker = warm_sessions.get_template_worker(template_path, config)
    if not worker or not worker.is_ready or worker.error:
        raise RuntimeError(f"Excel COM worker unavailable.")
    
    return worker.calculate_sync(input_data, keep_file=keep_file)

def prime_upload_session(upload_id: str, upload_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    import warm_sessions
    from excel_worker import ExcelWorker
    
    worker = ExcelWorker(upload_id, upload_path, config)
    worker.start()
    
    start_wait = time.time()
    while not worker.is_ready and worker.error is None:
        if time.time() - start_wait > 30:
            worker.shutdown()
            raise RuntimeError("Excel worker start timeout")
        time.sleep(0.1)
        
    if worker.error:
        worker.shutdown()
        raise RuntimeError(f"Failed to start Excel worker: {worker.error}")
        
    warm_sessions.set_worker(upload_id, worker)
    prime_inputs = _build_prime_inputs(config)
    _, timings = worker.calculate_sync(prime_inputs, keep_file=False)
    
    return {
        "upload_id": upload_id,
        "timings": timings,
    }

def calculate_for_upload_session(
    upload_id: str,
    upload_path: Path,
    config: dict[str, Any],
    input_data: dict[str, Any],
    keep_file: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    import warm_sessions
    
    worker = warm_sessions.get_worker(upload_id)
    if worker and worker.is_ready and not worker.error:
        warm_sessions.mark_used(upload_id)
        outputs, timings = worker.calculate_sync(input_data, keep_file=keep_file)
        return outputs, {
            "warm_state": "active",
            "warm_used": True,
            "timings": timings,
        }
        
    raise RuntimeError(f"Missing active Excel worker for upload_id: {upload_id}")
