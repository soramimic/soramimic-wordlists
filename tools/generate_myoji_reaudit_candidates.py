#!/usr/bin/env python3
"""Create DuckDuckGo-runner-compatible candidates from the audit queue."""

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path

FIELDS = ("batch_index", "id", "surface", "pronunciation", "rank", "query")
KATA2HIRA = str.maketrans(
    {chr(c): chr(c - 0x60) for c in range(ord("ァ"), ord("ヶ") + 1)}
)


def _rows(paths):
    result = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                surface, pronunciation = (
                    row.get("surface", ""),
                    row.get("pronunciation", ""),
                )
                if not surface or not pronunciation:
                    raise ValueError(
                        f"{path}:{line_no}: surface/pronunciation required"
                    )
                key = (surface, pronunciation)
                rank = row.get("rank", "")
                if key in result and result[key].get("rank", "") != rank:
                    raise ValueError(f"conflicting rank for {surface}/{pronunciation}")
                result.setdefault(
                    key,
                    {"surface": surface, "pronunciation": pronunciation, "rank": rank},
                )
    return list(result.values())


def _atomic_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for i, row in enumerate(rows):
                writer.writerow(
                    {
                        "batch_index": i,
                        "id": row["id"],
                        "surface": row["surface"],
                        "pronunciation": row["pronunciation"],
                        "rank": row["rank"],
                        "query": f"{row['surface']} {row['pronunciation'].translate(KATA2HIRA)} 氏名",
                    }
                )
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    except Exception:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        raise


def _catalog(path):
    result = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (row.get("surface", ""), row.get("pronunciation", ""))
            if not all(key):
                continue
            if key in result:
                raise ValueError(f"pair is not unique in catalog: {key[0]}/{key[1]}")
            result[key] = {
                "id": row.get("id", ""),
                "rank": row.get("rank", ""),
                "verified": row.get("verified", ""),
            }
    return result


def generate(
    input_paths, output_path, catalog_path=Path("myoji.csv"), only_unverified=False
):
    if isinstance(input_paths, (str, Path)):
        input_paths = [Path(input_paths)]
    queue = _rows([Path(path) for path in input_paths])
    catalog = _catalog(Path(catalog_path))
    rows = []
    for row in queue:
        key = (row["surface"], row["pronunciation"])
        if key not in catalog:
            raise ValueError(f"pair not found in catalog: {key[0]}/{key[1]}")
        if only_unverified and catalog[key]["verified"] != "no":
            continue
        rows.append({**row, **catalog[key]})
    _atomic_csv(Path(output_path), rows)
    return len(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, nargs="+", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--myoji", type=Path, default=Path("myoji.csv"))
    p.add_argument("--only-unverified", action="store_true")
    a = p.parse_args()
    print(
        json.dumps(
            {
                "rows": generate(a.input, a.output, a.myoji, a.only_unverified),
                "output": str(a.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
