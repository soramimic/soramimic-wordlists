#!/usr/bin/env python3
"""Material Symbols から `tools/material_icons.py`(職業アイコン)を生成する。

象徴カード・選手カードの地紋に敷く職業アイコンの取り込み。
判断の経緯は ADR 00024。

**構成**: 人が就く役割は「人型のポーズ + 小さな役割マーク」で描く。
人型が職業を人として示し、マークが職業を確定させる。マスコットだけは
人ではないのでキャラクターの図そのものを使う。

**バリエーション**: 同じ役割でも1枚ごとに見た目が変わるよう、役割ごとに
ポーズのプール(6〜8種)と、役割マークを置く**スロット**(3か所)を持つ。
どの組み合わせを使うかは `silhouettes.py` が**人物IDのハッシュから決定的に**
選ぶ(乱数ではない。乱数だと再生成のたびに1万3千枚すべてが差分になる)。
左右反転・微小な回転・上下オフセット・±10%の拡縮も同じハッシュから決まる。

人型とマークは**別々の断片として書き出し、実行時に連結する**。ポーズ x
スロットぶんの合成図を全部並べると生成ファイルが数百KBに膨らむのに対し、
実行時の振れ(反転・回転・拡縮・上下)はどれも組全体に掛かる相似変換なので、
**人型とマークの相対位置は実行時に変わらない**。つまり枠への収まりも重なりも
生成時に1度確かめれば足りる。

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
from PIL import Image, ImageChops, ImageFilter

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
# この幅で振っても枠から出ないことを、組み合わせごとに生成時へ焼き込む
# 縮小率(`ROLE_COMBOS` の第3要素)で保証する。
MAX_ROT = 5.0        # 回転(度)
MAX_DY = 3.0         # 上下オフセット
MAX_SCALE = 0.10     # 拡縮(±10%)
FLIP_AXIS = LIMIT / 2                # 左右反転の軸
ROT_CX, ROT_CY = LIMIT / 2, 50.0     # 回転・拡縮の中心

# 人型とマークの重なりの許容量。**触れるのは良いが、食い込むのは不可**。
# 地紋は単色を薄く敷くだけなので、輪郭が重なった部分は溶けて1つの塊になる。
# 腕を伸ばしたポーズがマークに接して「持っている」ように見えるのは狙いどおり
# なので(ADR 00024)、接触ぶんの数ピクセルだけ見逃す
OVERLAP_TOL = 0.004   # マークの面積に対する比

# 役割ごとの構成。
#   poses      : ポーズのプール(この中からIDのハッシュで1つ選ぶ)
#   figure_box : 人型を収める箱 (x, y, w, h) in 0..100
#   mark       : 小さな役割マークのアイコン名。None なら無し
#   slots      : マークを置く位置のプール (中心x, 中心y, 直径)。
#                左右のバリエーションは左右反転で自然に出るので、
#                **スロットは高さで振る**(上=手元/頭上、下=足元)
#
# ポーズは**小道具の付いていない全身の人型**から選ぶ。`hiking`(杖)や
# `follow_the_signs`(標識)のように元から物を持っている図は、役割マークと
# 情報がぶつかるので使わない。`downhill_skiing` / `surfing` /
# `roller_skating` のように用具が競技を語ってしまう図も、サッカー選手の
# カードに敷くとその競技を誤解させるので使わない。`person` 系の胸像や
# `man` / `woman` のようなトイレ標識型も、全身のポーズと並べると別の家族に
# 見えるうえ、後者は性別を決め打ちしてしまうので使わない。
ROLES = {
    # サッカー選手: 走る・蹴るなどの躍動。ボールは足元・中段・頭の高さ
    "football_player": {
        "poses": ["directions_run", "sprint", "sports_martial_arts",
                  "sports_gymnastics", "sports_kabaddi", "directions_walk",
                  "accessibility_new"],
        "figure_box": (0, 4, 66, 88),
        "mark": "sports_soccer",
        "slots": [(74, 84, 26), (76, 50, 24), (74, 15, 26)],
    },
    # サッカー監督: 指示を出す立ち姿。躍動する選手とは体の使い方で分ける。
    # ホイッスルは手元・腰元・足元
    "manager": {
        "poses": ["emoji_people", "accessibility_new", "accessibility",
                  "directions_walk", "hail", "self_improvement"],
        "figure_box": (0, 6, 66, 86),
        "mark": "sports",
        "slots": [(74, 19, 28), (76, 52, 24), (74, 84, 24)],
    },
    # クラブマスコット: 人ではないのでキャラクターの図そのもの。マークは不要。
    # ロボットだけだと同じ顔が並ぶので、実在のクラブマスコットに多い動物や
    # 抽象キャラクターの図も混ぜる(Google製品のマスコットである `android` /
    # `flutter_dash` は、他社の商標を敷くことになるので使わない)
    "mascot": {
        "poses": ["smart_toy", "robot", "robot_2", "pets", "cruelty_free",
                  "raven", "pest_control_rodent", "heart_smile",
                  "sound_detection_dog_barking", "sentiment_very_satisfied"],
        "figure_box": (4, 6, 80, 86),
        "mark": None,
        "slots": [],
    },
    # プロ野球選手: 走塁・構えの立ち姿。バットは手元・腰元・足元
    "baseball_batter": {
        "poses": ["directions_run", "sprint", "accessibility_new",
                  "accessibility", "directions_walk", "sports_gymnastics",
                  "sports_handball"],
        "figure_box": (0, 6, 66, 86),
        "mark": "sports_cricket",
        "slots": [(74, 19, 28), (76, 52, 24), (74, 84, 24)],
    },
    # YouTuber: 挨拶・立ち姿。ビデオカメラは手元・腰元・足元
    "youtuber": {
        "poses": ["emoji_people", "accessibility_new", "accessibility",
                  "directions_walk", "hail", "self_improvement"],
        "figure_box": (0, 6, 66, 86),
        "mark": "videocam",
        "slots": [(74, 19, 28), (76, 52, 24), (74, 84, 24)],
    },
    # VTuber: 座って配信する図も混ぜる。ヘッドセットは手元・腰元・足元
    "vtuber": {
        "poses": ["self_improvement", "emoji_people", "accessibility_new",
                  "accessibility", "directions_walk", "hail"],
        "figure_box": (0, 6, 66, 86),
        "mark": "headset_mic",
        "slots": [(74, 19, 28), (76, 52, 24), (74, 84, 24)],
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


def _alpha(svg_body: str, viewbox: str) -> Image.Image:
    """SVG断片を PROBE x PROBE で描いて、アルファチャンネルを返す。"""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{PROBE}" '
           f'height="{PROBE}" viewBox="{viewbox}">{svg_body}</svg>')
    buf = io.BytesIO()
    cairosvg.svg2png(bytestring=svg.encode(), write_to=buf,
                     output_width=PROBE, output_height=PROBE)
    return Image.open(buf).convert("RGBA").getchannel("A")


def _bbox_of(svg_body: str, viewbox: str, span: float):
    """SVG断片を描いて、実インクのbboxを viewBox 座標(x, y, w, h)で返す。"""
    bb = _alpha(svg_body, viewbox).getbbox()
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


def figure_svg(role: str, pose: str) -> str:
    """人型1ポーズぶんの断片(縮小は掛けない)。"""
    return (f'<g transform="{fit(pose, ROLES[role]["figure_box"])}">'
            f'<path d="{icon_path(pose)}"/></g>')


def mark_svg(role: str, slot) -> str:
    """役割マーク1スロットぶんの断片(縮小は掛けない)。"""
    return (f'<g transform="{fit_disc(ROLES[role]["mark"], *slot)}">'
            f'<path d="{icon_path(ROLES[role]["mark"])}"/></g>')


def fit_scale(bb) -> float:
    """実行時の振れを全部かけても枠に収まる、最大の縮小率を返す。

    実行時 `silhouettes.variant()` は組全体に
    「左右反転 → (ROT_CX, ROT_CY) を中心とした拡縮 → 同じ中心の回転 →
    上下移動」を掛ける。反転・拡縮・回転はどれも中心のまわりの相似変換なので、
    bboxの角が中心からどれだけ離れるかだけを見れば済む。上下移動だけは
    拡縮の外側に掛かるので、そのぶん枠を狭めて考える。

    返すのは**生成時に焼き込む縮小率**で、実行時の ±MAX_SCALE はこれに
    掛かる。1.0 を超えては返さない(`figure_box` より大きくはしない)。
    """
    x, y, w, h = bb
    corners = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
    # 左右反転も候補に入れる(軸 FLIP_AXIS のまわり)
    corners += [(2 * FLIP_AXIS - cx, cy) for cx, cy in corners]
    lim = 1.0
    # 回転の範囲は狭いが、角の最遠点が範囲の内側に来ることもあるので刻んで見る
    for i in range(21):
        t = math.radians(-MAX_ROT + 2 * MAX_ROT * i / 20)
        for cx, cy in corners:
            dx, dy = cx - ROT_CX, cy - ROT_CY
            u = dx * math.cos(t) - dy * math.sin(t)
            v = dx * math.sin(t) + dy * math.cos(t)
            if u < 0:
                lim = min(lim, ROT_CX / -u)
            elif u > 0:
                lim = min(lim, (LIMIT - ROT_CX) / u)
            if v < 0:
                lim = min(lim, (ROT_CY - MAX_DY) / -v)
            elif v > 0:
                lim = min(lim, (100.0 - ROT_CY - MAX_DY) / v)
    return min(1.0, lim / (1.0 + MAX_SCALE))


def runtime_svg(body: str, k: float, flip: int, rot: float, dy: float) -> str:
    """`silhouettes.variant()` と同じ変換を掛けた断片(検証用)。"""
    t = []
    if dy:
        t.append(f"translate(0 {dy:g})")
    if rot:
        t.append(f"rotate({rot:g} {ROT_CX:g} {ROT_CY:g})")
    if k != 1.0:
        t.append(f"translate({ROT_CX * (1 - k):.4f} {ROT_CY * (1 - k):.4f}) "
                 f"scale({k:.6f})")
    if flip:
        t.append(f"translate({2 * FLIP_AXIS:g} 0) scale(-1 1)")
    return f'<g transform="{" ".join(t)}">{body}</g>' if t else body


def verify_frame(body: str, k: float, where) -> None:
    """振れの端をすべて実際に描いて、枠(0..LIMIT, 0..100)を出ないか見る。"""
    for flip in (0, 1):
        for rot in (-MAX_ROT, MAX_ROT):
            for dy in (-MAX_DY, MAX_DY):
                s = k * (1 + MAX_SCALE)
                x, y, w, h = _bbox_of(
                    runtime_svg(body, s, flip, rot, dy), "0 0 100 100", 100.0)
                assert x >= -0.6 and x + w <= LIMIT + 0.6, (where, x, x + w)
                assert y >= -0.6 and y + h <= 100.6, (where, y, y + h)


def overlap_ratio(fig: str, mark: str) -> float:
    """人型とマークが食い込んでいる面積の、マーク面積に対する比。

    輪郭が触れるだけなら数ピクセルしか出ない。滲みを拾わないよう、
    アルファを二値化してから重ねる。
    """
    a = _alpha(fig, "0 0 100 100").point(lambda v: 255 if v > 128 else 0)
    b = _alpha(mark, "0 0 100 100").point(lambda v: 255 if v > 128 else 0)
    # 反転で近づく向きの差は出ないが、回転で1度ぶんは寄るので細らせずに見る
    inter = ImageChops.multiply(a, b)
    n = sum(inter.point(lambda v: 1 if v else 0).getdata())
    area = sum(b.point(lambda v: 1 if v else 0).getdata())
    return n / area if area else 0.0


def gap(fig: str, mark: str) -> float:
    """人型とマークの隙間(0..100 の座標系)。触れていれば 0。"""
    b = _alpha(mark, "0 0 100 100").point(lambda v: 255 if v > 128 else 0)
    a = _alpha(fig, "0 0 100 100").point(lambda v: 255 if v > 128 else 0)
    for r in range(0, 13):
        grown = b if r == 0 else b.filter(ImageFilter.MaxFilter(2 * r + 1))
        if ImageChops.multiply(a, grown).getbbox():
            return r * 100.0 / PROBE
    return 13 * 100.0 / PROBE


HEADER = '''"""Material Symbols(Apache License 2.0)から取り込んだ職業アイコン。

出典: https://github.com/google/material-design-icons
      symbols/web/<name>/materialsymbolsrounded/<name>_wght700fill1_48px.svg
      (Rounded / 塗りつぶし / wght700)
ライセンス: Apache License 2.0
      全文はリポジトリ直下の LICENSE-APACHE-2.0-material-symbols
改変: 実インクのbboxを測って 0..100 の座標系へ収める `transform` を外側に
      巻き、人型と小さな役割マークを組み合わせただけで、
      **パスデータそのものは1バイトも変えていない**。

役割ごとに**ポーズのプール**と**役割マークを置くスロット**を持つ。同じ役割
でも人ごとに違う図が出るように、`silhouettes.py` が人物IDのハッシュから
`ROLE_COMBOS` の組を1つ選び、人型とマークを連結する。

自作の図形で職業ごとの躍動ポーズを描く案も試したが(git履歴の
`tools/silhouettes.py`)、手描きのベジェでは関節と輪郭の造形が破綻して
「何の図かは読めるが下手」に見えた。カードは1万枚超に敷くので、造形の質は
プロの手による素材に任せ、こちらは**どのアイコンをどの職業に割り当てるか**と
**カード上での見せ方**に責任を持つ(ADR 00024)。

このファイルは tools/gen_material_icons.py で生成している。手で編集しない。
"""

# アイコンはどれもこの x を超えない。カード上で頭文字ディスクに食われて
# 形が壊れるのを防ぐための約束(tools/gen_material_icons.py 参照)
LIMIT = {limit}

# 実行時にハッシュで振れる幅。`silhouettes.py` は必ずこの値を使うこと
MAX_ROT = {rot}
MAX_DY = {dy}
MAX_SCALE = {sc}
FLIP_AXIS = LIMIT / 2
ROT_CX, ROT_CY = LIMIT / 2, {rcy}

'''


def emit(name: str, frag: str, indent: str = "        ") -> list:
    """長い断片を適当な幅で畳んで、Pythonの文字列リテラルとして書き出す。"""
    assert "'" not in frag
    step = 84
    chunks = [frag[i:i + step] for i in range(0, len(frag), step)]
    return [f"{indent}# {name}\n"] + [
        f"{indent}'{c}'{',' if last else ''}\n"
        for c, last in zip(chunks, [0] * (len(chunks) - 1) + [1])]


def main():
    figures, marks, combos = {}, {}, {}
    report = []
    for role, cfg in ROLES.items():
        figs = [figure_svg(role, p) for p in cfg["poses"]]
        mks = [mark_svg(role, s) for s in cfg["slots"]]
        figures[role], marks[role] = figs, mks
        rows, dropped = [], []
        for i, fig in enumerate(figs):
            if not mks:
                k = fit_scale(_bbox_of(fig, "0 0 100 100", 100.0))
                verify_frame(fig, k, (role, cfg["poses"][i]))
                rows.append([(-1, k)])
                continue
            ok = []
            for j, mk in enumerate(mks):
                over = overlap_ratio(fig, mk)
                if over > OVERLAP_TOL:
                    dropped.append((cfg["poses"][i], j, over))
                    continue
                body = fig + mk
                k = fit_scale(_bbox_of(body, "0 0 100 100", 100.0))
                verify_frame(body, k, (role, cfg["poses"][i], j))
                ok.append((j, k))
            # 全スロットが落ちたポーズは置き場所が無いので、設定の側を直す
            assert ok, (role, cfg["poses"][i])
            rows.append(ok)
        combos[role] = rows
        n = sum(len(r) for r in rows)
        report.append((role, len(figs), len(mks), n, [len(r) for r in rows],
                       dropped, min(k for r in rows for _, k in r)))

    lines = [HEADER.format(limit=LIMIT, rot=MAX_ROT, dy=MAX_DY,
                           sc=MAX_SCALE, rcy=ROT_CY)]
    lines.append("# 役割 -> 人型ポーズのプール(0..100 の座標系のSVG断片)\n"
                 "ROLE_FIGURES = {\n")
    for role, cfg in ROLES.items():
        lines.append(f'    "{role}": [\n')
        for pose, frag in zip(cfg["poses"], figures[role]):
            lines += emit(pose, frag)
        lines.append("    ],\n")
    lines.append("}\n\n")

    lines.append("# 役割 -> 役割マークを置くスロット(同じ図を高さ違いで)\n"
                 "ROLE_MARKS = {\n")
    for role, cfg in ROLES.items():
        lines.append(f'    "{role}": [\n')
        for slot, frag in zip(cfg["slots"], marks[role]):
            lines += emit(f'{cfg["mark"]} {slot}', frag)
        lines.append("    ],\n")
    lines.append("}\n\n")

    lines.append(
        "# 役割 -> 人型ごとに使える (マークの番号, 焼き込む縮小率) の一覧。\n"
        "# ハッシュは**まず人型を選び、次にその人型で使えるスロットを選ぶ**。\n"
        "# 平らな1本の配列にすると、スロットが3つ残ったポーズが2つ残った\n"
        "# ポーズの1.5倍出てしまう。マークが無い役割は番号 -1。\n"
        "# 食い込む組み合わせは生成時に落としてあるので、ここに残っている組は\n"
        "# **枠に収まり、かつ人型とマークが重ならない**ことが確かめてある\n"
        "ROLE_COMBOS = {\n")
    for role, cfg in ROLES.items():
        lines.append(f'    "{role}": [\n')
        for pose, row in zip(cfg["poses"], combos[role]):
            body = ", ".join(f"({j}, {k:.4f})" for j, k in row)
            lines.append(f"        [{body}],  # {pose}\n")
        lines.append("    ],\n")
    lines.append("}\n")
    OUT.write_text("".join(lines), encoding="utf-8")

    print(f"wrote {OUT} ({OUT.stat().st_size}B)")
    for role, nf, nm, nc, per_pose, dropped, kmin in report:
        print(f"  {role:16s} poses={nf} slots={nm} combos={nc} "
              f"(x反転2 = 知覚{nc * 2}通り) minfit={kmin:.3f} "
              f"ポーズ別スロット数={per_pose}")
        for pose, j, over in dropped:
            print(f"      drop {pose} x slot{j}: 食い込み {over:.1%}")


if __name__ == "__main__":
    main()
