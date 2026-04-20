# backend/warm_sessions.py
# In-memory warm session registry for local pilot.

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_sessions: dict[str, dict[str, Any]] = {}
_lock = threading.RLock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_workers = {}

def get_worker(upload_id: str) -> Any:
    with _lock:
        return _workers.get(upload_id)

def set_worker(upload_id: str, worker: Any) -> None:
    with _lock:
        _workers[upload_id] = worker

def cleanup_worker(upload_id: str) -> None:
    with _lock:
        worker = _workers.pop(upload_id, None)
    if worker:
        # Avoid blocking thread while COM worker shuts down
        threading.Thread(target=worker.shutdown, daemon=True).start()


def _copy_config(config: dict[str, Any]) -> dict[str, Any]:
    # Force plain JSON-compatible data to avoid accidental shared mutation.
    return json.loads(json.dumps(config))


def create_session(upload_id: str, upload_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    session = {
        "upload_id": upload_id,
        "upload_path": str(upload_path),
        "config_hash": compute_config_hash(config),
        "config": _copy_config(config),
        "state": "warming",
        "created_at": _utc_now_iso(),
        "created_at_ts": now,
        "last_used_at": None,
        "last_used_at_ts": None,
        "error": None,
        "active_operation": None,
        "active_operation_started_at": None,
    }
    with _lock:
        _sessions[upload_id] = session
        return dict(session)


def get_session(upload_id: str) -> dict[str, Any] | None:
    with _lock:
        session = _sessions.get(upload_id)
        return dict(session) if session else None


def mark_state(upload_id: str, state: str, error: str | None = None) -> dict[str, Any] | None:
    with _lock:
        session = _sessions.get(upload_id)
        if not session:
            return None
        session["state"] = state
        session["error"] = error
        return dict(session)


def get_session_config(upload_id: str) -> dict[str, Any] | None:
    with _lock:
        session = _sessions.get(upload_id)
        if not session:
            return None
        config = session.get("config")
        if not isinstance(config, dict):
            return None
        return _copy_config(config)


def update_session_config(upload_id: str, config: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        session = _sessions.get(upload_id)
        if not session:
            return None
        session["config"] = _copy_config(config)
        session["config_hash"] = compute_config_hash(config)
        return dict(session)


def try_start_execution(upload_id: str, operation: str) -> bool:
    with _lock:
        session = _sessions.get(upload_id)
        if not session:
            return False
        if session.get("active_operation"):
            return False
        session["active_operation"] = operation
        session["active_operation_started_at"] = _utc_now_iso()
        return True


def finish_execution(upload_id: str, operation: str | None = None) -> dict[str, Any] | None:
    with _lock:
        session = _sessions.get(upload_id)
        if not session:
            return None
        if operation and session.get("active_operation") not in {None, operation}:
            return dict(session)
        session["active_operation"] = None
        session["active_operation_started_at"] = None
        return dict(session)


def mark_ready(upload_id: str) -> dict[str, Any] | None:
    return mark_state(upload_id, "ready", None)


def mark_failed(upload_id: str, error: str) -> dict[str, Any] | None:
    return mark_state(upload_id, "failed", error)


def mark_used(upload_id: str) -> dict[str, Any] | None:
    now = time.time()
    with _lock:
        session = _sessions.get(upload_id)
        if not session:
            return None
        session["last_used_at"] = _utc_now_iso()
        session["last_used_at_ts"] = now
        return dict(session)


def delete_session(upload_id: str) -> bool:
    cleanup_worker(upload_id)
    with _lock:
        return _sessions.pop(upload_id, None) is not None


def expire_old_sessions(ttl_sec: int) -> list[str]:
    now = time.time()
    expired: list[str] = []

    with _lock:
        for upload_id, session in list(_sessions.items()):
            created_at_ts = float(session.get("created_at_ts") or 0)
            if now - created_at_ts > ttl_sec:
                session["state"] = "expired"
                expired.append(upload_id)

        for upload_id in expired:
            _sessions.pop(upload_id, None)

    for upload_id in expired:
        cleanup_worker(upload_id)

    return expired


def _reset_for_tests() -> None:
    with _lock:
        for upload_id in list(_workers.keys()):
            cleanup_worker(upload_id)
        _sessions.clear()


class TemplateWorkerPool:
    def __init__(self, size, name_prefix, template_path, config):
        self.workers = []
        self._index = 0
        import threading
        self._lock = threading.Lock()
        from excel_worker import ExcelWorker
        import time
        for i in range(size):
            worker = ExcelWorker(f"{name_prefix}-{i}", template_path, config)
            worker.start()
            self.workers.append(worker)
        start_wait = time.time()
        while True:
            all_ready = all(w.is_ready or w.error for w in self.workers)
            if all_ready:
                break
            if time.time() - start_wait > 60:
                for w in self.workers: w.shutdown()
                self.error = "Excel worker start timeout"
                self.is_ready = False
                return
            time.sleep(0.1)
        errors = [w.error for w in self.workers if w.error]
        if errors:
            self.error = f"Failed to start Excel worker: {errors[0]}"
            for w in self.workers: w.shutdown()
            self.is_ready = False
            return
        self.is_ready = True
        self.error = None

    def calculate_sync(self, input_data, keep_file=False, timeout=60.0):
        with self._lock:
            # find least busy worker
            worker = min(self.workers, key=lambda w: w.request_queue.qsize())
        return worker.calculate_sync(input_data, keep_file=keep_file, timeout=timeout)

    def shutdown(self):
        import threading
        for w in self.workers:
            threading.Thread(target=w.shutdown, daemon=True).start()

def get_template_worker(template_path, config):
    path_str = str(template_path)
    with _lock:
        if path_str not in _workers:
            _workers[path_str] = TemplateWorkerPool(4, f"tpl-{hash(path_str)}", template_path, config)
        return _workers[path_str]