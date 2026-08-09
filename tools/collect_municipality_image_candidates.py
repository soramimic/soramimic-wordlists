#!/usr/bin/env python3
"""画像の無い自治体について、Commonsカテゴリから実写候補台帳を作る。

municipality.csv で image が全表層とも空の自治体のうち、Wikidata P373 が
明示するCommonsカテゴリだけを探索する。校章・旗・地図・人物などを除外し、
再利用可能ライセンスの画像をレビュー用JSONLへ出す。CSVへは適用しない。

レビュー形式は学校候補台帳と共通で、再収集しても保持される。

  "review": {"status": "accepted", "selected_image_page": "https://..."}

usage:
  python3 tools/collect_municipality_image_candidates.py
  python3 tools/collect_municipality_image_candidates.py --limit 20
  python3 tools/collect_municipality_image_candidates.py --refresh
"""

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_school_image_candidates import (  # noqa: E402
    ALLOWED_LICENSE,
    COMMONS_API,
    clean_html,
    load_previous_records,
    merge_review_state,
    request_json,
)
from wpnames import WD_API, commons_urls  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "municipality.csv"
CACHE_ROOT = Path(__file__).resolve().parent / ".cache"
CATEGORY_CACHE = CACHE_ROOT / "municipality_commons_categories"
P373_CACHE = CACHE_ROOT / "municipality_p373.json"
DEFAULT_OUT = Path(__file__).resolve().parent / "municipality_image_candidates.jsonl"
WD_WORKERS = 4
COMMONS_WORKERS = 1
COMMONS_INTERVAL = 0.8

# ファイル名だけで明らかに自治体の代表実写ではないものを落とす。英語圏で
# よく使われる coat of arms / locator map と、日本語名の双方を対象にする。
REJECT_FILE = re.compile(
    r"logo|emblem|seal|flag|banner|coat[ _-]?of[ _-]?arms|crest|symbol|"
    r"map|locator|location|diagram|route|boundary|mayor|governor|portrait|"
    r"people|persons?|crowd|ceremony|election|assembly|council|festival|"
    r"parade|poster|pamphlet|"
    r"市章|区章|町章|村章|紋章|市旗|区旗|町旗|村旗|旗|シンボル|ロゴ|"
    r"地図|位置図|路線図|境界|首長|市長|区長|町長|村長|知事|議員|議会|"
    r"人物|集合写真|群衆|式典|祭り|選挙|ポスター|パンフレット",
    re.I,
)
POSITIVE_FILE = re.compile(
    r"city|town|village|municipality|ward|city[ _-]?hall|town[ _-]?hall|"
    r"village[ _-]?hall|municipal[ _-]?(?:hall|office|building)|"
    r"landscape|cityscape|streetscape|panorama|aerial|view|"
    r"市役所|区役所|町役場|村役場|庁舎|街並|町並|風景|全景|遠景|空撮",
    re.I,
)


def p373_for_qids(qids: list[str], refresh: bool = False) -> dict[str, str]:
    """QID -> Commonsカテゴリ名。空値もキャッシュして再照会を避ける。"""
    if P373_CACHE.exists() and not refresh:
        cached = json.loads(P373_CACHE.read_text(encoding="utf-8"))
        if all(qid in cached for qid in qids):
            return {qid: cached[qid] for qid in qids if cached[qid]}

    def fetch(batch: list[str]) -> dict[str, str]:
        url = WD_API + "?" + urllib.parse.urlencode({
            "action": "wbgetentities", "ids": "|".join(batch),
            "props": "claims", "format": "json",
        })
        data = request_json(url)
        found = {qid: "" for qid in batch}
        for qid, entity in data.get("entities", {}).items():
            for claim in entity.get("claims", {}).get("P373", []):
                value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
                if isinstance(value, str) and value:
                    found[qid] = value
                    break
        return found

    batches = [qids[i:i + 50] for i in range(0, len(qids), 50)]
    result = {}
    with ThreadPoolExecutor(max_workers=WD_WORKERS) as pool:
        for found in pool.map(fetch, batches):
            result.update(found)
    P373_CACHE.parent.mkdir(parents=True, exist_ok=True)
    P373_CACHE.write_text(
        json.dumps({qid: result.get(qid, "") for qid in sorted(qids)},
                   ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return {qid: result[qid] for qid in qids if result.get(qid)}


def category_candidates(category: str, max_files: int,
                        refresh: bool = False) -> list[dict]:
    key = hashlib.sha1(category.encode("utf-8")).hexdigest()[:20]
    cache_path = CATEGORY_CACHE / f"{key}.json"
    if cache_path.exists() and not refresh:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return sorted(cached, key=lambda c: c.get("image_page", ""))

    params = {
        "action": "query", "generator": "categorymembers",
        "gcmtitle": "Category:" + category, "gcmtype": "file",
        "gcmlimit": str(max_files), "prop": "imageinfo",
        "iiprop": "mime|size|extmetadata", "format": "json",
        "formatversion": "2",
    }
    try:
        data = request_json(COMMONS_API + "?" + urllib.parse.urlencode(params))
    except Exception as ex:
        print(f"warn: Commons Category:{category}: {ex}", file=sys.stderr, flush=True)
        return []
    time.sleep(COMMONS_INTERVAL)

    candidates = []
    for page in data.get("query", {}).get("pages", []):
        title = page.get("title", "")
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        license_name = meta.get("LicenseShortName", {}).get("value", "")
        if not ALLOWED_LICENSE.match(license_name):
            continue
        filename = title.removeprefix("File:")
        mime = info.get("mime", "")
        description = clean_html(
            meta.get("ImageDescription", {}).get("value", "")
        )
        # SVG/PDFは校章や地図が中心で「実写」ではない。ファイル名だけでなく
        # Commonsの説明文にも明示された除外対象を落とす。
        if mime not in {"image/jpeg", "image/png", "image/webp", "image/tiff"}:
            continue
        if REJECT_FILE.search(filename + " " + description):
            continue
        image, image_page = commons_urls(filename)
        width, height = info.get("width", 0), info.get("height", 0)
        candidates.append({
            "file": filename,
            "image": image,
            "image_page": image_page,
            "mime": mime,
            "width": width,
            "height": height,
            "license": license_name,
            "artist": clean_html(meta.get("Artist", {}).get("value", "")),
            "description": description,
            "recommended": bool(POSITIVE_FILE.search(filename)) and
                           width >= 640 and height >= 360,
        })
    candidates.sort(key=lambda c: c["image_page"])
    CATEGORY_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(candidates, ensure_ascii=False, sort_keys=True),
                          encoding="utf-8")
    return candidates


def load_targets(path: Path = CSV_PATH) -> dict[str, dict]:
    """全表層で画像が空の自治体だけを QID -> 自治体情報にまとめる。"""
    groups = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            gid = row["id"]
            group = groups.setdefault(gid, {
                "id": gid,
                "original": row["original"],
                "prefecture": row.get("prefecture", ""),
                "parent": row.get("parent", ""),
                "status": row.get("status", ""),
                "wikidata": row.get("wikidata", ""),
                "has_image": False,
            })
            if row.get("wikidata", "") != group["wikidata"]:
                raise ValueError(f"{path}: id {gid} のQIDが表層間で不一致")
            if row.get("image"):
                group["has_image"] = True
    return {g["wikidata"]: g for g in groups.values()
            if g["wikidata"] and not g["has_image"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=0,
                        help="処理するカテゴリ数。0は全件")
    parser.add_argument("--max-files", type=int, default=20)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)

    try:
        previous = load_previous_records(args.out)
        targets = load_targets()
        categories = p373_for_qids(sorted(targets), args.refresh)
    except (OSError, ValueError, json.JSONDecodeError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2

    items = [(qid, categories[qid]) for qid in sorted(categories)]
    if args.limit:
        items = items[:args.limit]
    print(f"画像なし・QIDあり {len(targets)}自治体 / P373あり {len(categories)} QID / "
          f"処理 {len(items)}カテゴリ", flush=True)

    records = []
    with ThreadPoolExecutor(max_workers=COMMONS_WORKERS) as pool:
        futures = {
            pool.submit(category_candidates, category, args.max_files,
                        args.refresh): (qid, category)
            for qid, category in items
        }
        done = 0
        for future in as_completed(futures):
            qid, category = futures[future]
            municipality = dict(targets[qid])
            municipality.update({
                "commons_category": category,
                "candidates": future.result(),
            })
            records.append(municipality)
            done += 1
            if done % 50 == 0 or done == len(items):
                print(f"  Commons {done}/{len(items)}カテゴリ", flush=True)

    records = merge_review_state(records, previous)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records),
        encoding="utf-8",
    )
    with_candidates = sum(bool(r.get("candidates")) for r in records)
    recommended = sum(any(c.get("recommended") for c in r.get("candidates", []))
                      for r in records)
    print(f"{args.out}: 候補あり {with_candidates}自治体 / "
          f"推奨候補あり {recommended}自治体")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
