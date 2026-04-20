# backend/registry.py
# Discovers raters from apps/raters/ and apps/templates/ folders

import json
from pathlib import Path
from config import RATERS_DIR, TEMPLATES_DIR


def _scan_folder(base_dir):
    """Scan a folder for rater subfolders (each must have config.json + template.xlsx)."""
    results = []
    if not base_dir.exists():
        return results

    for sub in sorted(base_dir.iterdir()):
        if not sub.is_dir():
            continue
        config_file = sub / "config.json"
        template_file = sub / "template.xlsx"
        meta_file = sub / "meta.json"

        if not config_file.exists() or not template_file.exists():
            continue

        entry = {"slug": sub.name, "has_config": True, "has_template": True}

        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                entry["name"] = meta.get("name", sub.name)
                entry["description"] = meta.get("description", "")
            except Exception:
                entry["name"] = sub.name
        else:
            entry["name"] = sub.name

        results.append(entry)

    return results


def list_raters():
    return _scan_folder(RATERS_DIR)


def list_templates():
    return _scan_folder(TEMPLATES_DIR)


def _get_base_dir(source):
    if source == "raters":
        return RATERS_DIR
    elif source == "templates":
        return TEMPLATES_DIR
    elif source == "records":
        from config import RECORDS_DIR
        return RECORDS_DIR
    else:
        raise ValueError(f"Unknown source: {source}")


def load_config(source, slug):
    """Load config.json for a rater from either apps/raters/ or apps/templates/."""
    base = _get_base_dir(source)
    config_file = base / slug / "config.json"
    if not config_file.exists():
        raise FileNotFoundError(f"Config not found: {source}/{slug}/config.json")
    return json.loads(config_file.read_text(encoding="utf-8"))


def get_template_path(source, slug):
    """Get the template.xlsx path for a rater."""
    base = _get_base_dir(source)
    template_file = base / slug / "template.xlsx"
    if not template_file.exists():
        raise FileNotFoundError(f"Template not found: {source}/{slug}/template.xlsx")
    return template_file
