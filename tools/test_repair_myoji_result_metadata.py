import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repair_myoji_result_metadata as subject


class RepairResultMetadataTest(unittest.TestCase):
    def test_repairs_only_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            candidates = Path(directory) / "candidates.csv"
            result = Path(directory) / "result.jsonl"
            candidates.write_text(
                "batch_index,id,surface,pronunciation,rank,query\n"
                "7,42,榎谷,エノキヤ,9,榎谷 えのきや 氏名\n",
                encoding="utf-8",
            )
            original = {
                "batch_index": 7,
                "id": "old",
                "surface": "榎谷",
                "pronunciation": "エノキヤ",
                "rank": "",
                "query": "bad",
                "status": "verified",
                "search_attempts": [{"receipt": 1}],
            }
            result.write_text(
                json.dumps(original, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            changed = subject.repair(result, subject.load_candidates(candidates))
            repaired = json.loads(result.read_text(encoding="utf-8"))
        self.assertEqual(changed, 1)
        self.assertEqual(
            (repaired["id"], repaired["rank"], repaired["query"]),
            ("42", "9", "榎谷 えのきや 氏名"),
        )
        self.assertEqual(repaired["search_attempts"], original["search_attempts"])


if __name__ == "__main__":
    unittest.main()
