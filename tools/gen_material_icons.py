#!/usr/bin/env python3
"""Material Symbols から `tools/material_icons.py`(職業アイコン)を生成する。

減量版カード(`--style minimal`)の地紋に敷く職業アイコンの取り込み。
判断の経緯は ADR 00022。

**構成**: 人が就く役割は「人型のポーズ + 小さな役割マーク」で描く。
人型が職業を人として示し、マークが職業を確定させる。マスコットだけは
人ではないのでキャラクターの図そのものを使う。

**バリエーション**: 同じ役割でも1枚ごとに見た目が変わるよう、役割ごとに
ポーズのプールを持つ。どのポーズを使うかは `silhouettes.py` が
**人物IDのハッシュから決定的に**選ぶ(乱数ではない。乱数だと再生成のたびに
1万3千枚すべてが差分になる)。左右反転・微小な回転・上下オフセットも
同じハッシュから決まる。

各アイコンは `viewBox="0 -960 960 960"` で、実インクは箱いっぱいには
広がっていない。**描画してアルファのbboxを測り**、カード用の 0..100 の
座標系へ収める `transform` を計算して外側に巻く。
**パスデータそのものは1バイトも変えない。**

生成物はリポジトリに入れてあるので、割り当てを変えるとき以外は走らせる必要は
ない。走らせるときだけ描画用のライブラリが要る:

  uv run --with cairosvg --with pillow python tools/gen_material_icons.py

取得元は master ブランチなので、再生成すると上流の描き直しを拾うことがある。
その場合は compare シートで6役割の見え方を確認してから差し替えること。
"""
import io
import math
import re
import urllib.request
from pathlib import Path

import cairosvg
from PIL import Image

TOOLS = Path(__file__).resolve().parent
CACHE = TOOLS / ".cache" / "material-symbols"
OUT = TOOLS / "material_icons.py"

# Rounded / 塗りつぶし / wght700。wght400 だと走る人型だけが細い棒線になり、
# ホイッスルやカメラのような塗りの塊と並べたとき薄く見える。地紋として
# 薄く敷くので、面の量が揃っていることを優先する
BASE = ("https://raw.githubusercontent.com/google/material-design-icons/"
        "master/symbols/web/{name}/materialsymbolsrounded/"
        "{name}_wght700fill1_48px.svg")

PROBE = 480          # bbox測定時のレンダリング解像度
VB = 960.0           # Material Symbols の viewBox 一辺

# **アイコンはどれも右端を x=LIMIT までに収める。** カード上ではこの 0..100 の
# 枠が `silhouettes.SIL_PLACEMENTS["water"]` で拡大されて敷かれるが、その右側
# には頭文字ディスク(cx=160, r=48+ハローの5)が不透明で乗る。中央から右を
# ディスクに食われると形が壊れて読めなくなるので、手前で止める。
LIMIT = 88

# 実行時にハッシュで振れる幅。`silhouettes.py` と必ず揃えること。
# 生成時にこの幅で振っても枠から出ないところまで縮めてある。
MAX_ROT = 5.0        # 回転(度)
MAX_DY = 3.0         # 上下オフセット
FLIP_AXIS = LIMIT / 2                # 左右反転の軸
ROT_CX, ROT_CY = LIMIT / 2, 50.0     # 回転の中心

# 役割ごとの構成。
#   poses      : ポーズのプール(この中からIDのハッシュで1つ選ぶ)
#   figure_box : 人型を収める箱 (x, y, w, h) in 0..100
#   mark       : 小さな役割マーク (アイコン名, 中心x, 中心y, 直径)。None なら無し
#
# ポーズは**小道具の付いていない全身の人型**から選ぶ。`hiking`(杖)や
# `follow_the_signs`(標識)のように元から物を持っている図は、役割マークと
# 情報がぶつかるので使わない。`person` 系の胸像も、全身のポーズと並べると
# 別の家族に見えるので使わない。
ROLES = {
    # サッカー選手: 走る・蹴るなどの躍動。足元に小さなサッカーボール
    "football_player": {
        "poses": ["directions_run", "sports_martial_arts",
                  "sports_gymnastics", "directions_walk"],
        "figure_box": (2, 4, 70, 88),
        "mark": ("sports_soccer", 74, 84, 26),
    },
    # サッカー監督: 指示を出す立ち姿。躍動する選手とは体の使い方で分ける。
    # 手元にホイッスル
    "manager": {
        "poses": ["emoji_people", "accessibility_new", "directions_walk",
                  "hail"],
        "figure_box": (2, 6, 70, 86),
        "mark": ("sports", 73, 22, 30),
    },
    # クラブマスコット: 人ではないのでキャラクターの図そのもの。マークは不要
    "mascot": {
        "poses": ["smart_toy", "robot", "robot_2", "pets"],
        "figure_box": (4, 6, 80, 86),
        "mark": None,
    },
    # プロ野球選手: 走塁・構えの立ち姿。手元にバットとボール
    "baseball_batter": {
        "poses": ["directions_run", "accessibility_new", "directions_walk",
                  "sports_gymnastics"],
        "figure_box": (2, 6, 70, 86),
        "mark": ("sports_cricket", 73, 22, 30),
    },
    # YouTuber: 挨拶・立ち姿。手元にビデオカメラ
    "youtuber": {
        "poses": ["emoji_people", "accessibility_new", "directions_walk",
                  "hail"],
        "figure_box": (2, 6, 70, 86),
        "mark": ("videocam", 73, 22, 30),
    },
    # VTuber: 座って配信する図も混ぜる。手元にヘッドセット
    "vtuber": {
        "poses": ["self_improvement", "emoji_people", "accessibility_new",
                  "directions_walk"],
        "figure_box": (2, 6, 70, 86),
        "mark": ("headset_mic", 73, 22, 30),
    },
}


def fetch(name: str) -> str:
    """アイコンのSVGを取ってくる(`tools/.cache/` に残す)。"""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{name}.svg"
    if not p.exists():
        with urllib.request.urlopen(BASE.format(name=name), timeout=30) as r:
            p.write_bytes(r.read())
    return p.read_text(encoding="utf-8")


def icon_path(name: str) -> str:
    """SVGから `d` 属性だけを取り出す。1アイコン=1パスであることも確かめる。"""
    body = re.search(r"<svg[^>]*>(.*)</svg>", fetch(name), re.S).group(1)
    body = body.strip()
    assert body.startswith("<path") and body.count("<path") == 1, name
    return re.search(r'\sd="([^"]+)"', body).group(1)


def _bbox_of(svg_body: str, viewbox: str, span: float):
    """SVG断片を描いて、実インクのbboxを viewBox 座標(x, y, w, h)で返す。"""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{PROBE}" '
           f'height="{PROBE}" viewBox="{viewbox}">{svg_body}</svg>')
    buf = io.BytesIO()
    cairosvg.svg2png(bytestring=svg.encode(), write_to=buf,
                     output_width=PROBE, output_height=PROBE)
    bb = Image.open(buf).convert("RGBA").getchannel("A").getbbox()
    k = span / PROBE
    return bb[0] * k, bb[1] * k, (bb[2] - bb[0]) * k, (bb[3] - bb[1]) * k


def ink_bbox(name: str):
    """アイコン単体の実インクのbboxを viewBox 座標で返す。"""
    x, y, w, h = _bbox_of(f'<path d="{icon_path(name)}"/>',
                          "0 -960 960 960", VB)
    return x, y - 960, w, h


def fit(name: str, box) -> str:
    """インクbboxを box (x, y, w, h) に「contain」で収める transform。"""
    bx, by, bw, bh = ink_bbox(name)
    tx, ty, tw, th = box
    s = min(tw / bw, th / bh)
    return (f"translate({tx + (tw - s * bw) / 2 - s * bx:.2f} "
            f"{ty + (th - s * bh) / 2 - s * by:.2f}) scale({s:.5f})")


def fit_disc(name: str, cx: float, cy: float, d: float) -> str:
    """インクbboxの長辺が d になるよう縮めて (cx, cy) を中心に置く。"""
    bx, by, bw, bh = ink_bbox(name)
    s = d / max(bw, bh)
    return (f"translate({cx - s * (bx + bw / 2):.2f} "
            f"{cy - s * (by + bh / 2):.2f}) scale({s:.5f})")


def worst_case(bb):
    """実行時の振れ(反転・回転・上下)を全部かけたときの最大のbboxを返す。

    実行時は `silhouettes.py` が反転→回転→上下移動の順に外側から掛ける。
    どの組み合わせでも枠(0..LIMIT, 0..100)に収まっていることを、
    生成時にこの矩形で確かめる。
    """
    x, y, w, h = bb
    corners = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
    # 左右反転も候補に入れる(軸 FLIP_AXIS のまわり)
    corners += [(2 * FLIP_AXIS - cx, cy) for cx, cy in corners]
    xs, ys = [], []
    for deg in (-MAX_ROT, 0.0, MAX_ROT):
        t = math.radians(deg)
        for cx, cy in corners:
            dx, dy = cx - ROT_CX, cy - ROT_CY
            xs.append(ROT_CX + dx * math.cos(t) - dy * math.sin(t))
            ys.append(ROT_CY + dx * math.sin(t) + dy * math.cos(t))
    return min(xs), min(ys) - MAX_DY, max(xs), max(ys) + MAX_DY


def compose(role: str, pose: str) -> str:
    """1ポーズぶんの断片。枠からはみ出すなら中心のまわりに縮めて収める。"""
    cfg = ROLES[role]
    parts = [f'<g transform="{fit(pose, cfg["figure_box"])}">'
             f'<path d="{icon_path(pose)}"/></g>']
    if cfg["mark"]:
        parts.append(f'<g transform="{fit_disc(*cfg["mark"])}">'
                     f'<path d="{icon_path(cfg["mark"][0])}"/></g>')
    body = "".join(parts)

    # 実際に描いて測る。ポーズごとに手足の張り出しが違うので、箱の指定だけでは
    # 実行時の振れを足したときに収まるかどうかが分からない
    x0, y0, x1, y1 = worst_case(_bbox_of(body, "0 0 100 100", 100.0))
    over = max(-x0, x1 - LIMIT, -y0, y1 - 100.0, 0.0)
    if over > 0:
        # 枠に収まる一様縮小を、はみ出し量から求めて回転中心のまわりに掛ける
        half = max(abs(x0 - ROT_CX), abs(x1 - ROT_CX),
                   abs(y0 - ROT_CY), abs(y1 - ROT_CY))
        s = (half - over) / half
        body = (f'<g transform="translate({ROT_CX * (1 - s):.3f} '
                f'{ROT_CY * (1 - s):.3f}) scale({s:.4f})">{body}</g>')
        x0, y0, x1, y1 = worst_case(_bbox_of(body, "0 0 100 100", 100.0))
    assert x0 >= -0.6 and x1 <= LIMIT + 0.6, (role, pose, x0, x1)
    assert y0 >= -0.6 and y1 <= 100.6, (role, pose, y0, y1)
    return body


HEADER = '''"""Material Symbols(Apache License 2.0)から取り込んだ職業アイコン。

出典: https://github.com/google/material-design-icons
      symbols/web/<name>/materialsymbolsrounded/<name>_wght700fill1_48px.svg
      (Rounded / 塗りつぶし / wght700)
ライセンス: Apache License 2.0
      全文はリポジトリ直下の LICENSE-APACHE-2.0-material-symbols
改変: 実インクのbboxを測って 0..100 の座標系へ収める `transform` を外側に
      巻き、人型と小さな役割マークを組み合わせただけで、
      **パスデータそのものは1バイトも変えていない**。

役割ごとに**ポーズのプール**を持つ。同じ役割でも人ごとに違う図が出るように、
`silhouettes.py` が人物IDのハッシュからこの配列の要素を1つ選ぶ。

自作の図形で職業ごとの躍動ポーズを描く案も試したが(git履歴の
`tools/silhouettes.py`)、手描きのベジェでは関節と輪郭の造形が破綻して
「何の図かは読めるが下手」に見えた。カードは1万枚超に敷くので、造形の質は
プロの手による素材に任せ、こちらは**どのアイコンをどの職業に割り当てるか**と
**カード上での見せ方**に責任を持つ(ADR 00022)。

このファイルは tools/gen_material_icons.py で生成している。手で編集しない。
"""

# アイコンはどれもこの x を超えない。カード上で頭文字ディスクに食われて
# 形が壊れるのを防ぐための約束(tools/gen_material_icons.py 参照)
LIMIT = {limit}

# 実行時にハッシュで振れる幅。この値まではどのポーズも枠から出ないことを
# 生成時に確かめてある。`silhouettes.py` は必ずこの値を使うこと
MAX_ROT = {rot}
MAX_DY = {dy}
FLIP_AXIS = LIMIT / 2
ROT_CX, ROT_CY = LIMIT / 2, {rcy}

# 役割 -> ポーズのプール(0..100 の座標系のSVG断片)
ROLE_POSES = {{
'''


def main():
    lines = [HEADER.format(limit=LIMIT, rot=MAX_ROT, dy=MAX_DY, rcy=ROT_CY)]
    for role, cfg in ROLES.items():
        mark = cfg["mark"][0] if cfg["mark"] else "マーク無し"
        lines.append(f'    # {role}: {mark}\n    "{role}": [\n')
        for pose in cfg["poses"]:
            body = compose(role, pose)
            assert "'" not in body, (role, pose)
            lines.append(f"        # {pose}\n")
            step = 84            # 1行が長すぎるので適当な幅で畳む
            chunks = [body[i:i + step] for i in range(0, len(body), step)]
            lines.append("".join(
                f"        '{c}'{',' if last else ''}\n"
                for c, last in zip(chunks, [0] * (len(chunks) - 1) + [1])))
        lines.append("    ],\n")
    lines.append("}\n")
    OUT.write_text("".join(lines), encoding="utf-8")
    n = sum(len(c["poses"]) for c in ROLES.values())
    print(f"wrote {OUT} ({OUT.stat().st_size}B, {n} poses)")


if __name__ == "__main__":
    main()
