import csv
import io
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import update_scientist
from scientist_celebrity_doctorates import apply_entries, load_entries, validate_flags

from update_scientist import (
    COLS,
    NEW_FIELDS,
    build_attr,
    parse_year,
    style_description,
)


class UpdateScientistTest(unittest.TestCase):
    def run_alias_update(self, rows, parsed_names):
        persons = {f"Q{i}": {"title": f"未収録{i}", "fields": ["物理"]}
                   for i in range(1, 2001)}
        attrs = {}
        for index, title in enumerate(parsed_names, 1):
            persons[f"Q{index}"] = {"title": title, "fields": ["物理"]}
            attrs[f"Q{index}"] = {"birth_year": "1929", "nobel": "yes"}

        def parse(title, extract):
            name = parsed_names.get(title)
            if name is None:
                return None
            return (name[:-1], "アカサキ", name[-1:], "イサム",
                    name, "アカサキイサム", None)

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "scientist.csv"
            update_scientist.write_csv_no_trailing_newline(csv_path, COLS, rows)
            with (patch.object(update_scientist, "NEW_CSV", csv_path),
                  patch.object(update_scientist, "load_entries", return_value=[]),
                  patch.object(update_scientist, "DESCRIPTION_OVERRIDES", {}),
                  patch.object(update_scientist, "fetch_person_set", return_value=persons),
                  patch.object(update_scientist, "fetch_all", return_value=(attrs, {})),
                  patch.object(update_scientist, "parse_person", side_effect=parse),
                  redirect_stdout(io.StringIO())):
                self.assertEqual(update_scientist.main(), 0)
                first = csv_path.read_bytes()
                self.assertEqual(update_scientist.main(), 0)
                self.assertEqual(csv_path.read_bytes(), first)
            with csv_path.open(encoding="utf-8", newline="") as fh:
                return list(csv.DictReader(fh))

    def test_aliases_match_existing_people_and_backfill_without_renaming(self):
        csv_path = Path(__file__).resolve().parent.parent / "scientist.csv"
        with csv_path.open(encoding="utf-8", newline="") as fh:
            rows = [r for r in csv.DictReader(fh) if r["id"] == "105"]
        for old_name, incoming_name in (("赤崎勇", "赤﨑勇"), ("赤﨑勇", "赤崎勇")):
            with self.subTest(old=old_name, incoming=incoming_name):
                existing = [dict(r, original=old_name,
                                 surface=old_name[:-1] if r["type"] == "family" else old_name,
                                 birth_year="NA", nobel="NA") for r in rows]
                actual = self.run_alias_update(existing, {incoming_name: incoming_name})
                self.assertEqual(actual, [dict(r, birth_year="1929", nobel="yes")
                                          for r in existing])

                # The article title may differ from the name parsed from its lead.
                actual = self.run_alias_update(existing, {"別の表題": incoming_name})
                self.assertEqual(actual, existing)

    def test_new_aliases_share_one_person_without_merging_matching_readings(self):
        seed = dict.fromkeys(COLS, "NA")
        seed.update(id="1", original="既存科学者", surface="既存科学者",
                    pronunciation="あかさきいさむ", type="full", field="物理",
                    description="理論を提唱した。", image="", image_page="",
                    celebrity_doctorate="no", usage_notice="", usage_terms_page="")
        for names in (("赤崎勇", "赤﨑勇"), ("赤﨑勇", "赤崎勇")):
            with self.subTest(names=names):
                actual = self.run_alias_update([seed], {name: name for name in names})
                self.assertEqual(actual[0], seed)
                self.assertEqual(len(actual), 3)
                self.assertEqual({r["id"] for r in actual[1:]}, {"2"})
                self.assertEqual({r["original"] for r in actual[1:]}, {names[0]})
                self.assertEqual({r["type"] for r in actual[1:]}, {"family", "full"})
        self.assertNotEqual(update_scientist.person_key("山崎勇"),
                            update_scientist.person_key("山﨑勇"))

    def test_akasaki_has_one_complete_person_in_csv(self):
        csv_path = Path(__file__).resolve().parent.parent / "scientist.csv"
        with csv_path.open(encoding="utf-8", newline="") as fh:
            rows = [r for r in csv.DictReader(fh)
                    if update_scientist.person_key(r["original"]) == "赤崎勇"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["id"] for r in rows}, {"105"})
        self.assertEqual({r["surface"] for r in rows}, {"赤崎", "赤崎勇"})
        self.assertEqual({r["type"] for r in rows}, {"family", "full"})
        for row in rows:
            self.assertEqual(row["nobel"], "yes")
            self.assertEqual(row["birth_year"], "1929")
            self.assertEqual(row["death_year"], "2021")
            self.assertTrue(row["image_page"].endswith("File:Isamu_Akasaki_201111.jpg"))

    def test_reviewed_celebrities_survive_monthly_exclusions_and_refresh(self):
        entries = load_entries()
        merkel = next(e for e in entries if e["original"] == "アンゲラ・メルケル")
        self.assertIn(merkel["original"], update_scientist.EXCLUDED)
        existing = dict.fromkeys(COLS, "NA")
        existing.update(id="1", original="既存科学者", surface="既存科学者",
                        pronunciation="キゾンカガクシャ", type="full", field="物理",
                        description="理論を提唱した。", image="", image_page="")
        del existing["celebrity_doctorate"]  # CSV from before the schema extension.
        expected = apply_entries([existing], COLS, entries)
        persons = {f"Q{i}": {"title": f"未収録{i}", "fields": ["物理"]}
                   for i in range(1, 2001)}
        persons["Q567"] = {"title": merkel["original"], "fields": ["物理"]}
        attrs = {"Q567": {"country": "誤った国", "birth_year": "1900"}}
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "scientist.csv"
            update_scientist.write_csv_no_trailing_newline(
                csv_path, [c for c in COLS if c != "celebrity_doctorate"], [existing])
            with (patch.object(update_scientist, "NEW_CSV", csv_path),
                  patch.object(update_scientist, "fetch_person_set", return_value=persons),
                  patch.object(update_scientist, "fetch_all", return_value=(attrs, {})),
                  patch.object(update_scientist, "parse_person", return_value=None),
                  redirect_stdout(io.StringIO())):
                self.assertEqual(update_scientist.main(), 0)
                first = csv_path.read_bytes()
                self.assertEqual(update_scientist.main(), 0)
                self.assertEqual(csv_path.read_bytes(), first)
            with csv_path.open(encoding="utf-8", newline="") as fh:
                actual = list(csv.DictReader(fh))
        self.assertEqual(actual, expected)
        validate_flags(actual, entries)

    def test_celebrities_preserve_existing_rows_and_reject_identity_conflicts(self):
        entries = load_entries()
        path = Path(__file__).resolve().parent.parent / "scientist.csv"
        with path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(apply_entries(rows, COLS, entries), rows)
        validate_flags(rows, entries)
        stale = [dict(row, description="以前の説明。")
                 if row["celebrity_doctorate"] == "yes" else dict(row)
                 for row in rows]
        updated = apply_entries(stale, COLS, entries)
        self.assertEqual(updated, rows)
        self.assertEqual(apply_entries(updated, COLS, entries), updated)
        notice_edit = [dict(row, usage_notice="", usage_terms_page="") for row in rows]
        self.assertEqual(apply_entries(notice_edit, COLS, entries), notice_edit)
        self.assertTrue(all(row["description"] == "以前の説明。" for row in stale
                            if row["celebrity_doctorate"] == "yes"))
        wrong_id = [dict(rows[0], id=entries[0]["id"])]
        with self.assertRaisesRegex(ValueError, "ID/name conflict"):
            apply_entries(wrong_id, COLS, entries)
        wrong_name = [dict(rows[0], original=entries[0]["original"])]
        with self.assertRaisesRegex(ValueError, "ID/name conflict"):
            apply_entries(wrong_name, COLS, entries)
        for flag in ("no", "NA", ""):
            broken = [dict(r) for r in rows]
            next(r for r in broken if r["celebrity_doctorate"] == "yes")["celebrity_doctorate"] = flag
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                validate_flags(broken, entries)
        with self.assertRaises(ValueError):
            validate_flags([dict(rows[0], celebrity_doctorate="yes")], [])

    def test_new_nobel_awards_are_applied_without_losing_confirmed_awards(self):
        cases = [
            ("新受賞者", "no", "yes", "yes"),
            ("既存受賞者", "yes", "no", "yes"),
            ("属性未取得", "yes", None, "yes"),
            ("人物未取得", "yes", None, "yes"),
            ("受賞有無未確認", "NA", "yes", "yes"),
            ("未受賞者", "no", "no", "no"),
        ]
        rows, persons, attrs = [], {}, {}
        expected = {}
        for index, (name, old, fresh, result) in enumerate(cases, 1):
            qid = f"Q{index}"
            base = dict.fromkeys(COLS, "NA")
            base.update(id=str(index), original=name, field="物理",
                        era="現代", birth_year="1970", country="日本",
                        gender="男性", status="存命", nobel=old,
                        description="光を用いた測定法を開発した。",
                        image="", image_page="", celebrity_doctorate="no")
            for kind in ("family", "full"):
                rows.append(dict(base, type=kind, surface=name,
                                 pronunciation="テスト"))
            expected[name] = result
            if name != "人物未取得":
                persons[qid] = {"title": name, "fields": ["物理"]}
            if fresh is not None:
                attrs[qid] = {"nobel": fresh, "country": "別の国"}

        # Exercise the normal entry point with a plausible, entirely local dataset.
        for index in range(100, 2100):
            persons[f"Q{index}"] = {"title": f"未収録{index}", "fields": ["物理"]}
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "scientist.csv"
            update_scientist.write_csv_no_trailing_newline(csv_path, COLS, rows)
            with (patch.object(update_scientist, "NEW_CSV", csv_path),
                  patch.object(update_scientist, "load_entries", return_value=[]),
                  patch.object(update_scientist, "fetch_person_set", return_value=persons),
                  patch.object(update_scientist, "fetch_all", return_value=(attrs, {})),
                  patch.object(update_scientist, "parse_person", return_value=None),
                  redirect_stdout(io.StringIO())):
                self.assertEqual(update_scientist.main(), 0)
                first_run = csv_path.read_bytes()
                self.assertEqual(update_scientist.main(), 0)
                self.assertEqual(csv_path.read_bytes(), first_run)
            with csv_path.open(encoding="utf-8", newline="") as fh:
                updated = list(csv.DictReader(fh))

        self.assertEqual(len(updated), len(rows))
        for before, after in zip(rows, updated):
            with self.subTest(name=before["original"], kind=before["type"]):
                self.assertEqual(after, dict(before, nobel=expected[before["original"]]))

    def test_parse_year_supports_common_era_and_bce(self):
        self.assertEqual(parse_year("1940-12-16T00:00:00Z"), ("1940", 1940))
        self.assertEqual(parse_year("-0287-01-01T00:00:00Z"), ("前287", -287))
        self.assertEqual(parse_year(None), (None, None))

    def test_build_attr_keeps_death_year_from_wikidata(self):
        attr = build_attr(
            {
                "b": {"value": "1858-01-28T00:00:00Z"},
                "d": {"value": "1940-12-16T00:00:00Z"},
            }
        )

        self.assertEqual(attr["birth_year"], "1858")
        self.assertEqual(attr["death_year"], "1940")
        self.assertEqual(attr["status"], "物故")

    def test_scientist_schema_persists_death_year(self):
        self.assertEqual(COLS.index("death_year"), COLS.index("birth_year") + 1)
        self.assertIn("death_year", NEW_FIELDS)

    def test_style_description_removes_redundant_pronoun_subject(self):
        self.assertEqual(
            style_description("彼は小惑星を発見した。", "架空太郎"),
            "小惑星を発見した。",
        )
        self.assertEqual(
            style_description("彼女が考案した装置を改良した。", "架空花子"),
            "考案した装置を改良した。",
        )

    def test_scientist_descriptions_have_no_known_redundant_subjects(self):
        csv_path = Path(__file__).resolve().parent.parent / "scientist.csv"
        with csv_path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        descriptions = {row["id"]: row["description"] for row in rows}

        for description in descriptions.values():
            self.assertIsNone(re.match(r"^(?:彼|彼女)(?:は|が)", description))
        self.assertNotRegex(descriptions["409"], r"^その後マルトは")
        self.assertNotRegex(descriptions["1361"], r"^さらにマルコフニコフは")
        self.assertNotRegex(descriptions["3036"], r"^フォルカーディングは")
        self.assertNotRegex(descriptions["3297"], r"^デュボアは")


if __name__ == "__main__":
    unittest.main()
