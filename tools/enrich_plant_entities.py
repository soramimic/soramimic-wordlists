#!/usr/bin/env python3
"""P18の有無に依存せず、plant.csvへ安全にtaxon QIDを補完する。

候補は植物側の目・門を起点に取得した「種ランクかつ日本語ラベル完全一致」に
限定する。同じ和名に複数の植物taxonが残る場合は推測せず未確定にする。

usage: python3 tools/enrich_plant_entities.py [--refresh]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plant_overrides import MANUAL_TAXA  # noqa: E402
from update_plant import ANGIOSPERM, ANIMALIA, CLADES, MONOCOTS, SPECIES  # noqa: E402
from wpnames import sparql_post, write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "plant.csv"
CACHE = Path(__file__).resolve().parent / ".cache" / "plant_entities.json"
BATCH = 50

CLASS_ROOTS = {
    "双子葉": {ANGIOSPERM},
    "単子葉": {MONOCOTS},
    "裸子植物": {"Q133712"},
    "シダ植物": {"Q178249", "Q215370"},
    "コケ植物": {"Q25347", "Q189808", "Q191156"},
    "藻類": {"Q103169", "Q264543", "Q184573", "Q9642991", "Q133219"},
}


def load_cache() -> dict:
    if CACHE.is_file():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def fetch_exact_species(names: list[str]) -> dict[str, list[str]]:
    values = " ".join(json.dumps(name, ensure_ascii=False) + "@ja" for name in names)
    data = sparql_post(f"""
SELECT DISTINCT ?label ?taxon WHERE {{
  VALUES ?label {{ {values} }}
  ?taxon rdfs:label ?label ; wdt:P105 {SPECIES} .
}}""")
    out = {name: [] for name in names}
    for binding in data["results"]["bindings"]:
        found = qid(binding["taxon"]["value"])
        values_for_name = out.setdefault(binding["label"]["value"], [])
        if found not in values_for_name:
            values_for_name.append(found)
    return out


def fetch_ancestors(qids: list[str]) -> dict[str, list[str]]:
    values = " ".join("wd:" + value for value in qids)
    data = sparql_post(f"""
SELECT DISTINCT ?taxon ?ancestor WHERE {{
  VALUES ?taxon {{ {values} }}
  ?taxon wdt:P171* ?ancestor .
}}""")
    out = {value: [] for value in qids}
    for binding in data["results"]["bindings"]:
        out[qid(binding["taxon"]["value"])].append(qid(binding["ancestor"]["value"]))
    return out


def candidate_matches_class(candidate: str, plant_class: str,
                            ancestors: dict[str, list[str]]) -> bool:
    reached = set(ancestors.get(candidate, ()))
    roots = CLASS_ROOTS.get(plant_class, set())
    if ANIMALIA in reached or not (roots & reached):
        return False
    # 伝統的な「双子葉」枠には単子葉植物を混ぜない。
    return plant_class != "双子葉" or MONOCOTS not in reached


def collect(rows: list[dict[str, str]], refresh: bool = False) -> dict[str, set[str]]:
    """種ランク完全一致候補を取得し、CSVの植物クレード内だけに制限する。"""
    cache = {} if refresh else load_cache()
    labels = cache.setdefault("labels", {})
    ancestors = cache.setdefault("ancestors", {})
    names = sorted({row["original"] for row in rows if not row.get("wikidata")})
    todo_names = [name for name in names if name not in labels]
    for i in range(0, len(todo_names), BATCH):
        chunk = todo_names[i:i + BATCH]
        labels.update(fetch_exact_species(chunk))
        save_cache(cache)
        print(f"完全一致taxon候補 {i + len(chunk)}/{len(todo_names)}", flush=True)
        time.sleep(1)
    candidate_qids = sorted({value for name in names for value in labels.get(name, [])})
    todo_qids = [value for value in candidate_qids if value not in ancestors]
    for i in range(0, len(todo_qids), BATCH):
        chunk = todo_qids[i:i + BATCH]
        ancestors.update(fetch_ancestors(chunk))
        save_cache(cache)
        print(f"植物クレード検証 {i + len(chunk)}/{len(todo_qids)}", flush=True)
        time.sleep(1)
    class_by_name = {row["original"]: row.get("class", "") for row in rows}
    return {
        name: {candidate for candidate in labels.get(name, [])
               if candidate_matches_class(candidate, class_by_name[name], ancestors)}
        for name in names
    }


def resolve_rows(rows: list[dict[str, str]], candidates: dict[str, set[str]]) -> dict:
    """一意な非動物候補だけを書き込み、解決統計を返す。"""
    todo = [row for row in rows if not (row.get("wikidata") or "").strip()]
    filled = manual = ambiguous = missing = 0
    for row in todo:
        name = row["original"]
        override = MANUAL_TAXA.get(name)
        if override:
            row["wikidata"] = override["wikidata"]
            manual += 1
            continue
        valid = sorted(candidates.get(name, set()))
        if len(valid) == 1:
            row["wikidata"] = valid[0]
            filled += 1
        elif len(valid) > 1:
            ambiguous += 1
        else:
            missing += 1
    return {
        "targets": len(todo), "automatic": filled, "manual": manual,
        "ambiguous": ambiguous, "missing": missing,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)
    with CSV_PATH.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        rows = [dict(row) for row in reader]
        columns = list(reader.fieldnames or [])
    candidates = collect(rows, args.refresh)
    if "wikidata" not in columns:
        columns.append("wikidata")
    for row in rows:
        row.setdefault("wikidata", "")
    stats = resolve_rows(rows, candidates)
    write_csv_no_trailing_newline(CSV_PATH, columns, rows)
    have = sum(bool(row["wikidata"]) for row in rows)
    print(f"plant.csv: QID {have}/{len(rows)}; missing対象 {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
