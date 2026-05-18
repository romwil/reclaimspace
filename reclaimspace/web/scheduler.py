"""Simple scheduled dry-run scans (in-process)."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Optional

from reclaimspace.config_store import Settings, load_merged_settings
from reclaimspace.web.jobs import get_job_manager

_scheduler_thread: Optional[threading.Thread] = None
_scheduler_lock = threading.Lock()
_last_run_at: float = 0.0


def start_scheduler() -> None:
    global _scheduler_thread
    with _scheduler_lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return
        _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
        _scheduler_thread.start()


def _scheduler_loop() -> None:
    global _last_run_at
    while True:
        time.sleep(60)
        data_dir = Path(os.environ.get("DATA_DIR", "/config"))
        settings = load_merged_settings(data_dir)
        if not settings.schedule_dry_run_enabled or not settings.onboarding_complete:
            continue
        interval_seconds = max(settings.schedule_dry_run_interval_hours, 1) * 3600
        now = time.time()
        if _last_run_at and (now - _last_run_at) < interval_seconds:
            continue
        manager = get_job_manager()
        active = any(
            job.status in ("queued", "running")
            for job in manager.list_jobs()
        )
        if active:
            continue
        media_type = settings.schedule_dry_run_media_type
        if media_type not in ("movies", "tv"):
            media_type = "movies"
        if media_type == "movies" and not (settings.plex_url and settings.radarr_url):
            continue
        if media_type == "tv" and not (settings.plex_url and settings.sonarr_url):
            continue
        manager.start_job(media_type, "dry_run", settings)  # type: ignore[arg-type]
        _last_run_at = now
