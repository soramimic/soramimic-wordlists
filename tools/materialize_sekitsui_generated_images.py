#!/usr/bin/env python3
"""脊椎動物の科別生成画像を整形し、検品済みmanifestを作る。

同じ科の検品済み海洋生物画像がある場合は再生成せず、そのWebPを安定した
sekitsui用ファイル名で再利用する。それ以外はCDP gridから分割・全数QC済みの
PNGを960x600へ整形し「生成イメージ」を焼き込む。

usage: python3 tools/materialize_sekitsui_generated_images.py PLAN SPLIT_DIR \
  [SPLIT_DIR ...] --out-dir DIR --manifest-out FILE [--base-manifest FILE]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

from materialize_marine_generated_images import split_filename
from prepare_marine_generated_fallback import prepare

ROOT = Path(__file__).resolve().parent.parent
MARINE_MANIFEST = Path(__file__).with_name("marine_life_generated_images.json")
MARINE_IMAGE_DIR = ROOT / "images" / "marine_life"


def locate(word: str, directories: list[Path]) -> Path | None:
    matches = [directory / split_filename(word) for directory in directories]
    matches = [path for path in matches if path.is_file()]
    if len(matches) > 1:
        raise ValueError(f"expected at most one split image for {word}, got {len(matches)}")
    return matches[0] if matches else None


def marine_families() -> dict[str, dict]:
    records = json.loads(MARINE_MANIFEST.read_text(encoding="utf-8"))
    return {
        record["name"]: record
        for record in records
        if record.get("scope") == "family" and record.get("name")
    }


def merge_base_records(records: list[dict], plan: list[dict]) -> list[dict]:
    existing_names = {record["name"] for record in records}
    planned_names = {item["name"] for item in plan}
    overlap = existing_names & planned_names
    if overlap:
        raise ValueError(f"base manifest overlaps plan: {sorted(overlap)}")
    return records


def load_base_manifest(path: Path | None, plan: list[dict]) -> list[dict]:
    records = json.loads(path.read_text(encoding="utf-8")) if path else []
    return merge_base_records(records, plan)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("split_dirs", type=Path, nargs="*")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument(
        "--base-manifest", type=Path,
        help="merge the newly materialized records after an existing manifest",
    )
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    reused = marine_families()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    records = load_base_manifest(args.base_manifest, plan)
    generated_count = reused_count = 0
    for item in plan:
        output = args.out_dir / item["filename"]
        marine = reused.get(item["name"])
        source = locate(item["word"], args.split_dirs)
        if marine:
            if source:
                raise ValueError(f"{item['word']} has both a split and reusable marine image")
            reused_path = MARINE_IMAGE_DIR / marine["filename"]
            if not reused_path.is_file():
                raise ValueError(f"missing reusable marine image: {reused_path}")
            shutil.copyfile(reused_path, output)
            generation_account = "reused-marine-life-reviewed-asset"
            source_sha256 = hashlib.sha256(reused_path.read_bytes()).hexdigest()
            prompt = marine["prompt"]
            reused_from = f"images/marine_life/{marine['filename']}"
            reused_count += 1
        else:
            if not source:
                raise ValueError(f"missing accepted split image for {item['word']}")
            prepare(source, output)
            generation_account = (
                "account2" if source.parent.name.endswith("account2") else "account1"
            )
            source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
            prompt = item["prompt"]
            reused_from = ""
            generated_count += 1
        record = {
            "name": item["name"],
            "group": item.get("group") or item.get("class"),
            "member_count": item["member_count"],
            "japanese_examples": item["japanese_examples"],
            "filename": item["filename"],
            "created_at": date.today().isoformat(),
            "generator": (
                "reused reviewed marine-life family asset" if marine
                else "ChatGPT Web image generation via local CDP pipeline"
            ),
            "generation_account": generation_account,
            "use_case": "scientific-educational",
            "scope": "family",
            "label": "生成イメージ",
            "qc": {
                "status": "accepted",
                "reviewed_at": date.today().isoformat(),
                "method": "全数連絡票と原寸試作の目視確認",
                "checks": [
                    "分類群の代表形態", "不自然な解剖の有無", "文字混入",
                    "セル混線", "中央16:10トリミング",
                ],
            },
            "prompt": prompt,
            "requested_prompt": item["prompt"],
            "reused_from": reused_from,
            "source_sha256": source_sha256,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        }
        records.append(record)
    args.manifest_out.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"materialized={len(records)} generated={generated_count} reused={reused_count} "
        f"out={args.out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
