import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import generate_myoji_reaudit_candidates as tool


class GenerateCandidatesTest(unittest.TestCase):
    def test_deduplicates_and_writes_runner_csv(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "q.jsonl"
            out = root / "c.csv"
            rows = [
                {"surface": "榎谷", "pronunciation": "エノキヤ", "rank": ""},
                {"surface": "榎谷", "pronunciation": "エノキヤ", "rank": ""},
                {"surface": "佐伯", "pronunciation": "サエキノ", "rank": "2"},
            ]
            inp.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                encoding="utf-8",
            )
            catalog = root / "myoji.csv"
            catalog.write_text(
                "id,surface,pronunciation,rank\n10,榎谷,エノキヤ,4\n11,佐伯,サエキノ,5\n",
                encoding="utf-8",
            )
            self.assertEqual(tool.generate(inp, out, catalog), 2)
            with out.open(encoding="utf-8", newline="") as f:
                got = list(csv.DictReader(f))
            self.assertEqual([r["surface"] for r in got], ["榎谷", "佐伯"])
            self.assertEqual(got[1]["query"], "佐伯 さえきの 氏名")
            self.assertEqual(got[0]["id"], "10")
            self.assertEqual(got[0]["rank"], "4")

    def test_conflicting_rank_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "q.jsonl"
            out = root / "c.csv"
            inp.write_text(
                json.dumps(
                    {"surface": "榎谷", "pronunciation": "エノキヤ", "rank": "1"},
                    ensure_ascii=False,
                )
                + "\n"
                + json.dumps(
                    {"surface": "榎谷", "pronunciation": "エノキヤ", "rank": "2"},
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            catalog = root / "myoji.csv"
            catalog.write_text(
                "id,surface,pronunciation,rank\n10,榎谷,エノキヤ,4\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                tool.generate(inp, out, catalog)
            self.assertFalse(out.exists())

    def test_multiple_inputs_can_keep_only_current_no_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = root / "a.jsonl"
            second = root / "b.jsonl"
            out = root / "c.csv"
            first.write_text(
                json.dumps(
                    {"surface": "榎谷", "pronunciation": "エノキヤ", "rank": ""},
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            second.write_text(
                json.dumps(
                    {"surface": "佐伯", "pronunciation": "サエキノ", "rank": ""},
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            catalog = root / "myoji.csv"
            catalog.write_text(
                "id,surface,pronunciation,rank,verified\n"
                "10,榎谷,エノキヤ,4,yes\n"
                "11,佐伯,サエキノ,5,no\n",
                encoding="utf-8",
            )
            self.assertEqual(
                tool.generate([first, second], out, catalog, only_unverified=True), 1
            )
            with out.open(encoding="utf-8", newline="") as stream:
                self.assertEqual(
                    [row["surface"] for row in csv.DictReader(stream)], ["佐伯"]
                )


if __name__ == "__main__":
    unittest.main()
