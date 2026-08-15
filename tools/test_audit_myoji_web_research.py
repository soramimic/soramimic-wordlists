import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_myoji_web_research as a


class ResearchTest(unittest.TestCase):
    def attempt(self, strategy, engine="bing", count=0, status=200):
        queries = {
            "exact_katakana": '"榎谷" "エノキヤ"',
            "exact_hiragana": '"榎谷" "えのきや"',
            "broad_person": "榎谷 氏名",
        }
        attempt = {
            "strategy": strategy,
            "engine": engine,
            "query": queries[strategy],
            "completed_at": "2026-08-14T00:00:00+09:00",
            "http_status": status,
            "result_count": count,
            "response_sha256": "",
            "result_urls": ["https://example.jp/x"] if count else [],
        }
        attempt["response_sha256"] = a.receipt_sha256(attempt)
        return attempt

    def record(self, status="no_support_found", attempts=None):
        x = {k: "" for k in a.BASE_KEYS + a.EXTRA_KEYS}
        x.update(
            {
                "batch_index": 0,
                "surface": "榎谷",
                "pronunciation": "エノキヤ",
                "rank": "1",
                "searched_on": "2026-08-14",
                "query": "榎谷 えのきや 氏名",
                "status": status,
                "search_attempts": attempts
                or [
                    self.attempt("exact_katakana", "bing"),
                    self.attempt("exact_hiragana", "duckduckgo"),
                    self.attempt("broad_person", "bing"),
                ],
            }
        )
        return x

    def write(self, td, x):
        p = Path(td) / "2026-08-14-a.jsonl"
        p.write_text(json.dumps(x, ensure_ascii=False) + "\n", encoding="utf-8")
        return [p]

    def candidates(self, td):
        p = Path(td) / "2026-08-14-candidates.csv"
        p.write_text(
            "batch_index,id,surface,pronunciation,rank,query\n0,1,榎谷,エノキヤ,1,榎谷 えのきや 氏名\n",
            encoding="utf-8",
        )
        return p

    def test_no_support_requires_three_strategies(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
        ):
            self.candidates(td)
            x = self.record(attempts=[self.attempt("exact_katakana")] * 3)
            with self.assertRaises(RuntimeError):
                a.load_results("2026-08-14", self.write(td, x))

    def test_one_real_search_provider_is_accepted(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
        ):
            self.candidates(td)
            attempts = [
                self.attempt(strategy, "openai_web_search") for strategy in a.STRATEGIES
            ]
            self.assertEqual(
                len(
                    a.load_results(
                        "2026-08-14", self.write(td, self.record(attempts=attempts))
                    )
                ),
                1,
            )

    def test_second_pass_requires_dictionary_exclusions_in_every_query(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
        ):
            batch = "2026-08-14-s2p1"
            (Path(td) / f"{batch}-candidates.csv").write_text(
                "batch_index,id,surface,pronunciation,rank,query\n"
                "0,1,榎谷,エノキヤ,1,榎谷 えのきや 氏名\n",
                encoding="utf-8",
            )
            record = self.record()
            result = Path(td) / f"{batch}-a.jsonl"
            result.write_text(
                json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "lacks dictionary exclusions"):
                a.load_results(batch)
            suffix = " " + " ".join(
                f"-site:{host}" for host in a.SECOND_PASS_EXCLUDED_SITES
            )
            for attempt in record["search_attempts"]:
                attempt["query"] += suffix
                attempt["response_sha256"] = a.receipt_sha256(attempt)
            result.write_text(
                json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            self.assertEqual(len(a.load_results(batch)), 1)

    def test_429_is_never_successful_attempt(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
        ):
            self.candidates(td)
            x = self.record()
            x["search_attempts"][0]["http_status"] = 429
            with self.assertRaises(RuntimeError):
                a.load_results("2026-08-14", self.write(td, x))

    def test_failed_attempt_may_be_retained_after_successful_retry(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
        ):
            self.candidates(td)
            x = self.record()
            failed = self.attempt("exact_katakana", "yahoo_japan", status=429)
            retry = self.attempt("exact_katakana", "google")
            x["search_attempts"].extend((failed, retry))
            self.assertEqual(len(a.load_results("2026-08-14", self.write(td, x))), 1)

    def test_result_count_requires_url(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
        ):
            self.candidates(td)
            x = self.record()
            x["search_attempts"][0]["result_count"] = 1
            with self.assertRaises(RuntimeError):
                a.load_results("2026-08-14", self.write(td, x))

    def test_markdown_trailing_parenthesis_is_not_a_url(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
        ):
            self.candidates(td)
            x = self.record()
            attempt = x["search_attempts"][0]
            attempt["result_count"] = 1
            attempt["result_urls"] = ["https://example.jp/person)"]
            attempt["response_sha256"] = a.receipt_sha256(attempt)
            with self.assertRaises(RuntimeError):
                a.load_results("2026-08-14", self.write(td, x))

    def test_batch_of_empty_search_responses_is_rejected(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
        ):
            candidate_path = Path(td) / "2026-08-14-candidates.csv"
            with candidate_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=(
                        "batch_index",
                        "id",
                        "surface",
                        "pronunciation",
                        "rank",
                        "query",
                    ),
                )
                writer.writeheader()
                for index in range(20):
                    writer.writerow(
                        {
                            "batch_index": index,
                            "id": index + 1,
                            "surface": "榎谷",
                            "pronunciation": "エノキヤ",
                            "rank": "1",
                            "query": "榎谷 えのきや 氏名",
                        }
                    )
            result_path = Path(td) / "2026-08-14-a.jsonl"
            records = []
            for index in range(20):
                record = self.record()
                record["batch_index"] = index
                records.append(json.dumps(record, ensure_ascii=False))
            result_path.write_text("\n".join(records) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "implausibly few"):
                a.load_results("2026-08-14", [result_path])

    def test_known_positive_control_cannot_be_returned_to_no(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
        ):
            self.candidates(td)
            (Path(td) / "2026-08-14-controls.csv").write_text(
                "surface,pronunciation,status\n榎谷,エノキヤ,verified\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "known control failed"):
                a.load_results("2026-08-14", self.write(td, self.record()))

    def test_exact_verified_requires_identity_basis_and_tier(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
        ):
            self.candidates(td)
            x = self.record("verified")
            x.update(
                evidence_tier="A",
                identity_basis="same_record",
                source_url="https://example.jp/p",
                source_type="official_person_profile",
                source_title="P",
                observed_surface="榎谷",
                observed_reading="エノキヤ",
                locator="line 1",
            )
            self.assertEqual(len(a.load_results("2026-08-14", self.write(td, x))), 1)

    def test_verified_observed_reading_accepts_hiragana(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
        ):
            self.candidates(td)
            x = self.record("verified")
            x.update(
                evidence_tier="A",
                identity_basis="same_row",
                source_url="https://example.jp/p",
                source_type="official_org_directory",
                source_title="P",
                observed_surface="榎谷",
                observed_reading="えのきや",
                locator="line 1",
            )
            self.assertEqual(len(a.load_results("2026-08-14", self.write(td, x))), 1)

    def test_prepare_ignores_old_official_logs(self):
        rows = [
            {
                "id": "1",
                "original": "榎谷",
                "surface": "榎谷",
                "pronunciation": "エノキヤ",
                "verified": "no",
                "rank": "1",
                "evidence_sources": "",
            }
        ]
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "CSV_PATH", Path(td) / "myoji.csv"),
            mock.patch.object(a, "RESEARCH_DIR", Path(td) / "new"),
        ):
            with (Path(td) / "myoji.csv").open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=rows[0])
                w.writeheader()
                w.writerows(rows)
            # An old official-web log is outside the new research directory and
            # must not suppress this independent recheck.
            (Path(td) / "old-official.jsonl").write_text(
                json.dumps({"surface": "榎谷", "pronunciation": "エノキヤ"}),
                encoding="utf-8",
            )
            a.prepare("2026-08-14")
            self.assertEqual(
                (Path(td) / "new/2026-08-14-candidates.csv")
                .read_text(encoding="utf-8")
                .count("榎谷"),
                2,
            )

    def test_candidate_exclusion_ignores_raw_excerpt_ledgers(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
        ):
            # U+2028 is valid inside a JSON string but splitlines() treats it as
            # a line boundary. Raw search material must never be parsed as a
            # reviewed result ledger.
            (Path(td) / "2026-08-14-p1-main-excerpts.jsonl").write_text(
                '{"surface":"榎谷","excerpt":"a\u2028b"}\n', encoding="utf-8"
            )
            self.assertEqual(a._new_pairs(), set())

    def promote_fixture(self, td, status="verified"):
        self.candidates(td)
        result = self.record(status)
        if status == "verified":
            result.update(
                evidence_tier="A",
                identity_basis="same_record",
                source_url="https://example.jp/new",
                source_type="official_person_profile",
                source_title="New profile",
                observed_surface="榎谷",
                observed_reading="エノキヤ",
                locator="line 2",
            )
        self.write(td, result)

    def test_replace_existing_rebuilds_scope_and_updates_evidence(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
            mock.patch.object(a, "EVIDENCE_PATH", Path(td) / "ledger.jsonl"),
        ):
            self.promote_fixture(td, "verified")
            outside = {
                "surface": "外姓",
                "pronunciation": "ガイセイ",
                "status": "verified",
                "source_url": "https://example.jp/outside",
            }
            stale = {
                "surface": "榎谷",
                "pronunciation": "エノキヤ",
                "status": "verified",
                "source_url": "https://example.jp/stale",
            }
            a.EVIDENCE_PATH.write_text(
                "\n".join(json.dumps(x, ensure_ascii=False) for x in (outside, stale))
                + "\n",
                encoding="utf-8",
            )
            a.promote("2026-08-14", replace_existing=True)
            rows = [
                json.loads(line)
                for line in a.EVIDENCE_PATH.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [(x["surface"], x["source_url"]) for x in rows],
                [
                    ("外姓", "https://example.jp/outside"),
                    ("榎谷", "https://example.jp/new"),
                ],
            )

    def test_promote_default_keeps_existing_scope_row(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
            mock.patch.object(a, "EVIDENCE_PATH", Path(td) / "ledger.jsonl"),
        ):
            self.promote_fixture(td, "verified")
            old = {
                "surface": "榎谷",
                "pronunciation": "エノキヤ",
                "status": "verified",
                "source_url": "https://example.jp/old",
            }
            a.EVIDENCE_PATH.write_text(json.dumps(old) + "\n", encoding="utf-8")
            a.promote("2026-08-14")
            self.assertEqual(
                json.loads(a.EVIDENCE_PATH.read_text())["source_url"], old["source_url"]
            )

    def test_replace_existing_rejects_duplicate_ledger_pair(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.object(a, "RESEARCH_DIR", Path(td)),
            mock.patch.object(a, "EVIDENCE_PATH", Path(td) / "ledger.jsonl"),
        ):
            self.promote_fixture(td, "no_support_found")
            duplicate = {"surface": "榎谷", "pronunciation": "エノキヤ"}
            a.EVIDENCE_PATH.write_text(
                json.dumps(duplicate) + "\n" + json.dumps(duplicate) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "duplicate pair"):
                a.promote("2026-08-14", replace_existing=True)


if __name__ == "__main__":
    unittest.main()
