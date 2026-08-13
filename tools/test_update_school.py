import unittest

from update_school import COLS, has_school_suffix


class UpdateSchoolTest(unittest.TestCase):
    def test_schema_appends_has_school_suffix(self):
        self.assertEqual("has_school_suffix", COLS[-1])

    def test_has_school_suffix_recognizes_general_suffix(self):
        cases = [
            ("北海道教育大学附属函館幼稚園", "common", "幼稚園"),
            ("札幌南高校", "common", "高等学校"),
            ("山鼻小", "common", "小学校"),
            ("第一中", "nick", "中学校"),
            ("東京工業高等専門学校", "common", "高等専門学校"),
            ("星幼学園", "common", "幼稚園"),
            ("高崎保育所", "common", "認定こども園"),
            ("筑波大附属中学", "nick", "中学校"),
            ("幕張インターナショナルスクール", "common", "各種学校"),
            ("愛光幼稚舎", "common", "幼稚園"),
            ("愛国フレンドようちえん", "common", "幼稚園"),
            ("附属小学部", "common", "特別支援学校"),
            ("附属中学部", "common", "特別支援学校"),
            ("附属高等部", "common", "特別支援学校"),
        ]
        for surface, surface_type, school_type in cases:
            with self.subTest(surface=surface, surface_type=surface_type):
                self.assertEqual(
                    "yes", has_school_suffix(surface, surface_type, school_type))

    def test_has_school_suffix_leaves_nonstandard_suffix_unchanged(self):
        self.assertEqual(
            "no", has_school_suffix("ニセコ町幼児センター", "common", "幼稚園"))

    def test_has_school_suffix_disambiguates_short_suffixes(self):
        self.assertEqual("no", has_school_suffix("田中", "name", "中学校"))
        self.assertEqual("no", has_school_suffix("上小", "name", "小学校"))
        self.assertEqual("no", has_school_suffix("山中", "nick", "高等学校"))
        self.assertEqual("no", has_school_suffix("第一中", "unknown", "中学校"))


if __name__ == "__main__":
    unittest.main()
