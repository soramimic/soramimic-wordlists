#!/usr/bin/env python3
"""WoRMSの検証済み分類・Traitsから海の生き物の説明を再生成する。

配布時やCIはネットワークへ接続しない。明示的にこのスクリプトを実行したときだけ
WoRMS REST APIを参照し、説明に実際に使う最小限の根拠を
``marine_life_description_sources.jsonl`` へ固定する。そのスナップショットから
``marine_life_source.csv`` の説明を決定的に更新する。

usage:
    python3 tools/enrich_marine_life_descriptions.py
    python3 tools/enrich_marine_life_descriptions.py --workers 6
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import io
import json
import threading
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import update_marine_life as marine

API_BASE = "https://www.marinespecies.org/rest"
USER_AGENT = (
    "soramimic-wordlists-marine-description/1.0 "
    "(+https://github.com/soramimic/soramimic-wordlists)"
)
DEFAULT_CACHE = Path(__file__).with_name(".cache") / "marine_life_descriptions"
RETRIES = 4
REQUEST_DELAY = 0.0
_request_lock = threading.Lock()
_next_request_at = 0.0


def wait_for_request_slot() -> None:
    """並列worker全体でAPI開始間隔を空け、WoRMSへ集中アクセスしない。"""
    global _next_request_at
    with _request_lock:
        now = time.monotonic()
        if now < _next_request_at:
            time.sleep(_next_request_at - now)
        _next_request_at = time.monotonic() + REQUEST_DELAY


def fetch_json(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            wait_for_request_slot()
            with urllib.request.urlopen(request, timeout=45) as response:
                if response.status == 204:
                    return []
                return json.load(response)
        except Exception as exc:  # urllibはHTTP・TLS・timeoutで例外型が分かれる
            error = exc
            if attempt + 1 < RETRIES:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"WoRMS APIの取得に失敗しました: {url} ({error})")


def load_cached_json(path: Path, url: str, refresh: bool = False) -> object:
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch_json(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    marine.write_atomic(
        path,
        json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    )
    return data


def fetch_records(
    rows: list[dict[str, str]], cache: Path, refresh: bool = False
) -> dict[str, dict]:
    """AphiaRecordを50件ずつ取得し、AphiaIDごとのキャッシュへ分けて保存する。"""
    out: dict[str, dict] = {}
    missing: list[str] = []
    for row in rows:
        aphia_id = row["aphia_id"]
        path = cache / "records" / f"{aphia_id}.json"
        if path.exists() and not refresh:
            out[aphia_id] = json.loads(path.read_text(encoding="utf-8"))
        else:
            missing.append(aphia_id)
    for start in range(0, len(missing), 50):
        ids = missing[start:start + 50]
        query = urllib.parse.urlencode([("aphiaids[]", value) for value in ids])
        url = f"{API_BASE}/AphiaRecordsByAphiaIDs?{query}"
        records = fetch_json(url)
        if not isinstance(records, list) or len(records) != len(ids):
            raise RuntimeError(f"WoRMS AphiaRecordの応答件数が不正です: {len(ids)}件 ({url})")
        returned = {
            str(record.get("AphiaID")): record
            for record in records
            if isinstance(record, dict)
        }
        for aphia_id in ids:
            record = returned.get(aphia_id)
            if not isinstance(record, dict):
                raise RuntimeError(f"WoRMS AphiaRecordが空です: {aphia_id}")
            path = cache / "records" / f"{aphia_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            marine.write_atomic(
                path,
                json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            )
            out[aphia_id] = record
        print(f"分類レコード: {min(start + len(ids), len(missing))}/{len(missing)}")
    return out


def fetch_attributes(
    row: dict[str, str], cache: Path, refresh: bool = False
) -> tuple[str, list[dict]]:
    aphia_id = row["aphia_id"]
    url = f"{API_BASE}/AphiaAttributesByAphiaID/{aphia_id}"
    data = load_cached_json(cache / "attributes" / f"{aphia_id}.json", url, refresh)
    if not isinstance(data, list):
        raise RuntimeError(f"WoRMS Traitsの応答が配列ではありません: {aphia_id}")
    return aphia_id, data


def walk_attributes(attributes: list[dict]):
    stack = list(attributes)
    while stack:
        item = stack.pop()
        yield item
        stack.extend(item.get("children") or [])


def child_value(attribute: dict, measurement_type: str) -> str:
    for child in walk_attributes(attribute.get("children") or []):
        if child.get("measurementType") == measurement_type:
            return str(child.get("measurementValue") or "").strip()
    return ""


def numeric(value: object) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def length_in_mm(value: float, unit: str) -> float | None:
    factors = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "µm": 0.001, "um": 0.001}
    factor = factors.get(unit.strip())
    return value * factor if factor else None


def select_maximum_length(attributes: list[dict], aphia_id: str) -> dict | None:
    candidates: list[tuple[int, float, dict]] = []
    for item in attributes:
        if item.get("measurementType") != "Body size":
            continue
        if str(item.get("AphiaID_Inherited")) != aphia_id:
            continue
        value = numeric(item.get("measurementValue"))
        unit = child_value(item, "Unit")
        size_mm = length_in_mm(value, unit) if value is not None else None
        if size_mm is None or child_value(item, "Dimension").lower() != "length":
            continue
        size_type = child_value(item, "Type").lower()
        if size_type and size_type != "maximum":
            continue
        quality = str(item.get("qualitystatus") or "")
        priority = 1 if quality == "checked" else 0
        candidates.append((priority, size_mm, item))
    if not candidates:
        return None
    _priority, _size, item = max(candidates, key=lambda value: (value[0], value[1]))
    return {
        "value": str(item["measurementValue"]),
        "unit": child_value(item, "Unit"),
        "type": "maximum_length",
        "quality_status": str(item.get("qualitystatus") or ""),
        "source_id": item.get("source_id"),
        "reference": str(item.get("reference") or ""),
    }


def select_iucn(attributes: list[dict], aphia_id: str) -> dict | None:
    candidates: list[dict] = []
    for item in walk_attributes(attributes):
        if item.get("measurementType") != "IUCN Red List Category":
            continue
        if str(item.get("AphiaID_Inherited")) != aphia_id:
            continue
        category = str(item.get("measurementValue") or "").strip()
        if not category:
            continue
        candidates.append({
            "category": category,
            "year": child_value(item, "Year Assessed"),
            "type": "iucn_status",
            "quality_status": str(item.get("qualitystatus") or ""),
            "source_id": item.get("source_id"),
            "reference": str(item.get("reference") or ""),
        })
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: int(item["year"]) if str(item["year"]).isdigit() else 0,
    )


def evidence_for(
    row: dict[str, str], record: dict, attributes: list[dict], fetched_at: str
) -> dict:
    aphia_id = row["aphia_id"]
    traits = []
    maximum_length = select_maximum_length(attributes, aphia_id)
    if maximum_length:
        traits.append(maximum_length)
    iucn = select_iucn(attributes, aphia_id)
    if iucn:
        traits.append(iucn)
    return {
        "name": row["name"],
        "aphia_id": aphia_id,
        "scientific_name": row["scientific_name"],
        "fetched_at": fetched_at,
        "record_url": str(record.get("url") or ""),
        "attributes_url": f"{API_BASE}/AphiaAttributesByAphiaID/{aphia_id}",
        "status": str(record.get("status") or ""),
        "rank": str(record.get("rank") or ""),
        "is_marine": record.get("isMarine"),
        "valid_aphia_id": record.get("valid_AphiaID"),
        "valid_name": str(record.get("valid_name") or ""),
        "traits": traits,
    }


def validate_record(row: dict[str, str], record: dict) -> None:
    aphia_id = int(row["aphia_id"])
    problems = []
    allowed_status = {"accepted", *marine.UNCERTAIN_STATUS_JA}
    if record.get("status") not in allowed_status:
        problems.append(f"status={record.get('status')}")
    if record.get("rank") not in {"Species", "Subspecies"}:
        problems.append(f"rank={record.get('rank')}")
    if record.get("isMarine") != 1:
        problems.append(f"isMarine={record.get('isMarine')}")
    if record.get("valid_AphiaID") != aphia_id:
        problems.append(f"valid_AphiaID={record.get('valid_AphiaID')}")
    if record.get("valid_name") != row["scientific_name"]:
        problems.append(f"valid_name={record.get('valid_name')}")
    if problems:
        raise ValueError(f"WoRMS分類が台帳と一致しません: {row['name']} ({', '.join(problems)})")


def write_source(rows: list[dict[str, str]], path: Path = marine.SOURCE) -> None:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=marine.SOURCE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    raw = out.getvalue().rstrip("\n").encode("utf-8")
    if b'"' in raw or b"\r" in raw:
        raise ValueError("更新後のsource CSVに引用符またはCRが含まれます")
    marine.write_atomic(path, raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--request-delay", type=float, default=0.25,
        help="WoRMS APIのリクエスト開始間隔（秒、全worker共通）",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--fetched-at", default=date.today().isoformat())
    args = parser.parse_args(argv)
    if args.workers < 1 or args.workers > 12:
        parser.error("--workers は1〜12で指定してください")
    if args.request_delay < 0:
        parser.error("--request-delay は0以上で指定してください")
    try:
        date.fromisoformat(args.fetched_at)
    except ValueError:
        parser.error("--fetched-at はYYYY-MM-DDで指定してください")
    global REQUEST_DELAY
    REQUEST_DELAY = args.request_delay

    rows = marine.load_source()
    targets = [
        row for row in rows if int(row["id"]) >= marine.AUTO_DESCRIPTION_START_ID
    ]
    if any(not row["aphia_id"] or not row["scientific_name"] for row in targets):
        raise ValueError("自動説明の対象にはAphiaIDと学名が必要です")
    records = fetch_records(targets, args.cache, args.refresh)

    attributes_by_id: dict[str, list[dict]] = {}
    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(fetch_attributes, row, args.cache, args.refresh)
            for row in targets
        ]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                aphia_id, attributes = future.result()
                attributes_by_id[aphia_id] = attributes
            except Exception as exc:
                failures.append(str(exc))
            if index % 100 == 0 or index == len(futures):
                print(f"Traits: {index}/{len(futures)}")
    if failures:
        sample = "\n".join(failures[:10])
        raise RuntimeError(
            f"Traitsを取得できなかった行が{len(failures)}件あります。再実行してください。\n{sample}"
        )

    evidence = []
    for row in targets:
        record = records[row["aphia_id"]]
        validate_record(row, record)
        item = evidence_for(
            row, record, attributes_by_id[row["aphia_id"]], args.fetched_at
        )
        evidence.append(item)
        row["description"] = marine.description_from_evidence(row, item)

    lines = [
        json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        for item in evidence
    ]
    marine.write_atomic(marine.DESCRIPTION_SOURCES, "\n".join(lines).encode("utf-8"))
    write_source(rows)
    marine.validate_description_sources(rows)
    generated = marine.generate(rows)
    marine.write_atomic(marine.OUTPUT, generated)

    trait_counts: dict[str, int] = {}
    for item in evidence:
        for trait in item["traits"]:
            trait_counts[trait["type"]] = trait_counts.get(trait["type"], 0) + 1
    print(
        f"説明を更新しました: {len(evidence)}件 "
        + " ".join(f"{key}={value}" for key, value in sorted(trait_counts.items()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
