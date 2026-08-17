#!/usr/bin/env python3
"""youtuber.csv に日本向け利用のための scope を付与する。

scope は知名度や国籍そのものではなく、人物の主な活動圏を絞り込むための保守的な
区分である。レビュー済み override、公式事務所の国内外区分、Wikidata の国籍の順で
判定し、根拠が足りない人物は unknown にする。日本語 Wikipedia 記事があることや
日本語表記の名前だけでは japan にしない。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import sparql, write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "youtuber.csv"
OVERRIDES_PATH = Path(__file__).resolve().parent / "youtuber_scope_overrides.json"
SCOPES = {"japan", "global", "unknown"}
JAPAN_QID = "Q17"
QID_RE = re.compile(r"^Q[1-9][0-9]*$")

# 海外支部を先に判定する。たとえば「ホロライブプロダクション」と
# 「hololive English」を併記する行を国内扱いしないため。
GLOBAL_ORG_MARKERS = (
    "NIJISANJI EN", "hololive English", "ホロライブEnglish",
    "ホロライブインドネシア", "hololive Indonesia", "VShojo",
)
GLOBAL_CHANNEL_MARKERS = (
    "hololive-EN", "hololive-ID", "NIJISANJI EN",
)
JAPAN_ORG_MARKERS = (
    "にじさんじ", "ホロライブ", "hololive DEV_IS", "あおぎり高校",
    "ぶいすぽっ!", ".LIVE", "ななしいんく", "V.W.P", "フィッシャーズ",
    "東海オンエア", "水溜りボンド", "スカイピース", "QuizKnock", "コムドット",
)


def load_overrides(path: Path = OVERRIDES_PATH) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("people", [])
    result: dict[str, dict] = {}
    required = {"original", "scope", "basis", "evidence_url", "reviewed"}
    for index, record in enumerate(records, 1):
        missing = required - set(record)
        if missing:
            raise SystemExit(
                f"error: scope override {index} に {sorted(missing)[0]} がない")
        original = record["original"]
        if not original or original in result:
            raise SystemExit(f"error: scope override の人物名が空または重複: {original}")
        if record["scope"] not in SCOPES:
            raise SystemExit(f"error: {original} の scope が不正: {record['scope']}")
        if not record["basis"] or not record["evidence_url"].startswith("https://"):
            raise SystemExit(f"error: {original} の scope 根拠が不正")
        if not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", record["reviewed"]):
            raise SystemExit(f"error: {original} の reviewed が不正")
        result[original] = record
    return result


def fetch_citizenships(qids: list[str]) -> dict[str, set[str]]:
    """QID -> 国籍(P27)QID集合。国籍なしも空集合として返す。"""
    result = {qid: set() for qid in qids}
    for start in range(0, len(qids), 200):
        batch = qids[start:start + 200]
        values = " ".join(f"wd:{qid}" for qid in batch)
        query = f"""
SELECT ?p ?country WHERE {{
  VALUES ?p {{ {values} }}
  OPTIONAL {{ ?p wdt:P27 ?country }}
}}"""
        for binding in sparql(query)["results"]["bindings"]:
            qid = binding["p"]["value"].rsplit("/", 1)[1]
            if "country" in binding:
                result[qid].add(
                    binding["country"]["value"].rsplit("/", 1)[1])
        print(f"  scope属性取得 {min(start + 200, len(qids))}/{len(qids)}",
              flush=True)
    return result


def infer_scope(row: dict[str, str], countries: set[str],
                overrides: dict[str, dict]) -> str:
    original = row.get("original", "")
    if original in overrides:
        return overrides[original]["scope"]
    org = row.get("org", "")
    channel = row.get("channel", "")
    if (any(marker in org for marker in GLOBAL_ORG_MARKERS)
            or any(marker in channel for marker in GLOBAL_CHANNEL_MARKERS)):
        return "global"
    if any(marker in org for marker in JAPAN_ORG_MARKERS):
        return "japan"
    if JAPAN_QID in countries:
        return "japan"
    if countries:
        return "global"
    return "unknown"


def apply_scopes(rows: list[dict[str, str]], columns: list[str],
                 citizenships: dict[str, set[str]],
                 overrides: dict[str, dict]) -> tuple[list[str], dict[str, int]]:
    if "scope" not in columns:
        columns = columns + ["scope"]
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["id"], []).append(row)
    counts = {scope: 0 for scope in sorted(SCOPES)}
    for person_id, person_rows in grouped.items():
        originals = {row["original"] for row in person_rows}
        qids = {row.get("wikidata", "") for row in person_rows
                if QID_RE.fullmatch(row.get("wikidata", ""))}
        if len(originals) != 1 or len(qids) > 1:
            raise SystemExit(f"error: id={person_id} の人物対応が不整合")
        representative = person_rows[0]
        countries = citizenships.get(next(iter(qids), ""), set())
        scope = infer_scope(representative, countries, overrides)
        for row in person_rows:
            row["scope"] = scope
        counts[scope] += 1
    return columns, counts


def update(path: Path = CSV_PATH, overrides_path: Path = OVERRIDES_PATH) -> dict[str, int]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        columns = list(reader.fieldnames or [])
    overrides = load_overrides(overrides_path)
    qids = sorted({row.get("wikidata", "") for row in rows
                   if QID_RE.fullmatch(row.get("wikidata", ""))})
    citizenships = fetch_citizenships(qids)
    columns, counts = apply_scopes(rows, columns, citizenships, overrides)
    write_csv_no_trailing_newline(path, columns, rows)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--overrides", type=Path, default=OVERRIDES_PATH)
    args = parser.parse_args()
    counts = update(args.csv, args.overrides)
    print("youtuber.csv scope: " + ", ".join(
        f"{scope}={counts[scope]}" for scope in ("japan", "global", "unknown")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
