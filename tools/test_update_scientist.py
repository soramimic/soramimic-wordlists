import unittest

from update_scientist import COLS, NEW_FIELDS, build_attr, parse_year


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


if __name__ == "__main__":
    unittest.main()
