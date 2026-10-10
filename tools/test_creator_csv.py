import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from creator_csv import CARD_IMAGE_PREFIX, read_creator_csvs, write_creator_csvs
from wpnames import write_csv_no_trailing_newline
import yt_common


class CreatorCsvTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = tuple(Path(self.temp.name) / f"{category}.csv"
                           for category in ("youtuber", "vtuber"))
        self.columns = [*yt_common.COLS, "image", "subscribers", "has_image",
                        "usage_notice", "usage_terms_page"]
        self.rows = [self.person("3", "ヒカリ", "youtuber"),
                     self.person("90", "ソラ", "vtuber")]
        write_creator_csvs(self.columns, self.rows, self.paths)

    def person(self, pid, name, category):
        return {**dict.fromkeys(self.columns, "NA"), "id": pid,
                "original": name, "surface": name, "pronunciation": name,
                "category": category, "type": "full", "status": "current",
                "image": "https://example.com/image.svg", "subscribers": "1230",
                "has_image": "yes",
                "usage_notice": "guidelines" if category == "vtuber" else "",
                "usage_terms_page": ""}

    def test_writer_adds_column_and_refreshes_image_availability(self):
        columns = [c for c in self.columns if c != "has_image"]
        for image, expected in (
            (None, "no"), ("", "no"), ("NA", "no"),
            (CARD_IMAGE_PREFIX + "yt_test.svg", "no"),
            ("https://upload.wikimedia.org/wikipedia/commons/a/ab/photo.jpg", "yes"),
            ("https://example.com/official-portrait.png", "yes"),
            ("https://raw.githubusercontent.com/soramimic/soramimic-wordlists/"
             "main/images/vtuber/portrait.png", "yes"),
            ("https://github.com/soramimic/soramimic-wordlists/releases/"
             "download/youtuber-images/fan-image.png", "yes"),
        ):
            with self.subTest(image=image):
                rows = [{**row, "image": image} for row in self.rows]
                write_creator_csvs(columns, rows, self.paths)
                actual_columns, actual = read_creator_csvs(self.paths)
                self.assertEqual(actual_columns, columns + ["has_image"])
                self.assertEqual({row["has_image"] for row in actual}, {expected})
                self.assertEqual({row["has_image"] for row in rows}, {"yes"})

    def test_round_trip_preserves_all_fields_and_split(self):
        rows = [*self.rows, {**self.rows[1], "surface": "ソ", "type": "family"}]
        write_creator_csvs(self.columns, rows, self.paths)
        columns, actual = read_creator_csvs(self.paths)
        self.assertEqual((columns, actual), (self.columns, rows))
        for path in self.paths:
            self.assertFalse(path.read_bytes().endswith(b"\n"))
            self.assertEqual({row["category"] for row in read_creator_csvs((path,))[1]},
                             {path.stem})

    def test_notice_is_preserved_independently_of_category_and_image(self):
        rows = [{**self.rows[0], "usage_notice": "guidelines",
                 "usage_terms_page": "https://example.com/terms"},
                {**self.rows[1], "usage_notice": "", "usage_terms_page": ""}]
        write_creator_csvs(self.columns, rows, self.paths)
        self.assertEqual(read_creator_csvs(self.paths)[1], rows)

    def test_id_collision_rejected_before_writing(self):
        before = [path.read_bytes() for path in self.paths]
        with self.assertRaisesRegex(ValueError, "ID collision"):
            write_creator_csvs(self.columns,
                               [self.rows[0], {**self.rows[1], "id": "3"}], self.paths)
        self.assertEqual(before, [path.read_bytes() for path in self.paths])

    def test_reader_rejects_cross_file_ids_and_wrong_category(self):
        write_csv_no_trailing_newline(self.paths[1], self.columns,
                                      [{**self.rows[1], "id": "3"}])
        with self.assertRaisesRegex(ValueError, "ID collision"):
            read_creator_csvs(self.paths)
        write_csv_no_trailing_newline(self.paths[1], self.columns, [self.rows[0]])
        with self.assertRaisesRegex(ValueError, "does not match"):
            read_creator_csvs(self.paths)

    def test_missing_destination_does_not_drop_people(self):
        before = self.paths[0].read_bytes()
        with self.assertRaisesRegex(ValueError, "Missing destination"):
            write_creator_csvs(self.columns, self.rows, self.paths[:1])
        self.assertEqual(before, self.paths[0].read_bytes())

    def test_updater_appends_both_categories_with_shared_ids_and_is_idempotent(self):
        specs = [dict(category=category, occ=category, must=(), must_not=(),
                      guard=(1, 5)) for category in ("youtuber", "vtuber")]
        people = {"youtuber": {"Q1": "アオ"}, "vtuber": {"Q2": "アカ"}}
        with mock.patch.object(yt_common, "assert_occupation"), \
                mock.patch.object(yt_common, "fetch_persons",
                                  side_effect=lambda occ, *args: people[occ]), \
                mock.patch.object(yt_common, "fetch_attrs", return_value={}), \
                mock.patch.object(yt_common, "fetch_extracts", return_value={}), \
                mock.patch.dict(os.environ, {}, clear=True), \
                contextlib.redirect_stdout(io.StringIO()):
            for _ in range(2):
                self.assertEqual(yt_common.build_list(
                    tuple(str(path) for path in self.paths), specs, "TEST_CREATOR_CACHE"), 0)
        columns, rows = read_creator_csvs(self.paths)
        self.assertEqual(columns, self.columns)
        self.assertEqual(len(rows), 4)
        self.assertEqual({row["id"] for row in rows}, {"3", "90", "91", "92"})
        for original in self.rows:
            self.assertIn(original, rows)
        self.assertEqual({r["original"]: r["category"] for r in rows
                          if r["id"] in {"91", "92"}},
                         {"アオ": "youtuber", "アカ": "vtuber"})
        self.assertEqual({r["has_image"] for r in rows if r["id"] in {"91", "92"}},
                         {"no"})
        self.assertEqual({r["category"]: r["usage_notice"] for r in rows
                          if r["id"] in {"91", "92"}},
                         {"youtuber": "", "vtuber": "guidelines"})

    def test_updater_applies_reviewed_category_override_to_new_person(self):
        specs = [dict(category=category, occ=category, must=(), must_not=(),
                      guard=(0, 5)) for category in ("youtuber", "vtuber")]
        people = {"youtuber": {}, "vtuber": {"Q1": "アカ"}}
        with mock.patch.object(yt_common, "assert_occupation"), \
                mock.patch.object(yt_common, "fetch_persons",
                                  side_effect=lambda occ, *args: people[occ]), \
                mock.patch.object(yt_common, "fetch_attrs", return_value={}), \
                mock.patch.object(yt_common, "fetch_extracts", return_value={}), \
                mock.patch.dict(os.environ, {}, clear=True), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(yt_common.build_list(
                tuple(str(path) for path in self.paths), specs, "TEST_CREATOR_CACHE",
                category_overrides={"アカ": "youtuber"}), 0)

        _, rows = read_creator_csvs(self.paths)
        added = [row for row in rows if row["original"] == "アカ"]
        self.assertEqual({row["category"] for row in added}, {"youtuber"})


if __name__ == "__main__":
    unittest.main()
