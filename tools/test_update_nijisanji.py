import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_nijisanji as target


def next_page(page_props):
    payload = {"props": {"pageProps": page_props}}
    return ('<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload, ensure_ascii=False) + "</script>")


class UpdateNijisanjiTest(unittest.TestCase):
    def test_roster_filters_supported_affiliations(self):
        old_guard = target.COUNT_GUARD
        target.COUNT_GUARD = (2, 2)
        self.addCleanup(setattr, target, "COUNT_GUARD", old_guard)
        page = next_page({"allLivers": [
            {"name": " 不破 湊 ", "slug": "minato-fuwa",
             "profile": {"affiliation": ["にじさんじ"]}},
            {"name": "闇ノシュウ", "slug": "shu-yamino",
             "profile": {"affiliation": ["NIJISANJI EN"]}},
            {"name": "艾因", "slug": "ein",
             "profile": {"affiliation": ["VirtuaReal"]}},
        ]})

        got = target.parse_roster(page)

        self.assertEqual([item["name"] for item in got], ["不破湊", "闇ノシュウ"])

    def test_detail_uses_official_reading_channel_and_color(self):
        page = next_page({"liverDetail": {
            "name": "不破湊", "slug": "minato-fuwa", "ruby": "ふわ みなと",
            "profile": {"affiliation": ["にじさんじ"],
                        "debutAt": "2019-11-27T15:00:00.000Z",
                        "color": "#BF69F4"},
            "channelId": "UC" + "a" * 22,
            "channelName": "不破 湊 / Fuwa Minato【にじさんじ】",
        }})

        got = target.parse_detail(page, {
            "name": "不破湊", "slug": "minato-fuwa",
            "affiliation": "にじさんじ"})

        self.assertEqual(got["ruby"], "フワミナト")
        self.assertEqual(got["debut_year"], "2019")
        self.assertEqual(got["color"], "#bf69f4")

    def test_apply_roster_adds_full_row_and_backfills_existing(self):
        cols = ["id", "original", "surface", "pronunciation", "type",
                "category", "org", "debut_year", "status", "image",
                "image_page", "wikidata", "channel", "description",
                "subscribers", "subscribers_as_of", "scope"]
        rows = [{col: "" for col in cols}]
        rows[0].update({"id": "4", "original": "静凛", "surface": "静凛",
                        "pronunciation": "シズカリン", "type": "full",
                        "category": "vtuber", "org": "NA",
                        "debut_year": "2018", "status": "current",
                        "channel": "NA", "description": "既存説明。",
                        "subscribers": "NA", "subscribers_as_of": "NA"})
        details = [
            {"name": "静凛", "ruby": "シズカリン", "affiliation": "にじさんじ",
             "debut_year": "2018", "channel": "ShizuRin Official"},
            {"name": "不破湊", "ruby": "フワミナト", "affiliation": "にじさんじ",
             "debut_year": "2019", "channel": "不破 湊 Official"},
        ]

        people, added, ids = target.apply_roster(rows, cols, details)

        self.assertEqual((people, added), (1, 1))
        self.assertEqual(rows[0]["org"], "にじさんじ")
        self.assertEqual(rows[0]["description"], "既存説明。")
        self.assertEqual(rows[1]["type"], "full")
        self.assertEqual(rows[1]["pronunciation"], "フワミナト")
        self.assertEqual(rows[1]["scope"], "japan")
        self.assertEqual(ids["不破湊"], "5")


if __name__ == "__main__":
    unittest.main()
