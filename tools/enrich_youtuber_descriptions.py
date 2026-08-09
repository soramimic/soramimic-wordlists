#!/usr/bin/env python3
"""youtuber.csv の description を活動内容中心の短文に更新する。

通常の自動更新は既存行を劣化させないため空欄補完だけを行う。このスクリプトは
説明文の基準を変更したときに明示的に全件を再生成するためのキュレーション用で、
同じ original の family/given/full 行には同じ説明を付ける。

usage: python3 tools/enrich_youtuber_descriptions.py --refresh
"""

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import api, write_csv_no_trailing_newline  # noqa: E402
from yt_common import make_youtuber_description  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "youtuber.csv"
CACHE_PATH = Path(__file__).resolve().parent / ".cache" / "youtuber_descriptions.json"
WIKIDATA_CACHE = Path(__file__).resolve().parent / ".cache" / "youtuber_wikidata.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8")


def fetch_intro_batch(titles: list[str]) -> dict[str, str]:
    data = api({
        "action": "query", "prop": "extracts", "exintro": 1,
        "explaintext": 1, "exlimit": "max", "redirects": 1,
        "titles": "|".join(titles),
    })
    aliases = {title: title for title in titles}
    for item in data["query"].get("normalized", []):
        for source, target in list(aliases.items()):
            if target == item["from"]:
                aliases[source] = item["to"]
    for item in data["query"].get("redirects", []):
        for source, target in list(aliases.items()):
            if target == item["from"]:
                aliases[source] = item["to"]
    pages = {
        page.get("title", ""): page.get("extract", "")
        for page in data["query"]["pages"].values()
        if "missing" not in page
    }
    return {source: pages.get(target, "") for source, target in aliases.items()}


def fetch_intros(titles: list[str], cache: dict[str, str], refresh: bool) -> None:
    missing = titles if refresh else [title for title in titles if title not in cache]
    batches = [missing[offset:offset + 20]
               for offset in range(0, len(missing), 20)]
    if not batches:
        return
    with ThreadPoolExecutor(max_workers=8) as executor:
        for number, result in enumerate(executor.map(fetch_intro_batch, batches), 1):
            cache.update(result)
            save_json(CACHE_PATH, cache)
            print(f"記事取得: {min(number * 20, len(missing))}/{len(missing)}",
                  flush=True)


def title_by_original(rows: list[dict[str, str]]) -> dict[str, str]:
    """既存行のQIDから、曖昧さ回避語を含む正確な記事タイトルを戻す。"""
    wd = load_json(WIKIDATA_CACHE)
    qid_title = {
        item["qid"]: item["title"]
        for items in wd.values()
        for item in items
        if item.get("qid") and item.get("title")
    }
    result = {}
    for row in rows:
        original = row["original"]
        qid = row.get("wikidata", "")
        result.setdefault(original, qid_title.get(qid, original))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh", action="store_true",
        help="既存の説明文も含めてWikipedia冒頭を再取得して更新する",
    )
    args = parser.parse_args()

    with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        columns = list(reader.fieldnames or [])
    if "description" not in columns:
        columns.append("description")
    for row in rows:
        row.setdefault("description", "")

    titles = title_by_original(rows)
    cache = load_json(CACHE_PATH)
    fetch_intros(sorted(set(titles.values())), cache, args.refresh)

    descriptions = {}
    for original, title in titles.items():
        description = make_youtuber_description(
            cache.get(title, ""), "", original)
        if description != "NA" or args.refresh:
            # 明示的な再生成では、記事が短すぎて安全な説明を作れない行も
            # 古い冗長・未完の説明を残さず NA に揃える。
            descriptions[original] = description

    changed = 0
    changed_people = set()
    for row in rows:
        new = descriptions.get(row["original"])
        if new is not None and row.get("description") != new:
            row["description"] = new
            changed += 1
            changed_people.add(row["original"])

    write_csv_no_trailing_newline(CSV_PATH, columns, rows)
    values = [row.get("description", "") for row in rows]
    print(f"youtuber.csv: description {len(changed_people)}人/{changed}行を更新")
    print(f"文字数: <=50字 {sum(len(v) <= 50 for v in values)}, "
          f"51-65字 {sum(51 <= len(v) <= 65 for v in values)}, "
          f">65字 {sum(len(v) > 65 for v in values)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
