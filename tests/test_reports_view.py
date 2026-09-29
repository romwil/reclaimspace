import unittest

from reclaimspace.web.reports_view import report_groups_table, report_summary


class ReportSummaryTests(unittest.TestCase):
    def test_derives_protected_count_when_older_reports_omit_the_field(self):
        summary = report_summary(
            {
                "ready_count": 1,
                "candidate_count": 1,
                "needs_review_count": 1,
                "groups": [
                    {"status": "ready", "candidate_paths": ["/movies/dup.mkv"]},
                    {"status": "protected"},
                    {"status": "protected"},
                    {"status": "needs_review"},
                ],
            }
        )

        self.assertEqual(summary["protected_count"], 2)

    def test_prefers_stored_protected_count(self):
        summary = report_summary(
            {
                "protected_count": 4,
                "groups": [{"status": "protected"}],
            }
        )

        self.assertEqual(summary["protected_count"], 4)


class ReportGroupsTableTests(unittest.TestCase):
    def test_rows_include_every_plex_protected_and_candidate_path(self):
        table = report_groups_table(
            {
                "groups": [
                    {
                        "title": "Needs review",
                        "year": 2020,
                        "rating_key": "9",
                        "status": "needs_review",
                        "reason": "No match",
                        "plex_paths": ["/movies/A.mkv", "/movies/B <script>.mkv"],
                        "protected_paths": [],
                        "candidate_paths": [],
                    },
                    {
                        "title": "Ready",
                        "status": "ready",
                        "plex_paths": [
                            "/movies/keep.mkv",
                            "/movies/dup1.mkv",
                            "/movies/dup2.mkv",
                        ],
                        "protected_paths": ["/movies/keep.mkv"],
                        "candidate_paths": ["/movies/dup1.mkv", "/movies/dup2.mkv"],
                    },
                ]
            },
            limit=10,
        )

        review = table["groups"][0]
        self.assertEqual(
            review["plex_paths"],
            ["/movies/A.mkv", "/movies/B <script>.mkv"],
        )
        self.assertEqual(review["protected_paths"], [])
        self.assertEqual(review["candidate_paths"], [])
        self.assertIsNone(review["protected_path"])
        self.assertIsNone(review["sample_candidate"])

        ready = table["groups"][1]
        self.assertEqual(ready["candidate_count"], 2)
        self.assertEqual(
            ready["candidate_paths"],
            ["/movies/dup1.mkv", "/movies/dup2.mkv"],
        )
        self.assertEqual(ready["protected_paths"], ["/movies/keep.mkv"])
        self.assertEqual(ready["sample_candidate"], "/movies/dup1.mkv")
        self.assertEqual(ready["protected_path"], "/movies/keep.mkv")
