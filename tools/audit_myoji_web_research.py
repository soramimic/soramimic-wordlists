#!/usr/bin/env python3
"""Validate a second, independent research log for previously unsupported surnames.

The program deliberately does not perform network searches.  Search workers write
the attempt receipts, and this tool makes incomplete/429 searches impossible to
label as negative evidence.
"""

import argparse
import csv
import hashlib
import json
import re
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from update_myoji import (
    OFFICIAL_SOURCE_TYPES,
    WEB_EVIDENCE_TIERS,
    WEB_IDENTITY_BASES,
    WEB_SOURCE_TYPES,
    clean_surname,
)
from wpnames import write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "myoji.csv"
RESEARCH_DIR = Path(__file__).resolve().parent / "myoji_web_research_batches"
EVIDENCE_PATH = Path(__file__).resolve().parent / "myoji_web_evidence.jsonl"
BASE_KEYS = (
    "batch_index",
    "surface",
    "pronunciation",
    "rank",
    "searched_on",
    "query",
    "status",
    "source_url",
    "source_type",
    "source_title",
    "observed_surface",
    "observed_reading",
    "locator",
    "notes",
)
EXTRA_KEYS = ("evidence_tier", "identity_basis", "search_attempts")
STRATEGIES = ("exact_katakana", "exact_hiragana", "broad_person")
STATUS = {"verified", "no_support_found", "ambiguous"}
SHA = re.compile(r"^[0-9a-f]{64}$")
URL = re.compile(r"^https://[^\s]+$")
KATA2HIRA = str.maketrans(
    {chr(c): chr(c - 0x60) for c in range(ord("ァ"), ord("ヶ") + 1)}
)
HIRA2KATA = str.maketrans(
    {chr(c): chr(c + 0x60) for c in range(ord("ぁ"), ord("ゖ") + 1)}
)
ENGINES = frozenset(
    (
        "bing",
        "duckduckgo",
        "duckduckgo_html",
        "google",
        "brave",
        "yahoo_japan",
        "openai_web_search",
    )
)
SOURCE_TYPES = OFFICIAL_SOURCE_TYPES | WEB_SOURCE_TYPES
TIER_A_TYPES = OFFICIAL_SOURCE_TYPES | frozenset(
    (
        "government_register",
        "school_profile",
        "university_profile",
        "sports_roster",
        "corporate_filing",
        "corporate_release",
        "professional_directory",
    )
)
TIER_B_TYPES = WEB_SOURCE_TYPES - TIER_A_TYPES
SEARCH_OR_REDIRECT_HOSTS = frozenset(
    (
        "bing.com",
        "www.bing.com",
        "storage.live.com",
        "google.com",
        "www.google.com",
        "duckduckgo.com",
        "html.duckduckgo.com",
        "search.yahoo.co.jp",
        "yahoo.co.jp",
        "www.yahoo.co.jp",
    )
)
# Surname dictionaries can be useful query leads, but they do not prove that a
# person with the surname/reading exists.  They must never be promoted as
# person evidence.
DISALLOWED_EVIDENCE_HOSTS = frozenset(
    (
        "name-power.net",
        "www.name-power.net",
        "myoji-yurai.net",
        "www.myoji-yurai.net",
        "myoji.namedic.jp",
        "japanese-names.info",
        "www.japanese-names.info",
        "myoji.jitenon.jp",
        "kanji.red",
        "name.sijisuru.com",
        "enamae.net",
        "tangorin.com",
        "kakijun.com",
        "kanji.reader.bz",
        "kanshudo.com",
        "myoujijiten.web.fc2.com",
        "namaenomori.com",
        "www.namaenomori.com",
    )
)
SECOND_PASS_EXCLUDED_SITES = (
    "name-power.net",
    "myoji-yurai.net",
    "myoji.jitenon.jp",
    "japanese-names.info",
    "myoji.namedic.jp",
    "name.sijisuru.com",
    "enamae.net",
    "tangorin.com",
)
BAD_URL_SUFFIXES = (")", "]", "}", "。", "、", "，", ",", ";")
MIN_BATCH_URL_COVERAGE = 0.05
EVIDENCE_REQUIRED = (
    "surface",
    "pronunciation",
    "status",
    "source_url",
    "source_type",
    "source_title",
    "observed_surface",
    "observed_reading",
    "locator",
    "identity_basis",
    "evidence_tier",
    "retrieved_on",
)


def _blocked_evidence_host(url):
    host = (
        urllib.parse.urlsplit(url).hostname.lower().rstrip(".")
        if urllib.parse.urlsplit(url).hostname
        else ""
    )
    return any(
        host == blocked or host.endswith("." + blocked)
        for blocked in DISALLOWED_EVIDENCE_HOSTS
    )


def validate_evidence_ledger(ledger_path=EVIDENCE_PATH, url_report=None):
    """Validate promoted evidence and, by default, its schema-v3 URL audit."""
    ledger_path = Path(ledger_path)
    rows = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    catalog = {(r["surface"], r["pronunciation"]) for r in _rows()}
    pairs = set()
    for number, row in enumerate(rows):
        missing = [
            key for key in EVIDENCE_REQUIRED if not str(row.get(key, "")).strip()
        ]
        if missing:
            raise RuntimeError(f"{ledger_path.name}:{number + 1}: missing {missing}")
        pair = (row["surface"], row["pronunciation"])
        if pair in pairs:
            raise RuntimeError(f"{ledger_path.name}:{number + 1}: duplicate pair")
        pairs.add(pair)
        if pair not in catalog:
            raise RuntimeError(
                f"{ledger_path.name}:{number + 1}: pair absent from myoji.csv"
            )
        if row["status"] != "verified":
            raise RuntimeError(
                f"{ledger_path.name}:{number + 1}: status is not verified"
            )
        if not URL.fullmatch(row["source_url"]):
            raise RuntimeError(f"{ledger_path.name}:{number + 1}: URL must be HTTPS")
        if _blocked_evidence_host(row["source_url"]):
            raise RuntimeError(
                f"{ledger_path.name}:{number + 1}: blocked surname dictionary"
            )
        if row["source_type"] not in SOURCE_TYPES:
            raise RuntimeError(f"{ledger_path.name}:{number + 1}: bad source type")
        if row["evidence_tier"] == "A" and row["source_type"] not in TIER_A_TYPES:
            raise RuntimeError(
                f"{ledger_path.name}:{number + 1}: source type/tier mismatch"
            )
        if row["evidence_tier"] == "B" and row["source_type"] not in TIER_B_TYPES:
            raise RuntimeError(
                f"{ledger_path.name}:{number + 1}: source type/tier mismatch"
            )
        observed = str(row["observed_reading"]).replace(" ", "")
        if observed != row["pronunciation"]:
            observed = observed.translate(HIRA2KATA)
        if (row["observed_surface"], observed) != pair:
            raise RuntimeError(
                f"{ledger_path.name}:{number + 1}: observed exact mismatch"
            )
    if url_report is not None:
        report_rows = [
            json.loads(line)
            for line in Path(url_report).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        passed = {}
        for number, audit in enumerate(report_rows):
            if audit.get("schema_version") != 3 or not audit.get("completed"):
                raise RuntimeError(
                    f"{Path(url_report).name}:{number + 1}: requires completed schema 3"
                )
            if audit.get("audit_result") != "pass":
                continue
            key = (
                audit.get("surface", ""),
                audit.get("pronunciation", ""),
                audit.get("source_url", ""),
            )
            if key in passed:
                raise RuntimeError(
                    f"{Path(url_report).name}:{number + 1}: duplicate pass"
                )
            passed[key] = audit
        for number, row in enumerate(rows):
            key = (row["surface"], row["pronunciation"], row["source_url"])
            if key not in passed:
                raise RuntimeError(
                    f"{ledger_path.name}:{number + 1}: no schema-3 URL audit pass"
                )
            if (
                str(row["locator"]).strip()
                != str(passed[key].get("match_context", "")).strip()
            ):
                raise RuntimeError(
                    f"{ledger_path.name}:{number + 1}: locator differs from URL audit context"
                )
    return len(rows)


def candidates_path(batch):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-[a-z0-9]+)?", batch):
        raise RuntimeError("invalid batch")
    return RESEARCH_DIR / f"{batch}-candidates.csv"


def controls_path(batch):
    return RESEARCH_DIR / f"{batch}-controls.csv"


def _rows():
    with CSV_PATH.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _new_pairs():
    pairs = set()
    for p in RESEARCH_DIR.glob("*.jsonl"):
        # Candidate exclusion is based only on reviewed result ledgers.  Raw
        # search excerpts may contain Unicode line separators and are not part
        # of the promotion schema.
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-[a-z0-9]+)?-[a-z]\.jsonl", p.name):
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                x = json.loads(line)
                pairs.add((x["surface"], x["pronunciation"]))
            except (ValueError, KeyError) as e:
                raise RuntimeError(f"{p.name}:{n}: invalid research log") from e
    return pairs


def prepare(batch, limit=None):
    out = candidates_path(batch)
    if out.exists():
        raise RuntimeError(f"snapshot exists: {out}")
    excluded = _new_pairs()
    rows = [
        r
        for r in _rows()
        if r["verified"] == "no" and (r["surface"], r["pronunciation"]) not in excluded
    ]
    rows.sort(
        key=lambda r: (
            int(r["rank"]) if r["rank"] else 10**9,
            int(r["id"]),
            r["pronunciation"],
        )
    )
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        raise RuntimeError("no candidates")
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    output = []
    for i, row in enumerate(rows):
        hira = row["pronunciation"].translate(KATA2HIRA)
        output.append(
            {
                "batch_index": i,
                "id": row["id"],
                "surface": row["surface"],
                "pronunciation": row["pronunciation"],
                "rank": row["rank"],
                "query": f"{row['surface']} {hira} 氏名",
            }
        )
    write_csv_no_trailing_newline(
        out,
        ("batch_index", "id", "surface", "pronunciation", "rank", "query"),
        output,
    )
    print(f"prepared {len(rows)} candidates: {out}")


def load_candidates(batch):
    p = candidates_path(batch)
    with p.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if [int(r["batch_index"]) for r in rows] != list(range(len(rows))):
        raise RuntimeError("candidate indices not contiguous")
    return {int(r["batch_index"]): r for r in rows}


def _parse_date(value, where):
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as exc:
        raise RuntimeError(f"{where}: bad date") from exc
    if parsed > datetime.now(ZoneInfo("Asia/Tokyo")).date():
        raise RuntimeError(f"{where}: future date")


def receipt_sha256(attempt):
    """検索receiptの改変検知用SHA-256を返す。"""
    payload = {
        key: attempt[key]
        for key in (
            "strategy",
            "engine",
            "query",
            "http_status",
            "result_count",
            "result_urls",
        )
    }
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _attempt(a, candidate, where):
    required = {
        "strategy",
        "engine",
        "query",
        "completed_at",
        "http_status",
        "result_count",
        "response_sha256",
        "result_urls",
    }
    if not required <= set(a):
        raise RuntimeError(f"{where}: attempt keys missing")
    if a["strategy"] not in STRATEGIES or a["engine"] not in ENGINES:
        raise RuntimeError(f"{where}: bad attempt identity")
    query = str(a["query"]).strip()
    surface = candidate["surface"]
    kata = candidate["pronunciation"]
    hira = kata.translate(KATA2HIRA)
    if not query or surface not in query:
        raise RuntimeError(f"{where}: attempt query lacks surface")
    if a["strategy"] == "exact_katakana" and kata not in query:
        raise RuntimeError(f"{where}: katakana strategy lacks reading")
    if a["strategy"] == "exact_hiragana" and hira not in query:
        raise RuntimeError(f"{where}: hiragana strategy lacks reading")
    if a["strategy"] == "broad_person" and not any(
        word in query for word in ("氏名", "人物", "選手", "名簿", "プロフィール")
    ):
        raise RuntimeError(f"{where}: broad strategy lacks person term")
    try:
        completed = datetime.fromisoformat(str(a["completed_at"]))
    except ValueError as exc:
        raise RuntimeError(f"{where}: bad completed_at") from exc
    if completed.tzinfo is None:
        raise RuntimeError(f"{where}: completed_at lacks timezone")
    try:
        status, count = int(a["http_status"]), int(a["result_count"])
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"{where}: bad HTTP/count") from e
    digest = str(a["response_sha256"])
    if (
        status < 100
        or status > 599
        or count < 0
        or not SHA.fullmatch(digest)
        or len(set(digest)) == 1
        or digest != receipt_sha256(a)
    ):
        raise RuntimeError(f"{where}: incomplete/tampered attempt")
    if not isinstance(a["result_urls"], list) or any(
        not URL.fullmatch(str(u)) or str(u).endswith(BAD_URL_SUFFIXES)
        for u in a["result_urls"]
    ):
        raise RuntimeError(f"{where}: bad result URLs")
    if count != len(a["result_urls"]):
        raise RuntimeError(f"{where}: result count/URLs mismatch")
    if any(
        urllib.parse.urlsplit(url).netloc.lower() in SEARCH_OR_REDIRECT_HOSTS
        for url in a["result_urls"]
    ):
        raise RuntimeError(f"{where}: search/redirect URL is not a target page")
    if count > 0 and not any(
        urllib.parse.urlsplit(url).path not in ("", "/")
        or bool(urllib.parse.urlsplit(url).query)
        for url in a["result_urls"]
    ):
        raise RuntimeError(f"{where}: result URLs lack target paths")
    if status != 200 and (count or a["result_urls"]):
        raise RuntimeError(f"{where}: failed attempt contains results")
    return status == 200


def load_results(batch, paths=None):
    cand = load_candidates(batch)
    paths = paths or sorted(RESEARCH_DIR.glob(f"{batch}-[a-z].jsonl"))
    seen = set()
    out = []
    for p in paths:
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            where = f"{p.name}:{n}"
            x = json.loads(line)
            missing = set(BASE_KEYS + EXTRA_KEYS) - set(x)
            if missing:
                raise RuntimeError(f"{where}: missing {sorted(missing)}")
            i = int(x["batch_index"])
            if i in seen or i not in cand:
                raise RuntimeError(f"{where}: duplicate/out-of-range index")
            seen.add(i)
            c = cand[i]
            for k in ("surface", "pronunciation", "rank", "query"):
                if str(x[k]) != c[k]:
                    raise RuntimeError(f"{where}: candidate mismatch {k}")
            if x["status"] not in STATUS:
                raise RuntimeError(f"{where}: bad status")
            if not isinstance(x["search_attempts"], list):
                raise TypeError(f"{where}: attempts not list")
            _parse_date(x["searched_on"], where)
            successful = [a for a in x["search_attempts"] if _attempt(a, c, where)]
            if "-s2" in batch:
                for attempt in x["search_attempts"]:
                    missing_exclusions = [
                        host
                        for host in SECOND_PASS_EXCLUDED_SITES
                        if f"-site:{host}" not in attempt["query"]
                    ]
                    if missing_exclusions:
                        raise RuntimeError(
                            f"{where}: second-pass query lacks dictionary exclusions"
                        )
            if x["status"] in (
                "no_support_found",
                "ambiguous",
            ) and {a["strategy"] for a in successful} != set(STRATEGIES):
                raise RuntimeError(
                    f"{where}: unresolved result lacks all 3 search strategies"
                )
            fields = (
                "source_url",
                "source_type",
                "source_title",
                "observed_surface",
                "observed_reading",
                "locator",
            )
            if x["status"] == "verified":
                if (
                    x["evidence_tier"] not in WEB_EVIDENCE_TIERS
                    or x["identity_basis"] not in WEB_IDENTITY_BASES
                ):
                    raise RuntimeError(f"{where}: bad evidence tier/identity")
                if not all(str(x[k]).strip() for k in fields) or not URL.fullmatch(
                    x["source_url"]
                ):
                    raise RuntimeError(f"{where}: incomplete verified evidence")
                if x["source_type"] not in SOURCE_TYPES:
                    raise RuntimeError(f"{where}: bad source type")
                if (
                    urllib.parse.urlsplit(x["source_url"]).netloc.lower()
                    in DISALLOWED_EVIDENCE_HOSTS
                ):
                    raise RuntimeError(
                        f"{where}: surname dictionary is not person evidence"
                    )
                if (
                    x["evidence_tier"] == "A" and x["source_type"] not in TIER_A_TYPES
                ) or (
                    x["evidence_tier"] == "B" and x["source_type"] not in TIER_B_TYPES
                ):
                    raise RuntimeError(f"{where}: source type/tier mismatch")
                reading = (
                    str(x["observed_reading"]).replace(" ", "").translate(HIRA2KATA)
                )
                expected = (c["surface"], c["pronunciation"])
                if (x["observed_surface"], reading) != expected or not clean_surname(
                    *expected
                ):
                    raise RuntimeError(f"{where}: exact identity mismatch")
                if not successful:
                    raise RuntimeError(f"{where}: verified has no successful attempts")
            elif any(
                str(x[k]).strip() for k in fields + ("evidence_tier", "identity_basis")
            ):
                raise RuntimeError(f"{where}: nonverified evidence fields nonempty")
            out.append(x)
    if seen != set(cand):
        raise RuntimeError(f"incomplete results: {len(set(cand) - seen)} missing")
    control_file = controls_path(batch)
    if control_file.exists():
        with control_file.open(encoding="utf-8") as stream:
            controls = list(csv.DictReader(stream))
        by_pair = {(row["surface"], row["pronunciation"]): row for row in out}
        for control in controls:
            pair = (control["surface"], control["pronunciation"])
            if pair not in by_pair or by_pair[pair]["status"] != control["status"]:
                raise RuntimeError(
                    f"known control failed: {pair[0]} / {pair[1]} "
                    f"must be {control['status']}"
                )
    if len(out) >= 20:
        with_urls = sum(
            any(
                int(attempt["http_status"]) == 200 and attempt["result_urls"]
                for attempt in row["search_attempts"]
            )
            for row in out
        )
        if with_urls / len(out) < MIN_BATCH_URL_COVERAGE:
            raise RuntimeError(
                "batch has implausibly few returned target URLs; "
                "empty search responses are not completed research"
            )
    return sorted(out, key=lambda x: int(x["batch_index"]))


def validate(batch, all_batches=False):
    batches = (
        [
            p.name.removesuffix("-candidates.csv")
            for p in RESEARCH_DIR.glob("*-candidates.csv")
        ]
        if all_batches
        else [batch]
    )
    for b in sorted(batches):
        rows = load_results(b)
        print(b, len(rows), {s: sum(x["status"] == s for x in rows) for s in STATUS})


def _evidence_record(result):
    record = {
        k: result[k]
        for k in (
            "surface",
            "pronunciation",
            "status",
            "source_url",
            "source_type",
            "source_title",
            "observed_surface",
            "observed_reading",
            "locator",
            "identity_basis",
            "evidence_tier",
        )
    }
    record["retrieved_on"] = result["searched_on"]
    return record


def promote(batch, replace_existing=False):
    rows = load_results(batch)
    EVIDENCE_PATH.parent.mkdir(exist_ok=True)
    existing = (
        EVIDENCE_PATH.read_text(encoding="utf-8").splitlines()
        if EVIDENCE_PATH.exists()
        else []
    )
    if replace_existing:
        parsed_existing = []
        existing_pairs = set()
        for number, line in enumerate(existing, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"{EVIDENCE_PATH.name}:{number}: invalid JSON"
                ) from exc
            if not record.get("surface") or not record.get("pronunciation"):
                raise RuntimeError(f"{EVIDENCE_PATH.name}:{number}: missing pair key")
            pair = (record["surface"], record["pronunciation"])
            if pair in existing_pairs:
                raise RuntimeError(f"{EVIDENCE_PATH.name}:{number}: duplicate pair")
            existing_pairs.add(pair)
            parsed_existing.append((line, pair))
        authoritative = {(x["surface"], x["pronunciation"]) for x in rows}
        kept = [line for line, pair in parsed_existing if pair not in authoritative]
        removed = len(parsed_existing) - len(kept)
        add = [
            json.dumps(_evidence_record(x), ensure_ascii=False, separators=(",", ":"))
            for x in rows
            if x["status"] == "verified"
        ]
        if kept or add:
            EVIDENCE_PATH.write_text("\n".join(kept + add) + "\n", encoding="utf-8")
        print(f"promoted {len(add)} removed={removed} added={len(add)}")
        return
    pairs = {
        (json.loads(x)["surface"], json.loads(x)["pronunciation"])
        for x in existing
        if x.strip()
    }
    add = []
    for x in rows:
        pair = (x["surface"], x["pronunciation"])
        if x["status"] == "verified" and pair not in pairs:
            record = _evidence_record(x)
            add.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            pairs.add(pair)
    if add:
        EVIDENCE_PATH.write_text("\n".join(existing + add) + "\n", encoding="utf-8")
    print(f"promoted {len(add)}")


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("prepare")
    q.add_argument("--batch", required=True)
    q.add_argument("--limit", type=int)
    q = s.add_parser("validate")
    q.add_argument("--batch", required=True)
    q.add_argument("--all", action="store_true")
    q = s.add_parser("validate-all")
    q = s.add_parser("validate-evidence")
    q.add_argument("--ledger", type=Path, default=EVIDENCE_PATH)
    q.add_argument(
        "--url-report",
        type=Path,
        default=Path(__file__).resolve().parent / "myoji_web_evidence_url_audit.jsonl",
    )
    q.add_argument("--no-url-audit", action="store_true")
    q = s.add_parser("promote")
    q.add_argument("--batch", required=True)
    q.add_argument(
        "--replace-existing",
        action="store_true",
        help="replace all ledger rows in this batch's authoritative scope",
    )
    a = p.parse_args()
    if a.cmd == "prepare":
        prepare(a.batch, a.limit)
    elif a.cmd == "validate":
        validate(a.batch, a.all)
    elif a.cmd == "validate-all":
        validate("", True)
    elif a.cmd == "validate-evidence":
        count = validate_evidence_ledger(
            a.ledger, None if a.no_url_audit else a.url_report
        )
        print(f"evidence ledger valid: {count}")
    else:
        promote(a.batch, a.replace_existing)


if __name__ == "__main__":
    main()
