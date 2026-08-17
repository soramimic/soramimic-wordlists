#!/usr/bin/env python3
"""レビュー済み台帳から、日本で馴染みのあるYouTuber人物を補完する。

チャンネル名は人物発見・本人確認と ``channel`` 付加列にだけ用いる。
``original`` / ``surface`` には、台帳でレビューした人物の活動名だけを収録する。

usage: python3 tools/update_youtuber_japan.py
"""

import argparse
import csv
import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "youtuber.csv"
PEOPLE_PATH = ROOT / "tools" / "youtuber_japan_people.json"
CHANNEL_SOURCES_PATH = ROOT / "tools" / "youtuber_channel_sources.jsonl"
CHANNEL_SHARED_COLUMN = "channel_shared"
CHANNEL_ID_RE = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
QID_RE = re.compile(r"^Q\d+$")
YEAR_RE = re.compile(r"^(?:NA|(?:19|20)\d{2})$")
MISSING = {None, "", "NA"}


class RosterConflict(ValueError):
    """台帳と既存人物・QID・チャンネルの対応が一意でない。"""


def _qid(value) -> str:
    value = str(value or "NA")
    return value if value != "NA" else "NA"


def load_people(path: Path = PEOPLE_PATH) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    people = payload.get("people") if isinstance(payload, dict) else None
    if payload.get("schema_version") != 1 or not isinstance(people, list):
        raise ValueError(f"{path}: 未対応の人物台帳形式")

    required = {
        "original", "pronunciation", "debut_year", "org", "description",
        "qid", "source_url", "channel_id", "channel_title", "channel_url",
        "channel_shared",
    }
    names, qids, channels = set(), set(), {}
    for pos, person in enumerate(people, 1):
        missing = sorted(required - person.keys())
        if missing:
            raise ValueError(f"{path}: people[{pos}]: 必須キー不足: {missing}")
        name = person["original"]
        qid = _qid(person["qid"])
        channel_id = person["channel_id"]
        if not name or name != name.strip() or name in names:
            raise RosterConflict(f"人物台帳の活動名が空または重複: {name!r}")
        if qid != "NA" and (not QID_RE.fullmatch(qid) or qid in qids):
            raise RosterConflict(f"人物台帳のQIDが不正または重複: {qid}")
        if not CHANNEL_ID_RE.fullmatch(channel_id):
            raise RosterConflict(f"人物台帳のチャンネルIDが不正: {channel_id}")
        if not isinstance(person["channel_shared"], bool):
            raise ValueError(f"{name}: channel_shared が真偽値ではない")
        if channel_id in channels:
            previous = channels[channel_id]
            if not previous["channel_shared"] or not person["channel_shared"]:
                raise RosterConflict(
                    f"人物台帳の個人チャンネルIDが重複: {channel_id}")
            for field in ("channel_title", "channel_url", "org"):
                if previous[field] != person[field]:
                    raise RosterConflict(
                        f"共有チャンネルの{field}が不一致: {channel_id}")
        if str(person["debut_year"]) != str(person["debut_year"]).strip() or \
                not YEAR_RE.fullmatch(str(person["debut_year"])):
            raise ValueError(f"{name}: 活動開始年が不正")
        if not person["pronunciation"] or not person["channel_title"]:
            raise ValueError(f"{name}: 読みまたはチャンネル名が空")
        expected_url = f"https://www.youtube.com/channel/{channel_id}"
        if person["channel_url"] != expected_url:
            raise ValueError(f"{name}: channel_urlとchannel_idが不一致")
        if not str(person["source_url"]).startswith("https://"):
            raise ValueError(f"{name}: source_urlがHTTPS URLではない")
        names.add(name)
        qids.add(qid)
        channels[channel_id] = person
    return people


def load_channel_sources(path: Path = CHANNEL_SOURCES_PATH) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: JSONが不正") from exc
    return records


def _person_indexes(rows: list[dict]) -> tuple[dict, dict, dict]:
    """name/qid -> id集合と id -> 代表行を返す。"""
    names, qids, by_id = {}, {}, {}
    for row in rows:
        pid = row.get("id", "")
        if not pid.isdigit():
            raise RosterConflict(f"既存CSVの人物IDが数値でない: {pid!r}")
        by_id.setdefault(pid, row)
        names.setdefault(row.get("original", ""), set()).add(pid)
        qid = _qid(row.get("wikidata"))
        if qid != "NA":
            if not QID_RE.fullmatch(qid):
                raise RosterConflict(f"既存CSVのQIDが不正: {qid}")
            qids.setdefault(qid, set()).add(pid)
    return names, qids, by_id


def apply_people(rows: list[dict], columns: list[str], people: list[dict],
                 channel_sources: list[dict], observed_on: str) -> tuple:
    """台帳をコピーへ反映し、(rows, sources, 新規人数, name->id)を返す。

    衝突時は入力を変更せず ``RosterConflict`` を送出する。
    """
    out_rows = deepcopy(rows)
    out_sources = deepcopy(channel_sources)
    out_columns = (columns if CHANNEL_SHARED_COLUMN in columns else
                   [*columns, CHANNEL_SHARED_COLUMN])
    for row in out_rows:
        if row.get(CHANNEL_SHARED_COLUMN) not in {"yes", "no", "NA"}:
            row[CHANNEL_SHARED_COLUMN] = "NA"
    names, qids, by_id = _person_indexes(out_rows)

    channel_owners = {}
    source_keys = {}
    for record in out_sources:
        channel_id = record.get("channel_id", "")
        pid = record.get("person_id", "")
        if not CHANNEL_ID_RE.fullmatch(channel_id) or not str(pid).isdigit():
            raise RosterConflict("既存チャンネル台帳に不正なIDがある")
        channel_owners.setdefault(channel_id, set()).add(str(pid))
        key = (str(pid), channel_id)
        source_keys.setdefault(key, []).append(record)

    # まず全人物の対応を確定する。ここでは入力もコピーも書き換えない。
    ids, effective_qids = {}, {}
    next_id = max((int(pid) for pid in by_id), default=-1) + 1
    for person in people:
        name, qid = person["original"], _qid(person["qid"])
        name_ids = names.get(name, set())
        qid_ids = qids.get(qid, set()) if qid != "NA" else set()
        if len(name_ids) > 1:
            raise RosterConflict(f"同じ活動名が複数人物IDに存在: {name}")
        if len(qid_ids) > 1:
            raise RosterConflict(f"同じQIDが複数人物IDに存在: {qid}")
        if name_ids and qid_ids and name_ids != qid_ids:
            raise RosterConflict(f"活動名とQIDが別人物を指す: {name} / {qid}")
        if qid_ids and not name_ids:
            existing = by_id[next(iter(qid_ids))].get("original", "")
            raise RosterConflict(f"QIDが別の活動名で存在: {qid}: {existing} / {name}")
        pid = next(iter(name_ids)) if name_ids else str(next_id)
        if not name_ids:
            next_id += 1
        owners = channel_owners.get(person["channel_id"], set())
        if not person["channel_shared"]:
            if owners - {pid}:
                raise RosterConflict(
                    f"チャンネルが別人物に紐づく: {person['channel_id']}: "
                    f"{sorted(owners)} / {pid}")
        if len(source_keys.get((pid, person["channel_id"]), [])) > 1:
            raise RosterConflict(
                f"対象チャンネル根拠が重複: person_id={pid} "
                f"{person['channel_id']}")
        if name_ids:
            categories = {
                row.get("category") for row in out_rows if row.get("id") == pid
            }
            if categories - {"youtuber"}:
                raise RosterConflict(
                    f"同名の既存人物がYouTuberではない: {name}: {sorted(categories)}")
            existing_qids = {
                _qid(row.get("wikidata")) for row in out_rows
                if row.get("id") == pid and _qid(row.get("wikidata")) != "NA"
            }
            if qid != "NA" and existing_qids and existing_qids != {qid}:
                raise RosterConflict(f"既存人物のQIDと台帳が不一致: {name}")
        ids[name] = pid
        effective_qids[name] = (next(iter(existing_qids))
                                if name_ids and existing_qids else qid)

        existing_sources = source_keys.get((pid, person["channel_id"]), [])
        if existing_sources:
            record = existing_sources[0]
            if record.get("original") != name or \
                    _qid(record.get("qid")) != effective_qids[name]:
                raise RosterConflict(
                    f"対象チャンネル根拠の人物対応が不一致: {name}")
            if person["channel_shared"]:
                decision = record.get("decision")
                if decision == "verified":
                    # 旧形式で個人チャンネル扱いだったレビュー済み
                    # 台帳と人物/QID/チャンネルが一致するレコードだけを、
                    # 登録者数非対象へ移行する。
                    record["decision"] = "verified_shared_group_channel"
                elif decision != "verified_shared_group_channel":
                    raise RosterConflict(
                        f"共有チャンネル根拠のdecisionが不正: {name}")

    added = 0
    for person in people:
        name, pid = person["original"], ids[person["original"]]
        if name not in names:
            row = {column: "" for column in out_columns}
            row.update({
                "id": pid,
                "original": name,
                "surface": name,
                "pronunciation": person["pronunciation"],
                "type": "full",
                "category": "youtuber",
                "org": person["org"],
                "debut_year": str(person["debut_year"]),
                "status": "current",
                "wikidata": _qid(person["qid"]),
                "channel": person["channel_title"],
                "description": person["description"],
                "subscribers": "NA",
                "subscribers_as_of": "NA",
                CHANNEL_SHARED_COLUMN: ("yes" if person["channel_shared"]
                                        else "no"),
            })
            if "scope" in columns:
                row["scope"] = "japan"
            out_rows.append(row)
            names[name] = {pid}
            by_id[pid] = row
            added += 1
        else:
            # 既存人物の表記・読み・個人チャンネルは維持し、公式人物台帳で
            # 確認できた欠損メタデータだけを補完する。
            for row in out_rows:
                if row.get("id") != pid:
                    continue
                for field in ("org", "debut_year", "channel", "description"):
                    value = (person["channel_title"] if field == "channel"
                             else person[field])
                    if row.get(field) in MISSING and value not in MISSING:
                        row[field] = str(value)
                row[CHANNEL_SHARED_COLUMN] = (
                    "yes" if person["channel_shared"] and
                    row.get("channel") == person["channel_title"] else "no")
                if "scope" in columns and row.get("scope") in MISSING | {"unknown"}:
                    row["scope"] = "japan"

        key = (pid, person["channel_id"])
        # グループ共有チャンネルは本人確認には使うが、個人の登録者数として
        # 集計しないことを decision に永続的に記録する。
        if key not in source_keys:
            record = {
                "channel_id": person["channel_id"],
                "channel_title": person["channel_title"],
                "decision": ("verified_shared_group_channel"
                             if person["channel_shared"] else "verified"),
                "evidence_url": person["channel_url"],
                "identity_basis": "reviewed_person_source_and_official_channel",
                "observed_on": observed_on,
                "original": name,
                "person_id": pid,
                "qid": effective_qids[name],
                "source_type": "reviewed_person_roster",
                "source_url": person["source_url"],
            }
            out_sources.append(record)
            source_keys[key] = [record]

    out_sources.sort(key=lambda r: (int(r["person_id"]), r["channel_id"]))
    return out_rows, out_sources, added, ids


def _write_atomic(path: Path, render) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                    dir=path.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        render(tmp)
        if path.exists():
            os.chmod(tmp, path.stat().st_mode)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    def render(tmp):
        with tmp.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns,
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        # リポジトリ内CSVの規約に合わせ、末尾改行は付けない。
        data = tmp.read_bytes()
        if data.endswith(b"\n"):
            tmp.write_bytes(data[:-1])
    _write_atomic(path, render)


def write_jsonl(path: Path, records: list[dict]) -> None:
    def render(tmp):
        with tmp.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False,
                                        sort_keys=True) + "\n")
    _write_atomic(path, render)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--people", type=Path, default=PEOPLE_PATH)
    parser.add_argument("--channel-sources", type=Path,
                        default=CHANNEL_SOURCES_PATH)
    parser.add_argument("--observed-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    with args.csv.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows, columns = list(reader), list(reader.fieldnames or [])
    if CHANNEL_SHARED_COLUMN not in columns:
        columns.append(CHANNEL_SHARED_COLUMN)
    people = load_people(args.people)
    sources = load_channel_sources(args.channel_sources)
    updated_rows, updated_sources, added, _ids = apply_people(
        rows, columns, people, sources, args.observed_on)
    write_csv(args.csv, columns, updated_rows)
    write_jsonl(args.channel_sources, updated_sources)
    print(f"日本向けレビュー済み人物: {len(people)}人、新規 {added}人")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
