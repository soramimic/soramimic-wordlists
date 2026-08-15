#!/usr/bin/env python3
"""Resumable candidate-isolated Yahoo! JAPAN surname search runner.

Each candidate is searched with the three strategies required by
``audit_myoji_web_research.py``.  The runner records receipts and deliberately
leaves the result ``ambiguous``: deciding that a returned page proves a real
person's surname/reading is a separate review and URL-body audit step.
"""

import argparse
import csv
import hashlib
import html
import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote_plus, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

STRATEGIES = ("exact_katakana", "exact_hiragana", "broad_person")
ENDPOINT = "https://search.yahoo.co.jp/search?p="
JST = ZoneInfo("Asia/Tokyo")
KATA2HIRA = str.maketrans(
    {chr(c): chr(c - 0x60) for c in range(ord("ァ"), ord("ヶ") + 1)}
)


class _YahooResults(HTMLParser):
    """Extract the first result link and visible text from each result ``li``."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.href = None
        self.text = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            if self.depth == 0:
                self.href, self.text = None, []
            self.depth += 1
        elif self.depth and tag == "a" and self.href is None:
            self.href = dict(attrs).get("href")

    def handle_data(self, data):
        if self.depth:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag != "li" or not self.depth:
            return
        self.depth -= 1
        if self.depth == 0 and self.href:
            self.rows.append((html.unescape(self.href), " ".join(self.text).strip()))


def _target_url(url):
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    if host.endswith((".yahoo.co.jp", ".yimg.jp")):
        return None
    return url


def fetch(query, timeout=20, opener=urlopen):
    req = Request(
        ENDPOINT + quote_plus(query) + "&n=10",
        headers={"User-Agent": "Mozilla/5.0 (compatible; surname-research/1.0)"},
    )
    with opener(req, timeout=timeout) as response:
        status = int(response.status)
        body = response.read()
    parser = _YahooResults()
    parser.feed(body.decode("utf-8", "replace"))
    urls, snippets = [], []
    for href, snippet in parser.rows:
        url = _target_url(href)
        if url and url not in urls:
            urls.append(url)
            snippets.append(snippet)
    return status, urls[:10], snippets[:10], body


def receipt_sha256(attempt):
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
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _query(candidate, strategy):
    surface, kata = candidate["surface"], candidate["pronunciation"]
    hira = kata.translate(KATA2HIRA)
    if strategy == "exact_katakana":
        return f'"{surface}" "{kata}" 氏名'
    if strategy == "exact_hiragana":
        return f'"{surface}" "{hira}" 氏名'
    return f'"{surface}" "{kata}" 人物'


def _attempt(candidate, strategy, delay, timeout):
    query = _query(candidate, strategy)
    if delay:
        time.sleep(delay)
    now = datetime.now(JST)
    result = {
        "strategy": strategy,
        "engine": "yahoo_japan",
        "query": query,
        "completed_at": now.isoformat(timespec="seconds"),
    }
    try:
        status, urls, snippets, body = fetch(query, timeout=timeout)
        result.update(
            http_status=status,
            result_count=len(urls),
            result_urls=urls,
            result_snippets=snippets,
            response_body_sha256=hashlib.sha256(body).hexdigest(),
        )
    except HTTPError as exc:
        result.update(
            http_status=int(exc.code),
            result_count=0,
            result_urls=[],
            result_snippets=[],
            error=f"HTTPError: {exc}",
        )
    except Exception as exc:
        result.update(
            http_status=599,
            result_count=0,
            result_urls=[],
            result_snippets=[],
            error=f"{type(exc).__name__}: {exc}",
        )
    result["response_sha256"] = receipt_sha256(result)
    return result


def _load_candidates(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    for index, row in enumerate(rows):
        row.setdefault("batch_index", str(index))
        row.setdefault("rank", "")
        if not row.get("surface") or not row.get("pronunciation"):
            raise ValueError(f"row {index}: surface/pronunciation required")
    return rows


def _load_checkpoint(path):
    if not path.exists():
        return {}
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[int(row["batch_index"])] = row
    return rows


def _complete(row):
    attempts = row.get("search_attempts", [])
    return {attempt.get("strategy") for attempt in attempts} == set(STRATEGIES) and all(
        attempt.get("http_status") == 200 for attempt in attempts
    )


def _save_checkpoint(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            for index in sorted(rows):
                stream.write(
                    json.dumps(rows[index], ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _research(candidate, delay, timeout, existing=None):
    kept = {
        attempt.get("strategy"): attempt
        for attempt in (existing or {}).get("search_attempts", [])
        if attempt.get("strategy") in STRATEGIES and attempt.get("http_status") == 200
    }
    attempts = []
    for strategy in STRATEGIES:
        attempt = kept.get(strategy) or _attempt(candidate, strategy, delay, timeout)
        attempts.append(attempt)
        if attempt.get("http_status") != 200:
            break
    row = {
        "batch_index": int(candidate["batch_index"]),
        "surface": candidate["surface"],
        "pronunciation": candidate["pronunciation"],
        "rank": candidate.get("rank", ""),
        "searched_on": datetime.now(JST).date().isoformat(),
        "query": candidate.get(
            "query", f"{candidate['surface']} {candidate['pronunciation']} 氏名"
        ),
        "status": "ambiguous",
        "source_url": "",
        "source_type": "",
        "source_title": "",
        "observed_surface": "",
        "observed_reading": "",
        "locator": "",
        "notes": "候補別独立Yahoo! JAPAN検索。人物根拠は別工程で確認。",
        "evidence_tier": "",
        "identity_basis": "",
        "search_attempts": attempts,
    }
    return row


def run(input_csv, output, workers=1, delay=2.0, timeout=20, start=None, stop=None):
    candidates = _load_candidates(Path(input_csv))
    selected = [
        row
        for row in candidates
        if (start is None or int(row["batch_index"]) >= start)
        and (stop is None or int(row["batch_index"]) < stop)
    ]
    output = Path(output)
    done = _load_checkpoint(output)
    pending = [
        row for row in selected if not _complete(done.get(int(row["batch_index"]), {}))
    ]
    processed = 0
    if workers == 1:
        # A rate-limit response is not a completed search.  Checkpoint it and
        # stop immediately instead of hammering the endpoint with the rest of
        # a large batch; a later invocation retries incomplete candidates.
        for candidate in pending:
            row = _research(
                candidate, delay, timeout, done.get(int(candidate["batch_index"]))
            )
            done[row["batch_index"]] = row
            _save_checkpoint(output, done)
            processed += 1
            if not _complete(row):
                break
        return len(done), processed
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [
            pool.submit(
                _research, row, delay, timeout, done.get(int(row["batch_index"]))
            )
            for row in pending
        ]
        for future in as_completed(futures):
            row = future.result()
            done[row["batch_index"]] = row
            _save_checkpoint(output, done)
            processed += 1
    return len(done), processed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--start", type=int)
    parser.add_argument("--stop", type=int)
    args = parser.parse_args()
    rows, processed = run(
        args.input_csv,
        args.output,
        args.workers,
        args.delay,
        args.timeout,
        args.start,
        args.stop,
    )
    print(f"checkpoint={args.output} rows={rows} processed={processed}")


if __name__ == "__main__":
    main()
