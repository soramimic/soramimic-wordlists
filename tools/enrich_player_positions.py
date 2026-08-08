#!/usr/bin/env python3
"""baseball.csv / football.csv の空の position をロースターとWikidataで補完する。

現役選手はWikipedia日本語版のロースターテンプレートを優先し、歴代選手は
Wikidataの選手のポジション(P413)を使う。既存値は上書きしない。

usage: python3 tools/enrich_player_positions.py
       python3 tools/enrich_player_positions.py baseball
       python3 tools/enrich_player_positions.py football
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_baseball import TEAMS, roster
from update_football import club_players, j_clubs
from wpnames import UA, WD_API, api, vnorm, write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = Path(__file__).resolve().parent / ".cache" / "player_positions.json"
BATCH = 50
KINDS = ("baseball", "football")
POSITION_ORDER = {
    "baseball": ("投手", "捕手", "内野手", "外野手"),
    "football": ("GK", "DF", "MF", "FW"),
}
POSITION_OVERRIDES = {
    "baseball": {
        "王貞治": "内野手",
    },
    "football": {
        "長友佑都": "DF",
        "吉田麻也": "DF",
        "朴智星": "MF",
        "マラドーナ": "MF",
        "リネカー": "FW",
        "ラウドルップ": "MF",
    },
}


def load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"titles": {}, "claims": {}, "labels": {}, "rosters": {}}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def key_of(name: str) -> str:
    return vnorm(re.sub(r"[ 　・]", "", name))


def candidates(name: str) -> list[str]:
    base = name.split("(", 1)[0].strip()
    return list(dict.fromkeys((
        base,
        base.replace(" ", "").replace("　", ""),
        re.sub(r"[ 　]+", "・", base),
    )))


def title_key(kind: str, name: str) -> str:
    return f"{kind}:{name}"


def wd_entities(qids: list[str], props: str) -> dict:
    url = WD_API + "?" + urllib.parse.urlencode({
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": props,
        "languages": "ja|en",
        "format": "json",
    })
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response).get("entities", {})
        except Exception as ex:
            print(f"retry {attempt}: {ex}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("wikidata api failed")


def fetch_roster(kind: str, cache: dict) -> dict[str, str]:
    if kind in cache["rosters"]:
        return cache["rosters"][kind]
    result = {}
    if kind == "baseball":
        for team in TEAMS:
            for article, _display, position in roster(team):
                if position:
                    result[key_of(article)] = position
            time.sleep(0.3)
    else:
        for club in j_clubs():
            for article, (_display, position) in club_players(club).items():
                if position:
                    result[key_of(article)] = position
            time.sleep(0.3)
    cache["rosters"][kind] = result
    save_cache(cache)
    return result


def resolve_title_batch(names: list[str]) -> dict[str, str]:
    title_list = list(dict.fromkeys(
        title for name in names for title in candidates(name)
    ))
    data = api({
        "action": "query",
        "prop": "pageprops",
        "ppprop": "wikibase_item|disambiguation",
        "redirects": 1,
        "titles": "|".join(title_list),
    })
    aliases = {title: title for title in title_list}
    for item in data["query"].get("normalized", []):
        for source, target in list(aliases.items()):
            if target == item["from"]:
                aliases[source] = item["to"]
    for item in data["query"].get("redirects", []):
        for source, target in list(aliases.items()):
            if target == item["from"]:
                aliases[source] = item["to"]
    pages = {}
    for page in data["query"]["pages"].values():
        props = page.get("pageprops", {})
        if "disambiguation" not in props and props.get("wikibase_item"):
            pages[page["title"]] = props["wikibase_item"]
    found = {source: pages.get(target, "") for source, target in aliases.items()}
    return {
        name: next(
            (found[title] for title in candidates(name) if found.get(title)),
            "",
        )
        for name in names
    }


def resolve_titles(kind: str, names: list[str], cache: dict) -> None:
    todo = [name for name in names if title_key(kind, name) not in cache["titles"]]
    batches = [todo[offset:offset + 15] for offset in range(0, len(todo), 15)]
    completed = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        for result in executor.map(resolve_title_batch, batches):
            for name, qid in result.items():
                cache["titles"][title_key(kind, name)] = qid
            completed += len(result)
            save_cache(cache)
            print(f"記事→QID: {completed}/{len(todo)}", flush=True)


def fetch_claims(qids: list[str], cache: dict) -> None:
    todo = [qid for qid in qids if qid and qid not in cache["claims"]]
    batches = [todo[offset:offset + BATCH] for offset in range(0, len(todo), BATCH)]
    completed = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        for chunk, entities in zip(
            batches, executor.map(lambda batch: wd_entities(batch, "claims"), batches)
        ):
            for qid in chunk:
                claims = entities.get(qid, {}).get("claims", {}).get("P413", [])
                cache["claims"][qid] = [
                    claim["mainsnak"]["datavalue"]["value"]["id"]
                    for claim in claims
                    if claim.get("rank") != "deprecated"
                    and claim.get("mainsnak", {}).get("datavalue")
                ]
            completed += len(chunk)
            save_cache(cache)
            print(f"ポジション(P413): {completed}/{len(todo)}", flush=True)


def fetch_labels(qids: list[str], cache: dict) -> None:
    todo = [qid for qid in qids if qid and qid not in cache["labels"]]
    batches = [todo[offset:offset + BATCH] for offset in range(0, len(todo), BATCH)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        for chunk, entities in zip(
            batches, executor.map(lambda batch: wd_entities(batch, "labels"), batches)
        ):
            for qid in chunk:
                labels = entities.get(qid, {}).get("labels", {})
                cache["labels"][qid] = (
                    labels.get("ja") or labels.get("en") or {}
                ).get("value", "")
            save_cache(cache)


def canonical_positions(kind: str, labels: list[str]) -> str:
    text = " / ".join(labels).lower()
    if kind == "baseball":
        matches = {
            "投手": ("投手", "pitcher"),
            "捕手": ("捕手", "catcher"),
            "内野手": (
                "内野手", "infielder", "baseman", "shortstop",
                "designated hitter",
            ),
            "外野手": (
                "外野手", "outfielder", "left fielder", "right fielder",
                "center fielder", "centre fielder",
            ),
        }
    else:
        matches = {
            "GK": ("ゴールキーパー", "goalkeeper"),
            "DF": (
                "ディフェンダー", "defender", "centre-back", "center-back",
                "full-back", "sweeper",
            ),
            "MF": ("ミッドフィールダー", "midfielder"),
            "FW": ("フォワード", "forward", "striker", "winger"),
        }
    found = [
        position for position in POSITION_ORDER[kind]
        if any(term in text for term in matches[position])
    ]
    return "/".join(found)


def enrich(kind: str, cache: dict) -> None:
    path = ROOT / f"{kind}.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    columns = list(rows[0])
    if "position" not in columns:
        index = columns.index("description") if "description" in columns else len(columns)
        columns.insert(index, "position")
    for row in rows:
        row.setdefault("position", "")

    groups = {}
    for row in rows:
        groups.setdefault(row["id"], []).append(row)
    names = {
        group_id: next(
            (row["surface"] for row in group if row["type"] == "full"),
            group[0]["original"],
        )
        for group_id, group in groups.items()
        if any(not row["position"] for row in group)
    }
    roster_positions = fetch_roster(kind, cache)
    unresolved = [
        name for name in names.values() if key_of(name) not in roster_positions
    ]
    resolve_titles(kind, list(dict.fromkeys(unresolved)), cache)
    qids = list(dict.fromkeys(
        cache["titles"].get(title_key(kind, name), "") for name in unresolved
    ))
    fetch_claims(qids, cache)
    position_qids = list(dict.fromkeys(
        position_qid
        for qid in qids
        for position_qid in cache["claims"].get(qid, [])
    ))
    fetch_labels(position_qids, cache)

    filled = 0
    for group_id, name in names.items():
        position = (
            POSITION_OVERRIDES[kind].get(key_of(name))
            or roster_positions.get(key_of(name), "")
        )
        if not position:
            qid = cache["titles"].get(title_key(kind, name), "")
            labels = [
                cache["labels"].get(position_qid, "")
                for position_qid in cache["claims"].get(qid, [])
            ]
            position = canonical_positions(kind, labels)
        if not position:
            continue
        changed = False
        for row in groups[group_id]:
            if not row["position"]:
                row["position"] = position
                changed = True
        filled += bool(changed)

    write_csv_no_trailing_newline(path, columns, rows)
    complete = sum(
        all(row["position"] for row in group) for group in groups.values()
    )
    print(f"{path.name}: position {filled}選手補完、{complete}/{len(groups)}選手")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", nargs="?", choices=(*KINDS, "all"), default="all")
    args = parser.parse_args()
    cache = load_cache()
    kinds = KINDS if args.kind == "all" else (args.kind,)
    for kind in kinds:
        enrich(kind, cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
