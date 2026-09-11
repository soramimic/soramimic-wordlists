#!/usr/bin/env python3
"""Audit image URLs in root word-list CSV files.

Scheduled runs keep a small cursor so a missed run resumes the same sweep. Pull
request runs check only URLs newly introduced relative to the base revision.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import html
import io
import json
import os
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

USER_AGENT = (
    "soramimic-wordlists-image-link-audit/1.0 "
    "(https://github.com/soramimic/soramimic-wordlists)"
)
STATUSES = ("ok", "broken", "invalid", "unavailable")
ACTIONABLE = {"broken", "invalid"}


def now() -> str:
    return datetime.now(UTC).isoformat()


def public_url(url: str) -> str:
    """Remove transient signatures and fragments from a redirect destination."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def image_prefix(data: bytes) -> bool:
    if data.startswith(
        (
            b"\x89PNG\r\n\x1a\n",
            b"\xff\xd8\xff",
            b"GIF87a",
            b"GIF89a",
            b"BM",
            b"II*\x00",
            b"MM\x00*",
            b"\x00\x00\x01\x00",
        )
    ):
        return True
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return True
    if data[4:8] == b"ftyp" and data[8:12] in {b"avif", b"avis"}:
        return True
    text = data.lstrip().lower()
    return text.startswith((b"<svg", b"<?xml")) and b"<svg" in text


def probe(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - CSV URLs are intended
            code = response.status
            final_url = public_url(response.url)
            content_type = response.headers.get_content_type().lower()
            prefix = response.read(1024)
    except HTTPError as exc:
        status = "broken" if exc.code in {404, 410} else "unavailable"
        return {
            "status": status,
            "http_status": exc.code,
            "reason": f"HTTP {exc.code}",
            "final_url": public_url(exc.url),
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "status": "unavailable",
            "http_status": None,
            "reason": type(exc).__name__,
        }

    result = {"http_status": code, "final_url": final_url}
    text = prefix.lstrip().lower()
    if code != 200:
        return {**result, "status": "unavailable", "reason": f"HTTP {code}"}
    if not text:
        return {**result, "status": "invalid", "reason": "empty response"}
    if content_type in {"text/html", "application/xhtml+xml"} or text.startswith(
        (b"<!doctype html", b"<html")
    ):
        return {**result, "status": "invalid", "reason": "HTML instead of image"}
    if content_type == "application/pdf" or prefix.startswith(b"%PDF-"):
        return {**result, "status": "invalid", "reason": "PDF instead of image"}
    if content_type.startswith("image/") or image_prefix(prefix):
        return {**result, "status": "ok", "reason": "image endpoint reachable"}
    return {
        **result,
        "status": "unavailable",
        "reason": f"unrecognized content type: {content_type}",
    }


class RateLimiter:
    """Space request starts globally while allowing slow requests to overlap."""

    def __init__(self, interval: float):
        self.interval = interval
        self.next_request = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            remaining = self.next_request - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            self.next_request = time.monotonic() + self.interval


def rows_from_text(text: str, wordlist: str) -> dict[str, list[dict[str, str]]]:
    links: dict[str, list[dict[str, str]]] = {}
    for row in csv.DictReader(io.StringIO(text, newline="")):
        url = (row.get("image") or "").strip()
        if not url.startswith(("https://", "http://")):
            continue
        reference = {
            "wordlist": wordlist,
            "name": row.get("original") or row.get("surface") or "",
        }
        refs = links.setdefault(url, [])
        if reference not in refs:
            refs.append(reference)
    return links


def merge_links(target: dict[str, list[dict[str, str]]], source: dict[str, list[dict[str, str]]]) -> None:
    for url, references in source.items():
        refs = target.setdefault(url, [])
        refs.extend(reference for reference in references if reference not in refs)


def collect_links(root: Path) -> dict[str, list[dict[str, str]]]:
    links: dict[str, list[dict[str, str]]] = {}
    for path in sorted(root.glob("*.csv")):
        merge_links(links, rows_from_text(path.read_text(encoding="utf-8"), path.stem))
    if not links:
        raise ValueError(f"画像URLを含むCSVがありません: {root}")
    return links


def git_text(revision: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout


def revision_links(revision: str) -> dict[str, list[dict[str, str]]]:
    result = subprocess.run(
        ["git", "ls-tree", "--name-only", revision],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    links: dict[str, list[dict[str, str]]] = {}
    for name in sorted(result.stdout.splitlines()):
        path = Path(name)
        if path.parent != Path(".") or path.suffix != ".csv":
            continue
        merge_links(links, rows_from_text(git_text(revision, name), path.stem))
    return links


def changed_links(base: str, head: str) -> dict[str, list[dict[str, str]]]:
    before = revision_links(base)
    after = revision_links(head)
    return {url: after[url] for url in sorted(after.keys() - before.keys())}


def load_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"version": 1, "cursor_after": "", "cycle": 0, "findings": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("version") != 1 or not isinstance(value.get("findings"), dict):
        raise ValueError(f"未対応の検査状態です: {path}")
    return value


def select_shard(urls: list[str], cursor_after: str, maximum: int) -> tuple[list[str], int]:
    if not urls:
        return [], 0
    if maximum <= 0 or maximum >= len(urls):
        return urls, 1
    start = bisect.bisect_right(urls, cursor_after) if cursor_after else 0
    end = start + maximum
    if end <= len(urls):
        return urls[start:end], 0
    return urls[start:] + urls[: end - len(urls)], 1


def audit(
    links: dict[str, list[dict[str, str]]],
    *,
    maximum: int,
    state_path: Path | None,
    report_path: Path,
    workers: int,
    timeout: float,
    delay: float,
) -> tuple[dict[str, Any], int]:
    if maximum < 0 or workers not in {1, 2} or not 0 < timeout <= 60 or not 0 <= delay <= 60:
        raise ValueError("max-urls>=0、workers=1..2、timeout=0..60、delay=0..60が必要です")
    state = load_state(state_path)
    urls = sorted(links)
    selected, wrapped = select_shard(urls, state.get("cursor_after", ""), maximum)
    limiter = RateLimiter(delay)
    started_at = now()

    def check(url: str) -> dict[str, Any]:
        limiter.wait()
        result = probe(url, timeout)
        if result["status"] in ACTIONABLE:
            limiter.wait()
            result = probe(url, timeout)
        return {**result, "url": url, "references": links[url], "checked_at": now()}

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, result in enumerate(pool.map(check, selected), 1):
            results.append(result)
            if index % 100 == 0:
                print(f"画像URL検査: {index} / {len(selected)}", flush=True)

    active = set(urls)
    findings = {
        url: {**finding, "references": links[url]}
        for url, finding in state.get("findings", {}).items()
        if url in active
    }
    for result in results:
        if result["status"] in ACTIONABLE:
            findings[result["url"]] = result
        elif result["status"] == "ok":
            findings.pop(result["url"], None)
    counts = {status: 0 for status in STATUSES}
    counts.update(Counter(result["status"] for result in results))
    next_state = {
        "version": 1,
        "cursor_after": selected[-1] if selected else state.get("cursor_after", ""),
        "cycle": int(state.get("cycle", 0)) + wrapped,
        "findings": findings,
        "updated_at": now(),
    }
    report = {
        "version": 1,
        "started_from": state.get("cursor_after", ""),
        "started_at": started_at,
        "finished_at": now(),
        "total_urls": len(urls),
        "checked_urls": len(results),
        "counts": counts,
        "cursor_after": next_state["cursor_after"],
        "cycle": next_state["cycle"],
        "known_findings": [findings[url] for url in sorted(findings)],
        "results": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if state_path is not None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(next_state, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "total_urls": report["total_urls"],
                "checked_urls": report["checked_urls"],
                **counts,
                "known_findings": len(findings),
                "cycle": report["cycle"],
            },
            ensure_ascii=False,
        )
    )
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        write_summary(report, Path(summary_path))
    return report, 1 if findings else 0


def write_summary(report: dict[str, Any], path: Path) -> None:
    counts = report["counts"]
    lines = [
        "## 画像URL検査",
        "",
        f"検査 {report['checked_urls']:,} / 全 {report['total_urls']:,} URL、"
        f"正常 {counts['ok']:,}、リンク切れ {counts['broken']:,}、"
        f"画像でない応答 {counts['invalid']:,}、一時取得不能 {counts['unavailable']:,}",
        "",
    ]
    findings = report["known_findings"]
    if findings:
        lines.extend(["### 未解消", "", "| 状態 | リスト・名前 | URL |", "|---|---|---|"])
        for finding in findings[:100]:
            references = "、".join(
                f"{ref['wordlist']}:{ref['name']}" for ref in finding["references"]
            )
            values = [finding["status"], references, finding["url"]]
            escaped = [html.escape(value.replace("|", "\\|").replace("\n", " ")) for value in values]
            lines.append(f"| {escaped[0]} | {escaped[1]} | {escaped[2]} |")
        if len(findings) > 100:
            lines.extend(["", f"残り {len(findings) - 100:,} 件はArtifactのJSONを確認してください。"])
        lines.append("")
    unavailable = [row for row in report["results"] if row["status"] == "unavailable"]
    if unavailable:
        lines.extend([
            "一時取得不能はリンク切れに含めません。詳細はArtifactのJSONに保存しています。",
            "",
        ])
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--root", type=Path, default=Path("."))
    result.add_argument("--report", type=Path, required=True)
    result.add_argument("--state", type=Path)
    result.add_argument("--max-urls", type=int, default=2500)
    result.add_argument("--workers", type=int, choices=(1, 2), default=2)
    result.add_argument("--timeout", type=float, default=5)
    result.add_argument("--delay", type=float, default=1)
    result.add_argument("--changed-from")
    result.add_argument("--changed-to")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if bool(args.changed_from) != bool(args.changed_to):
            raise ValueError("--changed-from と --changed-to は同時に指定してください")
        links = (
            changed_links(args.changed_from, args.changed_to)
            if args.changed_from
            else collect_links(args.root)
        )
        _, status = audit(
            links,
            maximum=0 if args.changed_from else args.max_urls,
            state_path=None if args.changed_from else args.state,
            report_path=args.report,
            workers=args.workers,
            timeout=args.timeout,
            delay=args.delay,
        )
        return status
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"画像URL検査失敗: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
