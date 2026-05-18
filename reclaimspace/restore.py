"""Restore quarantined files from a manifest."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Mapping


def load_manifest(manifest_path: Path) -> Mapping[str, object]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def list_quarantine_manifests(quarantine_root: Path) -> List[Dict[str, object]]:
    if not quarantine_root.exists():
        return []
    manifests = []
    for path in sorted(quarantine_root.glob("*/manifest.json"), reverse=True):
        try:
            data = load_manifest(path)
        except (json.JSONDecodeError, OSError):
            continue
        manifests.append(
            {
                "run_id": data.get("run_id") or path.parent.name,
                "manifest_path": str(path),
                "move_count": len(data.get("moves") or []),
                "modified_at": path.stat().st_mtime,
            }
        )
    return manifests


def restore_from_manifest(manifest_path: Path, *, dry_run: bool = True) -> Dict[str, object]:
    data = load_manifest(manifest_path)
    moves = data.get("moves") or []
    if not isinstance(moves, list):
        raise ValueError("Invalid manifest: moves must be a list.")

    restored: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []

    for entry in moves:
        if not isinstance(entry, dict):
            continue
        source = Path(str(entry.get("source") or ""))
        destination = Path(str(entry.get("destination") or ""))
        if not source or not destination:
            skipped.append("invalid entry")
            continue
        if not destination.exists():
            skipped.append(str(destination))
            continue
        if source.exists():
            errors.append(f"Original already exists: {source}")
            continue
        if dry_run:
            restored.append(str(destination))
            continue
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(destination), str(source))
        restored.append(str(source))

    return {
        "dry_run": dry_run,
        "run_id": data.get("run_id"),
        "manifest_path": str(manifest_path),
        "restored_count": len(restored),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "restored_paths": restored[:50],
        "skipped_paths": skipped[:50],
        "errors": errors[:50],
    }
