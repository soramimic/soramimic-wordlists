"""Apply the reviewed, opt-in doctorate-holder entries without network access."""

import argparse
import csv
import json
import re
from pathlib import Path

from wpnames import write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path(__file__).with_suffix(".json")
FLAG = "celebrity_doctorate"


def load_entries(path=MANIFEST):
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    ids, names = set(), set()
    for entry in entries:
        person_id, name = entry["id"], entry["original"]
        if not re.fullmatch(r"[0-9]+", person_id) or person_id in ids or name in names:
            raise ValueError(f"duplicate or invalid celebrity identity: {person_id} {name}")
        ids.add(person_id)
        names.add(name)
        if (entry["degree_kind"] != "earned_doctorate" or not entry["degree"]
                or not entry["source_urls"] or not entry["reviewed_on"]):
            raise ValueError(f"missing earned doctorate evidence: {name}")
        if not all(url.startswith("https://") for url in entry["source_urls"]):
            raise ValueError(f"invalid source URL: {name}")
        seen = set()
        for form in entry["forms"]:
            key = (form["surface"], form["pronunciation"], form["type"])
            if key in seen or form["type"] not in {"family", "given", "full"}:
                raise ValueError(f"duplicate or invalid name form: {name}")
            seen.add(key)
            if not re.fullmatch(r"[ァ-ヺー・＝]+", form["pronunciation"]):
                raise ValueError(f"invalid pronunciation: {name}")
        if not any(form["type"] == "full" for form in entry["forms"]):
            raise ValueError(f"missing full name: {name}")
        for value in [name, entry["field"], entry["description"],
                      *(v for form in entry["forms"] for v in form.values())]:
            if not value or any(c in value for c in ',"\r\n\t'):
                raise ValueError(f"unsafe CSV value: {name}")
    return entries


def apply_entries(rows, columns, entries):
    """Preserve existing IDs, forms and metadata; append only reviewed new people."""
    result = [dict(row) for row in rows]
    by_id, by_name = {}, {}
    for row in result:
        by_id.setdefault(row["id"], []).append(row)
        by_name.setdefault(row["original"], set()).add(row["id"])
        if row.get(FLAG) in (None, "", "NA"):
            row[FLAG] = "no"
    for entry in entries:
        person_id, name = entry["id"], entry["original"]
        current = by_id.get(person_id, [])
        if (any(row["original"] != name for row in current)
                or by_name.get(name, {person_id}) != {person_id}):
            raise ValueError(f"celebrity ID/name conflict: {person_id} {name}")
        if not current:
            base = dict.fromkeys(columns, "NA")
            base.update(id=person_id, original=name, field=entry["field"],
                        description=entry["description"], image="", image_page="",
                        nobel="no", status="存命")
            current = [dict(base, **form) for form in entry["forms"]]
            result.extend(current)
        for row in current:
            row[FLAG] = "yes"
    return result


def validate_flags(rows, entries):
    reviewed = {entry["id"]: entry["original"] for entry in entries}
    found = set()
    for row in rows:
        person_id, name = row["id"], row["original"]
        expected = "yes" if reviewed.get(person_id) == name else "no"
        if row.get(FLAG) != expected:
            raise ValueError(f"{name}: {FLAG} must be {expected}")
        if person_id in reviewed:
            if reviewed[person_id] != name:
                raise ValueError(f"celebrity ID/name conflict: {person_id} {name}")
            found.add(person_id)
    if found != set(reviewed):
        raise ValueError(f"missing reviewed celebrity IDs: {sorted(set(reviewed) - found)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "scientist.csv"
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        columns, rows = list(reader.fieldnames), list(reader)
    if FLAG not in columns:
        columns.append(FLAG)
    entries = load_entries()
    updated = apply_entries(rows, columns, entries)
    validate_flags(updated, entries)
    if args.check:
        if rows != updated:
            raise SystemExit("scientist.csv: reviewed doctorate entries need applying")
    else:
        write_csv_no_trailing_newline(path, columns, updated)
    print(f"scientist.csv: {len(entries)} reviewed doctorate holders; {len(updated)} rows")


if __name__ == "__main__":
    main()
