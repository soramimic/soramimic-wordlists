"""Check automatic creator updates against the published subscriber snapshots."""

import argparse
import csv
from datetime import date, datetime, timezone
import io
import math
from pathlib import Path
import subprocess

from creator_csv import subscriber_band

ROOT = Path(__file__).resolve().parent.parent
FILES = ("youtuber.csv", "vtuber.csv")
ALLOWED_PATHS = set(FILES) | {
    "tools/youtuber_channel_sources.jsonl",
    "tools/youtuber_channel_candidates.jsonl",
}
MUTABLE = {"channel", "channel_shared", "subscribers", "subscribers_as_of",
           "subscriber_band"}


def read_snapshot(text):
    reader = csv.DictReader(io.StringIO(text))
    return reader.fieldnames, list(reader)


def check_snapshots(before, after, *, require_current=False, today=None):
    today = today or datetime.now(timezone.utc).date().isoformat()
    old_people, new_people = {}, {}
    for name in FILES:
        old_columns, old_rows = read_snapshot(before[name])
        new_columns, new_rows = read_snapshot(after[name])
        if require_current:
            if old_columns != new_columns or len(old_rows) != len(new_rows):
                raise ValueError(f"{name}: subscriber refresh changed schema or rows")
            for old, new in zip(old_rows, new_rows):
                if any(old[key] != new[key] for key in old_columns
                       if key not in MUTABLE):
                    raise ValueError(f"{name}: unrelated creator fields changed")
                if old["channel"] not in ("", "NA", new["channel"]):
                    raise ValueError(f"{name}: existing channel was overwritten")
        for rows, people in ((old_rows, old_people), (new_rows, new_people)):
            for row in rows:
                snapshot = tuple(row.get(key, "NA") for key in
                                 ("channel", "subscribers", "subscribers_as_of"))
                if people.setdefault(row["id"], snapshot) != snapshot:
                    raise ValueError(f"{name}: inconsistent aliases: {row['id']}")
        for row in new_rows:
            count, as_of = row["subscribers"], row["subscribers_as_of"]
            if count == "NA":
                if as_of != "NA":
                    raise ValueError("unknown count has a retrieval date")
            elif (not count.isascii() or not count.isdecimal()
                  or date.fromisoformat(as_of).isoformat() != as_of
                  or as_of > today):
                raise ValueError("invalid subscriber count or retrieval date")
            if row["subscriber_band"] != subscriber_band(count):
                raise ValueError("subscriber band does not match the count")
    if not old_people.keys() <= new_people.keys():
        raise ValueError("existing creators were removed")
    known = {pid for pid, (_, count, _) in old_people.items() if count != "NA"}
    for pid in known:
        _, count, as_of = new_people[pid]
        if count == "NA" or as_of < old_people[pid][2]:
            raise ValueError(f"published subscriber snapshot regressed: {pid}")
    fresh = sum(new_people[pid][2] == today for pid in known)
    if require_current and (not known or fresh < math.ceil(len(known) * 0.95)):
        raise ValueError("fewer than 95% of published counts were refreshed today")
    return fresh, len(known)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--require-current", action="store_true")
    args = parser.parse_args(argv)
    base = subprocess.check_output(
        ["git", "rev-parse", "--verify", args.base_ref + "^{commit}"],
        cwd=ROOT, text=True).strip()
    if args.require_current:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", base], cwd=ROOT, text=True).splitlines()
        if set(changed) - ALLOWED_PATHS:
            raise SystemExit("subscriber refresh changed files outside its scope")
    before = {name: subprocess.check_output(
        ["git", "show", f"{base}:{name}"], cwd=ROOT, text=True) for name in FILES}
    after = {name: (ROOT / name).read_text(encoding="utf-8") for name in FILES}
    try:
        fresh, known = check_snapshots(before, after, require_current=args.require_current)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(f"Subscriber snapshots OK: {fresh}/{known} published counts dated today")


if __name__ == "__main__":
    main()
