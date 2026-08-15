import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_plant_images import needs_photo


class EnrichPlantImagesTest(unittest.TestCase):
    def test_only_non_photo_rows_with_qid_are_eligible(self):
        class_url = (
            "https://github.com/soramimic/soramimic-wordlists/"
            "releases/download/class-image-v1/class_dicot.svg"
        )
        generated_url = (
            "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/"
            "main/images/plant/plant_family_q1_generated.webp"
        )
        self.assertTrue(needs_photo({"wikidata": "Q1", "image": ""}))
        self.assertTrue(needs_photo({"wikidata": "Q1", "image": class_url}))
        self.assertTrue(needs_photo({"wikidata": "Q1", "image": generated_url}))
        self.assertFalse(needs_photo({"wikidata": "Q1", "image": "https://commons/photo.jpg"}))
        self.assertFalse(needs_photo({"wikidata": "", "image": generated_url}))


if __name__ == "__main__":
    unittest.main()
