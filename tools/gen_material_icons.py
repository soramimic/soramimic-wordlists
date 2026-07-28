#!/usr/bin/env python3
"""Material Symbols から `tools/material_icons.py`(職業アイコン)を生成する。

減量版カード(`--style minimal`)の地紋に敷く職業アイコンの取り込み。
判断の経緯は ADR 00022。

各アイコンは `viewBox="0 -960 960 960"` で、実インクは箱いっぱいには
広がっていない(ホイッスルは横長、ヘッドセットは縦長)。**描画してアルファの
bboxを測り**、カード用の 0..100 の座標系へ収める `transform` を計算して外側に
巻く。**パスデータそのものは1バイトも変えない。**

生成物はリポジトリに入れてあるので、アイコンの割り当てを変えるとき以外は
走らせる必要はない。走らせるときだけ描画用のライブラリが要る:

  uv run --with cairosvg --with pillow python tools/gen_material_icons.py

取得元は master ブランチなので、再生成すると上流の描き直しを拾うことがある。
その場合は compare シートで6役割の見え方を確認してから差し替えること。
"""
import io
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

# **どの箱も右端を x=LIMIT までに収める。** カード上ではこの 0..100 の枠が
# `silhouettes.SIL_PLACEMENTS["water"]` で拡大されて敷かれるが、その右側には
# 頭文字ディスク(cx=160, r=48+ハローの5)が不透明で乗る。アイコンは正方形に
# 収まる完結した図なので、中央から右をディスクに食われると形が壊れて読めなく
# なる。右端を揃えてディスクの手前で止めれば、どの役割も図が丸ごと見える。
LIMIT = 88

# 役割 -> (アイコン名, 収める箱 (x, y, w, h) in 0..100, 付け足す小物)
# 小物は (アイコン名, 中心x, 中心y, 直径) で 0..100 座標に置く。
PLAN = {
    # サッカー選手: 走る人型。足元にサッカーボールを添えて競技を確定させる
    "football_player": ("directions_run", (2, 2, 84, 96),
                        [("sports_soccer", 72, 84, 28)]),
    # サッカー監督: ホイッスル。人型にすると選手と紛れるので用具で示す
    "manager": ("sports", (0, 20, 88, 60), []),
    # クラブマスコット: キャラクターの頭。人型でも用具でもない第三の形
    "mascot": ("smart_toy", (4, 6, 84, 88), []),
    # プロ野球選手: バットとボール。人型は走る図とかぶるので用具で示す
    "baseball_batter": ("sports_cricket", (0, 4, 88, 92), []),
    # YouTuber: カメラの中の人。顔を出して撮る側
    "youtuber": ("video_camera_front", (0, 14, 88, 72), []),
    # VTuber: ヘッドセット。顔を出さず声で配信する側
    "vtuber": ("headset_mic", (2, 10, 84, 80), []),
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


def ink_bbox(name: str):
    """アイコンの実インクのbboxを viewBox 座標(x, y, w, h)で返す。"""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{PROBE}" '
           f'height="{PROBE}" viewBox="0 -960 960 960">'
           f'<path d="{icon_path(name)}"/></svg>')
    buf = io.BytesIO()
    cairosvg.svg2png(bytestring=svg.encode(), write_to=buf,
                     output_width=PROBE, output_height=PROBE)
    bb = Image.open(buf).convert("RGBA").getchannel("A").getbbox()
    k = VB / PROBE
    return bb[0] * k, -960 + bb[1] * k, (bb[2] - bb[0]) * k, (bb[3] - bb[1]) * k


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


HEADER = '''"""Material Symbols(Apache License 2.0)から取り込んだ職業アイコン。

出典: https://github.com/google/material-design-icons
      symbols/web/<name>/materialsymbolsrounded/<name>_wght700fill1_48px.svg
      (Rounded / 塗りつぶし / wght700)
ライセンス: Apache License 2.0
      全文はリポジトリ直下の LICENSE-APACHE-2.0-material-symbols
改変: 実インクのbboxを測って 0..100 の座標系へ収める `transform` を外側に
      巻いただけで、**パスデータそのものは1バイトも変えていない**。

自作の図形で6職業ぶんの躍動ポーズを描く案も試したが(git履歴の
`tools/silhouettes.py`)、手描きのベジェでは関節と輪郭の造形が破綻して
「何の図かは読めるが下手」に見えた。カードは1万枚超に敷くので、造形の質は
プロの手による素材に任せ、こちらは**どのアイコンをどの職業に割り当てるか**と
**カード上での見せ方**に責任を持つ(ADR 00022)。

このファイルは tools/gen_material_icons.py で生成している。手で編集しない。
"""

# アイコンはどれもこの x を超えない。カード上で頭文字ディスクに食われて
# 形が壊れるのを防ぐための約束(tools/gen_material_icons.py 参照)
LIMIT = {limit}

# 役割 -> SVG断片(0..100 の座標系。`silhouettes.SILHOUETTES` がそのまま使う)
MATERIAL_ICONS = {{
'''


def main():
    lines = [HEADER.format(limit=LIMIT)]
    for key, (name, box, extras) in PLAN.items():
        # contain 収めなのでインクは箱の中に必ず収まる。箱の右端さえ見ればよい
        assert box[0] + box[2] <= LIMIT, (key, box)
        frag = [f'<g transform="{fit(name, box)}">'
                f'<path d="{icon_path(name)}"/></g>']
        note = name
        for ename, cx, cy, d in extras:
            assert cx + d / 2 <= LIMIT, (key, ename)
            frag.append(f'<g transform="{fit_disc(ename, cx, cy, d)}">'
                        f'<path d="{icon_path(ename)}"/></g>')
            note += f" + {ename}"
        body = "".join(frag)
        assert "'" not in body, key
        lines.append(f'    # {note}\n    "{key}": (\n')
        step = 88            # 1行が長すぎるので適当な幅で畳む
        lines.append("".join(f"        '{body[i:i + step]}'\n"
                             for i in range(0, len(body), step)))
        lines.append("    ),\n")
    lines.append("}\n")
    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size}B)")


if __name__ == "__main__":
    main()
