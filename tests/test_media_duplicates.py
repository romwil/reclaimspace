import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reclaimspace.media_duplicates import (
    DuplicateGroup,
    PlexPart,
    RadarrMovieFile,
    SonarrEpisodeFile,
    build_duplicate_groups,
    build_quarantine_plan,
    build_needs_review_report,
    filter_existing_quarantine_moves,
    filter_current_sonarr_episode_files,
    load_config_from_env,
    normalize_media_path,
    parse_path_mappings,
    quarantine_files,
)


MOVIES_ROOT = Path("/mnt/user/appdata/data/media/movies")


class PathNormalizationTests(unittest.TestCase):
    def test_maps_radarr_movies_path_to_host_movies_root(self):
        result = normalize_media_path(
            "/movies/The Conjuring (2013)/The Conjuring (2013) Bluray-1080p.mkv",
            MOVIES_ROOT,
        )

        self.assertEqual(
            result,
            MOVIES_ROOT
            / "The Conjuring (2013)"
            / "The Conjuring (2013) Bluray-1080p.mkv",
        )

    def test_maps_plex_data_media_path_to_host_movies_root(self):
        result = normalize_media_path(
            "/data/media/movies/The Conjuring (2013)/The Conjuring (2013).mkv",
            MOVIES_ROOT,
        )

        self.assertEqual(
            result,
            MOVIES_ROOT / "The Conjuring (2013)" / "The Conjuring (2013).mkv",
        )

    def test_explicit_path_mappings_map_container_paths_to_host_paths(self):
        mappings = parse_path_mappings(
            "/movies=/host/movies;/data/media/movies=/host/movies"
        )

        self.assertEqual(
            normalize_media_path(
                "/movies/Alien (1979)/Alien (1979).mkv",
                MOVIES_ROOT,
                mappings,
            ),
            Path("/host/movies/Alien (1979)/Alien (1979).mkv"),
        )


class CandidateSelectionTests(unittest.TestCase):
    def test_only_unknown_plex_duplicate_parts_become_quarantine_candidates(self):
        protected_file = MOVIES_ROOT / "The Conjuring (2013)" / "managed.mkv"
        leftover_file = MOVIES_ROOT / "The Conjuring (2013)" / "leftover.mkv"

        groups = build_duplicate_groups(
            plex_parts=[
                PlexPart(
                    rating_key="1",
                    title="The Conjuring",
                    year=2013,
                    file_path=str(protected_file),
                ),
                PlexPart(
                    rating_key="1",
                    title="The Conjuring",
                    year=2013,
                    file_path=str(leftover_file),
                ),
            ],
            radarr_files=[
                RadarrMovieFile(
                    movie_id=10,
                    title="The Conjuring",
                    year=2013,
                    file_path=str(protected_file),
                )
            ],
            movies_root=MOVIES_ROOT,
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].protected_paths, [protected_file])
        self.assertEqual(groups[0].candidate_paths, [leftover_file])
        self.assertEqual(groups[0].status, "ready")

    def test_sonarr_protection_uses_only_episode_file_ids_currently_linked_to_episodes(self):
        stale_file = SonarrEpisodeFile(
            series_id=1,
            series_title="The Diplomat",
            season_number=1,
            episode_file_id=390746,
            file_path="/tv/The Diplomat (2023)/Season 1/The Diplomat - S01E03.mkv",
        )
        current_file = SonarrEpisodeFile(
            series_id=1,
            series_title="The Diplomat",
            season_number=1,
            episode_file_id=390767,
            file_path="/tv/The Diplomat (2023)/Season 1/The Diplomat (2023) - S01E03.mkv",
        )

        filtered = filter_current_sonarr_episode_files(
            [stale_file, current_file],
            current_episode_file_ids={390767},
        )

        self.assertEqual(filtered, [current_file])

    def test_single_file_plex_items_are_ignored(self):
        groups = build_duplicate_groups(
            plex_parts=[
                PlexPart(
                    rating_key="1",
                    title="The Conjuring",
                    year=2013,
                    file_path=str(MOVIES_ROOT / "The Conjuring (2013)" / "managed.mkv"),
                )
            ],
            radarr_files=[],
            movies_root=MOVIES_ROOT,
        )

        self.assertEqual(groups, [])

    def test_paths_outside_movies_root_are_marked_needs_review(self):
        groups = build_duplicate_groups(
            plex_parts=[
                PlexPart(
                    rating_key="1",
                    title="Example",
                    year=2020,
                    file_path="/tmp/outside-one.mkv",
                ),
                PlexPart(
                    rating_key="1",
                    title="Example",
                    year=2020,
                    file_path="/tmp/outside-two.mkv",
                ),
            ],
            radarr_files=[],
            movies_root=MOVIES_ROOT,
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].status, "needs_review")
        self.assertEqual(groups[0].candidate_paths, [])

    def test_tv_duplicate_parts_use_sonarr_episode_files_as_protected_paths(self):
        tv_root = Path("/mnt/user/data/media/tv")
        protected_file = tv_root / "Example Show (2024)" / "Season 1" / "managed.mkv"
        leftover_file = tv_root / "Example Show (2024)" / "Season 1" / "leftover.mkv"
        mappings = parse_path_mappings(
            "/data/media/tv=/mnt/user/data/media/tv;/tv=/mnt/user/data/media/tv"
        )

        groups = build_duplicate_groups(
            plex_parts=[
                PlexPart(
                    rating_key="episode-1",
                    title="Example Show - S01E01 - Pilot",
                    year=None,
                    file_path="/data/media/tv/Example Show (2024)/Season 1/managed.mkv",
                ),
                PlexPart(
                    rating_key="episode-1",
                    title="Example Show - S01E01 - Pilot",
                    year=None,
                    file_path="/data/media/tv/Example Show (2024)/Season 1/leftover.mkv",
                ),
            ],
            radarr_files=[
                SonarrEpisodeFile(
                    series_id=1,
                    series_title="Example Show",
                    season_number=1,
                    episode_file_id=10,
                    file_path="/tv/Example Show (2024)/Season 1/managed.mkv",
                )
            ],
            movies_root=tv_root,
            path_mappings=mappings,
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].protected_paths, [protected_file])
        self.assertEqual(groups[0].candidate_paths, [leftover_file])
        self.assertEqual(groups[0].status, "ready")


class QuarantineTests(unittest.TestCase):
    def test_quarantine_preserves_relative_paths_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "movies"
            quarantine_root = Path(tmp) / "quarantine"
            duplicate = root / "The Conjuring (2013)" / "leftover.mkv"
            duplicate.parent.mkdir(parents=True)
            duplicate.write_text("duplicate", encoding="utf-8")

            group = DuplicateGroup(
                rating_key="1",
                title="The Conjuring",
                year=2013,
                plex_paths=[duplicate],
                protected_paths=[],
                candidate_paths=[duplicate],
                status="ready",
                reason="",
            )

            plan = build_quarantine_plan([group], root, quarantine_root, "run-1")
            manifest_path = quarantine_files(plan)

            expected_destination = (
                quarantine_root / "run-1" / "movies" / "The Conjuring (2013)" / "leftover.mkv"
            )
            self.assertFalse(duplicate.exists())
            self.assertTrue(expected_destination.exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["run_id"], "run-1")
            self.assertEqual(manifest["moves"][0]["source"], str(duplicate))
            self.assertEqual(manifest["moves"][0]["destination"], str(expected_destination))

    def test_tv_quarantine_uses_tv_media_subfolder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tv"
            quarantine_root = Path(tmp) / "quarantine"
            duplicate = root / "Example Show (2024)" / "Season 1" / "leftover.mkv"
            duplicate.parent.mkdir(parents=True)
            duplicate.write_text("duplicate", encoding="utf-8")

            group = DuplicateGroup(
                rating_key="episode-1",
                title="Example Show - S01E01 - Pilot",
                year=None,
                plex_paths=[duplicate],
                protected_paths=[],
                candidate_paths=[duplicate],
                status="ready",
                reason="",
            )

            plan = build_quarantine_plan(
                [group], root, quarantine_root, "run-1", media_subdir="tv"
            )
            manifest_path = quarantine_files(plan)

            expected_destination = (
                quarantine_root
                / "run-1"
                / "tv"
                / "Example Show (2024)"
                / "Season 1"
                / "leftover.mkv"
            )
            self.assertFalse(duplicate.exists())
            self.assertTrue(expected_destination.exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["moves"][0]["destination"], str(expected_destination))

    def test_filter_existing_quarantine_moves_removes_missing_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tv"
            quarantine_root = Path(tmp) / "quarantine"
            existing = root / "Show (2024)" / "Season 1" / "existing.mkv"
            missing = root / "Show (2024)" / "Season 1" / "missing.mkv"
            existing.parent.mkdir(parents=True)
            existing.write_text("duplicate", encoding="utf-8")

            group = DuplicateGroup(
                rating_key="episode-1",
                title="Show - S01E01 - Pilot",
                year=None,
                plex_paths=[existing, missing],
                protected_paths=[],
                candidate_paths=[existing, missing],
                status="ready",
                reason="",
            )
            plan = build_quarantine_plan(
                [group], root, quarantine_root, "run-1", media_subdir="tv"
            )

            filtered_plan, missing_sources = filter_existing_quarantine_moves(plan)

            self.assertEqual([move.source for move in filtered_plan.moves], [existing])
            self.assertEqual(missing_sources, [missing])


class ConfigTests(unittest.TestCase):
    def test_loads_missing_environment_values_from_dotenv_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dotenv_path = Path(tmp) / ".env"
            dotenv_path.write_text(
                "\n".join(
                    [
                        "PLEX_URL=http://plex.example",
                        "PLEX_TOKEN=plex-token",
                        "RADARR_URL=http://radarr.example",
                        "RADARR_API_KEY=radarr-key",
                        "MOVIES_ROOT=/custom/movies",
                    ]
                ),
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {}, clear=True):
                config = load_config_from_env(dotenv_path)

        self.assertEqual(config["plex_url"], "http://plex.example")
        self.assertEqual(config["radarr_api_key"], "radarr-key")
        self.assertEqual(config["movies_root"], "/custom/movies")


class NeedsReviewReportTests(unittest.TestCase):
    def test_filters_existing_report_to_needs_review_groups(self):
        source_report = {
            "groups": [
                {
                    "title": "Ready Movie",
                    "year": 2020,
                    "status": "ready",
                    "candidate_paths": ["/movies/ready/duplicate.mkv"],
                },
                {
                    "title": "Review Movie",
                    "year": 2021,
                    "status": "needs_review",
                    "reason": "No Plex duplicate matched Radarr's managed file list",
                    "plex_paths": ["/movies/review/cd1.mkv", "/movies/review/cd2.mkv"],
                    "candidate_paths": [],
                },
            ],
            "candidate_count": 1,
            "quarantined_count": 1,
        }

        review_report = build_needs_review_report(source_report)

        self.assertEqual(review_report["needs_review_count"], 1)
        self.assertEqual(review_report["source_group_count"], 2)
        self.assertEqual(review_report["groups"][0]["title"], "Review Movie")
        self.assertEqual(review_report["groups"][0]["plex_file_count"], 2)
        self.assertNotIn("candidate_count", review_report)


if __name__ == "__main__":
    unittest.main()
