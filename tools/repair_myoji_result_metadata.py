#!/usr/bin/env python3
"""Restore immutable candidate metadata in research result JSONL files."""

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path


def load_candidates(path):
    with Path(path).open(encoding="utf-8") as handle:
        return {int(row["batch_index"]): row for row in csv.DictReader(handle)}


def repair(path, candidates):
    path = Path(path)
    rows = []
    changed = 0
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        row = json.loads(line)
        index = int(row["batch_index"])
        if index not in candidates:
            raise RuntimeError(f"{path}:{line_number}: unknown batch_index")
        candidate = candidates[index]
        if (row.get("surface"), row.get("pronunciation")) != (
            candidate["surface"],
            candidate["pronunciation"],
        ):
            raise RuntimeError(f"{path}:{line_number}: candidate identity mismatch")
        before = tuple(str(row.get(field, "")) for field in ("id", "rank", "query"))
        for field in ("id", "rank", "query"):
            row[field] = candidate[field]
        changed += before != tuple(row[field] for field in ("id", "rank", "query"))
        rows.append(row)
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
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("results", nargs="+", type=Path)
    args = parser.parse_args()
    candidates = load_candidates(args.candidates)
    total = 0
    for path in args.results:
        count = repair(path, candidates)
        total += count
        print(f"{path}: repaired {count} rows")
    print(f"repaired {total} rows total")


if __name__ == "__main__":
    main()
