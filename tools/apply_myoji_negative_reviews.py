#!/usr/bin/env python3
"""Apply body-audit person reviews to research JSONL without touching receipts."""

import argparse
import json
import os
import tempfile
from pathlib import Path

from update_myoji import (
    OFFICIAL_SOURCE_TYPES,
    WEB_EVIDENCE_TIERS,
    WEB_IDENTITY_BASES,
    WEB_SOURCE_TYPES,
)

TIER_A_TYPES = OFFICIAL_SOURCE_TYPES | frozenset(
    {
        "government_register",
        "school_profile",
        "university_profile",
        "sports_roster",
        "corporate_filing",
        "corporate_release",
        "professional_directory",
    }
)


EVIDENCE_FIELDS = (
    "source_url",
    "source_type",
    "source_title",
    "observed_surface",
    "observed_reading",
    "locator",
    "notes",
    "evidence_tier",
    "identity_basis",
)

RESET_UNREVIEWED_NOTE = "最新URL監査レビュー範囲で未採用（レビュー対象外）"


def load_reviews(paths):
    reviews = {}
    for path in paths:
        with Path(path).open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                decision = row.get("decision")
                if decision not in {"verified", "reject", "ambiguous"}:
                    raise RuntimeError(f"{path}:{line_number}: bad decision")
                key = (row.get("surface", ""), row.get("pronunciation", ""))
                if not all(key) or key in reviews:
                    raise RuntimeError(
                        f"{path}:{line_number}: missing or duplicate candidate"
                    )
                if decision == "verified":
                    if not str(row.get("source_url", "")).startswith("https://"):
                        raise RuntimeError(
                            f"{path}:{line_number}: verified review lacks HTTPS evidence"
                        )
                    if (
                        row.get("source_type")
                        not in OFFICIAL_SOURCE_TYPES | WEB_SOURCE_TYPES
                    ):
                        raise RuntimeError(f"{path}:{line_number}: invalid source_type")
                    if row.get("evidence_tier") not in WEB_EVIDENCE_TIERS:
                        raise RuntimeError(
                            f"{path}:{line_number}: invalid evidence_tier"
                        )
                    if row.get("identity_basis") not in WEB_IDENTITY_BASES:
                        raise RuntimeError(
                            f"{path}:{line_number}: invalid identity_basis"
                        )
                    for field in (
                        "source_title",
                        "observed_surface",
                        "observed_reading",
                        "locator",
                    ):
                        if not row.get(field):
                            raise RuntimeError(f"{path}:{line_number}: missing {field}")
                reviews[key] = row
    return reviews


def apply_many(result_paths, review_paths, reset_unreviewed=False):
    reviews = load_reviews(review_paths)
    results = []
    found = set()
    for result_path in result_paths:
        path = Path(result_path)
        rows = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                key = (row.get("surface", ""), row.get("pronunciation", ""))
                review = reviews.get(key)
                if review is not None:
                    found.add(key)
                    decision = review["decision"]
                    if decision == "verified":
                        row["status"] = "verified"
                        for field in EVIDENCE_FIELDS:
                            row[field] = review.get(field, "")
                        # Tier is a deterministic consequence of source_type in
                        # the repository schema; do not trust hand-entered review
                        # metadata to drift from that rule.
                        row["evidence_tier"] = (
                            "A" if row["source_type"] in TIER_A_TYPES else "B"
                        )
                        # Research/evidence schema records the surname token, not
                        # the full personal name transcribed by a reviewer.
                        row["observed_surface"] = row["surface"]
                        row["observed_reading"] = row["pronunciation"]
                    elif decision == "ambiguous":
                        row["status"] = "ambiguous"
                        for field in EVIDENCE_FIELDS:
                            row[field] = ""
                        row["notes"] = review.get(
                            "notes", "body-audit person identity ambiguous"
                        )
                    else:
                        row["status"] = "no_support_found"
                        for field in EVIDENCE_FIELDS:
                            row[field] = ""
                        row["notes"] = review.get(
                            "notes", "body-audit match was not person evidence"
                        )
                elif reset_unreviewed:
                    row["status"] = "no_support_found"
                    for field in EVIDENCE_FIELDS:
                        row[field] = ""
                    row["notes"] = RESET_UNREVIEWED_NOTE
                rows.append(row)
        results.append((path, rows))
    missing = set(reviews) - found
    if missing:
        raise RuntimeError(
            f"review candidates absent from result: {sorted(missing)[:3]}"
        )
    total_rows = 0
    for path, rows in results:
        fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(
                        json.dumps(row, ensure_ascii=False, separators=(",", ":"))
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
        total_rows += len(rows)
    return (
        total_rows,
        len(reviews),
        sum(r["decision"] == "verified" for r in reviews.values()),
    )


def apply(result_path, review_paths, reset_unreviewed=False):
    return apply_many([result_path], review_paths, reset_unreviewed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", "--results", nargs="+", type=Path, required=True)
    parser.add_argument("--reviews", nargs="+", type=Path, required=True)
    parser.add_argument(
        "--reset-unreviewed",
        action="store_true",
        help="reset result rows absent from the supplied review scope",
    )
    args = parser.parse_args()
    rows, reviewed, verified = apply_many(
        args.result, args.reviews, reset_unreviewed=args.reset_unreviewed
    )
    print(
        f"results={len(args.result)} rows={rows} reviewed={reviewed} verified={verified}"
    )


if __name__ == "__main__":
    main()
