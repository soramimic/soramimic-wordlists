import csv
import io
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import update_scientist

from update_scientist import (
    COLS,
    NEW_FIELDS,
    build_attr,
    parse_year,
    style_description,
)


class UpdateScientistTest(unittest.TestCase):
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
                        image="", image_page="")
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
