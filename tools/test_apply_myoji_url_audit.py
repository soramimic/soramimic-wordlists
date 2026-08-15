import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import apply_myoji_url_audit as tool


class ApplyAuditTest(unittest.TestCase):
    def _write(self, path, rows):
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def test_dry_run_and_apply_pass_only_with_queue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = root / "ledger.jsonl"
            report = root / "report.jsonl"
            queue = root / "queue.jsonl"
            backup = root / "backup.jsonl"
            source = [
                {
                    "surface": "榎谷",
                    "pronunciation": "エノキヤ",
                    "source_url": "https://a.example/p",
                },
                {
                    "surface": "佐伯",
                    "pronunciation": "サエキノ",
                    "source_url": "https://b.example/p",
                },
            ]
            audits = [
                {
                    "schema_version": 3,
                    "row_number": i,
                    **row,
                    "completed": True,
                    "audit_result": "pass" if i == 0 else "fail",
                    "reason": "surface_and_reading_far_apart"
                    if i
                    else "surface_and_reading_nearby",
                    "match_context": "ctx",
                    "min_distance": 3,
                    "reading_token_boundary": True,
                    "matched_reading_token": row["pronunciation"],
                }
                for i, row in enumerate(source)
            ]
            self._write(ledger, source)
            self._write(report, audits)
            got = tool.apply(ledger, report, queue, backup, False)
            self.assertEqual(
                got, {"input": 2, "retained": 1, "queued": 1, "applied": False}
            )
            self.assertFalse(backup.exists())
            self.assertEqual(
                ledger.read_text(encoding="utf-8"),
                "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in source),
            )
            tool.apply(ledger, report, queue, backup, True)
            self.assertEqual(len(ledger.read_text(encoding="utf-8").splitlines()), 1)
            self.assertEqual(
                json.loads(ledger.read_text(encoding="utf-8"))["locator"], "ctx"
            )
            self.assertEqual(len(queue.read_text(encoding="utf-8").splitlines()), 1)
            self.assertEqual(
                backup.read_text(encoding="utf-8"),
                "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in source),
            )

    def test_mismatch_duplicate_and_old_schema_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = root / "l"
            report = root / "r"
            self._write(
                ledger,
                [{"surface": "榎谷", "pronunciation": "エノキヤ", "source_url": "u"}],
            )
            base = {
                "row_number": 0,
                "surface": "榎谷",
                "pronunciation": "エノキヤ",
                "source_url": "u",
                "completed": True,
                "audit_result": "pass",
            }
            self._write(report, [{"schema_version": 2, **base}])
            with self.assertRaises(ValueError):
                tool.prepare(ledger, report)
            self._write(
                report, [{"schema_version": 3, **base}, {"schema_version": 3, **base}]
            )
            with self.assertRaises(ValueError):
                tool.prepare(ledger, report)


if __name__ == "__main__":
    unittest.main()
