#!/usr/bin/env python3
"""sekitsui.csv の目・科に残ったラテン学名をWikidataの日本語名に直す。

P225（学名）とP105（階級）が一致する項目だけをバッチ検索する。階級語尾付きの
日本語ラベル、同語尾付きの日本語別名、その他の日本語ラベルの順で採用する。
同じ学名・階級の複数項目で採用名が食い違う場合は置換しない。
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxonomy import FAMILY, ORDER, fetch_scientific_taxa
from wpnames import UA, WP_API, write_csv_no_trailing_newline

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "sekitsui.csv"
CACHE_PATH = Path(__file__).resolve().parent / ".cache" / "sekitsui_taxonomy_labels.json"
RANKS = {"order": (ORDER, "目"), "family": (FAMILY, "科")}
BATCH = 100
JA_NAME = re.compile(r"[ァ-ヶ一-龥々ー]{2,}(?:目|科)")
GENERIC = {"独立目", "独立科", "新目", "新科"}
KNOWN_LABELS = {"Lutjaniformes": "フエダイ目"}
CONFLICT = "__WIKIDATA_CONFLICT__"


def load_cache(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"invalid cache: {path}")
    return payload


def save_cache(path: Path, cache: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def scientific_name(value: str) -> str:
    """セル全体がラテン文字の単名学名の場合だけ返す。"""
    value = (value or "").strip()
    if len(value) >= 4 and value[0].isupper() and value.replace("-", "").isalpha():
        if value.isascii():
            return value
    return ""


def is_japanese(value: str) -> bool:
    return any(
        "\u3040" <= char <= "\u30ff" or "\u3400" <= char <= "\u9fff"
        for char in value
    )


def candidate_label(candidate: dict, suffix: str) -> str:
    """階級語尾付きlabel > 階級語尾付きaltLabel > 日本語label。"""
    label = str(candidate.get("ja", "")).strip()
    if is_japanese(label) and label.endswith(suffix):
        return label
    alts = sorted({
        str(alt).strip() for alt in candidate.get("alts", [])
        if is_japanese(str(alt)) and str(alt).strip().endswith(suffix)
    })
    if alts:
        return alts[0]
    return label if is_japanese(label) else ""


def resolve_label(candidates: list[dict], suffix: str) -> str:
    """全候補の採用名が一意な場合だけ返す。"""
    labels = {candidate_label(candidate, suffix) for candidate in candidates}
    labels.discard("")
    return next(iter(labels)) if len(labels) == 1 else ""


def conflicting_labels(candidates: list[dict], suffix: str) -> bool:
    labels = {candidate_label(candidate, suffix) for candidate in candidates}
    labels.discard("")
    return len(labels) > 1


def fetch_wikitexts(term: str) -> list[str]:
    """Wikidataに日本語名がない場合のため日本語版Wikipedia本文を取得する。"""
    params = {
        "action": "query", "generator": "search",
        "gsrsearch": f'insource:"{term}"', "gsrnamespace": 0,
        "gsrlimit": 20, "prop": "revisions", "rvprop": "content",
        "rvslots": "main", "format": "json", "formatversion": 2,
    }
    url = WP_API + "?" + urllib.parse.urlencode(params)
    last_error = None
    for attempt in range(5):
        try:
            request = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.load(response)
            return [
                page.get("revisions", [{}])[0]
                .get("slots", {}).get("main", {}).get("content", "")
                for page in data.get("query", {}).get("pages", [])
                if page.get("revisions")
            ]
        except urllib.error.HTTPError as error:
            last_error = error
            if attempt + 1 < 5:
                time.sleep(60 if error.code == 429 else 5 * (attempt + 1))
        except Exception as error:
            last_error = error
            if attempt + 1 < 5:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Wikipedia API failed: {last_error}")


def resolve_wikipedia_label(term: str, suffix: str) -> str:
    """本文中で学名と分類欄・太字見出しが直接対応する階級名だけを返す。"""
    candidates: Counter[str] = Counter()
    for text in fetch_wikitexts(term):
        for line in text.splitlines():
            for match in re.finditer(re.escape(term), line, flags=re.IGNORECASE):
                before = line[max(0, match.start() - 180):match.start()]
                names = [
                    name for name in JA_NAME.findall(before)
                    if name.endswith(suffix) and name not in GENERIC
                    and not name.endswith(("亜" + suffix, "上" + suffix, "下" + suffix))
                ]
                if not names:
                    continue
                name = names[-1]
                field = re.match(r"^\s*\|\s*([目科])\s*=", line)
                if field and field.group(1) == suffix:
                    candidates[name] += 10
                elif re.search(r"'{2,3}" + re.escape(name) + r"'{2,3}", before):
                    candidates[name] += 5
    if not candidates:
        return ""
    return min(candidates, key=lambda name: (-candidates[name], len(name), name))


def cache_key(term: str, rank: str) -> str:
    return f"{rank}:{term}"


def fetch_all(
    pairs: list[tuple[str, str]], cache: dict[str, str], cache_path: Path,
    *, sleeper=time.sleep,
) -> None:
    for offset in range(0, len(pairs), BATCH):
        chunk = pairs[offset:offset + BATCH]
        results = fetch_scientific_taxa(chunk)
        for term, rank in chunk:
            suffix = "目" if rank == ORDER else "科"
            candidates = results.get((term, rank), [])
            cache[cache_key(term, rank)] = (
                CONFLICT if conflicting_labels(candidates, suffix)
                else resolve_label(candidates, suffix)
            )
        save_cache(cache_path, cache)
        print(f"Wikidata: {min(offset + BATCH, len(pairs))}/{len(pairs)} 件", flush=True)
        if offset + BATCH < len(pairs):
            sleeper(1.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--cache", type=Path, default=CACHE_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    with args.csv.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = list(reader.fieldnames or [])

    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        for column, (rank, _suffix) in RANKS.items():
            term = scientific_name(row.get(column, ""))
            if term:
                counts[(term, rank)] += 1

    cache = load_cache(args.cache)
    targets = [
        pair for pair, _ in counts.most_common()
        if args.refresh or cache_key(*pair) not in cache
    ]
    if args.limit:
        targets = targets[:args.limit]
    fetch_all(targets, cache, args.cache)

    # 従来のWikipedia本文照合は、Wikidataに採用可能な日本語名がない場合だけ使う。
    # 複数候補の日本語名が衝突した場合は、別ソースで曖昧性を覆い隠さない。
    cache.update({term: label for term, label in KNOWN_LABELS.items()
                  if term not in cache})
    fallback_targets = [
        (term, rank) for term, rank in counts
        if cache_key(term, rank) in cache
        and cache.get(cache_key(term, rank)) == ""
        and (args.refresh or term not in cache)
    ]
    for index, (term, rank) in enumerate(fallback_targets, 1):
        suffix = "目" if rank == ORDER else "科"
        cache[term] = resolve_wikipedia_label(term, suffix)
        save_cache(args.cache, cache)
        print(f"Wikipedia: {index}/{len(fallback_targets)} {term}", flush=True)
        if index < len(fallback_targets):
            time.sleep(0.5)

    changed = 0
    for row in rows:
        for column, (rank, _suffix) in RANKS.items():
            term = scientific_name(row.get(column, ""))
            wikidata_label = cache.get(cache_key(term, rank), "")
            label = "" if wikidata_label == CONFLICT else (
                wikidata_label or cache.get(term, "")
            )
            if term and label:
                row[column] = label
                changed += 1

    if not args.dry_run and changed:
        write_csv_no_trailing_newline(args.csv, columns, rows)
    unresolved = sum(
        1 for row in rows for column in ("order", "family")
        if scientific_name(row.get(column, ""))
    )
    action = "変更予定" if args.dry_run else "変更"
    print(f"{args.csv}: 日本語階級名 {changed}セル{action}、未解決 {unresolved}セル")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
