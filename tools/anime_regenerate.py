#!/usr/bin/env python3
"""Prepare ChatGPT prompts, track pending portraits, and split generated grids."""

import argparse
import json
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
QC = ROOT / ".generated/anime_qc/qc_ng_weak.jsonl"
WORK = ROOT / ".generated/anime_regen"
WORD_RE = re.compile(r"^(?:ac|dc)_\d{4}$")


def prompt_for(item: dict[str, str]) -> str:
    kind = {
        "human": "人間",
        "pet": "動物",
        "beastfolk": "獣人",
        "android": "アンドロイド",
        "robot": "ロボット",
    }.get(item["species"], item["species"])
    note = item["note"]
    if any(term in note for term in ("下着", "扇情的", "露出")):
        note = "現在画像は年齢感と役割の表現が弱く、設定との一致が不十分"
    if item["species"] == "human":
        subject_rule = "人物1人だけを描き、動物や別人物、複数ポーズは描かない。"
    elif item["species"] == "pet":
        subject_rule = "動物1匹だけを描き、人物や別の動物、複数ポーズは描かない。"
    else:
        subject_rule = "1人または1匹だけを描き、別人物や別の動物、複数ポーズは描かない。"
    return (
        f"完全オリジナルの架空アニメキャラクター「{item['name']}」の単独ポートレート。"
        f"設定は「{item['desc']}」、役割は「{item['role']}」、種族は{kind}。"
        f"現在画像の問題点「{note}」を必ず解消し、設定どおりの年齢、性別、"
        f"種族、服装、毛色、持ち物、雰囲気を明瞭に描く。1マスに{subject_rule}"
        "対象をセル中央に小さめに配置し、頭頂から靴底または足先まで上下左右に"
        "十分な白い余白を残して全身を描く。体の一部をセル外へ出さず、額縁、"
        "カード枠は描かない。日本のテレビアニメ風の端正なキャラクターデザイン、"
        "くっきりした線、フラットデザイン、パステルカラー、白背景、文字なし、正方形。"
    )


def prepare() -> None:
    items = [json.loads(line) for line in QC.read_text(encoding="utf-8").splitlines()]
    WORK.mkdir(parents=True, exist_ok=True)
    prepared = [
        {
            "word": item["file"].removesuffix(".jpg"),
            "prompt": prompt_for(item),
            "name": item["name"],
            "verdict": item["verdict"],
            "list": item["list"],
        }
        for item in items
    ]
    split = 225
    for account, rows in ((1, prepared[:split]), (2, prepared[split:])):
        path = WORK / f"account{account}.jsonl"
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
    (WORK / "items.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in prepared),
        encoding="utf-8",
    )
    print(f"prepared {len(prepared)} items: account1=225, account2={len(prepared) - split}")


def prepare_pending() -> None:
    items = [
        json.loads(line)
        for line in (WORK / "items.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    completed = {path.stem for path in (WORK / "images").glob("*.jpg")}
    pending = [item for item in items if item["word"] not in completed]
    for name, rows in (("pending", pending), ("pending_probe", pending[:16])):
        (WORK / f"{name}.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
    print(f"prepared {len(pending)} pending items")


def split_grids() -> None:
    grid_dir = WORK / "grids"
    out_dir = WORK / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    skipped = 0
    written: set[str] = set()
    for meta in sorted(grid_dir.glob("*.json")):
        data = json.loads(meta.read_text(encoding="utf-8"))
        source = grid_dir / f"grid_{meta.stem}.png"
        if not source.exists():
            skipped += 1
            continue
        image = Image.open(source).convert("RGB")
        cols, rows = data["cols"], data["rows"]
        words = data["words"]
        if not isinstance(cols, int) or not isinstance(rows, int) or cols < 1 or rows < 1:
            raise ValueError(f"{meta}: cols and rows must be positive integers")
        if not isinstance(words, list) or not words or len(words) > cols * rows:
            raise ValueError(f"{meta}: invalid words length for {cols}x{rows} grid")
        if any(not isinstance(word, str) or not WORD_RE.fullmatch(word) for word in words):
            raise ValueError(f"{meta}: invalid output stem")
        accepted = data.get("accepted", [True] * len(words))
        if len(accepted) != len(words) or any(type(value) is not bool for value in accepted):
            raise ValueError(
                f"{meta}: accepted length {len(accepted)} does not match "
                f"words length {len(words)}, or contains a non-boolean value"
            )
        for index, stem in enumerate(words):
            if not accepted[index]:
                continue
            if stem in written:
                raise ValueError(f"{meta}: duplicate accepted output stem {stem}")
            col, row = index % cols, index // cols
            x0, x1 = round(col * image.width / cols), round((col + 1) * image.width / cols)
            y0, y1 = round(row * image.height / rows), round((row + 1) * image.height / rows)
            trim_x, trim_y = int((x1 - x0) * 0.04), int((y1 - y0) * 0.04)
            cell = image.crop(
                (x0 + trim_x, y0 + trim_y, x1 - trim_x, y1 - trim_y)
            )
            side = min(cell.size)
            left, top = (cell.width - side) // 2, (cell.height - side) // 2
            cell = cell.crop((left, top, left + side, top + side))
            cell.resize((720, 720), Image.Resampling.LANCZOS).save(
                out_dir / f"{stem}.jpg", quality=92, optimize=True
            )
            written.add(stem)
            count += 1
    print(f"split {count} images into {out_dir}; skipped {skipped} incomplete grids")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "pending", "split"))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "pending":
        prepare_pending()
    else:
        split_grids()


if __name__ == "__main__":
    main()
