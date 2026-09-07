import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_vtuber_realize_images as realize
import validate_csvs as validator
from wpnames import write_csv_no_trailing_newline


class RealizeImagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.record = {
            "original": "テストライバー", "profile_id": 123, "enabled": True,
            "image_url": "https://realize-pro.com/wp-content/uploads/2026/09/test.png",
            "source_page": "https://realize-pro.com/talents/?open=123",
            "credit": "© Realize Production", "terms_page": realize.TERMS_PAGE,
            "reviewed": "2026-09-07", "source_sha256": "a" * 64,
        }
        self.row = {
            "id": "1", "original": "テストライバー", "surface": "テストライバー",
            "pronunciation": "テストライバー", "type": "full", "category": "vtuber",
            "org": realize.ORG, "status": "former", "scope": "japan",
            "image": realize.card_image_url("テストライバー"),
            "image_page": realize.card_page_url("テストライバー"),
            "image_credit": "", "image_usage": "", "image_terms_page": "",
        }

    def manifest(self, records=None):
        path = self.root / "images.json"
        path.write_text(json.dumps({
            "schema_version": 1, "images": records if records is not None else [self.record],
        }, ensure_ascii=False), encoding="utf-8")
        return path

    def csv_path(self, rows):
        path = self.root / "vtuber.csv"
        write_csv_no_trailing_newline(path, list(self.row), rows)
        return path

    def test_applies_all_name_parts_idempotently_and_preserves_other_fields(self):
        full = dict(self.row)
        part = dict(self.row, type="given", surface="テスト")
        other = dict(self.row, id="2", original="別の人", org="別の事務所")
        path = self.csv_path([full, part, other])
        manifest = self.manifest()
        self.assertEqual((1, 2), realize.apply(path, manifest))
        result = list(csv.DictReader(io.StringIO(path.read_text())))
        for before, after in zip([full, part], result):
            for key in before:
                if not key.startswith("image"):
                    self.assertEqual(before[key], after[key], key)
            self.assertEqual(self.record["image_url"], after["image"])
            self.assertEqual(realize.IMAGE_USAGE, after["image_usage"])
            self.assertEqual(self.record["credit"], after["image_credit"])
            self.assertEqual(self.record["terms_page"], after["image_terms_page"])
        self.assertEqual(other, result[2])
        first = path.read_bytes()
        self.assertEqual((0, 0), realize.apply(path, manifest))
        self.assertEqual(first, path.read_bytes())
        self.assertFalse(first.endswith(b"\n"))

    def test_inactive_image_is_retained_in_manifest_but_reverts_to_card(self):
        self.record["enabled"] = False
        manifest = self.manifest()
        self.assertEqual({}, realize.load_manifest(manifest))
        self.assertIn(self.record["original"], realize.load_manifest(manifest, include_inactive=True))
        row = dict(self.row, image=self.record["image_url"], image_usage=realize.IMAGE_USAGE,
                   image_credit=self.record["credit"], image_terms_page=realize.TERMS_PAGE)
        path = self.csv_path([row])
        self.assertEqual((1, 1), realize.apply(path, manifest))
        result = next(csv.DictReader(io.StringIO(path.read_text())))
        self.assertEqual(self.row, result)

    def test_rejects_mismatched_metadata(self):
        cases = [
            ("image_url", "https://realize-pro.com.example.org/wp-content/uploads/test.png"),
            ("source_page", "https://realize-pro.com/talents/?open=456"),
            ("terms_page", "https://example.org/terms/"),
            ("credit", ""), ("source_sha256", "invalid"), ("enabled", "false"),
        ]
        for key, value in cases:
            with self.subTest(field=key):
                with self.assertRaises(ValueError):
                    realize.load_manifest(self.manifest([dict(self.record, **{key: value})]))

    def test_person_conflicts_leave_csv_unchanged(self):
        manifest = self.manifest()
        for row in (dict(self.row, org="別の事務所"), dict(self.row, original="別の人")):
            with self.subTest(row=row):
                path = self.csv_path([row])
                original = path.read_bytes()
                with self.assertRaises(ValueError):
                    realize.apply(path, manifest)
                self.assertEqual(original, path.read_bytes())


class RealizeCsvValidationTests(unittest.TestCase):
    def setUp(self):
        with realize.CSV_PATH.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            self.fields = list(reader.fieldnames)
            self.rows = list(reader)
        self.addCleanup(validator.errors.clear)

    def validate(self, changes):
        rows = [dict(row) for row in self.rows]
        target = next(row for row in rows if row["original"] == "アイリス・ルセン")
        target.update(changes)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vtuber.csv"
            write_csv_no_trailing_newline(path, self.fields, rows)
            validator.errors.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                validator.validate(path)
        return list(validator.errors)

    def test_valid_data_and_image_metadata_mismatches(self):
        self.assertEqual([], self.validate({}))
        for changes in (
            {"image_credit": ""}, {"image_usage": ""},
            {"image_terms_page": "https://example.org/terms"},
            {"image_page": "https://realize-pro.com/talents/?open=8071"},
            {"original": "別のライバー"}, {"org": "別の事務所"},
        ):
            with self.subTest(changes=changes):
                self.assertTrue(any("りあぷろ公式画像" in error for error in self.validate(changes)))

    def test_inactive_portrait_is_not_accepted_by_csv_validator(self):
        records = realize.load_manifest(include_inactive=True)
        record = next(record for record in records.values() if not record["enabled"])
        errors = self.validate({"image": record["image_url"], "image_page": record["source_page"]})
        self.assertTrue(any("不正なURL" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
