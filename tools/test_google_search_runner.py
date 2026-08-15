import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import google_search_runner as runner


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


class GoogleRunnerTest(unittest.TestCase):
    def test_fetch_extracts_target_https_urls_and_snippets(self):
        body = """<div class="MjjYud"><a href="https://example.jp/person"><h3>人物</h3></a><div class="VwiC3b">榎谷 礼央（エノキヤ レオ）</div></div>
        <div class="MjjYud"><a href="https://www.google.com/url?q=https%3A%2F%2Fexample.jp%2Fother"><h3>別人</h3></a><span class="VwiC3b">別の snippet</span></div>
        <div class="MjjYud"><a href="https://www.google.com/search?q=x">Google</a></div>
        <div class="MjjYud"><a href="http://example.jp/plain">HTTP</a></div>""".encode()
        status, urls, snippets, returned = runner.fetch(
            "榎谷", timeout=7, opener=lambda req, timeout: _Response(body)
        )
        self.assertEqual(status, 200)
        self.assertEqual(returned, body)
        self.assertEqual(
            urls, ["https://example.jp/person", "https://example.jp/other"]
        )
        self.assertIn("エノキヤ", snippets[0])

    def test_query_receipt_has_exclusions_and_sha(self):
        with patch.object(
            runner,
            "fetch",
            return_value=(200, ["https://example.jp/p"], ["hit"], b"page"),
        ):
            attempt = runner._attempt(
                {"surface": "榎谷", "pronunciation": "エノキヤ"}, "exact_katakana", 0, 5
            )
        self.assertEqual(attempt["engine"], "google_html")
        for host in runner.SECOND_PASS_EXCLUDED_SITES:
            self.assertIn(f"-site:{host}", attempt["query"])
        self.assertEqual(attempt["response_sha256"], runner.receipt_sha256(attempt))

    def test_three_strategy_checkpoint_resume_and_range(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "candidates.csv"
            out = root / "out.jsonl"
            with inp.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["batch_index", "surface", "pronunciation"]
                )
                writer.writeheader()
                for i in range(3):
                    writer.writerow(
                        {
                            "batch_index": i,
                            "surface": f"姓{i}",
                            "pronunciation": f"ヨミ{i}",
                        }
                    )
            with patch.object(
                runner,
                "fetch",
                return_value=(200, ["https://example.jp/p"], ["hit"], b"page"),
            ) as fetch:
                self.assertEqual(runner.run(inp, out, delay=0, start=1, stop=2), (1, 1))
                self.assertEqual(runner.run(inp, out, delay=0, start=1, stop=2), (1, 0))
            self.assertEqual(fetch.call_count, 3)
            self.assertEqual(len(json.loads(out.read_text())["search_attempts"]), 3)

    def test_single_worker_stops_on_incomplete_response_and_keeps_success(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "candidates.csv"
            out = root / "out.jsonl"
            with inp.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["batch_index", "surface", "pronunciation"]
                )
                writer.writeheader()
                writer.writerow(
                    {"batch_index": 0, "surface": "姓", "pronunciation": "ヨミ"}
                )
            calls = iter(
                [
                    (200, ["https://example.jp/p"], ["hit"], b"page"),
                    (429, [], [], b"limited"),
                ]
            )
            with patch.object(
                runner, "fetch", side_effect=lambda *args, **kwargs: next(calls)
            ):
                self.assertEqual(runner.run(inp, out, delay=0), (1, 1))
            row = json.loads(out.read_text())
            self.assertEqual(
                [a["http_status"] for a in row["search_attempts"]], [200, 429]
            )


if __name__ == "__main__":
    unittest.main()
