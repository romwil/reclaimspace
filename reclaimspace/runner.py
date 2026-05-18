"""Programmatic scan runners for CLI and web UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Mapping, Optional

from reclaimspace.config_store import Settings
from reclaimspace.media_duplicates import (
    TV_PATH_PREFIXES,
    PlexClient,
    RadarrClient,
    SonarrClient,
    build_duplicate_groups,
    build_needs_review_report,
    build_quarantine_plan,
    filter_existing_quarantine_moves,
    parse_path_mappings,
    quarantine_files,
    report_groups,
)

MediaType = Literal["movies", "tv"]
ScanMode = Literal["dry_run", "quarantine"]


def run_scan(
    settings: Settings,
    media_type: MediaType,
    mode: ScanMode,
    report_path: Path,
    *,
    tv_page_size: Optional[int] = None,
) -> Mapping[str, object]:
    settings.apply_to_environ()
    if media_type == "movies":
        return _run_movies(settings, mode, report_path)
    return _run_tv(settings, mode, report_path, tv_page_size or settings.tv_page_size)


def _run_movies(settings: Settings, mode: ScanMode, report_path: Path) -> Mapping[str, object]:
    if not settings.radarr_url or not settings.radarr_api_key:
        raise RuntimeError("Radarr URL and API key are required for movie scans.")
    movies_root = Path(settings.movies_root)
    if not movies_root.exists():
        raise RuntimeError(f"MOVIES_ROOT does not exist: {movies_root}")

    path_mappings = parse_path_mappings(settings.path_mappings)
    radarr_files = RadarrClient(settings.radarr_url, settings.radarr_api_key).movie_files()
    plex_parts = PlexClient(
        settings.plex_url,
        settings.plex_token,
        movie_section=settings.plex_movie_section or None,
    ).movie_parts()
    groups = build_duplicate_groups(plex_parts, radarr_files, movies_root, path_mappings)
    payload = dict(report_groups(groups))
    payload["media_type"] = "movies"
    payload["scan_mode"] = mode

    if mode == "quarantine":
        quarantine_root = Path(settings.quarantine_root)
        plan = build_quarantine_plan(groups, movies_root, quarantine_root)
        plan, missing_sources = filter_existing_quarantine_moves(plan)
        manifest_path = quarantine_files(plan)
        payload["quarantine_manifest"] = str(manifest_path)
        payload["quarantined_count"] = len(plan.moves)
        payload["missing_source_count"] = len(missing_sources)
        payload["missing_source_paths"] = [str(path) for path in missing_sources]
    else:
        payload["quarantine_manifest"] = None
        payload["quarantined_count"] = 0
        payload["missing_source_count"] = 0
        payload["missing_source_paths"] = []

    _write_json_report(payload, report_path)
    return payload


def _run_tv(
    settings: Settings,
    mode: ScanMode,
    report_path: Path,
    page_size: int,
) -> Mapping[str, object]:
    if not settings.tv_root:
        raise RuntimeError("TV_ROOT is required for TV scans.")
    if not settings.sonarr_url or not settings.sonarr_api_key:
        raise RuntimeError("Sonarr URL and API key are required for TV scans.")
    if not settings.plex_tv_section:
        raise RuntimeError("PLEX_TV_SECTION is required for TV scans.")

    tv_root = Path(settings.tv_root)
    if not tv_root.exists():
        raise RuntimeError(f"TV_ROOT does not exist: {tv_root}")

    path_mappings = parse_path_mappings(settings.tv_path_mappings)
    plex_parts = PlexClient(settings.plex_url, settings.plex_token).tv_episode_parts(
        settings.plex_tv_section, page_size=page_size
    )
    sonarr_files = SonarrClient(settings.sonarr_url, settings.sonarr_api_key).episode_files()
    groups = build_duplicate_groups(
        plex_parts,
        sonarr_files,
        tv_root,
        path_mappings,
        arr_app_name="Sonarr",
        media_root_env="TV_ROOT",
        fallback_prefixes=TV_PATH_PREFIXES,
    )
    payload = dict(report_groups(groups))
    payload["media_type"] = "tv"
    payload["scan_mode"] = mode
    payload["plex_episode_part_count"] = len(plex_parts)
    payload["sonarr_episode_file_count"] = len(sonarr_files)

    if mode == "quarantine":
        quarantine_root = Path(settings.quarantine_root)
        plan = build_quarantine_plan(groups, tv_root, quarantine_root, media_subdir="tv")
        plan, missing_sources = filter_existing_quarantine_moves(plan)
        manifest_path = quarantine_files(plan)
        payload["quarantine_manifest"] = str(manifest_path)
        payload["quarantined_count"] = len(plan.moves)
        payload["missing_source_count"] = len(missing_sources)
        payload["missing_source_paths"] = [str(path) for path in missing_sources]
    else:
        payload["quarantine_manifest"] = None
        payload["quarantined_count"] = 0
        payload["missing_source_count"] = 0
        payload["missing_source_paths"] = []

    _write_json_report(payload, report_path)
    return payload


def build_review_report(source_report_path: Path, output_path: Path) -> Mapping[str, object]:
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    review = build_needs_review_report(source_report)
    _write_json_report(review, output_path)
    return review


def list_plex_sections(settings: Settings) -> list[dict[str, str]]:
    client = PlexClient(settings.plex_url, settings.plex_token)
    root = client._request_xml("/library/sections")
    sections = []
    for directory in root.findall(".//Directory"):
        key = directory.attrib.get("key")
        if not key:
            continue
        sections.append(
            {
                "key": key,
                "title": directory.attrib.get("title") or "",
                "type": directory.attrib.get("type") or "",
            }
        )
    return sections


def _write_json_report(payload: Mapping[str, object], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
