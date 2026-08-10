import csv
import re
import unittest
from pathlib import Path

from update_scientist import (
    COLS,
    NEW_FIELDS,
    build_attr,
    parse_year,
    style_description,
)


class UpdateScientistTest(unittest.TestCase):
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
