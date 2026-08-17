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

    def test_shared_channel_backfill_marks_only_shared_only_people(self):
        rows = [
            {"id": "1", "channel": "NA", "channel_shared": "NA"},
            {"id": "1", "channel": "NA", "channel_shared": "NA"},
            {"id": "2", "channel": "個人ch", "channel_shared": "no"},
            {"id": "3", "channel": "別の表示", "channel_shared": "NA"},
        ]
        selected = {
            "2": {"channel_id": "UC" + "p" * 22,
                  "subscribers": 1, "title": "個人ch"},
        }

        applied = subscribers.apply_shared_channel_backfill(
            rows, {"1": ["共有ch"], "2": ["共有ch"], "3": ["共有ch"]},
            selected)

        self.assertEqual(applied, {"1"})
        self.assertEqual(
            [(row["channel"], row["channel_shared"]) for row in rows],
            [("共有ch", "yes"), ("共有ch", "yes"),
             ("個人ch", "no"), ("別の表示", "NA")])

    def test_personal_channel_marker_requires_selected_verified_pair(self):
        rows = [
            {"id": "1", "channel_shared": "NA"},
            {"id": "2", "channel_shared": "NA"},
        ]
        channel_id = "UC" + "v" * 22
        selected = {
            "1": {"channel_id": channel_id, "subscribers": 1,
                  "title": "検証済み"},
            "2": {"channel_id": "UC" + "w" * 22, "subscribers": 2,
                  "title": "Wikidataのみ"},
        }

        marked = subscribers.apply_personal_channel_markers(
            rows, selected, {("1", channel_id)})

        self.assertEqual(marked, {"1"})
        self.assertEqual([row["channel_shared"] for row in rows], ["no", "NA"])

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

    def test_audit_report_drops_resolved_candidate_but_keeps_unresolved(self):
        channel_id = "UC" + "a" * 22
        rows = [
            {"id": "1", "original": "解決済み", "channel": "正式名"},
            {"id": "2", "original": "未解決", "channel": "NA"},
        ]
        old_report = [
            {"person_id": "1", "decision": "deferred_ambiguous",
             "source_type": "web_search_candidate",
             "evidence_url": "https://example.com/resolved"},
            {"person_id": "2", "decision": "deferred_ambiguous",
             "source_type": "web_search_candidate",
             "evidence_url": "https://example.com/unresolved"},
        ]
        selected = {
            "1": {"channel_id": channel_id, "subscribers": 100,
                  "title": "正式名"},
        }

        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "sources.jsonl"
            report_path = Path(tmp) / "report.jsonl"
            report_path.write_text(
                "".join(json.dumps(record, ensure_ascii=False) + "\n"
                        for record in old_report), encoding="utf-8")
            with mock.patch.object(subscribers, "SOURCE_PATH", source_path), \
                    mock.patch.object(subscribers, "REPORT_PATH", report_path):
                _evidence_count, deferred_count = \
                    subscribers.update_audit_files(
                        rows, {}, {}, selected, "2026-08-15")
            rendered = [json.loads(line) for line in
                        report_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(deferred_count, 1)
        self.assertEqual([record["person_id"] for record in rendered], ["2"])

    def test_audit_report_drops_shared_channel_from_unavailable_queue(self):
        rows = [{"id": "1", "original": "共有人物", "channel": "共有ch"}]
        old_report = [{
            "person_id": "1", "decision": "deferred_channel_unavailable",
            "source_type": "youtube_data_api",
        }]
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "sources.jsonl"
            report_path = Path(tmp) / "report.jsonl"
            report_path.write_text(
                json.dumps(old_report[0], ensure_ascii=False) + "\n",
                encoding="utf-8")
            with mock.patch.object(subscribers, "SOURCE_PATH", source_path), \
                    mock.patch.object(subscribers, "REPORT_PATH", report_path):
                _evidence_count, deferred_count = \
                    subscribers.update_audit_files(
                        rows, {}, {}, {}, "2026-08-17", {"1"})

            self.assertEqual(report_path.read_text(encoding="utf-8"), "")
        self.assertEqual(deferred_count, 0)

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

    def test_wikidata_handle_source_is_allowed_with_matching_identity(self):
        channel_id = "UC" + "a" * 22
        record = {
            "channel_id": channel_id, "decision": "verified",
            "evidence_url": "https://youtube.com/@person",
            "original": "本人", "person_id": "1", "qid": "Q1",
            "source_type": "wikidata_youtube_handle",
            "source_url": "https://www.wikidata.org/wiki/Q1",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with mock.patch.object(subscribers, "SOURCE_PATH", path):
                result = subscribers.load_verified_channel_sources(
                    {"1": "Q1"}, {"1": "本人"})

        self.assertEqual(result, {"1": [channel_id]})

    def test_web_search_source_requires_primary_link_evidence(self):
        channel_id = "UC" + "a" * 22
        record = {
            "channel_id": channel_id, "decision": "verified",
            "discovery_method": "gemini_chrome_google_search",
            "evidence_quote": "本人公式YouTubeです。",
            "evidence_url": "https://youtube.com/@person",
            "identity_basis": "youtube_about_self_identification",
            "original": "本人", "person_id": "1", "qid": "Q1",
            "source_type": "web_search_primary_link",
            "source_url": "https://youtube.com/@person",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with mock.patch.object(subscribers, "SOURCE_PATH", path):
                result = subscribers.load_verified_channel_sources(
                    {"1": "Q1"}, {"1": "本人"})
        self.assertEqual(result, {"1": [channel_id]})

        record["identity_basis"] = "wikipedia_person_article_explicit_link"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with mock.patch.object(subscribers, "SOURCE_PATH", path):
                result = subscribers.load_verified_channel_sources(
                    {"1": "Q1"}, {"1": "本人"})
        self.assertEqual(result, {"1": [channel_id]})

        del record["evidence_quote"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with mock.patch.object(subscribers, "SOURCE_PATH", path):
                with self.assertRaises(SystemExit):
                    subscribers.load_verified_channel_sources(
                        {"1": "Q1"}, {"1": "本人"})

    def test_web_search_primary_link_supports_person_without_qid(self):
        channel_id = "UC" + "a" * 22
        record = {
            "channel_id": channel_id, "decision": "verified",
            "discovery_method": "gemini_chrome_google_search",
            "evidence_quote": "所属先が本人のチャンネルとして明示した。",
            "evidence_url": "https://youtube.com/channel/" + channel_id,
            "identity_basis": "official_page_explicit_channel_link",
            "original": "本人", "person_id": "1", "qid": "NA",
            "source_type": "web_search_primary_link",
            "source_url": "https://example.com/person",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with mock.patch.object(subscribers, "SOURCE_PATH", path):
                result = subscribers.load_verified_channel_sources(
                    {}, {"1": "本人"})
        self.assertEqual(result, {"1": [channel_id]})

    def test_official_talent_profile_supports_person_without_qid(self):
        channel_id = "UC" + "n" * 22
        profile = "https://www.nijisanji.jp/talents/l/example"
        record = {
            "channel_id": channel_id, "decision": "verified",
            "evidence_url": profile,
            "identity_basis": "official_page_explicit_channel_link",
            "original": "公式ライバー", "person_id": "7", "qid": "NA",
            "source_type": "official_talent_profile", "source_url": profile,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with mock.patch.object(subscribers, "SOURCE_PATH", path):
                result = subscribers.load_verified_channel_sources(
                    {}, {"7": "公式ライバー"})
        self.assertEqual(result, {"7": [channel_id]})

    def test_shared_group_channel_is_valid_but_subscriber_ineligible(self):
        channel_id = "UC" + "s" * 22
        personal_id = "UC" + "p" * 22
        record = {
            "channel_id": channel_id,
            "decision": "verified_shared_group_channel",
            "evidence_url": "https://www.youtube.com/channel/" + channel_id,
            "identity_basis": "reviewed_person_source_and_official_channel",
            "original": "共有人物", "person_id": "8", "qid": "NA",
            "source_type": "reviewed_person_roster",
            "source_url": "https://example.com/official-member",
        }
        personal = {
            "channel_id": personal_id, "decision": "verified",
            "evidence_url": "https://www.youtube.com/channel/" + personal_id,
            "identity_basis": "official_page_explicit_channel_link",
            "original": "共有人物", "person_id": "8", "qid": "NA",
            "source_type": "official_talent_profile",
            "source_url": "https://example.com/personal",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.jsonl"
            path.write_text(
                json.dumps(record) + "\n" + json.dumps(personal) + "\n",
                encoding="utf-8")
            with mock.patch.object(subscribers, "SOURCE_PATH", path):
                eligible, shared = subscribers.load_channel_source_registry(
                    {}, {"8": "共有人物"})

        self.assertEqual(eligible, {"8": [personal_id]})
        self.assertEqual(shared, {"8": [channel_id]})

    def test_unknown_ledger_decision_is_rejected(self):
        channel_id = "UC" + "x" * 22
        record = {
            "channel_id": channel_id, "decision": "typo",
            "evidence_url": "https://www.youtube.com/channel/" + channel_id,
            "original": "人物", "person_id": "9", "qid": "NA",
            "source_type": "reviewed_person_roster",
            "source_url": "https://example.com/person",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with mock.patch.object(subscribers, "SOURCE_PATH", path):
                with self.assertRaises(SystemExit):
                    subscribers.load_channel_source_registry(
                        {}, {"9": "人物"})


if __name__ == "__main__":
    unittest.main()
