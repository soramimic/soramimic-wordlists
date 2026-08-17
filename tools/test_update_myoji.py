import csv
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
        first = (
            b'"surname","yomi"\n'
            b'"\xe7\x94\xb0\xe4\xb8\xad","\xe3\x82\xbf\xe3\x83\x8a\xe3\x82\xab"\n'
            b'"\xe4\xbd\x90\xe8\x97\xa4","\xe3\x82\xb5\xe3\x83\x88\xe3\x82\xa6"\n'
        )
        last = b'"surname","yomi"\n'
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(m, "CACHE_DIR", td),
            mock.patch.object(m, "NDL_PAGE_SIZE", 2),
            mock.patch.object(m, "MIN_NDL_PAIRS", 2),
            mock.patch.object(m.time, "sleep"),
            mock.patch.object(
                m, "http_get", side_effect=[OSError("temporary"), first, last]
            ) as get,
        ):
            self.assertEqual(
                m.fetch_ndl_pairs(), {("田中", "タナカ"), ("佐藤", "サトウ")}
            )
            self.assertEqual(get.call_count, 3)
            cached = json.loads(
                (Path(td) / "ndl-person-surname-pairs.json").read_text()
            )
            self.assertEqual(len(cached), 2)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ndl-person-surname-pairs.json"
            path.write_text(json.dumps([["田中", "タナカ"]]), encoding="utf-8")
            with (
                mock.patch.object(m, "CACHE_DIR", td),
                mock.patch.object(m, "MIN_NDL_PAIRS", 1),
                mock.patch.object(m, "http_get") as get,
            ):
                self.assertEqual(m.fetch_ndl_pairs(), {("田中", "タナカ")})
                get.assert_not_called()

    def test_fetch_ndl_pairs_rejects_small_cache(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "ndl-person-surname-pairs.json").write_text(
                "[]", encoding="utf-8"
            )
            with (
                mock.patch.object(m, "CACHE_DIR", td),
                mock.patch.object(m, "MIN_NDL_PAIRS", 1),
                self.assertRaises(RuntimeError),
            ):
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
            with (
                mock.patch.object(m, "CACHE_DIR", td),
                mock.patch.object(m, "MIN_JMNEDICT_PAIRS", 1),
                mock.patch.object(m, "http_get") as get,
            ):
                self.assertEqual(m.fetch_jmnedict_pairs(), {("鈴木", "スズキ")})
                get.assert_not_called()
        with self.assertRaises((gzip.BadGzipFile, EOFError)):
            m.parse_jmnedict(b"not gzip")


class EvidenceSemanticsTest(unittest.TestCase):
    def test_sources_are_ordered_and_dictionary_only_is_not_verified(self):
        pair = ("鈴木", "スズキ")
        sources = m.evidence_for(pair, {pair}, {pair}, {pair}, {pair}, {pair}, {pair})
        self.assertEqual(
            m.format_evidence(sources),
            "person_lists|ndl|wikidata_person|official_web|web_person|jmnedict",
        )
        self.assertTrue(m.is_human_verified(sources))
        self.assertFalse(m.is_human_verified({"jmnedict"}))

    def test_each_new_person_source_verifies(self):
        self.assertTrue(m.is_human_verified({"wikidata_person"}))
        self.assertTrue(m.is_human_verified({"official_web"}))
        self.assertTrue(m.is_human_verified({"web_person"}))

    def test_make_row_exposes_dictionary_evidence_without_verifying(self):
        pair = ("鈴木", "ススキ")
        row = m.make_row("1", pair[0], pair[1], {}, {}, {}, {pair: {"jmnedict"}})
        self.assertEqual(row["verified"], "no")
        self.assertEqual(row["evidence_sources"], "jmnedict")

    def test_merge_is_monotonic_and_migrates_legacy_yes(self):
        old = [
            {
                "id": "1",
                "original": "鈴木",
                "surface": "鈴木",
                "pronunciation": "スズキ",
                "verified": "yes",
                "rank": "1",
                "description": "",
                "wikidata": "",
            },
            {
                "id": "2",
                "original": "佐藤",
                "surface": "佐藤",
                "pronunciation": "サトウ",
                "verified": "no",
                "rank": "2",
                "description": "",
                "wikidata": "",
                "evidence_sources": "jmnedict",
            },
        ]
        evidence = {
            ("鈴木", "スズキ"): {"jmnedict"},
            ("佐藤", "サトウ"): {"ndl", "jmnedict"},
        }
        rows = m.merge_rows(
            old,
            {"鈴木": ["スズキ"], "佐藤": ["サトウ"]},
            {"鈴木": 1, "佐藤": 2},
            {},
            {},
            evidence,
        )
        self.assertEqual(rows[0]["verified"], "yes")
        self.assertEqual(rows[0]["evidence_sources"], "person_lists|jmnedict")
        self.assertEqual(rows[1]["verified"], "yes")
        self.assertEqual(rows[1]["evidence_sources"], "ndl|jmnedict")

    def test_merge_syncs_web_person_to_current_ledger(self):
        old = [
            {
                "id": "1",
                "original": "A",
                "surface": "A",
                "pronunciation": "ア",
                "verified": "yes",
                "rank": "",
                "description": "",
                "wikidata": "",
                "evidence_sources": "web_person|jmnedict",
            },
            {
                "id": "2",
                "original": "B",
                "surface": "B",
                "pronunciation": "イ",
                "verified": "no",
                "rank": "",
                "description": "",
                "wikidata": "",
                "evidence_sources": "official_web|web_person",
            },
        ]
        rows = m.merge_rows(
            old, {"A": ["ア"], "B": ["イ"]}, {}, {}, {}, {("B", "イ"): {"web_person"}}
        )
        self.assertEqual(rows[0]["evidence_sources"], "jmnedict")
        self.assertEqual(rows[0]["verified"], "no")
        self.assertEqual(rows[1]["evidence_sources"], "official_web|web_person")
        self.assertEqual(rows[1]["verified"], "yes")


class WikidataPersonEvidenceTest(unittest.TestCase):
    def test_query_uses_surname_item_reading_without_reference_requirement(self):
        query = m.WIKIDATA_PERSON_READING_QUERY
        for token in (
            "P31",
            "Q5",
            "P27",
            "Q17",
            "P734",
            "P1814",
            'LANG(?fnLabel) = "ja"',
        ):
            self.assertIn(token, query)
        self.assertNotIn("prov:wasDerivedFrom", query)

    def test_parser_normalizes_deduplicates_and_filters(self):
        def binding(surface=None, reading=None):
            row = {}
            if surface is not None:
                row["fnLabel"] = {"value": surface}
            if reading is not None:
                row["kana"] = {"value": reading}
            return row

        data = {
            "results": {
                "bindings": [
                    binding(" 鈴木 ", "す ず き"),
                    binding("鈴木", "スズキ"),
                    binding("Suzuki", "スズキ"),
                    binding("佐藤", "sato"),
                    binding("田中", None),
                    {},
                ]
            }
        }
        self.assertEqual(m.parse_wikidata_person_json(data), {("鈴木", "スズキ")})

    def test_fetch_uses_cache_and_rejects_small_uncached_result(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "wikidata-person-surname-pairs.json"
            path.write_text(json.dumps([["鈴木", "スズキ"]]), encoding="utf-8")
            with (
                mock.patch.object(m, "CACHE_DIR", td),
                mock.patch.object(m, "MIN_WIKIDATA_PERSON_PAIRS", 1),
                mock.patch.object(m, "sparql") as sparql,
            ):
                self.assertEqual(m.fetch_wikidata_person_pairs(), {("鈴木", "スズキ")})
                sparql.assert_not_called()

        data = {
            "results": {
                "bindings": [
                    {
                        "fnLabel": {"value": "鈴木"},
                        "kana": {"value": "すずき"},
                    }
                ]
            }
        }
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(m, "CACHE_DIR", td),
            mock.patch.object(m, "MIN_WIKIDATA_PERSON_PAIRS", 2),
            mock.patch.object(m, "sparql", return_value=data),
            self.assertRaises(RuntimeError),
        ):
            m.fetch_wikidata_person_pairs()
            self.assertFalse((Path(td) / "wikidata-person-surname-pairs.json").exists())


class OfficialEvidenceTest(unittest.TestCase):
    def test_loader_uses_only_verified_records(self):
        base = {
            "surface": "東",
            "pronunciation": "アヅマ",
            "status": "verified",
            "source_url": "https://example.jp/person",
            "source_type": "official_org_directory",
            "retrieved_on": "2026-08-13",
        }
        review = dict(
            base,
            surface="西",
            pronunciation="ニシ",
            status="review",
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "evidence.jsonl"
            path.write_text(
                "\n".join(map(json.dumps, (base, review))), encoding="utf-8"
            )
            self.assertEqual(m.load_official_evidence(path), {("東", "アヅマ")})

    def test_loader_rejects_duplicates(self):
        record = {
            "surface": "東",
            "pronunciation": "アヅマ",
            "status": "verified",
            "source_url": "https://example.jp/person",
            "source_type": "official_person_profile",
            "retrieved_on": "2026-08-13",
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "evidence.jsonl"
            path.write_text(json.dumps(record), encoding="utf-8")
            path.write_text(
                "\n".join((json.dumps(record), json.dumps(record))), encoding="utf-8"
            )
            with self.assertRaises(RuntimeError):
                m.load_official_evidence(path)


class WebEvidenceTest(unittest.TestCase):
    def test_evidence_only_changes_only_two_fields(self):
        record = {
            "surface": "榎谷",
            "pronunciation": "エノキヤ",
            "status": "verified",
            "source_url": "https://example.jp/player/enokiya",
            "source_type": "sports_database",
            "retrieved_on": "2026-08-14",
            "evidence_tier": "B",
            "identity_basis": "same_profile",
        }
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            evidence = td / "web.jsonl"
            evidence.write_text(json.dumps(record), encoding="utf-8")
            csv_path = td / "myoji.csv"
            csv_path.write_text(
                "id,original,surface,pronunciation,verified,rank,description,wikidata,evidence_sources\n"
                "7,榎谷,榎谷,エノキヤ,no,42,keep, Q1,\n",
                encoding="utf-8",
            )
            before = csv_path.read_text(encoding="utf-8")
            changed = m.apply_web_evidence_only(csv_path, evidence)
            self.assertEqual(changed, (1, 1))
            with csv_path.open(encoding="utf-8", newline="") as stream:
                row = next(iter(csv.DictReader(stream)))
            self.assertEqual(row["verified"], "yes")
            self.assertEqual(row["evidence_sources"], "web_person")
            self.assertEqual(row["rank"], "42")
            self.assertEqual(row["description"], "keep")
            self.assertEqual(row["wikidata"], " Q1")
            self.assertNotEqual(before, csv_path.read_text(encoding="utf-8"))

    def test_evidence_only_removes_stale_web_person_and_recomputes(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            evidence = td / "web.jsonl"
            evidence.write_text("", encoding="utf-8")
            csv_path = td / "myoji.csv"
            csv_path.write_text(
                "id,original,surface,pronunciation,verified,evidence_sources\n"
                "1,A,A,ア,yes,web_person|jmnedict\n"
                "2,B,B,イ,no,official_web|web_person\n",
                encoding="utf-8",
            )
            self.assertEqual(m.apply_web_evidence_only(csv_path, evidence), (1, 2))
            rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
            self.assertEqual(rows[0]["verified"], "no")
            self.assertEqual(rows[0]["evidence_sources"], "jmnedict")
            self.assertEqual(rows[1]["verified"], "yes")
            self.assertEqual(rows[1]["evidence_sources"], "official_web")

    def test_loader_accepts_reviewed_tier_b_person_page(self):
        record = {
            "surface": "榎谷",
            "pronunciation": "エノキヤ",
            "status": "verified",
            "source_url": "https://example.jp/player/enokiya",
            "source_type": "sports_database",
            "retrieved_on": "2026-08-14",
            "evidence_tier": "B",
            "identity_basis": "same_profile",
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "web-evidence.jsonl"
            path.write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(m.load_web_evidence(path), {("榎谷", "エノキヤ")})

    def test_loader_accepts_official_source_in_general_web_ledger(self):
        record = {
            "surface": "榎谷",
            "pronunciation": "エノキヤ",
            "status": "verified",
            "source_url": "https://example.jp/roster/enokiya",
            "source_type": "official_roster",
            "retrieved_on": "2026-08-14",
            "evidence_tier": "A",
            "identity_basis": "same_record",
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "web-evidence.jsonl"
            path.write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(m.load_web_evidence(path), {("榎谷", "エノキヤ")})

    def test_loader_rejects_weak_or_mismatched_web_evidence(self):
        record = {
            "surface": "榎谷",
            "pronunciation": "エノキヤ",
            "status": "verified",
            "source_url": "https://example.jp/person",
            "source_type": "person_database",
            "retrieved_on": "2026-08-14",
            "evidence_tier": "C",
            "identity_basis": "same_profile",
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "web-evidence.jsonl"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                m.load_web_evidence(path)

    def test_loader_rejects_source_type_tier_mismatch(self):
        record = {
            "surface": "榎谷",
            "pronunciation": "エノキヤ",
            "status": "verified",
            "source_url": "https://example.jp/person",
            "source_type": "person_database",
            "retrieved_on": "2026-08-14",
            "evidence_tier": "A",
            "identity_basis": "same_profile",
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "web-evidence.jsonl"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "不一致"):
                m.load_web_evidence(path)


class MainGuardTest(unittest.TestCase):
    def test_full_rebuild_requires_explicit_flag(self):
        with self.assertRaises(SystemExit):
            m.main([])


if __name__ == "__main__":
    unittest.main()
