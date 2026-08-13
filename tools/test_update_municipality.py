import unittest

from update_municipality import COLS, build_group, municipality_type


class UpdateMunicipalityTest(unittest.TestCase):
    def test_municipality_type_uses_formal_name_suffix(self):
        self.assertEqual("市", municipality_type("札幌市"))
        self.assertEqual("区", municipality_type("中央区"))
        self.assertEqual("町", municipality_type("日の出町"))
        self.assertEqual("村", municipality_type("読谷村"))
        self.assertEqual("", municipality_type("札幌"))

    def test_schema_appends_municipality_type(self):
        self.assertEqual("municipality_type", COLS[-1])

    def test_full_and_short_rows_share_municipality_type(self):
        group = {
            "id": "0",
            "original": "日の出町",
            "pronunciation": "ヒノデマチ",
            "prefecture": "東京都",
            "parent": "",
            "status": "current",
            "population": "16701",
            "code": "133051",
            "description": "東京都の町。",
            "wikidata": "Q1359472",
        }

        rows = build_group(group, {})

        self.assertEqual(["full", "short"], [row["type"] for row in rows])
        self.assertEqual(["町", "町"],
                         [row["municipality_type"] for row in rows])


if __name__ == "__main__":
    unittest.main()
