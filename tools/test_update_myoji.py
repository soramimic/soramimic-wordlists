import gzip
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_myoji as m


def gz_xml(text: str) -> bytes:
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb") as fh:
        fh.write(text.encode())
    return out.getvalue()


class NdlEvidenceTest(unittest.TestCase):
    def test_parse_ndl_csv_normalizes_and_filters(self):
        data = (
            '"surname","yomi"\n'
            '"鈴木","スズキ"\n'
            '"鈴木","すずき"\n'
            '"佐藤","サ ト ウ"\n'
            '"ミッキー・カーチス","ミッキー"\n'
            '"玲","レイ"\n'
            '"","タナカ"\n'
        ).encode()
        self.assertEqual(
            m.parse_ndl_csv(data),
            {("鈴木", "スズキ"), ("佐藤", "サトウ"), ("玲", "レイ")},
        )

    def test_parse_ndl_csv_rejects_changed_schema(self):
        with self.assertRaises(RuntimeError):
            m.parse_ndl_csv(b'"label","reading"\n"A","B"\n')

    def test_fetch_ndl_pairs_pages_retries_and_caches(self):
        first = (b'"surname","yomi"\n'
                 b'"\xe7\x94\xb0\xe4\xb8\xad","\xe3\x82\xbf\xe3\x83\x8a\xe3\x82\xab"\n'
                 b'"\xe4\xbd\x90\xe8\x97\xa4","\xe3\x82\xb5\xe3\x83\x88\xe3\x82\xa6"\n')
        last = b'"surname","yomi"\n'
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
                m, "CACHE_DIR", td), mock.patch.object(
                m, "NDL_PAGE_SIZE", 2), mock.patch.object(
                m, "MIN_NDL_PAIRS", 2), mock.patch.object(
                m.time, "sleep"), mock.patch.object(
                m, "http_get", side_effect=[OSError("temporary"), first, last]) as get:
            self.assertEqual(
                m.fetch_ndl_pairs(), {("田中", "タナカ"), ("佐藤", "サトウ")})
            self.assertEqual(get.call_count, 3)
            cached = json.loads(
                (Path(td) / "ndl-person-surname-pairs.json").read_text())
            self.assertEqual(len(cached), 2)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ndl-person-surname-pairs.json"
            path.write_text(json.dumps([["田中", "タナカ"]]), encoding="utf-8")
            with mock.patch.object(m, "CACHE_DIR", td), mock.patch.object(
                    m, "MIN_NDL_PAIRS", 1), mock.patch.object(m, "http_get") as get:
                self.assertEqual(m.fetch_ndl_pairs(), {("田中", "タナカ")})
                get.assert_not_called()

    def test_fetch_ndl_pairs_rejects_small_cache(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "ndl-person-surname-pairs.json").write_text(
                "[]", encoding="utf-8")
            with mock.patch.object(m, "CACHE_DIR", td), mock.patch.object(
                    m, "MIN_NDL_PAIRS", 1), self.assertRaises(RuntimeError):
                m.fetch_ndl_pairs()


class JmnedictEvidenceTest(unittest.TestCase):
    def test_only_surname_entries_and_reading_restrictions_are_used(self):
        blob = gz_xml("""<?xml version="1.0"?>
<JMnedict>
  <entry>
    <k_ele><keb>鈴木</keb></k_ele><k_ele><keb>鈴城</keb></k_ele>
    <r_ele><reb>すずき</reb><re_restr>鈴木</re_restr></r_ele>
    <trans><name_type>family or surname</name_type></trans>
  </entry>
  <entry>
    <k_ele><keb>花子</keb></k_ele><r_ele><reb>はなこ</reb></r_ele>
    <trans><name_type>female given name or forename</name_type></trans>
  </entry>
  <entry>
    <k_ele><keb>さとう</keb></k_ele><r_ele><reb>さとう</reb></r_ele>
    <trans><name_type>family or surname</name_type></trans>
  </entry>
</JMnedict>""")
        self.assertEqual(m.parse_jmnedict(blob), {("鈴木", "スズキ")})

    def test_fetch_jmnedict_uses_cache_and_rejects_malformed_data(self):
        good = gz_xml("""<JMnedict><entry><k_ele><keb>鈴木</keb></k_ele>
<r_ele><reb>すずき</reb></r_ele><trans><name_type>family or surname</name_type>
</trans></entry></JMnedict>""")
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "JMnedict.xml.gz").write_bytes(good)
            with mock.patch.object(m, "CACHE_DIR", td), mock.patch.object(
                    m, "MIN_JMNEDICT_PAIRS", 1), mock.patch.object(
                    m, "http_get") as get:
                self.assertEqual(m.fetch_jmnedict_pairs(), {("鈴木", "スズキ")})
                get.assert_not_called()
        with self.assertRaises((gzip.BadGzipFile, EOFError)):
            m.parse_jmnedict(b"not gzip")


class EvidenceSemanticsTest(unittest.TestCase):
    def test_sources_are_ordered_and_dictionary_only_is_not_verified(self):
        pair = ("鈴木", "スズキ")
        sources = m.evidence_for(pair, {pair}, {pair}, {pair})
        self.assertEqual(
            m.format_evidence(sources), "person_lists|ndl|jmnedict")
        self.assertTrue(m.is_human_verified(sources))
        self.assertFalse(m.is_human_verified({"jmnedict"}))

    def test_make_row_exposes_dictionary_evidence_without_verifying(self):
        pair = ("鈴木", "ススキ")
        row = m.make_row("1", pair[0], pair[1], {}, {}, {},
                         {pair: {"jmnedict"}})
        self.assertEqual(row["verified"], "no")
        self.assertEqual(row["evidence_sources"], "jmnedict")

    def test_merge_is_monotonic_and_migrates_legacy_yes(self):
        old = [
            {"id": "1", "original": "鈴木", "surface": "鈴木",
             "pronunciation": "スズキ", "verified": "yes", "rank": "1",
             "description": "", "wikidata": ""},
            {"id": "2", "original": "佐藤", "surface": "佐藤",
             "pronunciation": "サトウ", "verified": "no", "rank": "2",
             "description": "", "wikidata": "",
             "evidence_sources": "jmnedict"},
        ]
        evidence = {
            ("鈴木", "スズキ"): {"jmnedict"},
            ("佐藤", "サトウ"): {"ndl", "jmnedict"},
        }
        rows = m.merge_rows(
            old, {"鈴木": ["スズキ"], "佐藤": ["サトウ"]},
            {"鈴木": 1, "佐藤": 2}, {}, {}, evidence)
        self.assertEqual(rows[0]["verified"], "yes")
        self.assertEqual(
            rows[0]["evidence_sources"], "person_lists|jmnedict")
        self.assertEqual(rows[1]["verified"], "yes")
        self.assertEqual(rows[1]["evidence_sources"], "ndl|jmnedict")


if __name__ == "__main__":
    unittest.main()
