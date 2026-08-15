import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import finalize_myoji_negative_audits as subject


class FinalizeNegativeAuditsTest(unittest.TestCase):
    def write(self, path, rows):
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def base(self, surface, pronunciation):
        return {
            "surface": surface,
            "pronunciation": pronunciation,
            "status": "ambiguous",
            "notes": "old",
            "search_attempts": [
                {"strategy": "exact_katakana", "response_sha256": "keep"}
            ],
        }

    def review(self, surface, pronunciation, decision):
        row = {
            "surface": surface,
            "pronunciation": pronunciation,
            "decision": decision,
            "notes": "Luna decision",
        }
        if decision == "verified":
            row.update(
                source_url="https://example.org/person",
                source_type="sports_database",
                source_title="Roster",
                observed_surface=surface,
                observed_reading=pronunciation,
                locator="profile",
                evidence_tier="B",
                identity_basis="same_profile",
            )
        return row

    def test_finalizes_verified_rejected_ambiguous_and_no_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = root / "result.jsonl"
            audit = root / "audit.jsonl"
            review = root / "review.jsonl"
            rows = [
                self.base("確認", "カクニン"),
                self.base("拒否", "キョヒ"),
                self.base("保留", "ホリュウ"),
                self.base("無通過", "ムツウカ"),
            ]
            self.write(result, rows)
            self.write(
                audit,
                [
                    {
                        "surface": "確認",
                        "pronunciation": "カクニン",
                        "source_url": "https://example.org/person",
                        "audit_result": "pass",
                    },
                    {
                        "surface": "拒否",
                        "pronunciation": "キョヒ",
                        "audit_result": "pass",
                    },
                    {
                        "surface": "保留",
                        "pronunciation": "ホリュウ",
                        "audit_result": "pass",
                    },
                ],
            )
            self.write(
                review,
                [
                    self.review("確認", "カクニン", "verified"),
                    self.review("拒否", "キョヒ", "reject"),
                    self.review("保留", "ホリュウ", "ambiguous"),
                ],
            )
            counts = subject.finalize([result], [audit], [review])
            changed = [json.loads(x) for x in result.read_text().splitlines()]
            self.assertEqual(
                [x["status"] for x in changed],
                ["verified", "no_support_found", "ambiguous", "no_support_found"],
            )
            self.assertEqual(changed[0]["search_attempts"], rows[0]["search_attempts"])
            self.assertEqual(counts["verified"], 1)
            self.assertEqual(counts["no_support_found"], 2)

    def test_verified_review_requires_pass_for_the_same_url(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = root / "result.jsonl"
            audit = root / "audit.jsonl"
            review = root / "review.jsonl"
            original = self.base("確認", "カクニン")
            self.write(result, [original])
            self.write(
                audit,
                [
                    {
                        "surface": "確認",
                        "pronunciation": "カクニン",
                        "source_url": "https://example.org/other",
                        "audit_result": "pass",
                    }
                ],
            )
            self.write(review, [self.review("確認", "カクニン", "verified")])
            with self.assertRaisesRegex(RuntimeError, "same URL"):
                subject.finalize([result], [audit], [review])
            self.assertEqual(json.loads(result.read_text()), original)

    def test_audit_error_keeps_nonverified_ambiguous_without_review(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = root / "result.jsonl"
            audit = root / "audit.jsonl"
            self.write(result, [self.base("障害", "ショウガイ")])
            self.write(
                audit,
                [
                    {
                        "surface": "障害",
                        "pronunciation": "ショウガイ",
                        "audit_result": "error",
                    }
                ],
            )
            subject.finalize([result], [audit], [])
            self.assertEqual(json.loads(result.read_text())["status"], "ambiguous")

    def test_audit_pass_without_review_is_error_and_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = root / "result.jsonl"
            audit = root / "audit.jsonl"
            original = self.base("不足", "フソク")
            self.write(result, [original])
            self.write(
                audit,
                [
                    {
                        "surface": "不足",
                        "pronunciation": "フソク",
                        "audit_result": "pass",
                    }
                ],
            )
            with self.assertRaisesRegex(RuntimeError, "requires Luna review"):
                subject.finalize([result], [audit], [])
            self.assertEqual(json.loads(result.read_text()), original)


if __name__ == "__main__":
    unittest.main()
