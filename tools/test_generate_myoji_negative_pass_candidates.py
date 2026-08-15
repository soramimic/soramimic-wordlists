import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_myoji_negative_pass_candidates as generator


class GenerateNegativePassCandidatesTest(unittest.TestCase):
    def test_groups_passes_and_deduplicates_urls(self):
        rows = [
            {
                "surface": "榎谷",
                "pronunciation": "エノキヤ",
                "batch_index": 7,
                "source_url": "https://example.jp/a",
                "audit_result": "pass",
                "final_url": "https://example.jp/a",
                "reason": "surface_and_reading_nearby",
            },
            {
                "surface": "榎谷",
                "pronunciation": "エノキヤ",
                "batch_index": 7,
                "source_url": "https://example.jp/a",
                "audit_result": "pass",
            },
            {
                "surface": "榎谷",
                "pronunciation": "エノキヤ",
                "batch_index": 7,
                "source_url": "https://example.jp/b",
                "audit_result": "fail",
            },
            {
                "surface": "四角目",
                "pronunciation": "シカクメ",
                "batch_index": 8,
                "source_url": "https://example.jp/c",
                "audit_result": "pass",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
            )
            queue = generator.build_queue([path])
        self.assertEqual([row["review_index"] for row in queue], [0, 1])
        self.assertEqual(len(queue[0]["pass_urls"]), 1)
        self.assertEqual(queue[0]["pass_urls"][0]["source_url"], "https://example.jp/a")

    def test_excludes_already_reviewed_candidate_keys_and_reindexes(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = Path(directory) / "audit.jsonl"
            exclude = Path(directory) / "review.jsonl"
            audit.write_text(
                "\n".join(
                    json.dumps(row, ensure_ascii=False)
                    for row in [
                        {
                            "surface": "榎谷",
                            "pronunciation": "エノキヤ",
                            "source_url": "https://example.jp/a",
                            "audit_result": "pass",
                        },
                        {
                            "surface": "四角目",
                            "pronunciation": "シカクメ",
                            "source_url": "https://example.jp/b",
                            "audit_result": "pass",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            exclude.write_text(
                json.dumps(
                    {
                        "surface": "榎谷",
                        "pronunciation": "エノキヤ",
                        "decision": "reject",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            queue = generator.build_queue([audit], [exclude])
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["surface"], "四角目")
        self.assertEqual(queue[0]["review_index"], 0)

    def test_retry_only_includes_recovered_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = Path(directory) / "audit.jsonl"
            audit.write_text(
                "\n".join(
                    json.dumps(row, ensure_ascii=False)
                    for row in [
                        {
                            "surface": "榎谷",
                            "pronunciation": "エノキヤ",
                            "source_url": "https://example.jp/a",
                            "audit_result": "pass",
                        },
                        {
                            "surface": "四角目",
                            "pronunciation": "シカクメ",
                            "source_url": "https://example.jp/b",
                            "audit_result": "pass",
                            "retry_of": "error",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            queue = generator.build_queue([audit], retry_only=True)
        self.assertEqual([row["surface"] for row in queue], ["四角目"])

    def test_new_only_includes_new_checkpoint_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = Path(directory) / "audit.jsonl"
            audit.write_text(
                "\n".join(
                    json.dumps(row, ensure_ascii=False)
                    for row in [
                        {
                            "surface": "榎谷",
                            "pronunciation": "エノキヤ",
                            "source_url": "https://example.jp/a",
                            "audit_result": "pass",
                        },
                        {
                            "surface": "榎谷",
                            "pronunciation": "エノキヤ",
                            "source_url": "https://example.jp/b",
                            "audit_result": "pass",
                            "new_since_checkpoint": True,
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            queue = generator.build_queue([audit], new_only=True)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["pass_urls"][0]["source_url"], "https://example.jp/b")


if __name__ == "__main__":
    unittest.main()
