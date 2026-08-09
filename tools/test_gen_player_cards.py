import csv
import tempfile
import unittest
from pathlib import Path

import gen_player_cards as target


class PlayerCardIdentityTests(unittest.TestCase):
    def test_same_display_name_with_different_qids_keeps_missing_photo_card(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "football.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "id", "original", "wikidata", "team", "category", "image",
                ])
                writer.writeheader()
                writer.writerows([
                    {"id": "1", "original": "同名 選手", "wikidata": "Q1",
                     "team": "クラブA", "category": "player",
                     "image": "https://commons.wikimedia.org/photo.jpg"},
                    {"id": "2", "original": "同名 選手", "wikidata": "Q2",
                     "team": "クラブB", "category": "player", "image": ""},
                ])
            original_root = target.ROOT
            try:
                target.ROOT = root
                people, photos = target.load_people(target.LISTS["football"])
            finally:
                target.ROOT = original_root
        self.assertEqual(1, photos)
        self.assertEqual(1, len(people))
        name, team, _silhouette, seed = people[0]
        self.assertEqual("同名 選手", name)
        self.assertEqual("クラブB", team)
        self.assertEqual("同名 選手\0Q2", seed)


if __name__ == "__main__":
    unittest.main()
