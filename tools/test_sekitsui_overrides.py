import csv
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote
from unittest import mock

import enrich_sekitsui_images
from enrich_sekitsui_images import manual_images
from sekitsui_overrides import (
    MANUAL_TAXONOMY,
    MANUAL_IMAGES,
    apply_manual_ranks,
    build_rank_class_maps,
    class_from_ranks,
)
from update_sekitsui import category_for


class SekitsuiOverridesTest(unittest.TestCase):
    def test_common_names_have_specific_images(self):
        self.assertTrue(
            {"モモンガ", "ヒト", "クマ", "ネコ", "イエイヌ", "ウシ", "ウマ",
             "ブタ", "ヒツジ", "ヤギ", "ウサギ", "ゾウ", "キリン", "サイ",
             "シカ", "キツネ", "カワウソ", "リス", "ビーバー", "モグラ",
             "ハリネズミ", "シロクマ", "オルカ", "ベルーガ", "アホロートル",
             "ナミチンパンジー", "ニワトリ", "ゴリラ", "パンダ", "イルカ",
             "クジラ", "オランウータン", "コウモリ", "カンガルー",
             "ナマケモノ", "アリクイ", "アルマジロ", "アザラシ",
             "オットセイ", "マナティー", "キーウィ", "ウナギ",
             "メダカ"}.issubset(MANUAL_IMAGES)
        )
        self.assertTrue(MANUAL_IMAGES["モモンガ"][1].endswith(".jpg"))

        records = manual_images()
        for name, (qid, filename) in MANUAL_IMAGES.items():
            self.assertEqual(records[name][0], qid)
            self.assertIn("Special:FilePath/", records[name][1])
            self.assertTrue(
                unquote(records[name][2]).endswith(filename.replace(" ", "_"))
            )

    def test_manual_only_replaces_class_image_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sekitsui.csv"
            columns = ["original", "image", "image_page", "wikidata"]
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerow({
                    "original": "ネコ",
                    "image": (
                        "https://github.com/soramimic/soramimic-wordlists/"
                        "releases/download/class-image-v1/class_mammal.svg"
                    ),
                    "image_page": "old",
                    "wikidata": "",
                })
            with mock.patch.object(enrich_sekitsui_images, "CSV_PATH", path), \
                 mock.patch.object(enrich_sekitsui_images, "fetch_images") as fetch:
                self.assertEqual(0, enrich_sekitsui_images.main(["--manual-only"]))
            fetch.assert_not_called()
            with path.open(encoding="utf-8", newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual("Q146", row["wikidata"])
            self.assertIn("Special:FilePath/Cat_grooming.jpg", row["image"])

    def test_manual_only_replaces_family_generated_image_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sekitsui.csv"
            columns = ["original", "image", "image_page", "wikidata"]
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerow({
                    "original": "ネコ",
                    "image": (
                        "https://raw.githubusercontent.com/soramimic/"
                        "soramimic-wordlists/main/images/sekitsui/"
                        "sekitsui_family_deadbeef0000_generated.webp"
                    ),
                    "image_page": "old",
                    "wikidata": "",
                })
            with mock.patch.object(enrich_sekitsui_images, "CSV_PATH", path), \
                 mock.patch.object(enrich_sekitsui_images, "fetch_images") as fetch:
                self.assertEqual(0, enrich_sekitsui_images.main(["--manual-only"]))
            fetch.assert_not_called()
            with path.open(encoding="utf-8", newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual("Q146", row["wikidata"])
            self.assertIn("Special:FilePath/Cat_grooming.jpg", row["image"])

    def test_refresh_manual_replaces_an_old_dedicated_image(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sekitsui.csv"
            columns = ["original", "image", "image_page", "wikidata"]
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerow({
                    "original": "イタチ",
                    "image": "https://example.test/old-mosaic.jpg",
                    "image_page": "https://example.test/old",
                    "wikidata": "Q28521",
                })
            with mock.patch.object(enrich_sekitsui_images, "CSV_PATH", path), \
                 mock.patch.object(enrich_sekitsui_images, "fetch_images") as fetch:
                self.assertEqual(0, enrich_sekitsui_images.main([
                    "--manual-only", "--refresh-manual",
                ]))
            fetch.assert_not_called()
            with path.open(encoding="utf-8", newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual("Q145201", row["wikidata"])
            self.assertIn("Mustela_nivalis", row["image"])

    def test_manual_class_fills_names_missing_from_species_query(self):
        self.assertEqual(category_for("モモンガ", {}), "哺乳類")
        self.assertEqual(category_for("ヒト", {}), "哺乳類")
        self.assertEqual(category_for("クマ", {}), "哺乳類")

    def test_manual_class_wins_over_incorrect_fetched_category(self):
        self.assertEqual(category_for("クマ", {"クマ": "魚類"}), "哺乳類")

    def test_fetched_class_is_used_for_other_names(self):
        self.assertEqual(category_for("ネコ", {"ネコ": "哺乳類"}), "哺乳類")

    def test_manual_ranks_restore_values_after_refresh(self):
        row = {"order": "", "family": ""}
        apply_manual_ranks("ヒト", row)
        self.assertEqual(row, {"order": "サル目", "family": "ヒト科"})

    def test_class_is_inferred_from_unambiguous_order_and_family(self):
        known = [
            {"class": "哺乳類", "order": "ネズミ目", "family": "リス科"},
            {"class": "哺乳類", "order": "ネズミ目", "family": "ネズミ科"},
        ]
        maps = build_rank_class_maps(known)
        self.assertEqual(
            class_from_ranks(
                {"class": "NA", "order": "ネズミ目", "family": "リス科"},
                maps,
            ),
            "哺乳類",
        )

    def test_conflicting_rank_evidence_is_not_used(self):
        maps = {
            "order": {"架空目": "哺乳類"},
            "family": {"架空科": "鳥類"},
        }
        self.assertIsNone(
            class_from_ranks(
                {"class": "NA", "order": "架空目", "family": "架空科"},
                maps,
            )
        )

    def test_common_mammal_names_have_full_taxonomy(self):
        self.assertEqual(
            MANUAL_TAXONOMY,
            {
                "モモンガ": {
                    "class": "哺乳類",
                    "order": "ネズミ目",
                    "family": "リス科",
                },
                "ヒト": {
                    "class": "哺乳類",
                    "order": "サル目",
                    "family": "ヒト科",
                },
                "クマ": {
                    "class": "哺乳類",
                    "order": "ネコ目",
                    "family": "クマ科",
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
