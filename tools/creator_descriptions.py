"""出典を確認した説明文を保持し、再生成時にも優先する。"""

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

SOURCES_PATH = Path(__file__).with_name("vtuber_description_sources.jsonl")


def load_reviewed(path: Path = SOURCES_PATH) -> list[dict]:
    records = []
    ids, names = set(), set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        person_id = record["person_id"]
        name = record["original"]
        description = record["description"]
        if not isinstance(person_id, str) or not person_id.isdecimal():
            raise ValueError(f"Invalid person_id: {person_id!r}")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Missing original")
        if person_id in ids or name in names:
            raise ValueError(f"Duplicate reviewed person: {name}")
        if not isinstance(description, str) or not 8 <= len(description) <= 65 \
                or not description.endswith("。") \
                or any(c in description for c in '\r\n\t,"'):
            raise ValueError(f"Invalid reviewed description: {name}")
        for left, right in (("（", "）"), ("「", "」"), ("『", "』"), ("(", ")")):
            if description.count(left) != description.count(right):
                raise ValueError(f"Unbalanced description: {name}")
        urls = record["source_urls"]
        if not isinstance(urls, list) or not urls or any(
                not isinstance(url, str) or urlsplit(url).scheme != "https"
                or not urlsplit(url).netloc for url in urls):
            raise ValueError(f"Missing source URL: {name}")
        date.fromisoformat(record["reviewed_on"])
        ids.add(person_id)
        names.add(name)
        records.append(record)
    return records


@lru_cache(maxsize=1)
def _descriptions_by_name() -> dict[str, str]:
    return {record["original"]: record["description"] for record in load_reviewed()}


def reviewed_description(name: str) -> str | None:
    return _descriptions_by_name().get(name)


def apply_reviewed(rows: list[dict], records: list[dict]) -> int:
    """人物IDと活動名を照合してから、同一人物の全表記行へ適用する。"""
    by_id = {}
    for row in rows:
        by_id.setdefault(row["id"], []).append(row)
    for record in records:
        matches = by_id.get(record["person_id"], [])
        if not matches or any(row["original"] != record["original"]
                              or row["category"] != "vtuber" for row in matches):
            raise ValueError(f"Reviewed person does not match CSV: {record['original']}")
    changed = 0
    for record in records:
        for row in by_id[record["person_id"]]:
            if row.get("description") != record["description"]:
                row["description"] = record["description"]
                changed += 1
    return changed
