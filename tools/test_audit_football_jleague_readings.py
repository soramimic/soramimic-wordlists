import csv
import json
import tempfile
import unittest
from pathlib import Path

import audit_football_jleague_readings as target


class ReadingAuditTests(unittest.TestCase):
    def test_parse_failure_is_review_warning(self):
        issues = target.audit_manifest([{
            "article": "解析不能選手", "status": "rejected",
            "reason": "reading_unparsed", "reading_provider": "ja.wikipedia.org:intro",
        }])
        self.assertEqual(["wikipedia_parse_person_failed"], [i.code for i in issues])
        self.assertEqual("warning", issues[0].severity)

    def test_accepted_romanization_guess_is_error(self):
        issues = target.audit_manifest([{
            "article": "大久保嘉人", "status": "accepted",
            "reading_provider": "jleague-english-romaji",
            "reading_evidence": {
                "method": "romanization_guess", "status": "verified",
                "player_id": "6502",
                "url": "https://data.j-league.or.jp/SFIX04/?player_id=6502",
            },
        }])
        self.assertIn("romanization_guess_accepted", {i.code for i in issues})

    def test_verified_registered_katakana_passes(self):
        issues = target.audit_manifest([{
            "article": "外国籍選手", "status": "accepted",
            "reading_provider": "jleague-official",
            "reading_evidence": {
                "method": "registered_katakana", "status": "verified",
                "player_id": "10247",
                "url": "https://data.j-league.or.jp/SFIX04/?player_id=10247",
                "registered_name": "イ・ジョンス",
                "resolved_reading": "イ ジョンス",
            },
        }])
        self.assertEqual([], issues)

    def test_wikipedia_reading_evidence_is_not_treated_as_jleague(self):
        issues = target.audit_manifest([{
            "article": "青山敏弘", "status": "accepted",
            "reading_provider": "ja.wikipedia.org:intro",
            "reading_evidence": {
                "method": "wikipedia_intro", "status": "verified",
                "source": "https://ja.wikipedia.org/wiki/青山敏弘",
                "revision_id": "123456",
            },
        }])
        self.assertEqual([], issues)

    def test_jleague_evidence_source_triggers_individual_source_checks(self):
        issues = target.audit_manifest([{
            "article": "青山敏弘", "status": "accepted",
            "reading_provider": "fallback-provider",
            "reading_evidence": {
                "source": "Jリーグ公式", "method": "katakana_search_match",
                "status": "verified", "identity_match": True,
            },
        }])
        self.assertIn("missing_individual_official_source", {i.code for i in issues})

    def test_katakana_search_requires_identity_match(self):
        issues = target.audit_manifest([{
            "article": "青山敏弘", "status": "accepted",
            "reading_provider": "jleague-official",
            "reading_evidence": {
                "method": "katakana_search_match", "status": "verified",
                "player_id": "7647",
                "url": "https://data.j-league.or.jp/SFIX04/?player_id=7647",
            },
        }])
        self.assertIn("katakana_search_identity_unverified", {i.code for i in issues})

    def test_csv_rejects_changed_katakana_registered_name(self):
        rows = [{
            "id": "1", "surface": "ドド", "pronunciation": "ドードー", "type": "full",
        }]
        issues = target.audit_candidates(rows)
        self.assertIn("katakana_registered_name_mismatch", {i.code for i in issues})

    def test_cli_exit_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates.csv"
            with candidates.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=["id", "surface", "pronunciation", "type"])
                writer.writeheader()
                writer.writerow({
                    "id": "0", "surface": "山田 太郎",
                    "pronunciation": "ヤマダ タロウ", "type": "full",
                })
            manifest = root / "manifest.jsonl"
            manifest.write_text(json.dumps({
                "article": "未解析", "status": "rejected",
                "reason": "reading_unparsed", "reading_provider": "ja.wikipedia.org:intro",
            }, ensure_ascii=False), encoding="utf-8")
            common = ["--candidates", str(candidates), "--manifest", str(manifest)]
            self.assertEqual(0, target.main(common))
            self.assertEqual(1, target.main(common + ["--fail-on", "warning"]))


if __name__ == "__main__":
    unittest.main()
