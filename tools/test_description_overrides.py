import copy
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import description_overrides as target
import rebuild_football_jleague
import update_marine_life
import wpnames


def record(**changes):
    return {
        "list": "baseball", "id": "player_1", "original": "山田太郎",
        "column": "description", "description": "野球選手。",
        "source_urls": ["https://example.org/player/1"],
        "reviewed_on": "2026-10-12", **changes,
    }


class DescriptionOverridesTest(unittest.TestCase):
    def test_id_and_name_guard_updates_all_aliases_only(self):
        rows = [
            {"id": "player_1", "original": "山田太郎", "description": "旧文。"},
            {"id": "player_1", "original": "山田太郎（旧登録名）", "description": "旧文。"},
            {"id": "player_2", "original": "山田太郎", "description": "同名の別人。"},
        ]
        self.assertEqual(2, target.apply_overrides("baseball", rows, [record()]))
        self.assertEqual(["野球選手。", "野球選手。", "同名の別人。"],
                         [row["description"] for row in rows])
        self.assertEqual(0, target.apply_overrides("baseball", rows, [record()]))
        renamed = [{"id": "player_1", "original": "別人", "description": "保護。"}]
        self.assertEqual(0, target.apply_overrides("baseball", renamed, [record()]))
        self.assertEqual("保護。", renamed[0]["description"])

    def test_strict_check_fails_before_any_mutation(self):
        rows = [{"id": "player_1", "original": "山田太郎", "description": "旧文。"}]
        before = copy.deepcopy(rows)
        with self.assertRaisesRegex(ValueError, "identity missing"):
            target.apply_overrides("baseball", rows,
                                   [record(), record(id="missing")], strict=True)
        self.assertEqual(before, rows)

    def test_empty_correction_suppresses_unidentified_description(self):
        rows = [{"id": "player_1", "original": "山田太郎", "description": "別人の説明。"}]
        target.apply_overrides("baseball", rows, [record(description="")])
        self.assertEqual("", rows[0]["description"])

    def test_ledger_validates_identity_and_csv_safe_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.jsonl"
            path.write_text(json.dumps(record(), ensure_ascii=False), encoding="utf-8")
            self.assertEqual([record()], target.load_records(path))
            for bad in [record(description="切れた（文。"), record(description='a,b'),
                        record(source_urls=["file:///secret"]), record(id="")]:
                path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
                with self.assertRaises(ValueError):
                    target.load_records(path)
            path.write_text("\n".join([json.dumps(record())] * 2), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                target.load_records(path)

    def test_ledger_rejects_conflicting_alias_corrections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.jsonl"
            aliases = [record(), record(original="旧登録名")]
            path.write_text("\n".join(json.dumps(row) for row in aliases), encoding="utf-8")
            self.assertEqual(aliases, target.load_records(path))
            aliases[1]["description"] = "別の説明。"
            path.write_text("\n".join(json.dumps(row) for row in aliases), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Conflicting"):
                target.load_records(path)

    def test_shared_writer_preserves_inputs_and_uses_list_name(self):
        rows = [{"id": "player_1", "original": "山田太郎", "description": "旧文。"}]
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            target, "_records_by_list", return_value={"baseball": [record()]}
        ):
            path = Path(directory) / "baseball.csv"
            wpnames.write_csv_no_trailing_newline(path, list(rows[0]), rows)
            self.assertEqual("野球選手。", next(csv.DictReader(io.StringIO(path.read_text())))["description"])
            self.assertFalse(path.read_bytes().endswith(b"\n"))
            self.assertEqual("旧文。", rows[0]["description"])

    def test_football_writer_retains_reviewed_text(self):
        row = {column: "" for column in rebuild_football_jleague.CSV_COLUMNS}
        row.update(id="player_1", original="山田太郎", description="旧文。")
        correction = record(list="football", description="サッカー選手。")
        with mock.patch.object(target, "_records_by_list", return_value={"football": [correction]}):
            rendered = rebuild_football_jleague.csv_text([row])
        self.assertEqual("サッカー選手。", next(csv.DictReader(io.StringIO(rendered)))["description"])
        self.assertEqual("旧文。", row["description"])

    def test_marine_render_keeps_source_evidence_unchanged(self):
        row = {column: "" for column in update_marine_life.SOURCE_COLUMNS}
        row.update(id="0", name="クジラ", description="元の出典文。", image_group="哺乳類")
        correction = record(list="marine_life", id="0", original="クジラ",
                            description="海で暮らす哺乳類。")
        with mock.patch.object(target, "_records_by_list", return_value={"marine_life": [correction]}):
            rendered = update_marine_life.generate([row], []).decode()
        self.assertEqual("海で暮らす哺乳類。", next(csv.DictReader(io.StringIO(rendered)))["description"])
        self.assertEqual("元の出典文。", row["description"])


if __name__ == "__main__":
    unittest.main()
