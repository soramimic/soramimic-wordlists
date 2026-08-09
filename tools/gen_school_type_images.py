#!/usr/bin/env python3
"""学校の実写が無い行に使う校種別の概念イメージSVGを生成する。

特定の学校・校舎・校章を表現せず、校種を示す汎用的な建物と記号だけを描く。
実写との誤認を避けるため、すべての画像に「イメージ」と明記する。

usage: python3 tools/gen_school_type_images.py [--out images/school_type] [--prune]
"""

import argparse
from html import escape
from pathlib import Path

W, H = 320, 200

# school_type -> (filename, background, accent, icon family)
SCHOOL_TYPES = {
    "幼稚園": ("kindergarten.svg", "#f7eee2", "#b66f45", "play"),
    "認定こども園": ("kodomoen.svg", "#f5eadf", "#a96645", "play"),
    "小学校": ("elementary.svg", "#e8f1e8", "#4f7f5d", "book"),
    "中学校": ("junior_high.svg", "#e7eef3", "#4d7188", "book"),
    "義務教育学校": ("compulsory.svg", "#e7efe9", "#457665", "book"),
    "高等学校": ("high_school.svg", "#e9eaf3", "#596695", "book"),
    "中等教育学校": ("secondary.svg", "#e9edf4", "#536f91", "book"),
    "特別支援学校": ("special_support.svg", "#f2eaf2", "#84608b", "support"),
    "大学": ("university.svg", "#eee9e3", "#795e47", "college"),
    "短期大学": ("junior_college.svg", "#f0eae5", "#80644e", "college"),
    "高等専門学校": ("technical_college.svg", "#e7efef", "#47777b", "gear"),
    "専修学校": ("vocational.svg", "#f1ece2", "#806d43", "tools"),
    "各種学校": ("miscellaneous.svg", "#ecebe8", "#6d6b63", "tools"),
}


def icon(kind: str, color: str) -> str:
    if kind == "play":
        return (
            f'<circle cx="160" cy="50" r="13" fill="{color}"/>'
            f'<path d="M132 82 L160 52 L188 82 Z" fill="{color}"/>'
            f'<rect x="142" y="76" width="36" height="8" rx="4" fill="#fff" opacity=".8"/>'
        )
    if kind == "college":
        return (
            f'<path d="M122 69 L160 43 L198 69 Z" fill="{color}"/>'
            f'<rect x="128" y="69" width="64" height="7" fill="{color}"/>'
            f'<path d="M134 78 V105 M151 78 V105 M169 78 V105 M186 78 V105" '
            f'stroke="{color}" stroke-width="7"/>'
        )
    if kind == "gear":
        return (
            f'<circle cx="160" cy="71" r="26" fill="none" stroke="{color}" stroke-width="9"/>'
            f'<circle cx="160" cy="71" r="8" fill="{color}"/>'
            f'<path d="M160 34 V45 M160 97 V108 M123 71 H134 M186 71 H197 '
            f'M134 45 L142 53 M178 89 L186 97 M186 45 L178 53 M142 89 L134 97" '
            f'stroke="{color}" stroke-width="8" stroke-linecap="round"/>'
        )
    if kind == "support":
        return (
            f'<circle cx="160" cy="55" r="12" fill="{color}"/>'
            f'<path d="M160 70 C140 54 122 70 132 86 C142 101 160 108 160 108 '
            f'C160 108 178 101 188 86 C198 70 180 54 160 70 Z" fill="{color}"/>'
        )
    if kind == "tools":
        return (
            f'<path d="M132 43 L188 99 M188 43 L132 99" stroke="{color}" '
            f'stroke-width="10" stroke-linecap="round"/>'
            f'<circle cx="132" cy="43" r="9" fill="none" stroke="{color}" stroke-width="6"/>'
            f'<path d="M178 37 L194 53 L186 61 L170 45 Z" fill="{color}"/>'
        )
    # open book
    return (
        f'<path d="M118 48 Q140 42 160 57 V104 Q140 89 118 94 Z" fill="{color}"/>'
        f'<path d="M202 48 Q180 42 160 57 V104 Q180 89 202 94 Z" fill="{color}"/>'
        f'<path d="M160 57 V104" stroke="#fff" stroke-width="3" opacity=".8"/>'
    )


def render(label: str, background: str, accent: str, family: str) -> str:
    title = escape(f"{label}のイメージ画像")
    text = escape(label)
    return "\n".join([
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200" role="img">',
        f"<title>{title}</title>",
        f'<rect width="320" height="200" rx="16" fill="{background}"/>',
        f'<circle cx="160" cy="76" r="62" fill="#fff" opacity=".55"/>',
        # 汎用の校舎。特定校の外観や意匠は使わない。
        f'<path d="M72 126 V83 L104 67 V126 M104 126 V74 H216 V126 '
        f'M216 126 V83 L248 67 V126" fill="#fff" stroke="{accent}" stroke-width="6" '
        f'stroke-linejoin="round"/>',
        f'<path d="M142 126 V105 H178 V126" fill="{background}" stroke="{accent}" stroke-width="5"/>',
        f'<path d="M88 99 H96 M88 113 H96 M224 99 H232 M224 113 H232" '
        f'stroke="{accent}" stroke-width="6" stroke-linecap="round"/>',
        icon(family, accent),
        f'<rect x="0" y="139" width="320" height="61" fill="{accent}"/>',
        f'<text x="160" y="177" text-anchor="middle" fill="#fff" font-size="25" '
        f'font-weight="700" font-family="Noto Sans JP,Hiragino Sans,sans-serif">{text}</text>',
        f'<rect x="237" y="12" width="70" height="25" rx="12.5" fill="{accent}"/>',
        '<text x="272" y="30" text-anchor="middle" fill="#fff" font-size="13" '
        'font-weight="700" font-family="Noto Sans JP,Hiragino Sans,sans-serif">イメージ</text>',
        '</svg>',
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parent.parent / "images" / "school_type")
    parser.add_argument("--prune", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    wanted = set()
    for label, (filename, bg, accent, family) in SCHOOL_TYPES.items():
        wanted.add(filename)
        (args.out / filename).write_text(render(label, bg, accent, family), encoding="utf-8")
    if args.prune:
        for path in args.out.glob("*.svg"):
            if path.name not in wanted:
                path.unlink()
    print(f"generated {len(wanted)} school type images in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
