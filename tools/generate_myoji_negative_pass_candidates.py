#!/usr/bin/env python3
"""Build a candidate-level review queue from negative URL-audit passes."""

import argparse
import json
import os
import tempfile
from pathlib import Path

PASS_FIELDS = (
    "source_url",
    "final_url",
    "content_type",
    "content_sha256",
    "match_context",
    "reason",
)


def candidate_keys(paths):
    keys = set()
    for path in paths:
        with Path(path).open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                key = (row.get("surface", ""), row.get("pronunciation", ""))
                if all(key):
                    keys.add(key)
    return keys


def build_queue(paths, exclude_paths=(), retry_only=False, new_only=False):
    excluded = candidate_keys(exclude_paths)
    grouped = {}
    order = []
    for path in paths:
        with Path(path).open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("audit_result") != "pass":
                    continue
                if retry_only and row.get("retry_of") != "error":
                    continue
                if new_only and not row.get("new_since_checkpoint"):
                    continue
                key = (row.get("surface", ""), row.get("pronunciation", ""))
                if not all(key):
                    raise RuntimeError(f"{path}: pass row lacks candidate key")
                if key in excluded:
                    continue
                if key not in grouped:
                    grouped[key] = {
                        "surface": key[0],
                        "pronunciation": key[1],
                        "batch_index": row.get("batch_index"),
                        "pass_urls": [],
                    }
                    order.append(key)
                urls = grouped[key]["pass_urls"]
                if any(item["source_url"] == row.get("source_url") for item in urls):
                    continue
                urls.append({field: row.get(field) for field in PASS_FIELDS})
    queue = []
    for review_index, key in enumerate(order):
        item = grouped[key]
        item["review_index"] = review_index
        queue.append(item)
    return queue


def save_queue(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--exclude-candidates",
        nargs="*",
        type=Path,
        default=(),
        help="omit candidate keys already present in these JSONL queues/reviews",
    )
    parser.add_argument(
        "--retry-only",
        action="store_true",
        help="include only passes recovered from a previous error",
    )
    parser.add_argument(
        "--new-only",
        action="store_true",
        help="include only passes for URLs newly added after a checkpoint",
    )
    args = parser.parse_args()
    rows = build_queue(
        args.inputs,
        args.exclude_candidates,
        args.retry_only,
        args.new_only,
    )
    save_queue(args.output, rows)
    print(f"queue={args.output} candidates={len(rows)}")


if __name__ == "__main__":
    main()
