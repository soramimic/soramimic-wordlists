import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_youtuber_scope as scope  # noqa: E402


class ScopeTest(unittest.TestCase):
    def row(self, **values):
        base = {"id": "1", "original": "人物", "surface": "人物",
                "wikidata": "Q1", "org": "NA", "scope": ""}
        base.update(values)
        return base

    def test_override_has_priority(self):
        row = self.row(scope="global", org="hololive English")
        overrides = {"人物": {"scope": "japan"}}
        self.assertEqual(scope.infer_scope(row, {"Q30"}, overrides), "japan")

    def test_reviewed_japan_registry_is_a_scope_source(self):
        row = self.row(original="レビュー済み人物", org="NA")
        self.assertEqual(scope.infer_scope(
            row, set(), {}, {"レビュー済み人物"}), "japan")
        self.assertEqual(scope.infer_scope(
            row, set(), {"レビュー済み人物": {"scope": "global"}},
            {"レビュー済み人物"}), "global")

    def test_load_reviewed_japan_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "people.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "people": [{"original": "甲"}, {"original": "乙"}],
            }, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(scope.load_reviewed_japan_names(path), {"甲", "乙"})

    def test_load_reviewed_japan_names_rejects_non_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "people.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "人物台帳"):
                scope.load_reviewed_japan_names(path)

    def test_domestic_and_overseas_official_branches(self):
        self.assertEqual(scope.infer_scope(
            self.row(org="にじさんじ"), set(), {}), "japan")
        self.assertEqual(scope.infer_scope(
            self.row(org="NIJISANJI EN/にじさんじ"), set(), {}), "global")
        self.assertEqual(scope.infer_scope(
            self.row(org="ホロライブプロダクション",
                     channel="Gawr Gura Ch. hololive-EN"), set(), {}), "global")

    def test_domestic_youtuber_groups(self):
        for org in ("東海オンエア", "フィッシャーズ", "水溜りボンド",
                    "スカイピース", "QuizKnock", "コムドット"):
            with self.subTest(org=org):
                self.assertEqual(
                    scope.infer_scope(self.row(org=org), set(), {}), "japan")

    def test_citizenship_is_conservative_fallback(self):
        self.assertEqual(scope.infer_scope(self.row(), {"Q17"}, {}), "japan")
        self.assertEqual(scope.infer_scope(self.row(), {"Q30"}, {}), "global")
        self.assertEqual(scope.infer_scope(self.row(), set(), {}), "unknown")

    def test_japanese_article_or_name_alone_is_not_japan(self):
        row = self.row(original="日本語名", surface="日本語名")
        self.assertEqual(scope.infer_scope(row, set(), {}), "unknown")

    def test_apply_adds_one_column_and_keeps_id_rows_aligned(self):
        rows = [self.row(surface="姓"), self.row(surface="名")]
        columns, counts = scope.apply_scopes(
            rows, ["id", "original", "surface", "wikidata", "org"],
            {"Q1": {"Q17"}}, {})
        self.assertEqual(columns.count("scope"), 1)
        self.assertEqual([row["scope"] for row in rows], ["japan", "japan"])
        self.assertEqual(counts["japan"], 1)


if __name__ == "__main__":
    unittest.main()
