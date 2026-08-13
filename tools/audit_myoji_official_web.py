#!/usr/bin/env python3
"""名字読みの公式Web確認バッチを準備・検証・根拠台帳へ反映する。

検索そのものは検索エンジンと人によるページ確認で行う。ここでは候補スナップショットを
固定し、全候補に調査結果があることと、正例の根拠メタデータを機械検証する。

usage:
  python tools/audit_myoji_official_web.py prepare --batch 2026-08-13 --limit 225
  python tools/audit_myoji_official_web.py validate --all
  python tools/audit_myoji_official_web.py promote --batch 2026-08-13
"""

import argparse
import csv
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from update_myoji import (
    HIRA2KATA,
    OFFICIAL_EVIDENCE_PATH,
    OFFICIAL_SOURCE_TYPES,
    clean_surname,
    load_official_evidence,
)
from wpnames import write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "myoji.csv"
BATCH_DIR = Path(__file__).resolve().parent / "myoji_official_search_batches"
DEFAULT_BATCH = datetime.now(timezone.utc).date().isoformat()
CANDIDATE_COLUMNS = ("batch_index", "id", "surface", "pronunciation", "rank",
                     "query")
SEARCH_STATUSES = frozenset(("verified", "no_support_found", "ambiguous"))
KATA2HIRA = str.maketrans(
    {chr(code): chr(code - 0x60) for code in range(ord("ァ"), ord("ヶ") + 1)})
REQUIRED_SEARCH_KEYS = frozenset((
    "batch_index", "surface", "pronunciation", "rank", "searched_on", "query",
    "status", "source_url", "source_type", "source_title", "observed_surface",
    "observed_reading", "locator", "notes",
))
URL_RE = re.compile(r"https://[^\s]+")


def select_candidates(path: Path = CSV_PATH, limit: int = 225,
                      excluded: set[tuple[str, str]] | None = None) -> list[dict]:
    """順位付き・JMnedict一致済みの未確認読みを上位から固定する。"""
    excluded = set() if excluded is None else excluded
    with path.open(encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh)
                if r["verified"] == "no" and r["rank"]
                and "jmnedict" in r["evidence_sources"].split("|")
                and (r["original"], r["pronunciation"]) not in excluded]
    rows.sort(key=lambda r: (int(r["rank"]), int(r["id"]), r["pronunciation"]))
    result = []
    for index, row in enumerate(rows[:limit]):
        hira = row["pronunciation"].translate(KATA2HIRA)
        # 検索者はこの基本形に site:go.jp 等を足してよい。
        query = f'{row["original"]} {hira} 氏名'
        result.append({
            "batch_index": str(index), "id": row["id"],
            "surface": row["original"], "pronunciation": row["pronunciation"],
            "rank": row["rank"], "query": query,
        })
    return result


def candidates_path(batch: str) -> Path:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-[a-z0-9]+)?", batch):
        raise RuntimeError("batchはYYYY-MM-DDまたはYYYY-MM-DD-suffix形式にする")
    return BATCH_DIR / f"{batch}-candidates.csv"


def searched_pairs() -> set[tuple[str, str]]:
    """過去ログにある候補を返し、新しいバッチでの再検索を避ける。"""
    pairs = set()
    for path in sorted(BATCH_DIR.glob("*-?.jsonl")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                pairs.add((str(record["surface"]), str(record["pronunciation"])))
            except (json.JSONDecodeError, KeyError) as exc:
                raise RuntimeError(f"{path.name}:{lineno}: 過去ログが不正") from exc
    return pairs


def prepare(limit: int, batch: str) -> None:
    path = candidates_path(batch)
    if path.exists():
        raise RuntimeError(f"候補スナップショットは上書きしない: {path}")
    rows = select_candidates(limit=limit, excluded=searched_pairs())
    if len(rows) != limit:
        raise RuntimeError(f"候補不足: {len(rows)} / {limit}")
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    write_csv_no_trailing_newline(path, CANDIDATE_COLUMNS, rows)
    print(f"検索候補を固定: {path} ({len(rows)}件)")


def load_candidates(path: Path) -> dict[int, dict]:
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    indexes = [int(r["batch_index"]) for r in rows]
    if indexes != list(range(len(rows))):
        raise RuntimeError("候補のbatch_indexが連番でない")
    return {int(r["batch_index"]): r for r in rows}


def result_paths(batch: str) -> list[Path]:
    return sorted(BATCH_DIR.glob(f"{batch}-[a-z].jsonl"))


def _parse_date(value: object, where: str) -> date:
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as exc:
        raise RuntimeError(f"{where}: 日付が不正") from exc
    if parsed > datetime.now(timezone.utc).date():
        raise RuntimeError(f"{where}: 未来の日付")
    return parsed


def load_results(candidates: dict[int, dict], paths: list[Path] | None = None,
                 require_complete: bool = True) -> list[dict]:
    """検索ログを候補スナップショットと突き合わせる。"""
    if paths is None:
        raise RuntimeError("検索結果ファイルを明示する")
    records = []
    seen = set()
    for path in paths:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            where = f"{path.name}:{lineno}"
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{where}: JSONが不正") from exc
            missing = REQUIRED_SEARCH_KEYS - set(record)
            if missing:
                raise RuntimeError(f"{where}: 必須キー不足: {sorted(missing)}")
            try:
                index = int(record["batch_index"])
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"{where}: batch_indexが不正") from exc
            if index in seen:
                raise RuntimeError(f"{where}: batch_indexが重複")
            seen.add(index)
            candidate = candidates.get(index)
            if candidate is None:
                raise RuntimeError(f"{where}: 候補外のbatch_index")
            for key in ("surface", "pronunciation", "rank"):
                if str(record[key]) != candidate[key]:
                    raise RuntimeError(f"{where}: 候補の{key}と不一致")
            if not str(record["query"]).strip():
                raise RuntimeError(f"{where}: queryが空")
            _parse_date(record["searched_on"], where)
            status = record["status"]
            if status not in SEARCH_STATUSES:
                raise RuntimeError(f"{where}: statusが不正")
            source_keys = ("source_url", "source_type", "source_title",
                           "observed_surface", "observed_reading", "locator")
            if status == "verified":
                if not all(str(record[k]).strip() for k in source_keys):
                    raise RuntimeError(f"{where}: verifiedの根拠欄が空")
                if not URL_RE.fullmatch(str(record["source_url"])):
                    raise RuntimeError(f"{where}: HTTPS URLでない")
                if record["source_type"] not in OFFICIAL_SOURCE_TYPES:
                    raise RuntimeError(f"{where}: source_typeが不正")
                observed = (
                    str(record["observed_surface"]).strip(),
                    str(record["observed_reading"]).replace(" ", "").strip()
                    .translate(HIRA2KATA),
                )
                expected = (candidate["surface"], candidate["pronunciation"])
                if observed != expected or not clean_surname(*expected):
                    raise RuntimeError(f"{where}: 掲載表記・読みと候補が不一致")
            elif any(str(record[k]).strip() for k in source_keys):
                raise RuntimeError(f"{where}: 未確認行の根拠欄は空にする")
            records.append(record)
    if require_complete and seen != set(candidates):
        missing = sorted(set(candidates) - seen)
        raise RuntimeError(f"検索結果が未完了: {len(missing)}件 (先頭 {missing[:10]})")
    return sorted(records, key=lambda r: int(r["batch_index"]))


def validate(batch: str) -> list[dict]:
    candidates = load_candidates(candidates_path(batch))
    records = load_results(candidates, result_paths(batch))
    counts = {status: sum(r["status"] == status for r in records)
              for status in sorted(SEARCH_STATUSES)}
    print(f"公式Web検索ログ {batch}: {len(records)}件 {counts}")
    return records


def validate_all() -> None:
    paths = sorted(BATCH_DIR.glob("*-candidates.csv"))
    if not paths:
        raise RuntimeError("候補スナップショットがない")
    for path in paths:
        validate(path.name.removesuffix("-candidates.csv"))


def promote(batch: str) -> None:
    records = validate(batch)
    existing_pairs = load_official_evidence()
    lines = OFFICIAL_EVIDENCE_PATH.read_text(encoding="utf-8").splitlines()
    added = 0
    for record in records:
        pair = (record["surface"], record["pronunciation"])
        if record["status"] != "verified" or pair in existing_pairs:
            continue
        evidence = {
            "surface": record["surface"],
            "pronunciation": record["pronunciation"],
            "status": "verified", "source_url": record["source_url"],
            "source_type": record["source_type"],
            "source_title": record["source_title"],
            "retrieved_on": record["searched_on"],
            "observed_surface": record["observed_surface"],
            "observed_reading": record["observed_reading"],
            "locator": record["locator"],
            "identity_basis": record["notes"],
        }
        lines.append(json.dumps(evidence, ensure_ascii=False, separators=(",", ":")))
        existing_pairs.add(pair)
        added += 1
    OFFICIAL_EVIDENCE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    load_official_evidence()
    print(f"公式根拠台帳へ追加: {added}件")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--limit", type=int, default=225)
    prepare_parser.add_argument("--batch", default=DEFAULT_BATCH)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--batch", default=DEFAULT_BATCH)
    validate_parser.add_argument("--all", action="store_true")
    promote_parser = sub.add_parser("promote")
    promote_parser.add_argument("--batch", default=DEFAULT_BATCH)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.limit, args.batch)
    elif args.command == "validate":
        validate_all() if args.all else validate(args.batch)
    else:
        promote(args.batch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
