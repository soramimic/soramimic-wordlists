#!/usr/bin/env python3
"""Resumable Yahoo! JAPAN search runner focused on public-sector and academic pages.

This is deliberately a receipt-producing search step, not an evidence
classifier.  Its JSONL checkpoint keeps the raw response hash and the
reachable result URLs/snippets so a later auditor can make that decision.
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
from urllib.error import HTTPError
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ENDPOINT = "https://search.yahoo.co.jp/search?p="
STRATEGIES = ("official_katakana", "official_hiragana", "official_person")
OFFICIAL_SITES = ("lg.jp", "go.jp", "ac.jp")
KATA2HIRA = str.maketrans(
    {chr(c): chr(c - 0x60) for c in range(ord("ァ"), ord("ヶ") + 1)}
)


class _Results(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.href = None
        self.parts = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            if self.depth == 0:
                self.href, self.parts = None, []
            self.depth += 1
        elif self.depth and tag == "a" and self.href is None:
            self.href = dict(attrs).get("href")

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "li" and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.href:
                self.rows.append(
                    (html.unescape(self.href), " ".join("".join(self.parts).split()))
                )


def _target_url(url):
    try:
        parts = urlsplit(html.unescape(url))
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    if host.endswith((".yahoo.co.jp", ".yimg.jp")):
        return None
    # Preserve the target while making URL-audit suffix checks unambiguous.
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            quote(parts.path, safe="/%:@!$&'*+,;=-._~"),
            quote(parts.query, safe="/?%:@!$&'*+,;=-._~"),
            quote(parts.fragment, safe="/?%:@!$&'*+,;=-._~"),
        )
    )


def fetch(query, timeout=20, opener=urlopen):
    req = Request(
        ENDPOINT + quote_plus(query) + "&n=10",
        headers={"User-Agent": "Mozilla/5.0 (compatible; surname-research/1.0)"},
    )
    with opener(req, timeout=timeout) as response:
        status, body = int(response.status), response.read()
    parser = _Results()
    parser.feed(body.decode("utf-8", "replace"))
    urls, snippets = [], []
    for href, snippet in parser.rows:
        target = _target_url(href)
        if target and target not in urls:
            urls.append(target)
            snippets.append(snippet)
    return status, urls[:20], snippets[:20], body


def _site_clause():
    return "(" + " OR ".join("site:" + site for site in OFFICIAL_SITES) + ")"


def query_for(candidate, strategy):
    surface, pronunciation = candidate["surface"], candidate["pronunciation"]
    hira = pronunciation.translate(KATA2HIRA)
    if strategy == "official_katakana":
        core = f'"{surface}" "{pronunciation}"'
    elif strategy == "official_hiragana":
        core = f'"{surface}" "{hira}"'
    else:
        core = f'"{surface}" ({pronunciation} OR {hira}) 人物'
    return f"{core} {_site_clause()}"


def receipt_sha256(attempt):
    payload = {
        k: attempt.get(k)
        for k in (
            "strategy",
            "engine",
            "query",
            "http_status",
            "result_count",
            "result_urls",
            "result_snippets",
            "response_body_sha256",
        )
    }
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _attempt(candidate, strategy, delay, timeout):
    query = query_for(candidate, strategy)
    if delay:
        time.sleep(delay)
    result = {
        "strategy": strategy,
        "engine": "yahoo_japan",
        "query": query,
        "completed_at": datetime.now(timezone.utc).isoformat(),
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


def _load_candidates(paths, status=None):
    if isinstance(paths, (str, Path)):
        paths = [paths]
    rows = []
    for source in paths:
        path = Path(source)
        if path.suffix.lower() == ".jsonl":
            rows.extend(
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        else:
            with path.open(newline="", encoding="utf-8-sig") as f:
                rows.extend(csv.DictReader(f))
    if status is not None:
        rows = [row for row in rows if row.get("status") == status]
    for i, row in enumerate(rows):
        row.setdefault("batch_index", str(i))
        row.setdefault("id", "")
        row.setdefault("rank", "")
        if not row.get("surface") or not row.get("pronunciation"):
            raise ValueError(f"row {i}: surface/pronunciation required")
    return rows


def _load_checkpoint(path):
    if not Path(path).exists():
        return {}
    return {
        _key(row := json.loads(line)): row
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _key(row):
    """Use the stable candidate id so multiple canonical batches can merge."""
    return str(row.get("id") or row["batch_index"])


def _complete(row):
    attempts = row.get("search_attempts", [])
    return {a.get("strategy") for a in attempts} == set(STRATEGIES) and all(
        a.get("http_status") == 200 for a in attempts
    )


def _save(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for i in sorted(rows):
                f.write(
                    json.dumps(rows[i], ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _research(candidate, delay, timeout, existing=None):
    old = {
        a.get("strategy"): a
        for a in (existing or {}).get("search_attempts", [])
        if a.get("strategy") in STRATEGIES and a.get("http_status") == 200
    }
    attempts = []
    for strategy in STRATEGIES:
        attempt = old.get(strategy) or _attempt(candidate, strategy, delay, timeout)
        attempts.append(attempt)
        if attempt.get("http_status") != 200:
            break
    return {
        "batch_index": int(candidate["batch_index"]),
        "id": candidate.get("id", ""),
        "surface": candidate["surface"],
        "pronunciation": candidate["pronunciation"],
        "rank": candidate.get("rank", ""),
        "searched_on": datetime.now(timezone.utc).date().isoformat(),
        "status": "ambiguous",
        "search_attempts": attempts,
    }


def run(
    input_csv,
    output,
    workers=1,
    delay=1.0,
    timeout=20,
    start=None,
    stop=None,
    status=None,
):
    selected = [
        r
        for r in _load_candidates(input_csv, status=status)
        if (start is None or int(r["batch_index"]) >= start)
        and (stop is None or int(r["batch_index"]) < stop)
    ]
    path = Path(output)
    done = _load_checkpoint(path)
    pending = [r for r in selected if not _complete(done.get(_key(r), {}))]
    processed = 0

    def save(row):
        nonlocal processed
        done[_key(row)] = row
        _save(path, done)
        processed += 1

    if workers <= 1:
        for candidate in pending:
            row = _research(candidate, delay, timeout, done.get(_key(candidate)))
            save(row)
            if not _complete(row):
                break
    else:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [
                pool.submit(_research, r, delay, timeout, done.get(_key(r)))
                for r in pending
            ]
            for future in as_completed(futures):
                save(future.result())
    return len(done), processed


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="candidate CSV or canonical result JSONL files",
    )
    p.add_argument("--output", required=True, type=Path)
    p.add_argument(
        "--status",
        default="no_support_found",
        help="filter JSONL rows by status (default: no_support_found)",
    )
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--delay", type=float, default=1.0)
    p.add_argument("--timeout", type=float, default=20)
    p.add_argument("--start", type=int)
    p.add_argument("--stop", type=int)
    a = p.parse_args()
    n, processed = run(
        a.inputs, a.output, a.workers, a.delay, a.timeout, a.start, a.stop, a.status
    )
    print(f"checkpoint={a.output} rows={n} processed={processed}")


if __name__ == "__main__":
    main()
