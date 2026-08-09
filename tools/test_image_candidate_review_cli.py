#!/usr/bin/env python3
"""候補レビュー記録CLIと自治体適用CLIの専用テスト。"""

import csv
import json
import tempfile
import unittest
from pathlib import Path

import apply_reviewed_municipality_images as municipality
import set_image_candidate_review as review_cli
from apply_reviewed_school_images import IMAGE_PAGE_PREFIX, IMAGE_PREFIX, ManifestError


def candidate(name: str = "Town_Hall.jpg") -> dict:
    return {"image": IMAGE_PREFIX + name,
            "image_page": IMAGE_PAGE_PREFIX + name, "recommended": True}


def record(gid: str = "12", review: dict | None = None) -> dict:
    value = {"id": gid, "original": "例町", "wikidata": "Q123",
             "candidates": [candidate()]}
    if review is not None:
        value["review"] = review
    return value


def rows(image: str = "", image_page: str = "") -> list[dict]:
    return [
        {"id": "12", "surface": "例町", "wikidata": "Q123",
         "image": image, "image_page": image_page},
        {"id": "12", "surface": "例", "wikidata": "Q123",
         "image": image, "image_page": image_page},
    ]


class SetReviewTest(unittest.TestCase):
    def test_accept_requires_exact_candidate(self):
        with self.assertRaisesRegex(review_cli.ReviewError, "完全一致"):
            review_cli.set_review([record()], "12", "accepted",
                                  IMAGE_PAGE_PREFIX + "Other.jpg", None)
        with self.assertRaisesRegex(review_cli.ReviewError, "必要"):
            review_cli.set_review([record()], "12", "accepted", None, None)

    def test_rejected_clears_old_selection_and_records_note(self):
        values = [record(review={"status": "accepted",
                                 "selected_image_page": candidate()["image_page"]}),
                  record("13")]
        untouched = json.loads(json.dumps(values[1]))
        review_cli.set_review(values, "12", "rejected", None, "別施設")
        self.assertEqual({"status": "rejected", "note": "別施設"},
                         values[0]["review"])
        self.assertEqual(untouched, values[1])
        self.assertEqual([candidate()], values[0]["candidates"])

    def test_cli_atomically_writes_selected_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            values = [record(), record("13")]
            path.write_text("".join(json.dumps(v) + "\n" for v in values),
                            encoding="utf-8")
            result = review_cli.main([
                "school", "12", "accepted", "--manifest", str(path),
                "--selected-image-page", candidate()["image_page"],
                "--note", "建物確認",
            ])
            self.assertEqual(0, result)
            loaded = review_cli.load_records(path)
            self.assertEqual("accepted", loaded[0]["review"]["status"])
            self.assertEqual("建物確認", loaded[0]["review"]["note"])
            self.assertNotIn("review", loaded[1])


class ApplyMunicipalityTest(unittest.TestCase):
    def test_applies_to_every_surface(self):
        values = rows()
        accepted = {"12": ("Q123", candidate()["image"],
                           candidate()["image_page"])}
        self.assertEqual((1, 2, 0, 0), municipality.apply_accepted(
            values, accepted, Path("municipality.csv")))
        self.assertTrue(all(row["image"] == candidate()["image"] for row in values))

    def test_already_applied_to_every_surface_is_unchanged(self):
        values = rows(candidate()["image"], candidate()["image_page"])
        accepted = {"12": ("Q123", candidate()["image"],
                           candidate()["image_page"])}
        self.assertEqual((0, 0, 1, 2), municipality.apply_accepted(
            values, accepted, Path("municipality.csv")))

    def test_partial_or_mixed_application_is_protected(self):
        accepted = {"12": ("Q123", candidate()["image"],
                           candidate()["image_page"])}
        partial = rows(candidate()["image"], "")
        with self.assertRaisesRegex(ManifestError, "ため保護"):
            municipality.apply_accepted(partial, accepted,
                                        Path("municipality.csv"))
        mixed = rows()
        mixed[0]["image"] = candidate()["image"]
        mixed[0]["image_page"] = candidate()["image_page"]
        with self.assertRaisesRegex(ManifestError, "ため保護"):
            municipality.apply_accepted(mixed, accepted,
                                        Path("municipality.csv"))

    def test_qid_mismatch_and_existing_media_are_protected(self):
        accepted = {"12": ("Q999", candidate()["image"],
                           candidate()["image_page"])}
        with self.assertRaisesRegex(ManifestError, "QIDが台帳と不一致"):
            municipality.apply_accepted(rows(), accepted, Path("municipality.csv"))
        accepted["12"] = ("Q123", candidate()["image"], candidate()["image_page"])
        with self.assertRaisesRegex(ManifestError, "ため保護"):
            municipality.apply_accepted(
                rows(image=IMAGE_PREFIX + "Existing.jpg"), accepted,
                Path("municipality.csv"))

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "ledger.jsonl"
            accepted_review = {"status": "accepted",
                               "selected_image_page": candidate()["image_page"]}
            manifest.write_text(json.dumps(record(review=accepted_review)) + "\n",
                                encoding="utf-8")
            csv_path = root / "municipality.csv"
            columns = ["id", "surface", "wikidata", "image", "image_page"]
            with csv_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows())
            before = csv_path.read_bytes()
            result = municipality.main(["--manifest", str(manifest), "--csv",
                                        str(csv_path), "--dry-run"])
            self.assertEqual(0, result)
            self.assertEqual(before, csv_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
