#!/usr/bin/env python3
"""GBIF の和名検索で sekitsui.csv の欠けた分類を補完する。

GBIF Species Search API を ``q=和名`` で検索し、検索結果自身が持つ
vernacularNames に ``language=jpn`` かつ完全一致の和名があるものだけを使う。
Animalia/Chordata 外の候補、および候補間で class/order/family が矛盾する名前は
適用しない。既存の分類値は上書きしない。

usage:
  python3 tools/enrich_sekitsui_gbif.py --limit 100 --dry-run
  python3 tools/enrich_sekitsui_gbif.py --refresh
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "sekitsui.csv"
CACHE_PATH = Path(__file__).resolve().parent / ".cache" / "sekitsui_gbif.json"
GBIF_API = "https://api.gbif.org/v1/species/search"
USER_AGENT = (
    "soramimic-wordlists-updater/1.0 "
    "(https://github.com/soramimic/soramimic-wordlists)"
)

# GBIF の class は魚類について複数の分類階級名を返す。現生脊椎動物として
# sekitsui.csv の既存5区分の「魚類」に当たるものを明示的に対応させる。
CLASS_MAP = {
    "Mammalia": "哺乳類",
    "Aves": "鳥類",
    "Reptilia": "爬虫類",
    "Amphibia": "両生類",
    "Actinopterygii": "魚類",
    "Chondrichthyes": "魚類",
    "Elasmobranchii": "魚類",
    "Holocephali": "魚類",
    "Sarcopterygii": "魚類",
    "Coelacanthi": "魚類",
    "Dipnoi": "魚類",
    "Myxini": "魚類",
    "Petromyzonti": "魚類",
    "Petromyzontida": "魚類",
    "Hyperoartia": "魚類",
    "Cephalaspidomorphi": "魚類",
}
RANK_FIELDS = ("class", "order", "family")
MISSING = {"", "NA"}


def is_missing(value: str | None) -> bool:
    return (value or "").strip() in MISSING


def eligible_candidates(name: str, results: list[dict]) -> list[dict[str, str]]:
    """API results から採用条件を満たす候補の分類値だけを返す。"""
    candidates: list[dict[str, str]] = []
    for result in results:
        if str(result.get("kingdom", "")).casefold() != "animalia":
            continue
        if str(result.get("phylum", "")).casefold() != "chordata":
            continue
        names = result.get("vernacularNames") or []
        exact = any(
            item.get("language") == "jpn"
            and item.get("vernacularName") == name
            for item in names
            if isinstance(item, dict)
        )
        if not exact:
            continue
        candidate = {
            field: str(result.get(field, "") or "").strip()
            for field in RANK_FIELDS
        }
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def resolve_candidates(candidates: list[dict[str, str]]) -> dict[str, str] | None:
    """候補が無矛盾なら一意な階級を返し、矛盾があれば None を返す。"""
    resolved: dict[str, str] = {}
    for field in RANK_FIELDS:
        values = {candidate.get(field, "").strip() for candidate in candidates}
        values.discard("")
        if len(values) > 1:
            return None
        resolved[field] = next(iter(values), "")
    return resolved


def fetch_candidates(
    name: str,
    *,
    opener: Callable = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
    retries: int = 5,
) -> list[dict[str, str]]:
    """GBIF を検索する。一時エラーは指数バックオフして再試行する。"""
    query = urllib.parse.urlencode({"q": name, "limit": 100})
    request = urllib.request.Request(
        f"{GBIF_API}?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with opener(request, timeout=60) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise ValueError("GBIF response is not an object")
            results = payload.get("results", [])
            if not isinstance(results, list):
                raise ValueError("GBIF response has no results list")
            return eligible_candidates(name, results)
        except urllib.error.HTTPError as error:
            last_error = error
            # 4xx はレート制限と一時的タイムアウト以外、再試行しても直らない。
            if error.code < 500 and error.code not in (408, 429):
                raise RuntimeError(f"GBIF API failed for {name}: {error}") from error
            if attempt + 1 < retries:
                retry_after = error.headers.get("Retry-After") if error.headers else None
                wait = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                sleeper(wait)
        except (OSError, ValueError) as error:
            last_error = error
            if attempt + 1 < retries:
                sleeper(2**attempt)
    raise RuntimeError(f"GBIF API failed for {name}: {last_error}") from last_error


def load_cache(path: Path) -> dict[str, list[dict[str, str]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"invalid cache: {path}")
    return payload


def save_cache(path: Path, cache: dict[str, list[dict[str, str]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(cache, stream, ensure_ascii=False, sort_keys=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def enrich_rows(
    rows: list[dict[str, str]],
    cache: dict[str, list[dict[str, str]]],
) -> tuple[int, int]:
    """キャッシュ済み結果を行へ適用し、変更行数と矛盾名数を返す。"""
    changed = 0
    conflicts: set[str] = set()
    for row in rows:
        name = row.get("original", "")
        if not name or name not in cache:
            continue
        resolved = resolve_candidates(cache[name])
        if resolved is None:
            conflicts.add(name)
            continue
        updates: dict[str, str] = {
            "class": CLASS_MAP.get(resolved["class"], ""),
            "order": resolved["order"],
            "family": resolved["family"],
        }
        row_changed = False
        for field, value in updates.items():
            if value and is_missing(row.get(field)):
                row[field] = value
                row_changed = True
        changed += int(row_changed)
    return changed, len(conflicts)


def write_csv_atomic(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    """列順と末尾改行なしというリポジトリのCSV規約を保って置換する。"""
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        temp_path = Path(temporary)
        text = temp_path.read_text(encoding="utf-8").rstrip("\n")
        if '"' in text:
            raise ValueError("quoted field would break the wordlist parser")
        temp_path.write_text(text, encoding="utf-8")
        os.chmod(temp_path, stat.S_IMODE(path.stat().st_mode))
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def fetch_all(
    names: list[str],
    cache: dict[str, list[dict[str, str]]],
    cache_path: Path,
    *,
    workers: int,
    delay: float,
) -> None:
    """問い合わせを並列実行し、完了結果をメインスレッドで逐次保存する。"""
    if not names:
        return
    iterator = iter(names)
    submitted = 0
    completed = 0
    last_submission = 0.0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending: dict[Future[list[dict[str, str]]], str] = {}

        def submit_one(name: str) -> None:
            nonlocal submitted, last_submission
            if submitted and delay:
                elapsed = time.monotonic() - last_submission
                if elapsed < delay:
                    time.sleep(delay - elapsed)
            pending[executor.submit(fetch_candidates, name)] = name
            submitted += 1
            last_submission = time.monotonic()

        for _ in range(min(workers, len(names))):
            submit_one(next(iterator))

        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                name = pending.pop(future)
                candidates = future.result()
                cache[name] = candidates
                save_cache(cache_path, cache)
                completed += 1
                print(
                    f"{completed}/{len(names)} {name}: "
                    f"{len(candidates)} exact candidate(s)",
                    flush=True,
                )
                try:
                    next_name = next(iterator)
                except StopIteration:
                    continue
                submit_one(next_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--cache", type=Path, default=CACHE_PATH)
    parser.add_argument("--limit", type=int, default=0,
                        help="今回GBIFへ問い合わせる和名数（0は無制限）")
    parser.add_argument("--dry-run", action="store_true",
                        help="検索・キャッシュは行うがCSVを書き換えない")
    parser.add_argument("--refresh", action="store_true",
                        help="対象名をキャッシュ済みでも再検索する")
    parser.add_argument("--delay", type=float, default=0.25,
                        help="GBIFリクエスト間の待機秒数")
    parser.add_argument("--workers", type=int, default=1,
                        help="GBIF問い合わせの並列数（既定: 1）")
    args = parser.parse_args(argv)
    if args.limit < 0 or args.delay < 0 or args.workers < 1:
        parser.error("--limit/--delay must not be negative and --workers must be positive")

    with args.csv.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    required = {"original", *RANK_FIELDS}
    if not required.issubset(columns):
        missing = ", ".join(sorted(required - set(columns)))
        print(f"error: missing CSV columns: {missing}", file=sys.stderr)
        return 2

    cache = load_cache(args.cache)
    names = list(dict.fromkeys(
        row["original"] for row in rows
        if row.get("original") and any(is_missing(row.get(field)) for field in RANK_FIELDS)
    ))
    targets = [name for name in names if args.refresh or name not in cache]
    if args.limit:
        targets = targets[:args.limit]
    fetch_all(
        targets,
        cache,
        args.cache,
        workers=args.workers,
        delay=args.delay,
    )

    changed, conflicts = enrich_rows(rows, cache)
    if not args.dry_run and changed:
        write_csv_atomic(args.csv, columns, rows)
    action = "変更予定" if args.dry_run else "変更"
    print(
        f"{args.csv}: {action} {changed}行、矛盾により未適用 {conflicts}名、"
        f"GBIF問い合わせ {len(targets)}名"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
