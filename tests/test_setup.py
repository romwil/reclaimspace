import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from reclaimspace.config_store import Settings, load_merged_settings, save_settings
from reclaimspace.web.app import _maybe_promote_legacy_onboarding
from reclaimspace.web.setup import (
    build_setup_status,
    default_path_mappings,
    merge_secret_fields,
    validate_paths,
)


class SetupTests(unittest.TestCase):
    def test_default_path_mappings(self) -> None:
        movies, tv = default_path_mappings("/media/movies", "/media/tv")
        self.assertIn("/media/movies", movies)
        self.assertIn("/media/tv", tv)

    def test_merge_secret_fields_keeps_existing(self) -> None:
        existing = Settings(plex_token="secret", radarr_api_key="r", sonarr_api_key="s")
        merged = merge_secret_fields({"plex_token": "", "radarr_api_key": ""}, existing)
        self.assertEqual(merged["plex_token"], "secret")
        self.assertEqual(merged["radarr_api_key"], "r")

    def test_build_setup_status_not_ready_without_sections(self) -> None:
        settings = Settings(
            plex_url="http://plex",
            plex_token="t",
            radarr_url="http://radarr",
            radarr_api_key="k",
            sonarr_url="http://sonarr",
            sonarr_api_key="k2",
            movies_root="/tmp",
            tv_root="/tmp",
            quarantine_root="/tmp",
        )
        with patch("reclaimspace.web.setup.validate_paths") as mock_paths:
            mock_paths.return_value = {
                "ok": True,
                "paths": {
                    "movies_root": {"ok": True},
                    "tv_root": {"ok": True},
                    "quarantine_root": {"ok": True},
                },
            }
            status = build_setup_status(settings)
        self.assertFalse(status["ready_to_scan_movies"])
        self.assertFalse(status["onboarding_complete"])

    def test_legacy_promotion_skipped_when_wizard_pending(self) -> None:
        settings = Settings(
            plex_url="http://plex",
            plex_token="t",
            radarr_url="http://radarr",
            radarr_api_key="k",
            movies_root="/media/movies",
            onboarding_complete=False,
            setup_wizard_pending=True,
        )
        promoted = _maybe_promote_legacy_onboarding(settings)
        self.assertFalse(promoted.onboarding_complete)

    def test_legacy_promotion_for_unmarked_install(self) -> None:
        settings = Settings(
            plex_url="http://plex",
            plex_token="t",
            radarr_url="http://radarr",
            radarr_api_key="k",
            movies_root="/media/movies",
            onboarding_complete=False,
            setup_wizard_pending=False,
        )
        promoted = _maybe_promote_legacy_onboarding(settings)
        self.assertTrue(promoted.onboarding_complete)

    def test_load_merged_settings_keeps_file_only_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings = Settings(setup_wizard_pending=True, onboarding_complete=False)
            save_settings(data_dir, settings)
            with patch.dict(os.environ, {}, clear=True):
                loaded = load_merged_settings(data_dir)
            self.assertTrue(loaded.setup_wizard_pending)
            self.assertFalse(loaded.onboarding_complete)


class RestoreTests(unittest.TestCase):
    def test_restore_dry_run(self) -> None:
        from reclaimspace.restore import restore_from_manifest
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            quarantine = Path(tmp) / "q"
            original = Path(tmp) / "movies" / "film.mkv"
            original.parent.mkdir(parents=True)
            original.write_bytes(b"x")
            dest = quarantine / "film.mkv"
            quarantine.mkdir()
            original.rename(dest)
            manifest = quarantine / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "run_id": "test",
                        "moves": [
                            {
                                "source": str(original),
                                "destination": str(dest),
                                "relative_path": "film.mkv",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = restore_from_manifest(manifest, dry_run=True)
            self.assertEqual(result["restored_count"], 1)
            self.assertTrue(dest.exists())


if __name__ == "__main__":
    unittest.main()
