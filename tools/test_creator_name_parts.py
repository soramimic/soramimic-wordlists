import copy
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_vtuber_name_parts as subject


class NamePartsTest(unittest.TestCase):
    def setUp(self):
        self.record = dict(person_id="12", original="試験あお",
                           pronunciation="シケンアオ", family="試験",
                           family_pronunciation="シケン", given="あお",
                           given_pronunciation="アオ", order="family_given",
                           source_urls=["https://example.com/profile"],
                           reviewed_on="2026-10-10")
        self.full = dict(id="12", original="試験あお", surface="試験あお",
                         pronunciation="シケンアオ", type="full", category="vtuber",
                         image="keep.webp", image_credit="credit", scope="japan",
                         description="説明", channel_shared="no", has_image="yes")
        self.other = {**self.full, "id": "13", "original": "既存", "type": "given"}

    def load(self, records):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
            return subject.load_reviewed(path)

    def test_preserves_rows_and_copies_metadata_idempotently(self):
        rows = [self.full, self.other]
        before = copy.deepcopy(rows)
        result, count = subject.add_reviewed_parts(rows, self.load([self.record]))
        self.assertEqual(count, 2)
        self.assertEqual(rows, before)
        self.assertEqual([result[0], result[3]], before)
        for part in result[1:3]:
            self.assertEqual({k: v for k, v in part.items() if k not in subject.PART_FIELDS},
                             {k: v for k, v in self.full.items() if k not in subject.PART_FIELDS})
        self.assertEqual(subject.add_reviewed_parts(result, [self.record]), (result, 0))

    def test_rejects_conflicts_and_stale_identity_without_mutating_input(self):
        for changed in ({"id": "99"}, {"original": "別人"},
                        {"pronunciation": "ベツジン"}, {"category": "youtuber"}):
            rows = [{**self.full, **changed}]
            before = copy.deepcopy(rows)
            with self.assertRaises(ValueError):
                subject.add_reviewed_parts(rows, [self.record])
            self.assertEqual(rows, before)
        with self.assertRaises(ValueError):
            subject.add_reviewed_parts([self.full, {**self.full, "type": "family"}], [self.record])

    def test_rejects_incomplete_or_inconsistent_evidence(self):
        for change in ({"source_urls": []}, {"source_urls": ["file:///tmp/source"]},
                       {"family": "別"}, {"given_pronunciation": "ベツ"},
                       {"reviewed_on": "2026-99-10"}, {"order": "unknown"}):
            with self.assertRaises(ValueError):
                self.load([{**self.record, **change}])
        with self.assertRaises(ValueError):
            self.load([self.record, self.record])

    def test_given_first_names_keep_correct_labels(self):
        record = {**self.record, "original": "アオ・シケン", "pronunciation": "アオシケン",
                  "family": "シケン", "given": "アオ", "order": "given_family"}
        row = {**self.full, "original": record["original"], "surface": record["original"],
               "pronunciation": record["pronunciation"]}
        result, count = subject.add_reviewed_parts([row], self.load([record]))
        self.assertEqual(count, 2)
        self.assertEqual([(r["type"], r["surface"]) for r in result[1:]],
                         [("family", "シケン"), ("given", "アオ")])

    def test_checked_in_rows_match_reviewed_parts(self):
        with subject.CSV_PATH.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(subject.add_reviewed_parts(rows, subject.load_reviewed()), (rows, 0))


if __name__ == "__main__":
    unittest.main()
