import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import official_domain_search_runner as runner


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


class OfficialRunnerTest(unittest.TestCase):
    def test_queries_include_official_domains_and_both_readings(self):
        c = {"surface": "倉野内", "pronunciation": "クラノウチ"}
        self.assertIn('"倉野内" "クラノウチ"', runner.query_for(c, "official_katakana"))
        self.assertIn('"倉野内" "くらのうち"', runner.query_for(c, "official_hiragana"))
        for site in runner.OFFICIAL_SITES:
            self.assertIn("site:" + site, runner.query_for(c, "official_person"))

    def test_fetch_extracts_https_target_and_snippet(self):
        body = '<li class="b_algo"><h2><a href="https://www.pref.saitama.lg.jp/a0903/saitamanougyoudanshi/dai151.html">x</a></h2><div class="b_caption"><p>倉野内直子（くらのうちなおこ）</p></div></li>'.encode()
        status, urls, snippets, raw = runner.fetch(
            "倉野内", opener=lambda req, timeout: Response(body)
        )
        self.assertEqual(
            (status, urls, raw),
            (
                200,
                [
                    "https://www.pref.saitama.lg.jp/a0903/saitamanougyoudanshi/dai151.html"
                ],
                body,
            ),
        )
        self.assertIn("くらのうち", snippets[0])

    def test_resume_range_and_receipt_hash(self):
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
                            "surface": "姓" + str(i),
                            "pronunciation": "ヨミ" + str(i),
                        }
                    )
            with patch.object(runner, "fetch", return_value=(429, [], [], b"limited")):
                self.assertEqual(
                    runner.run(inp, out, workers=1, delay=0, start=1, stop=3), (1, 1)
                )
            row = json.loads(out.read_text())
            self.assertEqual(row["batch_index"], 1)
            self.assertEqual(
                row["search_attempts"][0]["response_sha256"],
                runner.receipt_sha256(row["search_attempts"][0]),
            )

    def test_jsonl_status_filter(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "results.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "batch_index": i,
                            "surface": "姓" + str(i),
                            "pronunciation": "ヨミ",
                            "status": status,
                        },
                        ensure_ascii=False,
                    )
                    for i, status in enumerate(
                        ("no_support_found", "verified", "no_support_found")
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            rows = runner._load_candidates(path, status="no_support_found")
            self.assertEqual([int(row["batch_index"]) for row in rows], [0, 2])


if __name__ == "__main__":
    unittest.main()
