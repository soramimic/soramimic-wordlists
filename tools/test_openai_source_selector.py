import io
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent))
import openai_source_selector as selector  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class QueueOpener:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append({
            "url": request.full_url,
            "method": request.get_method(),
            "headers": dict(request.header_items()),
            "body": json.loads(request.data.decode("utf-8")),
            "timeout": timeout,
        })
        if not self.results:
            raise AssertionError("unexpected network call")
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        if callable(result):
            result = result(request)
        return FakeResponse(result)


class MutableClock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def count_response(tokens=23):
    return {"object": "response.input_tokens", "input_tokens": tokens}


def response_items(items, *, input_tokens=23, total_tokens=31,
                   response_id="resp_test", status="completed",
                   model="gpt-5.6-terra", service_tier="default"):
    output_tokens = total_tokens - input_tokens
    if output_tokens < 0:
        raise ValueError("total_tokens must be at least input_tokens")
    text = json.dumps({"items": items}, ensure_ascii=False)
    return {
        "id": response_id,
        "object": "response",
        "model": model,
        "service_tier": service_tier,
        "status": status,
        "output": [{
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        }],
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
    }


def valid_items(records):
    items = []
    for index, record in enumerate(records):
        if index % 3 == 0 and record.draft:
            items.append({
                "key": record.key,
                "action": "keep",
                "excerpt": record.source,
                "reason_code": "draft_supported",
            })
        elif index % 3 == 1:
            items.append({
                "key": record.key,
                "action": "select",
                "excerpt": record.source,
                "reason_code": "source_excerpt_preferred",
            })
        else:
            items.append({
                "key": record.key,
                "action": "abstain",
                "excerpt": "",
                "reason_code": "no_supported_excerpt",
            })
    return items


class SourceSelectorTest(unittest.TestCase):
    NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.records = (
            selector.SourceRecord(
                "alpha", "甲", "甲は海辺で活動する人物。", "101",
                "海辺で活動する人物。",
            ),
            selector.SourceRecord(
                "beta", "乙", "乙は長年にわたり音楽を配信した。", 202,
                "音楽を配信した。",
            ),
        )

    def make_selector(self, opener, *, db_name="state.sqlite3", **kwargs):
        options = {
            "api_key": "sk-test-secret",
            "db_path": self.root / db_name,
            "attestation": "2026-08-31",
            "opener": opener,
            "clock": lambda: self.NOW,
            "max_output_tokens": 64,
        }
        options.update(kwargs)
        return selector.SourceSelector(**options)

    def ledger_rows(self, db_name="state.sqlite3"):
        with sqlite3.connect(self.root / db_name) as connection:
            return connection.execute(
                """
                SELECT utc_date, reserved_tokens, actual_tokens, status, response_id
                FROM token_reservations ORDER BY id
                """
            ).fetchall()

    def cross_day_rows(self, db_name="state.sqlite3"):
        with sqlite3.connect(self.root / db_name) as connection:
            return connection.execute(
                """
                SELECT utc_date, actual_tokens, response_id
                FROM cross_day_usage ORDER BY reservation_id
                """
            ).fetchall()

    def test_success_uses_exact_count_body_and_locked_response_contract(self):
        items = valid_items(self.records)
        opener = QueueOpener(
            count_response(23),
            response_items(items, total_tokens=31),
        )
        service = self.make_selector(opener)

        # Input order is preserved in the returned mapping even though request
        # records are sorted by key for a stable cache key.
        result = service.select(tuple(reversed(self.records)))

        self.assertEqual(["beta", "alpha"], list(result))
        self.assertEqual("select", result["beta"].action)
        self.assertEqual(self.records[1].source, result["beta"].excerpt)
        self.assertEqual(2, len(opener.calls))
        count_call, response_call = opener.calls
        self.assertEqual(
            "https://api.openai.com/v1/responses/input_tokens",
            count_call["url"],
        )
        self.assertEqual(
            "https://api.openai.com/v1/responses",
            response_call["url"],
        )
        self.assertEqual("POST", count_call["method"])
        self.assertEqual(set(selector.COUNT_FIELDS), set(count_call["body"]))
        for field in selector.COUNT_FIELDS:
            self.assertEqual(response_call["body"][field], count_call["body"][field])
        for excluded in ("max_output_tokens", "store", "service_tier"):
            self.assertNotIn(excluded, count_call["body"])

        body = response_call["body"]
        self.assertEqual("gpt-5.6-terra", body["model"])
        self.assertIn("source-selector-v2", body["instructions"])
        input_payload = json.loads(body["input"][0]["content"][0]["text"])
        self.assertEqual(
            "select_complete_verbatim_supporting_sentences",
            input_payload["task"],
        )
        self.assertIs(False, body["store"])
        self.assertEqual("default", body["service_tier"])
        self.assertEqual([], body["tools"])
        self.assertEqual("none", body["tool_choice"])
        self.assertIs(False, body["parallel_tool_calls"])
        self.assertEqual("disabled", body["truncation"])
        self.assertEqual({"effort": "low"}, body["reasoning"])
        output_format = body["text"]["format"]
        self.assertEqual("json_schema", output_format["type"])
        self.assertIs(True, output_format["strict"])
        self.assertIs(False, output_format["schema"]["additionalProperties"])
        item_schema = output_format["schema"]["properties"]["items"]["items"]
        self.assertIs(False, item_schema["additionalProperties"])
        self.assertEqual(["alpha", "beta"], item_schema["properties"]["key"]["enum"])
        self.assertEqual(
            [("2026-08-25", 87, 31, "completed", "resp_test")],
            self.ledger_rows(),
        )

    def test_cache_only_hit_needs_no_key_attestation_or_network(self):
        opener = QueueOpener(
            count_response(),
            response_items(valid_items(self.records)),
        )
        self.make_selector(opener).select(self.records)
        no_network = QueueOpener()
        cached_service = selector.SourceSelector(
            db_path=self.root / "state.sqlite3",
            opener=no_network,
            clock=lambda: self.NOW,
            max_output_tokens=64,
        )

        result = cached_service.select(self.records, cache_only=True)

        self.assertEqual(set(("alpha", "beta")), set(result))
        self.assertEqual([], no_network.calls)
        self.assertEqual(1, len(self.ledger_rows()))

    def test_cache_only_miss_is_explicit_and_never_uses_network(self):
        opener = QueueOpener()
        service = selector.SourceSelector(
            db_path=self.root / "state.sqlite3",
            opener=opener,
            clock=lambda: self.NOW,
            max_output_tokens=64,
        )

        with self.assertRaises(selector.CacheMissError) as raised:
            service.select(self.records, cache_only=True)

        self.assertEqual(("alpha", "beta"), raised.exception.keys)
        self.assertEqual([], opener.calls)

    def test_cache_is_content_addressed_by_source_revision_and_draft(self):
        opener = QueueOpener(
            count_response(),
            response_items(valid_items(self.records)),
        )
        service = self.make_selector(opener)
        service.select(self.records)
        changed = (
            self.records[0],
            selector.SourceRecord(
                "beta", "乙", self.records[1].source + "追記。", 203,
                self.records[1].draft,
            ),
        )

        with self.assertRaises(selector.CacheMissError):
            service.select(changed, cache_only=True)

        self.assertEqual(2, len(opener.calls))

    def test_missing_malformed_and_expired_attestation_fail_before_network(self):
        values = (None, "", "2026/08/31", "2026-02-30", "2026-08-24")
        for index, value in enumerate(values):
            with self.subTest(value=value):
                opener = QueueOpener()
                service = selector.SourceSelector(
                    api_key="sk-test-secret",
                    db_path=self.root / f"attestation-{index}.sqlite3",
                    attestation=value,
                    opener=opener,
                    clock=lambda: self.NOW,
                    max_output_tokens=64,
                )
                with mock.patch.dict(
                    "os.environ", {selector.ATTESTATION_ENV: ""}, clear=False
                ):
                    with self.assertRaises(selector.AttestationError):
                        service.select(self.records)
                self.assertEqual([], opener.calls)

    def test_cache_miss_requires_api_key_after_valid_attestation(self):
        opener = QueueOpener()
        service = selector.SourceSelector(
            api_key="",
            db_path=self.root / "state.sqlite3",
            attestation="2026-08-25",
            opener=opener,
            clock=lambda: self.NOW,
            max_output_tokens=64,
        )
        with mock.patch.dict("os.environ", {selector.API_KEY_ENV: ""}):
            with self.assertRaises(selector.ConfigurationError):
                service.select(self.records)
        self.assertEqual([], opener.calls)

    def test_attestation_date_is_evaluated_in_utc_and_is_inclusive(self):
        # 2026-08-26 in JST is still 2026-08-25 UTC.
        jst = timezone(timedelta(hours=9))
        now = datetime(2026, 8, 26, 0, 30, tzinfo=jst)
        opener = QueueOpener(
            count_response(), response_items(valid_items(self.records))
        )
        service = selector.SourceSelector(
            api_key="sk-test-secret",
            db_path=self.root / "state.sqlite3",
            attestation="2026-08-25",
            opener=opener,
            clock=lambda: now,
            max_output_tokens=64,
        )
        service.select(self.records)
        self.assertEqual(2, len(opener.calls))

    def test_budget_cannot_be_configured_above_hard_ceiling(self):
        with self.assertRaises(selector.ConfigurationError):
            selector.SourceSelector(
                db_path=self.root / "state.sqlite3",
                daily_token_budget=selector.MAX_DAILY_TOKEN_BUDGET + 1,
            )
        with self.assertRaises(selector.ConfigurationError):
            selector.SourceSelector(
                db_path=self.root / "state.sqlite3",
                daily_token_budget=True,
            )

    def test_request_crossing_budget_is_not_submitted_or_reserved(self):
        opener = QueueOpener(count_response(61))
        service = self.make_selector(
            opener,
            daily_token_budget=100,
            max_output_tokens=40,
        )

        with self.assertRaises(selector.DailyBudgetExceeded) as raised:
            service.select(self.records)

        self.assertEqual(0, raised.exception.used)
        self.assertEqual(101, raised.exception.requested)
        self.assertEqual(1, len(opener.calls))
        self.assertEqual([], self.ledger_rows())

    def test_timeout_keeps_unresolved_worst_case_and_response_is_not_retried(self):
        opener = QueueOpener(
            count_response(20),
            urllib.error.URLError("connection lost after submission"),
        )
        service = self.make_selector(opener, max_output_tokens=30)

        with self.assertRaises(selector.APIError):
            service.select(self.records)

        self.assertEqual(2, len(opener.calls))
        self.assertEqual(
            [("2026-08-25", 50, None, "pending", None)],
            self.ledger_rows(),
        )
        with self.assertRaises(selector.ReservationExistsError):
            service.select(self.records)
        # Existing reservation is noticed before another count or submission.
        self.assertEqual(2, len(opener.calls))

    def test_pending_reservation_counts_at_worst_case_for_other_requests(self):
        first_opener = QueueOpener(
            count_response(20), urllib.error.URLError("unknown outcome")
        )
        first = self.make_selector(
            first_opener,
            daily_token_budget=100,
            max_output_tokens=30,
        )
        with self.assertRaises(selector.APIError):
            first.select(self.records)

        changed = (
            self.records[0],
            selector.SourceRecord(
                "beta", "乙", self.records[1].source + "追記。", 203,
                self.records[1].draft,
            ),
        )
        second_opener = QueueOpener(count_response(21))
        second = self.make_selector(
            second_opener,
            daily_token_budget=100,
            max_output_tokens=30,
        )
        with self.assertRaises(selector.DailyBudgetExceeded) as raised:
            second.select(changed)
        self.assertEqual(50, raised.exception.used)
        self.assertEqual(51, raised.exception.requested)
        self.assertEqual(1, len(second_opener.calls))

    def test_concurrent_identical_misses_submit_at_most_one_response(self):
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        calls = {"count": 0, "response": 0}

        def concurrent_opener(request, timeout):
            del timeout
            if request.full_url.endswith("/responses/input_tokens"):
                with lock:
                    calls["count"] += 1
                barrier.wait(timeout=5)
                return FakeResponse(count_response())
            if request.full_url.endswith("/responses"):
                with lock:
                    calls["response"] += 1
                return FakeResponse(response_items(valid_items(self.records)))
            raise AssertionError(f"unexpected endpoint: {request.full_url}")

        first = self.make_selector(concurrent_opener)
        second = self.make_selector(concurrent_opener)

        def invoke(service):
            try:
                return service.select(self.records)
            except Exception as error:  # Return it for assertions in this thread.
                return error

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = tuple(executor.map(invoke, (first, second)))

        self.assertTrue(any(isinstance(value, dict) for value in outcomes))
        self.assertTrue(all(
            isinstance(value, (dict, selector.ReservationExistsError))
            for value in outcomes
        ))
        self.assertEqual({"count": 2, "response": 1}, calls)
        self.assertEqual(
            [("2026-08-25", 87, 31, "completed", "resp_test")],
            self.ledger_rows(),
        )

    def test_concurrent_different_requests_cannot_cross_daily_budget(self):
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        calls = {"count": 0, "response": 0}

        def concurrent_opener(request, timeout):
            del timeout
            if request.full_url.endswith("/responses/input_tokens"):
                with lock:
                    calls["count"] += 1
                barrier.wait(timeout=5)
                return FakeResponse(count_response(30))
            if request.full_url.endswith("/responses"):
                with lock:
                    calls["response"] += 1
                return FakeResponse(response_items(
                    valid_items(self.records), input_tokens=30, total_tokens=50
                ))
            raise AssertionError(f"unexpected endpoint: {request.full_url}")

        changed = (
            self.records[0],
            selector.SourceRecord(
                "beta", "乙", self.records[1].source + "追記。", 203,
                self.records[1].draft,
            ),
        )
        first = self.make_selector(
            concurrent_opener,
            daily_token_budget=100,
            max_output_tokens=30,
        )
        second = self.make_selector(
            concurrent_opener,
            daily_token_budget=100,
            max_output_tokens=30,
        )

        def invoke(service, records):
            try:
                return service.select(records)
            except Exception as error:  # Return it for assertions in this thread.
                return error

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(invoke, first, self.records),
                executor.submit(invoke, second, changed),
            )
            outcomes = tuple(future.result() for future in futures)

        self.assertEqual(1, sum(isinstance(value, dict) for value in outcomes))
        self.assertEqual(
            1,
            sum(isinstance(value, selector.DailyBudgetExceeded)
                for value in outcomes),
        )
        self.assertEqual({"count": 2, "response": 1}, calls)
        self.assertEqual(1, len(self.ledger_rows()))
        self.assertEqual(50, self.ledger_rows()[0][2])

    def test_utc_rollover_allows_a_new_reservation_but_keeps_old_row(self):
        clock = MutableClock(self.NOW)
        opener = QueueOpener(
            count_response(20),
            urllib.error.URLError("unknown outcome"),
            count_response(20),
            response_items(valid_items(self.records), input_tokens=20,
                           total_tokens=24,
                           response_id="resp_next_day"),
        )
        service = selector.SourceSelector(
            api_key="sk-test-secret",
            db_path=self.root / "state.sqlite3",
            daily_token_budget=100,
            max_output_tokens=30,
            attestation="2026-08-31",
            opener=opener,
            clock=clock,
        )
        with self.assertRaises(selector.APIError):
            service.select(self.records)
        clock.value += timedelta(days=1)

        result = service.select(self.records)

        self.assertEqual(set(("alpha", "beta")), set(result))
        self.assertEqual(
            [
                ("2026-08-25", 50, None, "pending", None),
                ("2026-08-26", 50, 24, "completed", "resp_next_day"),
            ],
            self.ledger_rows(),
        )

    def test_count_crossing_utc_midnight_reserves_on_submission_day(self):
        before_midnight = datetime(2026, 8, 25, 23, 59, 59, tzinfo=timezone.utc)
        after_midnight = before_midnight + timedelta(seconds=2)
        clock = mock.Mock(
            side_effect=(before_midnight, after_midnight, after_midnight)
        )
        opener = QueueOpener(
            count_response(20),
            response_items(
                valid_items(self.records), input_tokens=20, total_tokens=24
            ),
        )
        service = selector.SourceSelector(
            api_key="sk-test-secret",
            db_path=self.root / "state.sqlite3",
            daily_token_budget=100,
            max_output_tokens=30,
            attestation="2026-08-31",
            opener=opener,
            clock=clock,
        )

        service.select(self.records)

        self.assertEqual(
            [("2026-08-26", 50, 24, "completed", "resp_test")],
            self.ledger_rows(),
        )

    def test_response_crossing_utc_midnight_is_charged_on_both_days(self):
        before_midnight = datetime(2026, 8, 25, 23, 59, 59, tzinfo=timezone.utc)
        after_midnight = before_midnight + timedelta(seconds=2)
        clock = mock.Mock(
            side_effect=(before_midnight, before_midnight, after_midnight)
        )
        opener = QueueOpener(
            count_response(20),
            response_items(
                valid_items(self.records), input_tokens=20, total_tokens=24
            ),
        )
        service = selector.SourceSelector(
            api_key="sk-test-secret",
            db_path=self.root / "state.sqlite3",
            daily_token_budget=100,
            max_output_tokens=30,
            attestation="2026-08-31",
            opener=opener,
            clock=clock,
        )

        service.select(self.records)

        self.assertEqual(
            [("2026-08-25", 50, 24, "completed", "resp_test")],
            self.ledger_rows(),
        )
        self.assertEqual(
            [("2026-08-26", 24, "resp_test")],
            self.cross_day_rows(),
        )

        changed = (
            self.records[0],
            selector.SourceRecord(
                "beta", "乙", self.records[1].source + "追記。", 203,
                self.records[1].draft,
            ),
        )
        next_opener = QueueOpener(count_response(10))
        next_service = selector.SourceSelector(
            api_key="sk-test-secret",
            db_path=self.root / "state.sqlite3",
            daily_token_budget=50,
            max_output_tokens=20,
            attestation="2026-08-31",
            opener=next_opener,
            clock=lambda: after_midnight,
        )
        with self.assertRaises(selector.DailyBudgetExceeded) as raised:
            next_service.select(changed)
        self.assertEqual(24, raised.exception.used)
        self.assertEqual(30, raised.exception.requested)
        self.assertEqual(1, len(next_opener.calls))

    def test_completed_requests_use_actual_not_reserved_tokens_in_daily_sum(self):
        first_opener = QueueOpener(
            count_response(20),
            response_items(valid_items(self.records), input_tokens=20,
                           total_tokens=25,
                           response_id="resp_first"),
        )
        first = self.make_selector(
            first_opener, daily_token_budget=100, max_output_tokens=30
        )
        first.select(self.records)

        changed = (
            self.records[0],
            selector.SourceRecord(
                "beta", "乙", self.records[1].source + "追記。", 203,
                self.records[1].draft,
            ),
        )
        second_items = valid_items(changed)
        second_opener = QueueOpener(
            count_response(44),
            response_items(second_items, input_tokens=44, total_tokens=49,
                           response_id="resp_second"),
        )
        second = self.make_selector(
            second_opener, daily_token_budget=100, max_output_tokens=30
        )

        second.select(changed)

        # 25 actual + (44 input + 30 max output) = 99, so this is allowed.
        self.assertEqual(2, len(self.ledger_rows()))

    def test_response_usage_above_reservation_is_charged_and_blocks_next_request(self):
        opener = QueueOpener(
            count_response(10),
            response_items(valid_items(self.records), input_tokens=10,
                           total_tokens=31),
        )
        service = self.make_selector(
            opener,
            daily_token_budget=60,
            max_output_tokens=20,
        )

        with self.assertRaises(selector.LedgerError):
            service.select(self.records)

        self.assertEqual(
            [("2026-08-25", 30, 31, "completed", "resp_test")],
            self.ledger_rows(),
        )
        changed = (
            self.records[0],
            selector.SourceRecord(
                "beta", "乙", self.records[1].source + "追記。", 203,
                self.records[1].draft,
            ),
        )
        next_opener = QueueOpener(count_response(10))
        next_service = self.make_selector(
            next_opener,
            daily_token_budget=60,
            max_output_tokens=20,
        )
        with self.assertRaises(selector.DailyBudgetExceeded) as raised:
            next_service.select(changed)
        self.assertEqual(31, raised.exception.used)
        self.assertEqual(30, raised.exception.requested)
        self.assertEqual(1, len(next_opener.calls))

    def test_invalid_response_is_charged_at_actual_usage_but_not_cached(self):
        response = response_items(
            valid_items(self.records), input_tokens=20, total_tokens=29
        )
        response["status"] = "incomplete"
        opener = QueueOpener(count_response(20), response)
        service = self.make_selector(opener, max_output_tokens=30)

        with self.assertRaises(selector.ResponseValidationError):
            service.select(self.records)

        self.assertEqual(
            [("2026-08-25", 50, 29, "completed", "resp_test")],
            self.ledger_rows(),
        )
        with sqlite3.connect(self.root / "state.sqlite3") as connection:
            cached = connection.execute("SELECT COUNT(*) FROM response_cache").fetchone()[0]
        self.assertEqual(0, cached)

    def test_response_object_model_and_tier_are_checked_after_usage_settlement(self):
        cases = []
        wrong_object = response_items(valid_items(self.records))
        wrong_object["object"] = "not-a-response"
        cases.append(("object", wrong_object))
        cases.append((
            "model",
            response_items(valid_items(self.records), model="gpt-5.6-luna"),
        ))
        cases.append((
            "tier",
            response_items(valid_items(self.records), service_tier="priority"),
        ))
        for suffix, response in cases:
            with self.subTest(case=suffix):
                opener = QueueOpener(count_response(23), response)
                service = self.make_selector(
                    opener,
                    db_name=f"wrapper-{suffix}.sqlite3",
                )

                with self.assertRaises(selector.ResponseValidationError):
                    service.select(self.records)

                self.assertEqual(
                    [("2026-08-25", 87, 31, "completed", "resp_test")],
                    self.ledger_rows(f"wrapper-{suffix}.sqlite3"),
                )
                with sqlite3.connect(
                    self.root / f"wrapper-{suffix}.sqlite3"
                ) as connection:
                    cached = connection.execute(
                        "SELECT COUNT(*) FROM response_cache"
                    ).fetchone()[0]
                self.assertEqual(0, cached)

    def test_dated_terra_snapshot_response_is_accepted(self):
        opener = QueueOpener(
            count_response(),
            response_items(
                valid_items(self.records),
                model="gpt-5.6-terra-2026-08-25",
            ),
        )
        service = self.make_selector(opener)

        result = service.select(self.records)

        self.assertEqual(set(("alpha", "beta")), set(result))

    def test_response_usage_must_match_exact_preflight_count_and_sum(self):
        mismatched_input = response_items(
            valid_items(self.records), input_tokens=19, total_tokens=24
        )
        inconsistent_sum = response_items(
            valid_items(self.records), input_tokens=20, total_tokens=25
        )
        inconsistent_sum["usage"]["output_tokens"] = 4
        for suffix, response in (
            ("input", mismatched_input),
            ("sum", inconsistent_sum),
        ):
            with self.subTest(case=suffix):
                opener = QueueOpener(count_response(20), response)
                service = self.make_selector(
                    opener,
                    db_name=f"usage-{suffix}.sqlite3",
                    max_output_tokens=30,
                )

                with self.assertRaises(selector.LedgerError):
                    service.select(self.records)

                self.assertEqual(
                    [("2026-08-25", 50, None, "pending", None)],
                    self.ledger_rows(f"usage-{suffix}.sqlite3"),
                )

    def assert_rejected_items(self, items, suffix):
        opener = QueueOpener(count_response(), response_items(items))
        service = self.make_selector(opener, db_name=f"invalid-{suffix}.sqlite3")
        with self.assertRaises(selector.ResponseValidationError):
            service.select(self.records)
        self.assertEqual(2, len(opener.calls))

    def test_duplicate_missing_and_extra_output_keys_are_rejected(self):
        valid = valid_items(self.records)
        duplicate = [valid[0], dict(valid[0])]
        missing = [valid[0]]
        extra = [valid[0], {
            "key": "gamma",
            "action": "abstain",
            "excerpt": "",
            "reason_code": "no_supported_excerpt",
        }]
        for suffix, items in (
            ("duplicate", duplicate),
            ("missing", missing),
            ("extra", extra),
        ):
            with self.subTest(case=suffix):
                self.assert_rejected_items(items, suffix)

    def test_invalid_excerpt_is_downgraded_without_losing_valid_batch_items(self):
        valid = valid_items(self.records)
        valid[0] = dict(valid[0], excerpt=self.records[1].source)
        self.assertNotIn(valid[0]["excerpt"], self.records[0].source)
        opener = QueueOpener(count_response(), response_items(valid))
        service = self.make_selector(opener, db_name="mixed-excerpts.sqlite3")

        result = service.select(self.records)

        self.assertEqual(
            selector.Selection("abstain", "", "no_supported_excerpt"),
            result["alpha"],
        )
        self.assertEqual("select", result["beta"].action)
        self.assertEqual(self.records[1].source, result["beta"].excerpt)
        self.assertEqual(
            [("2026-08-25", 87, 31, "completed", "resp_test")],
            self.ledger_rows("mixed-excerpts.sqlite3"),
        )
        with sqlite3.connect(self.root / "mixed-excerpts.sqlite3") as connection:
            cached = connection.execute(
                "SELECT COUNT(*) FROM response_cache"
            ).fetchone()[0]
        self.assertEqual(1, cached)

        no_network = QueueOpener()
        cached_service = selector.SourceSelector(
            db_path=self.root / "mixed-excerpts.sqlite3",
            opener=no_network,
            clock=lambda: self.NOW,
            max_output_tokens=64,
        )
        cached_result = cached_service.select(self.records, cache_only=True)
        self.assertEqual(result, cached_result)
        self.assertEqual([], no_network.calls)
        self.assertEqual(1, len(self.ledger_rows("mixed-excerpts.sqlite3")))

    def test_complete_one_or_more_sentence_boundaries_are_accepted(self):
        source = "彼は大会で受賞。\nその後、驚いた！？第三文？"
        record = selector.SourceRecord(
            "sentences", "人物", source, "1", "既存説明。"
        )
        excerpts = (
            "彼は大会で受賞。",
            "その後、驚いた！？",
            "第三文？",
            source,
        )
        for index, excerpt in enumerate(excerpts):
            with self.subTest(excerpt=excerpt):
                items = [{
                    "key": record.key,
                    "action": "select",
                    "excerpt": excerpt,
                    "reason_code": "source_excerpt_preferred",
                }]
                opener = QueueOpener(count_response(), response_items(items))
                service = self.make_selector(
                    opener,
                    db_name=f"complete-sentence-{index}.sqlite3",
                )

                result = service.select((record,))

                self.assertEqual(excerpt, result[record.key].excerpt)

    def test_partial_sentence_response_is_downgraded_charged_and_cached(self):
        source = "彼は大会で受賞。\nその後、驚いた！？第三文？"
        record = selector.SourceRecord(
            "sentences", "人物", source, "1", "既存説明。"
        )
        fragments = (
            "",                      # Empty select is not an extractive sentence.
            "受賞。",                 # Starts inside a sentence.
            "彼は大会で受賞",         # Does not include terminal punctuation.
            "その後、驚いた！",       # Splits the consecutive !? sequence.
        )
        for index, excerpt in enumerate(fragments):
            with self.subTest(excerpt=excerpt):
                items = [{
                    "key": record.key,
                    "action": "select",
                    "excerpt": excerpt,
                    "reason_code": "source_excerpt_preferred",
                }]
                opener = QueueOpener(count_response(), response_items(items))
                db_name = f"partial-sentence-{index}.sqlite3"
                service = self.make_selector(opener, db_name=db_name)

                result = service.select((record,))

                self.assertEqual(
                    selector.Selection("abstain", "", "no_supported_excerpt"),
                    result[record.key],
                )
                self.assertEqual(
                    [("2026-08-25", 87, 31, "completed", "resp_test")],
                    self.ledger_rows(db_name),
                )
                with sqlite3.connect(self.root / db_name) as connection:
                    cached = connection.execute(
                        "SELECT COUNT(*) FROM response_cache"
                    ).fetchone()[0]
                self.assertEqual(1, cached)

                no_network = QueueOpener()
                cached_service = selector.SourceSelector(
                    db_path=self.root / db_name,
                    opener=no_network,
                    clock=lambda: self.NOW,
                    max_output_tokens=64,
                )
                cached_result = cached_service.select((record,), cache_only=True)
                self.assertEqual(result, cached_result)
                self.assertEqual([], no_network.calls)
                self.assertEqual(1, len(self.ledger_rows(db_name)))

    def test_action_excerpt_and_reason_combinations_are_enforced(self):
        cases = []
        valid = valid_items(self.records)
        cases.append(("abstain-text", [valid[0], {
            "key": "beta", "action": "abstain", "excerpt": "乙",
            "reason_code": "no_supported_excerpt",
        }]))
        cases.append(("reason-mismatch", [dict(
            valid[0], reason_code="source_excerpt_preferred"
        ), valid[1]]))
        empty_draft_records = (
            selector.SourceRecord("alpha", "甲", self.records[0].source, "101", ""),
            self.records[1],
        )
        empty_keep = valid_items(empty_draft_records)
        empty_keep[0] = {
            "key": "alpha",
            "action": "keep",
            "excerpt": empty_draft_records[0].source,
            "reason_code": "draft_supported",
        }
        opener = QueueOpener(count_response(), response_items(empty_keep))
        service = self.make_selector(opener, db_name="invalid-empty-draft.sqlite3")
        with self.assertRaises(selector.ResponseValidationError):
            service.select(empty_draft_records)

        for suffix, items in cases:
            with self.subTest(case=suffix):
                self.assert_rejected_items(items, suffix)

    def test_refusal_and_multiple_output_text_are_rejected(self):
        refusal = response_items(valid_items(self.records))
        refusal["output"][0]["content"] = [
            {"type": "refusal", "refusal": "cannot comply"}
        ]
        opener = QueueOpener(count_response(), refusal)
        service = self.make_selector(opener, db_name="refusal.sqlite3")
        with self.assertRaises(selector.ResponseValidationError):
            service.select(self.records)

        multiple = response_items(valid_items(self.records))
        multiple["output"][0]["content"].append(
            {"type": "output_text", "text": "{}"}
        )
        opener = QueueOpener(count_response(), multiple)
        service = self.make_selector(opener, db_name="multiple.sqlite3")
        with self.assertRaises(selector.ResponseValidationError):
            service.select(self.records)

        unexpected = response_items(valid_items(self.records))
        unexpected["output"].insert(0, {"type": "web_search_call"})
        opener = QueueOpener(count_response(), unexpected)
        service = self.make_selector(opener, db_name="unexpected-output.sqlite3")
        with self.assertRaises(selector.ResponseValidationError):
            service.select(self.records)

    def test_invalid_input_token_count_never_creates_a_reservation(self):
        opener = QueueOpener({"object": "wrong", "input_tokens": 10})
        service = self.make_selector(opener)
        with self.assertRaises(selector.ResponseValidationError):
            service.select(self.records)
        self.assertEqual([], self.ledger_rows())
        self.assertEqual(1, len(opener.calls))

    def test_api_error_does_not_echo_secret_or_response_body(self):
        secret = "sk-super-secret"
        http_error = urllib.error.HTTPError(
            "https://api.openai.com/v1/responses/input_tokens",
            500,
            "server error",
            {},
            io.BytesIO(f"echoed {secret}".encode()),
        )
        opener = QueueOpener(http_error)
        service = selector.SourceSelector(
            api_key=secret,
            db_path=self.root / "state.sqlite3",
            attestation="2026-08-31",
            opener=opener,
            clock=lambda: self.NOW,
            max_output_tokens=64,
        )
        with self.assertRaises(selector.APIError) as raised:
            service.select(self.records)
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn("echoed", str(raised.exception))

    def test_corrupt_exact_cache_entry_fails_closed_without_network(self):
        opener = QueueOpener(
            count_response(), response_items(valid_items(self.records))
        )
        service = self.make_selector(opener)
        service.select(self.records)
        with sqlite3.connect(self.root / "state.sqlite3") as connection:
            connection.execute("UPDATE response_cache SET response_json = 'not-json'")

        no_network = QueueOpener()
        cached_service = selector.SourceSelector(
            db_path=self.root / "state.sqlite3",
            opener=no_network,
            clock=lambda: self.NOW,
            max_output_tokens=64,
        )
        with self.assertRaises(selector.CacheCorruptionError):
            cached_service.select(self.records, cache_only=True)
        self.assertEqual([], no_network.calls)

    def test_duplicate_record_keys_and_invalid_records_need_no_network(self):
        opener = QueueOpener()
        service = self.make_selector(opener)
        duplicate = (self.records[0], self.records[0])
        with self.assertRaises(selector.InputValidationError):
            service.select(duplicate)
        with self.assertRaises(selector.InputValidationError):
            service.select([object()])
        with self.assertRaises(selector.InputValidationError):
            service.select([
                selector.SourceRecord("empty", "題", "", "1", "")
            ])
        self.assertEqual([], opener.calls)

    def test_empty_record_set_is_a_network_free_noop(self):
        opener = QueueOpener()
        service = selector.SourceSelector(
            db_path=self.root / "state.sqlite3", opener=opener
        )
        self.assertEqual({}, service.select([], cache_only=False))
        self.assertEqual({}, service.select([], cache_only=True))
        self.assertEqual([], opener.calls)

    def test_model_is_fixed_and_naive_clock_is_rejected_before_network(self):
        with self.assertRaises(selector.ConfigurationError):
            selector.SourceSelector(
                db_path=self.root / "fixed.sqlite3", model="gpt-5.6-luna"
            )
        opener = QueueOpener()
        service = selector.SourceSelector(
            api_key="sk-test-secret",
            db_path=self.root / "clock.sqlite3",
            attestation="2026-08-31",
            opener=opener,
            clock=lambda: datetime(2026, 8, 25, 12, 0),
            max_output_tokens=64,
        )
        with self.assertRaises(selector.ConfigurationError):
            service.select(self.records)
        self.assertEqual([], opener.calls)


if __name__ == "__main__":
    unittest.main()
