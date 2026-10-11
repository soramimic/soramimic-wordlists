import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_sekitsui_taxonomy as enrich
import sekitsui_taxonomy_sources as sources


class TaxonomyCompletionTest(unittest.TestCase):
    def run_enrichment(self, row, resolved, refresh=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "list.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            with mock.patch.object(enrich, "CSV_PATH", path), \
                 mock.patch.object(enrich, "MIN_TOTAL", 0), \
                 mock.patch.object(enrich, "apply_sources"), \
                 mock.patch.object(enrich.tx, "load_cache", return_value={"nodes": {}, "labels": {}}), \
                 mock.patch.object(enrich.tx, "resolve_names"), \
                 mock.patch.object(enrich.tx, "crawl"), \
                 mock.patch.object(enrich.tx, "add_rank_aliases"), \
                 mock.patch.object(enrich.tx, "resolve", return_value=resolved) as resolve:
                self.assertEqual(0, enrich.main(["enrich", *(["--refresh"] if refresh else [])]))
            with path.open(encoding="utf-8", newline="") as stream:
                result = next(csv.DictReader(stream))
            return result, resolve.call_count

    def test_partial_row_is_completed_without_overwriting_known_order(self):
        row = {"id": "1", "original": "fixture", "class": "鳥類", "extinct": "no",
               "order": "スズメ目", "family": "", "wikidata": "Q123", "extra": "keep"}
        result, calls = self.run_enrichment(row, ["別の目", "ツバメ科"])
        self.assertEqual(1, calls)
        self.assertEqual("スズメ目", result["order"])
        self.assertEqual("ツバメ科", result["family"])
        self.assertEqual("keep", result["extra"])

    def test_refresh_never_erases_known_rank_when_fetch_is_incomplete(self):
        row = {"id": "1", "original": "fixture", "class": "鳥類", "extinct": "no",
               "order": "スズメ目", "family": "ツバメ科", "wikidata": "Q123"}
        result, calls = self.run_enrichment(row, ["", ""], refresh=True)
        self.assertEqual(1, calls)
        self.assertEqual(row, result)

    def test_complete_row_is_not_refetched(self):
        row = {"id": "1", "original": "fixture", "class": "鳥類", "extinct": "no",
               "order": "スズメ目", "family": "ツバメ科", "wikidata": "Q123"}
        result, calls = self.run_enrichment(row, ["別の目", "別の科"])
        self.assertEqual(0, calls)
        self.assertEqual(row, result)


class ReviewedTaxonomyTest(unittest.TestCase):
    def test_verified_supplements_preserve_existing_values_and_identity(self):
        records = {"ヤモリ": {"id": "3984", "values": {
            "class": "爬虫類", "order": "有鱗目", "family": "ヤモリ科",
        }}}
        rows = [
            {"id": "3984", "original": "ヤモリ", "class": "NA", "order": "手動目", "family": ""},
            {"id": "999", "original": "ヤモリ", "class": "NA", "order": "", "family": ""},
        ]
        self.assertEqual(2, sources.apply_sources(rows, records))
        self.assertEqual("手動目", rows[0]["order"])
        self.assertEqual("ヤモリ科", rows[0]["family"])
        self.assertEqual("NA", rows[1]["class"])
        self.assertEqual(0, sources.apply_sources(rows, records))

    def test_source_ledger_is_valid_and_covers_gecko(self):
        records = sources.load_sources()
        self.assertEqual("爬虫類", records["ヤモリ"]["values"]["class"])
        self.assertEqual("ヤモリ科", records["ヤモリ"]["values"]["family"])

    def test_common_names_spanning_families_do_not_claim_one_family(self):
        records = sources.load_sources()
        for name in ("クジラ", "ネズミ", "パンダ", "ヤマアラシ"):
            self.assertNotIn("family", records[name]["values"])


if __name__ == "__main__":
    unittest.main()
