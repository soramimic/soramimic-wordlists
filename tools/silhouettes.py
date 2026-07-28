#!/usr/bin/env python3
"""象徴カードの減量版に敷く「職業シルエット」。

減量版カード(`--style minimal`)は名前・区分・所属の文字を描かないので、
そのままだと「サッカー選手」と「サッカー監督」と「クラブマスコット」が
配色と頭文字だけになって見分けが付かない。区分の代わりに**職業が想像できる
人型のシルエット**をカードの地紋として敷き、文字を増やさずに区別する。

図形はすべて自作である。実在のロゴ・エンブレム・マスコット・公式ピクトグラムは
参照していない(ADR 00018 / 00020 の「素材を一切借りない」方針)。特定の人物・
キャラクターを想起させる造作(顔・髪型・番号・意匠)も入れていない。

**線ではなく面で構成する。** 細い棒線で描くと図が痩せて弱く見えるので、
頭は円、胴とコートは塗りの多角形、手足は太い塗りの帯(`_chain`)で組む。
関節は帯の幅と同じ直径の円で埋めて欠けを防ぐ。全職業で頭の大きさ・帯の太さ・
角度の語彙を揃えてあり、並べたときに同じ設計の家族に見える。

座標系は各シルエットとも 0..100 の正方形で、接地はおよそ y=95。
`silhouette_svg()` がカードの座標へ平行移動+拡大する。
"""

import math

# --- 共通の寸法(全職業でこの語彙を守る) --------------------------------------

HEAD_R = 11         # 頭の半径
W_THIGH = 15        # 腿
W_SHIN = 12         # 脛
W_UPPER_ARM = 12    # 上腕
W_FOREARM = 10      # 前腕


def _num(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _pts(points) -> str:
    """点列をパスに。**巻き方向を時計回りに揃える**。

    1体ぶんのパーツを1つの `<path>` に畳むので、巻き方向が混ざると
    既定の nonzero 規則で重なった所が打ち消し合い、関節に白い穴が空く。
    """
    area = sum(x1 * y2 - x2 * y1
               for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]))
    if area < 0:                      # y下向きの画面座標では正=時計回り
        points = points[::-1]
    return "L".join(f"{_num(x)} {_num(y)}" for x, y in points)


def _disc(cx: float, cy: float, r: float) -> str:
    """パスとして書いた円(円弧2つ)。`<circle>` と違いパスにまとめられる。

    sweep=1 は画面座標で時計回り。`_pts` の向きと揃えてある。
    """
    return (f"M{_num(cx - r)} {_num(cy)}"
            f"a{_num(r)} {_num(r)} 0 1 1 {_num(r * 2)} 0"
            f"a{_num(r)} {_num(r)} 0 1 1 {_num(-r * 2)} 0Z")


def _bar(x1: float, y1: float, x2: float, y2: float,
         w1: float, w2: float) -> str:
    """2点を結ぶ太い帯(端は直角に切り落とす)。w1/w2 で先細りにできる。"""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    ux, uy = -dy / length, dx / length      # 進行方向に対する法線
    return "M" + _pts([(x1 + ux * w1 / 2, y1 + uy * w1 / 2),
                       (x2 + ux * w2 / 2, y2 + uy * w2 / 2),
                       (x2 - ux * w2 / 2, y2 - uy * w2 / 2),
                       (x1 - ux * w1 / 2, y1 - uy * w1 / 2)]) + "Z"


def _chain(points, widths) -> str:
    """折れ線に沿った帯。関節と末端は帯の幅と同じ円で埋める。

    `widths` は各区間の (始点幅, 終点幅)。
    """
    out = [_bar(*points[i], *points[i + 1], *widths[i])
           for i in range(len(points) - 1)]
    for i in range(1, len(points) - 1):     # 関節
        out.append(_disc(*points[i], max(widths[i - 1][1], widths[i][0]) / 2))
    out.append(_disc(*points[-1], widths[-1][1] / 2))   # 末端
    return "".join(out)


def _poly(points) -> str:
    """胴・コートなどの塗りの面。"""
    return "M" + _pts(points) + "Z"


def _arc_band(cx: float, cy: float, r_out: float, r_in: float,
              a0: float, a1: float) -> str:
    """円環の一部(ヘッドセットのバンドなど)。角度は度、y下向き、a0→a1は時計回り。

    頭と同じ色で塗るので、頭の円から離した円環にしないと溶けて大きな髪の塊に
    見えてしまう。`r_in` を頭の半径より大きく取ること。
    """
    def pt(r, a):
        t = math.radians(a)
        return cx + r * math.cos(t), cy + r * math.sin(t)

    large = 1 if abs(a1 - a0) > 180 else 0
    ox0, oy0 = pt(r_out, a0)
    ox1, oy1 = pt(r_out, a1)
    ix1, iy1 = pt(r_in, a1)
    ix0, iy0 = pt(r_in, a0)
    return (f"M{_num(ox0)} {_num(oy0)}"
            f"A{_num(r_out)} {_num(r_out)} 0 {large} 1 {_num(ox1)} {_num(oy1)}"
            f"L{_num(ix1)} {_num(iy1)}"
            f"A{_num(r_in)} {_num(r_in)} 0 {large} 0 {_num(ix0)} {_num(iy0)}Z")


def _fig(*parts: str) -> dict:
    """パス片をまとめて1体のシルエットにする(1つの `<path>` に畳む)。"""
    return {"fill": f'<path d="{"".join(parts)}"/>'}


# --- 造形 --------------------------------------------------------------------
#
# 体軸を傾け、手足を大きな対角線に振る。図の対角線がカードの対角線と重なって
# 動きが出る。関節を45度の倍数へ揃えた端正な案も試したが(compare/styles.png)、
# 直立して静止した図になり、カードの地紋としては弱かったので採らなかった。

SILHOUETTES = {
    # サッカー選手: 蹴り脚を右上へ大きく振り上げ、軸足を左下へ流す
    "football_player": _fig(
        _disc(30, 17, HEAD_R),
        _poly([(21, 30), (45, 26), (54, 54), (36, 58)]),           # 傾いた胴
        _chain([(41, 57), (33, 76), (25, 94)],                     # 軸足
               [(W_THIGH, W_SHIN), (W_SHIN, W_SHIN - 2)]),
        _chain([(50, 53), (74, 45), (93, 25)],                     # 蹴り脚
               [(W_THIGH, W_SHIN), (W_SHIN, W_SHIN - 2)]),
        _chain([(24, 33), (8, 47)], [(W_UPPER_ARM, W_FOREARM)]),
        _chain([(43, 29), (58, 9)], [(W_UPPER_ARM, W_FOREARM)]),
    ),
    # サッカー監督: 踏み出した歩幅と、翻ったコートの裾
    "manager": _fig(
        _disc(35, 15, HEAD_R),
        _poly([(21, 28), (51, 25), (68, 64), (12, 72)]),           # 翻るコート
        _chain([(49, 32), (77, 23)], [(W_UPPER_ARM, W_FOREARM)]),
        _chain([(24, 33), (18, 52)], [(W_UPPER_ARM, W_FOREARM)]),
        _chain([(34, 66), (28, 94)], [(W_SHIN, W_SHIN - 2)]),
        _chain([(50, 62), (62, 90)], [(W_SHIN, W_SHIN - 2)]),
    ),
    # クラブマスコット: 跳ねて両手を上げた姿勢
    "mascot": _fig(
        _disc(42, 32, 24),
        _disc(22, 11, 10), _disc(62, 11, 10),
        _poly([(29, 52), (57, 52), (61, 78), (25, 78)]),
        _chain([(30, 57), (10, 39)], [(W_UPPER_ARM, W_UPPER_ARM)]),
        _chain([(56, 57), (78, 37)], [(W_UPPER_ARM, W_UPPER_ARM)]),
        _chain([(33, 76), (23, 95)], [(W_SHIN, W_SHIN)]),
        _chain([(53, 76), (66, 93)], [(W_SHIN, W_SHIN)]),
    ),
    # プロ野球選手: 脚を大きく開いて構え、バットを左上へ引き上げた打席の姿勢。
    # 帽子のつばで「打者」と読ませる
    "baseball_batter": _fig(
        _disc(36, 18, HEAD_R),
        _poly([(45, 14), (59, 16), (59, 22), (45, 23)]),           # 帽子のつば
        _poly([(26, 31), (50, 28), (56, 55), (34, 58)]),           # ひねった胴
        _chain([(38, 57), (26, 76), (18, 94)],                     # 後ろ脚
               [(W_THIGH, W_SHIN), (W_SHIN, W_SHIN - 2)]),
        _chain([(50, 55), (66, 74), (77, 92)],                     # 前脚
               [(W_THIGH, W_SHIN), (W_SHIN, W_SHIN - 2)]),
        _chain([(32, 33), (20, 28)], [(W_UPPER_ARM, W_FOREARM)]),  # 腕
        _bar(21, 29, 3, 8, 7, 12),                                 # バット
    ),
    # YouTuber: カメラを高く掲げて自分を撮る、踏み出した姿勢
    "youtuber": _fig(
        _disc(32, 21, HEAD_R),
        _poly([(23, 33), (46, 30), (52, 57), (32, 60)]),
        _chain([(44, 34), (58, 23), (67, 15)],                     # 掲げる腕
               [(W_UPPER_ARM, W_FOREARM), (W_FOREARM, W_FOREARM)]),
        _chain([(26, 35), (12, 49)], [(W_UPPER_ARM, W_FOREARM)]),
        _poly([(63, 3), (86, 3), (86, 25), (63, 25)]),             # カメラ
        _poly([(56, 9), (63, 9), (63, 19), (56, 19)]),             # レンズ
        _chain([(36, 59), (30, 77), (24, 94)],
               [(W_THIGH, W_SHIN), (W_SHIN, W_SHIN - 2)]),
        _chain([(48, 57), (53, 76), (59, 93)],
               [(W_THIGH, W_SHIN), (W_SHIN, W_SHIN - 2)]),
    ),
    # VTuber: ヘッドセットを着けて身振りしながら配信している姿勢。
    # 腕は**耳当てより下**でしか振れない。上げるとヘッドセットと繋がって
    # 頭の周りが1つの塊になり、何の形か読めなくなる。動きは脚の踏み出しと
    # 胴の傾きで出す。ブームマイクも同じ理由で入れていない(この寸法だと
    # 耳当ての隣の小さな瘤にしかならず、輪郭を濁すだけだった)
    "vtuber": _fig(
        _disc(34, 24, 10),
        _arc_band(34, 24, 20, 15.5, 170, 370),                     # ヘッドバンド
        _chain([(16, 27), (16, 36)], [(13, 13)]),                  # 耳当て
        _chain([(52, 27), (52, 36)], [(13, 13)]),
        _poly([(25, 39), (47, 36), (53, 63), (32, 66)]),
        _chain([(28, 44), (14, 57), (8, 71)],                      # 身振りする腕
               [(W_UPPER_ARM, W_FOREARM), (W_FOREARM, W_FOREARM)]),
        _chain([(46, 43), (62, 50), (74, 46)],
               [(W_UPPER_ARM, W_FOREARM), (W_FOREARM, W_FOREARM)]),
        _chain([(36, 65), (29, 81), (23, 95)],
               [(W_THIGH, W_SHIN), (W_SHIN, W_SHIN - 2)]),
        _chain([(48, 63), (54, 80), (61, 94)],
               [(W_THIGH, W_SHIN), (W_SHIN, W_SHIN - 2)]),
    ),
}



# カードのどこにどれだけの大きさで敷くか。`split` はカードの帯と下地を
# またぐ配置で、帯の側と下地の側を別の色・別の濃さで描き分ける必要がある
# (1色で通すと、帯で読める色が下地では消える)
SIL_PLACEMENTS = {
    # 帯の中で最大化。帯の高さいっぱいまで使う
    "band": {"box": (4, 1, 112), "opacity": 0.26, "split": False},
    # カード全面のウォーターマーク(既定)。カード高さの9割を使い、左端で
    # 切れる構図にして、頭文字ディスクと重なる部分を減らす
    "water": {"box": (-12, 10, 180), "opacity": 0.22, "split": True,
              "lower_opacity": 0.30},
    # 右側に大きく置いて右端と下端で切る
    "edge": {"box": (150, 16, 196), "opacity": 0.22, "split": True,
             "lower_opacity": 0.30},
}


def silhouette_card_svg(key: str, top_color: str, bottom_color: str,
                        split_y: float, w: float, h: float,
                        placement: str = "water", uid: str = "") -> str:
    """カード1枚ぶんのシルエット。カードの外へはみ出す分は切り落とす。

    切り抜きには `clipPath` ではなく**入れ子の `<svg>`**(ビューポートが
    そのまま切り抜きになる)を使う。定義を1つも増やさずに済むので、1万枚超を
    抱えるこのリポジトリではバイト数が効く。

    `split` の配置では帯(`split_y` より上)と下地を別々の入れ子svgで描く。
    同じ形のまま色と濃さだけが境目で変わるので、1体のシルエットが帯を
    またいでいるように見える。

    下地側は**主色(チームカラー/イメージカラー)を薄く敷く**のが良い。
    暗いインクで敷くとカードの色味から浮いた灰色の染みに見えてしまい、
    主色なら帯と同じ色の家族として馴染む。

    帯側と下地側で同じ形を2度描くことになるので、形は `<defs>` に1つだけ
    置いて `<use>` で使い回す。色は `<use>` 側に書けば継承される。
    パスを2度書くと1枚あたり400〜700バイト増え、1万枚超では数MB効いてくる。
    `uid` は同じページに複数のカードを並べたときにidが衝突しないための接尾辞。
    """
    p = SIL_PLACEMENTS[placement]
    x, y, size = p["box"]
    if not p["split"]:
        return (f'<svg width="{w:g}" height="{split_y:g}">'
                f'{silhouette_svg(key, top_color, x, y, size, p["opacity"])}'
                f"</svg>")
    s = SILHOUETTES.get(key)
    if not s:
        return ""
    k = size / 100
    sid = f"s{uid}"

    def inst(color: str, oy: float, op: float) -> str:
        # 透明度は `<use>` ではなく**外側の `<g>`** に書く。cairosvg は
        # `<use>` の opacity を無視してベタ塗りで描いてしまう
        # (soramimic-video はこのSVGを cairosvg でPNG化するので致命的)
        return (f'<g opacity="{op:g}"><use href="#{sid}" '
                f'transform="translate({x:g} {oy:g}) scale({k:g})" '
                f'fill="{color}"/></g>')

    return (f'<defs><g id="{sid}">{s["fill"]}</g></defs>'
            f'<svg width="{w:g}" height="{split_y:g}">'
            f'{inst(top_color, y, p["opacity"])}</svg>'
            f'<svg y="{split_y:g}" width="{w:g}" height="{h - split_y:g}">'
            f'{inst(bottom_color, y - split_y, p["lower_opacity"])}</svg>')


def silhouette_svg(key: str, color: str, x: float, y: float, size: float,
                   opacity: float = 0.26) -> str:
    """シルエット1体ぶんのSVG断片。未知のキーなら空文字。

    透明度は**グループにまとめて**掛ける。パーツごとに掛けると重なった所だけ
    濃くなって継ぎ目が出るため。
    """
    s = SILHOUETTES.get(key)
    if not s:
        return ""
    k = size / 100
    return (f'<g transform="translate({x:g} {y:g}) scale({k:g})" '
            f'fill="{color}" opacity="{opacity:g}">{s["fill"]}</g>')
