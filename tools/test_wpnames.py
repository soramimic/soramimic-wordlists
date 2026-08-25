import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import (has_redundant_player_subject, is_likely_disambiguation_text,
                     make_player_description, strip_name_prefix)


class PlayerDescriptionSubjectTest(unittest.TestCase):
    def test_birth_and_death_date_dash_is_not_disambiguation(self):
        self.assertFalse(is_likely_disambiguation_text(
            "山田太郎（1989年10月2日 - ）は、日本のプロ野球選手。"
        ))
        self.assertFalse(is_likely_disambiguation_text(
            "山田太郎（1930年 - 2020年）は、日本の元サッカー選手。"
        ))
        self.assertEqual(
            "日本のプロ野球選手。",
            make_player_description(
                "山田 太郎（やまだ たろう、1989年10月2日 - ）は、"
                "日本のプロ野球選手。",
                "山田太郎",
            ),
        )

    def test_disambiguation_entry_dash_is_detected(self):
        self.assertTrue(is_likely_disambiguation_text(
            "山田太郎（野球選手） - 日本のプロ野球選手。"
        ))
        self.assertTrue(is_likely_disambiguation_text(
            "池田弘 - 西武ライオンズに所属した元投手。"
        ))

    def test_detects_unrelated_full_name_subject_by_player_role(self):
        self.assertTrue(has_redundant_player_subject(
            "ロバート・ジョゼフ・アーリンは、"
            "アメリカ合衆国出身のプロ野球選手。"
        ))

    def test_ignores_non_name_subject_by_player_role(self):
        self.assertFalse(has_redundant_player_subject(
            "現役時代は、プロ野球選手として活躍した。"
        ))
        self.assertFalse(has_redundant_player_subject(
            "愛知県出身（出生地は秋田県）のプロ野球選手。"
        ))
        self.assertFalse(has_redundant_player_subject(
            "父のジョン・サディナは元プロ野球選手。"
        ))

    def test_player_description_removes_middle_name_subject(self):
        self.assertEqual(
            "アメリカ合衆国ハワイ準州出身の元プロ野球選手。",
            make_player_description(
                "ジョン・トーマス・サディナは、"
                "アメリカ合衆国ハワイ準州出身の元プロ野球選手。",
                "ジョン・サディナ",
            ),
        )

    def test_player_description_uses_willie_upshaw_override(self):
        self.assertEqual(
            "1989年に福岡ダイエーで33本塁打・80打点を記録。",
            make_player_description(
                "ウィリー・アップショーは、アメリカ合衆国出身の元プロ野球選手。",
                "ウィリー・アップショー",
            ),
        )

    def test_player_description_override_can_be_disabled_for_source_selection(self):
        source = "大谷翔平は、日本のプロ野球選手。"
        self.assertEqual(
            "日本のプロ野球選手。",
            make_player_description(source, "大谷翔平", allow_override=False),
        )

    def test_removes_middle_name_subject(self):
        self.assertEqual(
            "アメリカ合衆国出身の元プロ野球選手。",
            strip_name_prefix(
                "クリストファー・ポール・アーノルドは、"
                "アメリカ合衆国出身の元プロ野球選手。",
                "クリス・アーノルド",
            ),
        )

    def test_keeps_unrelated_subject(self):
        self.assertEqual(
            "父は元プロ野球選手。",
            strip_name_prefix("父は元プロ野球選手。", "架空太郎"),
        )

    def test_keeps_relative_with_player_name(self):
        description = "父のジョン・サディナは元プロ野球選手。"
        self.assertEqual(
            description,
            strip_name_prefix(description, "ジョン・サディナ"),
        )

    def test_keeps_time_period_subject(self):
        description = "現役時代は、投手としてプレーした。"
        self.assertEqual(description, strip_name_prefix(description, "架空太郎"))

    def test_keeps_later_name_subject(self):
        description = (
            "サイ・ヤング賞受賞者の息子がメジャーリーグでプレーしたのは"
            "バンス・ローが史上初である。"
        )
        self.assertEqual(description, strip_name_prefix(description, "バンスロー"))


if __name__ == "__main__":
    unittest.main()
