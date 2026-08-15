#!/usr/bin/env python3
"""Safely remove non-verified review candidates from the evidence ledger."""

import argparse
import json
import os
import tempfile
from pathlib import Path


def _read(path):
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for n, line in enumerate(handle, 1):
            if line.strip():
                rows.append((n, json.loads(line)))
    return rows


def _jsonl(rows):
    return "".join(
        json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows
    )


def _atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _key(r):
    return (r.get("surface", ""), r.get("pronunciation", ""))


def prepare(ledger_path, review_paths, allow_already_absent=False):
    ledger = _read(ledger_path)
    reviews = []
    for p in review_paths:
        reviews.extend(r for _, r in _read(p))
    lk = [_key(r) for _, r in ledger]
    if any(not all(k) for k in lk):
        raise ValueError("ledger contains missing candidate key")
    if len(set(lk)) != len(lk):
        raise ValueError("ledger contains duplicate candidate")
    rk = [_key(r) for r in reviews]
    if any(not all(k) for k in rk):
        raise ValueError("review contains missing candidate key")
    if len(set(rk)) != len(rk):
        raise ValueError("review contains duplicate candidate")
    decisions = {_key(r): r.get("decision") for r in reviews}
    if any(d not in {"verified", "reject", "ambiguous"} for d in decisions.values()):
        raise ValueError("review contains invalid decision")
    missing = set(rk) - set(lk)
    if missing and not (
        allow_already_absent
        and all(decisions[k] in {"reject", "ambiguous"} for k in missing)
    ):
        raise ValueError("review candidate absent from ledger")
    removed = [
        r for _, r in ledger if decisions.get(_key(r)) in {"reject", "ambiguous"}
    ]
    retained = [
        r for _, r in ledger if decisions.get(_key(r)) not in {"reject", "ambiguous"}
    ]
    return ledger, retained, removed


def apply(
    ledger_path,
    review_paths,
    queue_path,
    backup_path,
    do_apply=False,
    allow_already_absent=False,
):
    ledger, retained, removed = prepare(ledger_path, review_paths, allow_already_absent)
    current = Path(ledger_path).read_bytes()
    backup = Path(backup_path)
    if backup.exists() and backup.read_bytes() != current:
        raise ValueError("existing backup differs")
    if do_apply:
        if not backup.exists():
            _atomic_write(backup, current.decode("utf-8"))
        _atomic_write(queue_path, _jsonl(removed))
        _atomic_write(ledger_path, _jsonl(retained))
    return {
        "input": len(ledger),
        "retained": len(retained),
        "removed": len(removed),
        "applied": bool(do_apply),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--ledger", type=Path, default=Path("tools/myoji_web_evidence.jsonl")
    )
    p.add_argument("--reviews", nargs="+", type=Path, required=True)
    p.add_argument(
        "--queue",
        type=Path,
        default=Path("tools/myoji_web_evidence_rejection_queue.jsonl"),
    )
    p.add_argument(
        "--backup",
        type=Path,
        default=Path("tools/myoji_web_evidence.pre_review_rejections.jsonl"),
    )
    p.add_argument("--apply", action="store_true")
    p.add_argument(
        "--allow-already-absent",
        action="store_true",
        help="allow non-verified review candidates already removed by an earlier audit",
    )
    a = p.parse_args()
    print(
        json.dumps(
            apply(
                a.ledger, a.reviews, a.queue, a.backup, a.apply, a.allow_already_absent
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
