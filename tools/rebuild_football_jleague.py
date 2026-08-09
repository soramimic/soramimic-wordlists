#!/usr/bin/env python3
"""Jリーグ在籍経験者のレビュー用 football 候補CSVを生成する。

日本語版Wikipediaの各クラブ「Category:<クラブ>の選手」を母集団とする。
カテゴリ所属時期とクラブのJリーグ在籍時期は照合しないため、収録結果は確定版
ではなく候補である。football.csv は読みも書きもしない。

ネットワーク結果は段階ごとにキャッシュされ、中断後も再開できる。manifestには
候補ごとのQID、出典、クラブ/カテゴリ根拠、採否理由をJSONLで記録する。

usage:
  python3 tools/rebuild_football_jleague.py --dry-run
  python3 tools/rebuild_football_jleague.py --output /tmp/football-candidates.csv \
      --manifest /tmp/football-candidates.jsonl --resume
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_football import j_clubs  # noqa: E402
from wpnames import (DISAMBIG, KATAKANA, api, commons_urls,  # noqa: E402
                     make_player_description, parse_person)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "tools" / "football_jleague_candidates.csv"
DEFAULT_MANIFEST = ROOT / "tools" / "football_jleague_candidates.jsonl"
DEFAULT_CACHE = ROOT / "tools" / ".cache" / "football_jleague_rebuild"
# TextExtractsは通常利用者の場合、警告なしに21件目以降のextractを省く。
PAGE_BATCH_SIZE = 20
DEFAULT_WORKERS = 3

# 現加盟一覧だけでは拾えない旧・消滅クラブ。改称クラブは原則として現在の
# Categoryに歴代選手が集約されるが、Wikipedia側のcategory名が異なるものは
# aliasを明記する。値は「Category:」を除いた完全なcategory名。
FORMER_CLUB_CATEGORIES: dict[str, tuple[str, ...]] = {
    "横浜フリューゲルス": ("横浜フリューゲルスの選手",),
    # J3からJFLへ降格したクラブも「在籍経験者」の母集団に残す。
    "横浜スポーツ&カルチャークラブ": ("横浜スポーツ&カルチャークラブの選手",),
}
CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {
    "ザスパ群馬": ("ザスパクサツ群馬の選手",),
}

CSV_COLUMNS = [
    "id", "original", "team", "surface", "pronunciation", "type",
    "category", "scope", "wikidata", "image", "image_page", "position",
    "description",
]
PLAYER_WORD = re.compile(r"(?:サッカー|フットボール)選手")
UNSAFE_CSV = re.compile(r'[,"\r\n]')
PRON_ASCII = re.compile(r"[A-Za-z]{2,}")
POSITION_PATTERNS = (
    ("GK", re.compile(r"ゴールキーパー|(?<![A-Z])GK(?![A-Z])", re.I)),
    ("DF", re.compile(r"ディフェンダー|(?<![A-Z])DF(?![A-Z])", re.I)),
    ("MF", re.compile(r"ミッドフィールダー|(?<![A-Z])MF(?![A-Z])", re.I)),
    ("FW", re.compile(r"フォワード|(?<![A-Z])FW(?![A-Z])", re.I)),
)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class JsonCache:
    """小さいJSON応答をリクエスト単位で保存する再開可能キャッシュ。"""

    def __init__(self, directory: Path, refresh: bool = False):
        self.directory = directory
        self.refresh = refresh

    def get(self, namespace: str, key: str, build: Callable[[], object]):
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        path = self.directory / namespace / f"{digest}.json"
        if path.exists() and not self.refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        value = build()
        _atomic_text(path, json.dumps(value, ensure_ascii=False, sort_keys=True))
        return value


class ReadingProvider(Protocol):
    """読み取得provider。Jリーグ公式fallbackはこのinterfaceへ追加できる。"""

    name: str

    def resolve(self, article: str, intro: str):
        """parse_person互換の7要素tuple、またはNoneを返す。"""


class WikipediaIntroReadingProvider:
    name = "ja.wikipedia.org:intro"

    def __init__(self):
        self.evidence: dict = {}

    def resolve(self, article: str, intro: str):
        parsed = parse_person(article, intro)
        self.evidence = {
            "provider": self.name,
            "method": "wikipedia_intro",
            "status": "verified" if parsed else "unverified",
            "registered_name": parsed[6] if parsed else None,
            "resolved_reading": parsed[5] if parsed else None,
        }
        return parsed


class CachedReadingProvider:
    def __init__(self, provider: ReadingProvider, cache: JsonCache):
        self.provider = provider
        self.cache = cache
        self.name = provider.name
        self.evidence: dict = {}

    def resolve(self, article: str, intro: str):
        key = f"{self.provider.name}\0{article}\0{intro}"

        def build() -> dict:
            parsed = self.provider.resolve(article, intro)
            return {
                "parsed": list(parsed or []),
                "evidence": dict(getattr(self.provider, "evidence", {})),
            }

        value = self.cache.get(
            "readings-v2", key, build,
        )
        self.evidence = dict(value.get("evidence", {}))
        parsed = value.get("parsed", [])
        return tuple(parsed) if parsed else None


class FallbackReadingProvider:
    """順番にproviderを試す。将来のJリーグ公式fallback用の差込口。"""

    def __init__(self, providers: list[ReadingProvider]):
        if not providers:
            raise ValueError("at least one reading provider is required")
        self.providers = providers
        self.name = " -> ".join(provider.name for provider in providers)
        self.resolved_by = ""
        self.evidence: dict = {}

    def resolve(self, article: str, intro: str):
        self.resolved_by = ""
        self.evidence = {}
        for provider in self.providers:
            value = provider.resolve(article, intro)
            self.evidence = dict(getattr(provider, "evidence", {}))
            if value is not None:
                self.resolved_by = provider.name
                return value
        return None


class WikipediaClient:
    def __init__(self, cache: JsonCache, workers: int = DEFAULT_WORKERS):
        self.cache = cache
        self.workers = workers

    def current_clubs(self) -> list[str]:
        # 母集団の現加盟クラブ定義は既存update_footballと共有する。
        return list(self.cache.get("clubs", "j_clubs-v1", j_clubs))

    def category_members(self, category: str) -> dict:
        def build() -> dict:
            category_title = "Category:" + category
            metadata = api({
                "action": "query", "prop": "categoryinfo",
                "redirects": "1", "titles": category_title,
            })
            pages = metadata.get("query", {}).get("pages", {})
            page = next(iter(pages.values()), {})
            if "missing" in page:
                return {"exists": False, "category": category, "members": []}
            resolved_title = page.get("title", category_title)
            members: list[str] = []
            cont: dict[str, str] = {}
            while True:
                data = api({
                    "action": "query", "list": "categorymembers",
                    "cmtitle": resolved_title,
                    "cmnamespace": "0", "cmtype": "page", "cmlimit": "max",
                    **cont,
                })
                members.extend(
                    m["title"].strip()
                    for m in data.get("query", {}).get("categorymembers", [])
                )
                if "continue" not in data:
                    break
                cont = data["continue"]
                time.sleep(0.2)
            return {
                "exists": True,
                "category": resolved_title.removeprefix("Category:"),
                "members": sorted(set(members)),
            }

        return dict(self.cache.get("categories-v2", category, build))

    def pages(self, titles: list[str]) -> dict[str, dict]:
        batches = [titles[i:i + PAGE_BATCH_SIZE]
                   for i in range(0, len(titles), PAGE_BATCH_SIZE)]

        def fetch(batch: list[str]) -> dict[str, dict]:
            key = "\0".join(batch)

            def build() -> dict:
                data = api({
                    "action": "query", "prop": "extracts|pageprops|pageimages",
                    "ppprop": "wikibase_item|disambiguation", "exintro": "1",
                    "explaintext": "1", "exlimit": "max", "piprop": "name",
                    "redirects": "1", "maxlag": "5",
                    "titles": "|".join(batch),
                })
                query = data.get("query", {})
                aliases = {
                    item["from"]: item["to"]
                    for kind in ("normalized", "redirects")
                    for item in query.get(kind, [])
                }
                page_by_title = {
                    page.get("title", ""): page
                    for page in query.get("pages", {}).values()
                }

                def resolved(title: str) -> str:
                    seen = set()
                    while title in aliases and title not in seen:
                        seen.add(title)
                        title = aliases[title]
                    return title

                out = {}
                for requested in batch:
                    page = page_by_title.get(resolved(requested), {})
                    props = page.get("pageprops", {})
                    out[requested] = {
                        "canonical_title": page.get("title", ""),
                        "extract": page.get("extract", ""),
                        "qid": props.get("wikibase_item", ""),
                        "disambiguation": "disambiguation" in props,
                        "pageimage": page.get("pageimage", ""),
                        "missing": "missing" in page,
                    }
                return out

            return dict(self.cache.get("pages-v2", key, build))

        result: dict[str, dict] = {}
        # 20件上限を守りつつ少数並列にする。pool.mapは入力順なので結果も決定的。
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for found in pool.map(fetch, batches):
                result.update(found)
        return result


@dataclass(frozen=True)
class Evidence:
    club: str
    category: str


def club_categories(current_clubs: list[str]) -> dict[str, tuple[str, ...]]:
    result = {}
    for club in current_clubs:
        result[club] = CATEGORY_ALIASES.get(club, (f"{club}の選手",))
    result.update(FORMER_CLUB_CATEGORIES)
    return result


def infer_position(intro: str) -> str:
    # ポジション周辺を優先し、記事中の所属クラブ略称などの誤検出を抑える。
    chunks = re.findall(r"(?:ポジション|守備位置)[^。]{0,80}", intro)
    haystack = " ".join(chunks)
    found = [code for code, pattern in POSITION_PATTERNS if pattern.search(haystack)]
    return "/".join(found)


def registered_name_from_intro(intro: str) -> str:
    """記事冒頭に明記された登録名・通称だけを取り出す（推測はしない）。"""
    patterns = (
        r"^\s*([^（(、。]{1,40})\s*[（(][^）)]{1,100}[）)]\s*こと[、,]",
        r"(?:Jリーグでの)?登録名(?:は|[:：])\s*[「『]?([^」』、。（(]{1,40})",
    )
    for pattern in patterns:
        match = re.search(pattern, intro)
        if match:
            value = match.group(1).strip(" 「」『』")
            if KATAKANA.fullmatch(value.replace(" ", "")):
                return value
    return ""


def standalone_description(name: str, description: str) -> str:
    """文脈を失った接続語で始まる実績文に主語を補う。"""
    for prefix in ("うち、", "また、"):
        if description.startswith(prefix):
            return f"{name}は、{description[len(prefix):]}"
    return description


def clean_player_card_description(description: str) -> str:
    """カードの専用行と重複する所属・ポジション文をdescriptionから除く。"""
    sentences = [part.strip() for part in description.split("。") if part.strip()]
    kept = []
    for sentence in sentences:
        # 「選手（ポジションはFW）、指導者」のような括弧だけを先に除く。
        sentence = re.sub(
            r"[（(](?:現役時代の)?(?:ポジション|守備位置)\s*(?:は|[:：])[^）)]*[）)]",
            "", sentence).strip()
        # 独立したポジション文はカードのposition行と完全に重複する。
        if re.match(r"^(?:現役時代の)?(?:ポジション|守備位置)\s*(?:は|[:：])", sentence):
            continue
        # 「元選手でポジションはMF」のように人物属性と同じ文にある末尾節を除く。
        sentence = re.sub(
            r"(?:で[、,]?|[、,]\s*|\s+)?(?:現役時代の)?"
            r"(?:ポジション|守備位置)\s*(?:は|[:：])[^。]*$", "", sentence).strip()
        sentence = sentence.rstrip("、, ")
        if sentence.endswith("で"):
            sentence = sentence[:-1]
        # 現在所属だけの文もteam行と重複し、更新時に古くなりやすい。
        if (re.search(r"所属(?:している)?$", sentence)
                and "代表" not in sentence):
            continue
        if sentence:
            kept.append(sentence)
    return "。".join(kept) + ("。" if kept else "")


def identity_fields_from_intro(intro: str) -> tuple[str, list[str]]:
    """公式との本人照合用に生年月日と記事記載のラテン文字名を取り出す。"""
    born = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", intro[:500])
    birth_date = (f"{born.group(1)}/{int(born.group(2)):02d}/{int(born.group(3)):02d}"
                  if born else "")
    latin_names = []
    for value in re.findall(r"[（(]([^）)]*[A-Za-z][^）)]*)[）)]", intro[:500]):
        value = value.split("、", 1)[0].strip()
        if value and value not in latin_names:
            latin_names.append(value)
    return birth_date, latin_names


def rows_for_person(next_id: int, article: str, parsed, teams: list[str],
                    page: dict) -> list[dict]:
    f_s, f_y, g_s, g_y, full_s, full_y, _registered = parsed
    if KATAKANA.match(full_s.replace(" ", "")):
        original = full_s
        specs = [(full_s, full_y.replace("・", " "), "full")]
        if f_s:
            specs.extend([(full_s, f_y, "family"), (full_s, g_y, "given")])
    else:
        original = f"{f_s} {g_s}"
        specs = [
            (original, f"{f_y} {g_y}", "full"),
            (f_s, f_y, "family"), (g_s, g_y, "given"),
        ]
    image = image_page = ""
    if page.get("pageimage"):
        image, image_page = commons_urls(page["pageimage"])
    description = clean_player_card_description(standalone_description(
        full_s, make_player_description(page.get("extract", ""), article)))
    position = infer_position(page.get("extract", ""))
    return [{
        "id": str(next_id), "original": original, "team": "-".join(teams),
        "surface": surface, "pronunciation": pronunciation, "type": typ,
        "category": "player", "scope": "jleague",
        "wikidata": page.get("qid", ""), "image": image, "image_page": image_page,
        "position": position, "description": description,
    } for surface, pronunciation, typ in specs]


def unsafe_row_reason(rows: list[dict]) -> str:
    """downstreamの非RFC CSVパーサで壊れる値を採用前に検出する。"""
    for row in rows:
        for column, value in row.items():
            if UNSAFE_CSV.search(str(value)):
                return f"unsafe_csv_character:{column}"
        if PRON_ASCII.search(row["pronunciation"]):
            return "ascii_in_pronunciation"
        if not row["id"] or not row["original"] or not row["surface"]:
            return "missing_required_csv_field"
    return ""


def collect(client: WikipediaClient, reading_provider: ReadingProvider,
            limit: int | None = None) -> tuple[list[dict], list[dict], list[str]]:
    clubs = client.current_clubs()
    if not 50 <= len(clubs) <= 100:
        raise RuntimeError(f"implausible current J1-J3 club count: {len(clubs)}")
    evidence_by_title: dict[str, list[Evidence]] = {}
    missing_categories = []
    for club, categories in club_categories(clubs).items():
        for category in categories:
            response = client.category_members(category)
            if not response.get("exists"):
                missing_categories.append(category)
                continue
            resolved_category = response.get("category", category)
            for title in response.get("members", []):
                evidence = Evidence(club, resolved_category)
                if evidence not in evidence_by_title.setdefault(title, []):
                    evidence_by_title[title].append(evidence)
    titles = sorted(evidence_by_title)
    if limit is not None:
        titles = titles[:limit]
    pages = client.pages(titles)
    rows: list[dict] = []
    manifest: list[dict] = []
    seen_people: set[str] = set()
    next_id = 0
    for title in titles:
        page = pages.get(title, {})
        intro = page.get("extract", "")
        ev = evidence_by_title[title]
        canonical_title = page.get("canonical_title", title)
        person_name = DISAMBIG.sub("", canonical_title)
        record = {
            "article": title,
            "canonical_title": canonical_title,
            "parsed_name": person_name,
            "qid": page.get("qid", ""),
            "source": "https://ja.wikipedia.org/wiki/" + urllib.parse.quote(
                title.replace(" ", "_"), safe=""),
            "evidence": [{
                "type": "wikipedia_category_membership",
                "club": item.club,
                "category": "Category:" + item.category,
                "membership_period_verified": False,
            } for item in ev],
            "eligibility_status": "unverified",
            "reading_provider": reading_provider.name,
        }
        birth_date, latin_names = identity_fields_from_intro(intro)
        record["birth_date"] = birth_date
        record["latin_names"] = latin_names
        if page.get("missing") or not intro:
            record.update(status="rejected", reason="missing_article_or_intro")
        elif page.get("disambiguation"):
            record.update(status="rejected", reason="disambiguation")
        elif not PLAYER_WORD.search(intro):
            record.update(status="rejected", reason="not_a_football_player")
        else:
            parsed = reading_provider.resolve(person_name, intro)
            record["reading_provider"] = getattr(
                reading_provider, "resolved_by", "") or reading_provider.name
            record["reading_evidence"] = dict(
                getattr(reading_provider, "evidence", {}))
            record["reading_evidence"].setdefault("source", record["source"])
            registered_alias = registered_name_from_intro(intro)
            if registered_alias:
                record["reading_evidence"]["registered_name"] = registered_alias
                record["reading_evidence"]["registered_name_method"] = (
                    "wikipedia_intro_explicit_alias")
            if parsed is None:
                record.update(status="unverified", reason="reading_unparsed")
            else:
                identity = page.get("qid") or canonical_title
                if identity in seen_people:
                    record.update(status="rejected", reason="duplicate_person")
                else:
                    teams = list(dict.fromkeys(item.club for item in ev))
                    person_rows = rows_for_person(
                        next_id, person_name, parsed, teams, page)
                    unsafe = unsafe_row_reason(person_rows)
                    if unsafe:
                        record.update(status="rejected", reason=unsafe)
                    else:
                        rows.extend(person_rows)
                        seen_people.add(identity)
                        record.update(
                            status="accepted", reason="wikipedia_intro_parsed",
                            candidate_id=str(next_id),
                            original=person_rows[0]["original"], teams=teams,
                            position=person_rows[0]["position"],
                            image=person_rows[0]["image"],
                            image_source=record["source"],
                        )
                        next_id += 1
        manifest.append(record)
    return rows, manifest, missing_categories


def csv_text(rows: list[dict]) -> str:
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    text = buf.getvalue().rstrip("\n")
    if '"' in text:
        raise ValueError("quoted CSV field would break the downstream naive parser")
    return text


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--dry-run", action="store_true",
                        help="収集・検証だけ行いoutput/manifestを書かない")
    parser.add_argument("--resume", action="store_true",
                        help="既存キャッシュを再利用する（通常動作も安全に再利用する）")
    parser.add_argument("--refresh", action="store_true",
                        help="キャッシュを無視して再取得する")
    parser.add_argument("--limit", type=int, help="テスト実行用の記事数上限")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="Wikipedia記事APIの並列数（1〜4、既定3）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit is not None and args.limit < 0:
        print("error: --limit must be non-negative", file=sys.stderr)
        return 2
    if not 1 <= args.workers <= 4:
        print("error: --workers must be between 1 and 4", file=sys.stderr)
        return 2
    if args.resume and args.refresh:
        print("error: --resume and --refresh are mutually exclusive", file=sys.stderr)
        return 2
    cache = JsonCache(args.cache_dir, refresh=args.refresh)
    client = WikipediaClient(cache, workers=args.workers)
    provider = FallbackReadingProvider([
        CachedReadingProvider(WikipediaIntroReadingProvider(), cache),
        # Jリーグ公式reading providerは全件HTMLコピーをせず、ここへ追加する。
    ])
    try:
        rows, manifest, missing = collect(client, provider, args.limit)
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    accepted = sum(item["status"] == "accepted" for item in manifest)
    print(f"候補記事 {len(manifest)} / 採用 {accepted}人 / CSV {len(rows)}行")
    if missing:
        print("カテゴリ欠損: " + ", ".join(sorted(missing)), file=sys.stderr)
    if args.dry_run:
        print("dry-run: output/manifestは書きません")
        return 0
    _atomic_text(args.output, csv_text(rows))
    manifest_text = "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True)
                               for item in manifest)
    _atomic_text(args.manifest, manifest_text)
    print(f"output: {args.output}")
    print(f"manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
