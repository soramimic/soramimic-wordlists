import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_player_positions import position_from_description


class PositionFromDescriptionTests(unittest.TestCase):
    def test_extracts_parenthesized_baseball_position(self):
        self.assertEqual(
            "投手",
            position_from_description(
                "baseball", "神奈川県出身の元プロ野球選手（投手、右投右打）。"
            ),
        )

    def test_normalizes_multiple_positions_in_canonical_order(self):
        self.assertEqual(
            "捕手/内野手/外野手",
            position_from_description(
                "baseball", "日本のプロ野球選手（外野手、捕手、内野手）。"
            ),
        )

    def test_accepts_ascii_parentheses_and_role_before_parentheses(self):
        self.assertEqual(
            "捕手",
            position_from_description(
                "baseball", "日本のプロ野球選手・コーチ(捕手)。"
            ),
        )

    def test_accepts_direct_professional_baseball_title(self):
        self.assertEqual(
            "内野手",
            position_from_description("baseball", "東京都出身の元プロ野球内野手。"),
        )

    def test_rejects_position_of_a_relative(self):
        self.assertEqual(
            "",
            position_from_description(
                "baseball", "実父はツインズの捕手として活躍したブライアン・ハーパー。"
            ),
        )

    def test_rejects_position_mentioned_only_in_an_achievement(self):
        self.assertEqual(
            "",
            position_from_description(
                "baseball", "1997年には先発投手として10勝を挙げた。"
            ),
        )

    def test_does_not_apply_baseball_rules_to_football(self):
        self.assertEqual(
            "",
            position_from_description("football", "元プロ野球選手（投手）。"),
        )


if __name__ == "__main__":
    unittest.main()
