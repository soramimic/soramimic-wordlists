#!/usr/bin/env python3
"""生成画像manifestから、全数QC用のラベル付き連絡票を作る。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

COLS = 4
ROWS = 4
THUMB = (320, 200)
CAPTION_HEIGHT = 44


def font() -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 20
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("image_dir", type=Path)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()
    records = [
        record for record in json.loads(args.manifest.read_text(encoding="utf-8"))
        if record.get("scope") in {"family", "order"}
    ]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    sheet_size = (COLS * THUMB[0], ROWS * (THUMB[1] + CAPTION_HEIGHT))
    label_font = font()
    for page, start in enumerate(range(0, len(records), COLS * ROWS), 1):
        sheet = Image.new("RGB", sheet_size, "white")
        draw = ImageDraw.Draw(sheet)
        for index, record in enumerate(records[start:start + COLS * ROWS]):
            col, row = index % COLS, index // COLS
            left, top = col * THUMB[0], row * (THUMB[1] + CAPTION_HEIGHT)
            with Image.open(args.image_dir / record["filename"]) as source:
                image = source.convert("RGB").resize(THUMB, Image.Resampling.LANCZOS)
            sheet.paste(image, (left, top))
            draw.text((left + 8, top + THUMB[1] + 7), record["name"],
                      font=label_font, fill="black")
        sheet.save(args.out_dir / f"marine_generated_qc_{page:02d}.jpg", quality=90)
    print(f"sheets={(len(records) + COLS * ROWS - 1) // (COLS * ROWS)} images={len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
