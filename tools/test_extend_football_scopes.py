import csv
import io
import tempfile
import unittest
from pathlib import Path

import extend_football_scopes as target


class FakeWiki:
    def pages(self, titles):
        data = {
            "海外 太郎": {"canonical_title": "海外 太郎", "qid": "Q2",
                "extract": "海外 太郎（かいがい たろう）は、日本のサッカー選手。ポジションはMF。",
                "pageimage": "Overseas.jpg"},
            "J既存 選手": {"canonical_title": "J既存 選手", "qid": "Q1",
                "extract": "J既存 選手（じぇいきぞん せんしゅ）は、日本のサッカー選手。"},
            "世界 花子": {"canonical_title": "世界 花子", "qid": "Q3",
                "extract": "世界 花子（せかい はなこ）は、著名なサッカー選手。ポジションはFW。"},
            "偽陽性": {"canonical_title": "偽陽性", "qid": "Q4",
                "extract": "偽陽性は、サッカー選手を扱う一覧。"},
            "難読人": {"canonical_title": "難読人", "qid": "Q5",
                "extract": "難読人は、日本のサッカー選手。"},
            "所属不明": {"canonical_title": "所属不明", "qid": "Q6",
                "extract": "所属不明は、日本のサッカー選手。"},
        }
        for index, name in enumerate(("中井卓大", "三都主", "大城蛍", "久保木優", "川上靖"), 10):
            data[name] = {"canonical_title": name, "qid": f"Q{index}",
                          "extract": f"{name}は、日本のサッカー選手。"}
        for index, name in enumerate(
                ("丸山桂里奈", "川崎咲耶", "曽根七海", "稲山美優", "藤尾きらら"), 20):
            data[name] = {"canonical_title": name, "qid": f"Q{index}",
                          "extract": f"{name}は、日本のサッカー選手。"}
        return {title: data[title] for title in titles}


class FakeWikidata:
    def __init__(self):
        self.seen_minimum = None

    def famous_candidates(self, minimum_sitelinks):
        self.seen_minimum = minimum_sitelinks
        return [
            {"qid": "Q3", "title": "世界 花子", "sitelinks": 150},
            {"qid": "Q2", "title": "海外 太郎", "sitelinks": 120},
            {"qid": "Q4", "title": "偽陽性", "sitelinks": 110},
            {"qid": "Q5", "title": "難読人", "sitelinks": 105},
            # overseas側で不採用でもworldへ落としてはならない。
            {"qid": "Q10", "title": "中井卓大", "sitelinks": 100},
        ]

    def overseas_japanese_candidates(self):
        eligible = {"eligibility_status": "eligible",
                    "eligibility_reason": "all_club_countries_verified_non_japan",
                    "domestic_clubs": [], "foreign_clubs": ["Q900"],
                    "unknown_memberships": [], "ignored_non_club_memberships": []}
        items = [
            {"qid": "Q2", "title": "海外 太郎", **eligible},
            {"qid": "Q1", "title": "J既存 選手", **eligible},
        ]
        for index, name in enumerate(("中井卓大", "三都主", "大城蛍", "久保木優", "川上靖"), 10):
            items.append({"qid": f"Q{index}", "title": name,
                          "eligibility_status": "rejected",
                          "eligibility_reason": "domestic_club_history",
                          "domestic_clubs": [f"QJ{index}"], "foreign_clubs": ["Q900"],
                          "unknown_memberships": [], "ignored_non_club_memberships": []})
        items.append({"qid": "Q6", "title": "所属不明",
                      "eligibility_status": "unverified",
                      "eligibility_reason": "club_country_incomplete",
                      "domestic_clubs": [], "foreign_clubs": ["Q900"],
                      "unknown_memberships": ["Q999"],
                      "ignored_non_club_memberships": []})
        for index, name in enumerate(
                ("丸山桂里奈", "川崎咲耶", "曽根七海", "稲山美優", "藤尾きらら"), 20):
            items.append({"qid": f"Q{index}", "title": name,
                          "eligibility_status": "unverified",
                          "eligibility_reason": "club_country_incomplete",
                          "domestic_clubs": [], "foreign_clubs": ["Q900"],
                          "unknown_memberships": [f"QW{index}"],
                          "ignored_non_club_memberships": []})
        return items

    def latest_teams(self, qids):
        return {"Q2": "海外クラブ", "Q3": "世界クラブ"}


class FakeReading:
    name = "fake"
    evidence = {}

    def resolve(self, article, intro):
        values = {
            "海外 太郎": ("海外", "カイガイ", "太郎", "タロウ", "海外太郎", "カイガイタロウ", None),
            "世界 花子": ("世界", "セカイ", "花子", "ハナコ", "世界花子", "セカイハナコ", None),
        }
        return values.get(article)


class ExtendFootballScopesTests(unittest.TestCase):
    def setUp(self):
        self.existing = [{
            "id": "0", "original": "J既存 選手", "team": "Jクラブ",
            "surface": "J既存 選手", "pronunciation": "ジェイキゾン センシュ",
            "type": "full", "category": "player", "image": "", "image_page": "",
            "position": "DF", "description":
                "Jリーグの選手。Jリーグ・Jクラブ所属。ポジションはDF。",
        }]

    def test_existing_rows_are_enriched(self):
        rows = target.enrich_jleague_rows(self.existing, {"0": "Q1"})
        self.assertEqual("jleague", rows[0]["scope"])
        self.assertEqual("Q1", rows[0]["wikidata"])
        self.assertEqual("Jリーグの選手。", rows[0]["description"])

    def test_club_country_classification_is_conservative(self):
        club = lambda countries: {"countries": set(countries), "types": {"Q476028"},
                                  "is_football_club": True, "is_national_team": False}
        domestic = target.classify_club_countries(
            {"foreign": club({"Q30"}), "japan": club({"Q17"})})
        self.assertEqual("rejected", domestic["eligibility_status"])
        self.assertEqual("domestic_club_history", domestic["eligibility_reason"])
        incomplete = target.classify_club_countries(
            {"foreign": club({"Q30"}), "unknown": {"countries": set(), "types": set(),
                                                     "is_football_club": False,
                                                     "is_national_team": False}})
        self.assertEqual("unverified", incomplete["eligibility_status"])
        eligible = target.classify_club_countries({
            "foreign": club({"Q30"}),
            "japan_national_team": {"countries": {"Q17"}, "types": {"Q6979593"},
                                    "is_football_club": False,
                                    "is_national_team": True},
        })
        self.assertEqual("eligible", eligible["eligibility_status"])
        self.assertEqual(["japan_national_team"], eligible["ignored_non_club_memberships"])
        mistyped_womens_club = target.classify_club_countries({
            "foreign": club({"Q30"}),
            "domestic_womens_club": {"countries": {"Q17"}, "types": {"QSomeTeamType"},
                                     "is_football_club": False,
                                     "is_national_team": False},
        })
        self.assertEqual("unverified", mistyped_womens_club["eligibility_status"])
        self.assertEqual(["domestic_womens_club"],
                         mistyped_womens_club["unknown_memberships"])

    def test_world_threshold_defaults_to_eighty_and_is_configurable(self):
        self.assertEqual(80, target.parse_args([]).world_min_sitelinks)
        self.assertEqual(95, target.parse_args(
            ["--world-min-sitelinks", "95"]).world_min_sitelinks)

    def test_scopes_are_exclusive_and_jleague_has_priority(self):
        wd = FakeWikidata()
        rows, manifest = target.collect(
            self.existing, {"0": "Q1"}, FakeWiki(), wd, FakeReading())
        full = {row["original"]: row for row in rows if row["type"] == "full"}
        self.assertEqual("jleague", full["J既存 選手"]["scope"])
        self.assertEqual("overseas_japanese", full["海外 太郎"]["scope"])
        self.assertEqual("world", full["世界 花子"]["scope"])
        self.assertEqual("海外クラブ", full["海外 太郎"]["team"])
        self.assertEqual("Q3", full["世界 花子"]["wikidata"])
        j_record = next(item for item in manifest if item["qid"] == "Q1")
        self.assertEqual("already_in_jleague_or_duplicate", j_record["reason"])
        false_record = next(item for item in manifest if item["qid"] == "Q4")
        self.assertEqual("first_sentence_not_player_subject", false_record["reason"])
        unread_record = next(item for item in manifest if item["qid"] == "Q5")
        self.assertEqual("unverified", unread_record["status"])
        self.assertEqual("reading_unparsed", unread_record["reason"])
        self.assertEqual(80, wd.seen_minimum)
        self.assertEqual("eligible", next(
            item for item in manifest if item["qid"] == "Q3")["eligibility"]["status"])

    def test_domestic_history_and_incomplete_club_country_are_not_adopted(self):
        rows, manifest = target.collect(
            self.existing, {"0": "Q1"}, FakeWiki(), FakeWikidata(), FakeReading())
        originals = {row["original"] for row in rows}
        for name in ("中井卓大", "三都主", "大城蛍", "久保木優", "川上靖"):
            self.assertNotIn(name, originals)
            record = next(item for item in manifest if item["article"] == name)
            self.assertEqual("rejected", record["eligibility"]["status"])
            self.assertEqual("domestic_club_history", record["reason"])
        unknown = next(item for item in manifest if item["article"] == "所属不明")
        self.assertEqual("unverified", unknown["status"])
        self.assertEqual("club_country_incomplete", unknown["eligibility"]["reason"])
        for name in ("丸山桂里奈", "川崎咲耶", "曽根七海", "稲山美優", "藤尾きらら"):
            self.assertNotIn(name, originals)
            record = next(item for item in manifest if item["article"] == name)
            self.assertEqual("unverified", record["status"])
            self.assertEqual("club_country_incomplete", record["reason"])

    def test_first_sentence_must_define_player(self):
        self.assertTrue(target.first_sentence_is_player("山田太郎は、日本のサッカー選手。監督でもある。"))
        self.assertFalse(target.first_sentence_is_player("山田太郎は、俳優。以前はサッカー選手だった。"))
        self.assertFalse(target.first_sentence_is_player("選手一覧は、サッカー選手を扱う一覧。"))

    def test_csv_schema(self):
        rows = target.enrich_jleague_rows(self.existing, {"0": "Q1"})
        text = target.csv_text(rows)
        self.assertFalse(text.endswith("\n"))
        parsed = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(target.CSV_COLUMNS, list(parsed[0]))

    def test_load_jleague_qids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.jsonl"
            path.write_text('{"verified_id":"7","qid":"Q77"}\n', encoding="utf-8")
            self.assertEqual({"7": "Q77"}, target.load_jleague_qids(path))


if __name__ == "__main__":
    unittest.main()
