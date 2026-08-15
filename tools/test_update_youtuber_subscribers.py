import csv
import json
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
             "subscribers_as_of": "2026-07-30", "channel": "Keep A",
             "untouched": "x"},
            {"id": "1", "original": "A alias", "subscribers": "100",
             "subscribers_as_of": "2026-07-30", "channel": "Keep A",
             "untouched": "y"},
            {"id": "2", "original": "B", "subscribers": "200",
             "subscribers_as_of": "2026-07-30", "channel": "Keep B"},
            {"id": "3", "original": "C", "subscribers": "NA",
             "subscribers_as_of": "NA", "channel": "NA"},
        ]

        filled, updated, lost = subscribers.apply_snapshot(
            rows, columns,
            {"1": 150, "3": 300},
            "2026-08-15")

        self.assertEqual(
            [(row["channel"], row["subscribers"], row["subscribers_as_of"])
             for row in rows],
            [("Keep A", "150", "2026-08-15"),
             ("Keep A", "150", "2026-08-15"),
             ("Keep B", "NA", "NA"),
             ("NA", "300", "2026-08-15")],
        )
        self.assertEqual([rows[0]["untouched"], rows[1]["untouched"]], ["x", "y"])
        self.assertEqual(filled, {"3"})
        self.assertEqual(updated, {"1"})
        self.assertEqual(lost, {"2"})

    def test_columns_are_added_once_and_atomic_writer_preserves_format(self):
        columns = ["id", "original"]
        rows = [{"id": "1", "original": "A"}]
        subscribers.apply_snapshot(rows, columns, {"1": 42}, "2026-08-15")
        subscribers.apply_snapshot(rows, columns, {"1": 43}, "2026-08-16")

        self.assertEqual(
            columns,
            ["id", "original", "subscribers", "subscribers_as_of"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "youtuber.csv"
            path.write_text("old", encoding="utf-8")
            subscribers.write_snapshot_atomic(path, columns, rows)
            self.assertFalse(path.read_bytes().endswith(b"\n"))
            with path.open(encoding="utf-8") as handle:
                rendered = list(csv.DictReader(handle))
        self.assertEqual(rendered[0]["subscribers"], "43")
        self.assertEqual(rendered[0]["subscribers_as_of"], "2026-08-16")

    def test_channel_backfill_only_changes_na_and_all_rows_share_selection(self):
        rows = [
            {"id": "1", "channel": "NA"},
            {"id": "1", "channel": "NA"},
            {"id": "2", "channel": "手入力を保持"},
        ]
        selected = {
            "1": {"channel_id": "UC" + "a" * 22,
                  "subscribers": 500, "title": "正式タイトル"},
            "2": {"channel_id": "UC" + "b" * 22,
                  "subscribers": 900, "title": "別タイトル"},
        }

        filled = subscribers.apply_channel_backfill(rows, selected)

        self.assertEqual(filled, {"1"})
        self.assertEqual([row["channel"] for row in rows],
                         ["正式タイトル", "正式タイトル", "手入力を保持"])

    def test_mismatched_existing_channel_preserves_whole_previous_snapshot(self):
        columns = ["id", "channel", "subscribers", "subscribers_as_of"]
        rows = [{"id": "1", "channel": "既存チャンネル", "subscribers": "100",
                 "subscribers_as_of": "2026-07-30"}]

        subscribers.apply_snapshot(
            rows, columns, {"1": 999}, "2026-08-15", preserve={"1"})
        subscribers.apply_channel_backfill(rows, {
            "1": {"channel_id": "UC" + "a" * 22,
                  "subscribers": 999, "title": "別チャンネル"}})

        self.assertEqual(rows[0], {
            "id": "1", "channel": "既存チャンネル", "subscribers": "100",
            "subscribers_as_of": "2026-07-30"})

    def test_alignment_rejects_title_or_count_from_another_channel(self):
        selected = {"1": {"channel_id": "UC" + "a" * 22,
                          "subscribers": 200, "title": "選定チャンネル"}}
        good = [{"id": "1", "channel": "選定チャンネル", "subscribers": "200"}]
        subscribers.validate_snapshot_alignment(good, selected, set())

        bad = [{"id": "1", "channel": "別チャンネル", "subscribers": "200"}]
        with self.assertRaises(SystemExit):
            subscribers.validate_snapshot_alignment(bad, selected, set())

    def test_max_subscribers_keeps_id_title_and_count_from_same_channel(self):
        smaller = {"channel_id": "UC" + "a" * 22,
                   "subscribers": 100, "title": "small"}
        larger = {"channel_id": "UC" + "b" * 22,
                  "subscribers": 200, "title": "large"}

        selected = subscribers.select_channels(
            {"person": [smaller["channel_id"], larger["channel_id"]]},
            {smaller["channel_id"]: smaller, larger["channel_id"]: larger})

        self.assertEqual(selected["person"], larger)

    def test_fetch_channels_requests_statistics_and_snippet(self):
        channel_id = "UC" + "a" * 22
        response = {"items": [{
            "id": channel_id,
            "snippet": {"title": 'Formal, "Title"'},
            "statistics": {"subscriberCount": "123", "hiddenSubscriberCount": False},
        }]}
        with mock.patch.object(subscribers, "_get", return_value=response) as get:
            channels, hidden = subscribers.fetch_channels([channel_id], "secret")

        query = urllib.parse.parse_qs(urllib.parse.urlsplit(
            get.call_args.args[0]).query)
        self.assertEqual(query["part"], ["snippet,statistics"])
        self.assertEqual(channels[channel_id], {
            "channel_id": channel_id, "subscribers": 123,
            "title": "Formal Title"})
        self.assertEqual(hidden, 0)

    def test_verified_source_must_match_current_csv_identity(self):
        record = {
            "channel_id": "UC" + "a" * 22,
            "decision": "verified", "evidence_url": "https://youtube.com/@x",
            "original": "別人", "person_id": "1", "qid": "Q2",
            "source_type": "jawiki_external_link",
            "source_url": "https://ja.wikipedia.org/wiki/x",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with mock.patch.object(subscribers, "SOURCE_PATH", path):
                with self.assertRaises(SystemExit):
                    subscribers.load_verified_channel_sources(
                        {"1": "Q1"}, {"1": "本人"})


if __name__ == "__main__":
    unittest.main()
