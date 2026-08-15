#!/usr/bin/env python3
"""Fetch every URL returned for unresolved candidates.

Search success is not evidence that a negative classification is sound.  This
tool expands the URL receipts embedded in research result JSONL files and runs
the same body-level surface/reading check used for accepted evidence.  Its
output is resumable and deliberately separate from both the research result
and the evidence ledger.
"""

import argparse
import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from audit_myoji_evidence_urls import audit_row, dictionary_host, fetch_document

SCHEMA_VERSION = 1


def expand_rows(paths):
    """Return unique candidate/URL audit jobs in deterministic order."""
    jobs = []
    positions = {}
    for path in paths:
        path = Path(path)
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("status") not in {"no_support_found", "ambiguous"}:
                    continue
                for attempt_index, attempt in enumerate(row.get("search_attempts", [])):
                    for result_rank, url in enumerate(
                        attempt.get("result_urls", []), 1
                    ):
                        key = (
                            row.get("surface", ""),
                            row.get("pronunciation", ""),
                            url,
                        )
                        origin = {
                            "strategy": attempt.get("strategy", ""),
                            "attempt_index": attempt_index,
                            "result_rank": result_rank,
                            "query": attempt.get("query", ""),
                        }
                        if key in positions:
                            jobs[positions[key]]["origins"].append(origin)
                            continue
                        positions[key] = len(jobs)
                        jobs.append(
                            {
                                "surface": row.get("surface", ""),
                                "pronunciation": row.get("pronunciation", ""),
                                "source_url": url,
                                "research_file": path.name,
                                "research_line": line_number,
                                "batch_index": row.get("batch_index"),
                                "origins": [origin],
                            }
                        )
    return jobs


def fingerprint(row):
    return (
        row.get("surface", ""),
        row.get("pronunciation", ""),
        row.get("source_url", ""),
    )


def load_checkpoint(path):
    done = {}
    if not path.exists():
        return done
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raw = raw[: raw.rfind(b"\n") + 1] if b"\n" in raw else b""
        path.write_bytes(raw)
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("negative_audit_schema_version") == SCHEMA_VERSION:
            done[fingerprint(item)] = item
    return done


def compact_checkpoint(path, jobs, done):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for job in jobs:
                item = done.get(fingerprint(job))
                if item is not None:
                    handle.write(
                        json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                        + "\n"
                    )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        raise


def audit_job(
    job, ordinal, timeout, delay, max_distance, fetched=None, shared_fetch=False
):
    kwargs = {
        "timeout": timeout,
        "delay": delay,
        "max_distance": max_distance,
    }
    if shared_fetch:
        kwargs["fetched"] = fetched
    result = audit_row(job, ordinal, **kwargs)
    result.pop("schema_version", None)
    result.pop("row_number", None)
    result.update(
        {
            "negative_audit_schema_version": SCHEMA_VERSION,
            "research_file": job["research_file"],
            "research_line": job["research_line"],
            "batch_index": job.get("batch_index"),
            "origins": job.get("origins", []),
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return result


def audit_url_group(entries, timeout, delay, max_distance):
    """Fetch one URL once, then evaluate it for every candidate using it."""
    if len(entries) == 1 or dictionary_host(entries[0][1].get("source_url", "")):
        return [
            audit_job(job, number, timeout, delay, max_distance)
            for number, job in entries
        ]
    if delay:
        time.sleep(max(0.0, delay))
    try:
        fetched = fetch_document(entries[0][1]["source_url"], timeout=timeout)
    except Exception as exc:
        fetched = exc
    return [
        audit_job(
            job,
            number,
            timeout,
            0.0,
            max_distance,
            fetched=fetched,
            shared_fetch=True,
        )
        for number, job in entries
    ]


def run(
    inputs,
    output,
    workers=8,
    timeout=20,
    delay=0.0,
    max_distance=120,
    limit=None,
    retry_errors=False,
):
    jobs = expand_rows(inputs)
    if limit is not None:
        jobs = jobs[:limit]
    path = Path(output)
    loaded = load_checkpoint(path)
    had_checkpoint = bool(loaded)
    valid = {fingerprint(job) for job in jobs}
    done = {key: item for key, item in loaded.items() if key in valid}
    retry_keys = set()
    if retry_errors:
        retry_keys = {
            key for key, item in done.items() if item.get("audit_result") == "error"
        }
        done = {
            key: item
            for key, item in done.items()
            if item.get("audit_result") != "error"
        }
    pending = [
        (number, job) for number, job in enumerate(jobs) if fingerprint(job) not in done
    ]
    new_keys = {
        fingerprint(job)
        for _, job in pending
        if had_checkpoint and fingerprint(job) not in loaded
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    groups = {}
    for number, job in pending:
        groups.setdefault(job.get("source_url", ""), []).append((number, job))
    with (
        path.open("a", encoding="utf-8") as checkpoint,
        ThreadPoolExecutor(max_workers=max(1, workers)) as pool,
    ):
        futures = {
            pool.submit(audit_url_group, entries, timeout, delay, max_distance): entries
            for entries in groups.values()
        }
        since_sync = 0
        for future in as_completed(futures):
            for item in future.result():
                if fingerprint(item) in retry_keys:
                    item["retry_of"] = "error"
                if fingerprint(item) in new_keys:
                    item["new_since_checkpoint"] = True
                done[fingerprint(item)] = item
                checkpoint.write(
                    json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
                )
                checkpoint.flush()
                since_sync += 1
                if since_sync >= 25:
                    os.fsync(checkpoint.fileno())
                    since_sync = 0
        checkpoint.flush()
        os.fsync(checkpoint.fileno())
    compact_checkpoint(path, jobs, done)
    counts = {}
    for item in done.values():
        counts[item["audit_result"]] = counts.get(item["audit_result"], 0) + 1
    return len(jobs), len(pending), counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--max-distance", type=int, default=120)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="refetch checkpoint rows whose previous audit result was error",
    )
    args = parser.parse_args()
    total, processed, counts = run(
        args.inputs,
        args.output,
        args.workers,
        args.timeout,
        args.delay,
        args.max_distance,
        args.limit,
        args.retry_errors,
    )
    print(
        f"checkpoint={args.output} urls={total} processed={processed} results={counts}"
    )


if __name__ == "__main__":
    main()
