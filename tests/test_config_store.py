import json
import os
import tempfile
import unittest
from pathlib import Path

from reclaimspace.config_store import Settings, load_merged_settings, save_settings


class ConfigStoreTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings = Settings(plex_url="http://plex", plex_token="secret")
            save_settings(data_dir, settings)
            loaded = load_merged_settings(data_dir)
            self.assertEqual(loaded.plex_url, "http://plex")
            self.assertEqual(loaded.plex_token, "secret")

    def test_env_overrides_saved_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(data_dir, Settings(plex_url="http://from-file"))
            os.environ["PLEX_URL"] = "http://from-env"
            try:
                merged = load_merged_settings(data_dir)
            finally:
                os.environ.pop("PLEX_URL", None)
            self.assertEqual(merged.plex_url, "http://from-env")

    def test_settings_json_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(data_dir, Settings(movies_root="/movies"))
            payload = json.loads((data_dir / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["movies_root"], "/movies")


if __name__ == "__main__":
    unittest.main()
