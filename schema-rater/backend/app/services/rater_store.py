"""
Rater Store
===========
Manages file-based persistence of uploaded rater workbooks and their
parsed JSON schemas.  Each rater gets a UUID directory under DATA_DIR:

    data/raters/<rater_id>/
        original.xlsx          – the uploaded file
        schema.json            – parsed RaterSchema
        metadata.json          – name, upload timestamp, etc.

See docs/ARCHITECTURE.md §3 and docs/IMPLEMENTATION_PLAN.md §1.2 for design.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR
from app.models.schemas import RaterSchema


class RaterStore:
    """File-system backed storage for rater workbooks and schemas."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or DATA_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ── Write operations ─────────────────────────────────────────────

    def save_rater(self, rater_id: str, file_bytes: bytes, filename: str) -> Path:
        """Persist the uploaded Excel file (using original filename)."""
        rater_dir = self.base_dir / rater_id
        rater_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename: keep original name for formulas library compatibility
        safe_name = filename.replace("/", "_").replace("\\", "_")
        dest = rater_dir / safe_name
        dest.write_bytes(file_bytes)

        # Write metadata
        meta = {
            "rater_id": rater_id,
            "original_filename": filename,
            "saved_filename": safe_name,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        (rater_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return dest

    def save_schema(self, rater_id: str, schema: RaterSchema) -> Path:
        """Persist the parsed schema as JSON."""
        rater_dir = self.base_dir / rater_id
        rater_dir.mkdir(parents=True, exist_ok=True)

        dest = rater_dir / "schema.json"
        dest.write_text(schema.model_dump_json(indent=2), encoding="utf-8")

        # Also update metadata with rater_name
        meta_path = rater_dir / "metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            meta = {"rater_id": rater_id}
        meta["rater_name"] = schema.rater_name
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        return dest

    def update_metadata(self, rater_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge additional metadata into the persisted rater record."""
        rater_dir = self.base_dir / rater_id
        rater_dir.mkdir(parents=True, exist_ok=True)

        meta_path = rater_dir / "metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            meta = {"rater_id": rater_id}

        for key, value in updates.items():
            if value is not None:
                meta[key] = value

        meta["rater_id"] = rater_id
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta

    # ── Read operations ──────────────────────────────────────────────

    def load_schema(self, rater_id: str) -> RaterSchema:
        """Load and return the cached schema for a rater."""
        schema_path = self.base_dir / rater_id / "schema.json"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema not found for rater {rater_id}")
        return RaterSchema.model_validate_json(schema_path.read_text(encoding="utf-8"))

    def get_workbook_path(self, rater_id: str) -> Path:
        """Return the path to the original .xlsx file."""
        rater_dir = self.base_dir / rater_id
        if not rater_dir.exists():
            raise FileNotFoundError(f"Workbook not found for rater {rater_id}")
        # Try to read saved_filename from metadata
        meta_path = rater_dir / "metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            saved = meta.get("saved_filename")
            if saved:
                path = rater_dir / saved
                if path.exists():
                    return path
        # Fallback: find first .xlsx file
        for f in rater_dir.iterdir():
            if f.suffix.lower() in (".xlsx", ".xls"):
                return f
        raise FileNotFoundError(f"Workbook not found for rater {rater_id}")

    def list_raters(self) -> list[dict[str, Any]]:
        """List all uploaded raters with basic metadata."""
        raters = []
        if not self.base_dir.exists():
            return raters
        for d in sorted(self.base_dir.iterdir()):
            if not d.is_dir():
                continue
            meta_path = d / "metadata.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                raters.append(meta)
            else:
                # Minimal entry
                raters.append({"rater_id": d.name})
        return raters

    def rater_exists(self, rater_id: str) -> bool:
        return (self.base_dir / rater_id / "schema.json").exists()

    def find_by_filename(self, filename: str) -> dict[str, Any] | None:
        """Find an existing rater by original filename. Returns metadata if found."""
        if not self.base_dir.exists():
            return None
        for d in self.base_dir.iterdir():
            if not d.is_dir():
                continue
            meta_path = d / "metadata.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("original_filename") == filename:
                    return meta
        return None

    def delete_rater(self, rater_id: str) -> bool:
        """Delete a rater directory and all its contents."""
        rater_dir = self.base_dir / rater_id
        if rater_dir.exists():
            shutil.rmtree(rater_dir)
            return True
        return False
