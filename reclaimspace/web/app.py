"""FastAPI application for Reclaimspace."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from reclaimspace import __version__
from reclaimspace.config_store import Settings, load_merged_settings, save_settings
from reclaimspace.restore import list_quarantine_manifests, restore_from_manifest
from reclaimspace.runner import list_plex_sections
from reclaimspace.web.jobs import get_job_manager
from reclaimspace.web.reports_view import report_groups_table, report_summary
from reclaimspace.web.scheduler import start_scheduler
from reclaimspace.web.setup import (
    build_setup_status,
    default_path_mappings,
    merge_secret_fields,
    test_plex,
    test_radarr,
    test_sonarr,
    validate_paths,
)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/config"))
STATIC_DIR = Path(__file__).resolve().parent / "static"

SECRET_FIELDS = ("plex_token", "radarr_api_key", "sonarr_api_key")

app = FastAPI(title="Reclaimspace", version=__version__)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class SettingsPayload(BaseModel):
    plex_url: str = ""
    plex_token: str = ""
    radarr_url: str = ""
    radarr_api_key: str = ""
    sonarr_url: str = ""
    sonarr_api_key: str = ""
    movies_root: str = ""
    tv_root: str = ""
    quarantine_root: str = ""
    path_mappings: str = ""
    tv_path_mappings: str = ""
    plex_movie_section: str = ""
    plex_tv_section: str = ""
    tv_page_size: int = Field(default=500, ge=50, le=2000)
    onboarding_complete: bool = False
    notification_webhook_url: str = ""
    schedule_dry_run_enabled: bool = False
    schedule_dry_run_interval_hours: int = Field(default=168, ge=1, le=24 * 30)
    schedule_dry_run_media_type: str = "movies"


class ScanRequest(BaseModel):
    media_type: Literal["movies", "tv"]
    mode: Literal["dry_run", "quarantine"]


class PathsPayload(BaseModel):
    movies_root: str
    tv_root: str
    quarantine_root: str


class PlexTestPayload(BaseModel):
    plex_url: str
    plex_token: str


class RadarrTestPayload(BaseModel):
    radarr_url: str
    radarr_api_key: str
    movies_root: str = ""


class SonarrTestPayload(BaseModel):
    sonarr_url: str
    sonarr_api_key: str
    tv_root: str = ""


class PathMappingsPayload(BaseModel):
    movies_root: str
    tv_root: str


class RestoreRequest(BaseModel):
    manifest_path: str
    dry_run: bool = True


def _mask_settings(settings: Settings) -> Dict[str, Any]:
    payload = asdict(settings)
    for field in SECRET_FIELDS:
        payload[f"{field}_set"] = bool(getattr(settings, field))
        payload[field] = ""
    return payload


def _reports_dir() -> Path:
    return DATA_DIR / "reports"


@app.on_event("startup")
def _startup() -> None:
    start_scheduler()


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/config", response_class=HTMLResponse)
def config_page() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "config.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "version": __version__}


def _legacy_configured(settings: Settings) -> bool:
    """Treat pre-wizard installs with saved credentials as onboarded."""
    return bool(
        settings.plex_url
        and settings.plex_token
        and settings.radarr_url
        and settings.radarr_api_key
        and settings.movies_root
    )


def _maybe_promote_legacy_onboarding(settings: Settings) -> Settings:
    """One-time promotion for installs that predated the setup wizard."""
    if settings.setup_wizard_pending:
        return settings
    if settings.onboarding_complete:
        return settings
    if not _legacy_configured(settings):
        return settings
    settings.onboarding_complete = True
    return settings


@app.get("/api/setup/status")
def setup_status() -> Dict[str, object]:
    settings = load_merged_settings(DATA_DIR)
    promoted = _maybe_promote_legacy_onboarding(settings)
    if promoted.onboarding_complete and not settings.onboarding_complete:
        save_settings(DATA_DIR, promoted)
        settings = promoted
    return build_setup_status(settings)


@app.post("/api/setup/reset")
def setup_reset_onboarding() -> Dict[str, bool]:
    """Re-open the first-run wizard without clearing stored secrets."""
    settings = load_merged_settings(DATA_DIR)
    settings.onboarding_complete = False
    settings.setup_wizard_pending = True
    save_settings(DATA_DIR, settings)
    return {"ok": True}


@app.post("/api/setup/validate-paths")
def setup_validate_paths(payload: PathsPayload) -> Dict[str, object]:
    return validate_paths(payload.movies_root, payload.tv_root, payload.quarantine_root)


@app.post("/api/setup/path-mappings")
def setup_path_mappings(payload: PathMappingsPayload) -> Dict[str, str]:
    movie_mappings, tv_mappings = default_path_mappings(payload.movies_root, payload.tv_root)
    return {"path_mappings": movie_mappings, "tv_path_mappings": tv_mappings}


@app.post("/api/setup/test/plex")
def setup_test_plex(payload: PlexTestPayload) -> Dict[str, object]:
    return test_plex(payload.plex_url, payload.plex_token)


@app.post("/api/setup/test/radarr")
def setup_test_radarr(payload: RadarrTestPayload) -> Dict[str, object]:
    return test_radarr(payload.radarr_url, payload.radarr_api_key, payload.movies_root)


@app.post("/api/setup/test/sonarr")
def setup_test_sonarr(payload: SonarrTestPayload) -> Dict[str, object]:
    return test_sonarr(payload.sonarr_url, payload.sonarr_api_key, payload.tv_root)


@app.get("/api/settings")
def get_settings() -> Dict[str, Any]:
    return _mask_settings(load_merged_settings(DATA_DIR))


@app.put("/api/settings")
def put_settings(payload: SettingsPayload) -> Dict[str, Any]:
    existing = load_merged_settings(DATA_DIR)
    merged = merge_secret_fields(payload.model_dump(), existing)
    settings = Settings.from_mapping(merged)
    if settings.onboarding_complete:
        settings.setup_wizard_pending = False
    save_settings(DATA_DIR, settings)
    return _mask_settings(settings)


@app.get("/api/plex/sections")
def plex_sections() -> List[Dict[str, str]]:
    settings = load_merged_settings(DATA_DIR)
    if not settings.plex_url or not settings.plex_token:
        raise HTTPException(status_code=400, detail="Plex URL and token are required.")
    try:
        return list_plex_sections(settings)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/api/jobs")
def jobs_list() -> List[Dict[str, object]]:
    return [job.to_dict() for job in get_job_manager().list_jobs()]


@app.post("/api/jobs")
def jobs_create(request: ScanRequest) -> Dict[str, object]:
    settings = load_merged_settings(DATA_DIR)
    if not settings.plex_url or not settings.plex_token:
        raise HTTPException(status_code=400, detail="Plex URL and token are required.")
    job = get_job_manager().start_job(request.media_type, request.mode, settings)
    return job.to_dict()


@app.get("/api/jobs/{job_id}")
def jobs_get(job_id: str) -> Dict[str, object]:
    job = get_job_manager().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.to_dict()


@app.get("/api/reports")
def reports_list(
    needs_review_only: bool = Query(default=False),
) -> List[Dict[str, object]]:
    reports_dir = _reports_dir()
    reports_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(reports_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if needs_review_only and "needs-review" not in path.name:
            continue
        if not needs_review_only and "needs-review" in path.name:
            continue
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
                "is_needs_review": "needs-review" in path.name,
            }
        )
    return items


@app.get("/api/reports/{report_name}")
def reports_get(report_name: str) -> Dict[str, object]:
    path = _safe_report_path(report_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found.")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/reports/{report_name}/summary")
def reports_summary(report_name: str) -> Dict[str, object]:
    report = reports_get(report_name)
    return report_summary(report)


@app.get("/api/reports/{report_name}/groups")
def reports_groups(
    report_name: str,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, object]:
    report = reports_get(report_name)
    return report_groups_table(report, status_filter=status, limit=limit, offset=offset)


@app.get("/api/reports/{report_name}/download")
def reports_download(report_name: str) -> FileResponse:
    path = _safe_report_path(report_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found.")
    return FileResponse(path, filename=path.name, media_type="application/json")


@app.get("/api/quarantine/manifests")
def quarantine_manifests() -> List[Dict[str, object]]:
    settings = load_merged_settings(DATA_DIR)
    return list_quarantine_manifests(Path(settings.quarantine_root))


@app.post("/api/quarantine/restore")
def quarantine_restore(request: RestoreRequest) -> Dict[str, object]:
    manifest = Path(request.manifest_path)
    if not manifest.exists():
        raise HTTPException(status_code=404, detail="Manifest not found.")
    try:
        return restore_from_manifest(manifest, dry_run=request.dry_run)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(error)) from error


def _safe_report_path(report_name: str) -> Path:
    if "/" in report_name or "\\" in report_name or report_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid report name.")
    return _reports_dir() / report_name
