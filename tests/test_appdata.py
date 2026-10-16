import json
import os
import socket
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from reclaimspace.appdata import (
    ARCHIVE_NAME,
    AppdataSourceError,
    ContainerMount,
    classify_appdata,
    delete_folders,
    detect_workspace,
    directory_size,
    fetch_mounts,
    list_archive,
    list_children,
    migrate_workspace,
    mount_folder_name,
    parse_host_prefixes,
    purge_archive,
    quarantine_folders,
    remove_empty_top_level,
    restore_archive,
)

PREFIXES = ["/mnt/user/appdata", "/mnt/cache/appdata"]


class Settings:
    def __init__(self, **kwargs: object) -> None:
        self.appdata_root = ""
        self.appdata_host_prefixes = "/mnt/user/appdata;/mnt/cache/appdata"
        self.code_root = ""
        self.unraid_api_url = ""
        self.unraid_api_key = ""
        self.docker_socket = ""
        for key, value in kwargs.items():
            setattr(self, key, value)


def _mount(container: str, source: str, state: str = "running") -> ContainerMount:
    return ContainerMount(container=container, state=state, source=source)


class _Body:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_Body":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


class HostPrefixTests(unittest.TestCase):
    def test_parse_splits_semicolon_separated_prefixes(self) -> None:
        settings = Settings(appdata_host_prefixes=" /mnt/user/appdata/ ; ; /mnt/cache/appdata ")

        self.assertEqual(
            parse_host_prefixes(settings),
            ["/mnt/user/appdata", "/mnt/cache/appdata"],
        )

    def test_folder_name_matches_user_and_cache_prefixes(self) -> None:
        self.assertEqual(
            mount_folder_name("/mnt/user/appdata/plex/Library", PREFIXES),
            "plex",
        )
        self.assertEqual(
            mount_folder_name("/mnt/cache/appdata/plex/", PREFIXES),
            "plex",
        )

    def test_exact_prefix_is_the_whole_share(self) -> None:
        self.assertEqual(mount_folder_name("/mnt/user/appdata", PREFIXES), "")
        self.assertEqual(mount_folder_name("/mnt/cache/appdata/", PREFIXES), "")

    def test_unrelated_or_lookalike_prefix_does_not_match(self) -> None:
        self.assertIsNone(mount_folder_name("/mnt/user/appdata-backup/plex", PREFIXES))
        self.assertIsNone(mount_folder_name("/mnt/user/data/plex", PREFIXES))


class WorkspaceDetectionTests(unittest.TestCase):
    def test_git_directory_alone_is_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "proj"
            (folder / ".git").mkdir(parents=True)

            detection = detect_workspace(folder)

        self.assertTrue(detection.is_code)
        self.assertEqual(detection.evidence, [".git"])

    def test_git_file_alone_is_not_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "proj"
            folder.mkdir()
            (folder / ".git").write_text("gitdir: ../other\n", encoding="utf-8")

            detection = detect_workspace(folder)

        self.assertFalse(detection.is_code)

    def test_two_distinct_markers_are_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "proj"
            folder.mkdir()
            (folder / "package.json").write_text("{}", encoding="utf-8")
            (folder / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

            detection = detect_workspace(folder)

        self.assertTrue(detection.is_code)
        self.assertEqual(detection.evidence, ["package.json", "pyproject.toml"])

    def test_one_marker_is_not_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "proj"
            folder.mkdir()
            (folder / "Cargo.toml").write_text("[package]\n", encoding="utf-8")

            detection = detect_workspace(folder)

        self.assertFalse(detection.is_code)
        self.assertEqual(detection.evidence, ["Cargo.toml"])

    def test_two_solutions_are_still_one_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "proj"
            folder.mkdir()
            (folder / "A.sln").write_text("", encoding="utf-8")
            (folder / "B.sln").write_text("", encoding="utf-8")

            detection = detect_workspace(folder)

        self.assertFalse(detection.is_code)
        self.assertEqual(detection.evidence, ["A.sln", "B.sln"])

    def test_markers_in_a_child_directory_do_not_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "proj"
            nested = folder / "src"
            nested.mkdir(parents=True)
            (nested / "package.json").write_text("{}", encoding="utf-8")
            (nested / "go.mod").write_text("module example\n", encoding="utf-8")
            (folder / ".git").mkdir()

            parent = detect_workspace(folder)
            child = detect_workspace(nested)

        self.assertTrue(parent.is_code)
        self.assertEqual(parent.evidence, [".git"])
        self.assertTrue(child.is_code)
        self.assertEqual(child.evidence, ["package.json", "go.mod"])


class ClassifyTests(unittest.TestCase):
    def test_exact_prefix_mount_leaves_unnamed_folders_unused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plex").mkdir()
            (root / "sonarr").mkdir()
            (root / "unused").mkdir()
            (root / ARCHIVE_NAME).mkdir()
            (root / "notes.txt").write_text("ignore", encoding="utf-8")
            mounts = [
                _mount("reclaimspace", "/mnt/cache/appdata"),
                _mount("proxy", "/mnt/user/appdata/"),
                _mount("plex", "/mnt/cache/appdata/plex"),
                _mount("sonarr", "/mnt/user/appdata/sonarr/config", state="exited"),
            ]

            report = classify_appdata(root, PREFIXES, mounts)

        self.assertEqual([row["name"] for row in report["candidates"]], ["unused"])
        self.assertEqual(
            report["in_use"],
            [
                {"name": "plex", "containers": ["plex"]},
                {"name": "sonarr", "containers": ["sonarr"]},
            ],
        )
        self.assertNotIn(ARCHIVE_NAME, [row["name"] for row in report["candidates"]])
        self.assertNotIn(ARCHIVE_NAME, [row["name"] for row in report["in_use"]])

    def test_candidates_are_sized_descending_and_archive_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            small = root / "small"
            large = root / "large"
            small.mkdir()
            large.mkdir()
            (small / "a.txt").write_text("hi", encoding="utf-8")
            (large / "b.txt").write_text("hello there", encoding="utf-8")
            archive = root / ARCHIVE_NAME
            archive.mkdir()
            (archive / "old").mkdir()
            mounts = [_mount("sonarr", "/mnt/cache/appdata/sonarr")]
            (root / "sonarr").mkdir()

            report = classify_appdata(root, PREFIXES, mounts)

        self.assertEqual([row["name"] for row in report["candidates"]], ["large", "small"])
        self.assertGreater(
            report["candidates"][0]["size_bytes"],
            report["candidates"][1]["size_bytes"],
        )
        self.assertEqual(report["in_use"], [{"name": "sonarr", "containers": ["sonarr"]}])
        self.assertNotIn(ARCHIVE_NAME, [row["name"] for row in report["candidates"]])
        self.assertNotIn(ARCHIVE_NAME, [row["name"] for row in report["in_use"]])

    def test_missing_prefixes_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plex").mkdir()
            with self.assertRaises(AppdataSourceError):
                classify_appdata(root, [], [_mount("plex", "/mnt/user/appdata/plex")])


class FetchMountsTests(unittest.TestCase):
    def test_graphql_posts_api_key_and_keeps_stopped_bind_mounts(self) -> None:
        body = {
            "data": {
                "docker": {
                    "containers": [
                        {
                            "names": ["/plex"],
                            "state": "RUNNING",
                            "mounts": [
                                {
                                    "Type": "bind",
                                    "Source": "/mnt/user/appdata/plex",
                                    "Destination": "/config",
                                },
                                {
                                    "Type": "volume",
                                    "Name": "cache",
                                    "Source": "/var/lib/docker/volumes/cache/_data",
                                },
                            ],
                        },
                        {
                            "names": ["/old"],
                            "state": "EXITED",
                            "mounts": [
                                {"type": "bind", "source": "/mnt/cache/appdata/old"}
                            ],
                        },
                    ]
                }
            }
        }
        captured: dict[str, object] = {}

        def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _Body:
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["headers"] = {key.lower(): value for key, value in request.header_items()}
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return _Body(json.dumps(body).encode("utf-8"))

        settings = Settings(
            unraid_api_url="http://10.10.1.202/graphql",
            unraid_api_key="secret-key",
            docker_socket="/tmp/does-not-exist-reclaimspace.sock",
        )
        with mock.patch("reclaimspace.appdata.urllib.request.urlopen", fake_urlopen):
            mounts = fetch_mounts(settings)

        self.assertEqual(captured["url"], "http://10.10.1.202/graphql")
        self.assertEqual(captured["method"], "POST")
        headers = captured["headers"]
        assert isinstance(headers, dict)
        self.assertEqual(headers.get("x-api-key"), "secret-key")
        self.assertEqual(headers.get("content-type"), "application/json")
        posted = captured["body"]
        assert isinstance(posted, dict)
        query = str(posted["query"])
        self.assertIn("docker", query)
        self.assertIn("containers", query)
        self.assertIn("mounts", query)
        self.assertEqual(
            mounts,
            [
                ContainerMount("plex", "RUNNING", "/mnt/user/appdata/plex"),
                ContainerMount("old", "EXITED", "/mnt/cache/appdata/old"),
            ],
        )

    def test_graphql_errors_do_not_fall_through_to_the_socket(self) -> None:
        def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _Body:
            raise urllib.error.URLError("connection refused")

        socket_path = "/tmp/reclaimspace-present.sock"
        Path(socket_path).touch()
        self.addCleanup(Path(socket_path).unlink, missing_ok=True)
        settings = Settings(
            unraid_api_url="http://10.10.1.202/graphql",
            unraid_api_key="secret-key",
            docker_socket=socket_path,
        )
        with mock.patch("reclaimspace.appdata.urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(AppdataSourceError) as raised:
                fetch_mounts(settings)

        self.assertIn("Unraid", str(raised.exception))

    def test_graphql_error_payload_raises(self) -> None:
        def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _Body:
            return _Body(json.dumps({"errors": [{"message": "nope"}]}).encode("utf-8"))

        settings = Settings(unraid_api_url="http://tower/graphql", unraid_api_key="k")
        with mock.patch("reclaimspace.appdata.urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(AppdataSourceError):
                fetch_mounts(settings)

    def test_missing_api_and_socket_raises(self) -> None:
        with self.assertRaises(AppdataSourceError):
            fetch_mounts(Settings())

    def test_configured_socket_that_does_not_exist_raises(self) -> None:
        settings = Settings(docker_socket="/tmp/reclaimspace-missing-docker.sock")
        with self.assertRaises(AppdataSourceError):
            fetch_mounts(settings)

    def test_docker_socket_lists_running_and_stopped_bind_mounts(self) -> None:
        payload = [
            {
                "Names": ["/plex"],
                "State": "running",
                "Mounts": [
                    {"Type": "bind", "Source": "/mnt/cache/appdata/plex"},
                    {"Type": "volume", "Source": "/var/lib/docker/volumes/x/_data"},
                ],
            },
            {
                "Names": ["/paused"],
                "State": "exited",
                "Mounts": [{"Type": "bind", "Source": "/mnt/user/appdata/paused"}],
            },
        ]
        sock_path = f"/tmp/rs-ad-{os.getpid()}.sock"
        self.addCleanup(lambda: os.path.exists(sock_path) and os.remove(sock_path))
        ready = threading.Event()
        seen: dict[str, str] = {}

        def serve() -> None:
            if os.path.exists(sock_path):
                os.remove(sock_path)
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(sock_path)
            server.listen(1)
            server.settimeout(5)
            ready.set()
            try:
                connection, _addr = server.accept()
            except socket.timeout:
                server.close()
                return
            with connection:
                data = b""
                while b"\r\n\r\n" not in data:
                    chunk = connection.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                seen["request"] = data.decode("utf-8", errors="replace")
                raw = json.dumps(payload).encode("utf-8")
                head = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: " + str(len(raw)).encode("ascii") + b"\r\n"
                    b"Connection: close\r\n\r\n"
                )
                connection.sendall(head + raw)
            server.close()

        thread = threading.Thread(target=serve)
        thread.start()
        self.assertTrue(ready.wait(5))
        try:
            mounts = fetch_mounts(Settings(docker_socket=sock_path))
        finally:
            thread.join(5)

        self.assertIn("GET /containers/json?all=1", seen["request"])
        self.assertEqual(
            mounts,
            [
                ContainerMount("plex", "running", "/mnt/cache/appdata/plex"),
                ContainerMount("paused", "exited", "/mnt/user/appdata/paused"),
            ],
        )


class FilesystemActionTests(unittest.TestCase):
    def test_directory_size_sums_nested_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "top.txt").write_text("ab", encoding="utf-8")
            nested = root / "sub"
            nested.mkdir()
            (nested / "deep.txt").write_text("cdef", encoding="utf-8")
            target = root / "target.txt"
            target.write_text("zzzz", encoding="utf-8")
            (root / "link.txt").symlink_to(target)

            # The symlink is not followed, so target.txt is counted once.
            self.assertEqual(directory_size(root), len("ab") + len("cdef") + len("zzzz"))

    def test_list_children_is_one_level_and_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "appdata"
            root.mkdir()
            folder = root / "proj"
            folder.mkdir()
            (folder / "file.txt").write_text("abc", encoding="utf-8")
            nested = folder / "nested"
            nested.mkdir()
            (nested / "big.txt").write_text("0123456789", encoding="utf-8")
            secret = Path(tmp) / "secret.txt"
            secret.write_text("nope", encoding="utf-8")

            rows = list_children(root, "proj")
            with self.assertRaises(ValueError):
                list_children(root, "../secret.txt")
            self.assertTrue(secret.is_file())

        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["file.txt"]["size_bytes"], 3)
        self.assertFalse(by_name["file.txt"]["is_dir"])
        self.assertEqual(by_name["nested"]["size_bytes"], 0)
        self.assertTrue(by_name["nested"]["is_dir"])

    def test_quarantine_writes_manifest_and_suffixes_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "proj"
            source.mkdir()
            (source / "file.txt").write_text("data", encoding="utf-8")
            (root / ARCHIVE_NAME / "proj").mkdir(parents=True)

            moved = quarantine_folders(root, ["proj"], [], PREFIXES)

            self.assertFalse(source.exists())
            self.assertEqual(len(moved), 1)
            destination = Path(moved[0]["destination"])
            self.assertTrue(destination.is_dir())
            self.assertNotEqual(destination.name, "proj")
            self.assertTrue(
                destination.resolve().is_relative_to((root / ARCHIVE_NAME).resolve())
            )
            manifest = json.loads(Path(moved[0]["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["original_name"], "proj")
            self.assertEqual(manifest["destination"], str(destination))
            listed = list_archive(root)
            match = next(row for row in listed if row["name"] == destination.name)
            self.assertEqual(match["original_name"], "proj")
            self.assertEqual(match["manifest_path"], moved[0]["manifest"])

    def test_in_use_between_classify_and_quarantine_delete_migrate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "appdata"
            code = Path(tmp) / "code"
            data = Path(tmp) / "data"
            project = root / "proj"
            project.mkdir(parents=True)
            (project / ".git").mkdir()
            (project / "file.txt").write_text("keep", encoding="utf-8")
            idle = classify_appdata(root, PREFIXES, [])
            self.assertEqual(idle["candidates"][0]["name"], "proj")
            self.assertTrue(idle["candidates"][0]["is_code"])
            live = [_mount("plex", "/mnt/user/appdata/proj", state="running")]

            with self.assertRaises(ValueError) as quarantine_error:
                quarantine_folders(root, ["proj"], live, PREFIXES)
            with self.assertRaises(ValueError) as delete_error:
                delete_folders(root, ["proj"], live, PREFIXES)
            with self.assertRaises(ValueError) as migrate_error:
                migrate_workspace(root, code, ["proj"], live, PREFIXES, data)

            self.assertIn("in use", str(quarantine_error.exception))
            self.assertIn("in use", str(delete_error.exception))
            self.assertIn("in use", str(migrate_error.exception))
            self.assertTrue((project / "file.txt").is_file())
            self.assertFalse((root / ARCHIVE_NAME).exists())
            self.assertFalse(code.exists())

    def test_actions_refuse_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "appdata"
            root.mkdir()
            secret = Path(tmp) / "secret.txt"
            secret.write_text("safe", encoding="utf-8")
            (root / "keep").mkdir()
            (root / "keep" / "file.txt").write_text("stay", encoding="utf-8")

            with self.assertRaises(ValueError):
                quarantine_folders(root, ["../secret.txt"], [], PREFIXES)
            with self.assertRaises(ValueError):
                delete_folders(root, ["../secret.txt"], [], PREFIXES)
            with self.assertRaises(ValueError):
                migrate_workspace(
                    root,
                    Path(tmp) / "code",
                    ["../secret.txt"],
                    [],
                    PREFIXES,
                    Path(tmp) / "data",
                )

            self.assertEqual(secret.read_text(encoding="utf-8"), "safe")
            self.assertTrue((root / "keep" / "file.txt").is_file())

    def test_delete_refuses_archive_and_removes_unused_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / ARCHIVE_NAME / "saved"
            archive.mkdir(parents=True)
            (archive / "file.txt").write_text("archived", encoding="utf-8")
            (root / "gone").mkdir()
            (root / "gone" / "file.txt").write_text("x", encoding="utf-8")

            with self.assertRaises(ValueError):
                delete_folders(root, [ARCHIVE_NAME], [], PREFIXES)
            deleted = delete_folders(root, ["gone"], [], PREFIXES)

            self.assertEqual(deleted, ["gone"])
            self.assertFalse((root / "gone").exists())
            self.assertTrue((archive / "file.txt").is_file())

    def test_symlink_delete_does_not_remove_the_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "appdata"
            root.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / "precious.txt").write_text("keep", encoding="utf-8")
            (root / "link").symlink_to(outside, target_is_directory=True)

            with self.assertRaises(ValueError):
                delete_folders(root, ["link"], [], PREFIXES)

            self.assertEqual((outside / "precious.txt").read_text(encoding="utf-8"), "keep")

    def test_migrate_moves_code_and_records_manifest_outside_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "appdata"
            code = Path(tmp) / "code"
            data = Path(tmp) / "data"
            project = root / "tool"
            project.mkdir(parents=True)
            (project / "package.json").write_text("{}", encoding="utf-8")
            (project / "pom.xml").write_text("<project/>", encoding="utf-8")
            (project / "src.txt").write_text("code", encoding="utf-8")

            result = migrate_workspace(root, code, ["tool"], [], PREFIXES, data)

            self.assertFalse(project.exists())
            self.assertEqual((code / "tool" / "src.txt").read_text(encoding="utf-8"), "code")
            self.assertFalse((root / ARCHIVE_NAME).exists())
            self.assertEqual(result["errors"], [])
            migrated = result["migrated"][0]
            self.assertEqual(migrated["evidence"], ["package.json", "pom.xml"])
            manifest_path = Path(str(migrated["manifest"]))
            self.assertTrue(str(manifest_path).startswith(str(data / "appdata-migrations")))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["name"], "tool")
            self.assertEqual(manifest["destination"], str((code / "tool").resolve()))

    def test_migrate_refuses_destination_collision_and_non_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "appdata"
            code = Path(tmp) / "code"
            data = Path(tmp) / "data"
            project = root / "tool"
            project.mkdir(parents=True)
            (project / ".git").mkdir()
            (project / "src.txt").write_text("code", encoding="utf-8")
            (code / "tool").mkdir(parents=True)
            (code / "tool" / "existing.txt").write_text("mine", encoding="utf-8")
            plain = root / "notes"
            plain.mkdir()
            (plain / "a.txt").write_text("nope", encoding="utf-8")

            with self.assertRaises(ValueError) as collision:
                migrate_workspace(root, code, ["tool"], [], PREFIXES, data)
            with self.assertRaises(ValueError) as not_code:
                migrate_workspace(root, code, ["notes"], [], PREFIXES, data)

            self.assertIn("exists", str(collision.exception))
            self.assertIn("not a code workspace", str(not_code.exception))
            self.assertEqual((project / "src.txt").read_text(encoding="utf-8"), "code")
            self.assertEqual((code / "tool" / "existing.txt").read_text(encoding="utf-8"), "mine")
            self.assertTrue((plain / "a.txt").is_file())

    def test_restore_reports_occupied_name_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archived = root / ARCHIVE_NAME / "proj"
            archived.mkdir(parents=True)
            (archived / "old.txt").write_text("archived", encoding="utf-8")
            manifest_path = root / ARCHIVE_NAME / "proj.manifest.json"
            manifest_path.write_text(
                json.dumps({"original_name": "proj", "destination": str(archived)}) + "\n",
                encoding="utf-8",
            )
            occupied = root / "proj"
            occupied.mkdir()
            (occupied / "new.txt").write_text("live", encoding="utf-8")

            result = restore_archive(root, ["proj"])

            self.assertEqual(result["restored"], [])
            self.assertEqual(result["errors"][0]["name"], "proj")
            self.assertIn("occupied", result["errors"][0]["error"])
            self.assertEqual((archived / "old.txt").read_text(encoding="utf-8"), "archived")
            self.assertEqual((occupied / "new.txt").read_text(encoding="utf-8"), "live")
            self.assertTrue(manifest_path.is_file())

    def test_restore_moves_back_to_the_original_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archived = root / ARCHIVE_NAME / "proj-stamped"
            archived.mkdir(parents=True)
            (archived / "old.txt").write_text("archived", encoding="utf-8")
            (root / ARCHIVE_NAME / "proj-stamped.manifest.json").write_text(
                json.dumps(
                    {
                        "original_name": "proj",
                        "destination": str(archived),
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = restore_archive(root, ["proj-stamped"])

            self.assertEqual(result["errors"], [])
            self.assertEqual((root / "proj" / "old.txt").read_text(encoding="utf-8"), "archived")
            self.assertFalse(archived.exists())
            self.assertFalse((root / ARCHIVE_NAME / "proj-stamped.manifest.json").exists())

    def test_purge_stays_inside_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "appdata"
            archive = root / ARCHIVE_NAME
            kept = archive / "keep"
            kept.mkdir(parents=True)
            (kept / "file.txt").write_text("keep", encoding="utf-8")
            (archive / "keep.manifest.json").write_text(
                json.dumps({"original_name": "keep"}) + "\n",
                encoding="utf-8",
            )
            outside = Path(tmp) / "outside.txt"
            outside.write_text("safe", encoding="utf-8")
            linked = Path(tmp) / "linked"
            linked.mkdir()
            (linked / "precious.txt").write_text("safe", encoding="utf-8")
            (archive / "link").symlink_to(linked, target_is_directory=True)

            with self.assertRaises(ValueError):
                purge_archive(root, ["../outside.txt"])
            with self.assertRaises(ValueError):
                purge_archive(root, ["link"])
            purged = purge_archive(root, ["keep"])

            self.assertEqual(purged, ["keep"])
            self.assertFalse(kept.exists())
            self.assertFalse((archive / "keep.manifest.json").exists())
            self.assertEqual(outside.read_text(encoding="utf-8"), "safe")
            self.assertEqual((linked / "precious.txt").read_text(encoding="utf-8"), "safe")
            self.assertTrue((archive / "link").is_symlink())

    def test_empty_sweep_skips_mounted_folders_and_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "empty").mkdir()
            (root / "mounted").mkdir()
            (root / "full").mkdir()
            (root / "full" / "file.txt").write_text("x", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "child").mkdir()
            archive = root / ARCHIVE_NAME
            archive.mkdir()
            mounts = [_mount("radarr", "/mnt/cache/appdata/mounted")]

            removed = remove_empty_top_level(root, mounts, PREFIXES)

            self.assertEqual(removed, ["empty"])
            self.assertFalse((root / "empty").exists())
            self.assertTrue((root / "mounted").is_dir())
            self.assertTrue((root / "full" / "file.txt").is_file())
            self.assertTrue((nested / "child").is_dir())
            self.assertTrue(archive.is_dir())


if __name__ == "__main__":
    unittest.main()
