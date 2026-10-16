"""Async Appdata migrate jobs. Temp directories and fake mounts only."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from reclaimspace.appdata import ContainerMount
from reclaimspace.web import app as app_module
from reclaimspace.web.app import AppdataNamesPayload, appdata_migrate, appdata_migrate_status

_ENV_KEYS = (
    "APPDATA_ROOT",
    "CODE_ROOT",
    "APPDATA_HOST_PREFIXES",
    "UNRAID_API_URL",
    "UNRAID_API_KEY",
    "DOCKER_SOCKET",
    "DATA_DIR",
)
_ROOT = Path(__file__).resolve().parents[1]


def _wait_job(job_id: str, timeout: float = 5) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        last = appdata_migrate_status(job_id)
        if last.get("status") in {"completed", "failed"}:
            return last
        time.sleep(0.02)
    raise AssertionError(f"migration did not finish: {last}")


class MigrateApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_env = {key: os.environ.pop(key) for key in _ENV_KEYS if key in os.environ}
        self._saved_data_dir = app_module.DATA_DIR
        self._empty = tempfile.TemporaryDirectory()
        self.addCleanup(self._empty.cleanup)
        app_module.DATA_DIR = Path(self._empty.name)
        with app_module._appdata_migrates_lock:
            app_module._appdata_migrates.clear()
            app_module._appdata_migrate_active.clear()

    def tearDown(self) -> None:
        app_module.DATA_DIR = self._saved_data_dir
        os.environ.update(self._saved_env)

    def test_post_returns_before_the_move_finishes_and_reports_progress(self) -> None:
        entered = threading.Event()
        release = threading.Event()

        def blocked(**kwargs: object) -> dict[str, object]:
            entered.set()
            self.assertTrue(release.wait(5))
            name = list(kwargs["names"])[0]  # type: ignore[index]
            return {
                "migrated": [
                    {
                        "name": name,
                        "destination": "/code/" + str(name),
                        "manifest": "m",
                        "evidence": [],
                    }
                ],
                "errors": [],
            }

        def cleanup() -> None:
            release.set()
            for _ in range(50):
                with app_module._appdata_migrates_lock:
                    if "tool" not in app_module._appdata_migrate_active:
                        return
                time.sleep(0.02)

        self.addCleanup(cleanup)
        with (
            mock.patch.object(app_module, "fetch_mounts", return_value=[]),
            mock.patch.object(app_module, "migrate_workspace", side_effect=blocked),
        ):
            started = time.monotonic()
            body = appdata_migrate(AppdataNamesPayload(names=["tool"]))
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 1.5)
            self.assertEqual(set(body), {"job_id"})
            self.assertNotIn("migrated", body)
            self.assertTrue(entered.wait(2))
            progress = appdata_migrate_status(body["job_id"])
            self.assertEqual(progress["status"], "running")
            self.assertEqual(progress["progress"]["current"], "tool")
            self.assertEqual(progress["progress"]["index"], 1)
            self.assertEqual(progress["progress"]["total"], 1)
            release.set()
            finished = _wait_job(body["job_id"])
            self.assertEqual(finished["status"], "completed")
            self.assertEqual(finished["result"]["migrated"][0]["name"], "tool")

    def test_completed_job_reports_migrated_names(self) -> None:
        with self._tree() as (root, code, _data):
            with mock.patch.object(app_module, "fetch_mounts", return_value=[]):
                body = appdata_migrate(AppdataNamesPayload(names=["tool"]))
                finished = _wait_job(body["job_id"])
            self.assertEqual(finished["status"], "completed")
            self.assertIsNone(finished["error"])
            self.assertEqual(finished["result"]["errors"], [])
            migrated = finished["result"]["migrated"][0]
            self.assertEqual(migrated["name"], "tool")
            self.assertIn("appdata-migrations", migrated["manifest"])
            self.assertFalse((root / "tool").exists())
            self.assertEqual((code / "tool" / "src.txt").read_text(encoding="utf-8"), "code")
            self.assertFalse((root / "_archive").exists())

    def test_engine_failure_marks_the_job_failed(self) -> None:
        with self._tree(occupied=True) as (root, code, _data):
            with mock.patch.object(app_module, "fetch_mounts", return_value=[]):
                body = appdata_migrate(AppdataNamesPayload(names=["tool"]))
                finished = _wait_job(body["job_id"])
            self.assertEqual(finished["status"], "failed")
            self.assertIn("exists", str(finished["error"]))
            self.assertEqual(finished["result"]["migrated"], [])
            self.assertEqual(finished["result"]["errors"][0]["name"], "tool")
            self.assertIn("exists", finished["result"]["errors"][0]["error"])
            self.assertEqual((root / "tool" / "src.txt").read_text(encoding="utf-8"), "code")
            self.assertEqual((code / "tool" / "existing.txt").read_text(encoding="utf-8"), "mine")

    def test_backend_exception_is_the_job_error(self) -> None:
        def explode(**_kwargs: object) -> None:
            raise RuntimeError("disk full")

        with (
            mock.patch.object(app_module, "fetch_mounts", return_value=[]),
            mock.patch.object(app_module, "migrate_workspace", side_effect=explode),
        ):
            body = appdata_migrate(AppdataNamesPayload(names=["tool"]))
            finished = _wait_job(body["job_id"])

        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["error"], "tool: disk full")
        self.assertEqual(finished["result"]["migrated"], [])

    def test_second_job_for_the_same_name_is_rejected(self) -> None:
        entered = threading.Event()
        release = threading.Event()

        def blocked(**_kwargs: object) -> dict[str, list]:
            entered.set()
            self.assertTrue(release.wait(5))
            return {"migrated": [], "errors": []}

        self.addCleanup(release.set)
        with (
            mock.patch.object(app_module, "fetch_mounts", return_value=[]),
            mock.patch.object(app_module, "migrate_workspace", side_effect=blocked),
        ):
            first = appdata_migrate(AppdataNamesPayload(names=["tool"]))
            self.assertIn("job_id", first)
            self.assertTrue(entered.wait(2))
            with self.assertRaises(HTTPException) as caught:
                appdata_migrate(AppdataNamesPayload(names=["tool", "other"]))
            self.assertEqual(caught.exception.status_code, 409)
            self.assertIn("tool", str(caught.exception.detail))
            other = appdata_migrate(AppdataNamesPayload(names=["other"]))
            self.assertIn("job_id", other)
            release.set()
            _wait_job(first["job_id"])
            _wait_job(other["job_id"])

    def test_refetch_per_folder_and_one_failure_is_not_success(self) -> None:
        calls = {"n": 0}

        def fake_mounts(_settings: object) -> list[ContainerMount]:
            calls["n"] += 1
            if calls["n"] >= 2:
                return [ContainerMount("plex", "running", "/mnt/cache/appdata/second")]
            return []

        with self._tree(extra=["second"]) as (root, code, _data):
            with mock.patch.object(app_module, "fetch_mounts", side_effect=fake_mounts):
                body = appdata_migrate(AppdataNamesPayload(names=["tool", "second"]))
                finished = _wait_job(body["job_id"])
            self.assertGreaterEqual(calls["n"], 2)
            self.assertEqual(finished["status"], "failed")
            self.assertIn("in use", str(finished["error"]))
            self.assertEqual([item["name"] for item in finished["result"]["migrated"]], ["tool"])
            self.assertEqual(finished["result"]["errors"][0]["name"], "second")
            self.assertFalse((root / "tool").exists())
            self.assertTrue((code / "tool" / "src.txt").is_file())
            self.assertTrue((root / "second" / "src.txt").is_file())
            self.assertFalse((code / "second").exists())

    def test_missing_job_is_404(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            appdata_migrate_status("missing")
        self.assertEqual(caught.exception.status_code, 404)

    def test_ui_polls_migrate_and_resets_in_finally(self) -> None:
        source = (_ROOT / "reclaimspace" / "web" / "static" / "appdata.js").read_text(
            encoding="utf-8"
        )
        start = source.index("async function migrateSelected")
        end = source.index("async function quarantineSelected")
        body = source[start:end]
        self.assertIn("pollMigrate", body)
        self.assertIn("finally", body)
        self.assertIn("/api/appdata/migrate/", source)
        self.assertIn("async function pollMigrate", source)

    def _tree(self, occupied: bool = False, extra: list[str] | None = None):
        return _Tree(occupied=occupied, extra=extra or [])


class _Tree:
    def __init__(self, occupied: bool, extra: list[str]) -> None:
        self._occupied = occupied
        self._extra = extra
        self._tmp: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> tuple[Path, Path, Path]:
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        root = tmp / "appdata"
        code = tmp / "code"
        data = tmp / "data"
        data.mkdir()
        self._make_project(root / "tool")
        for name in self._extra:
            self._make_project(root / name)
        if self._occupied:
            occupied = code / "tool"
            occupied.mkdir(parents=True)
            (occupied / "existing.txt").write_text("mine", encoding="utf-8")
        settings = {
            "appdata_root": str(root),
            "code_root": str(code),
            "appdata_host_prefixes": "/mnt/user/appdata;/mnt/cache/appdata",
            "unraid_api_url": "",
            "unraid_api_key": "",
            "docker_socket": "",
            "schedule_dry_run_enabled": False,
        }
        (data / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        app_module.DATA_DIR = data
        return root, code, data

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()

    def _make_project(self, project: Path) -> None:
        project.mkdir(parents=True)
        (project / ".git").mkdir()
        (project / "src.txt").write_text("code", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
