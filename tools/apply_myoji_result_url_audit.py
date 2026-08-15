#!/usr/bin/env python3
"""Demote research candidates rejected by the independent URL-body audit."""

import argparse
import json
import os
import tempfile
from pathlib import Path

from audit_myoji_web_research import RESEARCH_DIR

EVIDENCE_FIELDS = (
    "source_url",
    "source_type",
    "source_title",
    "observed_surface",
    "observed_reading",
    "locator",
    "evidence_tier",
    "identity_basis",
)


def _rejections(paths):
    rejected = {}
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("audit_result") == "pass":
                continue
            key = (
                row.get("surface", ""),
                row.get("pronunciation", ""),
                row.get("source_url", ""),
            )
            rejected[key] = row.get("reason", "url_body_audit_failed")
    return rejected


def _atomic_jsonl(path, rows):
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise


def apply(batch, queue_paths, do_apply=False, research_dir=RESEARCH_DIR):
    rejected = _rejections(queue_paths)
    changed = 0
    rewrites = []
    for path in sorted(Path(research_dir).glob(f"{batch}-[a-z].jsonl")):
        rows = []
        file_changed = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = (
                row.get("surface", ""),
                row.get("pronunciation", ""),
                row.get("source_url", ""),
            )
            if row.get("status") == "verified" and key in rejected:
                row["status"] = "ambiguous"
                for field in EVIDENCE_FIELDS:
                    row[field] = ""
                note = f"URL-body audit rejected: {rejected[key]}"
                row["notes"] = "; ".join(filter(None, (row.get("notes", ""), note)))
                changed += 1
                file_changed = True
            rows.append(row)
        if file_changed:
            rewrites.append((path, rows))
    if do_apply:
        for path, rows in rewrites:
            _atomic_jsonl(path, rows)
    return {"batch": batch, "changed": changed, "applied": bool(do_apply)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--queue", type=Path, nargs="+", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            apply(args.batch, args.queue, args.apply),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
