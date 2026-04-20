# backend/main.py
# Generic Excel Rater API — no hardcoded rater references

import json
import uuid
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

import engine
import registry
import schema_parser
import warm_sessions
from config import (
    UPLOADS_DIR,
    RATERS_DIR,
    TEMPLATES_DIR,
    WARM_START_ENABLED,
    WARM_SESSION_TTL_SEC,
    WARM_FAIL_OPEN,
)

app = FastAPI(
    title="Excel Rater System",
    description="Generic Excel-based rating engine",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _save_execution_record(template_path: Path, config: dict, meta_extra: dict):
    import time
    from datetime import datetime
    req_id = f"req-{uuid.uuid4().hex[:8]}"
    from config import RECORDS_DIR
    record_dir = RECORDS_DIR / req_id
    record_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        shutil.copy(template_path, record_dir / "template.xlsx")
        (record_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        
        meta = {
            "id": req_id,
            "created_ts": time.time(),
            "created_utc": datetime.utcnow().isoformat() + "Z",
            "slug": req_id
        }
        meta.update(meta_extra)
        (record_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"Failed to save execution record: {e}")

def _prime_upload_warm_session(upload_id: str, upload_path: Path, config: dict):
    if not warm_sessions.try_start_execution(upload_id, "warm-prime"):
        session = warm_sessions.get_session(upload_id) or {}
        print(
            f"[warm-prime] upload_id={upload_id} state=skipped active_operation={session.get('active_operation')}"
        )
        return

    try:
        warm_sessions.mark_state(upload_id, "warming", None)
        prime_meta = engine.prime_upload_session(upload_id, upload_path, config)
        warm_sessions.mark_ready(upload_id)
        print(
            f"[warm-prime] upload_id={upload_id} state=ready total_ms={prime_meta.get('timings', {}).get('total_ms')}"
        )
    except Exception as e:
        warm_sessions.mark_failed(upload_id, str(e))
        print(f"[warm-prime] upload_id={upload_id} state=failed error={e}")
    finally:
        warm_sessions.finish_execution(upload_id, "warm-prime")


def _sanitize_header_value(value: str) -> str:
    return "".join(ch if 32 <= ord(ch) <= 126 else "_" for ch in str(value))


def _resolve_session_config(upload_id: str, payload_config: Any) -> dict[str, Any]:
    if payload_config is not None and not isinstance(payload_config, dict):
        raise HTTPException(status_code=400, detail="config must be an object when provided")

    if isinstance(payload_config, dict):
        warm_sessions.update_session_config(upload_id, payload_config)
        return payload_config

    session_config = warm_sessions.get_session_config(upload_id)
    if session_config is None:
        raise HTTPException(
            status_code=400,
            detail="config is required when upload session has no stored config",
        )
    return session_config


def _start_execution_or_raise(upload_id: str, operation: str) -> None:
    session = warm_sessions.get_session(upload_id)
    if not session:
        return

    if warm_sessions.try_start_execution(upload_id, operation):
        return
    active = session.get("active_operation") or "another operation"
    raise HTTPException(
        status_code=409,
        detail=f"Calculation already in progress ({active}). Please retry shortly.",
    )


@app.get("/")
def root_redirect():
    return RedirectResponse(url="/docs")



# ===================================================================
# RECORDS - Immutable History for Both Admin & Client
# ===================================================================
from config import RECORDS_DIR
import time
from datetime import datetime

@app.get("/api/records")
def api_list_records():
    # Show newest first
    records = registry._scan_folder(RECORDS_DIR)
    # Extract sorting metadata safely
    for r in records:
        try:
            with open(RECORDS_DIR / r["slug"] / "meta.json", "r") as mf:
                m = json.load(mf)
                r["created_ts"] = m.get("created_ts", 0)
        except Exception:
            r["created_ts"] = 0
            
    records.sort(key=lambda x: x.get("created_ts", 0), reverse=True)
    return records

@app.post("/api/admin/upload-record")
async def api_upload_record(file: UploadFile = File(...)):
    req_id = f"req-{uuid.uuid4().hex[:8]}"
    record_dir = RECORDS_DIR / req_id
    record_dir.mkdir(parents=True, exist_ok=True)
    
    template_path = record_dir / "template.xlsx"
    with open(template_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        from schema_parser import parse_schema_to_config
        config = parse_schema_to_config(str(template_path))
        with open(record_dir / "config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            
        meta = {
            "id": req_id,
            "name": file.filename or req_id,
            "description": f"Autogenerated schema mapped from {file.filename}",
            "created_ts": time.time(),
            "created_utc": datetime.utcnow().isoformat() + "Z"
        }
        with open(record_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
            
    except Exception as e:
        shutil.rmtree(record_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse Excel schema: {str(e)}")
        
    return {"status": "success", "id": req_id, "name": meta["name"], "config": config}

@app.get("/api/records/{req_id}/config")
def api_record_config(req_id: str):
    try:
        return registry.load_config("records", req_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/records/{req_id}/calculate")
async def api_record_calculate(req_id: str, request: Request):
    inputs = await request.json()
    try:
        config = registry.load_config("records", req_id)
        template_path = registry.get_template_path("records", req_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        results = engine.calculate(template_path, config, inputs)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calculation error: {e}")

    return {"status": "success", "outputs": results}

# ===================================================================
# HEALTH & STATUS
# ===================================================================

@app.get("/api/health")
def health_check():
    """Health check endpoint for frontend connection testing."""
    return {
        "status": "ok",
        "version": "2.0.0",
        "message": "Backend is running and accepting requests"
    }


# ===================================================================
# RATERS — live raters from raters/ folder
# ===================================================================

@app.get("/api/raters")
def api_list_raters():
    return registry.list_raters()


@app.get("/api/raters/{slug}/config")
def api_rater_config(slug: str, background_tasks: BackgroundTasks):
    try:
        config = registry.load_config("raters", slug)
        template_path = registry.get_template_path("raters", slug)
        # Pre-warm the COM instances in the background
        background_tasks.add_task(warm_sessions.get_template_worker, template_path, config)
        return config
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/raters/{slug}/calculate")
async def api_rater_calculate(slug: str, request: Request):
    inputs = await request.json()
    try:
        config = registry.load_config("raters", slug)
        template_path = registry.get_template_path("raters", slug)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        results = engine.calculate(template_path, config, inputs)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calculation error: {e}")

    _save_execution_record(template_path, config, {
        "name": f"Client Run: {slug}",
        "description": f"Execution of rater '{slug}' from Client Panel",
        "inputs": inputs,
        "outputs": results
    })

    return {"status": "success", "outputs": results}


@app.post("/api/raters/{slug}/calculate-and-download")
async def api_rater_download(slug: str, request: Request):
    inputs = await request.json()
    try:
        config = registry.load_config("raters", slug)
        template_path = registry.get_template_path("raters", slug)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        results = engine.calculate(template_path, config, inputs, keep_file=True)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calculation error: {e}")

    output_path = results.get("_output_file")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=500, detail="Output file not found")

    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{slug}_calculated.xlsx",
    )


# ===================================================================
# TEMPLATES — test raters from templates/ folder
# ===================================================================

@app.get("/api/templates")
def api_list_templates():
    return registry.list_templates()


@app.get("/api/templates/{name}/config")
def api_template_config(name: str, background_tasks: BackgroundTasks):
    try:
        config = registry.load_config("templates", name)
        template_path = registry.get_template_path("templates", name)
        # Pre-warm the COM instances in the background
        background_tasks.add_task(warm_sessions.get_template_worker, template_path, config)
        return config
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/templates/{name}/calculate")
async def api_template_calculate(name: str, request: Request):
    inputs = await request.json()
    try:
        config = registry.load_config("templates", name)
        template_path = registry.get_template_path("templates", name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        results = engine.calculate(template_path, config, inputs)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calculation error: {e}")

    _save_execution_record(template_path, config, {
        "name": f"System Template Run: {name}",
        "description": f"Execution of base template '{name}' from Client Panel",
        "inputs": inputs,
        "outputs": results
    })

    return {"status": "success", "outputs": results}


@app.post("/api/templates/{name}/calculate-and-download")
async def api_template_download(name: str, request: Request):
    inputs = await request.json()
    try:
        config = registry.load_config("templates", name)
        template_path = registry.get_template_path("templates", name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        results = engine.calculate(template_path, config, inputs, keep_file=True)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calculation error: {e}")

    output_path = results.get("_output_file")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=500, detail="Output file not found")

    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{name}_calculated.xlsx",
    )


# ===================================================================
# ADMIN — upload, parse, test-calculate, save
# ===================================================================

@app.post("/api/admin/upload")
async def api_admin_upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload Excel, parse _Schema sheet, return config preview + upload_id."""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")

    upload_id = str(uuid.uuid4())
    upload_path = UPLOADS_DIR / f"{upload_id}.xlsx"

    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        config = schema_parser.parse_schema(upload_path)
    except ValueError as e:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Error parsing Excel: {e}")

    _save_execution_record(upload_path, config, {
        "name": f"Admin Initial Upload: {file.filename}",
        "description": "Instance automatically saved on upload.",
        "inputs": {},
        "outputs": {}
    })

    warm = {
        "state": "disabled",
        "message": "Warm start disabled",
    }

    warm_sessions.expire_old_sessions(WARM_SESSION_TTL_SEC)
    warm_sessions.create_session(upload_id, upload_path, config)

    if WARM_START_ENABLED:
        background_tasks.add_task(_prime_upload_warm_session, upload_id, upload_path, config)
        warm = {
            "state": "warming",
            "message": "Warm start initialized",
        }
    else:
        warm_sessions.mark_state(upload_id, "disabled", None)

    return {
        "upload_id": upload_id,
        "filename": file.filename,
        "config": config,
        "warm": warm,
        "warm_status": warm["state"],
        "warm_message": warm["message"],
    }


@app.get("/api/admin/warm-status/{upload_id}")
def api_admin_warm_status(upload_id: str):
    warm_sessions.expire_old_sessions(WARM_SESSION_TTL_SEC)
    session = warm_sessions.get_session(upload_id)
    if not session:
        raise HTTPException(status_code=404, detail="Warm session not found")

    return {
        "upload_id": upload_id,
        "state": session.get("state", "missing"),
        "error": session.get("error"),
        "active_operation": session.get("active_operation"),
        "created_at": session.get("created_at"),
        "last_used_at": session.get("last_used_at"),
    }


@app.post("/api/admin/test-calculate")
async def api_admin_test_calculate(request: Request):
    """Test calculate using a temporarily uploaded file + config."""
    warm_sessions.expire_old_sessions(WARM_SESSION_TTL_SEC)

    payload = await request.json()
    upload_id = payload.get("upload_id")
    payload_config = payload.get("config")
    inputs = payload.get("inputs", {})

    if not upload_id:
        raise HTTPException(status_code=400, detail="upload_id is required")

    upload_path = UPLOADS_DIR / f"{upload_id}.xlsx"
    if not upload_path.exists():
        warm_sessions.delete_session(upload_id)
        raise HTTPException(status_code=404, detail="Upload not found — please re-upload the file")

    config = _resolve_session_config(upload_id, payload_config)

    _start_execution_or_raise(upload_id, "test-calculate")

    try:
        try:
            results, meta = engine.calculate_for_upload_session(upload_id, upload_path, config, inputs)
        except Exception as e:
            if not WARM_FAIL_OPEN:
                raise HTTPException(status_code=500, detail=f"Calculation error: {e}")
            try:
                results, timings = engine.calculate_with_metrics(upload_path, config, inputs)
                meta = {
                    "warm_used": False,
                    "warm_state": "fallback-cold",
                    "timings": timings,
                }
            except Exception as inner:
                raise HTTPException(status_code=500, detail=f"Calculation error: {inner}")

        session = warm_sessions.get_session(upload_id)
        if session and session.get("state") in {"warming", "failed"}:
            warm_sessions.mark_ready(upload_id)
    finally:
        warm_sessions.finish_execution(upload_id, "test-calculate")

    print(
        f"[admin/test-calculate] upload_id={upload_id} warm_used={meta.get('warm_used')} "
        f"warm_state={meta.get('warm_state')} total_ms={meta.get('timings', {}).get('total_ms')}"
    )

    return {
        "status": "success",
        "outputs": results,
        "warm_used": bool(meta.get("warm_used", False)),
        "warm_state": meta.get("warm_state", "unknown"),
        "timings": meta.get("timings", {}),
    }


@app.post("/api/admin/test-download")
async def api_admin_test_download(request: Request):
    """Test calculate and return the calculated Excel file for verification."""
    warm_sessions.expire_old_sessions(WARM_SESSION_TTL_SEC)

    payload = await request.json()
    upload_id = payload.get("upload_id")
    payload_config = payload.get("config")
    inputs = payload.get("inputs", {})

    if not upload_id:
        raise HTTPException(status_code=400, detail="upload_id is required")

    upload_path = UPLOADS_DIR / f"{upload_id}.xlsx"
    if not upload_path.exists():
        warm_sessions.delete_session(upload_id)
        raise HTTPException(status_code=404, detail="Upload not found — please re-upload the file")

    config = _resolve_session_config(upload_id, payload_config)

    _start_execution_or_raise(upload_id, "test-download")

    try:
        try:
            results, meta = engine.calculate_for_upload_session(
                upload_id,
                upload_path,
                config,
                inputs,
                keep_file=True,
            )
        except Exception as e:
            if not WARM_FAIL_OPEN:
                raise HTTPException(status_code=500, detail=f"Calculation error: {e}")
            try:
                results, timings = engine.calculate_with_metrics(upload_path, config, inputs, keep_file=True)
                meta = {
                    "warm_used": False,
                    "warm_state": "fallback-cold",
                    "timings": timings,
                }
            except Exception as inner:
                raise HTTPException(status_code=500, detail=f"Calculation error: {inner}")

        session = warm_sessions.get_session(upload_id)
        if session and session.get("state") in {"warming", "failed"}:
            warm_sessions.mark_ready(upload_id)
    finally:
        warm_sessions.finish_execution(upload_id, "test-download")

    output_path = results.get("_output_file")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=500, detail="Output file not found")

    print(
        f"[admin/test-download] upload_id={upload_id} warm_used={meta.get('warm_used')} "
        f"warm_state={meta.get('warm_state')} total_ms={meta.get('timings', {}).get('total_ms')}"
    )

    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="test_calculated.xlsx",
        headers={
            "X-Warm-Used": "true" if meta.get("warm_used") else "false",
            "X-Warm-State": _sanitize_header_value(str(meta.get("warm_state", "unknown"))),
        },
    )


@app.post("/api/admin/save")
async def api_admin_save(request: Request):
    """Approve: save uploaded Excel + config to raters/<slug>/ or templates/<slug>/."""
    warm_sessions.expire_old_sessions(WARM_SESSION_TTL_SEC)

    payload = await request.json()
    upload_id = payload.get("upload_id")
    config = payload.get("config")
    slug = payload.get("slug", "").strip()
    name = payload.get("name", "").strip()
    description = payload.get("description", "").strip()
    source = payload.get("source", "raters").strip()

    if source not in {"raters", "templates"}:
        raise HTTPException(status_code=400, detail="source must be 'raters' or 'templates'")

    if not upload_id or not config or not slug:
        raise HTTPException(status_code=400, detail="upload_id, config, and slug are required")

    upload_path = UPLOADS_DIR / f"{upload_id}.xlsx"
    if not upload_path.exists():
        warm_sessions.delete_session(upload_id)
        raise HTTPException(status_code=404, detail="Upload not found — please re-upload the file")

    # Create destination directory
    base_dir = RATERS_DIR if source == "raters" else TEMPLATES_DIR
    rater_dir = base_dir / slug
    if rater_dir.exists():
        raise HTTPException(status_code=409, detail=f"Rater '{slug}' already exists in {source}")

    rater_dir.mkdir(parents=True, exist_ok=True)

    # Release file lock by deleting the active warmup COM session
    warm_sessions.delete_session(upload_id)
    time.sleep(1.5)

    try:
        # Copy template
        shutil.copy(upload_path, rater_dir / "template.xlsx")

        # Write config
        (rater_dir / "config.json").write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Write meta
        meta = {
            "name": name or slug,
            "slug": slug,
            "description": description,
        }
        (rater_dir / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Clean up temp upload
        upload_path.unlink(missing_ok=True)
        warm_sessions.delete_session(upload_id)

    except Exception as e:
        # Rollback on failure
        if rater_dir.exists():
            shutil.rmtree(rater_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to save rater: {e}")

    return {
        "status": "success",
        "slug": slug,
        "source": source,
        "message": f"Rater '{name or slug}' saved to {source}/{slug}/",
    }


# ===================================================================
# HEALTH
# ===================================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "raters_count": len(registry.list_raters()),
        "templates_count": len(registry.list_templates()),
    }


