#!/usr/bin/env python3
"""学校画像候補のレビュー保持と安全な適用のテスト。"""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from apply_reviewed_school_images import (
    IMAGE_PAGE_PREFIX,
    IMAGE_PREFIX,
    ManifestError,
    apply_accepted,
    load_manifest,
    main,
)
from apply_school_type_images import RAW_PREFIX
from collect_school_image_candidates import merge_review_state


def candidate(name: str = "Sample_School.jpg") -> dict:
    return {
        "image": IMAGE_PREFIX + name,
        "image_page": IMAGE_PAGE_PREFIX + name,
    }


def record(review: dict | None = None) -> dict:
    value = {
        "id": "12",
        "wikidata": "Q123",
        "candidates": [candidate()],
    }
    if review is not None:
        value["review"] = review
    return value


def school_rows(image: str | None = None) -> list[dict]:
    image = image if image is not None else RAW_PREFIX + "high_school.svg"
    return [
        {"id": "12", "surface": "例高校", "wikidata": "Q123",
         "image": image, "image_page": "placeholder-page"},
        {"id": "12", "surface": "例", "wikidata": "Q123",
         "image": image, "image_page": "placeholder-page"},
    ]


class ReviewPreservationTest(unittest.TestCase):
    def test_recollection_preserves_review(self):
        review = {"status": "accepted",
                  "selected_image_page": candidate()["image_page"], "note": "校舎確認"}
        fresh = [record()]
        merged = merge_review_state(fresh, [record(review)])
        self.assertEqual(review, merged[0]["review"])

    def test_reviewed_record_outside_new_targets_is_retained(self):
        old = record({"status": "rejected", "note": "別施設"})
        self.assertEqual([old], merge_review_state([], [old]))


class ManifestValidationTest(unittest.TestCase):
    def write_manifest(self, value: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "manifest.jsonl"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def test_manifest_without_review_is_compatible(self):
        self.assertEqual("12", load_manifest(self.write_manifest(record()))[0]["id"])

    def test_accepted_url_must_be_in_candidates(self):
        value = record({"status": "accepted",
                        "selected_image_page": IMAGE_PAGE_PREFIX + "Other.jpg"})
        with self.assertRaisesRegex(ManifestError, "候補に無い"):
            load_manifest(self.write_manifest(value))


class ApplyAcceptedTest(unittest.TestCase):
    def test_applies_to_every_surface_of_same_id(self):
        rows = school_rows()
        media = {"12": ("Q123", candidate()["image"], candidate()["image_page"])}
        self.assertEqual((1, 2, 0, 0),
                         apply_accepted(rows, media, Path("school.csv")))
        self.assertTrue(all(r["image"] == candidate()["image"] for r in rows))

    def test_already_applied_to_every_surface_is_unchanged(self):
        values = school_rows(candidate()["image"])
        for row in values:
            row["image_page"] = candidate()["image_page"]
        media = {"12": ("Q123", candidate()["image"], candidate()["image_page"])}
        self.assertEqual((0, 0, 1, 2),
                         apply_accepted(values, media, Path("school.csv")))

    def test_partially_applied_surfaces_are_protected(self):
        values = school_rows()
        values[0]["image"] = candidate()["image"]
        values[0]["image_page"] = candidate()["image_page"]
        media = {"12": ("Q123", candidate()["image"], candidate()["image_page"])}
        with self.assertRaisesRegex(ManifestError, "ため保護"):
            apply_accepted(values, media, Path("school.csv"))

    def test_qid_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ManifestError, "QIDが台帳と不一致"):
            apply_accepted(school_rows(),
                           {"12": ("Q999", candidate()["image"],
                                   candidate()["image_page"])}, Path("school.csv"))

    def test_existing_real_image_is_protected(self):
        rows = school_rows(IMAGE_PREFIX + "Existing.jpg")
        with self.assertRaisesRegex(ManifestError, "校種SVGではないため保護"):
            apply_accepted(rows,
                           {"12": ("Q123", candidate()["image"],
                                   candidate()["image_page"])}, Path("school.csv"))

    def test_dry_run_does_not_write_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.jsonl"
            manifest.write_text(json.dumps(record({
                "status": "accepted",
                "selected_image_page": candidate()["image_page"],
            })), encoding="utf-8")
            csv_path = root / "school.csv"
            cols = ["id", "surface", "wikidata", "image", "image_page"]
            with csv_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
                writer.writeheader()
                writer.writerows(school_rows())
            before = csv_path.read_bytes()
            self.assertEqual(0, main(["--manifest", str(manifest), "--csv",
                                      str(csv_path), "--dry-run"]))
            self.assertEqual(before, csv_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
