#!/usr/bin/env python3
"""Apply the final image plan and static media replacements to gimukyoiku."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "gimukyoiku.csv"
MANIFEST = ROOT / "tools" / "gimukyoiku_image_manifest.jsonl"
PLAN = ROOT / "tools" / "gimukyoiku_final_image_plan.json"
BASE = "https://github.com/soramimic/soramimic-wordlists/releases"
SVG_PROMPT = (
    "tools/gen_gimukyoiku_final_figs.py で作図"
    "(プログラム描画・生成AI不使用)"
)
MEDIA_REPLACEMENTS = {"原稿用紙": ".pdf", "越天楽": ".webm"}


def key(word: str) -> str:
    return "gk_" + hashlib.sha1(word.encode()).hexdigest()[:10]


def entry_for(row: dict) -> dict:
    file_key = key(row["word"])
    extension = "svg" if row["mode"] == "svg" else "jpg"
    return {
        "word": row["word"],
        "file": f"{file_key}.{extension}",
        "bucket": "v1" if int(file_key[3], 16) < 8 else "v1b",
        "method": "svg" if row["mode"] == "svg" else "gpt-image",
        "prompt": SVG_PROMPT if row["mode"] == "svg" else row["prompt"],
    }


def media_entry(word: str) -> dict:
    file_key = key(word)
    return {
        "word": word,
        "file": f"{file_key}.svg",
        "bucket": "v1" if int(file_key[3], 16) < 8 else "v1b",
        "method": "svg",
        "prompt": SVG_PROMPT,
    }


def urls(entry: dict) -> tuple[str, str]:
    tag = f"gimukyoiku-image-{entry['bucket']}"
    return (
        f"{BASE}/download/{tag}/{entry['file']}",
        f"{BASE}/tag/{tag}",
    )


def main() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert len(plan) == 122
    planned = {row["word"]: row for row in plan}

    manifest = [
        json.loads(line)
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
    ]
    manifest_index = {row["word"]: i for i, row in enumerate(manifest)}
    entries = {word: entry_for(row) for word, row in planned.items()}
    entries.update({word: media_entry(word) for word in MEDIA_REPLACEMENTS})
    for word, entry in entries.items():
        if word in manifest_index:
            manifest[manifest_index[word]] = entry
        else:
            manifest_index[word] = len(manifest)
            manifest.append(entry)

    lines = CSV.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    index = {
        name: header.index(name)
        for name in ("original", "image", "image_page", "wikidata")
    }
    output = [lines[0]]
    found = set()
    changed = 0
    for source in lines[1:]:
        fields = source.split(",")
        word = fields[index["original"]]
        if word not in entries:
            output.append(source)
            continue
        found.add(word)
        image, image_page = urls(entries[word])
        current_image = fields[index["image"]]
        current_page = fields[index["image_page"]]
        if current_image == image and current_page == image_page:
            output.append(source)
            continue
        if word in planned:
            if current_image or current_page:
                raise SystemExit(f"refusing to replace existing image for {word}")
        else:
            suffix = MEDIA_REPLACEMENTS[word]
            if (
                "commons.wikimedia.org" not in current_image
                or "commons.wikimedia.org" not in current_page
                or suffix not in current_image.lower()
            ):
                raise SystemExit(f"unexpected current media for {word}: {current_image}")
            fields[index["wikidata"]] = ""
        fields[index["image"]] = image
        fields[index["image_page"]] = image_page
        output.append(",".join(fields))
        changed += 1

    if found != entries.keys():
        raise SystemExit(f"missing CSV words: {sorted(entries.keys() - found)}")
    MANIFEST.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in manifest),
        encoding="utf-8",
    )
    CSV.write_text("\n".join(output), encoding="utf-8")
    print(f"applied {changed} final images")


if __name__ == "__main__":
    main()
