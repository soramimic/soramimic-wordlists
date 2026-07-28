#!/usr/bin/env python3
"""象徴カードの減量版に敷く「職業アイコン」。

減量版カード(`--style minimal`)は名前・区分・所属の文字を描かないので、
そのままだと「サッカー選手」と「サッカー監督」と「クラブマスコット」が
配色と頭文字だけになって見分けが付かない。区分の文字の代わりに**職業が
想像できるアイコン**をカードの地紋(ウォーターマーク)として敷き、文字を
増やさずに区別する。

図形は **Material Symbols(Google, Apache License 2.0)** をそのまま使う。
`tools/material_icons.py` を参照。以前は同じ用途の人型を自作していたが、
手描きのベジェでは関節と輪郭の造形が破綻して「何の図かは読めるが下手」に
見えたので、造形はプロの素材に任せることにした(ADR 00022)。
実在のロゴ・エンブレム・マスコット・公式競技ピクトグラムは参照していない。
特定の人物・キャラクターを想起させる造作も入れていない。

**同じ役割でも1枚ごとに図を変える。** 同じ区分の人が何十人も並ぶので、
全員が寸分違わぬ同じ絵だと「同じ画像を使い回した」ように見える。役割ごとに
ポーズのプール(6〜8種)と役割マークのスロット(3か所)を持ち、その組を
1つ選んだうえで左右反転・微小な回転・上下オフセット・±10%の拡縮を掛ける。

選択は**人物IDのハッシュから決定的に**行う(`variant()`)。乱数にすると
再生成のたびに1万3千枚すべてが差分になり、レビューできなくなる。同じ人は
何度生成しても必ず同じ図になる。

座標系は各アイコンとも 0..100 の正方形で、`silhouette_svg()` /
`silhouette_card_svg()` がカードの座標へ平行移動+拡大する。
"""

import hashlib

from material_icons import (FLIP_AXIS, MAX_DY, MAX_ROT, MAX_SCALE,
                            ROLE_COMBOS, ROLE_FIGURES, ROLE_MARKS,
                            ROT_CX, ROT_CY)

# 役割 -> 人型ごとの (マークの番号, 焼き込む縮小率) の一覧
SILHOUETTES = ROLE_COMBOS

# 回転・上下オフセット・拡縮の刻み。奇数にして 0(無変化)を必ず含める
ROT_STEPS = 5
DY_STEPS = 5
SCALE_STEPS = 5

# Apache License 2.0 の帰属。カードSVGの `<desc>` に1行入れる。
# 生成カードは raw URL で1枚ずつ直リンクされる使われ方をするので、
# リポジトリのLICENSE/READMEだけでなく**ファイル単体でも出所が辿れる**
# ようにしておく(1枚あたり約80バイト)
ATTRIBUTION = ("図形はMaterial Symbols (Google, Apache License 2.0) を"
               "使用しています。")


# カードのどこにどれだけの大きさで敷くか。`split` はカードの帯と下地を
# またぐ配置で、帯の側と下地の側を別の色・別の濃さで描き分ける必要がある
# (1色で通すと、帯で読める色が下地では消える)
SIL_PLACEMENTS = {
    # 帯の中で最大化。帯の高さいっぱいまで使う
    "band": {"box": (4, 1, 112), "opacity": 0.26, "split": False},
    # カードの左半分のウォーターマーク(既定)。
    # 自作の人型は縦長で、カード全面に敷いて頭文字ディスク(cx=160, r=48)と
    # 重なっても手足が周りに出るぶん形が読めた。Material のアイコンは
    # **正方形に収まる完結した図**なので、中央から右を不透明なディスクに
    # 食われると輪郭が壊れて何の図か読めなくなる(compare/placements.png)。
    # そこで左に寄せ、`material_icons.LIMIT` で右端を揃えたアイコンが
    # ディスクの左端(x=112)でほぼ止まる大きさにする。
    # 上下は 46..174 で、帯の境目(y=112)を図のほぼ中央でまたぐ
    # (compare/size_check.png。これ以上大きくするとホイッスルやカメラの
    #  マークがディスクに掛かって読めなくなる)。
    # 左端は 0 に合わせる。以前は -3 で、**左右反転で左に来た役割マークが
    # カードの左辺で削れていた**(compare/variation.html の3枚目)
    "water": {"box": (0, 46, 128), "opacity": 0.22, "split": True,
              "lower_opacity": 0.30},
    # 右側に大きく置いて右端と下端で切る
    "edge": {"box": (150, 16, 196), "opacity": 0.22, "split": True,
             "lower_opacity": 0.30},
}


def variant(key: str, uid: str = "") -> str:
    """役割と人物IDから、敷く図形を**決定的に**1つ選んで返す。

    `uid` は呼び出し側の `asset_key()`(名前のsha1の先頭10桁)を想定するが、
    どんな文字列でも受けられるようここで改めてハッシュを取る。同じ `uid` なら
    何度呼んでも同じ図が返る。これが崩れると、再生成のたびに1万3千枚すべてが
    差分になってレビューできなくなる。

    ハッシュの整数から、下の桁から順に
    「人型 → マークのスロット → 左右反転 → 回転 → 上下オフセット → 拡縮」を
    取り出す。振れ幅は `material_icons` 側の定数で、**その幅なら枠から
    出ないこと**と**人型とマークが食い込まないこと**が生成時に確かめてある
    (`gen_material_icons.fit_scale` / `overlap_ratio`)。組ごとの縮小率は
    その検証の結果で、実行時の拡縮はこれに掛かる。

    人型を先に選ぶのは分布のため。ポーズによって使えるスロットの数が違う
    ので、平らな組の配列から1つ選ぶとスロットが多いポーズばかり出る。

    反転・回転・拡縮はどれも組全体に掛かる相似変換なので、**人型とマークの
    相対位置は実行時に変わらない**。だから重なりの検証は生成時の1度で足りる。
    """
    per_pose = SILHOUETTES.get(key)
    if not per_pose:
        return ""
    h = int(hashlib.sha1(uid.encode("utf-8")).hexdigest(), 16)
    pi, h = h % len(per_pose), h // len(per_pose)
    slots = per_pose[pi]
    mi, fit = slots[h % len(slots)]
    h //= len(slots)
    flip, h = h & 1, h >> 1
    rot = (h % ROT_STEPS - ROT_STEPS // 2) * (MAX_ROT / (ROT_STEPS // 2))
    h //= ROT_STEPS
    dy = (h % DY_STEPS - DY_STEPS // 2) * (MAX_DY / (DY_STEPS // 2))
    h //= DY_STEPS
    k = fit * (1 + (h % SCALE_STEPS - SCALE_STEPS // 2)
               * (MAX_SCALE / (SCALE_STEPS // 2)))

    body = ROLE_FIGURES[key][pi] + (ROLE_MARKS[key][mi] if mi >= 0 else "")

    # 外側から順に:上下移動 → 回転 → 拡縮 → 左右反転
    t = []
    if dy:
        t.append(f"translate(0 {dy:g})")
    if rot:
        t.append(f"rotate({rot:g} {ROT_CX:g} {ROT_CY:g})")
    if abs(k - 1) > 1e-9:
        t.append(f"translate({ROT_CX * (1 - k):.4f} {ROT_CY * (1 - k):.4f}) "
                 f"scale({k:.6f})")
    if flip:
        t.append(f"translate({2 * FLIP_AXIS:g} 0) scale(-1 1)")
    return f'<g transform="{" ".join(t)}">{body}</g>' if t else body


def silhouette_card_svg(key: str, top_color: str, bottom_color: str,
                        split_y: float, w: float, h: float,
                        placement: str = "water", uid: str = "") -> str:
    """カード1枚ぶんのアイコン。カードの外へはみ出す分は切り落とす。

    切り抜きには `clipPath` ではなく**入れ子の `<svg>`**(ビューポートが
    そのまま切り抜きになる)を使う。定義を1つも増やさずに済むので、1万枚超を
    抱えるこのリポジトリではバイト数が効く。

    `split` の配置では帯(`split_y` より上)と下地を別々の入れ子svgで描く。
    同じ形のまま色と濃さだけが境目で変わるので、1つの図が帯を
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
        inner = silhouette_svg(key, top_color, x, y, size,
                               p["opacity"], uid)
        return f'<svg width="{w:g}" height="{split_y:g}">{inner}</svg>'
    s = variant(key, uid)
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

    return (f'<defs><g id="{sid}">{s}</g></defs>'
            f'<svg width="{w:g}" height="{split_y:g}">'
            f'{inst(top_color, y, p["opacity"])}</svg>'
            f'<svg y="{split_y:g}" width="{w:g}" height="{h - split_y:g}">'
            f'{inst(bottom_color, y - split_y, p["lower_opacity"])}</svg>')


def silhouette_svg(key: str, color: str, x: float, y: float, size: float,
                   opacity: float = 0.26, uid: str = "") -> str:
    """アイコン1つぶんのSVG断片。未知のキーなら空文字。

    透明度は**グループにまとめて**掛ける。パーツごとに掛けると重なった所だけ
    濃くなって継ぎ目が出るため。
    """
    s = variant(key, uid)
    if not s:
        return ""
    k = size / 100
    return (f'<g transform="translate({x:g} {y:g}) scale({k:g})" '
            f'fill="{color}" opacity="{opacity:g}">{s}</g>')
