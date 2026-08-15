import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_2000_hierarchy_parses_only_the_next_level(self):
        root = """<a href='/2000/1/index.html'>北海道</a>
        <a href='https://example.test/2000/2/index.html'>outside</a>
        <a href='/2012/1/index.html'>wrong year</a>"""
        self.assertEqual(
            m.parse_hierarchy_links(root, m.YEAR_2000_ROOT),
            [("https://jpon.xyz/2000/1/index.html", "prefecture")],
        )
        prefecture = """<a href='../index.html'>戻る</a>
        <a href='2/index.html'>札幌市</a><a href='2/index.html#top'>duplicate</a>"""
        self.assertEqual(
            m.parse_hierarchy_links(prefecture, "https://jpon.xyz/2000/1/index.html"),
            [("https://jpon.xyz/2000/1/2/index.html", "municipality")],
        )
        municipality = """<a href='3.html?p=1'>中央</a>
        <a href='4.html?p=2#names'>北</a><a href='index.html'>self</a>"""
        self.assertEqual(
            m.parse_hierarchy_links(municipality, "https://jpon.xyz/2000/1/2/index.html"),
            [
                ("https://jpon.xyz/2000/1/2/3.html", "town"),
                ("https://jpon.xyz/2000/1/2/4.html", "town"),
            ],
        )

    def test_2000_url_normalization_rejects_other_years_and_hosts(self):
        self.assertEqual(
            m.normalize_2000_url("/2000/01/002/3.html?p=9#x"),
            "https://jpon.xyz/2000/01/002/3.html",
        )
        self.assertIsNone(m.normalize_2000_url("https://jpon.xyz/2012/1/2/3.html"))
        self.assertIsNone(m.normalize_2000_url("https://evil.test/2000/1/2/3.html"))
        self.assertIsNone(m.normalize_2000_url("//evil.test/2000/1/index.html"))


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

    def test_2000_hierarchy_resume_skips_checkpointed_items(self):
        with tempfile.TemporaryDirectory() as td:
            db = m.init_db(Path(td) / "pilot.sqlite3")
            m.enqueue_hierarchy(db, [(m.YEAR_2000_ROOT, "root")], None)
            m.checkpoint_index(
                db,
                m.YEAR_2000_ROOT,
                [("https://jpon.xyz/2000/1/index.html", "prefecture")],
            )
            self.assertEqual(
                m.next_hierarchy_url(db),
                ("https://jpon.xyz/2000/1/index.html", "prefecture"),
            )


class CookieTest(unittest.TestCase):
    def test_cdp_cookie_is_kept_in_memory_and_not_in_sqlite(self):
        secret = "session-secret-must-not-be-persisted"

        class FakeProcess:
            returncode = 0

            def __init__(self, _command, **kwargs):
                payload = json.dumps(
                    [{
                        "name": "session", "value": secret, "domain": ".jpon.xyz",
                        "path": "/", "secure": True, "httpOnly": True, "expires": -1,
                    }]
                ).encode()
                os.write(kwargs["pass_fds"][0], payload)

            def communicate(self):
                return b"", b""

        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            m.subprocess, "Popen", FakeProcess
        ):
            jar = m.load_cdp_cookie_jar()
            self.assertEqual([(cookie.name, cookie.value) for cookie in jar], [("session", secret)])
            db_path = Path(td) / "pilot.sqlite3"
            db = m.init_db(db_path)
            m.enqueue_hierarchy(db, [(m.YEAR_2000_ROOT, "root")], None)
            db.close()
            for path in Path(td).iterdir():
                self.assertNotIn(secret.encode(), path.read_bytes())


if __name__ == "__main__":
    unittest.main()
