#!/usr/bin/env python3
"""QC済みの汎用SVG置換157件をmanifestとCSVへ適用する。

置換計画は ``gimukyoiku_semantic_image_replacements.jsonl`` に固定し、
プログラム作図98件、ChatGPT Web生成56件、Commons画像3件を扱う。
非対象行はバイト単位で維持する。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "tools" / "gimukyoiku_semantic_image_replacements.jsonl"
MANIFEST = ROOT / "tools" / "gimukyoiku_image_manifest.jsonl"
CSV = ROOT / "gimukyoiku.csv"
BASE = "https://github.com/soramimic/soramimic-wordlists/releases"
ALLOWED_METHODS = {"svg", "gpt-image", "commons"}
LEGACY_PROMPTS = {
    "tools/gen_gimukyoiku_remaining_figs.py で作図(プログラム描画・生成AI不使用)",
    "tools/gen_gimukyoiku_final_figs.py で作図(プログラム描画・生成AI不使用)",
}


def load_plan(path: Path = PLAN) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for lineno, source in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not source.strip():
            continue
        row = json.loads(source)
        word = row["word"]
        if word in result:
            raise ValueError(f"{path}:{lineno}: duplicate word: {word}")
        if row["method"] not in ALLOWED_METHODS:
            raise ValueError(f"{path}:{lineno}: invalid method: {row['method']}")
        expected_ext = {"svg": ".svg", "gpt-image": ".jpg"}.get(row["method"])
        if expected_ext and not row["file"].endswith(expected_ext):
            raise ValueError(f"{path}:{lineno}: unexpected extension: {row['file']}")
        if row["bucket"] not in {"v1", "v1b"}:
            raise ValueError(f"{path}:{lineno}: invalid bucket: {row['bucket']}")
        key = "gk_" + hashlib.sha1(word.encode("utf-8")).hexdigest()[:10]
        if Path(row["file"]).stem != key:
            raise ValueError(f"{path}:{lineno}: invalid file key: {row['file']}")
        expected_bucket = "v1" if int(key[3], 16) < 8 else "v1b"
        if row["bucket"] != expected_bucket:
            raise ValueError(f"{path}:{lineno}: invalid hash bucket: {row['bucket']}")
        if row["method"] == "commons":
            for field in ("image", "source_page", "license"):
                if not row.get(field):
                    raise ValueError(f"{path}:{lineno}: commons requires {field}")
        result[word] = row
    if len(result) != 157:
        raise ValueError(f"replacement plan must contain 157 words, got {len(result)}")
    return result


def release_urls(row: dict) -> tuple[str, str]:
    if row["method"] == "commons":
        return row["image"], row["source_page"]
    tag = f"gimukyoiku-image-{row['bucket']}"
    image = f"{BASE}/download/{tag}/{row['file']}"
    image_page = row.get("source_page") or f"{BASE}/tag/{tag}"
    return image, image_page


def updated_manifest(source: str, plan: dict[str, dict]) -> tuple[str, set[str]]:
    output: list[str] = []
    found: set[str] = set()
    for line in source.splitlines():
        row = json.loads(line)
        replacement = plan.get(row["word"])
        if not replacement or replacement["method"] == "commons":
            output.append(line)
            continue
        found.add(row["word"])
        if all(row.get(key) == value for key, value in replacement.items()):
            output.append(line)
            continue
        expected_old = str(Path(replacement["file"]).with_suffix(".svg"))
        if not (row.get("file") == expected_old and row.get("method") == "svg"
                and row.get("prompt") in LEGACY_PROMPTS):
            raise ValueError(f"unexpected current manifest image for {row['word']}: {row}")
        for stale in ("card_main", "card_sub", "source_page", "license", "author", "institution"):
            row.pop(stale, None)
        row.update(replacement)
        output.append(json.dumps(row, ensure_ascii=False))
    generated = {word for word, row in plan.items() if row["method"] != "commons"}
    missing = generated - found
    if missing:
        raise ValueError(f"manifest missing replacement words: {sorted(missing)}")
    return "\n".join(output) + "\n", found


def _csv_line(row: list[str]) -> str:
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="").writerow(row)
    return stream.getvalue()


def updated_csv(source: str, plan: dict[str, dict]) -> tuple[str, set[str]]:
    lines = source.splitlines()
    header = next(csv.reader([lines[0]]))
    index = {name: header.index(name) for name in ("original", "image", "image_page")}
    output = [lines[0]]
    found: set[str] = set()
    for line in lines[1:]:
        row = next(csv.reader([line]))
        replacement = plan.get(row[index["original"]])
        if not replacement:
            output.append(line)
            continue
        found.add(row[index["original"]])
        desired_image, desired_page = release_urls(replacement)
        if (row[index["image"]], row[index["image_page"]]) == (desired_image, desired_page):
            output.append(line)
            continue
        legacy = {
            "word": replacement["word"],
            "file": str(Path(replacement["file"]).with_suffix(".svg")),
            "bucket": replacement["bucket"],
            "method": "svg",
        }
        expected_image, expected_page = release_urls(legacy)
        if (row[index["image"]], row[index["image_page"]]) != (expected_image, expected_page):
            raise ValueError(f"unexpected current CSV image for {row[index['original']]}: "
                             f"{row[index['image']]}")
        row[index["image"]], row[index["image_page"]] = desired_image, desired_page
        output.append(_csv_line(row))
    missing = set(plan) - found
    if missing:
        raise ValueError(f"CSV missing replacement words: {sorted(missing)}")
    return "\n".join(output), found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="適用済みか検査するだけ")
    args = parser.parse_args()
    plan = load_plan()
    manifest_text, manifest_words = updated_manifest(MANIFEST.read_text(encoding="utf-8"), plan)
    csv_text, csv_words = updated_csv(CSV.read_text(encoding="utf-8"), plan)
    generated_words = {word for word, row in plan.items() if row["method"] != "commons"}
    assert manifest_words == generated_words
    assert csv_words == set(plan)
    changed = (manifest_text != MANIFEST.read_text(encoding="utf-8") or
               csv_text != CSV.read_text(encoding="utf-8"))
    if args.check:
        if changed:
            raise SystemExit("semantic image replacements are not applied")
        print("semantic image replacements: 157/157 applied")
        return
    MANIFEST.write_text(manifest_text, encoding="utf-8")
    CSV.write_text(csv_text, encoding="utf-8")
    print("manifest updated: 154 / CSV updated: 157")


if __name__ == "__main__":
    main()
