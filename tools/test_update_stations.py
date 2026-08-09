"""update_stations.py の説明文生成をネットワークなしで検証する。"""

import csv
import re
import unittest
from pathlib import Path

from update_stations import compact_station_description, make_station_description


class StationDescriptionTest(unittest.TestCase):
    def test_distinctive_description_has_priority_over_station_facts(self):
        intro = (
            "別府駅は、福岡県福岡市城南区にある福岡市地下鉄の駅。"
            "駅のシンボルマークは西島雅幸がデザインした。"
        )
        self.assertEqual(
            "駅のシンボルマークは西島雅幸がデザイン。",
            make_station_description(
                intro, "", "別府駅", "2005", "福岡県", "城南区",
                "福岡市交通局", "福岡市交通局 七隈線",
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
            compact_station_description(
                description, "1989", "", "熊本県", "あさぎり町",
                "くま川鉄道", "くま川鉄道 湯前線",
            ),
        )

    def test_ordinary_station_uses_detailed_location_and_year(self):
        self.assertEqual(
            "相生市本郷町に所在。1890年開業。",
            make_station_description(
                "相生駅は、兵庫県相生市本郷町にある西日本旅客鉄道の駅。",
                "", "相生駅", "1890", "兵庫県", "相生市", "JR西日本",
                "JR西日本 山陽新幹線／JR西日本 山陽本線／JR西日本 赤穂線",
            ),
        )

    def test_opening_year_only_is_last_resort(self):
        self.assertEqual(
            "1927年開業。",
            compact_station_description("駅。", "1927"),
        )

    def test_missing_article_falls_back_to_station_facts(self):
        self.assertEqual(
            "札幌市に所在。1880年開業。",
            make_station_description(
                "", "", "", "1880", "北海道", "札幌市", "JR北海道",
                "JR北海道 函館本線",
            ),
        )

    def test_facts_without_opening_year_remain_useful(self):
        self.assertEqual(
            "狛江市に所在。",
            compact_station_description(
                "東京都狛江市にある駅。", "", "", "東京都", "狛江市",
                "小田急電鉄", "小田急電鉄 小田急小田原線",
            ),
        )

    def test_routes_are_fallback_when_city_is_unknown(self):
        self.assertEqual(
            "山陽電気鉄道の駅。路線は山陽電気鉄道本線。1923年開業。",
            compact_station_description(
                "駅。", "1923", "", "兵庫県", "",
                "山陽電気鉄道", "山陽電気鉄道本線",
            ),
        )

    def test_generated_csv_does_not_collapse_to_opening_year(self):
        csv_path = Path(__file__).resolve().parents[1] / "stations.csv"
        with csv_path.open(encoding="utf-8") as file:
            rows = list(csv.DictReader(file))

        year_only = [
            row for row in rows
            if re.fullmatch(r"\d{4}年開業。", row["description"])
        ]
        self.assertLessEqual(len(year_only), 10)
        for row in year_only:
            self.assertFalse(any(row[key] for key in ("city", "operator", "lines")))

        empty = [row for row in rows if not row["description"]]
        for row in empty:
            self.assertFalse(any(
                row[key] for key in ("city", "operator", "lines", "opened_year")
            ))

        self.assertFalse(any(
            row["description"].rstrip().endswith(("…", "...")) for row in rows
        ))


if __name__ == "__main__":
    unittest.main()
