#!/usr/bin/env python3
"""目視採用したCommons候補だけを municipality.csv へ適用する。"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_reviewed_school_images import (  # noqa: E402
    ManifestError,
    accepted_media,
    load_manifest,
    write_csv_atomic,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "municipality.csv"
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "municipality_image_candidates.jsonl"


def load_municipality(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        cols = list(reader.fieldnames or [])
    required = {"id", "wikidata", "image", "image_page"}
    missing = sorted(required - set(cols))
    if missing:
        raise ManifestError(f"{path}: 必須列が無い: {', '.join(missing)}")
    return cols, rows


def apply_accepted(rows: list[dict], accepted: dict[str, tuple[str, str, str]],
                   csv_path: Path) -> tuple[int, int, int, int]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["id"]].append(row)

    changed_ids = 0
    changed_rows = 0
    unchanged_ids = 0
    unchanged_rows = 0
    for gid in sorted(accepted, key=int):
        expected_qid, image, image_page = accepted[gid]
        group = groups.get(gid)
        if not group:
            raise ManifestError(f"{csv_path}: accepted idが存在しない: {gid}")
        qids = {row.get("wikidata", "") for row in group}
        if qids != {expected_qid}:
            raise ManifestError(
                f"{csv_path}: id {gid} のQIDが台帳と不一致: "
                f"{sorted(qids)} != {expected_qid}"
            )
        if all(row.get("image", "") == image and
               row.get("image_page", "") == image_page for row in group):
            unchanged_ids += 1
            unchanged_rows += len(group)
            continue
        occupied = [row for row in group
                    if row.get("image", "") or row.get("image_page", "")]
        if occupied:
            raise ManifestError(
                f"{csv_path}: id {gid} は既存画像または画像ページがあるため保護"
            )
        for row in group:
            row["image"] = image
            row["image_page"] = image_page
        changed_ids += 1
        changed_rows += len(group)
    return changed_ids, changed_rows, unchanged_ids, unchanged_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        records = load_manifest(args.manifest)
        accepted = accepted_media(records)
        cols, rows = load_municipality(args.csv)
        changed_ids, changed_rows, unchanged_ids, unchanged_rows = apply_accepted(
            rows, accepted, args.csv
        )
        action = "適用予定" if args.dry_run else "適用"
        print(f"{args.csv}: accepted {len(accepted)}自治体、{action} "
              f"{changed_ids}自治体 ({changed_rows}行)、既反映 "
              f"{unchanged_ids}自治体 ({unchanged_rows}行)")
        if not args.dry_run and changed_ids:
            write_csv_atomic(args.csv, cols, rows)
    except (OSError, ManifestError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
