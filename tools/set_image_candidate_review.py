#!/usr/bin/env python3
"""学校・自治体の画像候補台帳へレビュー結果を安全に記録する。

usage:
  python3 tools/set_image_candidate_review.py school 5146 accepted \
    --selected-image-page https://commons.wikimedia.org/wiki/File:Example.jpg
  python3 tools/set_image_candidate_review.py municipality 2106 rejected --note 別施設
"""

import argparse
import json
import os
import stat
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFESTS = {
    "school": ROOT / "school_image_candidates.jsonl",
    "municipality": ROOT / "municipality_image_candidates.jsonl",
}
STATUSES = {"pending", "rejected", "accepted"}


class ReviewError(ValueError):
    pass


def load_records(path: Path) -> list[dict]:
    records: list[dict] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        context = f"{path}:{lineno}"
        try:
            record = json.loads(line)
        except json.JSONDecodeError as ex:
            raise ReviewError(f"{context}: JSONが不正: {ex}") from ex
        if not isinstance(record, dict):
            raise ReviewError(f"{context}: JSON objectではない")
        gid = record.get("id")
        if not isinstance(gid, str) or not gid.isdigit() or not gid:
            raise ReviewError(f"{context}: idが不正")
        if gid in seen:
            raise ReviewError(f"{context}: idが重複: {gid}")
        seen.add(gid)
        candidates = record.get("candidates")
        if not isinstance(candidates, list):
            raise ReviewError(f"{context}: candidatesが配列ではない")
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ReviewError(f"{context}: candidateがobjectではない")
        records.append(record)
    return records


def set_review(records: list[dict], gid: str, status: str,
               selected_image_page: str | None, note: str | None) -> dict:
    if status not in STATUSES:
        raise ReviewError(f"statusが不正: {status!r}")
    matches = [record for record in records if record["id"] == gid]
    if not matches:
        raise ReviewError(f"idが台帳に存在しない: {gid}")
    record = matches[0]
    pages = [candidate.get("image_page") for candidate in record["candidates"]]
    if status == "accepted":
        if not selected_image_page:
            raise ReviewError("acceptedには--selected-image-pageが必要")
        if selected_image_page not in pages:
            raise ReviewError("selected_image_pageが候補と完全一致しない")
    elif selected_image_page is not None:
        raise ReviewError("--selected-image-pageはacceptedでのみ指定できる")

    review = {"status": status}
    if status == "accepted":
        review["selected_image_page"] = selected_image_page
    if note is not None:
        review["note"] = note
    record["review"] = review
    return record


def write_jsonl_atomic(path: Path, records: list[dict]) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                    dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            for record in records:
                json.dump(record, fh, ensure_ascii=False, separators=(",", ":"))
                fh.write("\n")
        os.chmod(tmp_path, stat.S_IMODE(path.stat().st_mode))
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=sorted(DEFAULT_MANIFESTS))
    parser.add_argument("id")
    parser.add_argument("status", choices=sorted(STATUSES))
    parser.add_argument("--selected-image-page")
    parser.add_argument("--note")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    path = args.manifest or DEFAULT_MANIFESTS[args.kind]
    try:
        records = load_records(path)
        record = set_review(records, args.id, args.status,
                            args.selected_image_page, args.note)
        write_jsonl_atomic(path, records)
        detail = f" ({record.get('original', '')})" if record.get("original") else ""
        print(f"{path}: id {args.id}{detail} を {args.status} に更新")
    except (OSError, ReviewError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
