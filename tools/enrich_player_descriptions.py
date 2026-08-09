#!/usr/bin/env python3
"""baseball.csv / football.csv の空の description を Wikipedia から補完する。

同じ選手IDの全表記行には同じ説明を付ける。記事冒頭に競技名がある場合だけ本人の
記事とみなし、既存値は上書きしない。取得結果は逐次キャッシュするため中断後も
続きから再開できる。

usage: python3 tools/enrich_player_descriptions.py
       python3 tools/enrich_player_descriptions.py baseball
       python3 tools/enrich_player_descriptions.py football
       python3 tools/enrich_player_descriptions.py --refresh
"""

import argparse
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import (KATAKANA, api, is_likely_disambiguation_text,
                     make_player_description,
                     write_csv_no_trailing_newline)

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = Path(__file__).resolve().parent / ".cache" / "player_descriptions.json"
CONFIG = {
    "baseball": {
        "path": ROOT / "baseball.csv",
        "keywords": ("野球",),
    },
    "football": {
        "path": ROOT / "football.csv",
        "keywords": ("サッカー", "フットボール"),
    },
}


def article_candidates(kind: str, rows: list[dict[str, str]]) -> list[str]:
    full = next((r["surface"] for r in rows if r["type"] == "full"), "")
    original = rows[0]["original"]
    names = [full, original.split("(", 1)[0]]
    candidates = []
    for name in names:
        name = name.strip()
        if not name:
            continue
        compact = name.replace(" ", "").replace("　", "")
        if kind == "football" and KATAKANA.fullmatch(name):
            candidates.extend((re.sub(r"[ 　]+", "・", name), name))
        else:
            candidates.extend((compact, name))
    return list(dict.fromkeys(c for c in candidates if c))


def load_cache() -> dict[str, dict[str, str]]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_cache(cache: dict[str, dict[str, str]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def fetch_intro_batch(batch: list[str]) -> dict[str, dict[str, str]]:
    data = api({
        "action": "query",
        "prop": "extracts|pageprops",
        "ppprop": "disambiguation",
        "exintro": 1,
        "explaintext": 1,
        "exlimit": "max",
        "redirects": 1,
        "titles": "|".join(batch),
    })
    aliases = {title: title for title in batch}
    for item in data["query"].get("normalized", []):
        for source, target in list(aliases.items()):
            if target == item["from"]:
                aliases[source] = item["to"]
    for item in data["query"].get("redirects", []):
        for source, target in list(aliases.items()):
            if target == item["from"]:
                aliases[source] = item["to"]
    pages = {
        page.get("title", ""): {
            "intro": page.get("extract", ""),
            "disambiguation": "disambiguation" in page.get("pageprops", {}),
        }
        for page in data["query"]["pages"].values()
        if "missing" not in page
    }
    return {
        source: {
            "title": target,
            "intro": pages.get(target, {}).get("intro", ""),
            "disambiguation": pages.get(target, {}).get("disambiguation", False),
        }
        for source, target in aliases.items()
    }


def fetch_intros(titles: list[str], cache: dict[str, dict[str, str]]) -> None:
    missing = [
        title
        for title in titles
        if title not in cache or "disambiguation" not in cache[title]
    ]
    batches = [missing[offset:offset + 20] for offset in range(0, len(missing), 20)]
    completed = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        for result in executor.map(fetch_intro_batch, batches):
            cache.update(result)
            completed += len(result)
            print(f"記事取得: {completed}/{len(missing)}", flush=True)
            save_cache(cache)


def enrich(kind: str, cache: dict[str, dict[str, str]], refresh: bool) -> None:
    config = CONFIG[kind]
    path = config["path"]
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    columns = list(rows[0])
    if "description" not in columns:
        columns.append("description")
    for row in rows:
        row.setdefault("description", "")

    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(row["id"], []).append(row)
    targets = {
        group_id: article_candidates(kind, group_rows)
        for group_id, group_rows in groups.items()
        if refresh or any(not row["description"] for row in group_rows)
    }
    titles = list(dict.fromkeys(
        title for candidates in targets.values() for title in candidates
    ))
    fetch_intros(titles, cache)

    filled_groups = 0
    for group_id, candidates in targets.items():
        intro = title = ""
        for candidate in candidates:
            article = cache.get(candidate, {})
            text = article.get("intro", "")
            if (
                text
                and not article.get("disambiguation")
                and not is_likely_disambiguation_text(text)
                and any(keyword in text for keyword in config["keywords"])
            ):
                intro = text
                title = article.get("title", candidate)
                break
        if not intro:
            continue
        description = make_player_description(intro, title)
        if description == "NA":
            continue
        changed = False
        for row in groups[group_id]:
            if refresh or not row["description"]:
                row["description"] = description
                changed = True
        filled_groups += bool(changed)

    write_csv_no_trailing_newline(path, columns, rows)
    complete = sum(
        all(row["description"] for row in group_rows)
        for group_rows in groups.values()
    )
    print(
        f"{path.name}: description {filled_groups}選手補完、"
        f"{complete}/{len(groups)}選手"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "kind",
        nargs="?",
        choices=(*CONFIG, "all"),
        default="all",
    )
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    cache = load_cache()
    kinds = CONFIG if args.kind == "all" else (args.kind,)
    for kind in kinds:
        enrich(kind, cache, args.refresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
