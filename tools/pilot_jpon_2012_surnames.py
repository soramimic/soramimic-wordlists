#!/usr/bin/env python3
"""Pilot a resumable, low-rate aggregation of Jpon phonebook surname tables.

Only aggregate surname/count facts are persisted. HTML, phone numbers, personal names,
and addresses are never written to disk. This is a feasibility tool, not a production
updater for myoji.csv.
"""

from __future__ import annotations

import argparse
import csv
import email.utils
import html.parser
import http.cookiejar
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
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
YEAR_2000_ROOT = "https://jpon.xyz/2000/index.html"
DEFAULT_2000_DB = Path(__file__).resolve().parent / ".cache/jpon-2000-pilot.sqlite3"
DEFAULT_2000_CSV = Path(__file__).resolve().parent / ".cache/jpon-2000-pilot.csv"
SECTIONS = {
    "この地域に多い苗字": "common",
    "この地域の希少苗字": "rare",
}
YEAR_URL_RE = re.compile(
    r"^(https://jpon\.xyz/2012/\d+/\d+/\d+\.html)(?:\?p=(\d+))?$"
)
SPACE_RE = re.compile(r"\s+")
INT_RE = re.compile(r"^[0-9][0-9,]*$")
YEAR_2000_PATH_RE = re.compile(
    r"^/2000/(?:index\.html|\d+/index\.html|\d+/\d+/index\.html|\d+/\d+/\d+\.html)$"
)


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


class LinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


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


def normalize_2000_url(href: str, base_url: str = YEAR_2000_ROOT) -> str | None:
    """Return a canonical in-scope 2000 hierarchy URL, or None.

    Query strings and fragments are deliberately discarded: surname tables describe
    the whole town, while pagination exposes the same aggregate tables.
    """
    parsed = urllib.parse.urlsplit(urllib.parse.urljoin(base_url, href))
    if parsed.scheme != "https" or parsed.netloc.lower() != "jpon.xyz":
        return None
    path = re.sub(r"/+", "/", parsed.path)
    if not YEAR_2000_PATH_RE.fullmatch(path):
        return None
    return urllib.parse.urlunsplit(("https", "jpon.xyz", path, "", ""))


def hierarchy_kind(url: str) -> str | None:
    normalized = normalize_2000_url(url)
    if not normalized:
        return None
    parts = urllib.parse.urlsplit(normalized).path.strip("/").split("/")[1:]
    if parts == ["index.html"]:
        return "root"
    if parts[-1] == "index.html":
        return {2: "prefecture", 3: "municipality"}.get(len(parts))
    return "town" if len(parts) == 3 else None


def parse_hierarchy_links(html_text: str, source_url: str) -> list[tuple[str, str]]:
    """Extract only the next hierarchy level, ignoring navigation/breadcrumb links."""
    source_kind = hierarchy_kind(source_url)
    wanted = {
        "root": "prefecture",
        "prefecture": "municipality",
        "municipality": "town",
    }.get(source_kind)
    if wanted is None:
        return []
    parser = LinkParser()
    parser.feed(html_text)
    found: dict[str, str] = {}
    for href in parser.hrefs:
        url = normalize_2000_url(href, source_url)
        if url and hierarchy_kind(url) == wanted:
            found[url] = wanted
    return sorted(found.items())


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
        CREATE TABLE IF NOT EXISTS hierarchy_queue (
          url TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          source_url TEXT,
          fetched_at TEXT
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


def fetch(
    url: str,
    user_agent: str,
    timeout: float,
    retries: int = 3,
    opener: urllib.request.OpenerDirector | None = None,
) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    open_url = opener.open if opener else urllib.request.urlopen
    for attempt in range(retries + 1):
        try:
            with open_url(request, timeout=timeout) as response:
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


_CDP_COOKIE_SCRIPT = r"""
const http = require('http');
const endpoint = process.argv[1];
const outputFd = Number(process.env.JPON_COOKIE_FD);
const deadline = setTimeout(() => {
  process.stderr.write('Timed out while reading Chrome cookies');
  process.exit(1);
}, 10000);
function getJson(url) {
  return new Promise((resolve, reject) => http.get(url, response => {
    let body = '';
    response.setEncoding('utf8');
    response.on('data', chunk => body += chunk);
    response.on('end', () => {
      try { resolve(JSON.parse(body)); } catch (error) { reject(error); }
    });
  }).on('error', reject));
}
(async () => {
  const version = await getJson(endpoint.replace(/\/$/, '') + '/json/version');
  const ws = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, {once: true});
    ws.addEventListener('error', reject, {once: true});
  });
  const reply = new Promise((resolve, reject) => {
    ws.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (message.id === 1) message.error ? reject(new Error(message.error.message)) : resolve(message.result);
    });
  });
  ws.send(JSON.stringify({id: 1, method: 'Storage.getCookies'}));
  const result = await reply;
  const cookies = result.cookies.filter(cookie => cookie.domain === 'jpon.xyz' || cookie.domain.endsWith('.jpon.xyz'));
  require('fs').writeFileSync(outputFd, JSON.stringify(cookies));
  clearTimeout(deadline);
  ws.close();
})().catch(error => { process.stderr.write(String(error.message || error)); process.exit(1); });
"""


def load_cdp_cookie_jar(
    cdp_endpoint: str = "http://127.0.0.1:9224",
) -> http.cookiejar.CookieJar:
    """Copy Jpon cookies from Chrome to an in-memory CookieJar via a private pipe."""
    read_fd, write_fd = os.pipe()
    env = dict(os.environ)
    env["JPON_COOKIE_FD"] = str(write_fd)
    try:
        process = subprocess.Popen(
            ["node", "-e", _CDP_COOKIE_SCRIPT, cdp_endpoint],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            pass_fds=(write_fd,),
            env=env,
        )
        os.close(write_fd)
        write_fd = -1
        with os.fdopen(read_fd, "rb") as pipe:
            payload = pipe.read()
        read_fd = -1
        _unused, error = process.communicate()
        if process.returncode:
            raise RuntimeError(
                "Could not read Jpon login from Chrome CDP: "
                + error.decode("utf-8", "replace")
            )
        records = json.loads(payload)
    finally:
        if read_fd >= 0:
            os.close(read_fd)
        if write_fd >= 0:
            os.close(write_fd)
    jar = http.cookiejar.CookieJar()
    for item in records:
        domain = item["domain"]
        jar.set_cookie(
            http.cookiejar.Cookie(
                version=0,
                name=item["name"],
                value=item["value"],
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=domain.startswith("."),
                domain_initial_dot=domain.startswith("."),
                path=item.get("path", "/"),
                path_specified=True,
                secure=bool(item.get("secure")),
                expires=int(item["expires"]) if item.get("expires", -1) > 0 else None,
                discard=item.get("expires", -1) <= 0,
                comment=None,
                comment_url=None,
                rest={"HttpOnly": item.get("httpOnly", False)},
                rfc2109=False,
            )
        )
    if not list(jar):
        raise RuntimeError("Chrome CDP returned no Jpon cookies; log in at https://jpon.xyz first")
    return jar


def enqueue_hierarchy(
    db: sqlite3.Connection,
    entries: list[tuple[str, str]],
    source_url: str | None,
) -> None:
    with db:
        db.executemany(
            "INSERT OR IGNORE INTO hierarchy_queue(url, kind, source_url) VALUES (?, ?, ?)",
            ((url, kind, source_url) for url, kind in entries),
        )


def next_hierarchy_url(db: sqlite3.Connection) -> tuple[str, str] | None:
    row = db.execute(
        """SELECT url, kind FROM hierarchy_queue WHERE fetched_at IS NULL
           ORDER BY CASE kind WHEN 'town' THEN 0 WHEN 'municipality' THEN 1
                              WHEN 'prefecture' THEN 2 ELSE 3 END, rowid LIMIT 1"""
    ).fetchone()
    return (row[0], row[1]) if row else None


def checkpoint_index(db: sqlite3.Connection, url: str, children: list[tuple[str, str]]) -> None:
    with db:
        db.executemany(
            "INSERT OR IGNORE INTO hierarchy_queue(url, kind, source_url) VALUES (?, ?, ?)",
            ((child_url, kind, url) for child_url, kind in children),
        )
        db.execute(
            "UPDATE hierarchy_queue SET fetched_at = ? WHERE url = ?",
            (datetime.now(timezone.utc).isoformat(), url),
        )


def checkpoint_town(db: sqlite3.Connection, url: str, facts: PageFacts) -> None:
    store_page(db, url, facts)
    with db:
        db.execute(
            "UPDATE hierarchy_queue SET fetched_at = ? WHERE url = ?",
            (datetime.now(timezone.utc).isoformat(), url),
        )


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
    parser.add_argument("--year", choices=("2000", "2012"), default="2012")
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
        "--cdp-endpoint",
        default="http://127.0.0.1:9224",
        help="Chrome DevTools endpoint used only for the authenticated 2000 edition",
    )
    parser.add_argument(
        "--user-agent",
        default="soramimic-wordlists-jpon-feasibility-pilot/0.1",
        help="Descriptive User-Agent; append a contact URL or email when running",
    )
    return parser


def crawl_2000(args: argparse.Namespace, db: sqlite3.Connection) -> None:
    jar = load_cdp_cookie_jar(args.cdp_endpoint)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    enqueue_hierarchy(db, [(YEAR_2000_ROOT, "root")], None)
    completed_towns = 0
    while completed_towns < args.limit:
        queued = next_hierarchy_url(db)
        if queued is None:
            break
        url, kind = queued
        body = fetch(url, args.user_agent, args.timeout, opener=opener).decode("utf-8")
        if kind == "town":
            facts = parse_page(body)
            if facts.sections_seen != {"common", "rare"}:
                raise RuntimeError(f"No surname tables parsed; refusing to checkpoint {url}")
            if facts.conflicting_overlaps:
                names = ", ".join(sorted(facts.conflicting_overlaps)[:5])
                raise RuntimeError(f"Conflicting local counts in common/rare tables at {url}: {names}")
            checkpoint_town(db, url, facts)
            completed_towns += 1
            print(f"[{summary(db)['pages']}] {url} surnames={len(facts.merged)}", flush=True)
        else:
            children = parse_hierarchy_links(body, url)
            if not children:
                raise RuntimeError(f"No next-level 2000 links parsed; refusing to checkpoint {url}")
            checkpoint_index(db, url, children)
            print(f"indexed {url} children={len(children)}", flush=True)

        # The response body has been fully read and the resulting checkpoint committed.
        # Wait here (not before fetch) so slow responses can never overlap requests.
        if completed_towns < args.limit and next_hierarchy_url(db) is not None and args.delay:
            multiplier = random.uniform(1 - args.jitter, 1 + args.jitter)
            time.sleep(args.delay * multiplier)
    export_csv(db, args.output)
    print(summary(db), flush=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit < 1 or args.delay < 0 or not 0 <= args.jitter <= 1:
        raise SystemExit("--limit must be positive; --delay >= 0; --jitter between 0 and 1")
    if args.year == "2000":
        if args.db == DEFAULT_DB:
            args.db = DEFAULT_2000_DB
        if args.output == DEFAULT_CSV:
            args.output = DEFAULT_2000_CSV
        if args.all_shards or args.sitemap:
            raise SystemExit("--all-shards and --sitemap apply only to --year 2012")
        db = init_db(args.db)
        crawl_2000(args, db)
        return 0

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
