"""Persistent settings for Reclaimspace web and CLI."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


ENV_TO_FIELD = {
    "PLEX_URL": "plex_url",
    "PLEX_TOKEN": "plex_token",
    "RADARR_URL": "radarr_url",
    "RADARR_API_KEY": "radarr_api_key",
    "SONARR_URL": "sonarr_url",
    "SONARR_API_KEY": "sonarr_api_key",
    "MOVIES_ROOT": "movies_root",
    "TV_ROOT": "tv_root",
    "QUARANTINE_ROOT": "quarantine_root",
    "PATH_MAPPINGS": "path_mappings",
    "TV_PATH_MAPPINGS": "tv_path_mappings",
    "PLEX_MOVIE_SECTION": "plex_movie_section",
    "PLEX_TV_SECTION": "plex_tv_section",
}

FIELD_TO_ENV = {value: key for key, value in ENV_TO_FIELD.items()}


@dataclass
class Settings:
    plex_url: str = ""
    plex_token: str = ""
    radarr_url: str = ""
    radarr_api_key: str = ""
    sonarr_url: str = ""
    sonarr_api_key: str = ""
    movies_root: str = "/mnt/user/data/media/movies"
    tv_root: str = "/mnt/user/data/media/tv"
    quarantine_root: str = "/mnt/user/data/quarantine"
    path_mappings: str = (
        "/data/media/movies=/mnt/user/data/media/movies;"
        "/movies=/mnt/user/data/media/movies"
    )
    tv_path_mappings: str = (
        "/data/media/tv=/mnt/user/data/media/tv;/tv=/mnt/user/data/media/tv"
    )
    plex_movie_section: str = ""
    plex_tv_section: str = ""
    tv_page_size: int = 500

    def to_env(self) -> Dict[str, str]:
        payload = {
            "PLEX_URL": self.plex_url,
            "PLEX_TOKEN": self.plex_token,
            "RADARR_URL": self.radarr_url,
            "RADARR_API_KEY": self.radarr_api_key,
            "SONARR_URL": self.sonarr_url,
            "SONARR_API_KEY": self.sonarr_api_key,
            "MOVIES_ROOT": self.movies_root,
            "TV_ROOT": self.tv_root,
            "QUARANTINE_ROOT": self.quarantine_root,
            "PATH_MAPPINGS": self.path_mappings,
            "TV_PATH_MAPPINGS": self.tv_path_mappings,
            "PLEX_MOVIE_SECTION": self.plex_movie_section,
            "PLEX_TV_SECTION": self.plex_tv_section,
        }
        return {key: value for key, value in payload.items() if value is not None}

    def apply_to_environ(self) -> None:
        for key, value in self.to_env().items():
            os.environ[key] = value

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Settings":
        known = {field.name for field in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {key: data[key] for key in known if key in data}
        return cls(**filtered)

    @classmethod
    def from_env(cls) -> "Settings":
        values: Dict[str, Any] = {}
        for env_name, field_name in ENV_TO_FIELD.items():
            if env_name in os.environ:
                values[field_name] = os.environ[env_name]
        if "TV_PAGE_SIZE" in os.environ:
            values["tv_page_size"] = int(os.environ["TV_PAGE_SIZE"])
        return cls.from_mapping(values)

    @classmethod
    def load(cls, path: Path) -> "Settings":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_mapping(data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_merged_settings(data_dir: Path) -> Settings:
    """Load settings file, then apply non-empty environment overrides."""
    settings_path = data_dir / "settings.json"
    settings = Settings.load(settings_path)
    env_settings = Settings.from_env()
    merged = asdict(settings)
    for key, value in asdict(env_settings).items():
        if value in ("", None):
            continue
        merged[key] = value
    return Settings.from_mapping(merged)


def save_settings(data_dir: Path, settings: Settings) -> Path:
    path = data_dir / "settings.json"
    settings.save(path)
    return path
