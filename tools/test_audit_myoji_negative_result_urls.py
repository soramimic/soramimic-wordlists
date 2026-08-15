import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_myoji_negative_result_urls as subject


class NegativeResultUrlAuditTest(unittest.TestCase):
    @patch("audit_myoji_negative_result_urls.fetch_document")
    def test_same_url_is_fetched_once_for_different_candidates(self, fetch):
        fetch.return_value = {
            "http_status": 200,
            "final_url": "https://example.org/roster",
            "content_type": "text/html",
            "content_sha256": "abc",
            "text": "榎谷 エノキヤ 太郎\n坂植 サカウエ 花子",
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "batch.jsonl"
            output = Path(directory) / "audit.jsonl"
            rows = [
                {
                    "surface": "榎谷",
                    "pronunciation": "エノキヤ",
                    "status": "no_support_found",
                    "search_attempts": [
                        {"result_urls": ["https://example.org/roster"]}
                    ],
                },
                {
                    "surface": "坂植",
                    "pronunciation": "サカウエ",
                    "status": "no_support_found",
                    "search_attempts": [
                        {"result_urls": ["https://example.org/roster"]}
                    ],
                },
            ]
            source.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )
            total, processed, counts = subject.run([source], output, workers=2)
        self.assertEqual((total, processed, counts), (2, 2, {"pass": 2}))
        fetch.assert_called_once_with("https://example.org/roster", timeout=20)

    def test_expands_deduplicated_non_dictionary_urls_for_negative_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.jsonl"
            rows = [
                {
                    "surface": "榎谷",
                    "pronunciation": "エノキヤ",
                    "status": "no_support_found",
                    "search_attempts": [
                        {
                            "result_urls": [
                                "https://example.org/a",
                                "https://example.org/a",
                            ]
                        },
                        {
                            "result_urls": [
                                "https://name-power.net/x",
                                "https://example.org/b",
                            ]
                        },
                    ],
                },
                {
                    "surface": "既済",
                    "pronunciation": "キサイ",
                    "status": "verified",
                    "search_attempts": [{"result_urls": ["https://example.org/c"]}],
                },
            ]
            path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )
            jobs = subject.expand_rows([path])
            self.assertEqual(
                [job["source_url"] for job in jobs],
                [
                    "https://example.org/a",
                    "https://name-power.net/x",
                    "https://example.org/b",
                ],
            )
            self.assertEqual(len(jobs[0]["origins"]), 2)

    def test_expands_ambiguous_rows_but_excludes_verified_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.jsonl"
            rows = [
                {
                    "surface": "曖昧",
                    "pronunciation": "アイマイ",
                    "status": "ambiguous",
                    "search_attempts": [
                        {"result_urls": ["https://example.org/ambiguous"]}
                    ],
                },
                {
                    "surface": "既済",
                    "pronunciation": "キサイ",
                    "status": "verified",
                    "search_attempts": [
                        {"result_urls": ["https://example.org/verified"]}
                    ],
                },
            ]
            path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )
            jobs = subject.expand_rows([path])
            self.assertEqual(
                [job["source_url"] for job in jobs],
                ["https://example.org/ambiguous"],
            )

    @patch("audit_myoji_negative_result_urls.audit_row")
    def test_checkpoint_is_keyed_by_candidate_and_url(self, audit):
        audit.side_effect = lambda row, number, **kwargs: {
            "schema_version": 3,
            "row_number": number,
            "surface": row["surface"],
            "pronunciation": row["pronunciation"],
            "source_url": row["source_url"],
            "audit_result": "pass",
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "batch.jsonl"
            output = Path(directory) / "audit.jsonl"
            source.write_text(
                json.dumps(
                    {
                        "surface": "上高原",
                        "pronunciation": "カミタカハラ",
                        "status": "no_support_found",
                        "search_attempts": [
                            {"result_urls": ["https://example.org/profile"]}
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(subject.run([source], output)[1], 1)
            self.assertEqual(subject.run([source], output)[1], 0)
            item = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(item["audit_result"], "pass")
            self.assertEqual(item["research_file"], "batch.jsonl")

    @patch("audit_myoji_negative_result_urls.audit_row")
    def test_retry_errors_only_refetches_error_results(self, audit):
        outcomes = iter(("error", "pass"))
        audit.side_effect = lambda row, number, **kwargs: {
            "schema_version": 3,
            "row_number": number,
            "surface": row["surface"],
            "pronunciation": row["pronunciation"],
            "source_url": row["source_url"],
            "audit_result": next(outcomes),
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "batch.jsonl"
            output = Path(directory) / "audit.jsonl"
            source.write_text(
                json.dumps(
                    {
                        "surface": "榎谷",
                        "pronunciation": "エノキヤ",
                        "status": "no_support_found",
                        "search_attempts": [
                            {"result_urls": ["https://example.org/profile"]}
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(subject.run([source], output)[1], 1)
            self.assertEqual(subject.run([source], output)[1], 0)
            self.assertEqual(subject.run([source], output, retry_errors=True)[1], 1)
            item = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(item["audit_result"], "pass")
            self.assertEqual(item["retry_of"], "error")

    @patch("audit_myoji_negative_result_urls.audit_row")
    def test_new_url_after_checkpoint_is_marked(self, audit):
        audit.side_effect = lambda row, number, **kwargs: {
            "schema_version": 3,
            "row_number": number,
            "surface": row["surface"],
            "pronunciation": row["pronunciation"],
            "source_url": row["source_url"],
            "audit_result": "pass",
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "batch.jsonl"
            output = Path(directory) / "audit.jsonl"
            row = {
                "surface": "榎谷",
                "pronunciation": "エノキヤ",
                "status": "no_support_found",
                "search_attempts": [{"result_urls": ["https://example.org/a"]}],
            }
            source.write_text(
                json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            subject.run([source], output)
            row["search_attempts"][0]["result_urls"].append("https://example.org/b")
            source.write_text(
                json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            self.assertEqual(subject.run([source], output)[1], 1)
            items = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
            ]
        by_url = {item["source_url"]: item for item in items}
        self.assertNotIn("new_since_checkpoint", by_url["https://example.org/a"])
        self.assertTrue(by_url["https://example.org/b"]["new_since_checkpoint"])


if __name__ == "__main__":
    unittest.main()
