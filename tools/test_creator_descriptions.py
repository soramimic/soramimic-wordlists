import copy
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from creator_descriptions import apply_reviewed, load_reviewed
from yt_common import make_youtuber_description


class ReviewedDescriptionsTest(unittest.TestCase):
    def setUp(self):
        self.record = {
            "person_id": "12", "original": "テスト",
            "description": "ゲーム実況を中心に活動する。",
            "source_urls": ["https://example.com/profile"],
            "reviewed_on": "2026-09-08",
        }
        self.rows = [
            {"id": "12", "original": "テスト", "category": "vtuber",
             "surface": surface, "description": "NA", "image": "keep.png"}
            for surface in ("テスト", "てすと")
        ] + [{"id": "13", "original": "別人", "category": "vtuber",
              "description": "既存の説明。"}]

    def test_applies_to_all_aliases_and_preserves_other_fields(self):
        before = copy.deepcopy(self.rows)
        self.assertEqual(apply_reviewed(self.rows, [self.record]), 2)
        for row in before[:2]:
            row["description"] = self.record["description"]
        self.assertEqual(self.rows, before)
        self.assertEqual(apply_reviewed(self.rows, [self.record]), 0)

    def test_identity_mismatch_fails_before_any_changes(self):
        for change in ({"person_id": "99"}, {"original": "別人"}):
            before = copy.deepcopy(self.rows)
            with self.assertRaises(ValueError):
                apply_reviewed(self.rows, [self.record, {**self.record, **change}])
            self.assertEqual(self.rows, before)
        self.rows[1]["category"] = "youtuber"
        with self.assertRaises(ValueError):
            apply_reviewed(self.rows, [self.record])
        self.assertEqual(self.rows[0]["description"], "NA")

    def test_rejects_duplicate_or_unsourced_records(self):
        invalid = [
            [self.record, self.record],
            [{**self.record, "source_urls": []}],
            [{**self.record, "source_urls": ["file:///profile"]}],
            [{**self.record, "description": "ゲーム配信を行う（VTuber。"}],
            [{**self.record, "reviewed_on": "2026-99-08"}],
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.jsonl"
            for records in invalid:
                path.write_text("\n".join(map(json.dumps, records)), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_reviewed(path)

    def test_regeneration_preserves_person_description_over_group_intro(self):
        name = "アイラニ・イオフィフティーン"
        expected = next(r["description"] for r in load_reviewed()
                        if r["original"] == name)
        for intro in ("", "代表アイドルをイメージキャラクターとしたサービスに由来する。"):
            self.assertEqual(make_youtuber_description(intro, "VTuber。", name), expected)
        self.assertEqual(make_youtuber_description("", "", "未確認の人物"), "NA")

    def test_source_ledger_matches_every_csv_alias(self):
        path = Path(__file__).resolve().parent.parent / "vtuber.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(apply_reviewed(rows, load_reviewed()), 0)


if __name__ == "__main__":
    unittest.main()
