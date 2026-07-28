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

座標系は各アイコンとも 0..100 の正方形で、`silhouette_svg()` /
`silhouette_card_svg()` がカードの座標へ平行移動+拡大する。
"""

from material_icons import MATERIAL_ICONS

# 役割 -> SVG断片(0..100 の座標系)
SILHOUETTES = MATERIAL_ICONS

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
    # ディスクの手前(x=107)で止まる大きさにする。
    # 上下は 48..172 で、帯の境目(y=112)をほぼ中央でまたぐ
    "water": {"box": (0, 48, 124), "opacity": 0.22, "split": True,
              "lower_opacity": 0.30},
    # 右側に大きく置いて右端と下端で切る
    "edge": {"box": (150, 16, 196), "opacity": 0.22, "split": True,
             "lower_opacity": 0.30},
}


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

    return (f'<defs><g id="{sid}">{s}</g></defs>'
            f'<svg width="{w:g}" height="{split_y:g}">'
            f'{inst(top_color, y, p["opacity"])}</svg>'
            f'<svg y="{split_y:g}" width="{w:g}" height="{h - split_y:g}">'
            f'{inst(bottom_color, y - split_y, p["lower_opacity"])}</svg>')


def silhouette_svg(key: str, color: str, x: float, y: float, size: float,
                   opacity: float = 0.26) -> str:
    """アイコン1つぶんのSVG断片。未知のキーなら空文字。

    透明度は**グループにまとめて**掛ける。パーツごとに掛けると重なった所だけ
    濃くなって継ぎ目が出るため。
    """
    s = SILHOUETTES.get(key)
    if not s:
        return ""
    k = size / 100
    return (f'<g transform="translate({x:g} {y:g}) scale({k:g})" '
            f'fill="{color}" opacity="{opacity:g}">{s}</g>')
