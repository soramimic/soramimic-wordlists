import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_player_descriptions as player_sources
import enrich_player_descriptions_openai as target
import validate_openai_player_description_sources as source_validator
from openai_source_selector import Selection


BASEBALL_COLUMNS = [
    "id", "original", "team", "surface", "pronunciation", "type",
    "org_id", "image", "image_page", "position", "description",
]


class FakeSelector:
    def __init__(self, choices):
        self.choices = choices
        self.calls = []

    def select(self, records, cache_only=False):
        records = list(records)
        self.calls.append((records, cache_only))
        return {record.key: self.choices[record.key] for record in records}


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def baseball_rows(description="NA。"):
    common = {
        "id": "1",
        "original": "山田 太郎",
        "team": "東京",
        "org_id": "player-1",
        "image": "",
        "image_page": "",
        "position": "内野手",
        "description": description,
    }
    return [
        {**common, "surface": "山田 太郎", "pronunciation": "ヤマダ タロウ", "type": "full"},
        {**common, "surface": "山田", "pronunciation": "ヤマダ", "type": "family"},
    ]


def source_cache():
    cache = {
        "山田太郎": {
            "title": "山田太郎",
            "intro": (
                "山田 太郎（やまだ たろう）は、日本のプロ野球選手。"
                "2025年に新人王を受賞した。"
            ),
            "disambiguation": False,
            "qid": "Q1",
            "revision": "12345",
        }
    }
    for title in target.source_titles("baseball", "1", baseball_rows(), {}):
        cache.setdefault(title, {
            "title": title,
            "intro": "",
            "disambiguation": False,
            "qid": "",
            "revision": "",
        })
    return cache


class EnrichPlayerDescriptionsOpenAITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.csv_path = self.root / "baseball.csv"
        self.provenance_path = self.root / "sources.jsonl"
        self.pending_path = self.root / "pending.jsonl"
        write_csv(self.csv_path, BASEBALL_COLUMNS, baseball_rows())
        self.config = {**target.CONFIG["baseball"], "path": self.csv_path}

    def process(self, selector, mode, **kwargs):
        options = {
            "mode": mode,
            "selector": selector,
            "changed_from": None,
            "include_missing": True,
            "include_degraded": False,
            "limit": 100,
            "start_after": None,
            "cache_only": mode == "apply",
            "source_cache": source_cache(),
            "fetcher": lambda titles, cache: None,
            "verified": {"1": {"article": "山田太郎", "qid": "Q1"}},
            "provenance_path": self.provenance_path,
            "pending_path": self.pending_path,
        }
        options.update(kwargs)
        with mock.patch.dict(target.CONFIG, {"baseball": self.config}):
            return target.process_kind("baseball", **options)

    def test_fetch_caches_selection_without_changing_csv(self):
        before = self.csv_path.read_bytes()
        selector = FakeSelector({
            "baseball:1": Selection(
                "select", "2025年に新人王を受賞した。", "source_excerpt_preferred"
            )
        })

        candidates, updated = self.process(selector, "fetch")

        self.assertEqual((1, 0), (candidates, updated))
        self.assertEqual(before, self.csv_path.read_bytes())
        self.assertEqual(1, len(selector.calls))
        records, cache_only = selector.calls[0]
        self.assertFalse(cache_only)
        self.assertEqual("12345", records[0].revision)
        self.assertIn("2025年に新人王を受賞した。", records[0].source)

    def test_cache_only_apply_updates_every_row_of_the_same_id_atomically(self):
        selector = FakeSelector({
            "baseball:1": Selection(
                "select", "2025年に新人王を受賞した。", "source_excerpt_preferred"
            )
        })

        candidates, updated = self.process(selector, "apply")

        self.assertEqual((1, 1), (candidates, updated))
        with self.csv_path.open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(
            {"2025年に新人王を受賞した。"},
            {row["description"] for row in rows},
        )
        self.assertTrue(selector.calls[0][1])
        self.assertFalse(self.csv_path.read_bytes().endswith(b"\n"))
        provenance = target.load_provenance(self.provenance_path)
        self.assertEqual("Q1", provenance[("baseball", "1")]["qid"])
        self.assertEqual(
            "2025年に新人王を受賞した。",
            provenance[("baseball", "1")]["source_excerpt"],
        )
        self.assertFalse(self.provenance_path.read_bytes().endswith(b"\n"))

        with (
            mock.patch.dict(target.CONFIG, {"baseball": self.config}, clear=True),
            mock.patch.object(target, "PROVENANCE_PATH", self.provenance_path),
            mock.patch.object(target, "PENDING_PATH", self.pending_path),
            mock.patch.object(
                target,
                "load_verified_sources",
                return_value={
                    "1": {
                        "article": "山田太郎", "qid": "Q1", "method": "test",
                    }
                },
            ),
        ):
            source_validator.validate()

    def test_keep_and_abstain_do_not_write(self):
        before = self.csv_path.read_bytes()
        for selection in (
            Selection("keep", "日本のプロ野球選手。", "draft_supported"),
            Selection("abstain", "", "no_supported_excerpt"),
        ):
            with self.subTest(action=selection.action):
                selector = FakeSelector({"baseball:1": selection})
                self.process(selector, "apply")
                self.assertEqual(before, self.csv_path.read_bytes())

    def test_keep_does_not_drop_a_degraded_candidate_from_pending(self):
        selector = FakeSelector({
            "baseball:1": Selection(
                "keep", "日本のプロ野球選手。", "draft_supported"
            )
        })

        self.process(selector, "apply")

        pending = target.load_pending(self.pending_path)
        self.assertEqual(
            "no_supported_excerpt",
            pending[("baseball", "1")]["reason"],
        )

    def test_abstain_preserves_provenance_that_still_matches_the_csv(self):
        write_csv(
            self.csv_path,
            BASEBALL_COLUMNS,
            baseball_rows("2025年に新人王を受賞した。"),
        )
        candidate = target.PlayerCandidate(
            "baseball",
            "1",
            "山田太郎",
            target.SourceRecord(
                key="baseball:1",
                title="山田太郎",
                source="2025年に新人王を受賞した。",
                revision="12345",
                draft="2025年に新人王を受賞した。",
            ),
            "Q1",
        )
        source_record = target.provenance_record(
            candidate,
            Selection(
                "select",
                "2025年に新人王を受賞した。",
                "source_excerpt_preferred",
            ),
            "2025年に新人王を受賞した。",
        )
        self.provenance_path.write_bytes(target.jsonl_bytes([source_record]))
        selector = FakeSelector({
            "baseball:1": Selection("abstain", "", "no_supported_excerpt")
        })

        with mock.patch.object(
            target,
            "rows_from_git",
            return_value=baseball_rows("以前の説明。"),
        ):
            self.process(
                selector,
                "apply",
                changed_from="HEAD",
                include_missing=False,
            )

        self.assertEqual(
            source_record,
            target.load_provenance(self.provenance_path)[("baseball", "1")],
        )
        self.assertNotIn(("baseball", "1"), target.load_pending(self.pending_path))

    def test_invalid_selected_excerpt_becomes_abstain_before_csv_write(self):
        before = self.csv_path.read_bytes()
        selector = FakeSelector({
            "baseball:1": Selection(
                "select", "出典にない要約。", "source_excerpt_preferred"
            )
        })

        candidates, updated = self.process(selector, "apply")

        self.assertEqual((1, 0), (candidates, updated))
        self.assertEqual(before, self.csv_path.read_bytes())

    def test_selected_excerpt_must_start_and_end_at_source_sentence_boundaries(self):
        candidate = target.PlayerCandidate(
            kind="baseball",
            group_id="1",
            title="山田太郎",
            record=target.SourceRecord(
                key="baseball:1",
                title="山田太郎",
                source="山田太郎は選手。2025年に新人王を受賞した。",
                revision="1",
                draft="",
            ),
        )
        for excerpt in ("受賞", "新人王を受賞した。"):
            with self.subTest(excerpt=excerpt):
                with self.assertRaisesRegex(ValueError, "complete source sentence"):
                    target.render_selected_description(
                        candidate,
                        Selection("select", excerpt, "source_excerpt_preferred"),
                    )
        self.assertEqual(
            "2025年に新人王を受賞した。",
            target.render_selected_description(
                candidate,
                Selection(
                    "select", "2025年に新人王を受賞した。",
                    "source_excerpt_preferred",
                ),
            ),
        )

    def test_selector_batches_leave_output_room_for_reasoning_and_json(self):
        candidates = [
            target.PlayerCandidate(
                "baseball",
                str(index),
                f"選手{index}",
                target.SourceRecord(
                    key=f"baseball:{index}",
                    title=f"選手{index}",
                    source="日本のプロ野球選手。",
                    revision="1",
                    draft="",
                ),
                f"Q{index + 1}",
            )
            for index in range(21)
        ]
        selector = FakeSelector({
            candidate.record.key: Selection(
                "abstain", "", "no_supported_excerpt"
            )
            for candidate in candidates
        })

        result = target.select_in_batches(selector, candidates, cache_only=False)

        self.assertEqual(21, len(result))
        self.assertEqual([10, 10, 1], [len(call[0]) for call in selector.calls])

    def test_source_selector_never_uses_player_description_overrides(self):
        candidate = target.PlayerCandidate(
            kind="baseball",
            group_id="1",
            title="大谷翔平",
            record=target.SourceRecord(
                key="baseball:1",
                title="大谷翔平",
                source="大谷翔平は、日本のプロ野球選手。",
                revision="1",
                draft="",
            ),
        )
        selection = Selection(
            "select", "大谷翔平は、日本のプロ野球選手。",
            "source_excerpt_preferred",
        )

        self.assertEqual(
            "日本のプロ野球選手。",
            target.render_selected_description(candidate, selection),
        )

    def test_disambiguation_suffix_is_not_treated_as_part_of_player_name(self):
        candidate = target.PlayerCandidate(
            kind="baseball",
            group_id="274",
            title="荒川哲男 (野球)",
            record=target.SourceRecord(
                key="baseball:274",
                title="荒川哲男 (野球)",
                source="荒川 哲男は、埼玉県出身の元プロ野球選手。",
                revision="1",
                draft="",
            ),
            qid="Q11618546",
        )
        selection = Selection(
            "select",
            "荒川 哲男は、埼玉県出身の元プロ野球選手。",
            "source_excerpt_preferred",
        )

        self.assertEqual(
            "埼玉県出身の元プロ野球選手。",
            target.render_selected_description(candidate, selection),
        )
        self.assertEqual("荒川哲男 (野球)", candidate.title)

    def test_legacy_baseball_group_with_multiple_source_players_is_deferred(self):
        rows = baseball_rows()
        rows.append({**rows[0], "org_id": "player-2", "pronunciation": "ヤマダジロウ"})
        groups = target.group_rows(rows)
        article = source_cache()["山田太郎"]

        self.assertFalse(
            target.source_matches_identity("baseball", "1", groups["1"], article, {})
        )

    def test_same_name_and_reading_in_different_baseball_ids_are_deferred(self):
        first = baseball_rows()
        second = [
            {**row, "id": "2", "org_id": "player-2", "team": "大阪"}
            for row in baseball_rows()
        ]
        groups = target.group_rows(first + second)

        candidates = target.build_candidates(
            "baseball",
            groups,
            ["1", "2"],
            source_cache(),
            {
                "1": {"article": "山田太郎", "qid": "Q1"},
                "2": {"article": "山田太郎", "qid": "Q1"},
            },
        )

        self.assertEqual([], candidates)

    def test_explicit_source_reading_must_match_full_row(self):
        rows = baseball_rows()
        rows[0]["pronunciation"] = "ヤマダ ジロウ"
        article = source_cache()["山田太郎"]

        self.assertFalse(target.source_matches_identity("baseball", "1", rows, article, {}))

    def test_sport_and_same_name_without_qid_or_reading_are_not_identity_evidence(self):
        rows = baseball_rows()
        article = {
            "title": "山田太郎",
            "intro": "山田太郎は、日本のプロ野球選手。",
            "disambiguation": False,
            "qid": "Q999",
            "revision": "1",
        }

        self.assertFalse(
            target.source_matches_identity("baseball", "1", rows, article, {})
        )

    def test_matching_reading_alone_is_not_identity_evidence(self):
        rows = baseball_rows()
        article = source_cache()["山田太郎"]

        self.assertFalse(
            target.source_matches_identity("baseball", "1", rows, article, {})
        )

    def test_verified_football_article_is_identity_evidence_without_reading(self):
        rows = [{
            "id": "7", "original": "アイメン・タハール",
            "surface": "アイメン・タハール", "pronunciation": "アイメン タハール",
            "type": "full", "wikidata": "", "description": "",
        }]
        article = {
            "title": "アイメン・タハール",
            "intro": "アイメン・タハール（Aymen Tahar）はサッカー選手。",
            "disambiguation": False,
            "qid": "Q7",
            "revision": "1",
        }
        verified = {"7": {"article": "アイメン・タハール", "qid": "Q7"}}

        self.assertTrue(target.source_matches_identity(
            "football", "7", rows, article, verified, "アイメン・タハール"
        ))

    def test_football_qid_must_match_existing_identity(self):
        rows = [{
            "id": "7", "original": "山田 太郎", "surface": "山田 太郎",
            "pronunciation": "ヤマダ タロウ", "type": "full",
            "wikidata": "Q7", "description": "",
        }]
        article = {
            "intro": "山田 太郎（やまだ たろう）は、日本のサッカー選手。",
            "disambiguation": False,
            "qid": "Q8",
            "revision": "42",
        }

        self.assertFalse(target.source_matches_identity("football", "7", rows, article, {}))
        article["qid"] = "Q7"
        self.assertTrue(target.source_matches_identity("football", "7", rows, article, {}))

    def test_conflicting_existing_and_verified_qids_are_deferred(self):
        rows = [{
            "id": "7", "original": "山田 太郎", "surface": "山田 太郎",
            "pronunciation": "ヤマダ タロウ", "type": "full",
            "wikidata": "Q7", "description": "",
        }]
        article = {
            "title": "山田太郎",
            "intro": "山田 太郎（やまだ たろう）は、日本のサッカー選手。",
            "disambiguation": False,
            "qid": "Q7",
            "revision": "42",
        }
        verified = {"7": {"article": "山田太郎", "qid": "Q8"}}

        self.assertFalse(target.source_matches_identity(
            "football", "7", rows, article, verified, "山田太郎"
        ))

    def test_missing_revision_is_not_sent_to_selector(self):
        rows = baseball_rows()
        article = source_cache()["山田太郎"]
        article["revision"] = ""

        self.assertFalse(target.source_matches_identity("baseball", "1", rows, article, {}))

    def test_changed_ids_include_only_new_or_description_changed_groups(self):
        previous = [
            {"id": "1", "description": "既存。"},
            {"id": "2", "description": "旧案。"},
        ]
        current = target.group_rows([
            {"id": "1", "description": "既存。"},
            {"id": "2", "description": "新案。"},
            {"id": "3", "description": "追加。"},
        ])

        self.assertEqual(
            {"2", "3"}, target.changed_description_ids(current, previous)
        )

    def test_changed_from_never_silently_truncates_one_time_targets(self):
        groups = target.group_rows([
            {"id": str(index), "description": "追加。"} for index in range(3)
        ])
        with self.assertRaisesRegex(ValueError, "changed groups exceed"):
            target.target_group_ids(
                groups,
                previous_rows=[],
                include_missing=False,
                include_degraded=False,
                limit=2,
            )

    def test_backlog_cursor_advances_past_persistent_abstentions(self):
        groups = target.group_rows([
            {"id": str(index), "description": ""} for index in range(5)
        ])

        first = target.target_group_ids(
            groups,
            previous_rows=None,
            include_missing=True,
            include_degraded=False,
            limit=2,
        )
        second = target.target_group_ids(
            {key: value for key, value in groups.items() if key != first[-1]},
            previous_rows=None,
            include_missing=True,
            include_degraded=False,
            limit=2,
            start_after=first[-1],
        )

        self.assertEqual(["0", "1"], first)
        self.assertEqual(["2", "3"], second)

    def test_monthly_pending_queue_rotates_by_attempt_count(self):
        groups = target.group_rows([
            {"id": str(index), "description": "既存。"} for index in range(4)
        ])

        selected = target.target_group_ids(
            groups,
            previous_rows=[
                {"id": str(index), "description": "既存。"}
                for index in range(4)
            ],
            include_missing=False,
            include_degraded=False,
            limit=2,
            pending_attempts={"1": 3, "2": 1, "3": 1},
        )

        self.assertEqual(["2", "3"], selected)

    def test_offline_apply_requires_raw_cache_without_calling_fetcher(self):
        called = False

        def fail_fetch(_titles, _cache):
            nonlocal called
            called = True
            raise AssertionError("apply must not fetch")

        incomplete = source_cache()
        incomplete.pop("山田 太郎")
        selector = FakeSelector({
            "baseball:1": Selection(
                "select", "2025年に新人王を受賞した。",
                "source_excerpt_preferred",
            )
        })

        with self.assertRaisesRegex(ValueError, "raw source cache is incomplete"):
            self.process(
                selector,
                "apply",
                source_cache=incomplete,
                fetcher=fail_fetch,
            )
        self.assertFalse(called)

    def test_abstain_is_persisted_and_retried_with_incremented_attempts(self):
        selector = FakeSelector({
            "baseball:1": Selection("abstain", "", "ambiguous_source")
        })

        self.process(selector, "apply")
        self.process(selector, "apply")

        pending = target.load_pending(self.pending_path)
        self.assertEqual(2, pending[("baseball", "1")]["attempts"])
        self.assertEqual("ambiguous_source", pending[("baseball", "1")]["reason"])

    def test_known_disambiguation_text_is_a_degraded_candidate(self):
        self.assertTrue(target.is_degraded_description(
            "山田太郎（野球選手） - 日本のプロ野球選手。"
        ))
        self.assertFalse(target.is_degraded_description(
            "日本のプロ野球選手。"
        ))

    def test_verified_football_article_is_first_candidate(self):
        rows = [{
            "id": "7", "original": "山田 太郎", "surface": "山田 太郎",
            "pronunciation": "ヤマダ タロウ", "type": "full",
        }]
        verified = {"7": {"article": "山田太郎 (サッカー選手)"}}

        titles = target.source_titles("football", "7", rows, verified)

        self.assertEqual("山田太郎 (サッカー選手)", titles[0])
        self.assertIn("山田太郎", titles)

    def test_baseball_does_not_reuse_football_identity_ledger(self):
        football_sources = self.root / "football.jsonl"
        football_sources.write_text(
            '{"verified_id":"1","article":"別人","qid":"Q9"}',
            encoding="utf-8",
        )
        baseball_sources = self.root / "missing-baseball.jsonl"

        with (
            mock.patch.object(target, "VERIFIED_FOOTBALL_SOURCES", football_sources),
            mock.patch.object(target, "VERIFIED_BASEBALL_SOURCES", baseball_sources),
        ):
            self.assertEqual({}, target.load_verified_sources("baseball"))
            self.assertEqual("別人", target.load_verified_sources("football")["1"]["article"])

    def test_source_fetch_records_revision_qid_and_disambiguation(self):
        def fake_api(_params):
            return {"query": {"pages": {"1": {
                "title": "山田太郎",
                "extract": "山田太郎は日本の野球選手。",
                "pageprops": {"wikibase_item": "Q1"},
                "revisions": [{"revid": 987}],
            }}}}

        with mock.patch.object(player_sources, "api", fake_api):
            result = player_sources.fetch_intro_batch(["山田太郎"])

        self.assertEqual("Q1", result["山田太郎"]["qid"])
        self.assertEqual("987", result["山田太郎"]["revision"])
        self.assertFalse(result["山田太郎"]["disambiguation"])

    def test_default_plan_does_not_construct_selector_or_write_cache(self):
        with (
            mock.patch.dict(target.CONFIG, {"baseball": self.config}),
            mock.patch.object(
                target, "SourceSelector", side_effect=AssertionError("must not construct")
            ),
        ):
            result = target.main(["baseball", "--include-missing", "--limit", "1"])

        self.assertEqual(0, result)

    def test_all_apply_restores_both_lists_and_ledgers_on_second_kind_failure(self):
        football_path = self.root / "football.csv"
        football_path.write_bytes(b"football-before")
        self.csv_path.write_bytes(b"baseball-before")
        self.provenance_path.write_bytes(b"provenance-before")
        self.pending_path.write_bytes(b"pending-before")
        configs = {
            "baseball": {**target.CONFIG["baseball"], "path": self.csv_path},
            "football": {**target.CONFIG["football"], "path": football_path},
        }

        def fake_process(kind, **_kwargs):
            if kind == "baseball":
                self.csv_path.write_bytes(b"baseball-after")
                self.provenance_path.write_bytes(b"provenance-after")
                return 1, 1
            raise ValueError("football apply failed")

        with (
            mock.patch.dict(target.CONFIG, configs, clear=True),
            mock.patch.object(target, "PROVENANCE_PATH", self.provenance_path),
            mock.patch.object(target, "PENDING_PATH", self.pending_path),
            mock.patch.object(target, "SourceSelector", return_value=object()),
            mock.patch.object(target, "process_kind", side_effect=fake_process),
        ):
            result = target.main([
                "all", "--apply", "--cache-only", "--include-missing",
            ])

        self.assertEqual(1, result)
        self.assertEqual(b"baseball-before", self.csv_path.read_bytes())
        self.assertEqual(b"football-before", football_path.read_bytes())
        self.assertEqual(b"provenance-before", self.provenance_path.read_bytes())
        self.assertEqual(b"pending-before", self.pending_path.read_bytes())

    def test_cli_requires_cache_only_for_apply_and_caps_daily_budget(self):
        with self.assertRaises(SystemExit):
            target.parse_args(["baseball", "--apply", "--include-missing"])
        with self.assertRaises(SystemExit):
            target.parse_args([
                "baseball", "--fetch", "--include-missing",
                "--daily-token-budget", "2000001",
            ])


if __name__ == "__main__":
    unittest.main()
