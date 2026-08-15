import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).parent))
import yahoo_japan_search_runner as runner


class _Response:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class YahooJapanSearchRunnerTest(unittest.TestCase):
    def test_fetch_extracts_https_results_and_snippets(self):
        body = (
            '<ul><li><a href="https://example.jp/person">人物</a>'
            "<div>榎谷 礼央（エノキヤ レオ）</div></li>"
            '<li><a href="https://search.yahoo.co.jp/search?p=x">検索</a></li>'
            '<li><a href="http://example.net/plain">HTTP</a></li></ul>'
        ).encode()

        def opener(_request, timeout):
            self.assertEqual(timeout, 7)
            return _Response(body)

        status, urls, snippets, returned = runner.fetch(
            "榎谷", timeout=7, opener=opener
        )
        self.assertEqual(status, 200)
        self.assertEqual(urls, ["https://example.jp/person"])
        self.assertIn("エノキヤ", snippets[0])
        self.assertEqual(returned, body)

    def test_attempt_receipt_hash_matches_payload(self):
        candidate = {"surface": "榎谷", "pronunciation": "エノキヤ"}
        with patch.object(
            runner,
            "fetch",
            return_value=(
                200,
                ["https://example.jp/person"],
                ["榎谷 エノキヤ"],
                b"page",
            ),
        ):
            attempt = runner._attempt(candidate, "exact_katakana", 0, 5)
        self.assertEqual(attempt["engine"], "yahoo_japan")
        self.assertIn("榎谷", attempt["query"])
        self.assertIn("エノキヤ", attempt["query"])
        self.assertEqual(attempt["response_sha256"], runner.receipt_sha256(attempt))

    def test_attempt_preserves_rate_limit_status(self):
        candidate = {"surface": "榎谷", "pronunciation": "エノキヤ"}
        error = HTTPError("https://search.yahoo.co.jp/", 429, "rate limited", {}, None)
        with patch.object(runner, "fetch", side_effect=error):
            attempt = runner._attempt(candidate, "broad_person", 0, 5)
        self.assertEqual(attempt["http_status"], 429)
        self.assertEqual(attempt["result_urls"], [])
        self.assertEqual(attempt["response_sha256"], runner.receipt_sha256(attempt))

    def test_run_checkpoints_three_real_attempts_per_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates.csv"
            output = root / "results.jsonl"
            with candidates.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=(
                        "batch_index",
                        "surface",
                        "pronunciation",
                        "rank",
                        "query",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "batch_index": 0,
                        "surface": "榎谷",
                        "pronunciation": "エノキヤ",
                        "rank": "",
                        "query": "榎谷 えのきや 氏名",
                    }
                )
            with patch.object(
                runner,
                "fetch",
                return_value=(
                    200,
                    ["https://example.jp/person"],
                    ["榎谷 エノキヤ"],
                    b"page",
                ),
            ):
                total, processed = runner.run(candidates, output, workers=1, delay=0)
            self.assertEqual((total, processed), (1, 1))
            row = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(row["status"], "ambiguous")
            self.assertEqual(
                {attempt["strategy"] for attempt in row["search_attempts"]},
                set(runner.STRATEGIES),
            )
            self.assertTrue(
                all(attempt["http_status"] == 200 for attempt in row["search_attempts"])
            )

    def test_research_stops_after_first_failed_strategy(self):
        candidate = {
            "batch_index": "0",
            "surface": "榎谷",
            "pronunciation": "エノキヤ",
            "rank": "",
            "query": "榎谷 えのきや 氏名",
        }
        failed = {
            "strategy": "exact_katakana",
            "engine": "yahoo_japan",
            "query": '"榎谷" "エノキヤ" 氏名',
            "completed_at": "2026-08-14T00:00:00+09:00",
            "http_status": 429,
            "result_count": 0,
            "result_urls": [],
            "response_sha256": "x",
        }
        with patch.object(runner, "_attempt", return_value=failed) as attempt:
            row = runner._research(candidate, 0, 5)
        self.assertEqual(len(row["search_attempts"]), 1)
        attempt.assert_called_once()


if __name__ == "__main__":
    unittest.main()
