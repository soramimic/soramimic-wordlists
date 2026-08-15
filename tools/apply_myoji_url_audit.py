#!/usr/bin/env python3
"""Safely apply schema-v3 URL audits to the myoji evidence ledger.

The default mode is a validation-only dry run.  ``--apply`` writes a backup,
the pass-only ledger, and a review queue using atomic replacements.
"""

import argparse
import json
import os
import tempfile
from pathlib import Path

SCHEMA_VERSION = 3


def _read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f):
            if line.strip():
                rows.append((line_no, json.loads(line)))
    return rows


def _atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    except Exception:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        raise


def _jsonl(rows):
    return "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in rows
    )


def _fingerprint(row):
    return (
        row.get("surface", ""),
        row.get("pronunciation", ""),
        row.get("source_url", ""),
    )


def _validate(ledger_rows, report_rows):
    if len(ledger_rows) != len(report_rows):
        raise ValueError(
            f"count mismatch: ledger={len(ledger_rows)} report={len(report_rows)}"
        )
    expected = {n for n, _ in ledger_rows}
    seen = set()
    audits = {}
    for _, audit in report_rows:
        if audit.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("report contains schema != 3")
        if not audit.get("completed", False):
            raise ValueError("report contains incomplete row")
        number = audit.get("row_number")
        if number in seen:
            raise ValueError(f"duplicate report row_number: {number}")
        seen.add(number)
        audits[number] = audit
    if seen != expected:
        raise ValueError("report row_number set does not match ledger")
    for number, original in ledger_rows:
        audit = audits[number]
        if _fingerprint(original) != _fingerprint(audit):
            raise ValueError(f"row {number}: surface/pronunciation/source_url mismatch")
    return audits


def prepare(ledger_path, report_path):
    ledger = _read_jsonl(Path(ledger_path))
    report = _read_jsonl(Path(report_path))
    audits = _validate(ledger, report)
    retained, queue = [], []
    for number, original in ledger:
        audit = audits[number]
        if audit.get("audit_result") == "pass":
            context = str(audit.get("match_context", "")).strip()
            if not context:
                raise ValueError(f"row {number}: pass lacks match_context")
            retained_row = dict(original)
            retained_row["locator"] = context
            retained.append(retained_row)
        else:
            queued = dict(original)
            for key in (
                "audit_result",
                "reason",
                "match_context",
                "min_distance",
                "reading_token_boundary",
                "matched_reading_token",
                "http_status",
                "final_url",
                "content_type",
                "content_sha256",
                "surface_found",
                "reading_found",
                "schema_version",
            ):
                queued[key] = audit.get(key)
            queued["audit_row_number"] = number
            queue.append(queued)
    return ledger, retained, queue


def apply(ledger_path, report_path, queue_path, backup_path, do_apply=False):
    ledger, retained, queue = prepare(ledger_path, report_path)
    # Preserve the byte-for-byte input ledger in the pre-audit backup.
    current = Path(ledger_path).read_text(encoding="utf-8")
    backup = Path(backup_path)
    if do_apply:
        if backup.exists() and backup.read_text(encoding="utf-8") != current:
            raise ValueError(f"existing backup differs: {backup}")
        if not backup.exists():
            _atomic_write(backup, current)
        _atomic_write(Path(queue_path), _jsonl(queue))
        _atomic_write(Path(ledger_path), _jsonl(retained))
    return {
        "input": len(ledger),
        "retained": len(retained),
        "queued": len(queue),
        "applied": bool(do_apply),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--ledger", type=Path, default=Path("tools/myoji_web_evidence.jsonl")
    )
    p.add_argument(
        "--report", type=Path, default=Path("tools/myoji_web_evidence_url_audit.jsonl")
    )
    p.add_argument(
        "--queue",
        type=Path,
        default=Path("tools/myoji_web_evidence_reaudit_queue.jsonl"),
    )
    p.add_argument(
        "--backup",
        type=Path,
        default=Path("tools/myoji_web_evidence.pre_url_audit.jsonl"),
    )
    p.add_argument(
        "--apply", action="store_true", help="write backup, queue, and pass-only ledger"
    )
    a = p.parse_args()
    result = apply(a.ledger, a.report, a.queue, a.backup, a.apply)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
