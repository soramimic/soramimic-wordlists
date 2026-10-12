"""Preserve reviewed Economic Sciences awards and newly announced laureates."""

import json
from datetime import date
from pathlib import Path

SOURCES = Path(__file__).with_suffix(".json")


def load_awards():
    records = json.loads(SOURCES.read_text(encoding="utf-8"))
    seen = set()
    for record in records:
        name = record["original"]
        if name in seen or not name or not record["source_urls"]:
            raise ValueError(f"Invalid economic award record: {name}")
        if not 1969 <= record["award_year"] <= date.today().year:
            raise ValueError(f"Invalid economic award year: {name}")
        date.fromisoformat(record["reviewed_on"])
        seen.add(name)
    return records


def apply_awards(rows, columns, records=None):
    """Keep IDs/forms/photos; add curated entries only when not already present."""
    result = [dict(row) for row in rows]
    next_id = max((int(row["id"]) for row in result), default=-1) + 1
    for record in load_awards() if records is None else records:
        matching = [row for row in result if row["original"] == record["original"]]
        if not matching and "entry" in record:
            entry = record["entry"]
            for form in entry["forms"]:
                row = dict.fromkeys(columns, "")
                row.update({key: value for key, value in entry.items() if key != "forms"})
                row.update(form)
                row.update(id=str(next_id), original=record["original"],
                           field="経済学", celebrity_doctorate="no")
                matching.append(row)
                result.append(row)
            next_id += 1
        for row in matching:
            fields = [field for field in row.get("field", "").split("/")
                      if field and field != "NA"]
            if "経済学" not in fields:
                fields.append("経済学")
            row.update(field="/".join(fields), nobel="yes")
    return result
