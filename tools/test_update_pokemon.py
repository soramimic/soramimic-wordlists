import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_pokemon as target


class PokemonDescriptionTest(unittest.TestCase):
    def test_generation_does_not_assert_a_specific_debut_version(self):
        text = target.description("NA", "どく", "ドラゴン", "7", "ウルトラビースト",
                                  "ベベノム", "3.6", "150.0")
        self.assertIn("第7世代に登場。", text)
        self.assertNotIn("サン・ムーン", text)
        self.assertIn("ベベノムから進化。", text)

    def test_special_forms_do_not_inherit_normal_evolution(self):
        mega = target.description("かえんポケモン", "ほのお", "ドラゴン", "6", "NA",
                                  "リザード", "1.7", "110.5", is_mega=True)
        self.assertIn("メガシンカした姿。", mega)
        self.assertNotIn("リザードから進化", mega)
        self.assertIn("重さ110.5kg", mega)
        gmax = target.description("いねむりポケモン", "ノーマル", "NA", "8", "NA",
                                  "ゴンベ", "35.0", "1000.0",
                                  form_name="キョダイマックスのすがた")
        self.assertIn("キョダイマックスした姿。", gmax)
        self.assertNotIn("ゴンベ", gmax)
        self.assertNotIn("高さ", gmax)
        self.assertNotIn("1000.0", gmax)

    def test_local_refresh_preserves_all_other_columns_and_is_repeatable(self):
        template = {
            "id": "1", "original": "メガニウム", "surface": "メガニウム",
            "genus": "ハーブポケモン", "type1": "くさ", "type2": "NA",
            "generation": "2", "rarity": "NA", "evolves_from": "ベイリーフ",
            "height_m": "1.8", "weight_kg": "100.5", "description": "旧文。",
            "image": "https://example.org/retained.svg",
        }
        rows = [template, {**template, "id": "2", "original": "リザードン"},
                {**template, "id": "3", "original": "メガリザードンX"}]
        for name in ("アブソル", "ガブリアス", "ルカリオ"):
            rows.extend([{**template, "id": str(len(rows)), "original": name},
                         {**template, "id": str(len(rows) + 1), "original": f"メガ{name}Z"}])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pokemon.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(template), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            self.assertEqual(1, target.refresh_descriptions(check=True, path=path))
            self.assertEqual(0, target.refresh_descriptions(path=path))
            self.assertEqual(0, target.refresh_descriptions(check=True, path=path))
            with path.open(encoding="utf-8", newline="") as handle:
                result = list(csv.DictReader(handle))
            for old, new in zip(rows, result):
                self.assertEqual({k: v for k, v in old.items() if k != "description"},
                                 {k: v for k, v in new.items() if k != "description"})
            self.assertIn("ベイリーフから進化。", result[0]["description"])
            self.assertNotIn("メガシンカした姿", result[0]["description"])
            self.assertIn("メガシンカした姿", result[2]["description"])
            for index in (4, 6, 8):
                self.assertIn("メガシンカした姿", result[index]["description"])
                self.assertNotIn("から進化", result[index]["description"])


if __name__ == "__main__":
    unittest.main()
