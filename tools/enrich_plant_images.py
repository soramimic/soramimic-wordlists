#!/usr/bin/env python3
"""plant.csv(植物の和名)に画像(Wikimedia Commons)を付与する。

QID同定は `enrich_plant_entities.py` に分離する。このスクリプトはCSVに保存済みの
taxon QIDからP18だけを取得し、image/image_pageを埋める。

- QIDは `enrich_plant_entities.py` が種ランク完全一致と植物クレード制約を通して
  保存したものだけを使う。画像取得時に和名からtaxonを逆引きしない
- 確認済み実写は保持する。大分類SVGと科別生成画像は、後日P18が追加されたとき
  実写で上書きする(概念画像→実写は改善方向なので劣化にあたらない)
- 書き出し列は実ファイルのヘッダーに追随する(ADR 00014・00015 と同じ方針)
- ファイル名はカンマ等を含みうるので必ずURLエンコードする(利用側のCSVパーサは
  クオート非対応の素朴な split(",") のため)
- 取得結果はQID単位で CACHE に逐次保存する。中断しても再実行で続きから再開する(引き直したいときは
  `--refresh` かキャッシュ削除)

usage: python3 tools/enrich_plant_images.py [--refresh]
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_class_images import is_class_image, urls as class_image_urls  # noqa: E402
from plant_overrides import is_rejected_p18  # noqa: E402
from wpnames import qids_to_images, write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "plant.csv"
CACHE = Path(__file__).resolve().parent / ".cache" / "plant_images_by_qid.json"
# 書き出し列は実ファイルのヘッダーに追随する。この3列だけは無ければ末尾に足す
OWN_COLS = ["image", "image_page", "wikidata"]

GENERATED_MARKER = "/images/plant/plant_family_"


def load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def is_generated_image(url: str) -> bool:
    return GENERATED_MARKER in (url or "") and url.endswith("_generated.webp")


def needs_photo(row: dict[str, str]) -> bool:
    """QIDがあり、実写未取得の行だけをP18更新対象にする。"""
    image = row.get("image", "")
    return bool(row.get("wikidata") and (
        not image or is_class_image(image) or is_generated_image(image)
    ))


def collect(qids: list[str], refresh: bool) -> dict[str, tuple[str, str]]:
    """保存済みtaxon QIDのP18だけを取得する。"""
    cache = {} if refresh else load_cache()
    todo = [qid for qid in qids if qid not in cache]
    for i in range(0, len(todo), 500):
        chunk = todo[i:i + 500]
        found = qids_to_images(chunk)
        for qid in chunk:
            cache[qid] = list(found.get(qid, ()))
        save_cache(cache)
        print(f"P18取得 {i + len(chunk)}/{len(todo)}", flush=True)
        time.sleep(1)
    return {qid: tuple(value) for qid, value in cache.items() if value}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="キャッシュを無視して対象QIDを引き直す")
    args = ap.parse_args()

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        cols = list(reader.fieldnames)
    cols += [c for c in OWN_COLS if c not in cols]
    for r in rows:
        for c in cols:
            r.setdefault(c, "")

    # 過去にP18として採用した後、実写でないと目視確認されたファイルは、同じ
    # ファイルがキャッシュに残っていても再採用せずclass fallbackへ戻す。
    by_class = class_image_urls("plant", "class-image-v1")
    for r in rows:
        if is_rejected_p18(r["image"]):
            fallback = by_class.get((r.get("class") or "").strip(), by_class["NA"])
            r["image"], r["image_page"] = fallback

    # 実写が既に入っている行は触らない。class SVGと科別生成画像は、後日P18が
    # 追加されたとき実写へ改善できる対象として扱う。
    todo = [r for r in rows if needs_photo(r)]
    qids = sorted({r["wikidata"] for r in todo})
    images = collect(qids, args.refresh)

    filled = 0
    for r in todo:
        found = images.get(r["wikidata"])
        if not found or is_rejected_p18(found[0]):
            continue
        r["image"], r["image_page"] = found
        filled += 1

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    have = sum(1 for r in rows if r["image"] and not is_class_image(r["image"])
               and not is_generated_image(r["image"]))
    print(f"画像を付与: +{filled} (計 {have}/{len(rows)}行に実写画像 "
          f"= {have / len(rows) * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
