#!/usr/bin/env python3
"""stations.csv の operator/opened_year/station_code を Wikidata から補完する。

既存値は上書きせず、空欄だけを補完する。複数の運営者・駅番号は「／」で連結する。
開業年は正式開業日(P1619)の最古年を使い、無ければ設立日(P571)へフォールバックする。

usage: python3 tools/enrich_station_facts.py
"""

import csv
import io
import sys
from pathlib import Path

from update_stations import fetch_details, resolve_operator_labels, sanitize_cell

CSV_PATH = Path(__file__).resolve().parent.parent / "stations.csv"
COLS = [
    "id", "original", "surface", "pronunciation", "prefecture", "city",
    "lines", "operator", "opened_year", "station_code", "status",
    "image", "image_page", "description", "wikidata",
]


def main() -> int:
    if sys.argv[1:]:
        print(f"unknown option: {sys.argv[1]}", file=sys.stderr)
        return 2

    with CSV_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    targets = [
        row for row in rows
        if row.get("wikidata")
        and any(not row.get(col) for col in ("operator", "opened_year", "station_code"))
    ]
    details = fetch_details(sorted({row["wikidata"] for row in targets}))
    operator_qids = {
        op for detail in details.values() for op in detail["operator_qids"]
    }
    operator_labels = resolve_operator_labels(operator_qids)

    filled = {col: 0 for col in ("operator", "opened_year", "station_code")}
    for row in targets:
        detail = details.get(row["wikidata"])
        if not detail:
            continue
        values = {
            "operator": "／".join(sorted({
                operator_labels[op] for op in detail["operator_qids"]
                if operator_labels.get(op)
            })),
            "opened_year": detail["opened_year"],
            "station_code": detail["station_code"],
        }
        for col, value in values.items():
            if not row.get(col) and value:
                row[col] = sanitize_cell(value)
                filled[col] += 1

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=COLS, lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    writer.writerows(rows)
    CSV_PATH.write_text(buf.getvalue().rstrip("\n"), encoding="utf-8")

    totals = {
        col: sum(bool(row.get(col)) for row in rows)
        for col in ("operator", "opened_year", "station_code")
    }
    print(
        f"stations.csv: operator +{filled['operator']} ({totals['operator']}/{len(rows)}) / "
        f"opened_year +{filled['opened_year']} ({totals['opened_year']}/{len(rows)}) / "
        f"station_code +{filled['station_code']} ({totals['station_code']}/{len(rows)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
