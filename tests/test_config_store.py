import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_saved_unraid_url_and_key_survive_empty_env(self) -> None:
        """Scan reloads through load_merged_settings. Blank container env must not hide a save."""
        url = "http://10.10.1.202:8081/graphql"
        key = "saved-key"
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(data_dir, Settings(unraid_api_url=url, unraid_api_key=key))
            with patch.dict(os.environ, {"UNRAID_API_URL": "", "UNRAID_API_KEY": ""}, clear=False):
                loaded = load_merged_settings(data_dir)
            self.assertEqual(loaded.unraid_api_url, url)
            self.assertEqual(loaded.unraid_api_key, key)

    def test_missing_unraid_env_does_not_blank_saved_values(self) -> None:
        url = "http://10.10.1.202:8081/graphql"
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(data_dir, Settings(unraid_api_url=url, unraid_api_key="saved-key"))
            cleaned = os.environ.copy()
            cleaned.pop("UNRAID_API_URL", None)
            cleaned.pop("UNRAID_API_KEY", None)
            with patch.dict(os.environ, cleaned, clear=True):
                loaded = load_merged_settings(data_dir)
            self.assertEqual(loaded.unraid_api_url, url)
            self.assertEqual(loaded.unraid_api_key, "saved-key")

    def test_saved_unraid_url_beats_template_default_env(self) -> None:
        url = "http://10.10.1.202:8081/graphql"
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(data_dir, Settings(unraid_api_url=url, unraid_api_key="saved-key"))
            with patch.dict(
                os.environ,
                {
                    "UNRAID_API_URL": "http://10.10.1.202/graphql",
                    "UNRAID_API_KEY": "",
                },
                clear=False,
            ):
                loaded = load_merged_settings(data_dir)
            self.assertEqual(loaded.unraid_api_url, url)
            self.assertEqual(loaded.unraid_api_key, "saved-key")

    def test_unraid_env_seeds_when_settings_omit_the_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "settings.json").write_text("{}\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "UNRAID_API_URL": "http://tower:8081/graphql",
                    "UNRAID_API_KEY": "from-env",
                },
                clear=False,
            ):
                loaded = load_merged_settings(data_dir)
            self.assertEqual(loaded.unraid_api_url, "http://tower:8081/graphql")
            self.assertEqual(loaded.unraid_api_key, "from-env")

    def test_empty_env_does_not_wipe_other_saved_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(data_dir, Settings(plex_token="secret-token"))
            with patch.dict(os.environ, {"PLEX_TOKEN": ""}, clear=False):
                loaded = load_merged_settings(data_dir)
            self.assertEqual(loaded.plex_token, "secret-token")


if __name__ == "__main__":
    unittest.main()
