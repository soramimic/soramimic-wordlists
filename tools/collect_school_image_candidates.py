#!/usr/bin/env python3
"""P18の無い学校について、Commonsカテゴリから実写候補台帳を作る。

Wikidata P373 は対象とCommonsカテゴリの明示的なリンクなので、名称検索より
同名校の誤認が少ない。ただしカテゴリ内のファイルが校舎写真とは限らないため、
このスクリプトはCSVへ自動適用せず、ライセンス情報付きJSONLをレビュー用に出す。

人手レビューは各レコードの ``review`` に記録する。再収集時はこのフィールドを
同じ id / Wikidata QID のレコードへ引き継ぎ、収集対象から外れたレビュー済み
レコードも監査記録として残す。候補を採用する形式は次のとおり。

  "review": {"status": "accepted", "selected_image_page": "https://..."}

usage:
  python3 tools/collect_school_image_candidates.py
  python3 tools/collect_school_image_candidates.py --refresh --limit 100
"""

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_school_type_images import is_school_type_image  # noqa: E402
from wpnames import UA, WD_API, commons_urls  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "school.csv"
CACHE = Path(__file__).resolve().parent / ".cache" / "school_commons_categories"
DEFAULT_OUT = Path(__file__).resolve().parent / "school_image_candidates.jsonl"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WD_WORKERS = 4
COMMONS_WORKERS = 1
COMMONS_INTERVAL = 0.8

ALLOWED_LICENSE = re.compile(r"^(?:CC BY(?:-SA)?|CC0|Public domain)", re.I)
REJECT_FILE = re.compile(
    r"logo|emblem|seal|flag|map|diagram|uniform|poster|pamphlet|"
    r"校章|校旗|校歌|制服|ロゴ|シンボル|地図|案内図|人物|生徒|児童|園児|卒業|入学|運動会",
    re.I,
)
POSITIVE_FILE = re.compile(
    r"school|campus|academy|college|university|kindergarten|校舎|学校|大学|幼稚園|正門|全景",
    re.I,
)
TAG = re.compile(r"<[^>]+>")


def load_previous_records(path: Path) -> list[dict]:
    """既存台帳を読む。不正な台帳を空扱いしてレビューを消さない。"""
    if not path.exists():
        return []
    records = []
    seen = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as ex:
            raise ValueError(f"{path}:{lineno}: JSONが不正: {ex}") from ex
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{lineno}: JSON objectではない")
        key = (str(record.get("id", "")), str(record.get("wikidata", "")))
        if not all(key):
            raise ValueError(f"{path}:{lineno}: id/wikidataが無い")
        if not key[0].isdigit() or not key[1].startswith("Q") or not key[1][1:].isdigit():
            raise ValueError(f"{path}:{lineno}: id/wikidataの形式が不正")
        if key in seen:
            raise ValueError(f"{path}:{lineno}: id/QIDが重複: {key[0]} / {key[1]}")
        seen.add(key)
        records.append(record)
    return records


def merge_review_state(records: list[dict], previous: list[dict]) -> list[dict]:
    """収集結果へレビュー状態を戻し、対象外になったレビュー記録も保持する。"""
    old_by_key = {(str(r["id"]), str(r["wikidata"])): r for r in previous}
    current_keys = set()
    for record in records:
        key = (str(record["id"]), str(record["wikidata"]))
        current_keys.add(key)
        old = old_by_key.get(key)
        if old is not None and "review" in old:
            # 候補一覧は再収集結果を使うが、人が書いた判断はそのまま維持する。
            record["review"] = old["review"]

    # 採用後はCSVが実写扱いになり通常の収集対象から外れる。レビューの根拠を
    # 次回収集で消さないため、そのような既存レコードを台帳に残す。
    records.extend(
        old for key, old in old_by_key.items()
        if key not in current_keys and "review" in old
    )
    records.sort(key=lambda r: (int(r["id"]), str(r["wikidata"])))
    return records


def request_json(url: str, retries: int = 4) -> dict:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as res:
                return json.load(res)
        except Exception as ex:
            if attempt == retries - 1:
                raise
            print(f"retry {attempt + 1}: {ex}", file=sys.stderr, flush=True)
            time.sleep(4 * (attempt + 1))
    return {}


def p373_for_qids(qids: list[str]) -> dict[str, str]:
    """QID -> Commons category名。"""
    cache_path = CACHE.parent / "school_p373.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if all(qid in cached for qid in qids):
            return {qid: cached[qid] for qid in qids if cached[qid]}

    def fetch(batch: list[str]) -> dict[str, str]:
        url = WD_API + "?" + urllib.parse.urlencode({
            "action": "wbgetentities", "ids": "|".join(batch),
            "props": "claims", "format": "json",
        })
        data = request_json(url)
        out = {}
        for qid, entity in data.get("entities", {}).items():
            for claim in entity.get("claims", {}).get("P373", []):
                value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
                if isinstance(value, str) and value:
                    out[qid] = value
                    break
        return out

    batches = [qids[i:i + 50] for i in range(0, len(qids), 50)]
    result = {}
    with ThreadPoolExecutor(max_workers=WD_WORKERS) as pool:
        for found in pool.map(fetch, batches):
            result.update(found)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({qid: result.get(qid, "") for qid in qids},
                                     ensure_ascii=False), encoding="utf-8")
    return result


def clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", value or ""))).strip()


def category_candidates(category: str, max_files: int, refresh: bool) -> list[dict]:
    key = hashlib.sha1(category.encode("utf-8")).hexdigest()[:20]
    cache_path = CACHE / f"{key}.json"
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    # 旧版はURLエンコードしたカテゴリ名をファイル名にしていた。短い既存名だけ再利用。
    legacy_name = urllib.parse.quote(category, safe="") + ".json"
    if len(legacy_name.encode()) < 240 and not refresh:
        legacy_path = CACHE / legacy_name
        if legacy_path.exists():
            data = json.loads(legacy_path.read_text(encoding="utf-8"))
            CACHE.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
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
    out = []
    for page in data.get("query", {}).get("pages", []):
        title = page.get("title", "")
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        license_name = meta.get("LicenseShortName", {}).get("value", "")
        if not ALLOWED_LICENSE.match(license_name):
            continue
        filename = title.removeprefix("File:")
        image_url, image_page = commons_urls(filename)
        rejected = bool(REJECT_FILE.search(filename))
        positive = bool(POSITIVE_FILE.search(filename))
        out.append({
            "file": filename,
            "image": image_url,
            "image_page": image_page,
            "mime": info.get("mime", ""),
            "width": info.get("width", 0),
            "height": info.get("height", 0),
            "license": license_name,
            "artist": clean_html(meta.get("Artist", {}).get("value", "")),
            "description": clean_html(meta.get("ImageDescription", {}).get("value", "")),
            "recommended": positive and not rejected and
                           info.get("width", 0) >= 640 and info.get("height", 0) >= 360,
            "rejected_by_filename": rejected,
        })
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def load_targets() -> dict[str, dict]:
    groups = {}
    with CSV_PATH.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            gid = row["id"]
            group = groups.setdefault(gid, {
                "id": gid, "original": row["original"], "school_type": row["school_type"],
                "prefecture": row["prefecture"], "city": row["city"],
                "wikidata": row.get("wikidata", ""), "has_real": False,
            })
            if row.get("image") and not is_school_type_image(row["image"]):
                group["has_real"] = True
    return {g["wikidata"]: g for g in groups.values()
            if g["wikidata"] and not g["has_real"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=0,
                        help="処理するカテゴリ数。0は全件")
    parser.add_argument("--max-files", type=int, default=20)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    try:
        previous = load_previous_records(args.out)
    except ValueError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2

    targets = load_targets()
    categories = p373_for_qids(sorted(targets))
    items = [(qid, categories[qid]) for qid in sorted(categories)]
    if args.limit:
        items = items[:args.limit]
    print(f"P18なし・QIDあり {len(targets)}校 / P373あり {len(categories)} QID / "
          f"処理 {len(items)}カテゴリ", flush=True)

    records = []
    # Commons APIのレート制限を尊重し、カテゴリ照会は逐次で行う。
    with ThreadPoolExecutor(max_workers=COMMONS_WORKERS) as pool:
        futures = {pool.submit(category_candidates, category, args.max_files,
                               args.refresh): (qid, category)
                   for qid, category in items}
        done = 0
        for future in as_completed(futures):
            qid, category = futures[future]
            candidates = sorted(future.result(), key=lambda c: c.get("image_page", ""))
            school = dict(targets[qid])
            school.update({"commons_category": category, "candidates": candidates})
            records.append(school)
            done += 1
            if done % 50 == 0 or done == len(items):
                print(f"  Commons {done}/{len(items)}カテゴリ", flush=True)

    records = merge_review_state(records, previous)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records),
                        encoding="utf-8")
    with_candidates = sum(bool(r["candidates"]) for r in records)
    recommended = sum(any(c["recommended"] for c in r["candidates"]) for r in records)
    print(f"{args.out}: 候補あり {with_candidates}校 / 推奨候補あり {recommended}校")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
