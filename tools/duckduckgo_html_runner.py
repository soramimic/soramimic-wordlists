#!/usr/bin/env python3
"""Resumable, rate-limited DuckDuckGo HTML search runner.

The runner records search receipts only; deciding whether a hit proves a person
has the surname remains a separate review step.
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
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlsplit
from urllib.request import Request, urlopen

STRATEGIES = ("exact_katakana", "exact_hiragana", "broad_person")
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
ENDPOINT = "https://lite.duckduckgo.com/lite/?q="
KATA2HIRA = str.maketrans(
    {chr(c): chr(c - 0x60) for c in range(ord("ァ"), ord("ヶ") + 1)}
)


class _Results(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.snippets = []
        self.href = None
        self.text = []
        self.in_snippet = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set(a.get("class", "").split())
        if tag == "a" and ("result__a" in classes or "result-link" in classes):
            self.href = a.get("href")
            self.text = []
        elif tag in ("a", "td") and (
            "result__snippet" in classes or "result-snippet" in classes
        ):
            self.in_snippet = True
            self.text = []

    def handle_data(self, data):
        if self.href is not None or self.in_snippet:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.in_snippet:
            self.snippets.append("".join(self.text).strip())
            self.in_snippet = False
        elif tag != "a":
            return
        elif self.href is not None:
            self.rows.append((self.href, "".join(self.text).strip()))
            self.href = None
        elif self.in_snippet:
            self.snippets.append("".join(self.text).strip())
        self.in_snippet = False


def _target_url(href):
    """Unwrap DDG redirect links and reject non-http targets."""
    if not href:
        return None
    href = html.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    p = urlsplit(href)
    if p.netloc.endswith("duckduckgo.com") and p.path == "/l/":
        href = parse_qs(p.query).get("uddg", [""])[0]
    p = urlsplit(href)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    return href


def fetch(query, timeout=20, opener=urlopen):
    req = Request(
        ENDPOINT + quote_plus(query),
        headers={"User-Agent": "Mozilla/5.0 (compatible; surname-research/1.0)"},
    )
    with opener(req, timeout=timeout) as response:
        status = int(response.status)
        body = response.read()
    parser = _Results()
    parser.feed(body.decode("utf-8", "replace"))
    urls, snippets = [], []
    for href, snippet in parser.rows:
        url = _target_url(href)
        if url and url not in urls:
            urls.append(url)
            snippets.append(snippet)
    return status, urls[:20], parser.snippets[:20], body


def receipt_sha256(attempt):
    payload = {
        k: attempt[k]
        for k in (
            "strategy",
            "engine",
            "query",
            "http_status",
            "result_count",
            "result_urls",
        )
    }
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _attempt(candidate, strategy, delay, timeout):
    s, p = candidate["surface"], candidate["pronunciation"]
    hira = p.translate(KATA2HIRA)
    exclusions = " " + " ".join(f"-site:{host}" for host in SECOND_PASS_EXCLUDED_SITES)
    q = (
        f'"{s}" "{p}" 氏名'
        if strategy == "exact_katakana"
        else f'"{s}" "{hira}" 氏名'
        if strategy == "exact_hiragana"
        else f"{s} {p} 人物 プロフィール"
    )
    q += exclusions
    if delay:
        time.sleep(delay)
    base = {
        "strategy": strategy,
        "engine": "duckduckgo_html",
        "query": q,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        status, urls, snippets, body = fetch(q, timeout=timeout)
        base.update(
            http_status=status,
            result_count=len(urls),
            result_urls=urls,
            result_snippets=snippets,
            response_body_sha256=hashlib.sha256(body).hexdigest(),
        )
    except Exception as exc:  # preserve explicit failure for resumption/diagnostics
        base.update(
            http_status=599,
            result_count=0,
            result_urls=[],
            result_snippets=[],
            error=f"{type(exc).__name__}: {exc}",
        )
    base["response_sha256"] = receipt_sha256(base)
    return base


def _load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for i, row in enumerate(rows):
        row.setdefault("batch_index", str(i))
        row.setdefault("rank", "")
        row.setdefault("id", "")
        if not row.get("surface") or not row.get("pronunciation"):
            raise ValueError(f"row {i}: surface/pronunciation required")
    return rows


def _load_checkpoint(path):
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            result[int(row["batch_index"])] = row
    return result


def _complete(row):
    attempts = row.get("search_attempts", [])
    return {attempt.get("strategy") for attempt in attempts} == set(STRATEGIES) and all(
        attempt.get("http_status") == 200 for attempt in attempts
    )


def _save_checkpoint(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for i in sorted(rows):
                f.write(
                    json.dumps(rows[i], ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    except Exception:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        raise


def _research(candidate, delay, timeout, existing=None):
    """Retry only strategies without a successful HTTP 200 receipt."""
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
    return {
        "batch_index": int(candidate["batch_index"]),
        "id": candidate.get("id", ""),
        "surface": candidate["surface"],
        "pronunciation": candidate["pronunciation"],
        "rank": candidate.get("rank", ""),
        "query": candidate.get(
            "query", f"{candidate['surface']} {candidate['pronunciation']} 氏名"
        ),
        "searched_on": datetime.now(timezone.utc).date().isoformat(),
        "status": "ambiguous",
        "source_url": "",
        "source_type": "",
        "source_title": "",
        "observed_surface": "",
        "observed_reading": "",
        "locator": "",
        "notes": "",
        "evidence_tier": "",
        "identity_basis": "",
        "search_attempts": attempts,
    }


def run(input_csv, output, workers=1, delay=1.0, timeout=20, start=None, stop=None):
    candidates = _load_csv(input_csv)
    selected = [
        row
        for row in candidates
        if (start is None or int(row["batch_index"]) >= start)
        and (stop is None or int(row["batch_index"]) < stop)
    ]
    path = Path(output)
    done = _load_checkpoint(path)
    pending = [
        row for row in selected if not _complete(done.get(int(row["batch_index"]), {}))
    ]
    processed = 0
    if workers == 1:
        for candidate in pending:
            row = _research(
                candidate, delay, timeout, done.get(int(candidate["batch_index"]))
            )
            done[row["batch_index"]] = row
            _save_checkpoint(path, done)
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
            _save_checkpoint(path, done)
            processed += 1
    return len(done), processed


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input_csv", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--delay", type=float, default=1.0)
    p.add_argument("--timeout", type=float, default=20)
    p.add_argument("--start", type=int)
    p.add_argument("--stop", type=int)
    a = p.parse_args()
    n, processed = run(
        a.input_csv, a.output, a.workers, a.delay, a.timeout, a.start, a.stop
    )
    print(f"checkpoint={a.output} rows={n} processed={processed}")


if __name__ == "__main__":
    main()
