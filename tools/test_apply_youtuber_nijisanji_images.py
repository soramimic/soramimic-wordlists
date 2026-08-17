import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_youtuber_nijisanji_images as nijisanji


FIELDS = [
    "id", "original", "surface", "pronunciation", "type", "category", "org",
    "debut_year", "status", "image", "image_page", "wikidata", "channel",
    "description", "subscribers", "subscribers_as_of", "image_credit",
    "image_usage", "image_terms_page",
]


class ApplyNijisanjiImagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.record = {
            "original": "テストライバー",
            "talent_status": "current",
            "image_url": (
                "https://images.microcms-assets.io/assets/"
                "5694fd90407444338a64d654e407cc0e/abc/test.png"
            ),
            "source_page": "https://www.nijisanji.jp/talents/l/test-liver",
            "credit": "にじさんじ公式立ち絵 © ANYCOLOR Inc.",
            "terms_page": nijisanji.TERMS_PAGE,
            "reviewed": "2026-08-17",
            "source_sha256": "1" * 64,
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
        path.write_bytes(path.read_bytes().rstrip(b"\n"))
        return path

    def base_row(self):
        row = {field: "NA" for field in FIELDS}
        row.update({
            "id": "1", "original": "テストライバー", "surface": "テストライバー",
            "pronunciation": "テストライバー", "type": "full", "category": "vtuber",
            "org": "にじさんじ", "debut_year": "2020", "status": "current",
            "image": nijisanji.CARD_PREFIX + "test.svg", "image_page": "old",
            "image_credit": "", "image_usage": "", "image_terms_page": "",
        })
        return row

    def test_updates_all_existing_rows(self):
        first = self.base_row()
        second = dict(first, type="given", surface="テスト")
        csv_path = self.write_csv([first, second])
        result = nijisanji.apply(csv_path, self.write_manifest())
        self.assertEqual(result, (1, 2))
        with csv_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertTrue(all(row["image"] == self.record["image_url"] for row in rows))
        self.assertTrue(all(row["image_usage"] == "noncommercial_fanwork" for row in rows))

    def test_rejects_unapproved_host(self):
        self.record["image_url"] = "https://example.com/test.png"
        with self.assertRaises(SystemExit):
            nijisanji.load_manifest(self.write_manifest())

    def test_rejects_missing_person(self):
        csv_path = self.write_csv([])
        with self.assertRaises(SystemExit):
            nijisanji.apply(csv_path, self.write_manifest())


if __name__ == "__main__":
    unittest.main()
