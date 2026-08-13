import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_myoji_official_web as a


class CandidateTest(unittest.TestCase):
    def test_batch_name_supports_multiple_runs_per_day(self):
        self.assertEqual(
            a.candidates_path("2026-08-13-2").name,
            "2026-08-13-2-candidates.csv",
        )
        with self.assertRaises(RuntimeError):
            a.candidates_path("batch2")

    def test_selects_ranked_unverified_dictionary_pairs_in_order(self):
        rows = [
            {"id": "2", "original": "西", "pronunciation": "ニシ",
             "verified": "no", "rank": "3", "evidence_sources": "jmnedict"},
            {"id": "1", "original": "東", "pronunciation": "アズマ",
             "verified": "no", "rank": "2", "evidence_sources": "jmnedict"},
            {"id": "3", "original": "南", "pronunciation": "ミナミ",
             "verified": "yes", "rank": "1", "evidence_sources": "ndl"},
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "myoji.csv"
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)
            selected = a.select_candidates(path, 10)
        self.assertEqual([(r["surface"], r["pronunciation"]) for r in selected],
                         [("東", "アズマ"), ("西", "ニシ")])

    def test_excludes_previously_searched_pair(self):
        rows = [
            {"id": "1", "original": "東", "pronunciation": "アズマ",
             "verified": "no", "rank": "1", "evidence_sources": "jmnedict"},
            {"id": "2", "original": "西", "pronunciation": "ニシ",
             "verified": "no", "rank": "2", "evidence_sources": "jmnedict"},
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "myoji.csv"
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)
            selected = a.select_candidates(path, 10, {("東", "アズマ")})
        self.assertEqual([(r["surface"], r["pronunciation"]) for r in selected],
                         [("西", "ニシ")])

    def test_prepare_does_not_overwrite_snapshot(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
                a, "BATCH_DIR", Path(td)):
            path = Path(td) / "2026-08-13-candidates.csv"
            path.write_text("fixed", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                a.prepare(1, "2026-08-13")
            self.assertEqual(path.read_text(encoding="utf-8"), "fixed")

    def test_searched_pairs_reads_suffixed_batches(self):
        record = {"surface": "東", "pronunciation": "アズマ"}
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
                a, "BATCH_DIR", Path(td)):
            (Path(td) / "2026-08-13-2-a.jsonl").write_text(
                json.dumps(record), encoding="utf-8")
            self.assertEqual(a.searched_pairs(), {("東", "アズマ")})


class ResultValidationTest(unittest.TestCase):
    def setUp(self):
        self.candidates = {0: {
            "batch_index": "0", "id": "1", "surface": "東",
            "pronunciation": "アヅマ", "rank": "2", "query": "東 あづま",
        }}
        self.record = {
            "batch_index": 0, "surface": "東", "pronunciation": "アヅマ",
            "rank": "2", "searched_on": "2026-08-13", "query": "東 あづま",
            "status": "verified", "source_url": "https://example.jp/person",
            "source_type": "official_person_profile", "source_title": "人物紹介",
            "observed_surface": "東", "observed_reading": "あづま",
            "locator": "氏名欄", "notes": "公式プロフィール",
        }

    def load(self, records):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "batch.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in records),
                            encoding="utf-8")
            return a.load_results(self.candidates, [path])

    def test_accepts_exact_verified_result(self):
        self.assertEqual(len(self.load([self.record])), 1)

    def test_rejects_mismatched_reading(self):
        record = dict(self.record, observed_reading="ひがし")
        with self.assertRaises(RuntimeError):
            self.load([record])

    def test_no_support_has_no_source_metadata(self):
        record = dict(self.record, status="no_support_found",
                      source_url="", source_type="", source_title="",
                      observed_surface="", observed_reading="", locator="")
        self.assertEqual(self.load([record])[0]["status"], "no_support_found")

    def test_requires_every_candidate_once(self):
        with self.assertRaises(RuntimeError):
            self.load([])
        with self.assertRaises(RuntimeError):
            self.load([self.record, self.record])


if __name__ == "__main__":
    unittest.main()
