"""Appdata share scan: container mounts, workspace detection, and file actions.

Mounts come from the Unraid GraphQL API when a URL and API key are set, using
the same ``x-api-key`` POST /graphql style as Hand of Franklin. Otherwise an
explicit Docker socket is read with ``GET /containers/json?all=1``. If neither
source is available, scans fail closed.

Settings is duck-typed (``appdata_root``, ``appdata_host_prefixes``,
``code_root``, ``unraid_api_url``, ``unraid_api_key``, ``docker_socket``).
"""

from __future__ import annotations

import json
import os
import posixpath
import shutil
import socket
import stat
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path
from typing import Iterable, Mapping, Sequence

ARCHIVE_NAME = "_archive"
_EXACT_MARKERS = (
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
)
_GRAPHQL_CONTAINERS = """query {
  docker {
    containers {
      names
      state
      mounts
    }
  }
}"""
_REQUEST_TIMEOUT = 30


class AppdataSourceError(RuntimeError):
    """Unraid or Docker could not be queried, so in-use folders are unknown."""


@dataclass
class ContainerMount:
    container: str
    state: str
    source: str


@dataclass
class WorkspaceDetection:
    is_code: bool
    evidence: list[str]


class _UnixHTTPConnection(HTTPConnection):
    """HTTP over a Docker Engine unix socket, matching Franklin's client."""

    def __init__(self, uds_path: str):
        super().__init__("localhost")
        self._uds_path = uds_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(_REQUEST_TIMEOUT)
        self.sock.connect(self._uds_path)


def fetch_mounts(settings: object) -> list[ContainerMount]:
    """Return bind mounts for every container, running or stopped.

    Prefers ``unraid_api_url`` plus ``unraid_api_key``. Falls back to
    ``docker_socket`` only when that path is set and exists. Raises
    ``AppdataSourceError`` when neither source can be read.
    """
    url = _setting(settings, "unraid_api_url")
    key = _setting(settings, "unraid_api_key")
    if url and key:
        payload = _post_graphql(url, key, _GRAPHQL_CONTAINERS)
        return _mounts_from_graphql(payload)

    socket_path = _setting(settings, "docker_socket")
    if socket_path and os.path.exists(socket_path):
        raw = _docker_socket_json(socket_path, "/containers/json?all=1")
        return _mounts_from_docker_api(raw)

    raise AppdataSourceError(
        "No Appdata mount source: set the Unraid API URL and key, or a Docker socket that exists."
    )


def parse_host_prefixes(settings: object) -> list[str]:
    """Split ``appdata_host_prefixes`` on semicolons and normalize each path."""
    raw = getattr(settings, "appdata_host_prefixes", "") or ""
    prefixes: list[str] = []
    for part in str(raw).split(";"):
        normalized = _norm_posix(part)
        if normalized and normalized not in prefixes:
            prefixes.append(normalized)
    return prefixes


def mount_folder_name(source: str, prefixes: Sequence[str]) -> str | None:
    """Map a container source path to an appdata folder name.

    ``None`` when ``source`` is outside every prefix. ``""`` when ``source``
    is exactly a prefix (the whole share). Otherwise the first path segment
    under the first matching prefix.
    """
    src = _norm_posix(source)
    if not src:
        return None
    for prefix in prefixes:
        pref = _norm_posix(prefix)
        if not pref:
            continue
        if src == pref:
            return ""
        needle = pref + "/"
        if src.startswith(needle):
            segment = src[len(needle) :].split("/", 1)[0]
            if segment in {"", ".", ".."}:
                return None
            return segment
    return None


def detect_workspace(folder: Path) -> WorkspaceDetection:
    """Detect a code workspace from the folder itself, not its descendants.

    A top-level ``.git`` directory is enough. Otherwise at least two distinct
    marker kinds are required.
    """
    root = Path(folder)
    if not root.is_dir():
        return WorkspaceDetection(False, [])
    try:
        entries = list(root.iterdir())
    except OSError:
        return WorkspaceDetection(False, [])

    evidence: list[str] = []
    git_dir = root / ".git"
    is_git = git_dir.is_dir() and not git_dir.is_symlink()
    if is_git:
        evidence.append(".git")

    by_name = {entry.name: entry for entry in entries}
    marker_kinds = 0
    for marker in _EXACT_MARKERS:
        entry = by_name.get(marker)
        if entry is not None and _is_regular_file(entry):
            evidence.append(marker)
            marker_kinds += 1

    solutions = _matching_files(entries, ".sln")
    if solutions:
        evidence.extend(solutions)
        marker_kinds += 1
    workspaces = _matching_files(entries, ".code-workspace")
    if workspaces:
        evidence.extend(workspaces)
        marker_kinds += 1

    return WorkspaceDetection(is_git or marker_kinds >= 2, evidence)


def directory_size(path: Path) -> int:
    """Total size in bytes of regular files under ``path``.

    Symlinks are not followed and do not add the target's size.
    """
    root = Path(path)
    try:
        info = root.lstat()
    except OSError:
        return 0
    if stat.S_ISLNK(info.st_mode):
        return 0
    if stat.S_ISREG(info.st_mode):
        return info.st_size
    if not stat.S_ISDIR(info.st_mode):
        return 0

    total = 0
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            try:
                file_info = os.lstat(file_path)
            except OSError:
                continue
            if stat.S_ISREG(file_info.st_mode):
                total += file_info.st_size
    return total


def classify_appdata(
    appdata_root: Path,
    prefixes: Sequence[str],
    mounts: Sequence[ContainerMount],
) -> dict[str, list[dict[str, object]]]:
    """Split top-level folders into sized candidates and in-use rows.

    ``_archive`` is omitted. A mount of a host prefix with no child segment
    does not mark folders in use. A folder is in use only when a mount names
    that folder or a path inside it. Candidates are sorted by size, largest
    first.
    """
    root = _existing_dir(appdata_root)
    names = _real_top_level_names(root)
    usage = _usage_map(names, mounts, prefixes)
    candidates: list[dict[str, object]] = []
    in_use: list[dict[str, object]] = []
    for name in names:
        containers = usage.get(name)
        if containers:
            in_use.append({"name": name, "containers": containers})
            continue
        folder = root / name
        detection = detect_workspace(folder)
        candidates.append(
            {
                "name": name,
                "size_bytes": directory_size(folder),
                "is_code": detection.is_code,
                "evidence": list(detection.evidence),
            }
        )
    candidates.sort(key=lambda row: (-int(row["size_bytes"]), str(row["name"])))
    in_use.sort(key=lambda row: str(row["name"]))
    return {"candidates": candidates, "in_use": in_use}


def list_children(appdata_root: Path, relative: str) -> list[dict[str, object]]:
    """List one directory level under ``appdata_root``.

    ``relative`` must stay inside the root after resolve. Directory rows
    report ``size_bytes`` 0; only files report their own size.
    """
    root = _existing_dir(appdata_root)
    target = _resolve_inside(root, relative)
    if not target.is_dir():
        raise ValueError(f"Not a directory: {relative}")
    rows: list[dict[str, object]] = []
    for entry in target.iterdir():
        if entry.is_symlink():
            try:
                size = entry.lstat().st_size
            except OSError:
                size = 0
            rows.append({"name": entry.name, "is_dir": False, "size_bytes": size})
            continue
        if entry.is_dir():
            rows.append({"name": entry.name, "is_dir": True, "size_bytes": 0})
            continue
        try:
            size = entry.stat().st_size if entry.is_file() else 0
        except OSError:
            size = 0
        rows.append({"name": entry.name, "is_dir": False, "size_bytes": size})
    rows.sort(key=lambda row: str(row["name"]))
    return rows


def quarantine_folders(
    appdata_root: Path,
    names: Sequence[str],
    mounts: Sequence[ContainerMount],
    prefixes: Sequence[str],
) -> list[dict[str, str]]:
    """Move folders into ``appdata_root/_archive``.

    Refuses in-use folders and path escape before moving anything. When the
    archive name already exists, a timestamp suffix is appended. Each move
    writes a sibling manifest recording the original name and destination.
    """
    root = _existing_dir(appdata_root)
    plans = _plan_all(names, root, mounts, prefixes, verb="quarantine")
    archive = root / ARCHIVE_NAME
    archive.mkdir(exist_ok=True)
    _require_inside(archive, root)
    moved: list[dict[str, str]] = []
    for name, source in plans:
        destination = _unique_archive_dir(archive, name)
        _require_inside(destination, archive)
        manifest_path = archive / f"{destination.name}.manifest.json"
        record = {
            "original_name": name,
            "destination": str(destination),
            "archived_name": destination.name,
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


def delete_folders(
    appdata_root: Path,
    names: Sequence[str],
    mounts: Sequence[ContainerMount],
    prefixes: Sequence[str],
) -> list[str]:
    """Recursively delete top-level folders.

    Refuses in-use folders, ``_archive``, and any path that escapes the root.
    Nothing is deleted when any requested name is refused.
    """
    root = _existing_dir(appdata_root)
    plans = _plan_all(names, root, mounts, prefixes, verb="delete")
    deleted: list[str] = []
    for name, source in plans:
        shutil.rmtree(source)
        deleted.append(name)
    return deleted


def remove_empty_top_level(
    appdata_root: Path,
    mounts: Sequence[ContainerMount],
    prefixes: Sequence[str],
) -> list[str]:
    """Remove top-level directories that contain nothing.

    Skips ``_archive`` and any folder a container still mounts.
    """
    root = _existing_dir(appdata_root)
    names = _real_top_level_names(root)
    usage = _usage_map(names, mounts, prefixes)
    removed: list[str] = []
    for name in names:
        if usage.get(name):
            continue
        folder = root / name
        try:
            next(folder.iterdir())
        except StopIteration:
            folder.rmdir()
            removed.append(name)
    return removed


def list_archive(appdata_root: Path) -> list[dict[str, object]]:
    """List ``_archive`` directories and the manifest written beside each."""
    root = _existing_dir(appdata_root)
    archive = root / ARCHIVE_NAME
    if not archive.is_dir():
        return []
    rows: list[dict[str, object]] = []
    for entry in archive.iterdir():
        if entry.is_symlink() or not entry.is_dir():
            continue
        manifest_path = archive / f"{entry.name}.manifest.json"
        original = entry.name
        if manifest_path.is_file():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            if isinstance(data, dict) and isinstance(data.get("original_name"), str):
                recorded = data["original_name"].strip()
                if recorded:
                    original = recorded
        rows.append(
            {
                "name": entry.name,
                "size_bytes": directory_size(entry),
                "original_name": original,
                "manifest_path": str(manifest_path) if manifest_path.is_file() else "",
            }
        )
    rows.sort(key=lambda row: (-int(row["size_bytes"]), str(row["name"])))
    return rows


def restore_archive(appdata_root: Path, names: Sequence[str]) -> dict[str, list[dict[str, str]]]:
    """Move archive entries back to their original top-level names.

    If the original name is already occupied, that folder is left in
    ``_archive`` and reported in ``errors``. Other names are still restored.
    Occupied destinations are never overwritten or merged.
    """
    root = _existing_dir(appdata_root)
    _preflight_names(names, root_label="archive")
    archive = root / ARCHIVE_NAME
    restored: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for name in names:
        try:
            entry = _archive_entry(archive, name)
            original = _original_name(entry)
            _safe_child_name(original)
            destination = _direct_child(root, original)
            if destination.exists() or destination.is_symlink():
                raise ValueError(f"Original name is occupied: {original}")
            manifest_path = archive / f"{entry.name}.manifest.json"
            shutil.move(str(entry), str(destination))
            if manifest_path.is_symlink() or manifest_path.is_file():
                if manifest_path.parent.resolve() != archive.resolve():
                    raise ValueError(f"Path escapes {ARCHIVE_NAME}: {name}")
                manifest_path.unlink()
            restored.append(
                {
                    "name": name,
                    "original_name": original,
                    "destination": str(destination),
                }
            )
        except ValueError as exc:
            errors.append({"name": name, "error": str(exc)})
    return {"restored": restored, "errors": errors}


def purge_archive(appdata_root: Path, names: Sequence[str]) -> list[str]:
    """Recursively delete archive entries and their manifests.

    Every path has to stay under ``_archive``. A refusing name deletes nothing.
    """
    root = _existing_dir(appdata_root)
    archive = root / ARCHIVE_NAME
    if not archive.is_dir():
        raise ValueError("Archive directory does not exist.")
    archive_resolved = archive.resolve()
    targets: list[tuple[str, Path, Path]] = []
    for name in names:
        entry = _archive_entry(archive, name)
        manifest_path = archive_resolved / f"{entry.name}.manifest.json"
        _require_inside(entry, archive_resolved)
        if manifest_path.parent.resolve() != archive_resolved:
            raise ValueError(f"Path escapes {ARCHIVE_NAME}: {name}")
        if manifest_path.exists() and not manifest_path.is_symlink():
            if not _is_within(manifest_path.resolve(), archive_resolved):
                raise ValueError(f"Path escapes {ARCHIVE_NAME}: {name}")
        targets.append((name, entry, manifest_path))
    purged: list[str] = []
    for name, entry, manifest_path in targets:
        shutil.rmtree(entry)
        if manifest_path.is_symlink() or manifest_path.is_file():
            manifest_path.unlink()
        purged.append(name)
    return purged


def migrate_workspace(
    appdata_root: Path,
    code_root: Path,
    names: Sequence[str],
    mounts: Sequence[ContainerMount],
    prefixes: Sequence[str],
    data_dir: Path,
) -> dict[str, list[dict[str, object]]]:
    """Move code workspaces from appdata into ``code_root``.

    Rechecks mounts and workspace markers. Refuses folders that are in use,
    not code, or whose destination already exists, and refuses when either
    path escapes its root. Nothing is moved when any name is refused. Writes
    an audit manifest under ``data_dir``; this is not an archive entry.
    """
    root = _existing_dir(appdata_root)
    destination_root = Path(code_root).resolve()
    if destination_root.exists() and not destination_root.is_dir():
        raise ValueError(f"Code root is not a directory: {code_root}")
    plans = _plan_migrations(names, root, destination_root, mounts, prefixes)
    destination_root.mkdir(parents=True, exist_ok=True)
    audit_dir = Path(data_dir) / "appdata-migrations"
    audit_dir.mkdir(parents=True, exist_ok=True)
    migrated: list[dict[str, object]] = []
    for name, source, destination, evidence in plans:
        manifest_path = _unique_audit_file(audit_dir, name)
        record = {
            "name": name,
            "source": str(source),
            "destination": str(destination),
            "evidence": evidence,
            "migrated_at": _iso_now(),
        }
        _write_json(manifest_path, record)
        try:
            shutil.move(str(source), str(destination))
        except Exception:
            manifest_path.unlink(missing_ok=True)
            raise
        migrated.append(
            {
                "name": name,
                "destination": str(destination),
                "manifest": str(manifest_path),
                "evidence": evidence,
            }
        )
    return {"migrated": migrated, "errors": []}


def _setting(settings: object, name: str) -> str:
    value = getattr(settings, name, "")
    if value is None:
        return ""
    return str(value).strip()


def _post_graphql(url: str, api_key: str, query: str) -> Mapping[str, object]:
    payload = json.dumps({"query": query}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise AppdataSourceError(f"Unraid API HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise AppdataSourceError(f"Could not reach Unraid API: {error.reason}") from error
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppdataSourceError("Unraid API did not return JSON.") from error
    if not isinstance(body, dict):
        raise AppdataSourceError("Unraid API returned an unexpected payload.")
    if body.get("errors"):
        raise AppdataSourceError(f"Unraid API GraphQL error: {body.get('errors')}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise AppdataSourceError("Unraid API response did not include data.")
    return data


def _docker_socket_json(uds_path: str, path: str) -> object:
    conn = _UnixHTTPConnection(uds_path)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        raw = response.read()
        status = response.status
    except OSError as error:
        raise AppdataSourceError(f"Could not read Docker socket: {error}") from error
    finally:
        conn.close()
    if status != 200:
        detail = raw.decode("utf-8", errors="replace")[:300]
        raise AppdataSourceError(f"Docker socket HTTP {status}: {detail}")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppdataSourceError("Docker socket did not return JSON.") from error


def _mounts_from_graphql(data: Mapping[str, object]) -> list[ContainerMount]:
    docker = data.get("docker")
    if not isinstance(docker, dict) or not isinstance(docker.get("containers"), list):
        raise AppdataSourceError("Unraid API response did not include docker.containers.")
    return _mounts_from_containers(docker["containers"], name_key="names", state_key="state", mounts_key="mounts")


def _mounts_from_docker_api(payload: object) -> list[ContainerMount]:
    if isinstance(payload, dict):
        containers = payload.get("containers", payload.get("Containers"))
    else:
        containers = payload
    if not isinstance(containers, list):
        raise AppdataSourceError("Docker socket response did not include a container list.")
    return _mounts_from_containers(
        containers,
        name_key=("Names", "names"),
        state_key=("State", "state"),
        mounts_key=("Mounts", "mounts"),
    )


def _mounts_from_containers(
    containers: Iterable[object],
    *,
    name_key: str | tuple[str, ...],
    state_key: str | tuple[str, ...],
    mounts_key: str | tuple[str, ...],
) -> list[ContainerMount]:
    mounts: list[ContainerMount] = []
    for container in containers:
        if not isinstance(container, dict):
            raise AppdataSourceError("Container list contained a non-object entry.")
        name = _container_name(_field(container, name_key))
        state = str(_field(container, state_key) or "")
        for source in _bind_sources(_field(container, mounts_key)):
            mounts.append(ContainerMount(container=name, state=state, source=source))
    return mounts


def _field(container: Mapping[str, object], key: str | tuple[str, ...]) -> object:
    keys = (key,) if isinstance(key, str) else key
    for candidate in keys:
        if candidate in container:
            return container[candidate]
    return None


def _container_name(raw: object) -> str:
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list) and raw:
        values = [str(raw[0])]
    else:
        values = []
    if not values:
        return "unknown"
    return values[0].strip().lstrip("/") or "unknown"


def _bind_sources(raw: object) -> list[str]:
    entries = _mount_entries(raw)
    sources: list[str] = []
    for entry in entries:
        mount_type = entry.get("Type", entry.get("type", ""))
        if str(mount_type).lower() != "bind":
            continue
        source = entry.get("Source", entry.get("source", ""))
        if isinstance(source, str) and source.strip():
            sources.append(source)
    return sources


def _mount_entries(raw: object) -> list[dict[str, object]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as error:
            raise AppdataSourceError("Container mounts were not valid JSON.") from error
    if not isinstance(raw, list):
        raise AppdataSourceError("Container mounts were not a list.")
    entries: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except json.JSONDecodeError as error:
                raise AppdataSourceError("Container mounts were not valid JSON.") from error
        if not isinstance(item, dict):
            raise AppdataSourceError("Container mounts contained a non-object entry.")
        entries.append(item)
    return entries


def _norm_posix(path: str) -> str:
    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        return ""
    normalized = posixpath.normpath(raw)
    if normalized in {"", "."}:
        return ""
    return normalized


def _require_prefixes(prefixes: Sequence[str]) -> list[str]:
    cleaned = [normalized for prefix in prefixes if (normalized := _norm_posix(prefix))]
    if not cleaned:
        raise AppdataSourceError(
            "Appdata host prefixes are not configured, so mounted folders cannot be identified."
        )
    return cleaned


def _usage_map(
    names: Sequence[str],
    mounts: Sequence[ContainerMount],
    prefixes: Sequence[str],
) -> dict[str, list[str]]:
    """Folder name to container names.

    An exact host-prefix mount (the share root, with no child segment) is
    ignored. A folder is in use only when a mount names that folder or a
    path inside it, including mounts from stopped containers.
    """
    cleaned = _require_prefixes(prefixes)
    specific: dict[str, set[str]] = {}
    for mount in mounts:
        folder = mount_folder_name(mount.source, cleaned)
        if not folder:
            continue
        container = (mount.container or "").strip().lstrip("/") or "unknown"
        specific.setdefault(folder, set()).add(container)
    usage: dict[str, list[str]] = {}
    for name in names:
        containers = specific.get(name)
        if containers:
            usage[name] = sorted(containers)
    return usage


def _containers_for(
    name: str,
    mounts: Sequence[ContainerMount],
    prefixes: Sequence[str],
) -> list[str]:
    return _usage_map([name], mounts, prefixes).get(name, [])


def _matching_files(entries: Sequence[Path], suffix: str) -> list[str]:
    matched = [
        entry.name
        for entry in entries
        if entry.name.endswith(suffix) and _is_regular_file(entry)
    ]
    return sorted(matched)


def _is_regular_file(path: Path) -> bool:
    try:
        info = path.stat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode)


def _existing_dir(path: Path) -> Path:
    root = Path(path).resolve()
    if not root.is_dir():
        raise AppdataSourceError(f"Appdata root is not a directory: {path}")
    return root


def _real_top_level_names(root: Path) -> list[str]:
    names: list[str] = []
    for entry in root.iterdir():
        if entry.name == ARCHIVE_NAME or entry.is_symlink() or not entry.is_dir():
            continue
        names.append(entry.name)
    return sorted(names)


def _safe_child_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise ValueError(f"Path escapes the root: {name!r}")
    if name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        raise ValueError(f"Path escapes the root: {name}")
    if Path(name).is_absolute():
        raise ValueError(f"Path escapes the root: {name}")
    return name


def _preflight_names(names: Sequence[str], *, root_label: str) -> None:
    for name in names:
        try:
            _safe_child_name(name)
        except ValueError as exc:
            raise ValueError(f"Path escapes {root_label}: {name}") from exc


def _direct_child(root: Path, name: str) -> Path:
    safe = _safe_child_name(name)
    root_resolved = root.resolve()
    candidate = root_resolved / safe
    if candidate.is_symlink():
        raise ValueError(f"Path escapes the root: {name}")
    if candidate.parent != root_resolved:
        raise ValueError(f"Path escapes the root: {name}")
    if candidate.exists():
        resolved = candidate.resolve()
        if resolved.parent != root_resolved or not _is_within(resolved, root_resolved):
            raise ValueError(f"Path escapes the root: {name}")
    return candidate


def _resolve_inside(root: Path, relative: str) -> Path:
    if relative is None:
        raise ValueError("Path escapes appdata root.")
    text = str(relative)
    if text.startswith("/") or text.startswith("\\") or "\x00" in text:
        raise ValueError(f"Path escapes appdata root: {relative}")
    candidate = (root / text).resolve()
    if not _is_within(candidate, root):
        raise ValueError(f"Path escapes appdata root: {relative}")
    return candidate


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _require_inside(path: Path, root: Path) -> None:
    resolved_root = root.resolve()
    resolved = path.resolve() if path.exists() or path.is_symlink() else path
    if path.is_symlink() or not _is_within(resolved, resolved_root):
        raise ValueError(f"Path escapes the root: {path}")


def _plan_all(
    names: Sequence[str],
    root: Path,
    mounts: Sequence[ContainerMount],
    prefixes: Sequence[str],
    *,
    verb: str,
) -> list[tuple[str, Path]]:
    problems: list[str] = []
    plans: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for name in names:
        try:
            if name in seen:
                raise ValueError(f"Duplicate folder: {name}")
            seen.add(name)
            source = _guard_folder(root, name, mounts, prefixes)
            plans.append((name, source))
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        raise ValueError(f"Refusing to {verb}: " + "; ".join(problems))
    return plans


def _guard_folder(
    root: Path,
    name: str,
    mounts: Sequence[ContainerMount],
    prefixes: Sequence[str],
) -> Path:
    if name == ARCHIVE_NAME:
        raise ValueError(f"Refusing {ARCHIVE_NAME}.")
    source = _direct_child(root, name)
    if not source.is_dir():
        raise ValueError(f"Folder does not exist: {name}")
    containers = _containers_for(name, mounts, prefixes)
    if containers:
        raise ValueError(f"{name} is in use by {', '.join(containers)}")
    return source


def _plan_migrations(
    names: Sequence[str],
    root: Path,
    code_root: Path,
    mounts: Sequence[ContainerMount],
    prefixes: Sequence[str],
) -> list[tuple[str, Path, Path, list[str]]]:
    problems: list[str] = []
    plans: list[tuple[str, Path, Path, list[str]]] = []
    seen: set[str] = set()
    for name in names:
        try:
            if name in seen:
                raise ValueError(f"Duplicate folder: {name}")
            seen.add(name)
            source = _guard_folder(root, name, mounts, prefixes)
            detection = detect_workspace(source)
            if not detection.is_code:
                raise ValueError(f"{name} is not a code workspace.")
            destination = _direct_child(code_root, name)
            if destination.exists() or destination.is_symlink():
                raise ValueError(f"Destination already exists: {destination}")
            _require_inside(source, root)
            _require_inside(destination, code_root)
            plans.append((name, source, destination, list(detection.evidence)))
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        raise ValueError("Refusing to migrate: " + "; ".join(problems))
    return plans


def _unique_archive_dir(archive: Path, name: str) -> Path:
    def taken(candidate: Path) -> bool:
        manifest = archive / f"{candidate.name}.manifest.json"
        return candidate.exists() or manifest.exists()

    candidate = archive / name
    if not taken(candidate):
        return candidate
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = archive / f"{name}-{stamp}"
    counter = 2
    while taken(candidate):
        candidate = archive / f"{name}-{stamp}-{counter}"
        counter += 1
    return candidate


def _unique_audit_file(audit_dir: Path, name: str) -> Path:
    candidate = audit_dir / f"{name}.json"
    if not candidate.exists():
        return candidate
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = audit_dir / f"{name}-{stamp}.json"
    counter = 2
    while candidate.exists():
        candidate = audit_dir / f"{name}-{stamp}-{counter}.json"
        counter += 1
    return candidate


def _archive_entry(archive: Path, name: str) -> Path:
    if not archive.is_dir():
        raise ValueError("Archive directory does not exist.")
    entry = _direct_child(archive, name)
    archive_resolved = archive.resolve()
    if entry.is_symlink() or not entry.is_dir():
        raise ValueError(f"Archive entry does not exist: {name}")
    resolved = entry.resolve()
    if resolved.parent != archive_resolved or not _is_within(resolved, archive_resolved):
        raise ValueError(f"Path escapes {ARCHIVE_NAME}: {name}")
    return entry


def _original_name(entry: Path) -> str:
    manifest_path = entry.parent / f"{entry.name}.manifest.json"
    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Archive manifest is unreadable: {entry.name}") from error
        if isinstance(data, dict) and isinstance(data.get("original_name"), str):
            original = data["original_name"].strip()
            if original:
                return original
    return entry.name


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
