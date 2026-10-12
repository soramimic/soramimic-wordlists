import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_baseball as target


class PlayerIdentityTest(unittest.TestCase):
    def test_homonyms_match_verified_article_to_separate_ids(self):
        ids = {"松本竜也": {"left", "right"}}
        verified = {"松本竜也 (左投手)": "left", "松本竜也 (右投手)": "right"}
        self.assertEqual("left", target.existing_player_id("松本竜也 (左投手)", ids, verified))
        self.assertEqual("right", target.existing_player_id("松本竜也 (右投手)", ids, verified))
        self.assertIsNone(target.existing_player_id("松本竜也", ids, verified))
        self.assertIsNone(target.existing_player_id("松本竜也 (別人)", ids, verified))

    def test_single_existing_player_still_matches_qualified_article(self):
        self.assertEqual("1", target.existing_player_id(
            "田中直樹 (野球)", {"田中直樹": {"1"}}, {}))
        self.assertIsNone(target.existing_player_id("新しい選手", {"田中直樹": {"1"}}, {}))
        self.assertEqual("1", target.existing_player_id(
            "田中直樹 (野球)", {"田中直樹": {"1"}}, {"田中直樹 (野球)": "deleted"}))

    def test_roster_retains_disambiguating_article_title(self):
        text = "| title = 選手\n| group1 = 投手\n* [[松本竜也 (右投手)|松本竜也]]"
        with mock.patch.object(target, "template_wikitext", return_value=text):
            self.assertEqual([("松本竜也 (右投手)", "松本竜也", "投手")], target.roster("広島"))


if __name__ == "__main__":
    unittest.main()
