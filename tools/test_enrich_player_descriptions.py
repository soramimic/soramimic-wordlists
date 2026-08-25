import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_player_descriptions as target


class EnrichPlayerDescriptionsTests(unittest.TestCase):
    def test_refresh_refetches_positive_and_negative_cached_articles(self):
        cache = {
            "既存": {
                "title": "既存", "intro": "旧。", "disambiguation": False,
                "qid": "Q1", "revision": "1",
            },
            "未作成": {
                "title": "未作成", "intro": "", "disambiguation": False,
                "qid": "", "revision": "",
            },
        }
        fetched = []

        def fake_fetch(batch):
            fetched.extend(batch)
            return {
                title: {
                    "title": title, "intro": "新。", "disambiguation": False,
                    "qid": "Q2", "revision": "2",
                }
                for title in batch
            }

        with (
            mock.patch.object(target, "fetch_intro_batch", side_effect=fake_fetch),
            mock.patch.object(target, "save_cache"),
        ):
            target.fetch_intros(["既存", "未作成"], cache, refresh=True)

        self.assertEqual(["既存", "未作成"], fetched)
        self.assertEqual("2", cache["既存"]["revision"])
        self.assertEqual("2", cache["未作成"]["revision"])

    def test_na_with_period_is_treated_as_missing(self):
        columns = ["id", "original", "surface", "pronunciation", "type", "description"]
        rows = [
            ["1", "山田 太郎", "山田 太郎", "ヤマダ タロウ", "full", "NA。"],
            ["1", "山田 太郎", "山田", "ヤマダ", "family", "NA。"],
            ["2", "佐藤 次郎", "佐藤 次郎", "サトウ ジロウ", "full", "既存の説明。"],
        ]
        cache = {
            "山田太郎": {
                "title": "山田太郎",
                "intro": "山田太郎は日本のサッカー選手。主要大会で優勝した。",
                "disambiguation": False,
            }
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "football.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(columns)
                writer.writerows(rows)

            config = {**target.CONFIG["football"], "path": path}
            with (
                mock.patch.dict(target.CONFIG, {"football": config}),
                mock.patch.object(target, "fetch_intros"),
                mock.patch.object(
                    target, "make_player_description", return_value="主要大会で優勝。"
                ),
            ):
                target.enrich("football", cache, refresh=False)

            with path.open(encoding="utf-8") as stream:
                updated = list(csv.DictReader(stream))

        self.assertEqual(
            ["主要大会で優勝。", "主要大会で優勝。"],
            [row["description"] for row in updated if row["id"] == "1"],
        )
        self.assertEqual("既存の説明。", updated[2]["description"])


if __name__ == "__main__":
    unittest.main()
