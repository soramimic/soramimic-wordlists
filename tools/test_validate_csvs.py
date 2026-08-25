import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_csvs as target


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
