import json
import tempfile
import unittest
from pathlib import Path

import apply_plant_generated_images as generated


def record(status="accepted", qid="Q104779", name="バラ科"):
    return {"scope": "family", "name": name, "family_qid": qid,
            "filename": "plant_family_q104779_generated.webp",
            "accepted": status == "accepted",
            "qc": {"status": status}}


class ApplyPlantGeneratedImagesTest(unittest.TestCase):
    def test_replaces_class_image_but_preserves_photo(self):
        rows = [
            {"family": "バラ科", "family_wikidata": "Q104779", "class": "双子葉",
             "image": "https://github.com/soramimic/soramimic-wordlists/releases/"
                      "download/class-image-v1/class_dicot.svg", "image_page": "old"},
            {"family": "バラ科", "family_wikidata": "Q104779", "class": "双子葉",
             "image": "https://commons.wikimedia.org/photo.jpg", "image_page": "photo"},
        ]
        rendered, changed = generated.render(rows, [record()])
        self.assertEqual(1, changed)
        self.assertTrue(rendered[0]["image"].endswith("plant_family_q104779_generated.webp"))
        self.assertEqual("photo", rendered[1]["image_page"])

    def test_only_accepted_manifest_records_are_assigned(self):
        row = {"family": "バラ科", "family_wikidata": "Q104779", "class": "双子葉",
               "image": "https://github.com/soramimic/soramimic-wordlists/releases/"
                        "download/class-image-v1/class_dicot.svg", "image_page": "old"}
        rendered, changed = generated.render([row], [record("rejected")])
        self.assertEqual(0, changed)
        self.assertIn("class-image-v1", rendered[0]["image"])

    def test_unresolved_stale_generated_image_returns_to_class_svg(self):
        row = {"family": "", "family_wikidata": "", "class": "双子葉",
               "image": generated.GENERATED_PREFIX + "q1_generated.webp", "image_page": "old"}
        rendered, changed = generated.render([row], [])
        self.assertEqual(1, changed)
        self.assertIn("class-image-v1", rendered[0]["image"])

    def test_qid_name_mismatch_is_not_assigned(self):
        row = {"family": "別科", "family_wikidata": "Q104779", "class": "双子葉",
               "image": "https://github.com/soramimic/soramimic-wordlists/releases/"
                        "download/class-image-v1/class_dicot.svg", "image_page": "old"}
        _, changed = generated.render([row], [record()])
        self.assertEqual(0, changed)

    def test_manifest_rejects_conflicting_qids_for_same_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps([record(), record(qid="Q2")]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "conflicting family QIDs"):
                generated.load_manifest(path)


if __name__ == "__main__":
    unittest.main()
