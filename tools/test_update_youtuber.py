import csv
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_youtuber as target  # noqa: E402


class YouTuberExclusionTest(unittest.TestCase):
    def test_reviewed_channel_exclusions_are_absent_from_csv(self):
        excluded = {"うごくちゃん", "佐々木康平", "熱田隆介"}
        self.assertTrue(excluded <= target.EXCLUDED)

        with (Path(__file__).resolve().parent.parent / "youtuber.csv").open(
                encoding="utf-8", newline="") as handle:
            originals = {row["original"] for row in csv.DictReader(handle)}
        self.assertFalse(excluded & originals)

    def test_channel_ledgers_only_reference_current_people(self):
        root = Path(__file__).resolve().parent.parent
        with (root / "youtuber.csv").open(
                encoding="utf-8", newline="") as handle:
            people = {}
            for row in csv.DictReader(handle):
                people.setdefault(row["id"], row)

        for name in (
                "youtuber_channel_sources.jsonl",
                "youtuber_channel_candidates.jsonl"):
            path = root / "tools" / name
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                person = people.get(record["person_id"])
                self.assertIsNotNone(person, record)
                self.assertEqual(record["original"], person["original"])
                self.assertEqual(
                    record.get("qid", "NA"), person["wikidata"] or "NA")


if __name__ == "__main__":
    unittest.main()
