#!/usr/bin/env python3
"""Resumable Google HTML surname-search receipt runner.

The runner records three search receipts per candidate.  Search hits are only
inputs to later URL/body review; this command never decides verification.
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
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit
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
ENDPOINT = "https://www.google.com/search?q="
KATA2HIRA = str.maketrans(
    {chr(c): chr(c - 0x60) for c in range(ord("ァ"), ord("ヶ") + 1)}
)


class _GoogleResults(HTMLParser):
    """Extract result anchors and snippets from common Google result markup."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.blocks = []
        self.block = None
        self.anchor = None
        self.snippet = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag == "div" and ("MjjYud" in classes or "g" in classes):
            if self.block is None:
                self.block = {"href": "", "title": [], "snippet": []}
                self.depth = 1
            else:
                self.depth += 1
        elif self.block is not None:
            self.depth += 1
        if self.block is not None and tag == "a" and not self.block["href"]:
            self.anchor = []
            self.block["href"] = attrs.get("href", "")
        if (
            self.block is not None
            and tag in ("div", "span")
            and ("VwiC3b" in classes or "yXK7kf" in classes)
        ):
            self.snippet = []

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor.append(data)
        if self.snippet is not None:
            self.snippet.append(data)

    def handle_endtag(self, tag):
        if self.anchor is not None and tag == "a":
            self.anchor = None
        if self.snippet is not None and tag in ("div", "span"):
            self.block["snippet"].append(" ".join("".join(self.snippet).split()))
            self.snippet = None
        if self.block is not None:
            self.depth -= 1
            if self.depth <= 0:
                self.blocks.append(self.block)
                self.block = None


def _target_url(href):
    if not href:
        return None
    href = html.unescape(href)
    parts = urlsplit(href)
    if parts.netloc.endswith("google.com") and parts.path in ("/url", "/aclk"):
        href = parse_qs(parts.query).get("q", parse_qs(parts.query).get("url", [""]))[0]
        href = unquote(href)
        parts = urlsplit(href)
    if parts.scheme != "https" or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    if host == "google.com" or host.endswith(".google.com"):
        return None
    return href


def fetch(query, timeout=20, opener=urlopen):
    request = Request(
        ENDPOINT + quote_plus(query),
        headers={"User-Agent": "Mozilla/5.0 (compatible; surname-research/1.0)"},
    )
    with opener(request, timeout=timeout) as response:
        status, body = int(response.status), response.read()
    parser = _GoogleResults()
    parser.feed(body.decode("utf-8", "replace"))
    urls, snippets = [], []
    for block in parser.blocks:
        url = _target_url(block["href"])
        if url and url not in urls:
            urls.append(url)
            snippets.append(" ".join(block["snippet"]).strip())
    return status, urls[:20], snippets[:20], body


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
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _query(candidate, strategy):
    surface, kata = candidate["surface"], candidate["pronunciation"]
    hira = kata.translate(KATA2HIRA)
    if strategy == "exact_katakana":
        query = f'"{surface}" "{kata}" 氏名'
    elif strategy == "exact_hiragana":
        query = f'"{surface}" "{hira}" 氏名'
    else:
        query = f"{surface} {kata} 人物 プロフィール"
    return (
        query + " " + " ".join(f"-site:{host}" for host in SECOND_PASS_EXCLUDED_SITES)
    )


def _attempt(candidate, strategy, delay, timeout):
    query = _query(candidate, strategy)
    if delay:
        time.sleep(delay)
    result = {
        "strategy": strategy,
        "engine": "google_html",
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
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    for i, row in enumerate(rows):
        row.setdefault("batch_index", str(i))
        row.setdefault("rank", "")
        row.setdefault("id", "")
        if not row.get("surface") or not row.get("pronunciation"):
            raise ValueError(f"row {i}: surface/pronunciation required")
    return rows


def _load_checkpoint(path):
    if not Path(path).exists():
        return {}
    return {
        int(row["batch_index"]): row
        for row in (
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def _complete(row):
    attempts = row.get("search_attempts", [])
    return {a.get("strategy") for a in attempts} == set(STRATEGIES) and all(
        a.get("http_status") == 200 for a in attempts
    )


def _save_checkpoint(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            for index in sorted(rows):
                stream.write(
                    json.dumps(rows[index], ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except Exception:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        raise


def _research(candidate, delay, timeout, existing=None):
    kept = {
        a.get("strategy"): a
        for a in (existing or {}).get("search_attempts", [])
        if a.get("strategy") in STRATEGIES and a.get("http_status") == 200
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
        "query": candidate.get("query", ""),
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
    rows = _load_candidates(input_csv)
    selected = [
        r
        for r in rows
        if (start is None or int(r["batch_index"]) >= start)
        and (stop is None or int(r["batch_index"]) < stop)
    ]
    path, done = Path(output), _load_checkpoint(output)
    pending = [
        r for r in selected if not _complete(done.get(int(r["batch_index"]), {}))
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
    else:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [
                pool.submit(
                    _research, r, delay, timeout, done.get(int(r["batch_index"]))
                )
                for r in pending
            ]
            for future in as_completed(futures):
                row = future.result()
                done[row["batch_index"]] = row
                _save_checkpoint(path, done)
                processed += 1
    return len(done), processed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--delay", type=float, default=1.0)
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
