import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_marine_life_descriptions as enrich


class MarineLifeDescriptionEnricherTest(unittest.TestCase):
    def test_fetch_json_treats_no_content_as_empty_traits(self):
        class Response:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with mock.patch.object(enrich.urllib.request, "urlopen", return_value=Response()):
            self.assertEqual([], enrich.fetch_json("https://example.test/traits"))

    def test_select_maximum_length_requires_exact_species_and_length(self):
        attributes = [
            {
                "measurementType": "Body size", "measurementValue": "100",
                "AphiaID_Inherited": 1, "qualitystatus": "checked",
                "source_id": 10, "reference": "parent",
                "children": [
                    {"measurementType": "Unit", "measurementValue": "cm", "children": []},
                    {"measurementType": "Type", "measurementValue": "maximum", "children": []},
                    {"measurementType": "Dimension", "measurementValue": "length", "children": []},
                ],
            },
            {
                "measurementType": "Body size", "measurementValue": "38",
                "AphiaID_Inherited": 159559, "qualitystatus": "checked",
                "source_id": 11, "reference": "species reference",
                "children": [
                    {"measurementType": "Unit", "measurementValue": "cm", "children": []},
                    {"measurementType": "Type", "measurementValue": "maximum", "children": []},
                    {"measurementType": "Dimension", "measurementValue": "length", "children": []},
                ],
            },
        ]
        selected = enrich.select_maximum_length(attributes, "159559")
        self.assertEqual("38", selected["value"])
        self.assertEqual(11, selected["source_id"])

    def test_checked_length_is_preferred_over_larger_unreviewed_value(self):
        def item(value, quality, source_id):
            return {
                "measurementType": "Body size", "measurementValue": value,
                "AphiaID_Inherited": 2, "qualitystatus": quality,
                "source_id": source_id, "reference": "reference",
                "children": [
                    {"measurementType": "Unit", "measurementValue": "cm", "children": []},
                    {"measurementType": "Type", "measurementValue": "maximum", "children": []},
                    {"measurementType": "Dimension", "measurementValue": "length", "children": []},
                ],
            }
        selected = enrich.select_maximum_length(
            [item("200", "unreviewed", 1), item("40", "checked", 2)], "2"
        )
        self.assertEqual("40", selected["value"])

    def test_select_iucn_uses_latest_assessment(self):
        attributes = [{
            "measurementType": "Species importance to society", "children": [
                {
                    "measurementType": "IUCN Red List Category",
                    "measurementValue": "Vulnerable", "AphiaID_Inherited": 3,
                    "source_id": 1, "reference": "IUCN", "qualitystatus": "checked",
                    "children": [{
                        "measurementType": "Year Assessed", "measurementValue": "2023",
                        "children": [],
                    }],
                }
            ],
        }]
        selected = enrich.select_iucn(attributes, "3")
        self.assertEqual("Vulnerable", selected["category"])
        self.assertEqual("2023", selected["year"])


if __name__ == "__main__":
    unittest.main()
