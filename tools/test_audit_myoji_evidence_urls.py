import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import audit_myoji_evidence_urls as audit


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = (
            "<html><body>"
            + (
                "榎谷 礼央（エノキヤ レオ）"
                if self.path == "/person"
                else "佐伯 さえきのりお"
                if self.path == "/embedded"
                else "倉野内直子（くらのうちなおこ）"
                if self.path == "/parenthetical"
                else "榎谷\n" + "あ" * 130 + "\nエノキヤ"
            )
            + "</body></html>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/person"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def fake_fetch(self, url, timeout=20):
        path = url.rsplit("/", 1)[-1]
        text = (
            "榎谷 礼央（エノキヤ レオ）"
            if path == "person"
            else "佐伯 さえきのりお"
            if path == "embedded"
            else "倉野内直子（くらのうちなおこ）"
            if path == "parenthetical"
            else "榎谷\n" + "あ" * 130 + "\nエノキヤ"
        )
        return {
            "http_status": 200,
            "final_url": url,
            "content_type": "text/html; charset=utf-8",
            "content_sha256": "0" * 64,
            "text": text,
        }

    def test_fetch_and_resume(self):
        row = {
            "surface": "榎谷",
            "pronunciation": "エノキヤ",
            "status": "verified",
            "source_url": self.url,
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "in.jsonl"
            out = root / "out.jsonl"
            inp.write_text(
                json.dumps(row, ensure_ascii=False)
                + "\n"
                + json.dumps({**row, "surface": "不存在"}, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            with patch.object(audit, "fetch_document", side_effect=self.fake_fetch):
                self.assertEqual(audit.run(inp, out, workers=2, delay=0), (2, 2))
                self.assertEqual(audit.run(inp, out, workers=2, delay=0), (2, 0))
            items = [
                json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(items[0]["audit_result"], "pass")
            self.assertEqual(items[0]["http_status"], 200)
            self.assertEqual(len(items[0]["content_sha256"]), 64)
            self.assertEqual(items[0]["schema_version"], 3)
            self.assertTrue(items[0]["reading_token_boundary"])
            self.assertEqual(items[0]["matched_reading_token"], "エノキヤ")

    def test_reading_prefix_inside_longer_kana_fails(self):
        row = {
            "surface": "佐伯",
            "pronunciation": "サエキノ",
            "source_url": self.url.rsplit("/", 1)[0] + "/embedded",
        }
        with patch.object(audit, "fetch_document", side_effect=self.fake_fetch):
            got = audit.audit_row(row, 0)
        self.assertEqual(got["audit_result"], "fail")
        self.assertEqual(got["reason"], "reading_embedded_in_longer_kana")
        self.assertFalse(got["reading_token_boundary"])
        self.assertEqual(got["matched_reading_token"], "さえきの")

    def test_parenthetical_full_name_allows_surname_reading_prefix(self):
        row = {
            "surface": "倉野内",
            "pronunciation": "クラノウチ",
            "source_url": self.url.rsplit("/", 1)[0] + "/parenthetical",
        }
        with patch.object(audit, "fetch_document", side_effect=self.fake_fetch):
            got = audit.audit_row(row, 0)
        self.assertEqual(got["audit_result"], "pass")
        self.assertEqual(got["reason"], "surface_and_reading_nearby")
        self.assertTrue(got["reading_token_boundary"])
        self.assertEqual(got["matched_reading_token"], "くらのうちなおこ")

    def test_parenthetical_pair_must_have_longer_kanji_name(self):
        got = audit._near_match(
            "倉野内（くらのうちなおこ）", "倉野内", "クラノウチ", 120
        )
        self.assertFalse(got["near"])

    def test_longer_kana_without_parenthetical_full_name_still_fails(self):
        got = audit._near_match("倉野内 くらのうちなおこ", "倉野内", "クラノウチ", 120)
        self.assertFalse(got["near"])
        self.assertFalse(got["reading_token_boundary"])

    def test_far_apart_pair_fails_and_distance_is_reported(self):
        row = {
            "surface": "榎谷",
            "pronunciation": "エノキヤ",
            "source_url": self.url + "-far",
        }
        with patch.object(audit, "fetch_document", side_effect=self.fake_fetch):
            got = audit.audit_row(row, 0, max_distance=20)
        self.assertEqual(got["audit_result"], "fail")
        self.assertEqual(got["reason"], "surface_and_reading_far_apart")
        self.assertGreater(got["min_distance"], 20)
        self.assertEqual(got["match_context"], "")

    def test_pdf_style_spaces_between_glyphs_match_on_same_line(self):
        got = audit._near_match("ダンムラ ハナ\n団 村 華", "団村", "ダンムラ", 120)
        self.assertTrue(got["near"])
        self.assertTrue(got["reading_token_boundary"])

    def test_pdf_character_spaced_furigana_is_joined_without_merging_name_tokens(self):
        got = audit._near_match(
            "た い よ う じ・ ま ゆ み\n太 養 寺 真 弓",
            "太養寺",
            "タイヨウジ",
            120,
        )
        self.assertTrue(got["near"])
        self.assertTrue(got["reading_token_boundary"])
        ordinary = audit._near_match(
            "今大地 晴美 コンダイジ ハルミ", "今大地", "コンダイジ", 120
        )
        self.assertTrue(ordinary["near"])
        self.assertEqual(ordinary["matched_reading_token"], "コンダイジ")

    def test_many_repeated_occurrences_do_not_require_cartesian_scan(self):
        text = ("一里山 イチリヤマ " * 10_000).strip()
        got = audit._near_match(text, "一里山", "イチリヤマ", 120)
        self.assertTrue(got["near"])
        self.assertEqual(got["min_distance"], 1)

    def test_halfwidth_katakana_reading_is_nfkc_normalized(self):
        got = audit._near_match("下之門 悠誠 ｼﾓﾉｶﾄﾞ ﾕｳｾｲ", "下之門", "シモノカド", 120)
        self.assertTrue(got["near"])
        self.assertEqual(got["matched_reading_token"], "シモノカド")

    def test_iso2022_jp_html_without_charset_is_decoded(self):
        body = "<html><body>固武 慶（こたけ けい）</body></html>".encode("iso2022_jp")
        self.assertIn("固武", audit._html_text(body, "text/html"))
        self.assertIn("こたけ", audit._html_text(body, "text/html"))

    def test_old_schema_is_not_resumed(self):
        row = {"surface": "榎谷", "pronunciation": "エノキヤ", "source_url": self.url}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "in.jsonl"
            out = root / "out.jsonl"
            inp.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            out.write_text(
                json.dumps({"schema_version": 2, "row_number": 0}) + "\n",
                encoding="utf-8",
            )
            with patch.object(audit, "fetch_document", side_effect=self.fake_fetch):
                self.assertEqual(audit.run(inp, out, workers=1, delay=0), (1, 1))
            self.assertEqual(json.loads(out.read_text())["schema_version"], 3)

    def test_shifted_checkpoint_row_is_refetched(self):
        row = {"surface": "榎谷", "pronunciation": "エノキヤ", "source_url": self.url}
        stale = audit._base(
            {"surface": "旧姓", "pronunciation": "キュウセイ", "source_url": self.url},
            0,
        )
        stale.update(audit_result="pass", reason="stale", completed=True)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "in.jsonl"
            out = root / "out.jsonl"
            inp.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            out.write_text(
                json.dumps(stale, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            with patch.object(audit, "fetch_document", side_effect=self.fake_fetch):
                self.assertEqual(audit.run(inp, out, workers=1, delay=0), (1, 1))
            refreshed = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(refreshed["surface"], "榎谷")
            self.assertEqual(refreshed["audit_result"], "pass")

    def test_retry_errors_refetches_only_error_checkpoint(self):
        row = {"surface": "榎谷", "pronunciation": "エノキヤ", "source_url": self.url}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "in.jsonl"
            out = root / "out.jsonl"
            inp.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            failed = audit._base(row, 0)
            failed.update(audit_result="error", reason="watchdog")
            out.write_text(
                json.dumps(failed, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            self.assertEqual(audit.run(inp, out, workers=1), (1, 0))
            with patch.object(audit, "fetch_document", side_effect=self.fake_fetch):
                self.assertEqual(
                    audit.run(inp, out, workers=1, retry_errors=True), (1, 1)
                )
            self.assertEqual(json.loads(out.read_text())["audit_result"], "pass")

    def test_dictionary_is_rejected_without_fetch(self):
        row = {
            "surface": "榎谷",
            "pronunciation": "エノキヤ",
            "source_url": "https://name-power.net/fn/x.html",
        }
        with patch.object(
            audit, "fetch_document", side_effect=AssertionError("must not fetch")
        ):
            got = audit.audit_row(row, 0)
        self.assertEqual(got["audit_result"], "reject")
        self.assertEqual(got["reason"], "surname_dictionary_host")

    def test_fetch_rejects_non_https_and_private_addresses(self):
        with self.assertRaisesRegex(RuntimeError, "public HTTPS"):
            audit._curl_resolve_args("http://example.org/person")
        with self.assertRaisesRegex(RuntimeError, "non-global"):
            audit._curl_resolve_args("https://127.0.0.1/person")


if __name__ == "__main__":
    unittest.main()
