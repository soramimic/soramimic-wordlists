import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_youtuber as target  # noqa: E402
from creator_csv import read_creator_csvs


class YouTuberExclusionTest(unittest.TestCase):
    def test_reviewed_channel_exclusions_are_absent_from_csv(self):
        excluded = {"うごくちゃん", "佐々木康平", "熱田隆介"}
        self.assertTrue(excluded <= target.EXCLUDED)

        _, rows = read_creator_csvs()
        originals = {row["original"] for row in rows}
        self.assertFalse(excluded & originals)

    def test_channel_ledgers_only_reference_current_people(self):
        root = Path(__file__).resolve().parent.parent
        _, rows = read_creator_csvs()
        people = {row["id"]: row for row in rows}

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
