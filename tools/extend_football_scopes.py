#!/usr/bin/env python3
"""football.csv に海外日本人・世界的著名選手の候補を非破壊で追加する。

既存のJリーグ確認済み行を ``scope=jleague`` として最優先し、次にWikidataで
海外クラブだけへの所属が検証できる日本人、最後に日本語記事と一定数以上の
sitelinkを持つ世界のサッカー選手を追加する。入力CSVは決して上書きしない。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rebuild_football_jleague import (  # noqa: E402
    CachedReadingProvider, FallbackReadingProvider, JsonCache,
    WikipediaClient, WikipediaIntroReadingProvider, infer_position,
    clean_player_card_description, rows_for_person, standalone_description,
    unsafe_row_reason,
)
from wpnames import DISAMBIG, UA, WD_API, make_player_description, sparql  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "football.csv"
DEFAULT_JLEAGUE_MANIFEST = ROOT / "tools" / "football_jleague_verified_sources.jsonl"
DEFAULT_OUTPUT = ROOT / "tools" / "football_scoped_candidates.csv"
DEFAULT_MANIFEST = ROOT / "tools" / "football_scoped_candidates.jsonl"
DEFAULT_CACHE = ROOT / "tools" / ".cache" / "football_scope_extension"
DEFAULT_WORLD_MIN_SITELINKS = 80
CSV_COLUMNS = [
    "id", "original", "team", "surface", "pronunciation", "type",
    "category", "scope", "wikidata", "image", "image_page", "position",
    "description",
]
PLAYER_WORD = re.compile(r"(?:サッカー|フットボール)選手")


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def normalize_person(value: str) -> str:
    return re.sub(r"[\s・=＝()（）・]", "", DISAMBIG.sub("", value)).casefold()


def first_sentence_is_player(intro: str) -> bool:
    """記事の第1文自体がサッカー選手本人を定義している場合だけ通す。"""
    first = intro.strip().split("。", 1)[0]
    if not first or not PLAYER_WORD.search(first):
        return False
    subject, separator, predicate = first.partition("は")
    if not separator or not subject.strip() or len(subject) > 180:
        return False
    if re.search(r"(?:一覧|カテゴリ|クラブ|チーム)$", subject.strip()):
        return False
    # 「サッカー選手を扱う一覧」のように単語だけ含む非人物記事を除く。
    return not re.search(r"(?:一覧|カテゴリ|クラブ|チーム)(?:である)?$", predicate.strip())


def load_input(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"id", "original", "team", "surface", "pronunciation", "type",
                "category", "image", "image_page", "position", "description"}
    missing = required - set(rows[0] if rows else [])
    if missing:
        raise ValueError("input CSV missing columns: " + ", ".join(sorted(missing)))
    return rows


def load_jleague_qids(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        row_id = str(item.get("verified_id", item.get("candidate_id", item.get("id", ""))))
        qid = str(item.get("qid", ""))
        if row_id and qid:
            result.setdefault(row_id, qid)
    return result


def enrich_jleague_rows(rows: list[dict], qids: dict[str, str]) -> list[dict]:
    return [{**row, "scope": "jleague", "wikidata": qids.get(row["id"], ""),
             "description": clean_player_card_description(row["description"])}
            for row in rows]


class CandidateSource(Protocol):
    def famous_candidates(self, minimum_sitelinks: int) -> list[dict]: ...
    def overseas_japanese_candidates(self) -> list[dict]: ...
    def latest_teams(self, qids: list[str]) -> dict[str, str]: ...


def classify_club_countries(memberships: dict[str, dict]) -> dict:
    """P54のうちサッカークラブだけを評価し、型欠損は安全側へ倒す。"""
    domestic, foreign, unknown, ignored_non_clubs = [], [], [], []
    for entity, facts in memberships.items():
        countries = facts.get("countries", set())
        if facts.get("is_football_club"):
            if not countries:
                unknown.append(entity)
            elif "Q17" in countries:
                domestic.append(entity)
            else:
                foreign.append(entity)
        elif facts.get("is_national_team"):
            # 明示的なサッカー代表チームだけをクラブ歴の判定対象外にする。
            ignored_non_clubs.append(entity)
        else:
            # 女子クラブ等はQ476028配下として型付けされていないことがある。
            # 「何らかの型がある」だけで代表扱いせず、安全側へ倒す。
            unknown.append(entity)
    domestic.sort()
    foreign.sort()
    unknown.sort()
    ignored_non_clubs.sort()
    if domestic:
        status, reason = "rejected", "domestic_club_history"
    elif unknown:
        status, reason = "unverified", "club_country_incomplete"
    elif not foreign:
        status, reason = "rejected", "no_foreign_club"
    else:
        status, reason = "eligible", "all_club_countries_verified_non_japan"
    return {"eligibility_status": status, "eligibility_reason": reason,
            "domestic_clubs": domestic, "foreign_clubs": foreign,
            "unknown_memberships": unknown,
            "ignored_non_club_memberships": ignored_non_clubs}


class WikidataClient:
    def __init__(self, cache: JsonCache):
        self.cache = cache

    def famous_candidates(self, minimum_sitelinks: int) -> list[dict]:
        def build() -> list[dict]:
            query = """
SELECT ?item ?article ?sitelinks WHERE {
  ?item wdt:P106 wd:Q937857 ; wikibase:sitelinks ?sitelinks .
  ?article schema:about ?item ; schema:isPartOf <https://ja.wikipedia.org/> .
  FILTER(?sitelinks >= $MINIMUM)
}
ORDER BY DESC(?sitelinks) ?item
""".replace("$MINIMUM", str(minimum_sitelinks))
            bindings = sparql(query).get("results", {}).get("bindings", [])
            return [{
                "qid": row["item"]["value"].rsplit("/", 1)[-1],
                "title": urllib.parse.unquote(row["article"]["value"].rsplit("/", 1)[-1]).replace("_", " "),
                "sitelinks": int(row["sitelinks"]["value"]),
            } for row in bindings]
        key = f"famous-footballers-ja-sitelinks-{minimum_sitelinks}-v2"
        return list(self.cache.get("wikidata", key, build))

    def overseas_japanese_candidates(self) -> list[dict]:
        """全P54の国が判明し、国内クラブ歴がない日本国籍選手だけをeligibleにする。

        P54の型・国が1件でも安全に分類できない人物はWikipedia本文から国内歴を
        否定できないため、manifestへ残す ``unverified`` 候補とする。
        """
        def build() -> list[dict]:
            query = """
SELECT ?item ?article ?club ?clubCountry ?membershipType ?isFootballClub ?isNationalTeam WHERE {
  ?item wdt:P31 wd:Q5 ;
        wdt:P106 wd:Q937857 ;
        wdt:P27 wd:Q17 ;
        wdt:P54 ?club .
  ?article schema:about ?item ; schema:isPartOf <https://ja.wikipedia.org/> .
  OPTIONAL { ?club wdt:P17 ?clubCountry . }
  OPTIONAL { ?club wdt:P31 ?membershipType . }
  OPTIONAL {
    ?club wdt:P31/wdt:P279* wd:Q476028 .
    BIND("1" AS ?isFootballClub)
  }
  OPTIONAL {
    ?club wdt:P31/wdt:P279* wd:Q6979593 .
    BIND("1" AS ?isNationalTeam)
  }
  FILTER EXISTS {
    ?item wdt:P54 ?foreignClub .
    ?foreignClub wdt:P17 ?foreignCountry .
    FILTER(?foreignCountry != wd:Q17)
  }
  FILTER NOT EXISTS {
    ?item wdt:P1532 ?sportNationality .
    FILTER(?sportNationality != wd:Q17)
  }
}
ORDER BY ?item ?club
"""
            bindings = sparql(query).get("results", {}).get("bindings", [])
            grouped: dict[str, dict] = {}
            for row in bindings:
                qid = row["item"]["value"].rsplit("/", 1)[-1]
                item = grouped.setdefault(qid, {
                    "qid": qid,
                    "title": urllib.parse.unquote(
                        row["article"]["value"].rsplit("/", 1)[-1]).replace("_", " "),
                    "memberships": {},
                })
                club = row["club"]["value"].rsplit("/", 1)[-1]
                membership = item["memberships"].setdefault(
                    club, {"countries": set(), "types": set(),
                           "is_football_club": False, "is_national_team": False})
                if row.get("clubCountry"):
                    membership["countries"].add(
                        row["clubCountry"]["value"].rsplit("/", 1)[-1])
                if row.get("membershipType"):
                    membership["types"].add(
                        row["membershipType"]["value"].rsplit("/", 1)[-1])
                if row.get("isFootballClub"):
                    membership["is_football_club"] = True
                if row.get("isNationalTeam"):
                    membership["is_national_team"] = True
            result = []
            for item in grouped.values():
                memberships = item.pop("memberships")
                result.append({**item, **classify_club_countries(memberships)})
            return sorted(result, key=lambda item: item["title"])
        return list(self.cache.get(
            "wikidata", "overseas-japanese-footballers-club-p54-countries-v4", build))

    def _entities(self, qids: list[str], props: str) -> dict:
        result: dict = {}
        for offset in range(0, len(qids), 50):
            batch = qids[offset:offset + 50]
            key = props + "\0" + "\0".join(batch)

            def build(batch=batch) -> dict:
                url = WD_API + "?" + urllib.parse.urlencode({
                    "action": "wbgetentities", "format": "json", "ids": "|".join(batch),
                    "props": props, "languages": "ja",
                })
                request = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(request, timeout=90) as response:
                    return json.load(response).get("entities", {})

            result.update(self.cache.get("entities-v1", key, build))
            time.sleep(0.1)
        return result

    @staticmethod
    def _statement_score(statement: dict) -> tuple:
        qualifiers = statement.get("qualifiers", {})
        def time_value(prop: str) -> str:
            try:
                return qualifiers[prop][0]["datavalue"]["value"]["time"]
            except (KeyError, IndexError, TypeError):
                return ""
        # 終了日のない所属を現所属として最優先。その後は時点・開始・終了の新しさ。
        return (
            1 if "P582" not in qualifiers else 0,
            1 if statement.get("rank") == "preferred" else 0,
            max(time_value("P585"), time_value("P580"), time_value("P582")),
        )

    def latest_teams(self, qids: list[str]) -> dict[str, str]:
        people = self._entities(qids, "claims")
        chosen: dict[str, str] = {}
        for qid in qids:
            statements = people.get(qid, {}).get("claims", {}).get("P54", [])
            valid = []
            for statement in statements:
                value = statement.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                club_qid = value.get("id") if isinstance(value, dict) else None
                if club_qid:
                    valid.append((self._statement_score(statement), club_qid))
            if valid:
                chosen[qid] = max(valid)[1]
        labels = self._entities(sorted(set(chosen.values())), "labels") if chosen else {}
        return {
            qid: labels.get(club_qid, {}).get("labels", {}).get("ja", {}).get("value", "")
            for qid, club_qid in chosen.items()
        }


def collect(existing_rows: list[dict], jleague_qids: dict[str, str],
            wiki: WikipediaClient, wd: CandidateSource, reading_provider,
            limit: int | None = None,
            world_min_sitelinks: int = DEFAULT_WORLD_MIN_SITELINKS,
            ) -> tuple[list[dict], list[dict]]:
    output = enrich_jleague_rows(existing_rows, jleague_qids)
    manifest: list[dict] = []
    used_qids = set(filter(None, jleague_qids.values()))
    used_people = {normalize_person(row["original"]) for row in existing_rows}

    overseas = wd.overseas_japanese_candidates()
    overseas_by_title = {item["title"]: item for item in overseas}
    overseas_titles = sorted(overseas_by_title)
    famous = wd.famous_candidates(world_min_sitelinks)
    famous_by_title = {item["title"]: item for item in famous}
    all_titles = list(dict.fromkeys(overseas_titles + sorted(famous_by_title)))
    if limit is not None:
        # 記事APIを全件取得した後で切らず、ネットワーク試験も小さく保つ。
        all_titles = all_titles[:limit]
    pages = wiki.pages(all_titles)

    # 同一人物が両方に現れる場合は overseas_japanese を world より優先する。
    overseas_qids = {item.get("qid", "") for item in overseas}
    overseas_people = {
        normalize_person(pages.get(title, {}).get("canonical_title", title))
        for title in overseas_titles
    }
    candidates: list[tuple[str, str, dict, dict]] = []
    for title in all_titles:
        page = pages.get(title, {})
        qid = page.get("qid", "") or famous_by_title.get(title, {}).get("qid", "")
        person_key = normalize_person(page.get("canonical_title", title))
        if title in overseas_titles:
            scope = "overseas_japanese"
            source_eligibility = overseas_by_title[title]
        elif qid in overseas_qids or person_key in overseas_people:
            continue
        else:
            scope = "world"
            source_eligibility = {
                "eligibility_status": "eligible",
                "eligibility_reason": "notability_threshold_met",
                "sitelinks": famous_by_title.get(title, {}).get("sitelinks"),
            }
        candidates.append((scope, title, {**page, "qid": qid}, source_eligibility))
    candidates.sort(key=lambda item: (0 if item[0] == "overseas_japanese" else 1, item[1]))
    team_by_qid = wd.latest_teams(sorted({p[2].get("qid", "") for p in candidates if p[2].get("qid")}))

    next_id = max((int(row["id"]) for row in existing_rows), default=-1) + 1
    for scope, title, page, source_eligibility in candidates:
        canonical = page.get("canonical_title", title)
        person_name = DISAMBIG.sub("", canonical)
        qid = page.get("qid", "")
        identity = qid or normalize_person(canonical)
        source = "https://ja.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="")
        eligibility = ({
            "type": "wikidata_overseas_japanese_query",
            "status": source_eligibility["eligibility_status"],
            "reason": source_eligibility["eligibility_reason"],
            "citizenship": "Q17",
            "occupation": "Q937857",
            "domestic_clubs": source_eligibility.get("domestic_clubs", []),
            "foreign_clubs": source_eligibility.get("foreign_clubs", []),
            "unknown_memberships": source_eligibility.get("unknown_memberships", []),
            "ignored_non_club_memberships": source_eligibility.get(
                "ignored_non_club_memberships", []),
        } if scope == "overseas_japanese" else {
            "type": "wikidata_notability_query",
            "status": "eligible",
            "reason": "notability_threshold_met",
            "occupation": "Q937857",
            "minimum_sitelinks": world_min_sitelinks,
            "sitelinks": famous_by_title.get(title, {}).get("sitelinks"),
        })
        record = {"article": title, "canonical_title": canonical, "qid": qid,
                  "scope": scope, "source": source, "eligibility": eligibility}
        if qid in used_qids or normalize_person(person_name) in used_people:
            record.update(status="rejected", reason="already_in_jleague_or_duplicate")
        elif eligibility["status"] != "eligible":
            record.update(status=eligibility["status"], reason=eligibility["reason"])
        elif page.get("missing") or not page.get("extract"):
            record.update(status="rejected", reason="missing_article_or_intro")
        elif page.get("disambiguation"):
            record.update(status="rejected", reason="disambiguation")
        elif not first_sentence_is_player(page["extract"]):
            record.update(status="rejected", reason="first_sentence_not_player_subject")
        else:
            parsed = reading_provider.resolve(person_name, page["extract"])
            record["reading_provider"] = getattr(reading_provider, "resolved_by", "") or reading_provider.name
            record["reading_evidence"] = dict(getattr(reading_provider, "evidence", {}))
            if parsed is None:
                record.update(status="unverified", reason="reading_unparsed")
            elif identity in used_qids or normalize_person(person_name) in used_people:
                record.update(status="rejected", reason="duplicate_person")
            else:
                team = team_by_qid.get(qid, "")
                person_rows = rows_for_person(next_id, person_name, parsed, [team] if team else [], page)
                for row in person_rows:
                    row["scope"] = scope
                    row["wikidata"] = qid
                    # rows_for_personのdescriptionを明示的に同じ公開helperで生成する。
                    row["description"] = clean_player_card_description(
                        standalone_description(
                            parsed[4], make_player_description(
                                page["extract"], person_name)))
                    row["position"] = infer_position(page["extract"])
                unsafe = unsafe_row_reason(person_rows)
                if unsafe:
                    record.update(status="rejected", reason=unsafe)
                else:
                    output.extend(person_rows)
                    if qid:
                        used_qids.add(qid)
                    used_people.add(normalize_person(person_name))
                    record.update(status="accepted", reason="wikipedia_intro_parsed",
                                  candidate_id=str(next_id), original=person_rows[0]["original"],
                                  team=team, position=person_rows[0]["position"])
                    next_id += 1
        manifest.append(record)
    return output, manifest


def csv_text(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    text = buf.getvalue().rstrip("\n")
    if '"' in text:
        raise ValueError("quoted CSV field would break the downstream naive parser")
    return text


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--jleague-manifest", type=Path, default=DEFAULT_JLEAGUE_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--world-min-sitelinks", type=int,
                        default=DEFAULT_WORLD_MIN_SITELINKS)
    parser.add_argument("--workers", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit is not None and args.limit < 0:
        print("error: --limit must be non-negative", file=sys.stderr)
        return 2
    if args.world_min_sitelinks < 1:
        print("error: --world-min-sitelinks must be positive", file=sys.stderr)
        return 2
    if args.resume and args.refresh:
        print("error: --resume and --refresh are mutually exclusive", file=sys.stderr)
        return 2
    if not 1 <= args.workers <= 4:
        print("error: --workers must be between 1 and 4", file=sys.stderr)
        return 2
    try:
        existing = load_input(args.input)
        qids = load_jleague_qids(args.jleague_manifest)
        cache = JsonCache(args.cache_dir, refresh=args.refresh)
        wiki = WikipediaClient(cache, workers=args.workers)
        wd = WikidataClient(cache)
        provider = FallbackReadingProvider([
            CachedReadingProvider(WikipediaIntroReadingProvider(), cache),
        ])
        rows, manifest = collect(existing, qids, wiki, wd, provider, args.limit,
                                 args.world_min_sitelinks)
        text = csv_text(rows)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    accepted = sum(item["status"] == "accepted" for item in manifest)
    unverified = sum(item["status"] == "unverified" for item in manifest)
    print(f"既存 {len(existing)}行 / 追加 {accepted}人 / 読み未確認 {unverified}人 / 合計 {len(rows)}行")
    if args.dry_run:
        print("dry-run: output/manifestは書きません")
        return 0
    _atomic_text(args.output, text)
    _atomic_text(args.manifest, "\n".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True) for item in manifest))
    print(f"output: {args.output}")
    print(f"manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
