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
    "jade":   {"bg": "#e3efe9", "halo": "#d1e4da", "fig": "#42836a", "ink": "#2a5343",
               "chip": "#42836a", "chip_ink": "#eef6f2"},
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
        _stroke("M 100 78 C 76 66 52 48 32 26", bg, 2.8),
        _stroke("M 100 78 C 124 66 148 48 168 26", bg, 2.8),                  # 主脈
        _stroke("M 78 65 C 76 54 76 44 78 36 M 61 53 C 59 44 59 36 61 28 "
                "M 122 65 C 124 54 124 44 122 36 M 139 53 C 141 44 141 36 139 28",
                bg, 2.2),                                                     # 側脈
    ])


def shape_monocot(p: dict) -> str:
    """単子葉: 平行脈の細長い葉。"""
    f, bg = p["fig"], p["bg"]
    return "".join([
        _path("M 100 116 C 84 88 62 60 26 34 C 52 72 74 92 96 116 Z", f),
        _path("M 100 116 C 116 88 138 60 174 34 C 148 72 126 92 104 116 Z", f),
        _path("M 100 116 C 96 84 96 50 100 14 C 108 50 108 84 104 116 Z", f),
        _stroke("M 102 108 C 100 78 100 46 101 24", bg, 2.2),
        _stroke("M 86 106 C 74 84 60 64 44 48", bg, 2.2),
        _stroke("M 116 106 C 128 84 142 64 158 48", bg, 2.2),                 # 平行脈
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
    """シダ植物: 羽状複葉と、先が渦を巻いた新芽(ゼンマイ)。"""
    f = p["fig"]
    pinnae = []
    for i in range(7):
        y = 108 - i * 11          # 下ほど大きい羽片を対で並べる
        half = (46 - i * 5) / 2
        ry = 5.6 - i * 0.45
        for sign, ang in ((-1, 25), (1, -25)):
            pinnae.append(f'<ellipse cx="{100 + sign * half:g}" cy="{y}" '
                          f'rx="{half:g}" ry="{ry:g}" fill="{f}" '
                          f'transform="rotate({ang} 100 {y})"/>')
    return "".join([
        _stroke("M 100 118 C 100 90 100 60 104 34", f, 6),                    # 中軸
        *pinnae,
        _stroke("M 104 34 C 106 22 114 14 124 16 C 133 18 136 28 130 34 "
                "C 125 39 117 37 117 30", f, 6),                              # 巻いた新芽
    ])


def shape_moss(p: dict) -> str:
    """コケ植物: 蒴をつけた胞子体と、粒だったマット状の群落。"""
    f = p["fig"]
    parts = []
    for x, h, tilt in ((60, 42, -6), (84, 62, -2), (112, 50, 4), (136, 68, 8)):
        top = 102 - h
        parts.append(_stroke(f"M {x} 102 C {x - 2} {102 - h * 0.5:g} "
                             f"{x + tilt * 0.5:g} {102 - h * 0.8:g} "
                             f"{x + tilt} {top}", f, 3.5))                    # 蒴柄
        parts.append(f'<ellipse cx="{x + tilt}" cy="{top - 7}" rx="6.5" ry="9" '
                     f'fill="{f}" transform="rotate({tilt * 2} {x + tilt} {top - 7})"/>')
    # 群落: 上端を小さな弧の連なりにして、土の塊ではなく葉の粒だちに見せる
    x0, x1, n, base, rise = 16, 184, 12, 118, 24
    d = [f"M {x0} 120", f"L {x0} {base}"]
    for i in range(n):
        xa = x0 + (x1 - x0) * i / n
        xb = x0 + (x1 - x0) * (i + 1) / n
        ya = base - rise * (1 - abs(i / n * 2 - 1) ** 2)
        yb = base - rise * (1 - abs((i + 1) / n * 2 - 1) ** 2)
        d.append(f"C {xa + 2:g} {ya - 9:g} {xb - 2:g} {yb - 9:g} {xb:g} {yb:g}")
    d.append(f"L {x1} 120 Z")
    parts.append(_path(" ".join(d), f))
    return "".join(parts)


def shape_algae(p: dict) -> str:
    """藻類: 付着器から伸びる帯状の葉状体と、水中を示す気泡。"""
    f = p["fig"]
    return "".join([
        f'<circle cx="34" cy="34" r="6" fill="{f}" opacity="0.4"/>',
        f'<circle cx="52" cy="58" r="3.5" fill="{f}" opacity="0.4"/>',
        f'<circle cx="170" cy="46" r="7" fill="{f}" opacity="0.4"/>',
        f'<circle cx="154" cy="72" r="4" fill="{f}" opacity="0.4"/>',         # 気泡
        _stroke("M 100 114 C 94 100 86 92 76 84", f, 5),
        _stroke("M 100 114 C 100 100 100 92 100 80", f, 5),
        _stroke("M 100 114 C 108 102 118 94 126 86", f, 5),                   # 柄
        _path("M 76 84 C 54 68 44 42 46 16 C 70 32 86 60 76 84 Z", f),
        _path("M 100 80 C 82 60 82 30 96 6 C 114 30 116 60 100 80 Z", f),
        _path("M 126 86 C 126 60 140 34 158 20 C 160 48 148 72 126 86 Z", f),  # 葉状体
        f'<rect x="68" y="110" width="66" height="9" rx="4.5" fill="{f}"/>',  # 付着器
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
        ("コケ植物", "class_moss.svg", "moss", "jade"),
        ("藻類", "class_algae.svg", "algae", "indigo"),
        # plant.csv に現状 NA の行は無いが、将来 class が増えたときの受け皿。
        # sekitsui と同じ絵・同じファイル名で、リリースのアセットも共用する
        ("NA", "class_unknown.svg", "unknown", "gray"),
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
