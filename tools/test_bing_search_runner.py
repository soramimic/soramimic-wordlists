import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import bing_search_runner as runner


class Response:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class BingRunnerTest(unittest.TestCase):
    def test_target_url_encodes_literal_parentheses(self):
        target = runner._target_url(
            "https://ja.wikipedia.org/wiki/%E5%A7%93_(%E3%81%82%E3%81%84)"
        )
        self.assertEqual(
            target, "https://ja.wikipedia.org/wiki/%E5%A7%93_%28%E3%81%82%E3%81%84%29"
        )
        self.assertFalse(target.endswith((")", "]", "}")))

    def test_fetch_fixture_extracts_target_and_snippet(self):
        body = '<li class="b_algo"><h2><a href="https://example.jp/person">Person</a></h2><div class="b_caption"><p>榎谷 礼央（エノキヤ レオ）</p></div></li><li class="b_algo"><h2><a href="https://www.bing.com/search?q=x">Search</a></h2></li><li class="b_algo"><h2><a href="http://example.jp/no">HTTP</a></h2></li>'.encode()
        status, urls, snippets, returned = runner.fetch(
            "榎谷", timeout=7, opener=lambda req, timeout: Response(body)
        )
        self.assertEqual(
            (status, urls, returned), (200, ["https://example.jp/person"], body)
        )
        self.assertIn("エノキヤ", snippets[0])

    def test_queries_receipts_and_resume(self):
        candidate = {"surface": "榎谷", "pronunciation": "エノキヤ"}
        with patch.object(
            runner,
            "fetch",
            return_value=(200, ["https://example.jp/p"], ["hit"], b"page"),
        ):
            for strategy in runner.STRATEGIES:
                a = runner._attempt(candidate, strategy, 0, 5)
                self.assertEqual(a["response_sha256"], runner.receipt_sha256(a))
                self.assertTrue(
                    all(f"-site:{h}" in a["query"] for h in runner.EXCLUDED_SITES)
                )

    def test_range_and_single_worker_stops(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "c.csv"
            out = root / "o.jsonl"
            with inp.open("w", newline="") as f:
                w = csv.DictWriter(
                    f, fieldnames=["batch_index", "surface", "pronunciation"]
                )
                w.writeheader()
                for i in range(3):
                    w.writerow(
                        {
                            "batch_index": i,
                            "surface": f"姓{i}",
                            "pronunciation": f"ヨミ{i}",
                        }
                    )
            with patch.object(runner, "fetch", return_value=(429, [], [], b"limited")):
                self.assertEqual(
                    runner.run(inp, out, workers=1, delay=0, start=1, stop=3), (1, 1)
                )
            self.assertEqual(json.loads(out.read_text())["batch_index"], 1)


if __name__ == "__main__":
    unittest.main()
