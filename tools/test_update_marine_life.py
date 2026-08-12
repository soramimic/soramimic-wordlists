import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_marine_life as marine


class MarineLifeUpdaterTest(unittest.TestCase):
    def source(self, rows):
        handle = io.StringIO(newline="")
        writer = csv.DictWriter(handle, fieldnames=marine.SOURCE_COLUMNS,
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return handle.getvalue().rstrip("\n").encode()

    def row(self, **changes):
        row = {
            "id": "0",
            "name": "クジラ",
            "class": "哺乳類",
            "vertebrate": "脊椎動物",
            "order": "鯨偶蹄目",
            "family": "ナガスクジラ科",
            "description": "海で暮らす大型の哺乳類で水面に浮上して呼吸する。",
            "wikidata": "Q42196",
            "scientific_name": "Balaenoptera musculus",
            "aphia_id": "137090",
            "jodc_code": "92010101010100",
            "image": "",
            "image_page": "",
            "image_group": "哺乳類",
        }
        row.update(changes)
        return row

    def load(self, *rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            path.write_bytes(self.source(rows))
            with mock.patch.dict(marine.MIN_CLASS_COUNTS, {key: 0 for key in marine.CLASSES}), \
                 mock.patch.object(marine, "MIN_QID_COUNT", 0), \
                 mock.patch.object(marine, "MIN_APHIA_COUNT", 0), \
                 mock.patch.object(marine, "MIN_JODC_COUNT", 0), \
                 mock.patch.object(marine, "MIN_TOTAL_COUNT", 0):
                return marine.load_source(path)

    def test_generate_has_filter_values_and_images(self):
        data = marine.generate(self.load(self.row())).decode()
        parsed = next(csv.DictReader(io.StringIO(data)))
        self.assertEqual("哺乳類", parsed["class"])
        self.assertEqual("脊椎動物", parsed["vertebrate"])
        self.assertTrue(parsed["image"].endswith("/marine_mammal.svg"))
        self.assertEqual(parsed["original"], parsed["pronunciation"])
        self.assertEqual("137090", parsed["aphia_id"])

    def test_explicit_commons_photo_overrides_fallback(self):
        row = self.row(
            image="https://upload.wikimedia.org/wikipedia/commons/a/ab/Blue_whale.jpg",
            image_page="https://commons.wikimedia.org/wiki/File:Blue_whale.jpg",
        )
        parsed = next(csv.DictReader(io.StringIO(marine.generate(self.load(row)).decode())))
        self.assertIn("Blue_whale.jpg", parsed["image"])

    def test_rejects_incomplete_photo_pair(self):
        with self.assertRaisesRegex(ValueError, "image/image_page mismatch"):
            self.load(self.row(image="https://upload.wikimedia.org/wikipedia/commons/a/ab/X.jpg"))

    def test_rejects_unknown_image_group(self):
        with self.assertRaisesRegex(ValueError, "invalid image group"):
            self.load(self.row(image_group="深海魚"))

    def test_image_source_manifest_matches_explicit_photo(self):
        row = self.row(
            image="https://upload.wikimedia.org/wikipedia/commons/a/ab/Blue_whale.jpg",
            image_page="https://commons.wikimedia.org/wiki/File:Blue_whale.jpg",
        )
        record = {
            "name": row["name"], "wikidata": row["wikidata"],
            "scientific_name": row["scientific_name"], "aphia_id": row["aphia_id"],
            "image": row["image"], "image_page": row["image_page"],
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "artist": "Example Photographer", "sha1": "a" * 40,
            "width": 640, "height": 480, "identification_basis": "QID and P18",
        }
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(marine, "MIN_PHOTO_COUNT", 0):
            path = Path(directory) / "images.jsonl"
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            marine.validate_image_sources([row], path)

    def test_image_source_manifest_rejects_unknown_license(self):
        row = self.row(
            image="https://upload.wikimedia.org/wikipedia/commons/a/ab/Blue_whale.jpg",
            image_page="https://commons.wikimedia.org/wiki/File:Blue_whale.jpg",
        )
        record = {
            "name": row["name"], "wikidata": row["wikidata"],
            "scientific_name": row["scientific_name"], "aphia_id": row["aphia_id"],
            "image": row["image"], "image_page": row["image_page"],
            "license": "unknown", "sha1": "a" * 40,
            "width": 640, "height": 480, "identification_basis": "QID and P18",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "images.jsonl"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported license"):
                marine.validate_image_sources([row], path)

    def test_rejects_duplicate_name(self):
        with self.assertRaisesRegex(ValueError, "duplicate name"):
            self.load(self.row(), self.row(id="1"))

    def test_rejects_duplicate_description(self):
        with self.assertRaisesRegex(ValueError, "duplicate description"):
            self.load(self.row(), self.row(id="1", name="イルカ"))

    def test_rejects_non_katakana_name(self):
        with self.assertRaisesRegex(ValueError, "not katakana"):
            self.load(self.row(name="海亀"))

    def test_rejects_class_hierarchy_mismatch(self):
        with self.assertRaisesRegex(ValueError, "class/vertebrate mismatch"):
            self.load(self.row(vertebrate="無脊椎動物"))

    def test_rejects_non_sequential_id(self):
        with self.assertRaisesRegex(ValueError, "append-only sequence"):
            self.load(self.row(id="4"))

    def test_rejects_bad_taxonomy_suffix(self):
        with self.assertRaisesRegex(ValueError, "order/family"):
            self.load(self.row(order="クジラ"))

    def test_rejects_extra_column(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            path.write_bytes(self.source([self.row()]) + b",extra")
            with self.assertRaisesRegex(ValueError, "number of columns"):
                marine.load_source(path)

    def test_rejects_class_below_minimum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            path.write_bytes(self.source([self.row()]))
            with mock.patch.object(marine, "MIN_QID_COUNT", 0):
                with self.assertRaisesRegex(ValueError, "too few"):
                    marine.load_source(path)

    def test_removed_names_detects_deletion(self):
        old = marine.generate([self.row(name="イルカ")])
        new = marine.generate([self.row(name="クジラ")])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "marine_life.csv"
            output.write_bytes(old)
            self.assertEqual({"イルカ"}, marine.removed_names(new, output))

    def test_write_atomic_replaces_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "marine_life.csv"
            output.write_bytes(b"old")
            marine.write_atomic(output, b"new")
            self.assertEqual(b"new", output.read_bytes())
            self.assertEqual([], list(output.parent.glob("*.tmp")))

    def test_check_does_not_rewrite_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "marine_life.csv"
            output.write_text("different", encoding="utf-8")
            with mock.patch.object(marine, "SOURCE", Path(directory) / "missing"), \
                 mock.patch.object(marine, "OUTPUT", output), \
                 mock.patch.object(marine, "load_source", return_value=[self.row()]), \
                 mock.patch.object(marine, "validate_images"), \
                 mock.patch.object(marine, "validate_image_sources"), \
                 mock.patch.object(marine, "validate_description_sources"):
                self.assertEqual(1, marine.main(["--check"]))
                self.assertEqual("different", output.read_text(encoding="utf-8"))

    def test_description_from_worms_traits(self):
        row = self.row(name="ハナミノカサゴ", family="フサカサゴ科")
        evidence = {
            "traits": [
                {"type": "maximum_length", "value": "38", "unit": "cm"},
                {"type": "iucn_status", "category": "Least Concern", "year": "2015"},
            ]
        }
        self.assertEqual(
            "ハナミノカサゴは最大体長約38センチ。IUCN評価は低懸念（2015年）。",
            marine.description_from_evidence(row, evidence),
        )

    def test_description_falls_back_to_verified_scientific_name(self):
        row = self.row(name="テストクジラ", scientific_name="Testus marinus")
        description = marine.description_from_evidence(row, {"traits": []})
        self.assertIn("Testus marinus", description)
        self.assertIn("WoRMS", description)
        self.assertGreaterEqual(len(description), 20)
        self.assertLessEqual(len(description), 60)

    def test_description_exposes_uncertain_worms_status(self):
        row = self.row(name="ハブクラゲ")
        evidence = {"status": "nomen dubium", "rank": "Species", "traits": []}
        self.assertEqual(
            "ハブクラゲはWoRMSで疑問名とされる海洋生物名である。",
            marine.description_from_evidence(row, evidence),
        )

    def test_description_source_manifest_reproduces_description(self):
        row = self.row(
            id="179", name="ハナミノカサゴ",
            order="カサゴ目", family="フサカサゴ科",
            scientific_name="Pterois volitans", aphia_id="159559",
        )
        row["class"] = "魚類"
        record = {
            "name": row["name"], "aphia_id": row["aphia_id"],
            "scientific_name": row["scientific_name"], "fetched_at": "2026-08-12",
            "record_url": "https://www.marinespecies.org/aphia.php?p=taxdetails&id=159559",
            "attributes_url": "https://www.marinespecies.org/rest/AphiaAttributesByAphiaID/159559",
            "status": "accepted", "rank": "Species", "is_marine": 1,
            "valid_aphia_id": 159559, "valid_name": "Pterois volitans",
            "traits": [{
                "type": "maximum_length", "value": "38", "unit": "cm",
                "source_id": 1, "reference": "Example source", "quality_status": "checked",
            }],
        }
        row["description"] = marine.description_from_evidence(row, record)
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(marine, "MIN_AUTO_DESCRIPTION_COUNT", 0):
            path = Path(directory) / "descriptions.jsonl"
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            marine.validate_description_sources([row], path)
            row["description"] = "根拠と一致しない説明文なので検査で拒否される。"
            with self.assertRaisesRegex(ValueError, "not generated from evidence"):
                marine.validate_description_sources([row], path)


if __name__ == "__main__":
    unittest.main()
