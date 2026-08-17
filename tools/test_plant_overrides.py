import csv
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plant_overrides import apply_manual_taxon, is_rejected_p18


class PlantOverridesTest(unittest.TestCase):
    def test_confirmed_examples_fill_taxonomy(self):
        sakura = {"original": "サクラバラ", "wikidata": "", "family": ""}
        munin = {"original": "ムニンノキ", "wikidata": "", "family": ""}
        yuzu = {"original": "ユズ", "wikidata": "", "family": ""}
        apply_manual_taxon(sakura)
        apply_manual_taxon(munin)
        apply_manual_taxon(yuzu)
        self.assertEqual(
            ("Q87642005", "バラ科", "Q46299", "バラ属"),
            tuple(sakura[key] for key in (
                "wikidata", "family", "family_wikidata", "genus",
            )),
        )
        self.assertEqual(
            ("Q15319651", "アカテツ科", "Q158981", "Planchonella"),
            tuple(munin[key] for key in (
                "wikidata", "family", "family_wikidata", "genus",
            )),
        )
        self.assertEqual(
            ("Q867776", "Citrus × junos", "ミカン科", "Q146030", "ミカン属"),
            tuple(yuzu[key] for key in (
                "wikidata", "scientific_name", "family", "family_wikidata", "genus",
            )),
        )

    def test_does_not_overwrite_existing_value(self):
        row = {"original": "サクラバラ", "family": "既存科"}
        apply_manual_taxon(row)
        self.assertEqual("既存科", row["family"])

    def test_yuzu_taxonomy_is_materialized_in_wordlist(self):
        with (Path(__file__).resolve().parent.parent / "plant.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            yuzu = next(
                row for row in csv.DictReader(stream) if row["original"] == "ユズ"
            )
        self.assertEqual(
            ("Q867776", "Citrus × junos", "ミカン科", "Q146030", "ミカン属"),
            tuple(yuzu[key] for key in (
                "wikidata", "scientific_name", "family", "family_wikidata", "genus",
            )),
        )

    def test_rejects_reviewed_botanical_illustration_only(self):
        self.assertTrue(is_rejected_p18(
            "https://commons.wikimedia.org/wiki/Special:FilePath/"
            "Sargassum_fulvellum_as_Fucus_fulvellus_in_Turner_1808.jpg"
        ))
        self.assertFalse(is_rejected_p18(
            "https://commons.wikimedia.org/wiki/Special:FilePath/plant_photo.jpg"
        ))


if __name__ == "__main__":
    unittest.main()
