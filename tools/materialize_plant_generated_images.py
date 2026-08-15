#!/usr/bin/env python3
"""植物の科別生成画像を960x600 WebPへ整形し、manifestを作る。"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from materialize_marine_generated_images import split_filename
from prepare_marine_generated_fallback import prepare


def locate(word: str, directories: list[Path]) -> Path | None:
    matches = [directory / split_filename(word) for directory in directories]
    matches = [path for path in matches if path.is_file()]
    if len(matches) > 1:
        raise ValueError(f"expected at most one split image for {word}, got {len(matches)}")
    return matches[0] if matches else None


def merge_base_records(records: list[dict], plan: list[dict]) -> list[dict]:
    existing = {(record.get("family_qid") or "", record.get("name")) for record in records}
    planned = {(item.get("family_qid") or "", item.get("name")) for item in plan}
    overlap = existing & planned
    if overlap:
        raise ValueError(f"base manifest overlaps plan: {sorted(overlap)}")
    return records


def load_base_manifest(path: Path | None, plan: list[dict]) -> list[dict]:
    records = json.loads(path.read_text(encoding="utf-8")) if path else []
    return merge_base_records(records, plan)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("split_dirs", type=Path, nargs="*")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--base-manifest", type=Path)
    args = parser.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    records = load_base_manifest(args.base_manifest, plan)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for item in plan:
        source = locate(item["word"], args.split_dirs)
        if not source:
            raise ValueError(f"missing accepted split image for {item['word']}")
        output = args.out_dir / item["filename"]
        prepare(source, output)
        raw = output.read_bytes()
        records.append({
            "name": item["name"], "family_qid": item.get("family_qid", ""),
            "group": item.get("class"), "member_count": item["member_count"],
            "japanese_examples": item["japanese_examples"],
            "scientific_examples": item.get("scientific_examples", []),
            "filename": item["filename"], "created_at": date.today().isoformat(),
            "generator": "OpenAI image generation",
            "use_case": "scientific-educational", "scope": "family",
            "label": "生成イメージ", "accepted": True,
            "qc": {"status": "accepted", "reviewed_at": date.today().isoformat(),
                   "method": "全数コンタクトシートと原寸画像の目視確認",
                   "checks": ["分類群の代表形態", "不自然な植物形態の有無", "文字混入",
                              "セル混線", "中央16:10トリミング"]},
            "prompt": item["prompt"], "requested_prompt": item["prompt"],
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    args.manifest_out.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print(f"materialized={len(plan)} total={len(records)} out={args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
