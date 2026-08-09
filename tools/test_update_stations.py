"""update_stations.py の説明文生成をネットワークなしで検証する。"""

import csv
import re
import unittest
from pathlib import Path

from update_stations import compact_station_description, make_station_description


class StationDescriptionTest(unittest.TestCase):
    def test_distinctive_description_has_priority_over_opening_year(self):
        intro = (
            "別府駅は、福岡県福岡市城南区にある福岡市地下鉄の駅。"
            "駅のシンボルマークは西島雅幸がデザインした。"
        )
        self.assertEqual(
            "駅のシンボルマークは西島雅幸がデザイン。",
            make_station_description(
                intro, "", "別府駅", "2005", "福岡県", "城南区",
                "福岡市交通局",
            ),
        )

    def test_long_distinctive_description_is_not_replaced_by_opening_year(self):
        description = (
            "日本の現存する駅で唯一「幸福」が駅名として使用されており、"
            "岡留熊野座神社が幸福神社と呼ばれることが由来となっている。"
        )
        expected = description.replace("由来となっている。", "由来。")
        self.assertEqual(
            expected,
            compact_station_description(description, "1989"),
        )

    def test_ordinary_station_uses_opening_year_only(self):
        self.assertEqual(
            "1890年開業。",
            make_station_description(
                "相生駅は、兵庫県相生市本郷町にある西日本旅客鉄道の駅。",
                "", "相生駅", "1890", "兵庫県", "相生市", "JR西日本",
            ),
        )

    def test_opening_year_only_is_default_without_feature(self):
        self.assertEqual(
            "1927年開業。",
            compact_station_description("駅。", "1927"),
        )

    def test_distinctive_wikidata_fallback_has_priority_over_opening_year(self):
        self.assertEqual(
            "駅名は近隣の温泉に由来する。",
            compact_station_description(
                "駅。", "1927", "駅名は近隣の温泉に由来する。"
            ),
        )

    def test_missing_article_falls_back_to_opening_year(self):
        self.assertEqual(
            "1880年開業。",
            make_station_description(
                "", "", "", "1880", "北海道", "札幌市", "JR北海道",
            ),
        )

    def test_ordinary_station_without_opening_year_is_empty(self):
        self.assertEqual(
            "NA",
            compact_station_description("東京都狛江市にある駅。"),
        )

    def test_operator_and_routes_do_not_repeat_card_metadata(self):
        self.assertEqual(
            "1923年開業。",
            compact_station_description("駅。", "1923"),
        )

    def test_generated_csv_uses_opening_year_without_feature(self):
        csv_path = Path(__file__).resolve().parents[1] / "stations.csv"
        with csv_path.open(encoding="utf-8") as file:
            rows = list(csv.DictReader(file))

        year_only = [
            row for row in rows
            if re.fullmatch(r"\d{4}年開業。", row["description"])
        ]
        self.assertGreater(len(year_only), 8000)
        self.assertFalse(any("に所在。" in row["description"] for row in rows))
        self.assertFalse(any("路線は" in row["description"] for row in rows))

        empty = [row for row in rows if not row["description"]]
        for row in empty:
            self.assertFalse(row["opened_year"])

        for row in rows:
            expected = compact_station_description(
                row["description"], row["opened_year"]
            )
            self.assertEqual("" if expected == "NA" else expected, row["description"])

        self.assertFalse(any(
            row["description"].rstrip().endswith(("…", "...")) for row in rows
        ))

        by_qid = {row["wikidata"]: row for row in rows}
        self.assertEqual("1890年開業。", by_qid["Q1132350"]["description"])
        self.assertEqual("1929年開業。", by_qid["Q4697555"]["description"])
        self.assertEqual(
            "駅のシンボルマークは西島雅幸がデザイン。",
            by_qid["Q4357195"]["description"],
        )


if __name__ == "__main__":
    unittest.main()
