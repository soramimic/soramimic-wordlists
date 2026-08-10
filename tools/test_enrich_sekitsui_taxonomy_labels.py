import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import enrich_sekitsui_taxonomy_labels as labels
import taxonomy


def binding(qid, scientific_name, rank, *, ja=None, alt=None):
    item = {
        "t": {"value": f"http://www.wikidata.org/entity/{qid}"},
        "sci": {"value": scientific_name},
        "rank": {"value": f"http://www.wikidata.org/entity/{rank}"},
    }
    if ja is not None:
        item["ja"] = {"value": ja}
    if alt is not None:
        item["alt"] = {"value": alt}
    return item


class ScientificTaxaQueryTest(unittest.TestCase):
    def test_batches_p225_and_p105_and_keeps_distinct_qid_candidates(self):
        payload = {"results": {"bindings": [
            binding("Q1", "Anura", taxonomy.ORDER, ja="無尾目"),
            binding("Q1", "Anura", taxonomy.ORDER, ja="無尾目", alt="カエル目"),
            binding("Q2", "Anura", taxonomy.ORDER, ja="カエル目"),
        ]}}
        with mock.patch.object(taxonomy, "sparql_post", return_value=payload) as post:
            got = taxonomy.fetch_scientific_taxa([
                ("Anura", taxonomy.ORDER),
                ("Hylidae", taxonomy.FAMILY),
            ])

        query = post.call_args.args[0]
        self.assertIn("VALUES (?sci ?rank)", query)
        self.assertIn("wdt:P225 ?sci ; wdt:P105 ?rank", query)
        self.assertIn('(\"Anura\" wd:Q36602)', query)
        self.assertEqual(2, len(got[("Anura", taxonomy.ORDER)]))
        self.assertEqual(["カエル目"], got[("Anura", taxonomy.ORDER)][0]["alts"])
        self.assertEqual([], got[("Hylidae", taxonomy.FAMILY)])


class LabelResolutionTest(unittest.TestCase):
    def test_ranked_label_wins_over_ranked_alt(self):
        candidate = {"ja": "ネズミ目", "alts": ["齧歯目"]}
        self.assertEqual("ネズミ目", labels.candidate_label(candidate, "目"))

    def test_ranked_alt_wins_when_label_has_no_rank_suffix(self):
        candidate = {"ja": "オオコウモリ", "alts": ["オオコウモリ科"]}
        self.assertEqual("オオコウモリ科", labels.candidate_label(candidate, "科"))

    def test_plain_japanese_label_is_last_fallback(self):
        candidate = {"ja": "翼手類", "alts": ["Chiroptera"]}
        self.assertEqual("翼手類", labels.candidate_label(candidate, "目"))

    def test_conflicting_wikidata_items_are_not_applied(self):
        candidates = [
            {"qid": "Q1", "ja": "ネズミ目", "alts": []},
            {"qid": "Q2", "ja": "齧歯目", "alts": []},
        ]
        self.assertEqual("", labels.resolve_label(candidates, "目"))

    def test_only_a_whole_latin_uninomial_is_a_scientific_name(self):
        self.assertEqual("Pteropodidae", labels.scientific_name(" Pteropodidae "))
        self.assertEqual("", labels.scientific_name("既存のオオコウモリ科"))
        self.assertEqual("", labels.scientific_name("family Pteropodidae"))
        self.assertEqual("", labels.scientific_name("NA"))


class CachedCliTest(unittest.TestCase):
    def test_cached_results_replace_only_latin_cells_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "sekitsui.csv"
            cache_path = root / "cache.json"
            columns = ["id", "original", "order", "family", "extra"]
            with csv_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerow({
                    "id": "1", "original": "オオコウモリ", "order": "翼手目",
                    "family": "Pteropodidae", "extra": "keep",
                })
                writer.writerow({
                    "id": "2", "original": "別種", "order": "Chiroptera",
                    "family": "既存科", "extra": "keep2",
                })
            labels.save_cache(cache_path, {
                labels.cache_key("Pteropodidae", taxonomy.FAMILY): "オオコウモリ科",
                labels.cache_key("Chiroptera", taxonomy.ORDER): "翼手目",
            })

            with mock.patch.object(labels, "fetch_scientific_taxa") as fetch:
                self.assertEqual(0, labels.main([
                    "--csv", str(csv_path), "--cache", str(cache_path),
                ]))
            fetch.assert_not_called()

            with csv_path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual("翼手目", rows[0]["order"])
            self.assertEqual("オオコウモリ科", rows[0]["family"])
            self.assertEqual("翼手目", rows[1]["order"])
            self.assertEqual("既存科", rows[1]["family"])
            self.assertEqual("keep2", rows[1]["extra"])

    def test_fetch_populates_cache_for_offline_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "cache.json"
            cache = {}
            candidates = {
                ("Rodentia", taxonomy.ORDER): [
                    {"qid": "Q1", "ja": "ネズミ目", "alts": ["齧歯目"]},
                ],
            }
            with mock.patch.object(labels, "fetch_scientific_taxa", return_value=candidates):
                labels.fetch_all(
                    [("Rodentia", taxonomy.ORDER)], cache, cache_path,
                    sleeper=lambda _seconds: None,
                )
            self.assertEqual(
                "ネズミ目",
                labels.load_cache(cache_path)[labels.cache_key("Rodentia", taxonomy.ORDER)],
            )


if __name__ == "__main__":
    unittest.main()
