import json
import tempfile
import unittest
import urllib.error
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from unittest import mock

from reclaimspace.orphans import (
    OrphanSourceError,
    classify_orphans,
    fetch_radarr_folders,
    fetch_sonarr_folders,
    list_orphan_quarantine,
    purge_orphan_folders,
    quarantine_orphan_folders,
    restore_orphan_folders,
)


class _Body:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_Body":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


def _http_error(url: str, code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "error", EmailMessage(), BytesIO(b""))


def _folder(root: Path, name: str, payload: bytes = b"x") -> Path:
    folder = root / name
    folder.mkdir()
    (folder / "title.mkv").write_bytes(payload)
    return folder


class FetchTests(unittest.TestCase):
    def test_radarr_returns_every_movie_path_including_movies_with_no_file(self) -> None:
        payload = [
            {"title": "Upcoming", "path": "/movies/Upcoming (2026)"},
            {
                "title": "Soon",
                "path": "/movies/Soon (2025)",
                "movieFile": {},
            },
            {
                "title": "Ready",
                "path": "/movies/Ready (2020)",
                "movieFile": {"path": "/movies/Ready (2020)/Ready.mkv"},
            },
            {"title": "No path"},
        ]
        with mock.patch(
            "urllib.request.urlopen", return_value=_Body(json.dumps(payload).encode())
        ) as urlopen:
            paths = fetch_radarr_folders("http://radarr.example/", "secret")

        self.assertEqual(
            paths,
            [
                "/movies/Upcoming (2026)",
                "/movies/Soon (2025)",
                "/movies/Ready (2020)",
            ],
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://radarr.example/api/v3/movie")
        self.assertEqual(request.get_header("X-api-key"), "secret")
        self.assertEqual(urlopen.call_count, 1)

    def test_sonarr_returns_every_series_path(self) -> None:
        payload = [
            {"title": "Show", "path": "/tv/Show"},
            {"title": "Other", "path": "/tv/Other Show"},
            {"title": "Missing path"},
        ]
        with mock.patch(
            "urllib.request.urlopen", return_value=_Body(json.dumps(payload).encode())
        ) as urlopen:
            paths = fetch_sonarr_folders("http://sonarr.example", "secret")

        self.assertEqual(paths, ["/tv/Show", "/tv/Other Show"])
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://sonarr.example/api/v3/series")
        self.assertEqual(urlopen.call_count, 1)

    def test_http_network_and_json_failures_raise(self) -> None:
        cases = [
            _http_error("http://radarr.example/api/v3/movie", 500),
            urllib.error.URLError("down"),
            _Body(b"not-json"),
            _Body(b"null"),
        ]
        for side_effect in cases:
            with self.subTest(side_effect=type(side_effect).__name__):
                effect = side_effect if isinstance(side_effect, Exception) else None
                returned = None if effect is not None else side_effect
                with mock.patch(
                    "urllib.request.urlopen",
                    side_effect=effect,
                    return_value=returned,
                ):
                    with self.assertRaises(OrphanSourceError):
                        fetch_radarr_folders("http://radarr.example", "secret")
                    with self.assertRaises(OrphanSourceError):
                        fetch_sonarr_folders("http://sonarr.example", "secret")


class ClassifyTests(unittest.TestCase):
    def test_presence_requires_manager_or_plex_and_sorts_orphans_by_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "library"
            library.mkdir()
            _folder(library, "Radarr Only", b"r")
            _folder(library, "Plex Only", b"p")
            _folder(library, "Both", b"b")
            _folder(library, "Big Missing", b"b" * 50)
            _folder(library, "Small Missing", b"s")
            (library / "readme.txt").write_text("loose", encoding="utf-8")

            result = classify_orphans(
                library,
                manager_paths=["/movies/Radarr Only", "/movies/Both"],
                plex_paths=[
                    "/data/media/movies/Plex Only/title.mkv",
                    "/data/media/movies/Both/title.mkv",
                ],
                path_mappings="",
            )

        self.assertEqual(
            [row["name"] for row in result["candidates"]],
            ["Big Missing", "Small Missing"],
        )
        self.assertGreater(
            result["candidates"][0]["size_bytes"],
            result["candidates"][1]["size_bytes"],
        )
        self.assertEqual(result["loose_files"], ["readme.txt"])

    def test_path_mapping_alias_protects_the_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "library"
            library.mkdir()
            _folder(library, "Aliased (1999)")
            _folder(library, "Unmapped Orphan")
            mappings = f"/volume1/movies={library}"

            protected = classify_orphans(
                library,
                manager_paths=["/volume1/movies/Aliased (1999)"],
                plex_paths=["/volume1/movies/Aliased (1999)/title.mkv"],
                path_mappings=mappings,
            )
            unmapped = classify_orphans(
                library,
                manager_paths=["/volume1/movies/Aliased (1999)"],
                plex_paths=[],
                path_mappings="",
            )

        self.assertEqual(
            [row["name"] for row in protected["candidates"]],
            ["Unmapped Orphan"],
        )
        self.assertEqual(
            [row["name"] for row in unmapped["candidates"]],
            ["Aliased (1999)", "Unmapped Orphan"],
        )

    def test_radarr_movie_without_a_file_still_protects_its_folder(self) -> None:
        payload = [
            {"title": "Upcoming", "path": "/movies/Upcoming (2026)", "movieFile": None},
            {"title": "Elsewhere", "path": "/movies/Not On Disk"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "library"
            library.mkdir()
            _folder(library, "Upcoming (2026)")
            _folder(library, "Abandoned")
            with mock.patch(
                "urllib.request.urlopen",
                return_value=_Body(json.dumps(payload).encode()),
            ):
                manager_paths = fetch_radarr_folders("http://radarr.example", "secret")
            result = classify_orphans(
                library,
                manager_paths=manager_paths,
                plex_paths=[],
                path_mappings="",
            )

        self.assertIn("/movies/Upcoming (2026)", manager_paths)
        self.assertEqual([row["name"] for row in result["candidates"]], ["Abandoned"])

    def test_tv_container_prefix_protects_a_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "tv"
            library.mkdir()
            _folder(library, "Show")
            _folder(library, "Abandoned")

            result = classify_orphans(
                library,
                manager_paths=["/tv/Show"],
                plex_paths=["/data/media/tv/Show/Season 1/S01E01.mkv"],
                path_mappings="",
            )

        self.assertEqual([row["name"] for row in result["candidates"]], ["Abandoned"])


class QuarantineRestorePurgeTests(unittest.TestCase):
    def test_loose_file_stays_and_orphan_folder_is_moved_with_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "library"
            quarantine = Path(tmp) / "quarantine"
            library.mkdir()
            loose = library / "loose.mkv"
            loose.write_bytes(b"leave-me")
            orphan = _folder(library, "Abandoned", b"movie")

            classified = classify_orphans(library, [], [], "")
            self.assertEqual(classified["loose_files"], ["loose.mkv"])
            self.assertEqual([row["name"] for row in classified["candidates"]], ["Abandoned"])

            with self.assertRaises(ValueError):
                quarantine_orphan_folders(library, quarantine, ["loose.mkv"], [], [], "")
            self.assertTrue(loose.is_file())
            self.assertFalse(quarantine.exists())

            moved = quarantine_orphan_folders(
                library, quarantine, ["Abandoned"], [], [], ""
            )

            self.assertTrue(loose.is_file())
            self.assertFalse(orphan.exists())
            self.assertEqual(len(moved), 1)
            destination = Path(moved[0]["destination"])
            manifest_path = Path(moved[0]["manifest"])
            self.assertEqual((destination / "title.mkv").read_bytes(), b"movie")
            self.assertTrue(destination.resolve().is_relative_to(quarantine.resolve()))
            self.assertNotIn("_archive", str(destination))
            self.assertTrue(destination.parent.name.startswith("orphan-"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["kind"], "orphan_folder")
            self.assertEqual(manifest["original_folder"], str(orphan))
            self.assertEqual(manifest["destination"], str(destination))
            listed = list_orphan_quarantine(quarantine)
            self.assertEqual(listed[0]["name"], destination.relative_to(quarantine).as_posix())
            self.assertEqual(listed[0]["original_name"], "Abandoned")
            self.assertEqual(listed[0]["manifest_path"], str(manifest_path))
            self.assertEqual(listed[0]["size_bytes"], len(b"movie"))

    def test_quarantine_refuses_a_folder_that_became_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "library"
            quarantine = Path(tmp) / "quarantine"
            library.mkdir()
            claimed = _folder(library, "Now Claimed", b"keep")
            still_orphan = _folder(library, "Still Orphan", b"also")

            with self.assertRaises(ValueError):
                quarantine_orphan_folders(
                    library,
                    quarantine,
                    ["Now Claimed", "Still Orphan"],
                    [str(claimed)],
                    [],
                    "",
                )

            self.assertTrue((claimed / "title.mkv").is_file())
            self.assertTrue((still_orphan / "title.mkv").is_file())
            self.assertFalse(quarantine.exists())

    def test_occupied_restore_leaves_the_folder_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "library"
            quarantine = Path(tmp) / "quarantine"
            library.mkdir()
            original = _folder(library, "Abandoned", b"quarantined")
            moved = quarantine_orphan_folders(
                library, quarantine, ["Abandoned"], [], [], ""
            )
            original.mkdir()
            (original / "new.mkv").write_bytes(b"occupied")
            listed = list_orphan_quarantine(quarantine)

            result = restore_orphan_folders(quarantine, [str(listed[0]["name"])])

            self.assertEqual(result["restored"], [])
            self.assertEqual(result["errors"][0]["name"], listed[0]["name"])
            self.assertIn("occupied", result["errors"][0]["error"].lower())
            self.assertEqual((original / "new.mkv").read_bytes(), b"occupied")
            self.assertFalse((original / "title.mkv").exists())
            destination = Path(str(moved[0]["destination"]))
            self.assertEqual((destination / "title.mkv").read_bytes(), b"quarantined")
            self.assertTrue(Path(str(moved[0]["manifest"])).is_file())

    def test_restore_moves_the_folder_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "library"
            quarantine = Path(tmp) / "quarantine"
            library.mkdir()
            original = _folder(library, "Abandoned", b"back")
            quarantine_orphan_folders(library, quarantine, ["Abandoned"], [], [], "")
            name = str(list_orphan_quarantine(quarantine)[0]["name"])

            result = restore_orphan_folders(quarantine, [name])

            self.assertEqual(result["errors"], [])
            self.assertEqual(result["restored"][0]["destination"], str(original))
            self.assertEqual((original / "title.mkv").read_bytes(), b"back")
            self.assertEqual(list_orphan_quarantine(quarantine), [])

    def test_purge_refuses_non_orphan_manifest_and_path_outside_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "library"
            quarantine = Path(tmp) / "quarantine"
            library.mkdir()
            _folder(library, "Abandoned", b"purge-me")
            moved = quarantine_orphan_folders(
                library, quarantine, ["Abandoned"], [], [], ""
            )
            orphan_name = str(list_orphan_quarantine(quarantine)[0]["name"])
            decoy = quarantine / "dup-run" / "Leftover"
            decoy.mkdir(parents=True)
            (decoy / "file.mkv").write_bytes(b"keep")
            (decoy.parent / "manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": "dup-run",
                        "moves": [
                            {
                                "source": "/library/Leftover/file.mkv",
                                "destination": str(decoy / "file.mkv"),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            outside = Path(tmp) / "outside.txt"
            outside.write_text("safe", encoding="utf-8")

            with self.assertRaises(ValueError):
                purge_orphan_folders(quarantine, ["dup-run"])
            with self.assertRaises(ValueError):
                purge_orphan_folders(quarantine, ["../outside.txt"])
            with self.assertRaises(ValueError):
                purge_orphan_folders(quarantine, [orphan_name, "../outside.txt"])

            self.assertTrue((decoy / "file.mkv").is_file())
            self.assertTrue(outside.is_file())
            self.assertTrue(Path(moved[0]["destination"]).is_dir())
            self.assertTrue(Path(moved[0]["manifest"]).is_file())

            purged = purge_orphan_folders(quarantine, [orphan_name])

            self.assertEqual(purged, [orphan_name])
            self.assertFalse(Path(moved[0]["destination"]).exists())
            self.assertFalse(Path(moved[0]["manifest"]).exists())
            self.assertTrue((decoy / "file.mkv").is_file())
            self.assertEqual(list_orphan_quarantine(quarantine), [])
