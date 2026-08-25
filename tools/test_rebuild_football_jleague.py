import csv
import io
import tempfile
import unittest
from pathlib import Path

import rebuild_football_jleague as target


class FakeClient:
    def current_clubs(self):
        return [f"クラブ{i}" for i in range(60)]

    def category_members(self, category):
        if category == "クラブ0の選手":
            return {"exists": True, "members": ["山田 太郎 (サッカー選手)", "クラブ監督"]}
        if category == "横浜フリューゲルスの選手":
            return {"exists": True, "members": ["山田 太郎 (サッカー選手)"]}
        if category == "クラブ1の選手":
            return {"exists": False, "members": []}
        return {"exists": True, "members": []}

    def pages(self, titles):
        return {
            "山田 太郎 (サッカー選手)": {
                "canonical_title": "山田 太郎 (サッカー選手)", "qid": "Q123",
                "extract": "山田 太郎（やまだ たろう）は、日本のサッカー選手。ポジションはMF。",
                "pageimage": "Yamada Taro.jpg", "missing": False,
                "disambiguation": False,
            },
            "クラブ監督": {
                "canonical_title": "クラブ監督", "qid": "Q999",
                "extract": "クラブ監督は、日本のサッカー指導者。",
                "pageimage": "", "missing": False, "disambiguation": False,
            },
        }


class FakeReadingProvider:
    name = "fake-reading"

    def resolve(self, article, intro):
        if article == "山田 太郎":
            return ("山田", "ヤマダ", "太郎", "タロウ", "山田太郎", "ヤマダタロウ", None)
        return None


class RebuildFootballTests(unittest.TestCase):
    def test_registered_name_from_intro_requires_explicit_katakana_alias(self):
        self.assertEqual(
            "カイコ", target.registered_name_from_intro(
                "カイコ (Caico) こと、アイルトン・グラシリアーノは元サッカー選手。"))
        self.assertEqual(
            "アダイウトン", target.registered_name_from_intro(
                "アダイウトン・ドス・サントスはサッカー選手。登録名はアダイウトン。"))
        self.assertEqual("", target.registered_name_from_intro(
            "田中太郎（たなか たろう）はサッカー選手。"))

    def test_identity_fields_from_intro(self):
        self.assertEqual(
            ("1990/12/06", ["Adaílton dos Santos da Silva"]),
            target.identity_fields_from_intro(
                "アダイウトン（Adaílton dos Santos da Silva、1990年12月6日 - ）は選手。"))

    def test_context_dependent_description_gets_subject(self):
        self.assertEqual(
            "ジーコは、509ゴールを記録。",
            target.standalone_description("ジーコ", "うち、509ゴールを記録。"))

    def test_card_facts_are_removed_from_description(self):
        self.assertEqual(
            "静岡県出身のプロサッカー選手。元日本代表。",
            target.clean_player_card_description(
                "静岡県出身のプロサッカー選手。Jリーグ・クラブ所属。"
                "ポジションはFW。元日本代表。"))
        self.assertEqual(
            "ブラジル出身の元サッカー選手。",
            target.clean_player_card_description(
                "ブラジル出身の元サッカー選手でポジションはMF。"))
        self.assertEqual(
            "山梨県出身の元プロサッカー選手、サッカー指導者。",
            target.clean_player_card_description(
                "山梨県出身の元プロサッカー選手（ポジションはFW）、サッカー指導者。"))

    def test_missing_description_sentinels_stay_missing(self):
        for value in ("", "NA", "NA。", " NA。。 "):
            with self.subTest(value=value):
                self.assertEqual("", target.clean_player_card_description(value))

    def test_collect_outputs_player_rows_and_auditable_manifest(self):
        rows, manifest, missing = target.collect(FakeClient(), FakeReadingProvider())
        self.assertEqual(3, len(rows))
        self.assertEqual({"full", "family", "given"}, {r["type"] for r in rows})
        self.assertTrue(all(r["category"] == "player" for r in rows))
        self.assertTrue(all(r["scope"] == "jleague" for r in rows))
        self.assertTrue(all(r["wikidata"] == "Q123" for r in rows))
        self.assertEqual("クラブ0-横浜フリューゲルス", rows[0]["team"])
        self.assertEqual("MF", rows[0]["position"])
        self.assertEqual("日本のサッカー選手。", rows[0]["description"])
        self.assertEqual(["クラブ1の選手"], missing)

        accepted = next(m for m in manifest if m["status"] == "accepted")
        self.assertEqual("山田 太郎 (サッカー選手)", accepted["article"])
        self.assertEqual("山田 太郎", accepted["parsed_name"])
        self.assertEqual("Q123", accepted["qid"])
        self.assertEqual("fake-reading", accepted["reading_provider"])
        self.assertEqual(rows[0]["id"], accepted["candidate_id"])
        self.assertEqual(2, len(accepted["evidence"]))
        self.assertTrue(all(not e["membership_period_verified"]
                            for e in accepted["evidence"]))
        rejected = next(m for m in manifest if m["article"] == "クラブ監督")
        self.assertEqual("not_a_football_player", rejected["reason"])

    def test_json_cache_resumes_without_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = target.JsonCache(Path(directory))
            self.assertEqual({"value": 1}, cache.get("stage", "key", lambda: {"value": 1}))

            def fail():
                raise AssertionError("builder must not run on resume")

            self.assertEqual({"value": 1}, cache.get("stage", "key", fail))

    def test_category_redirect_is_resolved_before_listing_members(self):
        calls = []

        def fake_api(params):
            calls.append(params)
            if params.get("prop") == "categoryinfo":
                return {"query": {"pages": {"1": {
                    "title": "Category:新クラブの選手", "categoryinfo": {"size": 2},
                }}}}
            if "cmcontinue" not in params:
                return {"query": {"categorymembers": [{"title": "同名 選手 (サッカー選手)"}]},
                        "continue": {"continue": "-||", "cmcontinue": "next"}}
            return {"query": {"categorymembers": [{"title": "別 選手"}]}}

        original_api = target.api
        try:
            target.api = fake_api
            with tempfile.TemporaryDirectory() as directory:
                client = target.WikipediaClient(target.JsonCache(Path(directory)))
                result = client.category_members("旧クラブの選手")
        finally:
            target.api = original_api
        self.assertEqual("新クラブの選手", result["category"])
        self.assertIn("同名 選手 (サッカー選手)", result["members"])
        self.assertTrue(all(call["cmtitle"] == "Category:新クラブの選手"
                            for call in calls[1:]))

    def test_pages_uses_twenty_title_batches_without_silent_extract_loss(self):
        calls = []

        def fake_api(params):
            requested = params["titles"].split("|")
            calls.append(requested)
            return {"query": {"pages": {
                str(index): {
                    "title": title, "extract": f"{title}のサッカー選手。",
                    "pageprops": {"wikibase_item": f"Q{title.removeprefix('選手')}"},
                }
                for index, title in enumerate(requested)
            }}}

        original_api = target.api
        try:
            target.api = fake_api
            with tempfile.TemporaryDirectory() as directory:
                client = target.WikipediaClient(
                    target.JsonCache(Path(directory)), workers=3)
                pages = client.pages([f"選手{i}" for i in range(45)])
        finally:
            target.api = original_api
        self.assertEqual(45, len(pages))
        self.assertEqual([20, 20, 5], sorted(map(len, calls), reverse=True))
        self.assertTrue(all(page["extract"] for page in pages.values()))

    def test_wikipedia_provider_records_registered_name_and_reading(self):
        provider = target.WikipediaIntroReadingProvider()
        parsed = provider.resolve(
            "山田 太郎", "山田 太郎（やまだ たろう）は、日本のサッカー選手。")
        self.assertIsNotNone(parsed)
        self.assertEqual("wikipedia_intro", provider.evidence["method"])
        self.assertEqual("verified", provider.evidence["status"])
        self.assertEqual("ヤマダタロウ", provider.evidence["resolved_reading"])
        self.assertIsNone(provider.evidence["registered_name"])

    def test_csv_schema_matches_football_and_has_no_trailing_newline(self):
        row = {column: "" for column in target.CSV_COLUMNS}
        row.update(id="0", original="山田 太郎", team="クラブ0", surface="山田 太郎",
                   pronunciation="ヤマダ タロウ", type="full", category="player")
        text = target.csv_text([row])
        self.assertFalse(text.endswith("\n"))
        parsed = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual("player", parsed[0]["category"])

    def test_dry_run_does_not_write_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_collect = target.collect
            try:
                target.collect = lambda *args, **kwargs: ([], [], [])
                code = target.main([
                    "--dry-run", "--output", str(root / "out.csv"),
                    "--manifest", str(root / "manifest.jsonl"),
                    "--cache-dir", str(root / "cache"),
                ])
            finally:
                target.collect = original_collect
            self.assertEqual(0, code)
            self.assertFalse((root / "out.csv").exists())
            self.assertFalse((root / "manifest.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
