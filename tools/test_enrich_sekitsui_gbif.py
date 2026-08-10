import csv
import io
import json
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import enrich_sekitsui_gbif as gbif


def result(
    name="ニホンアマガエル",
    language="jpn",
    kingdom="Animalia",
    phylum="Chordata",
    class_name="Amphibia",
    order="Anura",
    family="Hylidae",
):
    return {
        "kingdom": kingdom,
        "phylum": phylum,
        "class": class_name,
        "order": order,
        "family": family,
        "vernacularNames": [{"vernacularName": name, "language": language}],
    }


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class GbifCandidateTest(unittest.TestCase):
    def test_primary_classes_map_to_existing_japanese_categories(self):
        self.assertEqual("哺乳類", gbif.CLASS_MAP["Mammalia"])
        self.assertEqual("鳥類", gbif.CLASS_MAP["Aves"])
        self.assertEqual("爬虫類", gbif.CLASS_MAP["Reptilia"])
        self.assertEqual("両生類", gbif.CLASS_MAP["Amphibia"])
        for fish_class in ("Actinopterygii", "Chondrichthyes", "Myxini"):
            self.assertEqual("魚類", gbif.CLASS_MAP[fish_class])

    def test_only_exact_japanese_chordate_animal_candidates_are_eligible(self):
        valid = result()
        results = [
            valid,
            result(name="アマガエル"),
            result(language="eng"),
            result(kingdom="Plantae"),
            result(phylum="Arthropoda"),
        ]
        self.assertEqual(
            [{"class": "Amphibia", "order": "Anura", "family": "Hylidae"}],
            gbif.eligible_candidates("ニホンアマガエル", results),
        )

    def test_conflicting_exact_candidates_are_rejected(self):
        candidates = gbif.eligible_candidates(
            "同名",
            [result(name="同名"), result(name="同名", family="Ranidae")],
        )
        self.assertIsNone(gbif.resolve_candidates(candidates))

    def test_missing_values_do_not_conflict_with_a_known_value(self):
        resolved = gbif.resolve_candidates([
            {"class": "Aves", "order": "", "family": ""},
            {"class": "Aves", "order": "Passeriformes", "family": "Corvidae"},
        ])
        self.assertEqual(
            {"class": "Aves", "order": "Passeriformes", "family": "Corvidae"},
            resolved,
        )

    def test_fills_only_missing_values_and_maps_fish_class(self):
        rows = [{
            "original": "サンプル魚", "class": "NA",
            "order": "既存目", "family": "",
        }]
        cache = {"サンプル魚": [{
            "class": "Actinopterygii", "order": "Perciformes",
            "family": "Scombridae",
        }]}
        self.assertEqual((1, 0), gbif.enrich_rows(rows, cache))
        self.assertEqual("魚類", rows[0]["class"])
        self.assertEqual("既存目", rows[0]["order"])
        self.assertEqual("Scombridae", rows[0]["family"])

    def test_retry_then_success_without_network(self):
        calls = []

        def opener(_request, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise urllib.error.HTTPError("url", 503, "busy", {}, None)
            return Response(json.dumps({"results": [result()]}).encode())

        sleeps = []
        candidates = gbif.fetch_candidates(
            "ニホンアマガエル", opener=opener, sleeper=sleeps.append
        )
        self.assertEqual(2, len(calls))
        self.assertEqual([1], sleeps)
        self.assertEqual("Hylidae", candidates[0]["family"])


class GbifCliTest(unittest.TestCase):
    def write_csv(self, path: Path):
        columns = ["id", "original", "class", "order", "family", "extra"]
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerow({
                "id": "1", "original": "ニホンアマガエル", "class": "NA",
                "order": "", "family": "", "extra": "keep",
            })

    def test_dry_run_populates_cache_but_preserves_csv_and_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "sekitsui.csv"
            cache_path = root / "cache.json"
            self.write_csv(csv_path)
            before = csv_path.read_bytes()
            candidates = [{
                "class": "Amphibia", "order": "Anura", "family": "Hylidae",
            }]
            with mock.patch.object(gbif, "fetch_candidates", return_value=candidates):
                self.assertEqual(0, gbif.main([
                    "--csv", str(csv_path), "--cache", str(cache_path),
                    "--limit", "1", "--dry-run", "--delay", "0",
                ]))
            self.assertEqual(before, csv_path.read_bytes())
            self.assertEqual(candidates, json.loads(cache_path.read_text())["ニホンアマガエル"])

    def test_cached_result_updates_csv_without_network_and_keeps_extra_column(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "sekitsui.csv"
            cache_path = root / "cache.json"
            self.write_csv(csv_path)
            gbif.save_cache(cache_path, {"ニホンアマガエル": [{
                "class": "Amphibia", "order": "Anura", "family": "Hylidae",
            }]})
            with mock.patch.object(gbif, "fetch_candidates") as fetch:
                self.assertEqual(0, gbif.main([
                    "--csv", str(csv_path), "--cache", str(cache_path),
                    "--delay", "0",
                ]))
            fetch.assert_not_called()
            with csv_path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
                self.assertEqual(
                    ["id", "original", "class", "order", "family", "extra"],
                    reader.fieldnames,
                )
            self.assertEqual("両生類", rows[0]["class"])
            self.assertEqual("Anura", rows[0]["order"])
            self.assertEqual("Hylidae", rows[0]["family"])
            self.assertEqual("keep", rows[0]["extra"])

    def test_workers_fetch_concurrently_but_cache_on_main_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "sekitsui.csv"
            cache_path = root / "cache.json"
            columns = ["id", "original", "class", "order", "family"]
            names = ["和名A", "和名B", "和名C"]
            with csv_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                for index, name in enumerate(names):
                    writer.writerow({"id": index, "original": name, "class": "NA"})

            barrier = threading.Barrier(3)
            worker_threads = set()
            main_thread = threading.get_ident()
            save_threads = []
            real_save = gbif.save_cache

            def fetch(_name):
                worker_threads.add(threading.get_ident())
                barrier.wait(timeout=2)
                return [{"class": "Aves", "order": "Passeriformes",
                         "family": "Corvidae"}]

            def save(path, cache):
                save_threads.append(threading.get_ident())
                real_save(path, cache)

            with (
                mock.patch.object(gbif, "fetch_candidates", side_effect=fetch),
                mock.patch.object(gbif, "save_cache", side_effect=save),
            ):
                self.assertEqual(0, gbif.main([
                    "--csv", str(csv_path), "--cache", str(cache_path),
                    "--workers", "3", "--delay", "0", "--dry-run",
                ]))

            self.assertEqual(3, len(worker_threads))
            self.assertEqual([main_thread] * 3, save_threads)
            self.assertEqual(set(names), set(json.loads(cache_path.read_text())))


if __name__ == "__main__":
    unittest.main()
