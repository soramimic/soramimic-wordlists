#!/usr/bin/env python3
"""画像が空の人物行に、権利的に安全な画像(Wikimedia Commons)を遡及付与する。

対象: baseball / football / scientist。氏名からWikipedia記事を引き、
- 曖昧さ回避ページでない
- 記事冒頭に分野キーワード(野球/サッカー/科学分野)がある(同姓同名の別人ガード)
を満たす場合のみ、Wikidata P18 の画像URLを image/image_page に書き込む。
既存の画像・他の列は一切変更しない。冪等(空欄のみ埋める)。

見つからない場合は「氏名 (野球)」等の曖昧さ回避付きタイトルでも試す。

usage: python3 tools/enrich_images.py [baseball|football|scientist ...]
"""

import csv
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wpnames
from wpnames import UA, WP_API, qids_to_images, write_csv_no_trailing_newline

CONFIGS = {
    "baseball": {
        "csv": "baseball.csv", "keyword": r"野球", "suffixes": [" (野球)"],
    },
    "football": {
        "csv": "football.csv", "keyword": r"サッカー|フットボール",
        "suffixes": [" (サッカー選手)"],
    },
    "scientist": {
        "csv": "scientist.csv",
        "keyword": r"物理|天文|化学|数学|生物|生化学|計算機|情報|地質|地球|科学者|学者",
        "suffixes": [],
    },
}
PAREN = re.compile(r"^(.+?)[((](.+?)[))]$")


def lookup(titles: list, keyword: str) -> dict:
    """タイトル -> QID(曖昧回避でなく、冒頭にキーワードがあるもののみ)"""
    pat = re.compile(keyword)
    result = {}
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        url = WP_API + "?" + urllib.parse.urlencode({
            "action": "query", "prop": "pageprops|extracts",
            "ppprop": "wikibase_item|disambiguation",
            "exintro": 1, "explaintext": 1, "exlimit": "max", "redirects": 1,
            "format": "json", "titles": "|".join(batch)})
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=60) as res:
                    import json
                    data = json.load(res)
                break
            except Exception as ex:
                print(f"retry {attempt}: {ex}", flush=True)
                time.sleep(5 * (attempt + 1))
        else:
            continue
        redir = {r["to"]: r["from"] for r in data["query"].get("redirects", [])}
        for p in data["query"]["pages"].values():
            orig = redir.get(p["title"], p["title"])
            pp = p.get("pageprops", {})
            if "disambiguation" in pp or "wikibase_item" not in pp:
                continue
            if not pat.search(p.get("extract", "")[:300]):
                continue
            result[orig] = pp["wikibase_item"]
        if i % 2000 == 0 and i:
            print(f"  {i}/{len(titles)}", flush=True)
        time.sleep(0.4)
    return result


def enrich(name: str) -> None:
    cfg = CONFIGS[name]
    path = Path(__file__).resolve().parent.parent / cfg["csv"]
    reader = csv.DictReader(path.open(encoding="utf-8"))
    rows = list(reader)
    # 列は実ファイルのヘッダーに追随する(description列等の追加でここが
    # 壊れないように)。image/image_page が無いファイルには列を追加する
    fieldnames = list(reader.fieldnames)
    for c in ("image", "image_page"):
        if c not in fieldnames:
            fieldnames.append(c)
    for r in rows:
        r.setdefault("image", "")
        r.setdefault("image_page", "")

    # 画像が無いグループの代表名(fullのsurface。登録名グループは括弧内の本名)
    groups = {}
    has_image = set()
    for r in rows:
        if r["image"]:
            has_image.add(r["id"])
    for r in rows:
        if r["id"] in has_image or r["id"] in groups:
            continue
        if r["type"] == "full":
            groups[r["id"]] = r["surface"].replace(" ", "").replace("　", "")
        elif r["type"] in ("registered", "register"):
            m = PAREN.match(r["original"])
            if m:
                groups.setdefault(r["id"], m.group(2).replace(" ", ""))
    print(f"{cfg['csv']}: 画像なしグループ {len(groups)}", flush=True)

    # タイトル解決(そのまま -> 曖昧回避サフィックス付き)
    name_to_ids = {}
    for gid, nm in groups.items():
        name_to_ids.setdefault(nm, []).append(gid)
    unresolved = sorted(name_to_ids)
    qid_by_name = {}
    for suffix in [""] + cfg["suffixes"]:
        if not unresolved:
            break
        found = lookup([n + suffix for n in unresolved], cfg["keyword"])
        for title, qid in found.items():
            nm = title[: len(title) - len(suffix)] if suffix else title
            qid_by_name[nm] = qid
        unresolved = [n for n in unresolved if n not in qid_by_name]
        print(f"  解決済み {len(qid_by_name)} (suffix='{suffix}')", flush=True)

    images = qids_to_images(sorted(set(qid_by_name.values())))
    print(f"  画像あり {len(images)}/{len(qid_by_name)}", flush=True)

    filled = 0
    fill_by_id = {}
    for nm, qid in qid_by_name.items():
        if qid not in images:
            continue
        for gid in name_to_ids.get(nm, []):
            fill_by_id[gid] = images[qid]
    for r in rows:
        if not r["image"] and r["id"] in fill_by_id:
            r["image"], r["image_page"] = fill_by_id[r["id"]]
            filled += 1
    write_csv_no_trailing_newline(path, fieldnames, rows)
    print(f"{cfg['csv']}: 画像付与 {len(fill_by_id)}人 ({filled}行)", flush=True)


if __name__ == "__main__":
    targets = sys.argv[1:] or ["baseball", "football", "scientist"]
    for t in targets:
        enrich(t)
