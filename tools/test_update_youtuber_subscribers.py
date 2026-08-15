import csv
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_youtuber_subscribers as subscribers


class ApplySnapshotTest(unittest.TestCase):
    def test_date_is_refreshed_with_value_and_missing_rows_are_na(self):
        columns = ["id", "original", "subscribers", "subscribers_as_of"]
        rows = [
            {"id": "1", "original": "A", "subscribers": "100",
             "subscribers_as_of": "2026-07-30", "untouched": "x"},
            {"id": "1", "original": "A alias", "subscribers": "100",
             "subscribers_as_of": "2026-07-30", "untouched": "y"},
            {"id": "2", "original": "B", "subscribers": "200",
             "subscribers_as_of": "2026-07-30"},
            {"id": "3", "original": "C", "subscribers": "NA",
             "subscribers_as_of": "NA"},
        ]

        filled, updated, lost = subscribers.apply_snapshot(
            rows, columns,
            {"1": (150, "A Channel"), "3": (300, "C Channel")},
            "2026-08-15")

        self.assertEqual(
            [(row["channel"], row["subscribers"], row["subscribers_as_of"])
             for row in rows],
            [("A Channel", "150", "2026-08-15"),
             ("A Channel", "150", "2026-08-15"),
             ("NA", "NA", "NA"),
             ("C Channel", "300", "2026-08-15")],
        )
        self.assertEqual([rows[0]["untouched"], rows[1]["untouched"]], ["x", "y"])
        self.assertEqual(filled, {"3"})
        self.assertEqual(updated, {"1"})
        self.assertEqual(lost, {"2"})

    def test_columns_are_added_once_and_atomic_writer_preserves_format(self):
        columns = ["id", "original"]
        rows = [{"id": "1", "original": "A"}]
        subscribers.apply_snapshot(
            rows, columns, {"1": (42, "First")}, "2026-08-15")
        subscribers.apply_snapshot(
            rows, columns, {"1": (43, "Second")}, "2026-08-16")

        self.assertEqual(
            columns,
            ["id", "original", "channel", "subscribers", "subscribers_as_of"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "youtuber.csv"
            path.write_text("old", encoding="utf-8")
            subscribers.write_snapshot_atomic(path, columns, rows)
            self.assertFalse(path.read_bytes().endswith(b"\n"))
            with path.open(encoding="utf-8") as handle:
                rendered = list(csv.DictReader(handle))
        self.assertEqual(rendered[0]["subscribers"], "43")
        self.assertEqual(rendered[0]["subscribers_as_of"], "2026-08-16")
        self.assertEqual(rendered[0]["channel"], "Second")

    @mock.patch.object(subscribers, "_get")
    def test_fetch_records_batches_and_sanitizes_official_titles(self, get):
        ids = [f"UC{i:022d}" for i in range(51)]
        get.side_effect = [
            {"items": [
                {"id": ids[0], "snippet": {"title": ' Main,\n"Channel" '},
                 "statistics": {"subscriberCount": "123"}},
                {"id": ids[1], "snippet": {"title": "Hidden"},
                 "statistics": {"hiddenSubscriberCount": True}},
                {"id": ids[2], "snippet": {},
                 "statistics": {"subscriberCount": "5"}},
                {"id": ids[3], "snippet": {"title": "Bad count"},
                 "statistics": {"subscriberCount": "unknown"}},
            ]},
            {"items": []},
        ]

        records, hidden = subscribers.fetch_channel_records(ids, "secret")

        self.assertEqual(len(get.call_args_list), 2)
        queries = [urllib.parse.parse_qs(
            urllib.parse.urlsplit(call.args[0]).query)
            for call in get.call_args_list]
        self.assertEqual([q["part"] for q in queries],
                         [["snippet,statistics"], ["snippet,statistics"]])
        self.assertEqual([len(q["id"][0].split(",")) for q in queries], [50, 1])
        self.assertEqual(records, {ids[0]: (123, "Main Channel")})
        self.assertEqual(hidden, 1)

    def test_main_channel_keeps_count_and_title_from_same_id(self):
        qid_of = {"person": "Q1", "missing": "Q2", "tie": "Q3"}
        channels = {
            "Q1": ["UCb", "UCa"],
            "Q2": ["UCmissing"],
            "Q3": ["UCz", "UCa"],
        }
        records = {
            "UCa": (100, "A title"),
            "UCb": (200, "B title"),
            "UCz": (100, "Z title"),
        }

        best = subscribers.select_main_channels(qid_of, channels, records)

        self.assertEqual(best, {
            "person": (200, "B title"),
            "tie": (100, "A title"),
        })


if __name__ == "__main__":
    unittest.main()
