#!/usr/bin/env python3
"""自治体Commons候補収集のネットワーク不要テスト。"""

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import collect_municipality_image_candidates as target


def commons_page(filename: str, license_name: str = "CC BY-SA 4.0",
                 width: int = 1200, height: int = 800,
                 mime: str = "image/jpeg") -> dict:
    return {
        "title": "File:" + filename,
        "imageinfo": [{
            "mime": mime, "width": width, "height": height,
            "extmetadata": {
                "LicenseShortName": {"value": license_name},
                "Artist": {"value": "<b>Example Photographer</b>"},
                "ImageDescription": {"value": "<p>Municipal building</p>"},
            },
        }],
    }


class LoadTargetsTest(unittest.TestCase):
    def test_only_groups_with_no_image_are_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "municipality.csv"
            cols = ["id", "original", "surface", "prefecture", "parent",
                    "status", "image", "wikidata"]
            rows = [
                ["1", "例市", "例市", "例県", "", "current", "", "Q1"],
                ["1", "例市", "例", "例県", "", "current", "", "Q1"],
                ["2", "写真町", "写真町", "例県", "", "former",
                 "http://commons.wikimedia.org/wiki/Special:FilePath/Photo.jpg", "Q2"],
                ["2", "写真町", "写真", "例県", "", "former", "", "Q2"],
            ]
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh, lineterminator="\n")
                writer.writerow(cols)
                writer.writerows(rows)
            found = target.load_targets(path)
            self.assertEqual(["Q1"], list(found))
            self.assertEqual("例市", found["Q1"]["original"])


class CategoryCandidatesTest(unittest.TestCase):
    def test_filters_symbols_maps_people_and_nonfree_files(self):
        response = {"query": {"pages": [
            commons_page("Example City Hall.jpg"),
            commons_page("Example city locator map.svg"),
            commons_page("Portrait of Example mayor.jpg"),
            commons_page("Example town hall small.jpg", width=320, height=200),
            commons_page("Copyrighted cityscape.jpg", license_name="Copyrighted"),
            commons_page("Example vector.svg", mime="image/svg+xml"),
        ]}}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(target, "CATEGORY_CACHE", Path(directory)), \
                patch.object(target, "request_json", return_value=response), \
                patch.object(target.time, "sleep"):
            candidates = target.category_candidates("Example", 20, refresh=True)
        self.assertEqual(
            ["Example City Hall.jpg", "Example town hall small.jpg"],
            [c["file"] for c in candidates],
        )
        self.assertTrue(candidates[0]["recommended"])
        self.assertFalse(candidates[1]["recommended"])
        self.assertEqual("CC BY-SA 4.0", candidates[0]["license"])
        self.assertEqual("Example Photographer", candidates[0]["artist"])
        self.assertEqual((1200, 800),
                         (candidates[0]["width"], candidates[0]["height"]))
        self.assertTrue(candidates[0]["image_page"].startswith(
            "https://commons.wikimedia.org/wiki/File:"))

    def test_cache_is_used_without_network_and_output_is_sorted(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            response = {"query": {"pages": [
                commons_page("Z City Hall.jpg"),
                commons_page("A City Hall.jpg"),
            ]}}
            with patch.object(target, "CATEGORY_CACHE", cache), \
                    patch.object(target, "request_json", return_value=response) as request, \
                    patch.object(target.time, "sleep"):
                first = target.category_candidates("Example", 20, refresh=True)
                second = target.category_candidates("Example", 20, refresh=False)
            self.assertEqual(first, second)
            self.assertEqual(["A City Hall.jpg", "Z City Hall.jpg"],
                             [c["file"] for c in second])
            self.assertEqual(1, request.call_count)


class ReviewPreservationTest(unittest.TestCase):
    def test_main_preserves_existing_review(self):
        candidate = {
            "file": "Example City Hall.jpg",
            "image": "http://commons.wikimedia.org/wiki/Special:FilePath/Example_City_Hall.jpg",
            "image_page": "https://commons.wikimedia.org/wiki/File:Example_City_Hall.jpg",
            "recommended": True,
        }
        municipality = {
            "id": "1", "original": "例市", "prefecture": "例県", "parent": "",
            "status": "current", "wikidata": "Q1", "has_image": False,
        }
        review = {"status": "accepted",
                  "selected_image_page": candidate["image_page"], "note": "庁舎確認"}
        old = dict(municipality, commons_category="Example", candidates=[candidate],
                   review=review)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "candidates.jsonl"
            out.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
            with patch.object(target, "load_targets", return_value={"Q1": municipality}), \
                    patch.object(target, "p373_for_qids", return_value={"Q1": "Example"}), \
                    patch.object(target, "category_candidates", return_value=[candidate]):
                self.assertEqual(0, target.main(["--out", str(out)]))
            refreshed = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(review, refreshed["review"])


if __name__ == "__main__":
    unittest.main()
