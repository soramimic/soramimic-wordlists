#!/usr/bin/env python3
"""分類(class列)レベルの概念イメージSVGを生成する。

実写画像が取れない行のために、**その分類のイメージ**を1枚ずつ用意する。
特定の種を描かず、その分類を代表する記号的なシルエットだけを描く。実写と
誤認されないよう、画面右上に「イメージ」の札を必ず入れる。

- 自己完結SVG(外部参照なし)。viewBox は 320x200 固定
- 分類名・配色・シルエットは GROUPS/PALETTES/SHAPES の定義テーブルで持つ。
  sekitsui(脊椎動物)と plant(植物)の両方に対応する
- 生成物はリポジトリに置かず、GitHub Release のアセットとして配布する
  (CSVの image/image_page はそのURLを指す)

usage:
  python3 tools/gen_class_images.py --group sekitsui --out /tmp/class_images
  python3 tools/gen_class_images.py --group all --out /tmp/class_images
"""

import argparse
from pathlib import Path

W, H = 320, 200
# シルエットのローカル座標系(200x120)を配置する中心と倍率
FIG_CX, FIG_CY, FIG_SCALE = 160, 92, 0.95

# 分類ごとの配色。彩度は控えめ(実写と並んでも浮かないトーン)
# bg=背景, halo=背景に敷く楕円, fig=シルエット, ink=分類名の文字,
# chip=「イメージ」札の地色, chip_ink=札の文字
PALETTES = {
    "teal":   {"bg": "#e4eef1", "halo": "#d2e2e7", "fig": "#3f6f7e", "ink": "#28454e",
               "chip": "#3f6f7e", "chip_ink": "#eef5f7"},
    "green":  {"bg": "#e7efe7", "halo": "#d7e5d7", "fig": "#4c7a56", "ink": "#2f4d36",
               "chip": "#4c7a56", "chip_ink": "#eff5ef"},
    "olive":  {"bg": "#eeefe1", "halo": "#e0e2cd", "fig": "#6e7a3f", "ink": "#464e28",
               "chip": "#6e7a3f", "chip_ink": "#f4f5ec"},
    "indigo": {"bg": "#e8eaf3", "halo": "#d8dcec", "fig": "#4e5f8f", "ink": "#313d5c",
               "chip": "#4e5f8f", "chip_ink": "#eff1f8"},
    "brown":  {"bg": "#f1eae4", "halo": "#e5dad0", "fig": "#7a5a44", "ink": "#4e392b",
               "chip": "#7a5a44", "chip_ink": "#f6f0eb"},
    "gray":   {"bg": "#ecebe7", "halo": "#dedcd6", "fig": "#6b6b64", "ink": "#454540",
               "chip": "#6b6b64", "chip_ink": "#f2f1ee"},
    "amber":  {"bg": "#f2ece0", "halo": "#e7dfcc", "fig": "#8a6a35", "ink": "#584322",
               "chip": "#8a6a35", "chip_ink": "#f7f3ea"},
    "moss":   {"bg": "#e9eee6", "halo": "#dae3d5", "fig": "#5c7444", "ink": "#3a4a2b",
               "chip": "#5c7444", "chip_ink": "#f1f4ee"},
}


def _path(d: str, fill: str) -> str:
    return f'<path d="{d}" fill="{fill}"/>'


def _stroke(d: str, color: str, width: float) -> str:
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')


# --- シルエット(ローカル座標 200x120、原点は左上) ------------------------
# いずれも「その綱の一般的・記号的な姿」。実在の特定種は描かない

def shape_fish(p: dict) -> str:
    f, bg = p["fig"], p["bg"]
    return "".join([
        _path("M 92 27 C 100 10 122 4 140 10 C 124 15 110 21 100 30 Z", f),   # 背びれ
        _path("M 96 92 C 102 106 116 112 128 110 C 118 104 108 98 102 90 Z", f),  # 腹びれ
        _path("M 34 60 L 6 36 C 12 52 12 68 6 84 Z", f),                      # 尾びれ
        _path("M 30 60 C 52 30 96 20 132 26 C 158 31 176 43 186 60 "
              "C 176 77 158 89 132 94 C 96 100 52 90 30 60 Z", f),            # 体
        f'<circle cx="166" cy="52" r="4.5" fill="{bg}"/>',                    # 目
    ])


def shape_bird(p: dict) -> str:
    f, bg = p["fig"], p["bg"]
    return "".join([
        f'<rect x="56" y="112" width="116" height="6" rx="3" fill="{f}"/>',   # とまり木
        _stroke("M 104 100 L 104 114", f, 5),
        _stroke("M 122 100 L 122 114", f, 5),                                 # 脚
        _path("M 120 20 C 148 22 162 46 158 72 C 154 96 136 110 112 108 "
              "C 92 106 76 92 72 74 L 30 106 L 60 64 C 66 40 96 18 120 20 Z", f),  # 体+尾
        f'<circle cx="134" cy="34" r="20" fill="{f}"/>',                      # 頭
        _path("M 152 29 L 176 36 L 152 44 Z", f),                             # くちばし
        f'<circle cx="142" cy="30" r="3.5" fill="{bg}"/>',                    # 目
    ])


def shape_reptile(p: dict) -> str:
    f, bg = p["fig"], p["bg"]
    return "".join([
        _stroke("M 126 48 L 122 32 L 108 27", f, 9),
        _stroke("M 126 72 L 122 88 L 108 93", f, 9),
        _stroke("M 84 48 L 76 32 L 62 28", f, 9),
        _stroke("M 84 72 L 76 88 L 62 92", f, 9),                             # 四肢
        _path("M 70 44 C 42 38 24 50 4 72 C 26 60 46 56 72 62 "
              "C 74 54 72 48 70 44 Z", f),                                    # 尾
        f'<ellipse cx="102" cy="60" rx="38" ry="19" fill="{f}"/>',            # 胴
        f'<ellipse cx="150" cy="60" rx="22" ry="14" fill="{f}"/>',            # 頭
        f'<circle cx="160" cy="53" r="3.5" fill="{bg}"/>',                    # 目
    ])


def shape_amphibian(p: dict) -> str:
    f, bg = p["fig"], p["bg"]
    return "".join([
        _stroke("M 74 74 L 44 78 L 36 102 L 56 112", f, 13),
        _stroke("M 126 74 L 156 78 L 164 102 L 144 112", f, 13),              # 後肢
        _stroke("M 78 50 L 56 58 L 50 76", f, 9),
        _stroke("M 122 50 L 144 58 L 150 76", f, 9),                          # 前肢
        _path("M 100 28 C 124 28 138 52 134 78 C 130 100 118 110 100 110 "
              "C 82 110 70 100 66 78 C 62 52 76 28 100 28 Z", f),             # 体
        f'<circle cx="83" cy="32" r="12" fill="{f}"/>',
        f'<circle cx="117" cy="32" r="12" fill="{f}"/>',                      # 目の膨らみ
        f'<circle cx="83" cy="30" r="4.5" fill="{bg}"/>',
        f'<circle cx="117" cy="30" r="4.5" fill="{bg}"/>',                    # 瞳
    ])


def shape_mammal(p: dict) -> str:
    f, bg = p["fig"], p["bg"]
    return "".join([
        _stroke("M 44 46 C 30 40 22 50 20 64", f, 7),                         # 尾
        f'<rect x="56" y="78" width="13" height="36" rx="6" fill="{f}"/>',
        f'<rect x="78" y="78" width="13" height="36" rx="6" fill="{f}"/>',
        f'<rect x="104" y="78" width="13" height="36" rx="6" fill="{f}"/>',
        f'<rect x="125" y="78" width="13" height="36" rx="6" fill="{f}"/>',   # 四肢
        _path("M 42 46 C 42 34 52 28 66 28 L 118 28 C 132 28 140 36 142 48 "
              "L 142 66 C 140 78 130 84 118 84 L 64 84 C 50 84 42 76 42 66 Z", f),  # 胴
        _path("M 145 18 C 142 6 150 0 156 8 L 159 20 Z", f),
        _path("M 165 16 C 167 5 176 4 177 13 L 173 24 Z", f),                 # 耳
        _path("M 122 34 L 142 18 L 158 34 L 140 58 Z", f),                    # 首
        f'<circle cx="158" cy="32" r="21" fill="{f}"/>',                      # 頭
        _path("M 172 24 C 186 22 193 29 191 36 C 189 43 177 46 169 41 Z", f),  # 鼻づら
        f'<circle cx="166" cy="27" r="3.2" fill="{bg}"/>',                    # 目
    ])


def shape_unknown(p: dict) -> str:
    f = p["fig"]
    return "".join([
        f'<rect x="54" y="12" width="92" height="96" rx="18" fill="none" '
        f'stroke="{f}" stroke-width="5" stroke-dasharray="11 10" stroke-linecap="round"/>',
        f'<text x="100" y="86" text-anchor="middle" fill="{f}" '
        f'font-size="62" font-weight="700" '
        f'font-family="Noto Sans JP,Hiragino Sans,sans-serif">?</text>',
    ])


def shape_dicot(p: dict) -> str:
    """双子葉: 網状脈の広い葉。"""
    f, bg = p["fig"], p["bg"]
    return "".join([
        _stroke("M 100 116 L 100 74", f, 6),                                  # 葉柄
        _path("M 100 78 C 60 76 30 54 26 20 C 66 16 96 38 100 78 Z", f),
        _path("M 100 78 C 140 76 170 54 174 20 C 134 16 104 38 100 78 Z", f),  # 葉身
        _stroke("M 100 78 L 44 26", bg, 3),
        _stroke("M 100 78 L 156 26", bg, 3),                                  # 主脈
        _stroke("M 82 62 L 72 40 M 64 48 L 56 30 M 118 62 L 128 40 "
                "M 136 48 L 144 30", bg, 2.5),                                # 側脈
    ])


def shape_monocot(p: dict) -> str:
    """単子葉: 平行脈の細長い葉。"""
    f, bg = p["fig"], p["bg"]
    return "".join([
        _path("M 100 116 C 84 88 62 60 26 34 C 52 72 74 92 96 116 Z", f),
        _path("M 100 116 C 116 88 138 60 174 34 C 148 72 126 92 104 116 Z", f),
        _path("M 100 116 C 96 84 96 50 100 14 C 108 50 108 84 104 116 Z", f),
        _stroke("M 100 110 C 98 78 98 46 100 24", bg, 2.5),
        _stroke("M 84 108 C 72 84 58 62 40 44", bg, 2.5),
        _stroke("M 118 108 C 130 84 144 62 162 44", bg, 2.5),                 # 平行脈
    ])


def shape_gymnosperm(p: dict) -> str:
    """裸子植物: 針葉樹。"""
    f = p["fig"]
    return "".join([
        f'<rect x="93" y="92" width="14" height="24" rx="4" fill="{f}"/>',    # 幹
        _path("M 100 8 L 132 46 L 68 46 Z", f),
        _path("M 100 34 L 142 74 L 58 74 Z", f),
        _path("M 100 60 L 152 98 L 48 98 Z", f),                              # 樹冠
    ])


def shape_fern(p: dict) -> str:
    """シダ植物: 先が巻いた羽状複葉。"""
    f = p["fig"]
    pinnae = []
    for i in range(6):
        y = 100 - i * 14
        length = 46 - i * 5
        pinnae.append(_stroke(f"M 100 {y} C {100 - length * 0.6} {y - 2} "
                              f"{100 - length} {y - 8} {100 - length} {y - 16}", f, 6))
        pinnae.append(_stroke(f"M 100 {y} C {100 + length * 0.6} {y - 2} "
                              f"{100 + length} {y - 8} {100 + length} {y - 16}", f, 6))
    return "".join([
        _stroke("M 100 116 C 100 80 100 48 104 26 C 106 14 118 10 124 18 "
                "C 129 25 124 33 116 31", f, 7),                              # 中軸と巻きひげ
        *pinnae,
    ])


def shape_moss(p: dict) -> str:
    """コケ植物: 群落と胞子体(蒴)。"""
    f = p["fig"]
    stalks = []
    for x, h in ((66, 40), (88, 56), (112, 48), (136, 62)):
        stalks.append(_stroke(f"M {x} 96 C {x - 3} {96 - h * 0.6} {x + 3} "
                              f"{96 - h * 0.8} {x} {96 - h}", f, 4))
        stalks.append(f'<ellipse cx="{x}" cy="{96 - h - 6}" rx="8" ry="6" fill="{f}"/>')
    return "".join([
        *stalks,
        _path("M 24 116 C 30 96 48 90 66 98 C 82 88 104 90 116 100 "
              "C 134 90 158 96 176 116 Z", f),                                # 群落
    ])


def shape_algae(p: dict) -> str:
    """藻類: 水中でゆれる帯状の葉状体。"""
    f = p["fig"]
    return "".join([
        _stroke("M 76 116 C 62 90 70 62 58 34 C 54 24 60 16 68 18", f, 9),
        _stroke("M 100 116 C 96 84 108 56 100 26 C 98 14 106 8 114 12", f, 11),
        _stroke("M 124 116 C 136 92 130 68 142 44 C 147 34 142 26 134 26", f, 8),
        _stroke("M 92 84 C 78 74 74 62 76 50", f, 5),
        _stroke("M 110 70 C 124 62 128 50 126 38", f, 5),                     # 側枝
        f'<rect x="60" y="112" width="86" height="8" rx="4" fill="{f}"/>',    # 付着器
    ])


SHAPES = {
    "fish": shape_fish, "bird": shape_bird, "reptile": shape_reptile,
    "amphibian": shape_amphibian, "mammal": shape_mammal, "unknown": shape_unknown,
    "dicot": shape_dicot, "monocot": shape_monocot, "gymnosperm": shape_gymnosperm,
    "fern": shape_fern, "moss": shape_moss, "algae": shape_algae,
}

# 分類ごとの定義: (class列の値, ファイル名, シルエット, 配色)
# ファイル名は class_<英名>.svg。class列の値をそのままファイル名にしない
# (URLに日本語が入らないようにするため)
GROUPS = {
    "sekitsui": [
        ("魚類", "class_fish.svg", "fish", "teal"),
        ("両生類", "class_amphibian.svg", "amphibian", "green"),
        ("爬虫類", "class_reptile.svg", "reptile", "olive"),
        ("鳥類", "class_bird.svg", "bird", "indigo"),
        ("哺乳類", "class_mammal.svg", "mammal", "brown"),
        ("NA", "class_unknown.svg", "unknown", "gray"),
    ],
    # plant.csv 用(将来リリースする場合に使う。現時点では未配布)
    "plant": [
        ("双子葉", "class_dicot.svg", "dicot", "green"),
        ("単子葉", "class_monocot.svg", "monocot", "moss"),
        ("裸子植物", "class_gymnosperm.svg", "gymnosperm", "teal"),
        ("シダ植物", "class_fern.svg", "fern", "olive"),
        ("コケ植物", "class_moss.svg", "moss", "amber"),
        ("藻類", "class_algae.svg", "algae", "indigo"),
    ],
}

# class列の値をそのまま画面に出すと "NA" になってしまう分類の表示名
DISPLAY_LABEL = {"NA": "分類不明"}

FONT = "Noto Sans JP,Hiragino Sans,Yu Gothic,Meiryo,sans-serif"


def render(label: str, shape: str, palette: str) -> str:
    p = PALETTES[palette]
    disp = DISPLAY_LABEL.get(label, label)
    tx = FIG_CX - 100 * FIG_SCALE
    ty = FIG_CY - 60 * FIG_SCALE
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" \
width="{W}" height="{H}" role="img" aria-label="{disp}のイメージ画像">
<title>{disp}のイメージ画像</title>
<desc>特定の種ではなく{disp}という分類を表す概念イメージ。実写ではありません。</desc>
<rect width="{W}" height="{H}" rx="16" fill="{p['bg']}"/>
<ellipse cx="{FIG_CX}" cy="{FIG_CY + 4}" rx="106" ry="60" fill="{p['halo']}"/>
<g transform="translate({tx:g} {ty:g}) scale({FIG_SCALE:g})">{SHAPES[shape](p)}</g>
<rect x="240" y="10" width="70" height="22" rx="11" fill="{p['chip']}"/>
<text x="275" y="26" text-anchor="middle" fill="{p['chip_ink']}" font-size="13" \
font-weight="600" font-family="{FONT}">イメージ</text>
<text x="160" y="180" text-anchor="middle" fill="{p['ink']}" font-size="24" \
font-weight="700" font-family="{FONT}">{disp}</text>
</svg>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group", default="sekitsui",
                    choices=[*GROUPS, "all"], help="生成する分類グループ")
    ap.add_argument("--out", default="class_images", help="出力ディレクトリ")
    args = ap.parse_args()

    groups = list(GROUPS) if args.group == "all" else [args.group]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for g in groups:
        for label, fname, shape, palette in GROUPS[g]:
            (out / fname).write_text(render(label, shape, palette), encoding="utf-8")
            print(f"{g}: {label} -> {out / fname}")
            n += 1
    print(f"{n}枚を生成: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
