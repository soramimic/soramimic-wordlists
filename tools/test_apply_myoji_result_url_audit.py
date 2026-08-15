import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import apply_myoji_result_url_audit as tool


class ResultAuditApplyTest(unittest.TestCase):
    def test_demotes_exact_rejected_evidence_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = root / "2026-08-14-p1-a.jsonl"
            queue = root / "q.jsonl"
            row = {
                "surface": "榎谷",
                "pronunciation": "エノキヤ",
                "status": "verified",
                "source_url": "https://example.jp/p",
                "source_type": "official_person_profile",
                "source_title": "P",
                "observed_surface": "榎谷",
                "observed_reading": "エノキヤ",
                "locator": "x",
                "evidence_tier": "A",
                "identity_basis": "same_profile",
                "notes": "",
                "search_attempts": [],
            }
            result.write_text(
                json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            queue.write_text(
                json.dumps(
                    {
                        "surface": "榎谷",
                        "pronunciation": "エノキヤ",
                        "source_url": "https://example.jp/p",
                        "audit_result": "fail",
                        "reason": "reading_missing",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                tool.apply("2026-08-14-p1", [queue], True, root)["changed"], 1
            )
            got = json.loads(result.read_text(encoding="utf-8"))
            self.assertEqual(got["status"], "ambiguous")
            self.assertEqual(got["source_url"], "")
            self.assertIn("reading_missing", got["notes"])


if __name__ == "__main__":
    unittest.main()
