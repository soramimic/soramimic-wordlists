#!/usr/bin/env python3
"""出典確認済みの説明をvtuber.csvへ適用する。--checkは検証のみ。"""

import argparse
import csv
from pathlib import Path

from creator_descriptions import apply_reviewed, load_reviewed
from wpnames import write_csv_no_trailing_newline

CSV_PATH = Path(__file__).resolve().parent.parent / "vtuber.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with CSV_PATH.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = reader.fieldnames
        rows = list(reader)
    records = load_reviewed()
    changed = apply_reviewed(rows, records)
    if args.check:
        print(f"Reviewed descriptions: {len(records)} people; {changed} mismatched rows")
        return int(changed > 0)
    if changed:
        write_csv_no_trailing_newline(CSV_PATH, columns, rows)
    print(f"vtuber.csv: updated {changed} rows; {len(records)} reviewed people")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
