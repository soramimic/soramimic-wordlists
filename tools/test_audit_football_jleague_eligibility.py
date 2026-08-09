#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

import audit_football_jleague_eligibility as target


HTML = """
<table><tbody>
<tr><td><a href="/SFIX04/?player_id=173">阿井　達也</a></td>
<td>Tatsuya AI</td><td>甲府</td><td>MF</td><td>1968/04/17</td><td>169/67</td></tr>
<tr><td><a href="/SFIX04/?player_id=499">アイルトン</a></td>
<td>Ailton</td><td>清水</td><td>FW</td><td>1968/01/01</td><td>180/70</td></tr>
<tr><td><a href="/SFIX04/?player_id=6719">アイルトン</a></td>
<td>Ailton</td><td>札幌</td><td>FW</td><td>1970/01/01</td><td>180/70</td></tr>
</tbody></table>
"""


class EligibilityAuditTest(unittest.TestCase):
    def test_parses_official_rows(self):
        rows = target.parse_players(HTML)
        self.assertEqual(3, len(rows))
        self.assertEqual("173", rows[0]["player_id"])
        self.assertEqual("阿井 達也", rows[0]["registered_name"])

    def test_exact_unique_and_ambiguous_matches(self):
        manifest = [
            {"status": "accepted", "candidate_id": "0", "article": "阿井達也", "qid": "Q1",
             "original": "阿井 達也"},
            {"status": "accepted", "article": "アイルトン", "qid": "Q2",
             "original": "アイルトン"},
            {"status": "accepted", "article": "未登録", "qid": "Q3",
             "original": "未登録"},
        ]
        result = target.audit(manifest, target.parse_players(HTML))
        self.assertEqual("verified", result[0]["status"])
        self.assertEqual("0", result[0]["candidate_id"])
        self.assertEqual("173", result[0]["player_id"])
        self.assertEqual("ambiguous_registered_name", result[1]["reason"])
        self.assertEqual(2, len(result[1]["matches"]))
        self.assertEqual("official_name_not_found", result[2]["reason"])

    def test_same_registered_name_is_resolved_by_birth_date(self):
        manifest = [{"status": "accepted", "candidate_id": "2",
                     "article": "アイルトン", "original": "アイルトン",
                     "birth_date": "1970/01/01"}]
        result = target.audit(manifest, target.parse_players(HTML))
        self.assertEqual("verified", result[0]["status"])
        self.assertEqual("registered_name_and_birth_date", result[0]["method"])
        self.assertEqual("6719", result[0]["player_id"])

    def test_name_normalization(self):
        self.assertEqual(target.normalized_name("髙橋　太郎"),
                         target.normalized_name("高橋 太郎 (サッカー選手)"))
        self.assertTrue(target.latin_compatible("ADAILTON", "Adaílton dos Santos"))

    def test_birth_date_and_english_name_identity_fallback(self):
        manifest = [{
            "status": "accepted", "candidate_id": "9", "article": "本名の記事",
            "original": "長い本名", "birth_date": "1968/04/17",
            "latin_names": ["Tatsuya Ai"],
        }]
        result = target.audit(manifest, target.parse_players(HTML))
        self.assertEqual("verified", result[0]["status"])
        self.assertEqual("birth_date_and_english_name", result[0]["method"])
        self.assertEqual("173", result[0]["player_id"])

    def test_infobox_registered_name_match(self):
        manifest = [{"status": "accepted", "candidate_id": "7",
                     "article": "長い本名", "original": "長い本名"}]
        result = target.audit(manifest, target.parse_players(HTML),
                              {"長い本名": "アイルトン"})
        self.assertEqual("unverified", result[0]["status"])
        self.assertEqual("ambiguous_registered_name", result[0]["reason"])
        self.assertEqual("アウドロ", target.parse_infobox_name(
            "{{サッカー選手\n | 名前 = アウドロ\n | 本名 = 長い本名\n}}"))

    def test_verified_csv_filters_and_renumbers(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "candidates.csv"
            source.write_text(
                "id,original,surface,pronunciation,type\n"
                "4,A,A,ア,full\n4,A,A,ア,family\n"
                "8,B,B,ビ,full\n", encoding="utf-8")
            text = target.verified_csv(source, [
                {"candidate_id": "4", "status": "verified", "last_team": "甲府"},
                {"candidate_id": "8", "status": "unverified"},
            ])
            self.assertEqual(
                "id,original,surface,pronunciation,type\n"
                "0,A,A,ア,full\n0,A,A,ア,family", text)
            self.assertEqual(
                {"4": "0"}, target.verified_id_mapping(source, [
                    {"candidate_id": "4", "status": "verified"},
                    {"candidate_id": "8", "status": "unverified"},
                ]))

    def test_representative_team_maps_official_abbreviation(self):
        self.assertEqual(
            "福島ユナイテッドFC", target.representative_team(
                "東京ヴェルディ1969-福島ユナイテッドFC", "福島"))
        self.assertEqual(
            "セレッソ大阪", target.representative_team(
                "香川紫光クラブ-セレッソ大阪", "Ｃ大阪"))

    def test_public_source_record_excludes_bulk_official_fields(self):
        record = target.public_source_record({
            "verified_id": "1", "original": "選手", "article": "選手",
            "qid": "Q1", "player_id": "9", "method": "registered_name_exact",
            "url": "https://example.test/?player_id=9",
            "registered_name": "選手", "english_name": "PLAYER",
            "birth_date": "2000/01/01", "last_team": "チーム",
        })
        self.assertNotIn("english_name", record)
        self.assertNotIn("birth_date", record)
        self.assertEqual("9", record["player_id"])


if __name__ == "__main__":
    unittest.main()
