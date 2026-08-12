#!/usr/bin/env python3
"""脊椎動物の綱別代替画像を科別の生成画像へ置き換える計画を作る。

class-image-v1 の画像を使っている行のうち、実写未取得行が5件以上ある科を
科別画像の生成対象にする。全対象行について科別画像または従来の綱別画像への
割り当ても出力する。

usage: python3 tools/plan_sekitsui_generated_images.py --out-dir DIR
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "sekitsui.csv"
CLASS_IMAGE_V1_MARKER = "/releases/download/class-image-v1/"
MIN_FAMILY_ROWS = 5

CLASS_HABITATS = {
    "哺乳類": "その科に自然な森林、草原、岩場、水辺または海中の生息環境",
    "鳥類": "その科に自然な森林、草原、湿地、海岸または水辺の生息環境",
    "爬虫類": "その科に自然な森林、草原、砂地、岩場または水辺の生息環境",
    "両生類": "その科に自然な湿潤な森林、池、沼または沢の生息環境",
    "魚類": "その科に自然な淡水または海水の水中生息環境",
    "NA": "その科の動物に自然な生息環境",
}


def stable_filename(name: str) -> str:
    """科名だけから再現可能なASCIIファイル名を返す。"""
    key = hashlib.sha1(f"family:{name}".encode()).hexdigest()[:12]
    return f"sekitsui_family_{key}_generated.webp"


def load_rows(path: Path = CSV_PATH) -> list[dict[str, str]]:
    """現在 class-image-v1 を使っている行だけを読み込む。"""
    with path.open(encoding="utf-8", newline="") as source:
        return [
            dict(row) for row in csv.DictReader(source)
            if CLASS_IMAGE_V1_MARKER in row.get("image", "")
        ]


def row_name(row: dict[str, str]) -> str:
    """割り当てJSONのキーになる台帳上の和名を返す。"""
    return (row.get("original") or row.get("name") or "").strip()


def row_class(row: dict[str, str]) -> str:
    return (row.get("class") or "NA").strip() or "NA"


def dominant_class(rows: list[dict[str, str]]) -> str:
    counts = Counter(row_class(row) for row in rows)
    # 件数が同じ場合も入力順に依存させない。
    return min(counts, key=lambda name: (-counts[name], name))


def build_plan(rows: list[dict[str, str]]) -> tuple[list[dict], dict[str, str]]:
    family_counts = Counter(
        row.get("family", "").strip()
        for row in rows
        if row.get("family", "").strip()
    )
    eligible = {
        family for family, count in family_counts.items()
        if family.endswith("科") and count >= MIN_FAMILY_ROWS
    }

    members_by_family: dict[str, list[dict[str, str]]] = defaultdict(list)
    assignment: dict[str, str] = {}
    for row in rows:
        name = row_name(row)
        family = row.get("family", "").strip()
        if family in eligible:
            target = f"family:{family}"
            members_by_family[family].append(row)
        else:
            target = f"class:{row_class(row)}"
        if not name:
            raise ValueError("class-image row has no original/name")
        if name in assignment:
            raise ValueError(f"class-image rows have duplicate names: {name}")
        assignment[name] = target

    plan = []
    for family, members in sorted(members_by_family.items()):
        animal_class = dominant_class(members)
        examples = sorted({row_name(row) for row in members})[:3]
        example_text = "、".join(examples)
        habitat = CLASS_HABITATS.get(animal_class, CLASS_HABITATS["NA"])
        prompt = (
            f"脊椎動物リストの「{family}」という科を表す、教育用の写真風生成合成画像。"
            f"台帳内の和名の例は{example_text}。{habitat}で、"
            "この科に見られる代表的な特徴を備えた動物を1〜3個体示す。"
            "特定の一種を正確に再現した画像とは主張せず、科の形態的な特徴を自然に示す。"
            "自然史教材に適した高品質な生態写真風、被写体は中央、周囲に十分な余白、"
            "解剖学的に自然、文字なし、ロゴなし、透かしなし、人物なし、正方形。"
        )
        plan.append({
            "word": f"family:{family}",
            "scope": "family",
            "name": family,
            "class": animal_class,
            "member_count": len(members),
            "japanese_examples": examples,
            "filename": stable_filename(family),
            "prompt": prompt,
        })
    return plan, assignment


def validate_plan(
        plan: list[dict], assignment: dict[str, str],
        rows: list[dict[str, str]]) -> None:
    expected_names = [row_name(row) for row in rows]
    if not all(expected_names) or len(expected_names) != len(set(expected_names)):
        raise ValueError("class-image rows must have unique nonempty names")
    if set(assignment) != set(expected_names):
        raise ValueError("generated assignments do not cover every class-image row")

    words = [record.get("word") for record in plan]
    filenames = [record.get("filename") for record in plan]
    if len(words) != len(set(words)) or len(filenames) != len(set(filenames)):
        raise ValueError("generated plan has duplicate words or filenames")

    valid_families = {
        family for family, count in Counter(
            row.get("family", "").strip() for row in rows
            if row.get("family", "").strip()
        ).items() if count >= MIN_FAMILY_ROWS
        and family.endswith("科")
    }
    expected_words = {f"family:{family}" for family in valid_families}
    if set(words) != expected_words:
        raise ValueError("generated plan does not match eligible families")

    member_counts = Counter(assignment.values())
    for record in plan:
        family = record.get("name", "")
        word = record.get("word")
        examples = record.get("japanese_examples", [])
        if record.get("scope") != "family" or word != f"family:{family}":
            raise ValueError(f"invalid generated family record: {word}")
        if record.get("filename") != stable_filename(family):
            raise ValueError(f"generated plan filename mismatch: {word}")
        if record.get("member_count") != member_counts[word]:
            raise ValueError(f"generated plan member count mismatch: {word}")
        if not 1 <= len(examples) <= 3 or len(examples) != len(set(examples)):
            raise ValueError(f"generated plan has invalid examples: {word}")
        family_members = {
            row_name(row) for row in rows
            if row.get("family", "").strip() == family
        }
        if not set(examples) <= family_members:
            raise ValueError(f"generated plan has unknown examples: {word}")

    for row in rows:
        family = row.get("family", "").strip()
        expected = (
            f"family:{family}" if family in valid_families
            else f"class:{row_class(row)}"
        )
        if assignment[row_name(row)] != expected:
            raise ValueError(f"generated assignment target mismatch: {row_name(row)}")


def write_outputs(
        out_dir: Path, plan: list[dict], assignment: dict[str, str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (out_dir / "words.jsonl").open("w", encoding="utf-8") as output:
        for record in plan:
            output.write(json.dumps(
                {"word": record["word"], "prompt": record["prompt"]},
                ensure_ascii=False,
            ) + "\n")
    (out_dir / "assignment.json").write_text(
        json.dumps(assignment, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = load_rows()
    plan, assignment = build_plan(rows)
    validate_plan(plan, assignment, rows)
    write_outputs(args.out_dir, plan, assignment)
    counts = Counter(target.split(":", 1)[0] for target in assignment.values())
    print(f"assets={len(plan)} assignments={len(assignment)} scopes={dict(counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
