import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_youtuber_subscribers as subscribers


class ApplySnapshotTest(unittest.TestCase):
    def test_date_is_refreshed_with_value_and_missing_rows_are_na(self):
        columns = ["id", "original", "subscribers", "subscribers_as_of"]
        rows = [
            {"id": "1", "original": "A", "subscribers": "100",
             "subscribers_as_of": "2026-07-30"},
            {"id": "2", "original": "B", "subscribers": "200",
             "subscribers_as_of": "2026-07-30"},
            {"id": "3", "original": "C", "subscribers": "NA",
             "subscribers_as_of": "NA"},
        ]

        filled, updated, lost = subscribers.apply_snapshot(
            rows, columns, {"1": 150, "3": 300}, "2026-08-15")

        self.assertEqual(
            [(row["subscribers"], row["subscribers_as_of"]) for row in rows],
            [("150", "2026-08-15"), ("NA", "NA"),
             ("300", "2026-08-15")],
        )
        self.assertEqual(filled, {"3"})
        self.assertEqual(updated, {"1"})
        self.assertEqual(lost, {"2"})

    def test_columns_are_added_once_and_atomic_writer_preserves_format(self):
        columns = ["id", "original"]
        rows = [{"id": "1", "original": "A"}]
        subscribers.apply_snapshot(rows, columns, {"1": 42}, "2026-08-15")
        subscribers.apply_snapshot(rows, columns, {"1": 43}, "2026-08-16")

        self.assertEqual(
            columns, ["id", "original", "subscribers", "subscribers_as_of"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "youtuber.csv"
            path.write_text("old", encoding="utf-8")
            subscribers.write_snapshot_atomic(path, columns, rows)
            self.assertFalse(path.read_bytes().endswith(b"\n"))
            with path.open(encoding="utf-8") as handle:
                rendered = list(csv.DictReader(handle))
        self.assertEqual(rendered[0]["subscribers"], "43")
        self.assertEqual(rendered[0]["subscribers_as_of"], "2026-08-16")


if __name__ == "__main__":
    unittest.main()
