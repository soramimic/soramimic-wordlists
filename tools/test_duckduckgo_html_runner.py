import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import duckduckgo_html_runner as runner


class RunnerTest(unittest.TestCase):
    def test_lite_fixture_extracts_redirect_target_and_td_snippet(self):
        body = (
            "<table><tr><td><a class='result-link' href='//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fperson'>Person</a></td></tr>"
            "<tr><td class='result-snippet'>榎谷 礼央（エノキヤ レオ）</td></tr></table>"
        ).encode()
        status, urls, snippets, returned = runner.fetch(
            "榎谷",
            timeout=7,
            opener=lambda request, timeout: type(
                "R",
                (),
                {
                    "status": 200,
                    "__enter__": lambda self: self,
                    "__exit__": lambda self, *args: False,
                    "read": lambda self: body,
                },
            )(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(urls, ["https://example.org/person"])
        self.assertIn("エノキヤ", snippets[0])
        self.assertEqual(returned, body)

    def test_three_receipts_and_resume(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "candidates.csv"
            out = root / "results.jsonl"
            with inp.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=[
                        "batch_index",
                        "id",
                        "surface",
                        "pronunciation",
                        "rank",
                        "query",
                    ],
                )
                w.writeheader()
                w.writerow(
                    {
                        "batch_index": 0,
                        "id": "x",
                        "surface": "榎谷",
                        "pronunciation": "エノキタニ",
                        "rank": "",
                        "query": "榎谷 えのきたに 氏名",
                    }
                )
            calls = []

            def fake(query, timeout=20):
                calls.append(query)
                return (
                    200,
                    ["https://example.org/person/1"],
                    ["榎谷 一（エノキタニ）"],
                    query.encode(),
                )

            with patch.object(runner, "fetch", side_effect=fake):
                self.assertEqual(runner.run(inp, out, workers=2, delay=0), (1, 1))
                self.assertEqual(runner.run(inp, out, workers=2, delay=0), (1, 0))
            self.assertEqual(len(calls), 3)
            row = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(len(row["search_attempts"]), 3)
            self.assertTrue(
                all(len(a["response_sha256"]) == 64 for a in row["search_attempts"])
            )

    def test_queries_include_second_pass_dictionary_exclusions(self):
        candidate = {"surface": "榎谷", "pronunciation": "エノキヤ"}
        with patch.object(
            runner,
            "fetch",
            return_value=(200, [], [], b"page"),
        ):
            for strategy in runner.STRATEGIES:
                attempt = runner._attempt(candidate, strategy, 0, 5)
                for host in runner.SECOND_PASS_EXCLUDED_SITES:
                    self.assertIn(f"-site:{host}", attempt["query"])

    def test_range_and_single_worker_stop_on_incomplete_response(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "candidates.csv"
            out = root / "results.jsonl"
            with inp.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=[
                        "batch_index",
                        "id",
                        "surface",
                        "pronunciation",
                        "rank",
                        "query",
                    ],
                )
                w.writeheader()
                for i in range(3):
                    w.writerow(
                        {
                            "batch_index": i,
                            "id": str(i),
                            "surface": f"姓{i}",
                            "pronunciation": f"ヨミ{i}",
                            "rank": "",
                            "query": "",
                        }
                    )
            calls = []

            def fake(query, timeout=20):
                calls.append(query)
                return (
                    (429, [], [], b"limited")
                    if len(calls) == 2
                    else (200, ["https://example.org/p"], ["hit"], b"page")
                )

            with patch.object(runner, "fetch", side_effect=fake):
                self.assertEqual(
                    runner.run(inp, out, workers=1, delay=0, start=1, stop=3), (1, 1)
                )
            row = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(row["batch_index"], 1)
            self.assertEqual(len(row["search_attempts"]), 2)

    def test_resume_keeps_successful_strategy_receipts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "candidates.csv"
            out = root / "results.jsonl"
            with inp.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=[
                        "batch_index",
                        "id",
                        "surface",
                        "pronunciation",
                        "rank",
                        "query",
                    ],
                )
                w.writeheader()
                w.writerow(
                    {
                        "batch_index": 0,
                        "id": "x",
                        "surface": "榎谷",
                        "pronunciation": "エノキヤ",
                        "rank": "",
                        "query": "",
                    }
                )
            first_calls = [
                (200, ["https://example.org/p"], ["hit"], b"page"),
                (429, [], [], b"limited"),
            ]
            with patch.object(runner, "fetch", side_effect=first_calls):
                runner.run(inp, out, workers=1, delay=0)
            first = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(first["search_attempts"][0]["http_status"], 200)
            self.assertEqual(first["search_attempts"][1]["http_status"], 429)
            good = (200, ["https://example.org/p"], ["hit"], b"page")
            with patch.object(runner, "fetch", return_value=good) as fetch:
                runner.run(inp, out, workers=1, delay=0)
            self.assertEqual(fetch.call_count, 2)
            second = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(
                [a["http_status"] for a in second["search_attempts"]], [200, 200, 200]
            )


if __name__ == "__main__":
    unittest.main()
