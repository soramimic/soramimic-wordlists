import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_plant


class UpdatePlantSchemaTest(unittest.TestCase):
    def test_preserves_extended_columns_and_initializes_new_rows(self):
        columns = [
            "id", "original", "surface", "pronunciation", "class", "extinct",
            "family", "family_wikidata", "genus", "scientific_name", "image",
            "image_page", "wikidata",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plant.csv"
            with path.open("w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerow({
                    "id": "0", "original": "キゾン", "surface": "キゾン",
                    "pronunciation": "キゾン", "class": "双子葉", "extinct": "no",
                    "family": "既存科", "family_wikidata": "Q1", "genus": "既存属",
                    "scientific_name": "Existing plant", "image": "photo",
                    "image_page": "page", "wikidata": "Q2",
                })
            taxa = {
                "キゾン": (False, {"Q2"}),
                "シンキ": (False, {"Q3"}),
            }
            with (
                patch.object(update_plant, "CSV_PATH", path),
                patch.object(update_plant, "MIN_TOTAL", 0),
                patch.object(update_plant, "fetch_orders", return_value=set()),
                patch.object(update_plant, "fetch_taxa", return_value=taxa),
                patch.object(update_plant, "animal_taxa", return_value=set()),
                patch.object(update_plant.time, "sleep"),
            ):
                self.assertEqual(0, update_plant.main())
            with path.open(encoding="utf-8", newline="") as source:
                reader = csv.DictReader(source)
                rows = list(reader)
                self.assertEqual(columns, reader.fieldnames)
            self.assertEqual("既存科", rows[0]["family"])
            self.assertEqual("photo", rows[0]["image"])
            self.assertEqual("", rows[1]["family"])
            self.assertEqual("", rows[1]["wikidata"])


if __name__ == "__main__":
    unittest.main()
