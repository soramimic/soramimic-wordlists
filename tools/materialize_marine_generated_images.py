#!/usr/bin/env python3
"""分割済み生成画像を整形し、科・目画像のmanifestを作る。

usage: python3 tools/materialize_marine_generated_images.py PLAN SPLIT_DIR \
  [SPLIT_DIR ...] --out-dir DIR --manifest-out FILE
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from prepare_marine_generated_fallback import prepare


def split_filename(word: str) -> str:
    return "gk_" + hashlib.sha1(word.encode()).hexdigest()[:10] + ".png"


def locate(word: str, directories: list[Path]) -> Path:
    matches = [directory / split_filename(word) for directory in directories]
    matches = [path for path in matches if path.is_file()]
    if len(matches) != 1:
        raise ValueError(f"expected one split image for {word}, got {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("split_dirs", type=Path, nargs="+")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--base-manifest", type=Path)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    records = (
        json.loads(args.base_manifest.read_text(encoding="utf-8"))
        if args.base_manifest else []
    )
    for item in plan:
        source = locate(item["word"], args.split_dirs)
        output = args.out_dir / item["filename"]
        prepare(source, output)
        records.append({
            "name": item["name"],
            "group": item["group"],
            "member_count": item["member_count"],
            "scientific_examples": item["scientific_examples"],
            "japanese_examples": item["japanese_examples"],
            "filename": item["filename"],
            "created_at": date.today().isoformat(),
            "generator": "ChatGPT Web image generation via local CDP pipeline",
            "generation_account": (
                "account2" if source.parent.name == "split_account2" else "account1"
            ),
            "use_case": "scientific-educational",
            "scope": item["scope"],
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
            "prompt": item["prompt"],
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        })
    args.manifest_out.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"materialized={len(records)} out={args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
