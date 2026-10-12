import copy
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import entry_corrections as target
import update_municipality
import wpnames


def record(**changes):
    return {"list": "municipality", "id": "1", "original": "沖宿村",
            "previous_original": "沖宿町", "source_qid": "Q1",
            "fields": {"original": "沖宿村", "prefecture": "茨城県", "wikidata": ""},
            "forms": {"full": {"surface": "沖宿村", "pronunciation": "オキジュクムラ"},
                      "short": {"surface": "沖宿", "pronunciation": "オキジュク"}},
            "source_urls": ["https://example.org/village"],
            "reviewed_on": "2026-10-12", **changes}


def rows():
    return [{"id": "1", "original": "沖宿町", "type": "full", "surface": "沖宿町",
             "pronunciation": "", "prefecture": "", "wikidata": "Q1"},
            {"id": "1", "original": "沖宿町", "type": "short", "surface": "沖宿",
             "pronunciation": "", "prefecture": "", "wikidata": "Q1"}]


class EntryCorrectionsTest(unittest.TestCase):
    def test_correction_applies_both_forms_and_keeps_other_id(self):
        data = rows() + [{**rows()[0], "id": "2"}]
        untouched = dict(data[-1])
        self.assertGreater(target.apply_corrections("municipality", data, [record()]), 0)
        self.assertEqual(["沖宿村", "沖宿村"], [r["original"] for r in data[:2]])
        self.assertEqual(["オキジュクムラ", "オキジュク"],
                         [r["pronunciation"] for r in data[:2]])
        self.assertEqual(["", ""], [r["wikidata"] for r in data[:2]])
        self.assertEqual(untouched, data[-1])
        self.assertEqual(0, target.apply_corrections("municipality", data, [record()]))

    def test_id_with_unrecognized_name_is_not_reassigned(self):
        data = [{**row, "original": "別の町"} for row in rows()]
        before = copy.deepcopy(data)
        self.assertEqual(0, target.apply_corrections("municipality", data, [record()]))
        self.assertEqual(before, data)

    def test_strict_missing_identity_fails_before_any_change(self):
        data, before = rows(), rows()
        with self.assertRaisesRegex(ValueError, "identity missing"):
            target.apply_corrections("municipality", data,
                                     [record(), record(id="missing")], strict=True)
        self.assertEqual(before, data)

    def test_source_alias_preserves_id_without_readding_modern_district(self):
        data = [{**row, "original": "沖宿村", "wikidata": "",
                 "prefecture": "茨城県", "status": "former", "code": "", "parent": ""}
                for row in rows()]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "municipality.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(data[0]))
                writer.writeheader()
                writer.writerows(data)
            with mock.patch.object(update_municipality, "CSV_PATH", path), \
                    mock.patch.object(target, "records_by_list", return_value={"municipality": [record()]}):
                groups, next_id = update_municipality.load_existing()
            self.assertEqual({"qQ1"}, set(groups))
            self.assertEqual("1", groups.pop("qQ1")["id"])
            self.assertFalse(groups)
            self.assertEqual(2, next_id)

    def test_shared_writer_preserves_metadata_and_input(self):
        data = rows()
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            target, "records_by_list", return_value={"municipality": [record()]}
        ):
            path = Path(directory) / "municipality.csv"
            wpnames.write_csv_no_trailing_newline(path, list(data[0]), data)
            result = list(csv.DictReader(io.StringIO(path.read_text())))
            self.assertEqual("沖宿村", result[0]["original"])
            self.assertEqual("沖宿町", data[0]["original"])

    def test_ledger_rejects_invalid_fields_missing_sources_and_source_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.jsonl"
            path.write_text(json.dumps(record()), encoding="utf-8")
            self.assertEqual([record()], target.load_records(path))
            for invalid in [record(source_urls=[]), record(fields={"unknown": "x"}),
                            record(fields={"original": "別の村"}), record(source_qid="bad")]:
                path.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaises(ValueError):
                    target.load_records(path)
            path.write_text("\n".join(json.dumps(r) for r in [record(), record(id="2")]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate source"):
                target.load_records(path)


if __name__ == "__main__":
    unittest.main()
