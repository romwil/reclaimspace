import unittest

import reclaimspace
import reclaimspace.media_duplicates as media_duplicates
from reclaimspace._version import __version__ as version_module


class VersionTests(unittest.TestCase):
    def test_package_and_submodule_versions_match(self) -> None:
        self.assertEqual(reclaimspace.__version__, version_module)
        self.assertEqual(media_duplicates.__version__, version_module)

    def test_version_is_semver_like(self) -> None:
        parts = version_module.split(".")
        self.assertGreaterEqual(len(parts), 2)
        for part in parts[:3]:
            self.assertTrue(part.isdigit(), f"expected numeric segment, got {part!r}")


if __name__ == "__main__":
    unittest.main()
