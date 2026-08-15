#!/usr/bin/env python3
"""Safely finalize ambiguous surname results from URL audits and Luna reviews."""

import argparse
import json
import os
import tempfile
from pathlib import Path

from apply_myoji_negative_reviews import EVIDENCE_FIELDS, TIER_A_TYPES, load_reviews


def _keys(path, field):
    """Load candidate-keyed audit rows, rejecting malformed input."""
    found = {}
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            key = (row.get("surface", ""), row.get("pronunciation", ""))
            if not all(key):
                raise RuntimeError(f"{path}:{line_number}: missing candidate key")
            found.setdefault(key, []).append(row)
    return found


def _verified(row, review):
    row["status"] = "verified"
    for field in EVIDENCE_FIELDS:
        row[field] = review.get(field, "")
    row["evidence_tier"] = "A" if row["source_type"] in TIER_A_TYPES else "B"
    row["observed_surface"] = row["surface"]
    row["observed_reading"] = row["pronunciation"]


def _clear(row, status, notes):
    row["status"] = status
    for field in EVIDENCE_FIELDS:
        if field != "notes":
            row[field] = ""
    row["notes"] = notes


def finalize(result_paths, audit_paths, review_paths):
    audits = {}
    for path in audit_paths:
        for key, rows in _keys(path, "audit_result").items():
            audits.setdefault(key, []).extend(rows)
    reviews = load_reviews(review_paths) if review_paths else {}
    prepared = []
    counts = {"verified": 0, "no_support_found": 0, "ambiguous": 0, "errors": 0}
    missing_reviews = []
    unverified_review_urls = []
    for result_path in result_paths:
        path = Path(result_path)
        rows = []
        seen = set()
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                key = (row.get("surface", ""), row.get("pronunciation", ""))
                if not all(key):
                    raise RuntimeError(f"{path}:{line_number}: missing candidate key")
                if key in seen:
                    raise RuntimeError(f"{path}:{line_number}: duplicate candidate")
                seen.add(key)
                review = reviews.get(key)
                audit_rows = audits.get(key, [])
                has_error = any(a.get("audit_result") == "error" for a in audit_rows)
                has_pass = any(a.get("audit_result") == "pass" for a in audit_rows)
                if review and review["decision"] == "verified":
                    review_url_passed = any(
                        a.get("audit_result") == "pass"
                        and a.get("source_url") == review.get("source_url")
                        for a in audit_rows
                    )
                    if not review_url_passed:
                        unverified_review_urls.append((str(path), line_number, key))
                    else:
                        _verified(row, review)
                        counts["verified"] += 1
                elif has_error:
                    _clear(
                        row,
                        "ambiguous",
                        "URL audit error remains; negative result not finalized",
                    )
                    counts["ambiguous"] += 1
                elif has_pass:
                    if review is None:
                        missing_reviews.append((str(path), line_number, key))
                    elif review["decision"] == "reject":
                        _clear(
                            row,
                            "no_support_found",
                            review.get("notes", "Luna review rejected person evidence"),
                        )
                        counts["no_support_found"] += 1
                    else:
                        _clear(
                            row,
                            "ambiguous",
                            review.get("notes", "Luna review remains ambiguous"),
                        )
                        counts["ambiguous"] += 1
                else:
                    _clear(row, "no_support_found", "No URL audit pass or error")
                    counts["no_support_found"] += 1
                rows.append(row)
        prepared.append((path, rows))
    problems = []
    if missing_reviews:
        sample = ", ".join(f"{p}:{n}:{k[0]}/{k[1]}" for p, n, k in missing_reviews[:3])
        problems.append(
            f"audit pass requires Luna review ({len(missing_reviews)} missing; {sample})"
        )
    if unverified_review_urls:
        sample = ", ".join(
            f"{p}:{n}:{k[0]}/{k[1]}" for p, n, k in unverified_review_urls[:3]
        )
        problems.append(
            "verified Luna review requires a pass for the same URL "
            f"({len(unverified_review_urls)} missing; {sample})"
        )
    if problems:
        counts["errors"] = len(missing_reviews) + len(unverified_review_urls)
        raise RuntimeError("; ".join(problems))
    for path, rows in prepared:
        fd, temporary = tempfile.mkstemp(
            prefix=path.name + ".", dir=path.parent, text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(
                        json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                        + "\n"
                    )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
    counts["rows"] = sum(len(rows) for _, rows in prepared)
    counts["files"] = len(prepared)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", nargs="+", type=Path, required=True)
    parser.add_argument("--audits", nargs="+", type=Path, required=True)
    parser.add_argument("--reviews", nargs="*", type=Path, default=[])
    args = parser.parse_args()
    print(
        json.dumps(
            finalize(args.results, args.audits, args.reviews),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
