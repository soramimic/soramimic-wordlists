#!/usr/bin/env python3
"""gimukyoiku.csv の画像が空の行に、生成イメージ(GitHub Release)のURLを設定する。

- 対応表は tools/gimukyoiku_image_manifest.jsonl(語 → ファイル名・バケット・手法)
- image は releases/download/gimukyoiku-image-v1(v1b)/gk_<sha1(語)先頭10桁>.jpg
- image_page はリリースのタグページ(ライセンス・AI生成明示の確認先)
- 実写(Commons)が入っている行は触らない。冪等
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "gimukyoiku.csv"
MANIFEST = ROOT / "tools" / "gimukyoiku_image_manifest.jsonl"
BASE = "https://github.com/soramimic/soramimic-wordlists/releases"


def main():
    mapping = {}
    for line in MANIFEST.read_text(encoding="utf-8").strip().split("\n"):
        m = json.loads(line)
        tag = "gimukyoiku-image-v1" if m["bucket"] == "v1" else "gimukyoiku-image-v1b"
        mapping[m["word"]] = (
            f"{BASE}/download/{tag}/{m['file']}",
            f"{BASE}/tag/{tag}",
        )

    lines = CSV.read_text(encoding="utf-8").split("\n")
    header = lines[0].split(",")
    idx = {c: header.index(c) for c in header}
    rows = [l.split(",") for l in lines[1:]]
    n = 0
    for r in rows:
        if r[idx["image"]]:
            continue
        urls = mapping.get(r[idx["original"]])
        if not urls:
            continue
        r[idx["image"]], r[idx["image_page"]] = urls
        n += 1
    CSV.write_text("\n".join([",".join(header)] + [",".join(r) for r in rows]), encoding="utf-8")
    empty = sum(1 for r in rows if not r[idx["image"]])
    print(f"付与 {n} 行 / 残り空欄 {empty} 行")


if __name__ == "__main__":
    main()
