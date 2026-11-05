import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pronunciation as target
import update_pokemon
import wpnames


class PronunciationTest(unittest.TestCase):
    def test_normalization_preserves_supplied_sounds_and_vowels(self):
        for text, expected in [("はない", "はない"), ("トウキョウ", "トウキョウ"),
                               ("ケイ", "ケイ"), ("ドーー", "ドーー"),
                               ("ｳｯｾｪﾜ", "ウッセェワ"), ("ピエール＝ジル", "ピエールジル")]:
            self.assertEqual(expected, target.normalize_pronunciation("fixture", "名前", text))

    def test_reviewed_readings_are_scoped_to_list_and_surface(self):
        self.assertEqual("ポリゴンツー", target.normalize_pronunciation("pokemon", "ポリゴン2", "ポリゴン2"))
        self.assertEqual("ケルヴィンキョウ", target.normalize_pronunciation("scientist", "ケルヴィン卿", "ケルヴィン卿"))
        with self.assertRaisesRegex(ValueError, "カナで指定"):
            target.normalize_pronunciation("fixture", "ポリゴン2", "ポリゴン2")
        with self.assertRaisesRegex(ValueError, "カナで指定"):
            target.normalize_pronunciation("pokemon", "別の名前", "ポリゴン2")

    def test_unreviewed_non_kana_is_rejected(self):
        for text in ["メカX", "メカ2", "卿", "❤"]:
            with self.assertRaises(ValueError):
                target.normalize_pronunciation("fixture", "名前", text)
        for text in ["", "NA", "na"]:
            self.assertEqual(text, target.normalize_pronunciation("fixture", "名前", text))

    def test_shared_updater_writer_preserves_display_and_metadata(self):
        rows = [{"id": "17", "original": "チャールズ・K・カオ", "surface": "チャールズ・K・カオ",
                 "pronunciation": "チャールズ・K・カオ", "image_page": "https://example.org/license"}]
        original = dict(rows[0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scientist.csv"
            wpnames.write_csv_no_trailing_newline(path, list(rows[0]), rows)
            actual = list(csv.DictReader(io.StringIO(path.read_text())))[0]
        self.assertEqual("チャールズケイカオ", actual["pronunciation"])
        self.assertEqual({k: v for k, v in original.items() if k != "pronunciation"},
                         {k: v for k, v in actual.items() if k != "pronunciation"})
        self.assertEqual(original, rows[0])

    def test_pokemon_updater_retains_reviewed_suffix_readings(self):
        for text, expected in [("ポリゴン2", "ポリゴンツー"), ("メガリザードンX", "メガリザードンエックス"),
                               ("メガライチュウY", "メガライチュウワイ"), ("ポリゴンZ", "ポリゴンゼット"),
                               ("ニドラン♀", "ニドランメス"), ("ニドラン♂", "ニドランオス")]:
            self.assertEqual(expected, update_pokemon.pron(text))

    def test_batch_validation_does_not_partially_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.csv"
            first.write_text("id,surface,pronunciation\n1,名前,は・ない")
            second = root / "b.csv"
            second.write_text("id,surface,pronunciation\n1,名前,メカX")
            before = first.read_text()
            with mock.patch.object(target, "ROOT", root), self.assertRaises(ValueError):
                target.main([])
            self.assertEqual(before, first.read_text())
