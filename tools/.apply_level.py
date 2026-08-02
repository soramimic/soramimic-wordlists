#!/usr/bin/env python3
"""gimukyoiku.csv に level 列(小学校/中学校/高等学校)を追加する(1回限りの作業スクリプト)。

教科ごとに分類した scratchpad/level/<教科>.out.tsv を読み、original をキーに
level を割り当てる。level 列は subject の直後に挿入する。
"""

import collections
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "gimukyoiku.csv"
LEVELDIR = Path(
    "/tmp/claude-1000/-home-jiro-development-soramimic-wordlists/"
    "d994a36f-dc69-46a9-b53f-1ee73dceb388/scratchpad/level"
)
VALID = {"小学校", "中学校", "高等学校"}

rows = list(csv.DictReader(CSV.open()))
fields = list(rows[0].keys())
if "level" in fields:
    sys.exit("level 列は既にある")

level_of = {}
for f in sorted(LEVELDIR.glob("*.out.tsv")):
    for line in f.read_text().strip().split("\n")[1:]:
        if not line.strip():
            continue
        original, level = line.split("\t")[:2]
        parts = [p for p in level.strip().split("/") if p]
        bad = set(parts) - VALID
        if bad:
            sys.exit(f"{f.name}: 不正な level {bad!r} ({original})")
        merged = level_of.setdefault(original, [])
        for p in parts:
            if p not in merged:
                merged.append(p)

missing = [r["original"] for r in rows if r["original"] not in level_of]
if missing:
    sys.exit(f"level 未割当が {len(missing)}語: {missing[:20]}")

order = ["小学校", "中学校", "高等学校"]
pos = fields.index("subject") + 1
new_fields = fields[:pos] + ["level"] + fields[pos:]
for r in rows:
    parts = sorted(level_of[r["original"]], key=order.index)
    r["level"] = "/".join(parts)

with CSV.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=new_fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
CSV.write_bytes(CSV.read_bytes().rstrip(b"\n"))

print(collections.Counter(r["level"] for r in rows).most_common())
