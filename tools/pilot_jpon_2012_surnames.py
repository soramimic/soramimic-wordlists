#!/usr/bin/env python3
"""Pilot a resumable, low-rate aggregation of 2012 phonebook surname tables.

Only aggregate surname/count facts are persisted. HTML, phone numbers, personal names,
and addresses are never written to disk. This is a feasibility tool, not a production
updater for myoji.csv.
"""

from __future__ import annotations

import argparse
import csv
import email.utils
import html.parser
import random
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SITEMAP = "https://jpon.xyz/sitemap/sitemap-2012-0.xml"
SITEMAP_TEMPLATE = "https://jpon.xyz/sitemap/sitemap-2012-{shard}.xml"
SITEMAP_SHARDS = 30
DEFAULT_DB = Path(__file__).resolve().parent / ".cache/jpon-2012-pilot.sqlite3"
DEFAULT_CSV = Path(__file__).resolve().parent / ".cache/jpon-2012-pilot.csv"
SECTIONS = {
    "この地域に多い苗字": "common",
    "この地域の希少苗字": "rare",
}
YEAR_URL_RE = re.compile(
    r"^(https://jpon\.xyz/2012/\d+/\d+/\d+\.html)(?:\?p=(\d+))?$"
)
SPACE_RE = re.compile(r"\s+")
INT_RE = re.compile(r"^[0-9][0-9,]*$")


@dataclass(frozen=True)
class PageFacts:
    advertised_entries: int | None
    common: dict[str, int]
    rare: dict[str, int]
    sections_seen: frozenset[str]

    @property
    def merged(self) -> dict[str, int]:
        return {
            surname: max(self.common.get(surname, 0), self.rare.get(surname, 0))
            for surname in self.common.keys() | self.rare.keys()
        }

    @property
    def overlaps(self) -> set[str]:
        return self.common.keys() & self.rare.keys()

    @property
    def conflicting_overlaps(self) -> set[str]:
        return {
            surname
            for surname in self.overlaps
            if self.common[surname] != self.rare[surname]
        }


class SurnameTableParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.section: str | None = None
        self.pending_section: str | None = None
        self.in_h3 = False
        self.h3_parts: list[str] = []
        self.table_depth = 0
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.row: list[str] | None = None
        self.common: dict[str, int] = {}
        self.rare: dict[str, int] = {}
        self.sections_seen: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h3":
            self.in_h3 = True
            self.h3_parts = []
        elif tag == "table" and self.pending_section:
            self.section = self.pending_section
            self.sections_seen.add(self.section)
            self.pending_section = None
            self.table_depth = 1
        elif tag == "table" and self.section:
            self.table_depth += 1
        elif tag == "tr" and self.section:
            self.row = []
        elif tag in {"td", "th"} and self.section and self.row is not None:
            self.in_cell = True
            self.cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "h3" and self.in_h3:
            heading = clean_text("".join(self.h3_parts))
            self.pending_section = SECTIONS.get(heading)
            self.in_h3 = False
        elif tag in {"td", "th"} and self.in_cell:
            assert self.row is not None
            self.row.append(clean_text("".join(self.cell_parts)))
            self.in_cell = False
        elif tag == "tr" and self.section and self.row is not None:
            self._store_row(self.section, self.row)
            self.row = None
        elif tag == "table" and self.section:
            self.table_depth -= 1
            if self.table_depth <= 0:
                self.section = None
                self.table_depth = 0

    def handle_data(self, data: str) -> None:
        if self.in_h3:
            self.h3_parts.append(data)
        if self.in_cell:
            self.cell_parts.append(data)

    def _store_row(self, section: str, cells: list[str]) -> None:
        if len(cells) < 2 or cells[0] == "苗字" or not INT_RE.fullmatch(cells[1]):
            return
        surname = cells[0]
        count = int(cells[1].replace(",", ""))
        if not surname or count < 1:
            return
        target = self.common if section == "common" else self.rare
        target[surname] = max(target.get(surname, 0), count)


def clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()


def parse_page(html_text: str) -> PageFacts:
    parser = SurnameTableParser()
    parser.feed(html_text)
    advertised = None
    match = re.search(r"掲載([0-9,]+)件", html_text)
    if match:
        advertised = int(match.group(1).replace(",", ""))
    return PageFacts(
        advertised, parser.common, parser.rare, frozenset(parser.sections_seen)
    )


def parse_sitemap(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    # The sitemap lists every pagination URL for large localities. The two pages
    # of a locality expose the same locality-wide surname tables, so fetching all
    # pagination URLs would double count and create avoidable load. Prefer p=1,
    # otherwise use the unpaginated URL used by single-page localities.
    by_locality: dict[str, str] = {}
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "loc" or not element.text:
            continue
        url = element.text.strip()
        match = YEAR_URL_RE.fullmatch(url)
        if not match:
            continue
        locality, page = match.groups()
        if locality not in by_locality or page == "1":
            by_locality[locality] = url
    return list(by_locality.values())


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS pages (
          url TEXT PRIMARY KEY,
          fetched_at TEXT NOT NULL,
          http_status INTEGER NOT NULL,
          advertised_entries INTEGER,
          common_rows INTEGER NOT NULL,
          rare_rows INTEGER NOT NULL,
          overlap_rows INTEGER NOT NULL,
          conflicting_overlap_rows INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS page_surnames (
          url TEXT NOT NULL REFERENCES pages(url) ON DELETE CASCADE,
          surname TEXT NOT NULL,
          local_count INTEGER NOT NULL,
          in_common INTEGER NOT NULL,
          in_rare INTEGER NOT NULL,
          PRIMARY KEY (url, surname)
        );
        CREATE TABLE IF NOT EXISTS seeded_sitemaps (
          url TEXT PRIMARY KEY,
          seeded_at TEXT NOT NULL,
          locality_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS queued_urls (
          url TEXT PRIMARY KEY,
          sitemap_url TEXT NOT NULL REFERENCES seeded_sitemaps(url)
        );
        """
    )
    return db


def store_page(db: sqlite3.Connection, url: str, facts: PageFacts) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with db:
        db.execute("DELETE FROM page_surnames WHERE url = ?", (url,))
        db.execute("DELETE FROM pages WHERE url = ?", (url,))
        db.execute(
            "INSERT INTO pages VALUES (?, ?, 200, ?, ?, ?, ?, ?)",
            (
                url,
                now,
                facts.advertised_entries,
                len(facts.common),
                len(facts.rare),
                len(facts.overlaps),
                len(facts.conflicting_overlaps),
            ),
        )
        for surname, count in sorted(facts.merged.items()):
            db.execute(
                "INSERT INTO page_surnames VALUES (?, ?, ?, ?, ?)",
                (
                    url,
                    surname,
                    count,
                    int(surname in facts.common),
                    int(surname in facts.rare),
                ),
            )


def export_csv(db: sqlite3.Connection, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = db.execute(
        """
        SELECT surname, SUM(local_count) AS observed_households,
               COUNT(*) AS pages_seen
        FROM page_surnames
        GROUP BY surname
        ORDER BY observed_households DESC, surname
        """
    )
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["surname", "observed_households", "pages_seen"])
        writer.writerows(rows)


def retry_after_seconds(headers: object, default: float) -> float:
    value = getattr(headers, "get", lambda _key: None)("Retry-After")
    if not value:
        return default
    try:
        return max(float(value), 0.0)
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            return max((parsed - datetime.now(timezone.utc)).total_seconds(), 0.0)
        except (TypeError, ValueError):
            return default


def fetch(url: str, user_agent: str, timeout: float, retries: int = 3) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise RuntimeError("HTTP 403: crawl halted; do not bypass access controls") from exc
            if exc.code != 429 and exc.code < 500:
                raise
            if attempt == retries:
                raise
            time.sleep(retry_after_seconds(exc.headers, 30.0 * (2**attempt)))
        except (OSError, TimeoutError):
            if attempt == retries:
                raise
            time.sleep(10.0 * (2**attempt))
    raise AssertionError("unreachable")


def sitemap_is_seeded(db: sqlite3.Connection, url: str) -> bool:
    return db.execute(
        "SELECT 1 FROM seeded_sitemaps WHERE url = ?", (url,)
    ).fetchone() is not None


def seed_sitemap(db: sqlite3.Connection, sitemap_url: str, urls: list[str]) -> None:
    with db:
        db.execute(
            "INSERT OR REPLACE INTO seeded_sitemaps VALUES (?, ?, ?)",
            (sitemap_url, datetime.now(timezone.utc).isoformat(), len(urls)),
        )
        db.executemany(
            "INSERT OR IGNORE INTO queued_urls VALUES (?, ?)",
            ((url, sitemap_url) for url in urls),
        )


def select_urls(db: sqlite3.Connection, limit: int) -> list[str]:
    return [
        row[0]
        for row in db.execute(
            """SELECT q.url FROM queued_urls q
               LEFT JOIN pages p ON p.url = q.url
               WHERE p.url IS NULL
               ORDER BY q.rowid LIMIT ?""",
            (limit,),
        )
    ]


def summary(db: sqlite3.Connection) -> dict[str, int]:
    page_row = db.execute(
        """SELECT COUNT(*), COALESCE(SUM(advertised_entries), 0),
                  COALESCE(SUM(common_rows), 0), COALESCE(SUM(rare_rows), 0),
                  COALESCE(SUM(overlap_rows), 0),
                  COALESCE(SUM(conflicting_overlap_rows), 0)
           FROM pages"""
    ).fetchone()
    surname_row = db.execute(
        "SELECT COUNT(DISTINCT surname), COALESCE(SUM(local_count), 0) FROM page_surnames"
    ).fetchone()
    assert page_row and surname_row
    return {
        "pages": page_row[0],
        "advertised_entries": page_row[1],
        "common_rows": page_row[2],
        "rare_rows": page_row[3],
        "overlaps": page_row[4],
        "conflicting_overlaps": page_row[5],
        "distinct_surnames": surname_row[0],
        "observed_households": surname_row[1],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--delay", type=float, default=10.0)
    parser.add_argument("--jitter", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--sitemap",
        action="append",
        help="Sitemap shard URL (repeatable; defaults to shard 0)",
    )
    parser.add_argument(
        "--all-shards",
        action="store_true",
        help="Seed all 30 known 2012 sitemap shards for a resumable full crawl",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_CSV)
    parser.add_argument(
        "--user-agent",
        default="soramimic-wordlists-jpon-feasibility-pilot/0.1",
        help="Descriptive User-Agent; append a contact URL or email when running",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit < 1 or args.delay < 0 or not 0 <= args.jitter <= 1:
        raise SystemExit("--limit must be positive; --delay >= 0; --jitter between 0 and 1")
    db = init_db(args.db)
    if args.all_shards and args.sitemap:
        raise SystemExit("use either --all-shards or --sitemap, not both")
    sitemap_urls = (
        [SITEMAP_TEMPLATE.format(shard=shard) for shard in range(SITEMAP_SHARDS)]
        if args.all_shards
        else (args.sitemap or [SITEMAP])
    )
    fetched_sitemaps = 0
    for sitemap_url in sitemap_urls:
        if sitemap_is_seeded(db, sitemap_url):
            continue
        if fetched_sitemaps:
            time.sleep(min(args.delay, 2.0))
        sitemap_xml = fetch(sitemap_url, args.user_agent, args.timeout)
        seed_sitemap(db, sitemap_url, parse_sitemap(sitemap_xml))
        fetched_sitemaps += 1
    selected = select_urls(db, args.limit)
    for index, url in enumerate(selected, 1):
        if index > 1 and args.delay:
            multiplier = random.uniform(1 - args.jitter, 1 + args.jitter)
            time.sleep(args.delay * multiplier)
        facts = parse_page(fetch(url, args.user_agent, args.timeout).decode("utf-8"))
        if facts.sections_seen != {"common", "rare"}:
            raise RuntimeError(f"No surname tables parsed; refusing to checkpoint {url}")
        if facts.conflicting_overlaps:
            names = ", ".join(sorted(facts.conflicting_overlaps)[:5])
            raise RuntimeError(
                f"Conflicting local counts in common/rare tables at {url}: {names}"
            )
        store_page(db, url, facts)
        stats = summary(db)
        print(
            f"[{stats['pages']}] {url} surnames={len(facts.merged)} "
            f"overlaps={len(facts.overlaps)} conflicts={len(facts.conflicting_overlaps)}",
            flush=True,
        )
    export_csv(db, args.output)
    print(summary(db), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
