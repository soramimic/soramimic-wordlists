import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_youtuber_japan as target
import update_youtuber_subscribers as subscribers


COLUMNS = [
    "id", "original", "surface", "pronunciation", "type", "category",
    "org", "debut_year", "status", "image", "image_page", "wikidata",
    "channel", "description", "subscribers", "subscribers_as_of", "scope",
]


def person(name="人物", qid="NA", channel_id=None, title="人物チャンネル",
           shared=False, org="NA"):
    channel_id = channel_id or ("UC" + "a" * 22)
    return {
        "original": name,
        "pronunciation": "ジンブツ",
        "debut_year": "2020",
        "org": org,
        "description": "動画を発信するYouTuber。",
        "qid": qid,
        "source_url": "https://example.com/person",
        "channel_id": channel_id,
        "channel_title": title,
        "channel_url": f"https://www.youtube.com/channel/{channel_id}",
        "channel_shared": shared,
    }


class UpdateYoutuberJapanTest(unittest.TestCase):
    def test_reviewed_registry_is_valid_and_contains_initial_people(self):
        people = target.load_people()
        names = {item["original"] for item in people}

        self.assertEqual(len(people), 28)
        self.assertTrue({
            "ヒカル", "シルクロード", "カンタ", "テオくん", "☆イニ☆",
            "河村拓哉", "鶴崎修功", "山本祥彰", "やまと", "ひゅうが", "ゆうま",
        }.issubset(names))
        self.assertTrue({"フィッシャーズ", "水溜りボンド", "スカイピース",
                         "QuizKnock", "コムドット"}.isdisjoint(names))

    def test_requested_group_members_are_present_as_people(self):
        with target.CSV_PATH.open(encoding="utf-8", newline="") as handle:
            originals = {
                row["original"] for row in csv.DictReader(handle)
                if row["type"] == "full"
            }
        expected = {
            "てつや", "りょう", "しばゆー", "としみつ", "ゆめまる", "虫眼鏡",
            "シルクロード", "マサイ", "モトキ", "ザカオ", "ダーマ", "ンダホ",
            "カンタ", "トミー", "テオくん", "☆イニ☆", "伊沢拓司", "河村拓哉",
            "ふくらP", "鶴崎修功", "須貝駿貴", "山本祥彰", "東問", "東言",
            "やまと", "ゆうた", "ひゅうが", "ゆうま", "あむぎり",
        }

        self.assertTrue(expected.issubset(originals))

    def test_adds_person_activity_name_and_japan_scope(self):
        rows, sources, added, ids = target.apply_people(
            [], COLUMNS, [person(title="発見用チャンネル名")], [], "2026-08-17")

        self.assertEqual(added, 1)
        self.assertEqual(ids, {"人物": "0"})
        self.assertEqual(rows[0]["original"], "人物")
        self.assertEqual(rows[0]["surface"], "人物")
        self.assertNotIn("チャンネル", rows[0]["surface"])
        self.assertEqual(rows[0]["channel"], "発見用チャンネル名")
        self.assertEqual(rows[0]["channel_shared"], "no")
        self.assertEqual(rows[0]["scope"], "japan")
        self.assertEqual(sources[0]["person_id"], "0")
        self.assertEqual(sources[0]["source_type"], "reviewed_person_roster")

    def test_shared_channel_discovers_people_but_is_not_a_subscriber_source(self):
        channel_id = "UC" + "s" * 22
        people = [
            person(name="甲", channel_id=channel_id, title="共有チャンネル",
                   shared=True, org="グループ"),
            person(name="乙", channel_id=channel_id, title="共有チャンネル",
                   shared=True, org="グループ"),
        ]

        rows, sources, added, ids = target.apply_people(
            [], COLUMNS, people, [], "2026-08-17")

        self.assertEqual(added, 2)
        self.assertEqual(set(ids), {"甲", "乙"})
        self.assertEqual({row["channel"] for row in rows}, {"共有チャンネル"})
        self.assertEqual({row["channel_shared"] for row in rows}, {"yes"})
        self.assertEqual(len(sources), 2)
        self.assertEqual(
            {record["decision"] for record in sources},
            {"verified_shared_group_channel"})
        self.assertEqual(
            {record["person_id"] for record in sources}, set(ids.values()))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.jsonl"
            target.write_jsonl(path, sources)
            with mock.patch.object(subscribers, "SOURCE_PATH", path):
                got = subscribers.load_verified_channel_sources(
                    {pid: "NA" for pid in ids.values()},
                    {pid: name for name, pid in ids.items()})

        self.assertEqual(got, {})

    def test_shared_channel_provenance_is_idempotent_and_validated(self):
        shared = person(shared=True)
        first_rows, first_sources, _added, _ids = target.apply_people(
            [], COLUMNS, [shared], [], "2026-08-17")
        second_rows, second_sources, added, _ids = target.apply_people(
            first_rows, COLUMNS, [shared], first_sources, "2026-08-18")

        self.assertEqual(added, 0)
        self.assertEqual(second_rows, first_rows)
        self.assertEqual(second_sources, first_sources)

        wrong_decision = [dict(first_sources[0], decision="unknown")]
        with self.assertRaisesRegex(target.RosterConflict, "decision"):
            target.apply_people(
                first_rows, COLUMNS, [shared], wrong_decision, "2026-08-18")

        with self.assertRaisesRegex(target.RosterConflict, "根拠が重複"):
            target.apply_people(
                first_rows, COLUMNS, [shared], first_sources * 2,
                "2026-08-18")

    def test_migrates_matching_legacy_shared_roster_provenance_only(self):
        shared = person(shared=True)
        rows, sources, _added, _ids = target.apply_people(
            [], COLUMNS, [shared], [], "2026-08-17")
        legacy = [dict(sources[0], decision="verified")]

        migrated_rows, migrated, added, _ids = target.apply_people(
            rows, COLUMNS, [shared], legacy, "2026-08-18")

        self.assertEqual(added, 0)
        self.assertEqual(migrated_rows, rows)
        self.assertEqual(
            migrated[0]["decision"], "verified_shared_group_channel")
        self.assertEqual(legacy[0]["decision"], "verified")
        _rows, rerun, _added, _ids = target.apply_people(
            migrated_rows, COLUMNS, [shared], migrated, "2026-08-19")
        self.assertEqual(rerun, migrated)

        older_source = [dict(
            legacy[0], source_type="jawiki_external_link")]
        _rows, migrated_older_source, _added, _ids = target.apply_people(
            rows, COLUMNS, [shared], older_source, "2026-08-18")
        self.assertEqual(
            migrated_older_source[0]["decision"],
            "verified_shared_group_channel")

        unrelated = [dict(legacy[0], decision="deferred_ambiguous")]
        with self.assertRaisesRegex(target.RosterConflict, "decision"):
            target.apply_people(
                rows, COLUMNS, [shared], unrelated, "2026-08-18")

    def test_channel_shared_marks_unreviewed_and_duplicate_person_rows(self):
        unreviewed = {column: "" for column in COLUMNS}
        unreviewed.update({
            "id": "1", "original": "台帳外", "category": "youtuber",
            "wikidata": "NA",
        })
        reviewed_rows = []
        for surface in ("人物", "人物別表記"):
            row = {column: "" for column in COLUMNS}
            row.update({
                "id": "2", "original": "人物", "surface": surface,
                "category": "youtuber", "wikidata": "NA",
            })
            reviewed_rows.append(row)

        rows, _sources, added, _ids = target.apply_people(
            [unreviewed, *reviewed_rows], COLUMNS, [person(shared=True)],
            [], "2026-08-17")

        self.assertEqual(added, 0)
        self.assertEqual(rows[0]["channel_shared"], "NA")
        self.assertEqual(
            [row["channel_shared"] for row in rows if row["id"] == "2"],
            ["yes", "yes"])

    def test_channel_shared_preserves_reviewed_state_outside_roster(self):
        existing = {column: "" for column in COLUMNS}
        existing.update({
            "id": "1", "original": "台帳外", "category": "youtuber",
            "wikidata": "NA", "channel": "共有チャンネル",
            "channel_shared": "yes",
        })

        rows, _sources, added, _ids = target.apply_people(
            [existing], [*COLUMNS, "channel_shared"], [], [], "2026-08-17")

        self.assertEqual(added, 0)
        self.assertEqual(rows[0]["channel_shared"], "yes")

    def test_shared_candidate_preserves_existing_personal_channel_marker(self):
        existing = {column: "" for column in COLUMNS}
        existing.update({
            "id": "7", "original": "人物", "surface": "人物",
            "pronunciation": "ジンブツ", "category": "youtuber",
            "wikidata": "NA", "channel": "検証済み個人チャンネル",
        })
        shared = person(title="グループ共有チャンネル", shared=True)

        rows, sources, added, _ids = target.apply_people(
            [existing], COLUMNS, [shared], [], "2026-08-17")

        self.assertEqual(added, 0)
        self.assertEqual(rows[0]["channel"], "検証済み個人チャンネル")
        self.assertEqual(rows[0]["channel_shared"], "no")
        self.assertEqual(len(sources), 1)
        self.assertEqual(
            sources[0]["decision"], "verified_shared_group_channel")
        self.assertEqual(sources[0]["channel_title"], "グループ共有チャンネル")

    def test_is_idempotent_and_preserves_existing_spelling_and_reading(self):
        existing = {column: "" for column in COLUMNS}
        existing.update({
            "id": "7", "original": "人物", "surface": "人ぶつ",
            "pronunciation": "レビューズミノヨミ", "type": "full",
            "category": "youtuber", "wikidata": "NA",
            "channel": "手修正済みチャンネル",
            "scope": "unknown",
        })
        first_rows, first_sources, first_added, _ = target.apply_people(
            [existing], COLUMNS, [person()], [], "2026-08-17")
        second_rows, second_sources, second_added, _ = target.apply_people(
            first_rows, COLUMNS, [person()], first_sources, "2026-08-18")

        self.assertEqual(first_added, 0)
        self.assertEqual(second_added, 0)
        self.assertEqual(second_rows, first_rows)
        self.assertEqual(second_sources, first_sources)
        self.assertEqual(second_rows[0]["surface"], "人ぶつ")
        self.assertEqual(second_rows[0]["pronunciation"], "レビューズミノヨミ")
        self.assertEqual(second_rows[0]["channel"], "手修正済みチャンネル")
        self.assertEqual(second_rows[0]["debut_year"], "2020")
        self.assertEqual(second_rows[0]["description"], "動画を発信するYouTuber。")
        self.assertEqual(second_rows[0]["scope"], "japan")

    def test_existing_qid_is_used_for_new_channel_evidence(self):
        existing = {column: "" for column in COLUMNS}
        existing.update({
            "id": "7", "original": "人物", "surface": "人物",
            "pronunciation": "ジンブツ", "category": "youtuber",
            "wikidata": "Q123",
        })

        _rows, sources, added, _ids = target.apply_people(
            [existing], COLUMNS, [person(qid="NA")], [], "2026-08-17")

        self.assertEqual(added, 0)
        self.assertEqual(sources[0]["qid"], "Q123")

    def test_conflicting_name_qid_or_channel_stops_without_mutating_inputs(self):
        name_rows = [
            {"id": "1", "original": "人物", "wikidata": "NA"},
            {"id": "2", "original": "人物", "wikidata": "NA"},
        ]
        with self.assertRaisesRegex(target.RosterConflict, "同じ活動名"):
            target.apply_people(name_rows, COLUMNS, [person()], [], "2026-08-17")

        qid_rows = [{"id": "1", "original": "別人", "wikidata": "Q123"}]
        with self.assertRaisesRegex(target.RosterConflict, "別の活動名"):
            target.apply_people(
                qid_rows, COLUMNS, [person(qid="Q123")], [], "2026-08-17")

        ledger = [{
            "person_id": "9", "channel_id": "UC" + "a" * 22,
            "original": "別人",
        }]
        original_ledger = [dict(ledger[0])]
        with self.assertRaisesRegex(target.RosterConflict, "別人物"):
            target.apply_people([], COLUMNS, [person()], ledger, "2026-08-17")
        self.assertEqual(ledger, original_ledger)

    def test_written_ledger_is_accepted_by_subscriber_updater(self):
        rows, sources, _added, ids = target.apply_people(
            [], COLUMNS, [person()], [], "2026-08-17")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.jsonl"
            target.write_jsonl(path, sources)
            with mock.patch.object(subscribers, "SOURCE_PATH", path):
                got = subscribers.load_verified_channel_sources(
                    {ids["人物"]: "NA"}, {ids["人物"]: "人物"})

        self.assertEqual(got, {"0": ["UC" + "a" * 22]})
        self.assertEqual(rows[0]["channel"], "人物チャンネル")

    def test_cli_writes_csv_and_ledger_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "youtuber.csv"
            people_path = root / "people.json"
            sources_path = root / "sources.jsonl"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=COLUMNS)
                writer.writeheader()
            people_path.write_text(json.dumps({
                "schema_version": 1, "people": [person()]
            }, ensure_ascii=False), encoding="utf-8")

            args = ["--csv", str(csv_path), "--people", str(people_path),
                    "--channel-sources", str(sources_path),
                    "--observed-on", "2026-08-17"]
            self.assertEqual(target.main(args), 0)
            first = (csv_path.read_bytes(), sources_path.read_bytes())
            self.assertEqual(target.main(args), 0)

            self.assertEqual((csv_path.read_bytes(), sources_path.read_bytes()), first)
            with csv_path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                written_rows = list(reader)
            self.assertEqual(reader.fieldnames[-1], "channel_shared")
            self.assertEqual(written_rows[0]["channel_shared"], "no")


if __name__ == "__main__":
    unittest.main()
