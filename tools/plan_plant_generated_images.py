#!/usr/bin/env python3
"""植物の大分類SVGを科別の生成画像へ置き換える計画を作る。

usage: python3 tools/plan_plant_generated_images.py --out-dir DIR
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "plant.csv"
CLASS_IMAGE_MARKER = "/releases/download/class-image-"
FAMILY_GENERATED_MARKER = "/images/plant/plant_family_"
# Pilot manifests may intentionally contain a single family.
MIN_FAMILY_ROWS = 1
QID = re.compile(r"^Q[1-9][0-9]*$")


def valid_qid(value: str) -> bool:
    return bool(QID.fullmatch(value.strip()))


def stable_filename(family: str, family_qid: str = "") -> str:
    """Prefer a readable stable QID key; hash the family name only as fallback."""
    qid = family_qid.strip()
    if qid:
        if not valid_qid(qid):
            raise ValueError(f"invalid family QID: {qid}")
        return f"plant_family_{qid.lower()}_generated.webp"
    key = hashlib.sha1(f"family:{family}".encode()).hexdigest()[:12]
    return f"plant_family_{key}_generated.webp"


def load_rows(path: Path = CSV_PATH) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return [
            dict(row) for row in csv.DictReader(source)
            if (CLASS_IMAGE_MARKER in row.get("image", "")
                or FAMILY_GENERATED_MARKER in row.get("image", ""))
        ]


def row_name(row: dict[str, str]) -> str:
    return (row.get("original") or row.get("name") or "").strip()


def row_class(row: dict[str, str]) -> str:
    return (row.get("class") or "NA").strip() or "NA"


def family_qids(rows: list[dict[str, str]]) -> dict[str, str]:
    """Return the sole QID observed per family and reject contradictory identity."""
    found: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        family = row.get("family", "").strip()
        qid = row.get("family_wikidata", "").strip()
        if qid and not valid_qid(qid):
            raise ValueError(f"invalid family QID for {family}: {qid}")
        if family and qid:
            found[family].add(qid)
    conflicts = {name: sorted(qids) for name, qids in found.items() if len(qids) > 1}
    if conflicts:
        raise ValueError(f"family names have conflicting QIDs: {conflicts}")
    return {name: next(iter(qids)) for name, qids in found.items()}


def target_for(family: str, family_qid: str) -> str:
    return f"family:{family_qid or family}"


def build_plan(rows: list[dict[str, str]]) -> tuple[list[dict], dict[str, str]]:
    qids = family_qids(rows)
    counts = Counter(row.get("family", "").strip() for row in rows
                     if row.get("family", "").strip())
    eligible = {name for name, count in counts.items()
                if count >= MIN_FAMILY_ROWS and (name.endswith("科") or qids.get(name))}
    members: dict[str, list[dict[str, str]]] = defaultdict(list)
    assignment: dict[str, str] = {}
    for row in rows:
        name = row_name(row)
        if not name:
            raise ValueError("class-image row has no original/name")
        if name in assignment:
            raise ValueError(f"class-image rows have duplicate names: {name}")
        family = row.get("family", "").strip()
        if family in eligible:
            members[family].append(row)
            assignment[name] = target_for(family, qids.get(family, ""))
        else:
            assignment[name] = f"class:{row_class(row)}"

    plan = []
    for family, family_rows in sorted(members.items()):
        family_qid = qids.get(family, "")
        classes = Counter(row_class(row) for row in family_rows)
        plant_class = min(classes, key=lambda value: (-classes[value], value))
        examples = sorted({row_name(row) for row in family_rows})[:3]
        scientific = sorted({
            row.get("scientific_name", "").strip() for row in family_rows
            if row.get("scientific_name", "").strip()
        })[:3]
        scientific_text = (
            f"学名の例は{'、'.join(scientific)}。" if scientific else ""
        )
        prompt = (
            f"植物リストの「{family}」という科を表す、教育用の写真風生成合成画像。"
            f"台帳内の和名の例は{'、'.join(examples)}。{scientific_text}"
            "この科に見られる代表的な植物群を自然な生育環境に示す。草本・木本、"
            "葉序、葉形、花または胞子体、果実など、該当する科の多様性と識別要素を"
            "植物学的に無理のない範囲で組み合わせる。"
            "特定の一種を正確に再現した画像とは主張せず、葉、花、茎など科の特徴を自然に示す。"
            "自然史教材に適した高品質な植物写真風、主題は中央、周囲に十分な余白、"
            "植物学的に自然、文字なし、ロゴなし、透かしなし、人物なし、横長16:10。"
        )
        plan.append({
            "word": target_for(family, family_qid),
            "scope": "family",
            "name": family,
            "family_qid": family_qid,
            "class": plant_class,
            "member_count": len(family_rows),
            "japanese_examples": examples,
            "scientific_examples": scientific,
            "filename": stable_filename(family, family_qid),
            "prompt": prompt,
        })
    return plan, assignment


def validate_plan(plan: list[dict], assignment: dict[str, str],
                  rows: list[dict[str, str]]) -> None:
    names = [row_name(row) for row in rows]
    if not all(names) or len(names) != len(set(names)):
        raise ValueError("class-image rows must have unique nonempty names")
    if set(assignment) != set(names):
        raise ValueError("generated assignments do not cover every class-image row")
    qids = family_qids(rows)
    counts = Counter(row.get("family", "").strip() for row in rows
                     if row.get("family", "").strip())
    eligible = {name for name, count in counts.items()
                if count >= MIN_FAMILY_ROWS and (name.endswith("科") or qids.get(name))}
    expected = {target_for(name, qids.get(name, "")) for name in eligible}
    words = [record.get("word") for record in plan]
    filenames = [record.get("filename") for record in plan]
    if set(words) != expected:
        raise ValueError("generated plan does not match eligible families")
    if len(words) != len(set(words)) or len(filenames) != len(set(filenames)):
        raise ValueError("generated plan has duplicate words or filenames")
    covered = Counter(assignment.values())
    for record in plan:
        family = record.get("name", "")
        qid = record.get("family_qid", "")
        word = target_for(family, qid)
        if record.get("scope") != "family" or record.get("word") != word:
            raise ValueError(f"invalid generated family record: {record.get('word')}")
        if qid != qids.get(family, ""):
            raise ValueError(f"family QID mismatch: {family}")
        if record.get("filename") != stable_filename(family, qid):
            raise ValueError(f"generated plan filename mismatch: {word}")
        if record.get("member_count") != covered[word]:
            raise ValueError(f"generated plan member count mismatch: {word}")
        examples = record.get("japanese_examples", [])
        scientific = record.get("scientific_examples", [])
        if not 1 <= len(examples) <= 3 or len(examples) != len(set(examples)):
            raise ValueError(f"generated plan has invalid examples: {word}")
        if len(scientific) > 3 or len(scientific) != len(set(scientific)):
            raise ValueError(f"generated plan has invalid scientific examples: {word}")
    for row in rows:
        family = row.get("family", "").strip()
        expected_target = (target_for(family, qids.get(family, ""))
                           if family in eligible else f"class:{row_class(row)}")
        if assignment[row_name(row)] != expected_target:
            raise ValueError(f"generated assignment target mismatch: {row_name(row)}")


def write_outputs(out_dir: Path, plan: list[dict], assignment: dict[str, str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (out_dir / "words.jsonl").open("w", encoding="utf-8") as output:
        for record in plan:
            output.write(json.dumps({"word": record["word"], "prompt": record["prompt"]},
                                    ensure_ascii=False) + "\n")
    (out_dir / "assignment.json").write_text(
        json.dumps(assignment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = load_rows()
    plan, assignment = build_plan(rows)
    validate_plan(plan, assignment, rows)
    write_outputs(args.out_dir, plan, assignment)
    scopes = Counter(target.split(":", 1)[0] for target in assignment.values())
    print(f"assets={len(plan)} assignments={len(assignment)} scopes={dict(scopes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
