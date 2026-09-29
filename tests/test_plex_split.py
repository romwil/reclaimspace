import unittest
from unittest import mock

from fastapi import HTTPException

from reclaimspace.config_store import Settings
from reclaimspace.web.app import SplitRequest, plex_split


class PlexSplitRouteTests(unittest.TestCase):
    def test_split_route_calls_plex_and_asks_for_a_new_dry_run(self):
        settings = Settings(
            plex_url="http://plex.example",
            plex_token="secret-token",
            onboarding_complete=True,
        )
        with (
            mock.patch("reclaimspace.web.app.load_merged_settings", return_value=settings),
            mock.patch("reclaimspace.web.app.PlexClient") as plex,
        ):
            result = plex_split(SplitRequest(rating_key=" 42 "))

        plex.assert_called_once_with("http://plex.example", "secret-token")
        plex.return_value.split_item.assert_called_once_with("42")
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["rating_key"], "42")
        self.assertEqual(
            result["message"],
            "Split in Plex. Run a new dry run to refresh this report.",
        )
        self.assertNotIn("secret-token", str(result))

    def test_split_route_rejects_a_non_numeric_key_without_calling_plex(self):
        settings = Settings(plex_url="http://plex.example", plex_token="secret-token")
        with (
            mock.patch("reclaimspace.web.app.load_merged_settings", return_value=settings),
            mock.patch("reclaimspace.web.app.PlexClient") as plex,
        ):
            with self.assertRaises(HTTPException) as caught:
                plex_split(SplitRequest(rating_key="../42"))

        self.assertEqual(caught.exception.status_code, 400)
        plex.assert_not_called()

    def test_split_route_hides_the_token_when_plex_fails(self):
        settings = Settings(plex_url="http://plex.example", plex_token="secret-token")
        with (
            mock.patch("reclaimspace.web.app.load_merged_settings", return_value=settings),
            mock.patch("reclaimspace.web.app.PlexClient") as plex,
        ):
            plex.return_value.split_item.side_effect = RuntimeError(
                "Plex error at http://plex.example?X-Plex-Token=secret-token"
            )
            with self.assertRaises(HTTPException) as caught:
                plex_split(SplitRequest(rating_key="42"))

        self.assertEqual(caught.exception.status_code, 502)
        self.assertNotIn("secret-token", caught.exception.detail)
        self.assertIn("[redacted]", caught.exception.detail)
