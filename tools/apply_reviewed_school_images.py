#!/usr/bin/env python3
"""目視採用したCommons候補だけを school.csv へ適用する。

候補台帳のレコードに次のレビュー情報を手で追加する。

  "review": {
    "status": "accepted",
    "selected_image_page": "https://commons.wikimedia.org/wiki/File:..."
  }

``selected_image_page`` は同じレコードの ``candidates`` にある値と完全一致する
必要がある。accepted 以外はCSVを変更しない。既存の実写は保護し、校種別の共有
SVGが割り当てられた学校だけを置換する。

usage:
  python3 tools/apply_reviewed_school_images.py --dry-run
  python3 tools/apply_reviewed_school_images.py
"""

import argparse
import csv
import json
import os
import stat
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_school_type_images import is_school_type_image  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "school.csv"
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "school_image_candidates.jsonl"
REVIEW_STATUSES = {"pending", "rejected", "accepted"}
IMAGE_PREFIX = "http://commons.wikimedia.org/wiki/Special:FilePath/"
IMAGE_PAGE_PREFIX = "https://commons.wikimedia.org/wiki/File:"


class ManifestError(ValueError):
    pass


def safe_url(value: object, prefix: str, label: str, context: str) -> str:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ManifestError(f"{context}: {label}がCommons URLではない")
    if any(char in value for char in (",", '"', "\r", "\n")):
        raise ManifestError(f"{context}: {label}にCSVで使えない文字がある")
    return value


def load_manifest(path: Path) -> list[dict]:
    records = []
    seen_ids = set()
    seen_qids = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        context = f"{path}:{lineno}"
        try:
            record = json.loads(line)
        except json.JSONDecodeError as ex:
            raise ManifestError(f"{context}: JSONが不正: {ex}") from ex
        if not isinstance(record, dict):
            raise ManifestError(f"{context}: JSON objectではない")
        gid, qid = record.get("id"), record.get("wikidata")
        if not isinstance(gid, str) or not gid.isdigit() or not gid:
            raise ManifestError(f"{context}: idが不正")
        if not isinstance(qid, str) or not qid.startswith("Q") or not qid[1:].isdigit():
            raise ManifestError(f"{context}: wikidata QIDが不正")
        if gid in seen_ids:
            raise ManifestError(f"{context}: idが重複: {gid}")
        if qid in seen_qids:
            raise ManifestError(f"{context}: QIDが重複: {qid}")
        seen_ids.add(gid)
        seen_qids.add(qid)

        candidates = record.get("candidates")
        if not isinstance(candidates, list):
            raise ManifestError(f"{context}: candidatesが配列ではない")
        pages = set()
        for index, candidate in enumerate(candidates, 1):
            candidate_context = f"{context}: candidate {index}"
            if not isinstance(candidate, dict):
                raise ManifestError(f"{candidate_context}: objectではない")
            safe_url(candidate.get("image"), IMAGE_PREFIX, "image", candidate_context)
            page = safe_url(candidate.get("image_page"), IMAGE_PAGE_PREFIX,
                            "image_page", candidate_context)
            if page in pages:
                raise ManifestError(f"{candidate_context}: image_pageが重複")
            pages.add(page)

        review = record.get("review")
        if review is not None:
            if not isinstance(review, dict):
                raise ManifestError(f"{context}: reviewがobjectではない")
            status = review.get("status", "pending")
            if status not in REVIEW_STATUSES:
                raise ManifestError(f"{context}: review.statusが不正: {status!r}")
            if status == "accepted":
                selected = review.get("selected_image_page")
                if selected not in pages:
                    raise ManifestError(
                        f"{context}: acceptedのselected_image_pageが候補に無い"
                    )
        records.append(record)
    return records


def accepted_media(records: list[dict]) -> dict[str, tuple[str, str, str]]:
    accepted = {}
    for record in records:
        review = record.get("review") or {}
        if review.get("status", "pending") != "accepted":
            continue
        selected = review["selected_image_page"]
        candidate = next(c for c in record["candidates"]
                         if c["image_page"] == selected)
        accepted[record["id"]] = (
            record["wikidata"], candidate["image"], candidate["image_page"]
        )
    return accepted


def load_school(path: Path) -> tuple[list[str], list[dict]]:
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
    groups = defaultdict(list)
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
        unsafe = sorted({row.get("image", "") for row in group
                         if not is_school_type_image(row.get("image", ""))})
        if unsafe:
            shown = unsafe[0] or "(空欄)"
            raise ManifestError(
                f"{csv_path}: id {gid} は校種SVGではないため保護: {shown}"
            )
        for row in group:
            row["image"], row["image_page"] = image, image_page
        changed_ids += 1
        changed_rows += len(group)
    return changed_ids, changed_rows, unchanged_ids, unchanged_rows


def write_csv_atomic(path: Path, cols: list[str], rows: list[dict]) -> None:
    # 同じディレクトリで完成ファイルを書いてから置換し、中断時の書きかけを防ぐ。
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                    dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        tmp_path = Path(tmp_name)
        text = tmp_path.read_text(encoding="utf-8").rstrip("\n")
        if '"' in text:
            raise ManifestError("出力に引用符付きフィールドが生じる")
        tmp_path.write_text(text, encoding="utf-8")
        os.chmod(tmp_path, stat.S_IMODE(path.stat().st_mode))
        os.replace(tmp_path, path)
    finally:
        tmp_path = Path(tmp_name)
        if tmp_path.exists():
            tmp_path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        records = load_manifest(args.manifest)
        accepted = accepted_media(records)
        cols, rows = load_school(args.csv)
        changed_ids, changed_rows, unchanged_ids, unchanged_rows = apply_accepted(
            rows, accepted, args.csv
        )
        action = "適用予定" if args.dry_run else "適用"
        print(f"{args.csv}: accepted {len(accepted)}校、{action} "
              f"{changed_ids}校 ({changed_rows}行)、既反映 "
              f"{unchanged_ids}校 ({unchanged_rows}行)")
        if not args.dry_run and changed_ids:
            write_csv_atomic(args.csv, cols, rows)
    except (OSError, ManifestError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
