#!/usr/bin/env python3
"""Find Plex media duplicates and quarantine files not managed by Arr apps."""

from __future__ import annotations

__version__ = "1.0.0"

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


DEFAULT_MOVIES_ROOT = Path("/mnt/user/appdata/data/media/movies")
DEFAULT_QUARANTINE_ROOT = Path("/mnt/user/appdata/reclaimspace/quarantine")

# Container path prefixes used when PATH_MAPPINGS / TV_PATH_MAPPINGS are incomplete.
MOVIE_PATH_PREFIXES = ("/data/media/movies", "/movies")
TV_PATH_PREFIXES = ("/data/media/tv", "/tv")


@dataclass(frozen=True)
class RadarrMovieFile:
    movie_id: int
    title: str
    year: Optional[int]
    file_path: str


@dataclass(frozen=True)
class SonarrEpisodeFile:
    series_id: int
    series_title: str
    season_number: Optional[int]
    episode_file_id: int
    file_path: str


@dataclass(frozen=True)
class PlexPart:
    rating_key: str
    title: str
    year: Optional[int]
    file_path: str


@dataclass
class DuplicateGroup:
    rating_key: str
    title: str
    year: Optional[int]
    plex_paths: List[Path]
    protected_paths: List[Path]
    candidate_paths: List[Path]
    status: str
    reason: str


@dataclass(frozen=True)
class QuarantineMove:
    source: Path
    destination: Path
    rating_key: str
    title: str
    year: Optional[int]


@dataclass(frozen=True)
class QuarantinePlan:
    run_id: str
    moves: List[QuarantineMove]
    manifest_path: Path


def normalize_media_path(
    file_path: str | Path,
    media_root: Path,
    extra_mappings: Optional[Sequence[Tuple[str, str | Path]]] = None,
    *,
    fallback_prefixes: Sequence[str] = MOVIE_PATH_PREFIXES,
) -> Path:
    """Map Plex or *arr container paths to a host path under the library root."""
    raw_path = str(file_path).strip()
    root = Path(media_root)
    mappings: List[Tuple[str, Path]] = []

    for container_prefix, host_prefix in extra_mappings or []:
        mappings.append((container_prefix.rstrip("/"), Path(host_prefix)))

    for prefix in fallback_prefixes:
        mappings.append((prefix.rstrip("/"), root))

    for container_prefix, host_prefix in sorted(
        mappings, key=lambda item: len(item[0]), reverse=True
    ):
        if raw_path == container_prefix or raw_path.startswith(container_prefix + "/"):
            relative = raw_path[len(container_prefix) :].lstrip("/")
            return _clean_path(host_prefix / relative)

    return _clean_path(Path(raw_path))


def parse_path_mappings(value: str) -> List[Tuple[str, Path]]:
    mappings: List[Tuple[str, Path]] = []
    for entry in value.split(";"):
        stripped = entry.strip()
        if not stripped:
            continue
        if "=" not in stripped:
            raise ValueError(f"Invalid path mapping entry: {stripped}")
        container_prefix, host_prefix = stripped.split("=", 1)
        container_prefix = container_prefix.strip().rstrip("/")
        host_prefix = host_prefix.strip()
        if not container_prefix or not host_prefix:
            raise ValueError(f"Invalid path mapping entry: {stripped}")
        mappings.append((container_prefix, Path(host_prefix)))
    return mappings


def build_duplicate_groups(
    plex_parts: Iterable[PlexPart],
    managed_files: Iterable[RadarrMovieFile | SonarrEpisodeFile],
    media_root: Path,
    path_mappings: Optional[Sequence[Tuple[str, str | Path]]] = None,
    *,
    arr_app_name: str = "Radarr",
    media_root_env: str = "MOVIES_ROOT",
    fallback_prefixes: Sequence[str] = MOVIE_PATH_PREFIXES,
) -> List[DuplicateGroup]:
    normalize = lambda path: normalize_media_path(
        path, media_root, path_mappings, fallback_prefixes=fallback_prefixes
    )
    protected = {
        normalize(managed_file.file_path)
        for managed_file in managed_files
        if managed_file.file_path
    }

    parts_by_item: Dict[str, List[PlexPart]] = defaultdict(list)
    for part in plex_parts:
        parts_by_item[part.rating_key].append(part)

    groups: List[DuplicateGroup] = []
    for rating_key, item_parts in sorted(parts_by_item.items()):
        normalized_paths = [normalize(part.file_path) for part in item_parts]
        unique_paths = _unique_paths(normalized_paths)
        if len(unique_paths) <= 1:
            continue

        first_part = item_parts[0]
        outside_paths = [
            path for path in unique_paths if not _is_relative_to(path, media_root)
        ]
        protected_paths = [path for path in unique_paths if path in protected]

        if outside_paths:
            status = "needs_review"
            reason = f"Plex reported one or more files outside {media_root_env}"
            candidate_paths: List[Path] = []
        elif not protected_paths:
            status = "needs_review"
            reason = f"No Plex duplicate matched {arr_app_name}'s managed file list"
            candidate_paths = []
        else:
            candidate_paths = [path for path in unique_paths if path not in protected]
            status = "ready" if candidate_paths else "protected"
            reason = (
                ""
                if candidate_paths
                else f"All duplicate paths are managed by {arr_app_name}"
            )

        groups.append(
            DuplicateGroup(
                rating_key=rating_key,
                title=first_part.title,
                year=first_part.year,
                plex_paths=unique_paths,
                protected_paths=protected_paths,
                candidate_paths=candidate_paths,
                status=status,
                reason=reason,
            )
        )

    return groups


def filter_current_sonarr_episode_files(
    episode_files: Iterable[SonarrEpisodeFile],
    current_episode_file_ids: Iterable[int],
) -> List[SonarrEpisodeFile]:
    """Keep only Sonarr episode files still linked to an episode via episodeFileId."""
    current_ids = set(current_episode_file_ids)
    return [
        episode_file
        for episode_file in episode_files
        if episode_file.episode_file_id in current_ids
    ]


def build_quarantine_plan(
    groups: Iterable[DuplicateGroup],
    media_root: Path,
    quarantine_root: Path,
    run_id: Optional[str] = None,
    media_subdir: str = "movies",
) -> QuarantinePlan:
    run = run_id or time.strftime("%Y%m%d-%H%M%S")
    run_root = Path(quarantine_root) / run
    moves: List[QuarantineMove] = []

    for group in groups:
        if group.status != "ready":
            continue
        for candidate in group.candidate_paths:
            if not _is_relative_to(candidate, media_root):
                continue
            destination = run_root / media_subdir / candidate.relative_to(media_root)
            moves.append(
                QuarantineMove(
                    source=candidate,
                    destination=destination,
                    rating_key=group.rating_key,
                    title=group.title,
                    year=group.year,
                )
            )

    return QuarantinePlan(
        run_id=run,
        moves=moves,
        manifest_path=run_root / "manifest.json",
    )


def quarantine_files(plan: QuarantinePlan) -> Path:
    for move in plan.moves:
        if not move.source.exists():
            raise FileNotFoundError(f"Quarantine source does not exist: {move.source}")
        move.destination.parent.mkdir(parents=True, exist_ok=True)
        if move.destination.exists():
            raise FileExistsError(f"Quarantine destination exists: {move.destination}")
        shutil.move(str(move.source), str(move.destination))

    plan.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    plan.manifest_path.write_text(
        json.dumps(_manifest_payload(plan), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return plan.manifest_path


def filter_existing_quarantine_moves(
    plan: QuarantinePlan,
) -> Tuple[QuarantinePlan, List[Path]]:
    """Drop moves whose source file Plex listed but is already gone from disk."""
    existing_moves = []
    missing_sources = []
    for move in plan.moves:
        if move.source.exists():
            existing_moves.append(move)
        else:
            missing_sources.append(move.source)

    return (
        QuarantinePlan(
            run_id=plan.run_id,
            moves=existing_moves,
            manifest_path=plan.manifest_path,
        ),
        missing_sources,
    )


class RadarrClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def movie_files(self) -> List[RadarrMovieFile]:
        movies = _request_json(
            f"{self.base_url}/api/v3/movie",
            headers={"X-Api-Key": self.api_key},
            timeout=self.timeout,
        )
        files: List[RadarrMovieFile] = []
        for movie in movies:
            movie_file = movie.get("movieFile") or {}
            file_path = movie_file.get("path")
            if not file_path and movie_file.get("relativePath") and movie.get("path"):
                file_path = str(Path(movie["path"]) / movie_file["relativePath"])
            if not file_path:
                continue
            files.append(
                RadarrMovieFile(
                    movie_id=int(movie.get("id") or 0),
                    title=str(movie.get("title") or ""),
                    year=movie.get("year"),
                    file_path=str(file_path),
                )
            )
        return files


class SonarrClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def episode_files(self) -> List[SonarrEpisodeFile]:
        headers = {"X-Api-Key": self.api_key}
        series_items = _request_json(
            f"{self.base_url}/api/v3/series",
            headers=headers,
            timeout=self.timeout,
        )
        files: List[SonarrEpisodeFile] = []
        for series in series_items:
            series_id = int(series.get("id") or 0)
            if not series_id:
                continue
            episodes = _request_json(
                f"{self.base_url}/api/v3/episode?seriesId={series_id}",
                headers=headers,
                timeout=self.timeout,
            )
            current_episode_file_ids = {
                int(episode.get("episodeFileId") or 0)
                for episode in episodes
                if episode.get("episodeFileId")
            }
            episode_files = _request_json(
                f"{self.base_url}/api/v3/episodefile?seriesId={series_id}",
                headers=headers,
                timeout=self.timeout,
            )
            series_files: List[SonarrEpisodeFile] = []
            for episode_file in episode_files:
                file_path = episode_file.get("path")
                if not file_path:
                    continue
                series_files.append(
                    SonarrEpisodeFile(
                        series_id=series_id,
                        series_title=str(series.get("title") or ""),
                        season_number=episode_file.get("seasonNumber"),
                        episode_file_id=int(episode_file.get("id") or 0),
                        file_path=str(file_path),
                    )
                )
            files.extend(
                filter_current_sonarr_episode_files(
                    series_files, current_episode_file_ids
                )
            )
        return files


class PlexClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        movie_section: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.movie_section = movie_section
        self.timeout = timeout

    def movie_parts(self) -> List[PlexPart]:
        section_key = self.movie_section or self._find_movie_section_key()
        root = self._request_xml(f"/library/sections/{section_key}/all?type=1")
        parts: List[PlexPart] = []

        for video in root.findall(".//Video"):
            rating_key = str(video.attrib.get("ratingKey") or "")
            title = str(video.attrib.get("title") or "")
            year = _optional_int(video.attrib.get("year"))
            for part in video.findall(".//Part"):
                file_path = part.attrib.get("file")
                if file_path:
                    parts.append(
                        PlexPart(
                            rating_key=rating_key,
                            title=title,
                            year=year,
                            file_path=file_path,
                        )
                    )
        return parts

    def tv_episode_parts(self, section_key: str, page_size: int = 500) -> List[PlexPart]:
        parts: List[PlexPart] = []
        start = 0

        while True:
            root = self._request_xml(
                f"/library/sections/{section_key}/all"
                f"?type=4&X-Plex-Container-Start={start}"
                f"&X-Plex-Container-Size={page_size}"
            )
            videos = root.findall(".//Video")
            if not videos:
                break

            for video in videos:
                rating_key = str(video.attrib.get("ratingKey") or "")
                title = _format_plex_episode_title(video)
                for part in video.findall(".//Part"):
                    file_path = part.attrib.get("file")
                    if file_path:
                        parts.append(
                            PlexPart(
                                rating_key=rating_key,
                                title=title,
                                year=None,
                                file_path=file_path,
                            )
                        )

            start += len(videos)
            if len(videos) < page_size:
                break

        return parts

    def _find_movie_section_key(self) -> str:
        root = self._request_xml("/library/sections")
        for directory in root.findall(".//Directory"):
            if directory.attrib.get("type") == "movie":
                key = directory.attrib.get("key")
                if key:
                    return key
        raise RuntimeError("No Plex movie library section found")

    def _request_xml(self, path: str) -> ET.Element:
        separator = "&" if "?" in path else "?"
        url = f"{self.base_url}{path}{separator}X-Plex-Token={urllib.parse.quote(self.token)}"
        request = urllib.request.Request(url, headers={"Accept": "application/xml"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return ET.fromstring(response.read())


def report_groups(groups: Iterable[DuplicateGroup]) -> Dict[str, object]:
    group_payloads = []
    for group in groups:
        group_payloads.append(
            {
                "rating_key": group.rating_key,
                "title": group.title,
                "year": group.year,
                "status": group.status,
                "reason": group.reason,
                "plex_paths": [str(path) for path in group.plex_paths],
                "protected_paths": [str(path) for path in group.protected_paths],
                "candidate_paths": [str(path) for path in group.candidate_paths],
            }
        )

    return {
        "groups": group_payloads,
        "ready_count": sum(1 for group in group_payloads if group["status"] == "ready"),
        "candidate_count": sum(len(group["candidate_paths"]) for group in group_payloads),
        "needs_review_count": sum(
            1 for group in group_payloads if group["status"] == "needs_review"
        ),
    }


def build_needs_review_report(source_report: Mapping[str, object]) -> Dict[str, object]:
    source_groups = source_report.get("groups", [])
    if not isinstance(source_groups, list):
        raise ValueError("Source report must contain a list field named 'groups'")

    review_groups = []
    for group in source_groups:
        if not isinstance(group, dict) or group.get("status") != "needs_review":
            continue
        review_group = dict(group)
        plex_paths = review_group.get("plex_paths", [])
        protected_paths = review_group.get("protected_paths", [])
        candidate_paths = review_group.get("candidate_paths", [])
        review_group["plex_file_count"] = len(plex_paths) if isinstance(plex_paths, list) else 0
        review_group["protected_file_count"] = (
            len(protected_paths) if isinstance(protected_paths, list) else 0
        )
        review_group["candidate_file_count"] = (
            len(candidate_paths) if isinstance(candidate_paths, list) else 0
        )
        review_groups.append(review_group)

    reasons = Counter(
        str(group.get("reason") or "unspecified")
        for group in review_groups
        if isinstance(group, dict)
    )

    return {
        "source_group_count": len(source_groups),
        "needs_review_count": len(review_groups),
        "reason_counts": dict(sorted(reasons.items())),
        "groups": review_groups,
    }


def load_config_from_env(dotenv_path: str | Path = ".env") -> Mapping[str, str]:
    _load_dotenv(dotenv_path)
    return {
        "plex_url": _required_env("PLEX_URL"),
        "plex_token": _required_env("PLEX_TOKEN"),
        "radarr_url": _required_env("RADARR_URL"),
        "radarr_api_key": _required_env("RADARR_API_KEY"),
        "movies_root": os.environ.get("MOVIES_ROOT", str(DEFAULT_MOVIES_ROOT)),
        "quarantine_root": os.environ.get(
            "QUARANTINE_ROOT", str(DEFAULT_QUARANTINE_ROOT)
        ),
        "plex_movie_section": os.environ.get("PLEX_MOVIE_SECTION", ""),
        "path_mappings": os.environ.get("PATH_MAPPINGS", ""),
        "sonarr_url": os.environ.get("SONARR_URL", ""),
        "sonarr_api_key": os.environ.get("SONARR_API_KEY", ""),
        "tv_root": os.environ.get("TV_ROOT", ""),
        "plex_tv_section": os.environ.get("PLEX_TV_SECTION", ""),
        "tv_path_mappings": os.environ.get("TV_PATH_MAPPINGS", ""),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    effective_argv = list(argv) if argv is not None else sys.argv[1:]
    if effective_argv and effective_argv[0] == "review-report":
        return review_report_main(effective_argv[1:])
    if effective_argv and effective_argv[0] == "tv":
        return tv_main(effective_argv[1:])

    parser = argparse.ArgumentParser(
        description=(
            "Find Plex movie duplicates and quarantine files Radarr does not manage. "
            "Use the 'tv' subcommand for Sonarr-managed TV episodes."
        )
    )
    parser.add_argument(
        "--quarantine",
        action="store_true",
        help="Move ready candidates to quarantine. Omit for dry-run report only.",
    )
    parser.add_argument(
        "--report",
        default="-",
        help="Write JSON report to this path, or '-' for stdout.",
    )
    args = parser.parse_args(effective_argv)

    config = load_config_from_env()
    movies_root = Path(config["movies_root"])
    quarantine_root = Path(config["quarantine_root"])
    path_mappings = parse_path_mappings(config["path_mappings"])

    if not movies_root.exists():
        raise RuntimeError(f"MOVIES_ROOT does not exist: {movies_root}")

    radarr_files = RadarrClient(
        config["radarr_url"], config["radarr_api_key"]
    ).movie_files()
    plex_parts = PlexClient(
        config["plex_url"],
        config["plex_token"],
        movie_section=config["plex_movie_section"] or None,
    ).movie_parts()
    groups = build_duplicate_groups(plex_parts, radarr_files, movies_root, path_mappings)
    payload = report_groups(groups)
    payload["media_type"] = "movies"

    if args.quarantine:
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

    _write_report(payload, args.report)
    return 0


def review_report_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract needs-review groups from an existing duplicate report."
    )
    parser.add_argument("source_report", help="Existing dry-run or quarantine JSON report.")
    parser.add_argument(
        "--output",
        default="-",
        help="Write needs-review JSON report to this path, or '-' for stdout.",
    )
    args = parser.parse_args(argv)

    source_report = json.loads(Path(args.source_report).read_text(encoding="utf-8"))
    _write_report(build_needs_review_report(source_report), args.output)
    return 0


def tv_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run Plex TV duplicates against Sonarr-managed episode files."
    )
    parser.add_argument(
        "--report",
        default="-",
        help="Write JSON report to this path, or '-' for stdout.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=500,
        help="Plex episode page size. Lower this if Plex returns server errors.",
    )
    parser.add_argument(
        "--quarantine",
        action="store_true",
        help="Move ready candidates to quarantine. Omit for dry-run report only.",
    )
    args = parser.parse_args(argv)

    config = load_config_from_env()
    tv_root_value = config["tv_root"]
    if not tv_root_value:
        raise RuntimeError("Missing required environment variable: TV_ROOT")
    if not config["sonarr_url"]:
        raise RuntimeError("Missing required environment variable: SONARR_URL")
    if not config["sonarr_api_key"]:
        raise RuntimeError("Missing required environment variable: SONARR_API_KEY")
    if not config["plex_tv_section"]:
        raise RuntimeError("Missing required environment variable: PLEX_TV_SECTION")

    tv_root = Path(tv_root_value)
    if not tv_root.exists():
        raise RuntimeError(f"TV_ROOT does not exist: {tv_root}")

    path_mappings = parse_path_mappings(config["tv_path_mappings"])
    plex_parts = PlexClient(
        config["plex_url"], config["plex_token"]
    ).tv_episode_parts(config["plex_tv_section"], page_size=args.page_size)
    sonarr_files = SonarrClient(
        config["sonarr_url"], config["sonarr_api_key"]
    ).episode_files()
    groups = build_duplicate_groups(
        plex_parts,
        sonarr_files,
        tv_root,
        path_mappings,
        arr_app_name="Sonarr",
        media_root_env="TV_ROOT",
        fallback_prefixes=TV_PATH_PREFIXES,
    )
    payload = report_groups(groups)
    payload["media_type"] = "tv"
    payload["plex_episode_part_count"] = len(plex_parts)
    payload["sonarr_episode_file_count"] = len(sonarr_files)

    if args.quarantine:
        quarantine_root = Path(config["quarantine_root"])
        plan = build_quarantine_plan(
            groups, tv_root, quarantine_root, media_subdir="tv"
        )
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

    _write_report(payload, args.report)
    return 0


def _request_json(url: str, headers: Mapping[str, str], timeout: int) -> object:
    request = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code} from {url}") from error


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _load_dotenv(dotenv_path: str | Path) -> None:
    path = Path(dotenv_path)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_env_quotes(value.strip())


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _write_report(payload: Mapping[str, object], destination: str) -> None:
    output = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if destination == "-":
        sys.stdout.write(output)
    else:
        Path(destination).write_text(output, encoding="utf-8")


def _manifest_payload(plan: QuarantinePlan) -> Dict[str, object]:
    return {
        "run_id": plan.run_id,
        "moves": [
            {
                **asdict(move),
                "source": str(move.source),
                "destination": str(move.destination),
            }
            for move in plan.moves
        ],
    }


def _clean_path(path: Path) -> Path:
    return Path(os.path.normpath(str(path)))


def _unique_paths(paths: Iterable[Path]) -> List[Path]:
    seen = set()
    unique: List[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _optional_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _format_plex_episode_title(video: ET.Element) -> str:
    show_title = video.attrib.get("grandparentTitle") or "Unknown Show"
    season_number = _optional_int(video.attrib.get("parentIndex"))
    episode_number = _optional_int(video.attrib.get("index"))
    episode_title = video.attrib.get("title") or "Unknown Episode"
    if season_number is None or episode_number is None:
        return f"{show_title} - {episode_title}"
    return f"{show_title} - S{season_number:02d}E{episode_number:02d} - {episode_title}"


if __name__ == "__main__":
    raise SystemExit(main())
