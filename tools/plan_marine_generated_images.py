#!/usr/bin/env python3
"""実写未取得行を科・目・形態群へ安定的に割り当てる生成画像計画を作る。

科5件以上を科別、残りのうち同じ目が5件以上を目別、それ以外を既存の
形態群別fallbackへ割り当てる。生成用JSONLには、対象行に実在する学名を最大3件
だけ視覚参考として含める。

usage: python3 tools/plan_marine_generated_images.py --out-dir DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import update_marine_life as marine

MIN_FAMILY_ROWS = marine.MIN_GENERATED_FAMILY_ROWS
MIN_ORDER_ROWS = marine.MIN_GENERATED_ORDER_ROWS

GROUP_SCENES = {
    "哺乳類": "海中を泳ぐ海棲哺乳類。流線形の体、ひれ状の前肢、自然な水面光",
    "爬虫類": "海中を泳ぐ海棲爬虫類。甲羅または細長い体、浅海の自然光",
    "魚類": "海中の魚類。対象分類群に適した体型、ひれ、鱗、自然な海底または外洋",
    "刺胞動物": "海中の刺胞動物。対象分類群に適した傘、触手、ポリプまたは群体",
    "甲殻類": "海底の甲殻類。対象分類群に適した節、触角、脚を正確に表現した水中マクロ",
    "軟体動物": "海底または海中の軟体動物。対象分類群に適した殻、外套、腕または足",
    "棘皮動物": "海底の棘皮動物。対象分類群に適した放射相称、棘または管足",
    "蠕虫型": "海底の蠕虫型無脊椎動物。対象分類群に適した体節、体表または棲管の水中マクロ",
    "その他無脊椎": "岩礁や海底の無脊椎動物。対象分類群に適した固着性または浮遊性の体型",
}


def stable_filename(scope: str, name: str) -> str:
    key = hashlib.sha1(f"{scope}:{name}".encode()).hexdigest()[:12]
    return f"marine_{scope}_{key}_generated.webp"


def load_rows() -> list[dict[str, str]]:
    return [row for row in marine.load_source() if not row["image"]]


def build_plan(rows: list[dict[str, str]]) -> tuple[list[dict], dict[str, str]]:
    family_counts = Counter(row["family"] for row in rows)
    family_names = {name for name, count in family_counts.items() if count >= MIN_FAMILY_ROWS}
    remaining = [row for row in rows if row["family"] not in family_names]
    order_counts = Counter(row["order"] for row in remaining)
    order_names = {name for name, count in order_counts.items() if count >= MIN_ORDER_ROWS}

    buckets: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    assignment: dict[str, str] = {}
    for row in rows:
        if row["family"] in family_names:
            key = ("family", row["family"])
        elif row["order"] in order_names:
            key = ("order", row["order"])
        else:
            assignment[row["name"]] = f"group:{row['image_group']}"
            continue
        buckets[key].append(row)
        assignment[row["name"]] = f"{key[0]}:{key[1]}"

    plan = []
    for (scope, name), members in sorted(buckets.items()):
        groups = Counter(row["image_group"] for row in members)
        group = groups.most_common(1)[0][0]
        scientific_names = list(dict.fromkeys(
            row["scientific_name"] for row in members if row["scientific_name"]
        ))[:3]
        japanese_examples = [row["name"] for row in members[:3]]
        scope_ja = "科" if scope == "family" else "目"
        refs = "、".join(scientific_names) or "対象台帳の分類群"
        examples = "、".join(japanese_examples)
        prompt = (
            f"海の生き物リストの「{name}」という{scope_ja}を表す教育用の写真風生成合成画像。"
            f"台帳内の例は{examples}、学名参考は{refs}。"
            f"{GROUP_SCENES[group]}。同じ{scope_ja}に見られる代表的な体型を1〜3個体で示す。"
            "単一の既知種を正確に再現した写真とはせず、分類群の形態範囲を誇張なく示す。"
            "自然史博物館の高品質な水中生態写真風、被写体は中央、上下に十分な余白、"
            "解剖学的に自然、文字なし、ロゴなし、透かしなし、人物なし、正方形。"
        )
        plan.append({
            "word": f"{scope}:{name}", "scope": scope, "name": name,
            "group": group, "member_count": len(members),
            "scientific_examples": scientific_names,
            "japanese_examples": japanese_examples,
            "filename": stable_filename(scope, name), "prompt": prompt,
        })
    return plan, assignment


def validate_plan(plan: list[dict], assignment: dict[str, str], rows: list[dict[str, str]]) -> None:
    words = [record["word"] for record in plan]
    filenames = [record["filename"] for record in plan]
    if len(words) != len(set(words)) or len(filenames) != len(set(filenames)):
        raise ValueError("generated plan has duplicate words or filenames")
    if set(assignment) != {row["name"] for row in rows}:
        raise ValueError("generated assignments do not cover every missing-photo row")
    valid = set(words) | {f"group:{group}" for group in marine.IMAGE_FILE_BY_GROUP}
    unknown = set(assignment.values()) - valid
    if unknown:
        raise ValueError(f"generated assignments contain unknown targets: {sorted(unknown)}")
    member_counts = Counter(value for value in assignment.values() if not value.startswith("group:"))
    for record in plan:
        if record["member_count"] != member_counts[record["word"]]:
            raise ValueError(f"generated plan member count mismatch: {record['word']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = load_rows()
    plan, assignment = build_plan(rows)
    validate_plan(plan, assignment, rows)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (args.out_dir / "words.jsonl").open("w", encoding="utf-8") as output:
        for record in plan:
            output.write(json.dumps({"word": record["word"], "prompt": record["prompt"]}, ensure_ascii=False) + "\n")
    (args.out_dir / "assignment.json").write_text(
        json.dumps(assignment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    counts = Counter(value.split(":", 1)[0] for value in assignment.values())
    print(f"assets={len(plan)} assignments={len(assignment)} scopes={dict(counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
