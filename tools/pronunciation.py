"""Keep supplied pronunciation columns in kana without inferring their text."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
SOURCES = Path(__file__).with_name("pronunciation_sources.jsonl")
KANA_RE = re.compile(r"[ぁ-ゖァ-ヺー]+")
_SEPARATORS = re.compile(r"[\s・、。,.=:;/!?()\[\]{}「」『』【】〈〉《》<>\-'’\"]+")


@lru_cache(maxsize=1)
def reviewed_readings() -> dict[tuple[str, str], str]:
    readings = {}
    for line in SOURCES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        key = (record["list"], record["surface"])
        urls = record["source_urls"]
        if key in readings or record["list"] not in {"pokemon", "scientist"} \
                or not KANA_RE.fullmatch(record["pronunciation"]) \
                or not urls or any(urlsplit(url).scheme not in {"http", "https"}
                                   or not urlsplit(url).netloc for url in urls):
            raise ValueError(f"Invalid reviewed pronunciation: {key}")
        date.fromisoformat(record["reviewed_on"])
        readings[key] = record["pronunciation"]
    return readings


def normalize_pronunciation(list_name: str, surface: str, reading: str) -> str:
    if not reading or reading.lower() == "na":
        return reading
    reading = reviewed_readings().get((list_name, surface), reading)
    normalized = _SEPARATORS.sub("", unicodedata.normalize("NFKC", reading))
    if not KANA_RE.fullmatch(normalized):
        raise ValueError(f"{list_name}「{surface}」の読み「{reading}」をカナで指定してください")
    return normalized


def normalize_rows(list_name: str, rows: list[dict]) -> None:
    for row in rows:
        if "pronunciation" in row:
            row["pronunciation"] = normalize_pronunciation(
                list_name, row.get("surface", ""), row["pronunciation"]
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    updates = []
    for path in sorted(ROOT.glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns, rows = reader.fieldnames, list(reader)
        old = [dict(row) for row in rows]
        normalize_rows(path.stem, rows)
        changes = sum(before != after for before, after in zip(old, rows))
        if changes:
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            text = output.getvalue().rstrip("\n")
            if '"' in text:
                raise ValueError(f"Quoted CSV fields: {path.name}")
            updates.append((path, text))
            print(f"{path.name}: {changes} pronunciation changes")
    # Validate every list before writing any of them.
    if not args.check:
        for path, text in updates:
            path.write_text(text, encoding="utf-8")
    return int(args.check and bool(updates))


if __name__ == "__main__":
    raise SystemExit(main())
