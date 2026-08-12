#!/usr/bin/env python3
"""画像生成ツールの横長素材を海洋生物fallbackへ整形する。

入力画像から中央16:10を切り出し、960x600へ縮小して右上に
「生成イメージ」を焼き込む。生成モデルの出力自体には文字を任せず、表示を
決定的にするための後処理だけを担当する。

usage: python3 tools/prepare_marine_generated_fallback.py INPUT OUTPUT
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = (960, 600)
LABEL = "生成イメージ"
FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
)


def font() -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, 34)
    raise RuntimeError("日本語フォントが見つかりません")


def prepare(source: Path, output: Path) -> None:
    with Image.open(source) as raw:
        image = raw.convert("RGB")
    target_ratio = SIZE[0] / SIZE[1]
    if image.width / image.height > target_ratio:
        width = round(image.height * target_ratio)
        left = (image.width - width) // 2
        image = image.crop((left, 0, left + width, image.height))
    else:
        height = round(image.width / target_ratio)
        top = (image.height - height) // 2
        image = image.crop((0, top, image.width, top + height))
    image = image.resize(SIZE, Image.Resampling.LANCZOS)

    draw = ImageDraw.Draw(image, "RGBA")
    label_font = font()
    box = draw.textbbox((0, 0), LABEL, font=label_font, stroke_width=1)
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    pad_x, pad_y, margin = 22, 13, 18
    right = image.width - margin
    bottom = margin + text_height + pad_y * 2
    left = right - text_width - pad_x * 2
    draw.rounded_rectangle(
        (left, margin, right, bottom), radius=18,
        fill=(5, 18, 32, 215), outline=(255, 255, 255, 230), width=2,
    )
    draw.text(
        (left + pad_x, margin + pad_y - box[1]), LABEL, font=label_font,
        fill=(255, 255, 255, 255), stroke_width=1, stroke_fill=(0, 0, 0, 230),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "WEBP", quality=88, method=6)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
