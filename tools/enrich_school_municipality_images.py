#!/usr/bin/env python3
"""school.csv / municipality.csv に Commons 画像を遡及付与する。

両CSVに既に入っている Wikidata QID から P18(画像)を取得し、同じ id の
全表層へ image / image_page を付ける。既存画像は変更せず、画像が1行もない
グループだけを対象にするため冪等。

usage: python3 tools/enrich_school_municipality_images.py [school|municipality ...]
"""

import csv
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_school_type_images import is_school_type_image  # noqa: E402
from wpnames import qids_to_images, write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TARGETS = {"school", "municipality"}
WORKERS = 4
CHUNK_SIZE = 500


def image_columns(fieldnames: list[str]) -> list[str]:
    """image列を wikidata の直前に追加する(既にあれば列順を保つ)。"""
    cols = list(fieldnames)
    for col in ("image", "image_page"):
        if col in cols:
            continue
        pos = cols.index("wikidata") if "wikidata" in cols else len(cols)
        cols.insert(pos, col)
    return cols


def collect_images(qids: list[str], property_id: str = "P18") -> dict:
    """Wikidata APIを少数並列で照会し、進捗を表示する。"""
    chunks = [qids[i:i + CHUNK_SIZE] for i in range(0, len(qids), CHUNK_SIZE)]
    images = {}
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(qids_to_images, chunk, property_id): len(chunk)
                   for chunk in chunks}
        for future in as_completed(futures):
            images.update(future.result())
            done += futures[future]
            print(f"  Wikidata {property_id} {done}/{len(qids)} QID", flush=True)
    return images


def enrich(name: str) -> None:
    path = ROOT / f"{name}.csv"
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        cols = image_columns(list(reader.fieldnames or []))

    # 学校の校種別イメージは実写が見つかったら置き換えてよい。その他の既存画像は保護。
    has_image = {r["id"] for r in rows
                 if r.get("image") and not (name == "school" and
                                             is_school_type_image(r["image"]))}
    qid_by_id = {}
    for row in rows:
        gid, qid = row["id"], row.get("wikidata", "")
        if gid not in has_image and qid:
            qid_by_id.setdefault(gid, qid)

    qids = sorted(set(qid_by_id.values()))
    print(f"{name}.csv: 画像なし・QIDあり {len(qid_by_id)}件", flush=True)
    images = collect_images(qids)
    map_count = 0
    if name == "municipality":
        # 写真(P18)が無い自治体は、Wikidataが明示する位置図(P242)で補完する。
        remaining = [qid for qid in qids if qid not in images]
        maps = collect_images(remaining, "P242")
        map_count = len(maps)
        images.update(maps)
    by_id = {gid: images[qid] for gid, qid in qid_by_id.items() if qid in images}

    filled_rows = 0
    for row in rows:
        row.setdefault("image", "")
        row.setdefault("image_page", "")
        replaceable = not row["image"] or (name == "school" and
                                            is_school_type_image(row["image"]))
        if replaceable and row["id"] in by_id:
            row["image"], row["image_page"] = by_id[row["id"]]
            filled_rows += 1

    write_csv_no_trailing_newline(path, cols, rows)
    suffix = f"、うち位置図 {map_count}件" if name == "municipality" else ""
    print(f"{name}.csv: 画像付与 {len(by_id)}件 ({filled_rows}行){suffix}", flush=True)


def main() -> int:
    targets = sys.argv[1:] or sorted(TARGETS)
    unknown = [name for name in targets if name not in TARGETS]
    if unknown:
        print(f"unknown target: {', '.join(unknown)}", file=sys.stderr)
        return 2
    for name in targets:
        enrich(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
