#!/usr/bin/env python3
"""Normalize captured search receipts without inventing search evidence."""

import argparse
import json
import os
import re
import tempfile
import urllib.parse
from pathlib import Path

from audit_myoji_web_research import (
    BAD_URL_SUFFIXES,
    SEARCH_OR_REDIRECT_HOSTS,
    receipt_sha256,
)


def sanitize_url(value):
    url = str(value).strip()
    # A result href may legitimately end in punctuation, as with Wikipedia
    # titles such as ``Name_(surname)``. Preserve the target by encoding the
    # terminal character instead of truncating it.
    terminal = ""
    while url.endswith(BAD_URL_SUFFIXES):
        terminal = url[-1] + terminal
        url = url[:-1].rstrip()
    if terminal:
        url += "".join(urllib.parse.quote(char, safe="") for char in terminal)
    if not url.startswith("https://") or any(character.isspace() for character in url):
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or "").lower()
        # Accessing ``port`` also rejects malformed bracket/colon constructs
        # that urlsplit may otherwise leave in the authority component.
        _ = parsed.port
        ascii_host = host.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        return ""
    if not re.fullmatch(
        r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
        ascii_host,
    ):
        return ""
    if "." not in host or host in SEARCH_OR_REDIRECT_HOSTS:
        return ""
    # A bare site root is not a captured result page and cannot support a
    # candidate-specific audit.  Keep URLs with a path, query, or fragment.
    if parsed.path in ("", "/") and not parsed.query and not parsed.fragment:
        return ""
    return url


def sanitize_attempt(attempt):
    # Search-result snippets are not part of the receipt digest and are not
    # needed to reproduce the audit trail.  Do not redistribute captured page
    # text when the query, destination URLs, response hash, and timestamp are
    # sufficient.
    attempt.pop("result_snippets", None)
    urls = []
    for value in attempt.get("result_urls", []):
        url = sanitize_url(value)
        if url and url not in urls:
            urls.append(url)
    attempt["result_urls"] = urls
    attempt["result_count"] = len(urls)
    attempt["response_sha256"] = receipt_sha256(attempt)


def sanitize_file(path):
    path = Path(path)
    rows = []
    changed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        before = json.dumps(
            row.get("search_attempts", []), ensure_ascii=False, sort_keys=True
        )
        for attempt in row.get("search_attempts", []):
            sanitize_attempt(attempt)
        after = json.dumps(
            row.get("search_attempts", []), ensure_ascii=False, sort_keys=True
        )
        changed += before != after
        rows.append(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + ("\n" if rows else ""))
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", type=Path, nargs="+")
    args = parser.parse_args()
    total = 0
    for path in args.paths:
        changed = sanitize_file(path)
        total += changed
        print(f"{path}: normalized {changed} records")
    print(f"normalized {total} records total")


if __name__ == "__main__":
    main()
