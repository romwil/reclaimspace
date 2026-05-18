"""FastAPI application for Reclaimspace."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from reclaimspace import __version__
from reclaimspace.config_store import Settings, load_merged_settings, save_settings
from reclaimspace.runner import list_plex_sections
from reclaimspace.web.jobs import JobManager, get_job_manager

DATA_DIR = Path(os.environ.get("DATA_DIR", "/config"))
STATIC_DIR = Path(__file__).resolve().parent / "static"

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


class ScanRequest(BaseModel):
    media_type: Literal["movies", "tv"]
    mode: Literal["dry_run", "quarantine"]


def _settings_response() -> Dict[str, Any]:
    settings = load_merged_settings(DATA_DIR)
    return asdict(settings)


def _reports_dir() -> Path:
    return DATA_DIR / "reports"


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/settings")
def get_settings() -> Dict[str, Any]:
    return _settings_response()


@app.put("/api/settings")
def put_settings(payload: SettingsPayload) -> Dict[str, Any]:
    settings = Settings.from_mapping(payload.model_dump())
    save_settings(DATA_DIR, settings)
    return asdict(settings)


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
    manager = get_job_manager()
    return [job.to_dict() for job in manager.list_jobs()]


@app.post("/api/jobs")
def jobs_create(request: ScanRequest) -> Dict[str, object]:
    settings = load_merged_settings(DATA_DIR)
    if not settings.plex_url or not settings.plex_token:
        raise HTTPException(status_code=400, detail="Plex URL and token are required.")
    manager = get_job_manager()
    job = manager.start_job(request.media_type, request.mode, settings)
    return job.to_dict()


@app.get("/api/jobs/{job_id}")
def jobs_get(job_id: str) -> Dict[str, object]:
    manager = get_job_manager()
    job = manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.to_dict()


@app.get("/api/reports")
def reports_list() -> List[Dict[str, object]]:
    reports_dir = _reports_dir()
    reports_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(reports_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            }
        )
    return items


@app.get("/api/reports/{report_name}")
def reports_get(report_name: str) -> Dict[str, object]:
    path = _safe_report_path(report_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found.")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/reports/{report_name}/download")
def reports_download(report_name: str) -> FileResponse:
    path = _safe_report_path(report_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found.")
    return FileResponse(path, filename=path.name, media_type="application/json")


def _safe_report_path(report_name: str) -> Path:
    if "/" in report_name or "\\" in report_name or report_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid report name.")
    return _reports_dir() / report_name
