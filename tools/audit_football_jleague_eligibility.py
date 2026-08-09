#!/usr/bin/env python3
"""候補manifestをJリーグ公式「全選手一覧」と照合する。

公式一覧は再配布せずローカルcacheとしてだけ保持する。照合結果には、同名が一意に
決まった場合のplayer_idと個別ページURLだけを記録する。同名人物が複数いる場合は
生年月日等による本人確認が必要なので、自動的にverifiedにはしない。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html.parser
import io
import json
import re
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

from wpnames import api

ROOT = Path(__file__).resolve().parent.parent
INDEX_URL = "https://data.j-league.or.jp/SFIX03/search"
DETAIL_URL = "https://data.j-league.or.jp/SFIX04/?player_id={}"
DEFAULT_CACHE = ROOT / "tools/.cache/football_jleague_rebuild/jleague_players.html"
DEFAULT_OUTPUT = ROOT / "tools/football_jleague_eligibility.jsonl"
DEFAULT_WIKIPEDIA_CACHE = ROOT / "tools/.cache/football_jleague_rebuild/infobox_names"
PLAYER_ID = re.compile(r"/SFIX04/\?player_id=(\d+)")
PARENS = re.compile(r"\s+[（(][^）)]*[）)]$")
VARIANT = str.maketrans("髙﨑濵濱邉邊瀨栁眞", "高崎浜浜辺辺瀬柳真")
TEAM_ALIASES = {
    "東京V": "東京ヴェルディ1969",
    "C大阪": "セレッソ大阪",
    "千葉": "ジェフユナイテッド市原・千葉",
    "川崎F": "川崎フロンターレ",
    "G大阪": "ガンバ大阪",
    "横浜FM": "横浜F・マリノス",
    "YS横浜": "横浜スポーツ&カルチャークラブ",
    "横浜F": "横浜フリューゲルス",
    "栃木C": "栃木シティFC",
    "滋賀": "レイラック滋賀FC",
}


class PlayerTableParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []
        self.cells: list[str] | None = None
        self.cell: list[str] | None = None
        self.player_id = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        values = dict(attrs)
        if tag == "tr":
            self.cells, self.cell, self.player_id = [], None, ""
        elif tag == "td" and self.cells is not None:
            self.cell = []
        elif tag == "a" and self.cells is not None:
            match = PLAYER_ID.search(values.get("href") or "")
            if match:
                self.player_id = match.group(1)

    def handle_data(self, data: str):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str):
        if tag == "td" and self.cells is not None and self.cell is not None:
            self.cells.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.cells is not None:
            if self.player_id and len(self.cells) >= 6:
                self.rows.append({
                    "player_id": self.player_id,
                    "registered_name": self.cells[0],
                    "english_name": self.cells[1],
                    "last_team": self.cells[2],
                    "position": self.cells[3],
                    "birth_date": self.cells[4],
                })
            self.cells = self.cell = None


def parse_players(source: str) -> list[dict]:
    parser = PlayerTableParser()
    parser.feed(source)
    return parser.rows


def normalized_name(value: str) -> str:
    value = PARENS.sub("", unicodedata.normalize("NFKC", value or ""))
    value = value.translate(VARIANT)
    return re.sub(r"[\s・=＝]", "", value)


def normalized_latin(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(char.lower() for char in decomposed
                   if char.isascii() and char.isalnum())


def latin_compatible(left: str, right: str) -> bool:
    left, right = normalized_latin(left), normalized_latin(right)
    return min(len(left), len(right)) >= 4 and (left in right or right in left)


def candidate_names(record: dict, infobox_names: dict[str, str] | None = None) -> set[str]:
    evidence = record.get("reading_evidence") or {}
    values = (
        record.get("original", ""), record.get("parsed_name", ""),
        record.get("canonical_title", ""), evidence.get("registered_name", ""),
        (infobox_names or {}).get(str(record.get("article", "")), ""),
    )
    return {name for value in values if (name := normalized_name(str(value)))}


def audit(manifest: list[dict], players: list[dict],
          infobox_names: dict[str, str] | None = None) -> list[dict]:
    by_name: dict[str, list[dict]] = defaultdict(list)
    for player in players:
        by_name[normalized_name(player["registered_name"])].append(player)
    by_birth_date: dict[str, list[dict]] = defaultdict(list)
    for player in players:
        if player.get("birth_date"):
            by_birth_date[player["birth_date"]].append(player)
    results = []
    for record in manifest:
        if record.get("status") != "accepted":
            continue
        matches = {
            player["player_id"]: player
            for name in candidate_names(record, infobox_names)
            for player in by_name.get(name, [])
        }
        base = {
            "candidate_id": str(record.get("candidate_id", "")),
            "article": record.get("article", ""),
            "qid": record.get("qid", ""),
            "original": record.get("original", ""),
        }
        if len(matches) == 1:
            player = next(iter(matches.values()))
            method = ("wikipedia_infobox_registered_name"
                      if normalized_name((infobox_names or {}).get(
                          str(record.get("article", "")), "")) in {
                              normalized_name(player["registered_name"])}
                      else "registered_name_exact")
            results.append({
                **base, "status": "verified", "method": method,
                **player, "url": DETAIL_URL.format(player["player_id"]),
            })
        elif matches:
            dated = [player for player in matches.values()
                     if player.get("birth_date") == record.get("birth_date")]
            if len(dated) == 1:
                player = dated[0]
                results.append({
                    **base, "status": "verified",
                    "method": "registered_name_and_birth_date",
                    **player, "url": DETAIL_URL.format(player["player_id"]),
                })
                continue
            results.append({
                **base, "status": "unverified", "reason": "ambiguous_registered_name",
                "matches": [{**p, "url": DETAIL_URL.format(p["player_id"])}
                            for p in matches.values()],
            })
        else:
            identity_matches = {
                player["player_id"]: player
                for player in by_birth_date.get(str(record.get("birth_date", "")), [])
                if any(latin_compatible(player.get("english_name", ""), latin)
                       for latin in record.get("latin_names", []))
            }
            if len(identity_matches) == 1:
                player = next(iter(identity_matches.values()))
                results.append({
                    **base, "status": "verified",
                    "method": "birth_date_and_english_name",
                    **player, "url": DETAIL_URL.format(player["player_id"]),
                })
                continue
            results.append({
                **base, "status": "unverified", "reason": "official_name_not_found",
            })
    return results


def parse_infobox_name(wikitext: str) -> str:
    match = re.search(r"^\s*\|\s*名前\s*=\s*(.+)$", wikitext or "", re.M)
    if not match:
        return ""
    value = re.split(r"<br\s*/?>|<!--", match.group(1), maxsplit=1,
                     flags=re.I)[0]
    value = re.sub(r"'{2,}", "", value).strip()
    if not value or any(token in value for token in ("{{", "[[", "|")):
        return ""
    return value


def fetch_infobox_names(titles: list[str], cache_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    cache_dir.mkdir(parents=True, exist_ok=True)
    for offset in range(0, len(titles), 50):
        batch = titles[offset:offset + 50]
        digest = hashlib.sha256("\0".join(batch).encode()).hexdigest()
        cache = cache_dir / f"{digest}.json"
        if cache.exists():
            found = json.loads(cache.read_text(encoding="utf-8"))
        else:
            data = api({
                "action": "query", "prop": "revisions", "rvprop": "content",
                "rvslots": "main", "rvsection": "0", "redirects": "1",
                "titles": "|".join(batch),
            })
            query = data.get("query", {})
            aliases = {item["from"]: item["to"] for kind in ("normalized", "redirects")
                       for item in query.get(kind, [])}
            pages = {page.get("title", ""): page
                     for page in query.get("pages", {}).values()}
            found = {}
            for title in batch:
                resolved = aliases.get(title, title)
                page = pages.get(resolved, {})
                revisions = page.get("revisions", [])
                text = (revisions[0].get("slots", {}).get("main", {}).get("*", "")
                        if revisions else "")
                found[title] = parse_infobox_name(text)
            temporary = cache.with_suffix(".tmp")
            temporary.write_text(json.dumps(found, ensure_ascii=False), encoding="utf-8")
            temporary.replace(cache)
        result.update(found)
    return result


def load_manifest(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def verified_csv(source: Path, results: list[dict]) -> str:
    verified = {row["candidate_id"] for row in results
                if row["status"] == "verified" and row.get("candidate_id") != ""}
    evidence = {row["candidate_id"]: row for row in results
                if row["status"] == "verified"}
    with source.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = [row for row in reader if row.get("id") in verified]
    old_ids = list(dict.fromkeys(row["id"] for row in rows))
    new_ids = {old: str(index) for index, old in enumerate(old_ids)}
    for row in rows:
        old_id = row["id"]
        if "team" in fields:
            row["team"] = representative_team(
                row.get("team", ""), evidence[old_id].get("last_team", ""))
        if "position" in fields and not row.get("position"):
            row["position"] = evidence[old_id].get("position", "")
        row["id"] = new_ids[old_id]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().rstrip("\n")


def representative_team(candidate_teams: str, official_last_team: str) -> str:
    abbreviation = unicodedata.normalize("NFKC", official_last_team or "")
    teams = [team for team in candidate_teams.split("-") if team]
    explicit = TEAM_ALIASES.get(abbreviation)
    if explicit and explicit in teams:
        return explicit
    matches = [team for team in teams
               if abbreviation and abbreviation in unicodedata.normalize("NFKC", team)]
    if len(matches) == 1:
        return matches[0]
    return explicit or official_last_team or (teams[-1] if teams else "")


def verified_id_mapping(source: Path, results: list[dict]) -> dict[str, str]:
    verified = {row["candidate_id"] for row in results
                if row["status"] == "verified" and row.get("candidate_id") != ""}
    with source.open(encoding="utf-8", newline="") as stream:
        old_ids = list(dict.fromkeys(
            row["id"] for row in csv.DictReader(stream) if row.get("id") in verified))
    return {old: str(index) for index, old in enumerate(old_ids)}


def public_source_record(row: dict) -> dict:
    """再配布する根拠は人物キー・照合方法・個別URLだけに限定する。"""
    fields = ("verified_id", "original", "article", "qid", "player_id", "method", "url")
    return {field: row.get(field, "") for field in fields}


def fetch_index(cache: Path, refresh: bool) -> str:
    if cache.exists() and not refresh:
        return cache.read_text(encoding="utf-8")
    request = urllib.request.Request(INDEX_URL, headers={
        "User-Agent": "soramimic-wordlists/1.0 (J League eligibility audit)",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        source = response.read().decode("utf-8")
    cache.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache.with_suffix(cache.suffix + ".tmp")
    temporary.write_text(source, encoding="utf-8")
    temporary.replace(cache)
    return source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--verified-candidates", type=Path,
                        help="一意照合できた候補だけを再採番して出力する")
    parser.add_argument("--verified-manifest", type=Path,
                        help="確定候補だけを再採番後のid付きJSONLで出力する")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--no-wikipedia-infobox", action="store_true")
    parser.add_argument("--fail-on-unverified", action="store_true")
    args = parser.parse_args(argv)
    players = parse_players(fetch_index(args.cache, args.refresh))
    if not 9000 <= len(players) <= 12000:
        raise SystemExit(f"unexpected J League player count: {len(players)}")
    manifest = load_manifest(args.manifest)
    infobox_names = {}
    if not args.no_wikipedia_infobox:
        preliminary = audit(manifest, players)
        unresolved = {row["article"] for row in preliminary
                      if row.get("reason") == "official_name_not_found"}
        infobox_names = fetch_infobox_names(
            [str(row.get("article", "")) for row in manifest
             if row.get("article") in unresolved], DEFAULT_WIKIPEDIA_CACHE)
    results = audit(manifest, players, infobox_names)
    id_mapping = (verified_id_mapping(args.candidates, results)
                  if args.candidates else {})
    for row in results:
        if row["status"] == "verified" and row.get("candidate_id") in id_mapping:
            row["verified_id"] = id_mapping[row["candidate_id"]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True)
                  for row in results) + "\n", encoding="utf-8")
    if args.verified_candidates:
        if not args.candidates:
            parser.error("--verified-candidates requires --candidates")
        args.verified_candidates.parent.mkdir(parents=True, exist_ok=True)
        args.verified_candidates.write_text(
            verified_csv(args.candidates, results), encoding="utf-8")
    if args.verified_manifest:
        if not args.candidates:
            parser.error("--verified-manifest requires --candidates")
        args.verified_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.verified_manifest.write_text(
            "\n".join(json.dumps(public_source_record(row), ensure_ascii=False,
                                 sort_keys=True)
                      for row in results if row["status"] == "verified") + "\n",
            encoding="utf-8")
    verified = sum(row["status"] == "verified" for row in results)
    print(f"J公式 {len(players)}人 / 候補 {len(results)}人 / 一意照合 {verified}人 / "
          f"要確認 {len(results) - verified}人")
    return int(args.fail_on_unverified and verified != len(results))


if __name__ == "__main__":
    raise SystemExit(main())
