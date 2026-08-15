import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import audit_myoji_web_research as audit


class EvidenceLedgerValidationTest(unittest.TestCase):
    def test_current_ledger_and_v3_report(self):
        ledger = Path(__file__).with_name("myoji_web_evidence.jsonl")
        report = Path(__file__).with_name("myoji_web_evidence_url_audit.jsonl")
        expected = sum(
            1
            for line in ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        self.assertEqual(audit.validate_evidence_ledger(ledger, report), expected)

    def test_missing_audit_pass_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = root / "ledger.jsonl"
            report = root / "report.jsonl"
            row = {
                "surface": "田中",
                "pronunciation": "タナカ",
                "status": "verified",
                "source_url": "https://example.org/p",
                "source_type": "person_database",
                "source_title": "x",
                "observed_surface": "田中",
                "observed_reading": "タナカ",
                "locator": "x",
                "identity_basis": "same_record",
                "evidence_tier": "B",
                "retrieved_on": "2026-08-14",
            }
            ledger.write_text(
                json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            report.write_text(
                json.dumps(
                    {
                        "schema_version": 3,
                        "completed": True,
                        "audit_result": "fail",
                        **row,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                audit.validate_evidence_ledger(ledger, report)


if __name__ == "__main__":
    unittest.main()
