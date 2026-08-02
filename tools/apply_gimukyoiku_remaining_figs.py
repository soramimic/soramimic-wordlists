#!/usr/bin/env python3
"""残存SD 69語をプログラム作図SVGへ切り替える。

manifestのfile/method/promptと、gimukyoiku.csvのimage URLだけを更新する。
同じSVGを再生成・再適用しても差分が増えない。
"""
from __future__ import annotations

import json
from pathlib import Path

from gen_gimukyoiku_math_figs import key
from gen_gimukyoiku_remaining_figs import FIGURES

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tools" / "gimukyoiku_image_manifest.jsonl"
CSV = ROOT / "gimukyoiku.csv"
BASE = "https://github.com/soramimic/soramimic-wordlists/releases"
PROMPT = "tools/gen_gimukyoiku_remaining_figs.py で作図(プログラム描画・生成AI不使用)"


def main():
    source_lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    output_lines = []
    changed_manifest = set()
    found = set()
    for source in source_lines:
        row = json.loads(source)
        word = row["word"]
        if word not in FIGURES:
            output_lines.append(source)
            continue
        found.add(word)
        expected_file = f"{key(word)}.svg"
        if row["method"] not in {"sd", "svg"}:
            raise SystemExit(f"unexpected method for {word}: {row['method']}")
        if row["method"] == "svg" and row["file"] == expected_file and row["prompt"] == PROMPT:
            output_lines.append(source)
            continue
        row["file"] = expected_file
        row["method"] = "svg"
        row["prompt"] = PROMPT
        output_lines.append(json.dumps(row, ensure_ascii=False))
        changed_manifest.add(word)
    missing = set(FIGURES) - found
    if missing:
        raise SystemExit(f"missing manifest words: {sorted(missing)}")
    MANIFEST.write_text("".join(line + "\n" for line in output_lines), encoding="utf-8")

    lines = CSV.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    idx = {name: header.index(name) for name in ("original", "image", "image_page")}
    changed_csv = set()
    found_csv = set()
    out = [lines[0]]
    for source in lines[1:]:
        row = source.split(",")
        word = row[idx["original"]]
        if word not in FIGURES:
            out.append(source)
            continue
        found_csv.add(word)
        file_key = key(word)
        bucket = "v1" if int(file_key[3], 16) < 8 else "v1b"
        tag = f"gimukyoiku-image-{bucket}"
        image = f"{BASE}/download/{tag}/{file_key}.svg"
        image_page = f"{BASE}/tag/{tag}"
        if row[idx["image"]] != image or row[idx["image_page"]] != image_page:
            if row[idx["image"]] and not row[idx["image"]].endswith(f"/{file_key}.jpg"):
                raise SystemExit(f"unexpected old image for {word}: {row[idx['image']]}")
            row[idx["image"]] = image
            row[idx["image_page"]] = image_page
            changed_csv.add(word)
        out.append(",".join(row))
    missing_csv = set(FIGURES) - found_csv
    if missing_csv:
        raise SystemExit(f"missing CSV words: {sorted(missing_csv)}")
    CSV.write_text("\n".join(out), encoding="utf-8")
    print(f"manifest updated: {len(changed_manifest)} / CSV updated: {len(changed_csv)}")


if __name__ == "__main__":
    main()
