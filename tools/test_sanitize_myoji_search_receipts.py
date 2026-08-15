import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_myoji_web_research as audit
import sanitize_myoji_search_receipts as sanitizer


class SanitizeReceiptsTest(unittest.TestCase):
    def test_cleans_delimiters_drops_http_and_deduplicates(self):
        attempt = {
            "strategy": "exact_katakana",
            "engine": "openai_web_search",
            "query": '"榎谷" "エノキヤ"',
            "http_status": 200,
            "result_count": 9,
            "result_urls": [
                "https://example.jp/a.pdf)",
                "https://example.jp/a.pdf",
                "http://example.jp/b",
                "https://example.jp/c。",
                "https://example.jp",
                "https://example.jp/",
                "https://www.google.com/search?q=test",
                "https://example.jp/bad trailing text",
                "https://a",
            ],
            "response_sha256": "old",
        }
        sanitizer.sanitize_attempt(attempt)
        self.assertEqual(
            attempt["result_urls"],
            [
                "https://example.jp/a.pdf%29",
                "https://example.jp/a.pdf",
                "https://example.jp/c%E3%80%82",
            ],
        )
        self.assertEqual(attempt["result_count"], 3)
        self.assertEqual(attempt["response_sha256"], audit.receipt_sha256(attempt))

    def test_keeps_root_with_candidate_specific_query_or_fragment(self):
        self.assertEqual(
            sanitizer.sanitize_url("https://example.jp/?name=榎谷"),
            "https://example.jp/?name=榎谷",
        )
        self.assertEqual(
            sanitizer.sanitize_url("https://example.jp/#enokiya"),
            "https://example.jp/#enokiya",
        )

    def test_drops_search_ui_fragments_that_only_look_like_urls(self):
        self.assertEqual(sanitizer.sanitize_url("https://twitter.com…[Button:"), "")
        self.assertEqual(sanitizer.sanitize_url("https://example。jp/profile"), "")

    def test_drops_captured_snippets_without_changing_receipt_identity(self):
        attempt = {
            "strategy": "exact_katakana",
            "engine": "bing",
            "query": '"榎谷" "エノキヤ"',
            "http_status": 200,
            "result_count": 1,
            "result_urls": ["https://example.jp/profile"],
            "result_snippets": ["captured page text"],
            "response_sha256": "old",
        }
        sanitizer.sanitize_attempt(attempt)
        self.assertNotIn("result_snippets", attempt)
        self.assertEqual(attempt["response_sha256"], audit.receipt_sha256(attempt))

    def test_file_rewrite_is_valid_jsonl(self):
        attempt = {
            "strategy": "broad_person",
            "engine": "openai_web_search",
            "query": "榎谷 人物",
            "http_status": 200,
            "result_count": 1,
            "result_urls": ["https://example.jp/x)]"],
            "response_sha256": "old",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.jsonl"
            path.write_text(
                json.dumps({"search_attempts": [attempt]}) + "\n", encoding="utf-8"
            )
            self.assertEqual(sanitizer.sanitize_file(path), 1)
            row = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                row["search_attempts"][0]["result_urls"],
                ["https://example.jp/x%29%5D"],
            )


if __name__ == "__main__":
    unittest.main()
