from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import threading
import unittest
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import audit_image_links as audit


class AuditImageLinksTest(unittest.TestCase):
    def setUp(self):
        self.calls: Counter[str] = Counter()
        self.routes = {
            "/ok": (200, "image/png", b"\x89PNG\r\n\x1a\n"),
            "/binary": (200, "application/octet-stream", b"\xff\xd8\xff\xe0JFIF"),
            "/html": (200, "text/html", b"<html>not an image"),
            "/pdf": (200, "application/pdf", b"%PDF-1.7"),
            "/missing": (404, "text/html", b"missing"),
            "/denied": (403, "text/html", b"denied"),
            "/blank": (200, "image/png", b" \r\n"),
        }
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.calls[self.path] += 1
                path = urlsplit(self.path).path
                if path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/ok?signature=private")
                    self.end_headers()
                    return
                code, content_type, body = owner.routes[path]
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_probe_classifies_responses_and_strips_redirect_query(self):
        expected = {
            "ok": "ok",
            "binary": "ok",
            "redirect": "ok",
            "html": "invalid",
            "pdf": "invalid",
            "missing": "broken",
            "denied": "unavailable",
            "blank": "invalid",
        }
        for path, status in expected.items():
            result = audit.probe(f"{self.base}/{path}", 1)
            self.assertEqual(result["status"], status)
            self.assertNotIn("signature", result.get("final_url", ""))

    def test_cursor_resumes_and_findings_clear_when_url_is_removed(self):
        links = {
            f"https://example.com/{number}.png": [{"wordlist": "test", "name": str(number)}]
            for number in range(5)
        }
        checked: list[str] = []

        def fake_probe(url, timeout):
            checked.append(url)
            return {
                "status": "broken" if url.endswith("0.png") else "ok",
                "http_status": 404 if url.endswith("0.png") else 200,
                "reason": "test",
            }

        with tempfile.TemporaryDirectory() as directory, patch.object(audit, "probe", fake_probe), patch.object(
            audit.time, "sleep", lambda _: None
        ):
            root = Path(directory)
            state = root / "state.json"
            report = root / "report.json"
            first, status = audit.audit(
                links, maximum=2, state_path=state, report_path=report,
                workers=1, timeout=1, delay=0,
            )
            self.assertEqual(status, 1)
            self.assertEqual(first["checked_urls"], 2)
            second, status = audit.audit(
                links, maximum=2, state_path=state, report_path=report,
                workers=1, timeout=1, delay=0,
            )
            self.assertEqual(status, 1)
            self.assertEqual(len(set(checked)), 4)
            del links["https://example.com/0.png"]
            third, status = audit.audit(
                links, maximum=2, state_path=state, report_path=report,
                workers=1, timeout=1, delay=0,
            )
            self.assertEqual(status, 0)
            self.assertEqual(third["cycle"], 1)
            self.assertEqual(third["known_findings"], [])
            self.assertEqual(json.loads(state.read_text())["findings"], {})

    def test_changed_links_only_returns_new_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            path = root / "list.csv"
            self.write_csv(path, [("A", "https://example.com/a.png")])
            subprocess.run(["git", "add", "list.csv"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            self.write_csv(path, [
                ("A changed", "https://example.com/a.png"),
                ("B", "https://example.com/b.png"),
            ])
            subprocess.run(["git", "commit", "-qam", "head"], cwd=root, check=True)
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            with patch.object(audit.subprocess, "run", wraps=subprocess.run):
                previous = Path.cwd()
                try:
                    import os
                    os.chdir(root)
                    links = audit.changed_links(base, head)
                finally:
                    os.chdir(previous)
            self.assertEqual(list(links), ["https://example.com/b.png"])

    @staticmethod
    def write_csv(path: Path, rows: list[tuple[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["id", "original", "surface", "pronunciation", "image"])
            for index, (name, image) in enumerate(rows):
                writer.writerow([index, name, name, name, image])


if __name__ == "__main__":
    unittest.main()
