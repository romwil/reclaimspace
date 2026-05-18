"""Setup wizard helpers: connectivity tests, path validation, status."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from reclaimspace.config_store import Settings
from reclaimspace.media_duplicates import RadarrClient, SonarrClient, _request_json
from reclaimspace.runner import list_plex_sections

CheckResult = Dict[str, Any]


def default_path_mappings(movies_root: str, tv_root: str) -> tuple[str, str]:
    movies = movies_root.rstrip("/") or "/media/movies"
    tv = tv_root.rstrip("/") or "/media/tv"
    movie_mappings = f"/data/media/movies={movies};/movies={movies}"
    tv_mappings = f"/data/media/tv={tv};/tv={tv}"
    return movie_mappings, tv_mappings


def validate_paths(
    movies_root: str,
    tv_root: str,
    quarantine_root: str,
) -> CheckResult:
    results: Dict[str, Any] = {}
    for key, path_str in (
        ("movies_root", movies_root),
        ("tv_root", tv_root),
        ("quarantine_root", quarantine_root),
    ):
        path = Path(path_str)
        exists = path.exists()
        is_dir = path.is_dir() if exists else False
        writable = os.access(path, os.W_OK | os.X_OK) if is_dir else False
        results[key] = {
            "ok": exists and is_dir and (writable if key == "quarantine_root" else True),
            "exists": exists,
            "is_dir": is_dir,
            "writable": writable,
            "path": path_str,
        }
    ok = all(item["ok"] for item in results.values())
    return {
        "ok": ok,
        "message": "All paths valid." if ok else "Fix path errors before continuing.",
        "paths": results,
    }


def test_plex(plex_url: str, plex_token: str) -> CheckResult:
    if not plex_url or not plex_token:
        return {"ok": False, "message": "Plex URL and token are required."}
    try:
        sections = list_plex_sections(
            Settings(plex_url=plex_url.strip().rstrip("/"), plex_token=plex_token.strip())
        )
        return {
            "ok": True,
            "message": f"Connected — {len(sections)} librar{'y' if len(sections) == 1 else 'ies'} found.",
            "sections": sections,
        }
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "message": str(error), "sections": []}


def test_radarr(radarr_url: str, radarr_api_key: str, movies_root: str = "") -> CheckResult:
    if not radarr_url or not radarr_api_key:
        return {"ok": False, "message": "Radarr URL and API key are required."}
    base = radarr_url.strip().rstrip("/")
    headers = {"X-Api-Key": radarr_api_key.strip()}
    try:
        status = _request_json(f"{base}/api/v3/system/status", headers=headers, timeout=15)
        version = status.get("version", "unknown")
        file_count = len(RadarrClient(base, radarr_api_key.strip()).movie_files())
        message = f"Radarr {version} — {file_count} movie files indexed."
        root_note = ""
        if movies_root:
            root_path = Path(movies_root)
            if not root_path.exists():
                root_note = f" Warning: movies root {movies_root} does not exist inside this container."
        return {
            "ok": True,
            "message": message + root_note,
            "version": version,
            "movie_file_count": file_count,
        }
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "message": str(error)}


def test_sonarr(sonarr_url: str, sonarr_api_key: str, tv_root: str = "") -> CheckResult:
    if not sonarr_url or not sonarr_api_key:
        return {"ok": False, "message": "Sonarr URL and API key are required."}
    base = sonarr_url.strip().rstrip("/")
    headers = {"X-Api-Key": sonarr_api_key.strip()}
    try:
        status = _request_json(f"{base}/api/v3/system/status", headers=headers, timeout=15)
        version = status.get("version", "unknown")
        file_count = len(SonarrClient(base, sonarr_api_key.strip()).episode_files())
        message = f"Sonarr {version} — {file_count} episode files linked."
        if tv_root:
            root_path = Path(tv_root)
            if not root_path.exists():
                message += f" Warning: TV root {tv_root} does not exist inside this container."
        return {
            "ok": True,
            "message": message,
            "version": version,
            "episode_file_count": file_count,
        }
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "message": str(error)}


def build_setup_status(settings: Settings) -> Dict[str, Any]:
    path_check = validate_paths(
        settings.movies_root,
        settings.tv_root,
        settings.quarantine_root,
    )
    plex_ok = bool(settings.plex_url and settings.plex_token)
    radarr_ok = bool(settings.radarr_url and settings.radarr_api_key)
    sonarr_ok = bool(settings.sonarr_url and settings.sonarr_api_key)
    plex_sections_ok = bool(settings.plex_movie_section or settings.plex_tv_section)

    ready_movies = (
        path_check["paths"]["movies_root"]["ok"]
        and plex_ok
        and radarr_ok
        and bool(settings.plex_movie_section)
    )
    ready_tv = (
        path_check["paths"]["tv_root"]["ok"]
        and plex_ok
        and sonarr_ok
        and bool(settings.plex_tv_section)
    )

    return {
        "onboarding_complete": settings.onboarding_complete,
        "ready_to_scan_movies": ready_movies,
        "ready_to_scan_tv": ready_tv,
        "checks": {
            "paths": path_check,
            "plex": {
                "ok": plex_ok and plex_sections_ok,
                "message": "Configured"
                if plex_ok and plex_sections_ok
                else "Plex URL, token, and library keys required.",
            },
            "radarr": {
                "ok": radarr_ok,
                "message": "Configured" if radarr_ok else "Radarr URL and API key required.",
            },
            "sonarr": {
                "ok": sonarr_ok,
                "message": "Configured" if sonarr_ok else "Sonarr URL and API key required.",
            },
        },
    }


def merge_secret_fields(incoming: Mapping[str, Any], existing: Settings) -> Dict[str, Any]:
    """Keep stored secrets when the client submits blank masked fields."""
    merged = dict(incoming)
    for field in ("plex_token", "radarr_api_key", "sonarr_api_key"):
        if not str(merged.get(field) or "").strip():
            merged[field] = getattr(existing, field)
    return merged
