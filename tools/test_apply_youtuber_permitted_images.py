import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_youtuber_permitted_images as permitted


class PermittedImagesTest(unittest.TestCase):
    def setUp(self):
        data = json.loads(permitted.MANIFEST_PATH.read_text(encoding="utf-8"))
        self.record = data["images"][0].copy()

    def write_manifest(self, record=None):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", delete=False)
        with tmp:
            json.dump({"images": [] if record is None else [record]}, tmp,
                      ensure_ascii=False)
        self.addCleanup(Path(tmp.name).unlink, missing_ok=True)
        return Path(tmp.name)

    def write_csv(self, image):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".csv", newline="", delete=False)
        fields = [
            "id", "original", "surface", "category", "org", "status",
            "image", "image_page",
        ]
        with tmp:
            writer = csv.DictWriter(tmp, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerow({
                "id": "1", "original": self.record["original"],
                "surface": self.record["original"], "category": "vtuber",
                "org": self.record["organization"], "status": "current", "image": image,
                "image_page": "old",
            })
        self.addCleanup(Path(tmp.name).unlink, missing_ok=True)
        return Path(tmp.name)

    def test_repository_manifest_disables_reviewed_images(self):
        self.assertEqual({}, permitted.load_manifest())

    def test_applies_only_to_card_and_adds_credit(self):
        csv_path = self.write_csv(permitted.CARD_PREFIX + "old.svg")
        people, rows = permitted.apply(csv_path, self.write_manifest(self.record))
        self.assertEqual((1, 1), (people, rows))
        with csv_path.open(encoding="utf-8", newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(permitted.IMAGE_PREFIX + self.record["file"], row["image"])
        self.assertEqual(self.record["source_page"], row["image_page"])
        self.assertEqual(self.record["credit"], row["image_credit"])
        self.assertEqual("noncommercial_fanwork", row["image_usage"])
        self.assertEqual(self.record["guideline_url"], row["image_terms_page"])
        self.assertEqual((0, 0), permitted.apply(
            csv_path, self.write_manifest(self.record)))

    def test_removed_manifest_entry_restores_symbolic_card(self):
        image = permitted.IMAGE_PREFIX + self.record["file"]
        csv_path = self.write_csv(image)
        people, rows = permitted.apply(csv_path, self.write_manifest())
        self.assertEqual((1, 1), (people, rows))
        with csv_path.open(encoding="utf-8", newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(permitted.card_image_url(self.record["original"]), row["image"])
        self.assertEqual("", row["image_credit"])
        self.assertEqual("", row["image_usage"])
        self.assertEqual("", row["image_terms_page"])

    def test_refuses_to_replace_non_card_image(self):
        csv_path = self.write_csv("https://commons.wikimedia.org/example.jpg")
        with self.assertRaises(SystemExit):
            permitted.apply(csv_path, self.write_manifest(self.record))

    def test_rejects_unapproved_organization(self):
        self.record["organization"] = "未確認事務所"
        with self.assertRaises(SystemExit):
            permitted.load_manifest(self.write_manifest(self.record))

    def test_rejects_asset_hash_mismatch(self):
        self.record["sha256"] = "0" * 64
        with self.assertRaises(SystemExit):
            permitted.load_manifest(self.write_manifest(self.record))

    def test_rejects_invalid_source_hash(self):
        self.record["source_sha256"] = "reviewed"
        with self.assertRaises(SystemExit):
            permitted.load_manifest(self.write_manifest(self.record))

    def test_rejects_former_talent(self):
        csv_path = self.write_csv(permitted.CARD_PREFIX + "old.svg")
        text = csv_path.read_text(encoding="utf-8").replace(
            ",current,", ",former,")
        csv_path.write_text(text, encoding="utf-8")
        with self.assertRaises(SystemExit):
            permitted.apply(csv_path, self.write_manifest(self.record))


if __name__ == "__main__":
    unittest.main()
