import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_myoji_negative_reviews as subject


class ApplyNegativeReviewsTest(unittest.TestCase):
    def write_result(self, path, *rows):
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def write_review(self, path, surface="榎谷", pronunciation="エノキヤ"):
        path.write_text(
            json.dumps(
                {
                    "surface": surface,
                    "pronunciation": pronunciation,
                    "decision": "reject",
                    "notes": "reviewed negative",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_applies_verified_review_and_preserves_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.jsonl"
            review = Path(directory) / "review.jsonl"
            attempts = [
                {"strategy": "exact_katakana", "result_urls": ["https://example.org/p"]}
            ]
            result.write_text(
                json.dumps(
                    {
                        "surface": "榎谷",
                        "pronunciation": "エノキヤ",
                        "status": "no_support_found",
                        "notes": "",
                        "search_attempts": attempts,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            review.write_text(
                json.dumps(
                    {
                        "surface": "榎谷",
                        "pronunciation": "エノキヤ",
                        "decision": "verified",
                        "source_url": "https://example.org/p",
                        "source_type": "sports_database",
                        "source_title": "選手名鑑",
                        "observed_surface": "榎谷礼央",
                        "observed_reading": "エノキヤ レオ",
                        "locator": "profile",
                        "notes": "",
                        "evidence_tier": "B",
                        "identity_basis": "same_profile",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(subject.apply(result, [review]), (1, 1, 1))
            changed = json.loads(result.read_text(encoding="utf-8"))
            self.assertEqual(changed["status"], "verified")
            self.assertEqual(changed["search_attempts"], attempts)

    def test_reset_unreviewed_clears_stale_verified_row(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.jsonl"
            review = Path(directory) / "review.jsonl"
            self.write_result(
                result,
                {
                    "surface": "榎谷",
                    "pronunciation": "エノキヤ",
                    "status": "no_support_found",
                },
                {
                    "surface": "旧姓",
                    "pronunciation": "キュウセイ",
                    "status": "verified",
                    "source_url": "https://old.example/",
                    "source_type": "sports_database",
                    "source_title": "old",
                    "observed_surface": "旧姓",
                    "observed_reading": "キュウセイ",
                    "locator": "old",
                    "notes": "old evidence",
                    "evidence_tier": "B",
                    "identity_basis": "same_profile",
                },
            )
            self.write_review(review)

            self.assertEqual(
                subject.apply(result, [review], reset_unreviewed=True), (2, 1, 0)
            )
            changed = [
                json.loads(line)
                for line in result.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(changed[1]["status"], "no_support_found")
            self.assertTrue(
                changed[1]["notes"].startswith("最新URL監査レビュー範囲で未採用")
            )
            self.assertTrue(
                all(
                    changed[1][field] == ""
                    for field in subject.EVIDENCE_FIELDS
                    if field != "notes"
                )
            )

    def test_default_keeps_unreviewed_verified_row(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.jsonl"
            review = Path(directory) / "review.jsonl"
            original = {
                "surface": "旧姓",
                "pronunciation": "キュウセイ",
                "status": "verified",
                "source_url": "https://old.example/",
                "notes": "old evidence",
            }
            reviewed = {
                "surface": "榎谷",
                "pronunciation": "エノキヤ",
                "status": "no_support_found",
            }
            self.write_result(result, reviewed, original)
            self.write_review(review)

            subject.apply(result, [review])
            changed = [
                json.loads(line)
                for line in result.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(changed[0]["status"], "no_support_found")
            self.assertEqual(changed[1], original)

    def test_reviewed_row_is_applied_when_resetting_unreviewed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.jsonl"
            review = Path(directory) / "review.jsonl"
            self.write_result(
                result,
                {
                    "surface": "榎谷",
                    "pronunciation": "エノキヤ",
                    "status": "verified",
                    "source_url": "https://old.example/",
                    "notes": "old evidence",
                },
                {
                    "surface": "旧姓",
                    "pronunciation": "キュウセイ",
                    "status": "verified",
                    "source_url": "https://old.example/",
                    "notes": "old evidence",
                },
            )
            self.write_review(review)

            subject.apply(result, [review], reset_unreviewed=True)
            changed = [
                json.loads(line)
                for line in result.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(changed[0]["status"], "no_support_found")
            self.assertEqual(changed[0]["notes"], "reviewed negative")
            self.assertEqual(changed[1]["status"], "no_support_found")
            self.assertTrue(
                changed[1]["notes"].startswith("最新URL監査レビュー範囲で未採用")
            )


if __name__ == "__main__":
    unittest.main()
