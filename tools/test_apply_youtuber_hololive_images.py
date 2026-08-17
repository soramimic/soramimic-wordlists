import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_youtuber_hololive_images as hololive


FIELDS = [
    "id", "original", "surface", "pronunciation", "type", "category", "org",
    "debut_year", "status", "image", "image_page", "wikidata", "channel",
    "description", "subscribers", "subscribers_as_of", "image_credit",
    "image_usage", "image_terms_page",
]


class ApplyHololiveImagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.record = {
            "original": "テストタレント",
            "talent_status": "graduated",
            "image_url": hololive.IMAGE_PREFIX + "2026/08/test.png",
            "source_page": "https://hololive.hololivepro.com/talents/test-talent/",
            "credit": "ホロライブプロダクション公式立ち絵 © COVER",
            "terms_page": hololive.TERMS_PAGE,
            "reviewed": "2026-08-17",
            "source_sha256": "1" * 64,
            "fallback_rows": [],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def write_manifest(self, record=None):
        path = self.root / "manifest.json"
        path.write_text(
            json.dumps({"images": [record or self.record]}, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def write_csv(self, rows):
        path = self.root / "youtuber.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        data = path.read_bytes()
        path.write_bytes(data.rstrip(b"\n"))
        return path

    def base_row(self):
        row = {field: "NA" for field in FIELDS}
        row.update({
            "id": "1", "original": "テストタレント", "surface": "テストタレント",
            "pronunciation": "テストタレント", "type": "full", "category": "vtuber",
            "org": "ホロライブ", "debut_year": "2020", "status": "current",
            "image": hololive.CARD_PREFIX + "test.svg", "image_page": "old",
            "image_credit": "", "image_usage": "", "image_terms_page": "",
        })
        return row

    def test_updates_existing_rows_and_status(self):
        csv_path = self.write_csv([self.base_row()])
        result = hololive.apply(csv_path, self.write_manifest())
        self.assertEqual(result, (1, 1, 0))
        with csv_path.open(encoding="utf-8", newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(row["image"], self.record["image_url"])
        self.assertEqual(row["image_usage"], "noncommercial_fanwork")
        self.assertEqual(row["status"], "former")

    def test_adds_reviewed_fallback_row(self):
        fallback = {key: self.base_row()[key] for key in hololive.FALLBACK_COLUMNS}
        self.record["fallback_rows"] = [fallback]
        csv_path = self.write_csv([])
        result = hololive.apply(csv_path, self.write_manifest())
        self.assertEqual(result, (1, 1, 1))

    def test_rejects_unapproved_host(self):
        self.record["image_url"] = "https://example.com/test.png"
        with self.assertRaises(SystemExit):
            hololive.load_manifest(self.write_manifest())

    def test_rejects_duplicate_fallback_id(self):
        fallback = {key: self.base_row()[key] for key in hololive.FALLBACK_COLUMNS}
        self.record["fallback_rows"] = [fallback, fallback]
        with self.assertRaises(SystemExit):
            hololive.load_manifest(self.write_manifest())


if __name__ == "__main__":
    unittest.main()
