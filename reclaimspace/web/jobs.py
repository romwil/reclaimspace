"""Background scan job manager."""

from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional

from reclaimspace.config_store import Settings
from reclaimspace.runner import MediaType, ScanMode, build_review_report, run_scan
from reclaimspace.web.notifications import notify_scan_complete

JobStatus = Literal["queued", "running", "completed", "failed"]

_job_manager: Optional["JobManager"] = None
_manager_lock = threading.Lock()


@dataclass
class JobProgress:
    phase: str = "queued"
    current: int = 0
    total: int = 1
    message: str = ""

    def to_dict(self) -> Dict[str, object]:
        percent = int((self.current / self.total) * 100) if self.total > 0 else 0
        return {
            "phase": self.phase,
            "current": self.current,
            "total": self.total,
            "percent": min(percent, 100),
            "message": self.message,
        }


@dataclass
class Job:
    id: str
    media_type: MediaType
    mode: ScanMode
    status: JobStatus
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    report_name: Optional[str] = None
    review_report_name: Optional[str] = None
    summary: Dict[str, object] = field(default_factory=dict)
    progress: JobProgress = field(default_factory=JobProgress)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["progress"] = self.progress.to_dict()
        return payload


class JobManager:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.reports_dir = data_dir / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def list_jobs(self) -> List[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def start_job(self, media_type: MediaType, mode: ScanMode, settings: Settings) -> Job:
        job_id = uuid.uuid4().hex[:12]
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        report_name = f"{media_type}-{mode}-{timestamp}.json"
        job = Job(
            id=job_id,
            media_type=media_type,
            mode=mode,
            status="queued",
            created_at=time.time(),
            report_name=report_name,
        )
        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, settings, report_name),
            daemon=True,
        )
        thread.start()
        return job

    def _update_progress(self, job_id: str, phase: str, current: int, total: int, message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.progress = JobProgress(
                phase=phase,
                current=current,
                total=max(total, 1),
                message=message,
            )

    def _run_job(self, job_id: str, settings: Settings, report_name: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = time.time()
            job.progress = JobProgress(phase="connecting", message="Starting scan")

        report_path = self.reports_dir / report_name

        def progress(phase: str, current: int, total: int, message: str = "") -> None:
            self._update_progress(job_id, phase, current, total, message)

        try:
            payload = run_scan(
                settings,
                job.media_type,
                job.mode,
                report_path,
                tv_page_size=settings.tv_page_size,
                progress=progress,
            )
            review_name = None
            if int(payload.get("needs_review_count") or 0) > 0:
                review_name = report_name.replace(".json", "-needs-review.json")
                build_review_report(report_path, self.reports_dir / review_name)

            with self._lock:
                job.status = "completed"
                job.finished_at = time.time()
                job.review_report_name = review_name
                job.progress = JobProgress(phase="completed", current=1, total=1, message="Done")
                job.summary = {
                    "ready_count": payload.get("ready_count", 0),
                    "candidate_count": payload.get("candidate_count", 0),
                    "needs_review_count": payload.get("needs_review_count", 0),
                    "quarantined_count": payload.get("quarantined_count", 0),
                    "missing_source_count": payload.get("missing_source_count", 0),
                }
            notify_scan_complete(settings, job.media_type, job.mode, job.summary, report_name)
        except Exception as error:  # noqa: BLE001 - surface to UI
            with self._lock:
                job.status = "failed"
                job.finished_at = time.time()
                job.error = str(error)
                job.progress = JobProgress(phase="failed", message=str(error))
                job.summary = {"traceback": traceback.format_exc()}
            notify_scan_complete(
                settings,
                job.media_type,
                job.mode,
                job.summary,
                report_name,
                failed=True,
                error=str(error),
            )


def get_job_manager() -> JobManager:
    global _job_manager
    with _manager_lock:
        if _job_manager is None:
            data_dir = Path(os.environ.get("DATA_DIR", "/config"))
            _job_manager = JobManager(data_dir)
        return _job_manager
