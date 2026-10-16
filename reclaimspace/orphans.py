"""Find top-level media folders missing from both the manager app and Plex.

A folder is an orphan only when neither side claims it. Quarantine moves the
whole directory into the media quarantine root. Purge deletes only those
orphan-folder entries. Duplicate-file quarantine is untouched.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

from reclaimspace.appdata import directory_size
from reclaimspace.media_duplicates import (
    MOVIE_PATH_PREFIXES,
    TV_PATH_PREFIXES,
    normalize_media_path,
    parse_path_mappings,
)

# Movie and TV container prefixes both map onto the library root being scanned.
# TV scans otherwise treat every /tv path as absent and can quarantine a library.
_LIBRARY_PREFIXES = (*MOVIE_PATH_PREFIXES, *TV_PATH_PREFIXES)

_ORPHAN_KIND = "orphan_folder"
_MANIFEST_SUFFIX = ".manifest.json"
_REQUEST_TIMEOUT = 30


class OrphanSourceError(RuntimeError):
    """Radarr or Sonarr could not be read. The scan must not look empty."""


def fetch_radarr_folders(base_url: str, api_key: str) -> list[str]:
    """Return every Radarr movie folder path, including movies with no file.

    HTTP, network, and JSON failures raise OrphanSourceError. A failed request
    never looks like an empty library.
    """
    return _folder_paths(_api_url(base_url, "/api/v3/movie"), api_key)


def fetch_sonarr_folders(base_url: str, api_key: str) -> list[str]:
    """Return every Sonarr series folder path.

    HTTP, network, and JSON failures raise OrphanSourceError. A failed request
    never looks like an empty library.
    """
    return _folder_paths(_api_url(base_url, "/api/v3/series"), api_key)


def classify_orphans(
    library_root: Path,
    manager_paths: list[str],
    plex_paths: list[str],
    path_mappings: str,
) -> dict[str, list]:
    """List top-level folders that neither the manager nor Plex claims.

    Manager and Plex paths are mapped with ``normalize_media_path`` onto
    ``library_root``. Pass that library's path-mapping string. Movie and TV
    container prefixes are both applied, so ``/movies`` and ``/tv`` resolve
    into the root being scanned. A folder is present when a manager path is
    that folder, or a Plex path is inside it. Loose files directly in the
    library root are reported and are not candidates. Candidates are sorted
    by size, largest first.
    """
    root = _real_directory(library_root, "Library root")
    mappings = parse_path_mappings(path_mappings)
    directories: dict[str, Path] = {}
    loose_files: list[str] = []
    for entry in root.iterdir():
        if entry.is_symlink():
            continue
        if entry.is_dir():
            directories[entry.name] = entry
        elif entry.is_file():
            loose_files.append(entry.name)

    protected = _protected_names(root, directories, manager_paths, plex_paths, mappings)
    candidates = [
        {"name": name, "size_bytes": directory_size(path)}
        for name, path in directories.items()
        if name not in protected
    ]
    candidates.sort(key=lambda row: (-int(row["size_bytes"]), str(row["name"])))
    loose_files.sort()
    return {"candidates": candidates, "loose_files": loose_files}


def quarantine_orphan_folders(
    library_root: Path,
    quarantine_root: Path,
    names: Sequence[str],
    manager_paths: Sequence[str],
    plex_paths: Sequence[str],
    path_mappings: str,
) -> list[dict[str, str]]:
    """Move orphan folders into a timestamped run under ``quarantine_root``.

    Re-classifies before moving. A name that is no longer an orphan, escapes
    the library, or is not a real folder refuses the whole request. Nothing is
    deleted, and appdata ``_archive`` is not used.
    """
    library = _real_directory(library_root, "Library root")
    classified = classify_orphans(
        library,
        list(manager_paths),
        list(plex_paths),
        path_mappings,
    )
    orphans = {str(row["name"]) for row in classified["candidates"]}
    plans: list[tuple[str, Path]] = []
    problems: list[str] = []
    seen: set[str] = set()
    for name in names:
        try:
            if name in seen:
                raise ValueError(f"Duplicate folder: {name}")
            seen.add(name)
            source = _library_folder(library, name)
            if name not in orphans:
                raise ValueError(f"{name} is not an orphan")
            plans.append((name, source))
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        raise ValueError("Refusing to quarantine: " + "; ".join(problems))
    if not plans:
        return []

    quarantine = _quarantine_directory(quarantine_root)
    run_dir = _allocate_run_dir(quarantine)
    _require_inside(run_dir, quarantine)
    run_dir.mkdir(parents=True)
    moved: list[dict[str, str]] = []
    for name, source in plans:
        destination = run_dir / name
        manifest_path = run_dir / f"{name}{_MANIFEST_SUFFIX}"
        _require_inside(destination, quarantine)
        _require_inside(manifest_path, quarantine)
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"Quarantine destination exists: {name}")
        record = {
            "kind": _ORPHAN_KIND,
            "original_folder": str(source),
            "original_name": name,
            "destination": str(destination),
        }
        _write_json(manifest_path, record)
        try:
            shutil.move(str(source), str(destination))
        except Exception:
            manifest_path.unlink(missing_ok=True)
            raise
        moved.append(
            {
                "name": name,
                "destination": str(destination),
                "manifest": str(manifest_path),
            }
        )
    return moved


def restore_orphan_folders(
    quarantine_root: Path,
    names: Sequence[str],
) -> dict[str, list[dict[str, str]]]:
    """Move quarantined orphan folders back to the manifest's original path.

    If that path already exists, the folder stays in quarantine and the error
    is reported. Occupied destinations are never overwritten or merged.
    """
    quarantine = _real_directory(quarantine_root, "Quarantine root")
    restored: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for name in names:
        try:
            folder, manifest_path, record = _orphan_entry(quarantine, name)
            original = _original_folder(record, name)
            if original.exists() or original.is_symlink():
                raise ValueError(f"Original name is occupied: {original.name}")
            if not original.parent.is_dir() or original.parent.is_symlink():
                raise ValueError(f"Original folder is unavailable: {original}")
            shutil.move(str(folder), str(original))
            if manifest_path.is_file() and not manifest_path.is_symlink():
                if not _is_inside(manifest_path, quarantine):
                    raise ValueError(f"Path escapes quarantine: {name}")
                manifest_path.unlink()
            restored.append(
                {
                    "name": name,
                    "original_name": str(record.get("original_name") or original.name),
                    "destination": str(original),
                }
            )
        except ValueError as exc:
            errors.append({"name": name, "error": str(exc)})
    return {"restored": restored, "errors": errors}


def purge_orphan_folders(quarantine_root: Path, names: Sequence[str]) -> list[str]:
    """Permanently delete orphan-folder quarantine entries.

    Only a manifest whose kind is ``orphan_folder`` and whose folder stays
    inside ``quarantine_root`` can be deleted. Any other name refuses the
    request and deletes nothing.
    """
    quarantine = _real_directory(quarantine_root, "Quarantine root")
    targets: list[tuple[str, Path, Path]] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise ValueError(f"Duplicate folder: {name}")
        seen.add(name)
        folder, manifest_path, _record = _orphan_entry(quarantine, name)
        targets.append((name, folder, manifest_path))
    purged: list[str] = []
    for name, folder, manifest_path in targets:
        shutil.rmtree(folder)
        if manifest_path.is_file() and not manifest_path.is_symlink():
            if not _is_inside(manifest_path, quarantine):
                raise ValueError(f"Path escapes quarantine: {name}")
            manifest_path.unlink()
        purged.append(name)
    return purged


def list_orphan_quarantine(quarantine_root: Path) -> list[dict[str, object]]:
    """List quarantined orphan folders and the manifest beside each one.

    ``name`` is the path relative to ``quarantine_root`` and is what restore
    and purge accept. Duplicate-file runs are omitted.
    """
    root = Path(quarantine_root)
    if not root.exists() or not root.is_dir() or root.is_symlink():
        return []
    rows: list[dict[str, object]] = []
    for manifest_path in root.rglob(f"*{_MANIFEST_SUFFIX}"):
        if manifest_path.is_symlink() or not manifest_path.is_file():
            continue
        if not _is_inside(manifest_path, root):
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
        if not isinstance(data, dict) or data.get("kind") != _ORPHAN_KIND:
            continue
        folder = manifest_path.with_name(manifest_path.name[: -len(_MANIFEST_SUFFIX)])
        if folder.is_symlink() or not folder.is_dir() or not _is_inside(folder, root):
            continue
        original_name = data.get("original_name")
        if not isinstance(original_name, str) or not original_name.strip():
            recorded = data.get("original_folder")
            original_name = Path(str(recorded)).name if recorded else folder.name
        rows.append(
            {
                "name": folder.resolve().relative_to(root.resolve()).as_posix(),
                "original_name": original_name,
                "size_bytes": directory_size(folder),
                "manifest_path": str(manifest_path),
            }
        )
    rows.sort(key=lambda row: (-int(row["size_bytes"]), str(row["name"])))
    return rows


def _folder_paths(url: str, api_key: str) -> list[str]:
    payload = _get_json(url, api_key)
    if not isinstance(payload, list):
        raise OrphanSourceError(f"Expected a list from {url}")
    paths: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if isinstance(path, str) and path.strip():
            paths.append(path.strip())
    return paths


def _api_url(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise OrphanSourceError("Missing media manager URL.")
    return base + path


def _get_json(url: str, api_key: str) -> object:
    request = urllib.request.Request(url, headers={"X-Api-Key": api_key})
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as error:
        raise OrphanSourceError(f"Could not read {url}: {error}") from error


def _protected_names(
    root: Path,
    directories: Mapping[str, Path],
    manager_paths: Sequence[str],
    plex_paths: Sequence[str],
    mappings: Sequence[tuple[str, Path]],
) -> set[str]:
    protected: set[str] = set()
    for raw_path in manager_paths:
        parts = _relative_parts(_normalize(raw_path, root, mappings), root)
        if parts is not None and len(parts) == 1 and parts[0] in directories:
            protected.add(parts[0])
    for raw_path in plex_paths:
        parts = _relative_parts(_normalize(raw_path, root, mappings), root)
        if parts is not None and parts[0] in directories:
            protected.add(parts[0])
    return protected


def _normalize(
    raw_path: str,
    root: Path,
    mappings: Sequence[tuple[str, Path]],
) -> Path:
    return normalize_media_path(
        raw_path,
        root,
        mappings,
        fallback_prefixes=_LIBRARY_PREFIXES,
    )


def _relative_parts(path: Path, root: Path) -> tuple[str, ...] | None:
    cleaned = Path(os.path.normpath(str(path)))
    cleaned_root = Path(os.path.normpath(str(root)))
    try:
        relative = cleaned.relative_to(cleaned_root)
    except ValueError:
        return None
    if not relative.parts:
        return None
    return relative.parts


def _library_folder(library_root: Path, name: str) -> Path:
    safe = _safe_child_name(name)
    child = Path(library_root) / safe
    if child.is_symlink() or not _is_inside(child, library_root):
        raise ValueError(f"Path escapes the library: {name}")
    if child.exists() and child.resolve().parent != library_root.resolve():
        raise ValueError(f"Path escapes the library: {name}")
    if not child.is_dir():
        raise ValueError(f"Folder does not exist: {name}")
    return child


def _safe_child_name(name: str) -> str:
    if not isinstance(name, str) or not name or name.strip() != name:
        raise ValueError(f"Path escapes the library: {name!r}")
    if "/" in name or "\\" in name or "\x00" in name or name in {".", ".."}:
        raise ValueError(f"Path escapes the library: {name}")
    return name


def _safe_relative(name: str) -> Path:
    if not isinstance(name, str) or not name or name.strip() != name:
        raise ValueError(f"Path escapes quarantine: {name!r}")
    if "\\" in name or "\x00" in name or name.startswith("/"):
        raise ValueError(f"Path escapes quarantine: {name}")
    parts = PurePosixPath(name).parts
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError(f"Path escapes quarantine: {name}")
    return Path(*parts)


def _orphan_entry(
    quarantine_root: Path, name: str
) -> tuple[Path, Path, dict[str, object]]:
    relative = _safe_relative(name)
    folder = quarantine_root.resolve() / relative
    if folder.is_symlink() or not _is_inside(folder, quarantine_root):
        raise ValueError(f"Path escapes quarantine: {name}")
    manifest_path = _manifest_for(folder)
    if (
        manifest_path is None
        or manifest_path.is_symlink()
        or not manifest_path.is_file()
        or not _is_inside(manifest_path, quarantine_root)
    ):
        raise ValueError(f"Orphan manifest is missing: {name}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as error:
        raise ValueError(f"Orphan manifest is unreadable: {name}") from error
    if not isinstance(data, dict) or data.get("kind") != _ORPHAN_KIND:
        raise ValueError(f"Refusing non-orphan manifest: {name}")
    destination = data.get("destination")
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError(f"Orphan manifest is missing a destination: {name}")
    recorded = Path(destination)
    if recorded.is_symlink() or not _is_inside(recorded, quarantine_root):
        raise ValueError(f"Path escapes quarantine: {name}")
    if not folder.is_dir():
        raise ValueError(f"Orphan folder is missing: {name}")
    if folder.resolve() != recorded.resolve():
        raise ValueError(f"Manifest destination does not match {name}")
    return folder, manifest_path, data


def _manifest_for(folder: Path) -> Path | None:
    sibling = folder.parent / f"{folder.name}{_MANIFEST_SUFFIX}"
    if sibling.is_file() and not sibling.is_symlink():
        return sibling
    nested = folder / "manifest.json"
    if nested.is_file() and not nested.is_symlink():
        return nested
    return None


def _original_folder(record: Mapping[str, object], name: str) -> Path:
    original = record.get("original_folder")
    if not isinstance(original, str) or not original.strip():
        raise ValueError(f"Manifest is missing the original folder: {name}")
    return Path(original)


def _real_directory(path: Path, label: str) -> Path:
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"{label} is not a directory: {path}")
    return root


def _quarantine_directory(path: Path) -> Path:
    root = Path(path)
    if root.is_symlink():
        raise ValueError(f"Quarantine root is not a directory: {path}")
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"Quarantine root is not a directory: {path}")
    return root


def _allocate_run_dir(quarantine_root: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = quarantine_root / f"orphan-{stamp}"
    if not candidate.exists():
        return candidate
    for suffix in range(1, 1000):
        alternative = quarantine_root / f"orphan-{stamp}-{suffix}"
        if not alternative.exists():
            return alternative
    raise ValueError("Could not allocate an orphan quarantine directory.")


def _is_inside(path: Path, root: Path) -> bool:
    if path.is_symlink():
        return False
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved == resolved_root:
        return False
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return False
    return True


def _require_inside(path: Path, root: Path) -> None:
    if not _is_inside(path, root):
        raise ValueError(f"Path escapes quarantine: {path}")


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
