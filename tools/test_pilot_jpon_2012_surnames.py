import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pilot_jpon_2012_surnames as m


HTML = """
<meta name="description" content="掲載237件の名前・電話番号・住所">
<h3>この地域に多い苗字</h3><table>
<tr><th>苗字</th><th>軒数</th><th>全国順位</th></tr>
<tr><td><a>佐藤</a></td><td>12</td><td>1</td></tr>
<tr><td>鈴木</td><td>3</td><td>2</td></tr></table>
<h3>この地域の希少苗字</h3><table>
<tr><th>苗字</th><th>軒数</th><th>全国軒数</th></tr>
<tr><td>鈴木</td><td>3</td><td>99,999</td></tr>
<tr><td>四月一日</td><td>1</td><td>10</td></tr></table>
"""


class ParserTest(unittest.TestCase):
    def test_parses_local_counts_and_deduplicates_overlap(self):
        facts = m.parse_page(HTML)
        self.assertEqual(facts.advertised_entries, 237)
        self.assertEqual(facts.common, {"佐藤": 12, "鈴木": 3})
        self.assertEqual(facts.rare, {"鈴木": 3, "四月一日": 1})
        self.assertEqual(facts.merged, {"佐藤": 12, "鈴木": 3, "四月一日": 1})
        self.assertEqual(facts.overlaps, {"鈴木"})
        self.assertFalse(facts.conflicting_overlaps)

    def test_changed_markup_yields_no_facts(self):
        facts = m.parse_page("<h2>names</h2>")
        self.assertFalse(facts.merged)
        self.assertFalse(facts.sections_seen)

    def test_valid_empty_tables_are_recognized(self):
        facts = m.parse_page(
            "<h3>この地域に多い苗字</h3><table></table>"
            "<h3>この地域の希少苗字</h3><table></table>"
        )
        self.assertFalse(facts.merged)
        self.assertEqual(facts.sections_seen, {"common", "rare"})

    def test_conflicting_overlap_is_reported(self):
        facts = m.parse_page(
            "<h3>この地域に多い苗字</h3><table><tr><td>佐藤</td><td>2</td></tr></table>"
            "<h3>この地域の希少苗字</h3><table><tr><td>佐藤</td><td>1</td></tr></table>"
        )
        self.assertEqual(facts.conflicting_overlaps, {"佐藤"})

    def test_sitemap_selects_one_url_per_2012_locality(self):
        xml = b"""<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
        <url><loc>https://jpon.xyz/2012/1/2/3.html?p=2</loc></url>
        <url><loc>https://jpon.xyz/2012/1/2/3.html?p=1</loc></url>
        <url><loc>https://jpon.xyz/2012/1/2/4.html</loc></url>
        <url><loc>https://jpon.xyz/1968/1/2/3.html?p=1</loc></url></urlset>"""
        self.assertEqual(
            m.parse_sitemap(xml),
            [
                "https://jpon.xyz/2012/1/2/3.html?p=1",
                "https://jpon.xyz/2012/1/2/4.html",
            ],
        )


class StorageTest(unittest.TestCase):
    def test_store_is_idempotent_and_resume_skips_page(self):
        with tempfile.TemporaryDirectory() as td:
            db = m.init_db(Path(td) / "pilot.sqlite3")
            facts = m.parse_page(HTML)
            m.store_page(db, "https://jpon.xyz/2012/1/2/3.html?p=1", facts)
            m.store_page(db, "https://jpon.xyz/2012/1/2/3.html?p=1", facts)
            m.seed_sitemap(
                db,
                "https://jpon.xyz/sitemap/test.xml",
                [
                    "https://jpon.xyz/2012/1/2/3.html?p=1",
                    "https://jpon.xyz/2012/1/2/4.html?p=1",
                ],
            )
            self.assertEqual(m.summary(db)["pages"], 1)
            self.assertEqual(m.summary(db)["advertised_entries"], 237)
            self.assertEqual(m.summary(db)["distinct_surnames"], 3)
            self.assertEqual(m.summary(db)["observed_households"], 16)
            self.assertEqual(
                m.select_urls(db, 100),
                ["https://jpon.xyz/2012/1/2/4.html?p=1"],
            )
            self.assertTrue(
                m.sitemap_is_seeded(db, "https://jpon.xyz/sitemap/test.xml")
            )


if __name__ == "__main__":
    unittest.main()
