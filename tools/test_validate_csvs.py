import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_csvs as target
from wpnames import write_csv_no_trailing_newline


class CreatorImageAvailabilityValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "youtuber.csv"
        card = self.root / "images/youtuber/yt_test.svg"
        card.parent.mkdir(parents=True)
        card.write_text("<svg/>", encoding="utf-8")
        self.row = dict(
            id="1", original="テスト", surface="テスト", category="youtuber",
            scope="unknown", channel_shared="NA", channel="NA",
            subscribers="NA", subscribers_as_of="NA", image_credit="",
            image_usage="", image_terms_page="",
        )
        self.images = (
            (target.YOUTUBER_CARD_IMAGE_PREFIX + "yt_test.svg",
             target.YOUTUBER_CARD_PAGE_PREFIX + "yt_test.svg", "no"),
            ("https://upload.wikimedia.org/wikipedia/commons/a/ab/photo.jpg",
             "https://commons.wikimedia.org/wiki/File:photo.jpg", "yes"),
        )
        self.addCleanup(target.errors.clear)

    def validate(self, row):
        target.errors.clear()
        write_csv_no_trailing_newline(self.path, list(row), [row])
        with mock.patch.object(target, "ROOT", self.root), \
                contextlib.redirect_stdout(io.StringIO()):
            target.validate(self.path)
        return list(target.errors)

    def test_requires_column_and_correct_flag_for_cards_and_photos(self):
        for image, page, expected in self.images:
            row = dict(self.row, image=image, image_page=page, has_image=expected)
            with self.subTest(image=image):
                self.assertEqual(self.validate(row), [])
                for incorrect in ("no" if expected == "yes" else "yes", "NA", "", "true"):
                    errors = self.validate(dict(row, has_image=incorrect))
                    self.assertTrue(any("has_image が画像と不一致" in e for e in errors))
                del row["has_image"]
                self.assertTrue(any("必須列 has_image がない" in e for e in self.validate(row)))


class PlayerDescriptionValidationTests(unittest.TestCase):
    def setUp(self):
        target.errors.clear()
        self.addCleanup(target.errors.clear)

    def validate_description(self, filename: str, description: str) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / filename
            path.write_text(
                "id,original,surface,type,description\n"
                f"1,山田太郎,山田太郎,full,{description}",
                encoding="utf-8",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                target.validate(path)
        return list(target.errors)

    def test_rejects_na_description_sentinels(self):
        for filename in ("baseball.csv", "football.csv"):
            for value in ("NA", "NA。", " NA。。 "):
                with self.subTest(filename=filename, value=value):
                    target.errors.clear()
                    self.assertTrue(any(
                        "descriptionにNA sentinel" in error
                        for error in self.validate_description(filename, value)
                    ))

    def test_allows_a_missing_description_as_an_empty_field(self):
        for filename in ("baseball.csv", "football.csv"):
            with self.subTest(filename=filename):
                target.errors.clear()
                self.assertEqual([], self.validate_description(filename, ""))


if __name__ == "__main__":
    unittest.main()
