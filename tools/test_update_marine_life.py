import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_marine_life as marine


class MarineLifeUpdaterTest(unittest.TestCase):
    def source(self, rows):
        handle = io.StringIO(newline="")
        writer = csv.DictWriter(handle, fieldnames=marine.SOURCE_COLUMNS,
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return handle.getvalue().rstrip("\n").encode()

    def row(self, **changes):
        row = {
            "id": "0",
            "name": "クジラ",
            "class": "哺乳類",
            "vertebrate": "脊椎動物",
            "order": "鯨偶蹄目",
            "family": "ナガスクジラ科",
            "description": "海で暮らす大型の哺乳類で水面に浮上して呼吸する。",
            "wikidata": "Q42196",
        }
        row.update(changes)
        return row

    def load(self, *rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            path.write_bytes(self.source(rows))
            with mock.patch.dict(marine.MIN_CLASS_COUNTS, {key: 0 for key in marine.CLASSES}), \
                 mock.patch.object(marine, "MIN_QID_COUNT", 0):
                return marine.load_source(path)

    def test_generate_has_filter_values_and_images(self):
        data = marine.generate(self.load(self.row())).decode()
        parsed = next(csv.DictReader(io.StringIO(data)))
        self.assertEqual("哺乳類", parsed["class"])
        self.assertEqual("脊椎動物", parsed["vertebrate"])
        self.assertTrue(parsed["image"].endswith("/marine_mammal.svg"))
        self.assertEqual(parsed["original"], parsed["pronunciation"])

    def test_rejects_duplicate_name(self):
        with self.assertRaisesRegex(ValueError, "duplicate name"):
            self.load(self.row(), self.row(id="1"))

    def test_rejects_duplicate_description(self):
        with self.assertRaisesRegex(ValueError, "duplicate description"):
            self.load(self.row(), self.row(id="1", name="イルカ"))

    def test_rejects_non_katakana_name(self):
        with self.assertRaisesRegex(ValueError, "not katakana"):
            self.load(self.row(name="海亀"))

    def test_rejects_class_hierarchy_mismatch(self):
        with self.assertRaisesRegex(ValueError, "class/vertebrate mismatch"):
            self.load(self.row(vertebrate="無脊椎動物"))

    def test_rejects_non_sequential_id(self):
        with self.assertRaisesRegex(ValueError, "append-only sequence"):
            self.load(self.row(id="4"))

    def test_rejects_bad_taxonomy_suffix(self):
        with self.assertRaisesRegex(ValueError, "order/family"):
            self.load(self.row(order="クジラ"))

    def test_rejects_extra_column(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            path.write_bytes(self.source([self.row()]) + b",extra")
            with self.assertRaisesRegex(ValueError, "number of columns"):
                marine.load_source(path)

    def test_rejects_class_below_minimum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            path.write_bytes(self.source([self.row()]))
            with mock.patch.object(marine, "MIN_QID_COUNT", 0):
                with self.assertRaisesRegex(ValueError, "too few"):
                    marine.load_source(path)

    def test_removed_names_detects_deletion(self):
        old = marine.generate([self.row(name="イルカ")])
        new = marine.generate([self.row(name="クジラ")])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "marine_life.csv"
            output.write_bytes(old)
            self.assertEqual({"イルカ"}, marine.removed_names(new, output))

    def test_write_atomic_replaces_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "marine_life.csv"
            output.write_bytes(b"old")
            marine.write_atomic(output, b"new")
            self.assertEqual(b"new", output.read_bytes())
            self.assertEqual([], list(output.parent.glob("*.tmp")))

    def test_check_does_not_rewrite_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "marine_life.csv"
            output.write_text("different", encoding="utf-8")
            with mock.patch.object(marine, "SOURCE", Path(directory) / "missing"), \
                 mock.patch.object(marine, "OUTPUT", output), \
                 mock.patch.object(marine, "load_source", return_value=[self.row()]), \
                 mock.patch.object(marine, "validate_images"):
                self.assertEqual(1, marine.main(["--check"]))
                self.assertEqual("different", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
