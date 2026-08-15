import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_plant_entities as entities


class EnrichPlantEntitiesTest(unittest.TestCase):
    def test_only_unique_plant_candidate_is_applied(self):
        rows = [
            {"original": "一意", "wikidata": ""},
            {"original": "曖昧", "wikidata": ""},
            {"original": "動物のみ", "wikidata": ""},
            {"original": "既存", "wikidata": "Q9"},
        ]
        stats = entities.resolve_rows(rows, {
            # collect() がクレード外候補を除外するため「動物のみ」は空集合。
            "一意": {"Q1"}, "曖昧": {"Q3", "Q4"}, "動物のみ": set(),
        })
        self.assertEqual("Q1", rows[0]["wikidata"])
        self.assertEqual("", rows[1]["wikidata"])
        self.assertEqual("", rows[2]["wikidata"])
        self.assertEqual("Q9", rows[3]["wikidata"])
        self.assertEqual(1, stats["automatic"])
        self.assertEqual(1, stats["ambiguous"])
        self.assertEqual(1, stats["missing"])

    def test_reviewed_manual_mapping_persists_without_candidates(self):
        rows = [{"original": "サクラバラ", "wikidata": ""}]
        stats = entities.resolve_rows(rows, {})
        self.assertEqual("Q87642005", rows[0]["wikidata"])
        self.assertEqual(1, stats["manual"])

    def test_class_constraint_rejects_monocot_from_dicot(self):
        ancestors = {"Q1": [entities.ANGIOSPERM, entities.MONOCOTS]}
        self.assertFalse(entities.candidate_matches_class("Q1", "双子葉", ancestors))
        self.assertTrue(entities.candidate_matches_class("Q1", "単子葉", ancestors))

    def test_rejects_cross_linked_animal_even_if_plant_root_is_reached(self):
        ancestors = {"Q1": [entities.ANGIOSPERM, entities.ANIMALIA]}
        self.assertFalse(entities.candidate_matches_class("Q1", "双子葉", ancestors))


if __name__ == "__main__":
    unittest.main()
