import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_marine_life_wikipedia_descriptions as enrich


class MarineLifeWikipediaDescriptionTest(unittest.TestCase):
    def test_selects_feature_sentence_instead_of_classification(self):
        extract = (
            "ジンベエザメ（学名: Rhincodon typus）は、テンジクザメ目に属するサメ。"
            "世界中の熱帯・亜熱帯・温帯の表層海域に広く分布する。"
            "主食はプランクトンである。"
        )
        source, description = enrich.select_description(
            extract, "ジンベエザメ", "ジンベエザメ"
        )
        self.assertIn("表層海域", description)
        self.assertNotIn("テンジクザメ目", description)
        self.assertTrue(source.endswith("。"))

    def test_removes_redundant_name_subject(self):
        extract = "シャチは、白黒模様の体が特徴である。"
        _source, description = enrich.select_description(extract, "シャチ", "シャチ")
        self.assertEqual("白黒模様の体が特徴である。", description)

    def test_rejects_classification_only_extract(self):
        extract = "アオウミガメは、ウミガメ科に分類されるカメの一種である。"
        self.assertIsNone(
            enrich.select_description(extract, "アオウミガメ", "アオウミガメ")
        )

    def test_rejects_article_for_a_different_japanese_name(self):
        extract = "コモンカスベは、沿岸の砂泥底に生息する。"
        self.assertIsNone(
            enrich.select_description(extract, "クロカスベ", "コモンカスベ")
        )

    def test_rejects_generic_classification_even_with_weak_size_word(self):
        extract = "キミオコゼは、フサカサゴ科に属する小型の海水魚である。"
        self.assertIsNone(enrich.select_description(extract, "キミオコゼ", "キミオコゼ"))

    def test_removes_subject_with_space_and_mixed_parentheses(self):
        extract = "キミオコゼ（英名: lionfish、学名: Pterois radiata) は、インド太平洋に生息する。"
        _source, description = enrich.select_description(extract, "キミオコゼ", "キミオコゼ")
        self.assertEqual("インド太平洋に生息する。", description)

    def test_rejects_sentence_about_another_named_species(self):
        extract = (
            "イガイは、岩礁に付着して生息する。"
            "ムラサキイガイは波が穏やかな内湾に多い。"
        )
        _source, description = enrich.select_description(extract, "イガイ", "イガイ")
        self.assertEqual("岩礁に付着して生息する。", description)

    def test_removes_numeric_thousands_separator(self):
        extract = "水深2,000メートルまでの深海に生息する。"
        _source, description = enrich.select_description(extract, "テストイカ", "テストイカ")
        self.assertEqual("水深2000メートルまでの深海に生息する。", description)

    def test_contextual_lead_is_removed(self):
        extract = "また、深海に生息し青白い光を発する。"
        _source, description = enrich.select_description(extract, "テストイカ", "テストイカ")
        self.assertEqual("深海に生息し青白い光を発する。", description)

    def test_long_sentence_uses_complete_feature_clause(self):
        extract = (
            "熱帯の浅海に生息する、非常に長い修飾説明が続いて文章全体がカードには"
            "収まりにくくなるための試験用の文であり、さらに多くの情報が後ろへ続く。"
        )
        selected = enrich.select_description(extract, "テストヒトデ", "テストヒトデ")
        self.assertIsNotNone(selected)
        self.assertLessEqual(len(selected[1]), 90)
        self.assertTrue(selected[1].endswith("。"))


if __name__ == "__main__":
    unittest.main()
