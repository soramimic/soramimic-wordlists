#!/usr/bin/env python3
"""数学の語に、プログラムで作図した図版SVGを生成する。

数学の用語は Wikipedia に語と完全一致する記事が無いか、あっても図が無いものが
多い(95語が画像なし)。一方でこれらは**図そのものが定義**なので、生成イラストに
頼るより作図したほうが正確で読みやすい。判別式なら二次関数のグラフと x 軸の
交わり方、内分点なら線分上の点、というように図が語を説明する。

- 1語1枚。viewBox は 320x200 固定(ほかの生成カードと同じ)
- 自己完結SVG(外部フォント・画像を参照しない)。日本語は font-family の
  フォールバック指定で描く
- **AI生成ではないので「AIイメージ」の札は入れない**(ADR 00028 の札は生成
  イラストが実写と誤認されるのを防ぐためのもので、線画の作図には当たらない)
- ファイル名は生成イラストと同じ `gk_<sha1(語)先頭10桁>.svg`。拡張子だけ .svg
- 生成物はリポジトリに置かず、GitHub Release のアセットとして配布する
  (gimukyoiku の既存画像と同じ。CSV の image/image_page はそのURLを指す)

usage:
  python3 tools/gen_gimukyoiku_math_figs.py --out /tmp/mathfigs
  python3 tools/gen_gimukyoiku_math_figs.py --out /tmp/mathfigs --sheet  # 一覧HTMLも出す
"""

import argparse
import hashlib
import math
from pathlib import Path

W, H = 320, 200
# 先頭は fontconfig で実際に日本語グリフへ解決されるファミリ名にする。
# "Noto Sans JP" は環境によってラテン専用の "Noto Sans" にマッチしてしまい、
# 日本語が□(トーフ)になる(Noto Sans CJK JP が正しいファミリ名)。
FONT = "Noto Sans CJK JP,Noto Sans JP,Hiragino Sans,Yu Gothic,Meiryo,sans-serif"
MATHFONT = "Times New Roman,Georgia,serif"

INK = "#26303d"        # 主線・文字
SUB = "#8b97a6"        # 補助線・目盛り
ACCENT = "#d1603c"     # 強調(注目させたい要素)
FILL = "#dce8f5"       # 面の塗り
FILL2 = "#f3ddd3"      # 強調の面
BG = "#ffffff"


def key(word):
    return "gk_" + hashlib.sha1(word.encode()).hexdigest()[:10]


# ---- 描画ヘルパ(figure関数はこれらを使って部品を返す) --------------------

def t(x, y, s, size=11, fill=INK, anchor="middle", font=FONT, weight="400", style=""):
    st = f' font-style="{style}"' if style else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-family="{font}" font-weight="{weight}"{st}>{s}</text>')


def mt(x, y, s, size=12, fill=INK, anchor="middle"):
    """数式用(斜体セリフ)。x や y のような変数はこちらで書く。"""
    return t(x, y, s, size, fill, anchor, MATHFONT, "400", "italic")


def line(x1, y1, x2, y2, stroke=INK, w=1.4, dash=None, cap="round"):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{w}" stroke-linecap="{cap}"{d}/>')


def path(d, stroke=INK, w=1.6, fill="none", dash=None):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{w}" '
            f'stroke-linejoin="round" stroke-linecap="round"{da}/>')


def circle(cx, cy, r, stroke=INK, w=1.4, fill="none", dash=None):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{w}"{da}/>')


def dot(cx, cy, r=2.6, fill=INK):
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}"/>'


def rect(x, y, w_, h_, stroke=INK, w=1.3, fill="none", rx=0, dash=None):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w_:.1f}" height="{h_:.1f}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{w}"{da}/>')


def poly(pts, stroke=INK, w=1.5, fill="none"):
    p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return f'<polygon points="{p}" fill="{fill}" stroke="{stroke}" stroke-width="{w}" stroke-linejoin="round"/>'


def arrow(x1, y1, x2, y2, stroke=INK, w=1.5, head="end"):
    m = f' marker-end="url(#ah)"' if head in ("end", "both") else ""
    m += f' marker-start="url(#ahs)"' if head in ("start", "both") else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{w}" stroke-linecap="round"{m}/>')


def axes(ox, oy, x0, x1, y0, y1, xlab="x", ylab="y"):
    """原点(ox,oy)の座標軸。x0..x1 / y0..y1 は原点からの相対の伸び。"""
    g = [arrow(ox + x0, oy, ox + x1, oy, SUB, 1.2),
         arrow(ox, oy - y0, ox, oy - y1, SUB, 1.2)]
    if xlab:
        g.append(mt(ox + x1 + 7, oy + 4, xlab, 11, SUB))
    if ylab:
        g.append(mt(ox - 7, oy - y1 - 3, ylab, 11, SUB))
    g.append(mt(ox - 6, oy + 11, "O", 10, SUB))
    return g


def svg(body):
    defs = (
        '<defs>'
        f'<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" '
        f'markerHeight="5" orient="auto-start-reverse">'
        f'<path d="M0,1 L9,5 L0,9 z" fill="context-stroke"/></marker>'
        f'<marker id="ahs" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" '
        f'markerHeight="5" orient="auto">'
        f'<path d="M0,1 L9,5 L0,9 z" fill="context-stroke"/></marker>'
        '</defs>'
    )
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{W}" height="{H}">{defs}'
            f'<rect width="{W}" height="{H}" fill="{BG}"/>'
            + "".join(body) + '</svg>')


def titled(word, body, note=None):
    """語を上部に、必要なら補足を下部に置いた1枚に仕上げる。"""
    head = [t(W / 2, 20, word, 13, INK, "middle", FONT, "700")]
    foot = [t(W / 2, H - 8, note, 9.5, SUB)] if note else []
    return svg(head + list(body) + foot)


FIGURES = {}


def figure(*words):
    def deco(fn):
        for w in words:
            FIGURES[w] = fn
        return fn
    return deco


# ---- figs_A_二次関数と論理 ----------------------------------------------------

"""グループA(二次関数と論理)の図版。

framework.py のヘルパだけで描く。各関数は引数なしで SVG 文字列を返す。
"""

def _v_A(s):
    """日本語まじりの文中に置く変数(斜体セリフの tspan)。"""
    return f'<tspan font-family="{MATHFONT}" font-style="italic">{s}</tspan>'

def _pts_path_A(pts):
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)

def _mparab(ox, oy, sx, sy, a, h, k, x0, x1, n=48):
    """数学座標の放物線 y = a(x-h)^2 + k の path d 文字列。"""
    pts = []
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        y = a * (x - h) ** 2 + k
        pts.append((ox + sx * x, oy - sy * y))
    return _pts_path_A(pts)

def _pparab(cx, vy, m, half, n=40, up=True):
    """ピクセル座標の放物線。頂点(cx,vy)、上に開くなら up=True。"""
    return _pparab_range(cx, vy, m, cx - half, cx + half, n, up)

def _pparab_range(cx, vy, m, px0, px1, n=44, up=True):
    """頂点(cx,vy)の放物線を px0..px1 の範囲だけ描く。"""
    pts = []
    for i in range(n + 1):
        px = px0 + (px1 - px0) * i / n
        dx = px - cx
        py = vy - m * dx * dx if up else vy + m * dx * dx
        pts.append((px, py))
    return _pts_path_A(pts)

def _frac(cx, cy, num, den, size=15, fill=INK, half=11):
    """分数。cy が横線の y。"""
    return [mt(cx, cy - 5, num, size, fill),
            line(cx - half, cy, cx + half, cy, fill, 1.2),
            mt(cx, cy + size + 2, den, size, fill)]

def fig_平方完成():
    ox, oy, sx, sy = 120, 140, 20, 6
    body = []
    body.append(mt(150, 56, "x² − 4x + 1  =", 14, INK, "end"))
    body.append(mt(156, 56, "(x − 2)² − 3", 14, ACCENT, "start"))
    body += axes(ox, oy, -28, 118, -30, 62)
    body.append(path(_mparab(ox, oy, sx, sy, 1, 2, -3, -1.3, 5.3), INK, 1.8))
    body.append(line(160, 96, 160, 168, SUB, 1.0, dash="3 3"))
    body.append(dot(160, 158, 3.2, ACCENT))
    body.append(mt(180, 169, "(2, −3)", 11, ACCENT, "start"))
    return titled("平方完成", body, "( )² の形にまとめると頂点が見える")

def fig_判別式():
    body = [mt(160, 46, "D = b² − 4ac", 13)]
    ax = 128            # x軸の高さ
    m = 0.0375
    half = 34
    panels = [(60, 148, "D > 0", "交点 2個"),
              (160, 128, "D = 0", "交点 1個"),
              (260, 108, "D &lt; 0", "交点 0個")]
    for cx, vy, dlab, nlab in panels:
        body.append(line(cx - 42, ax, cx + 42, ax, SUB, 1.1))
        body.append(path(_pparab(cx, vy, m, half), INK, 1.6))
        d = vy - ax
        if d > 0:
            k = (d / m) ** 0.5
            body.append(dot(cx - k, ax, 3.0, ACCENT))
            body.append(dot(cx + k, ax, 3.0, ACCENT))
        elif d == 0:
            body.append(dot(cx, ax, 3.0, ACCENT))
        body.append(mt(cx, 164, dlab, 12.5))
        body.append(t(cx, 178, nlab, 9.5, SUB))
    return titled("判別式", body)

def fig_最大値():
    ox, oy = 70, 160
    body = axes(ox, oy, -16, 228, -14, 112)
    body.append(line(100, oy, 252, oy, INK, 2.6))
    body.append(path(_pparab_range(170, 62, 0.011, 100, 252, up=False), INK, 1.8))
    body.append(line(100, 116, 100, oy, SUB, 1.0, dash="3 3"))
    body.append(line(252, 136, 252, oy, SUB, 1.0, dash="3 3"))
    body.append(dot(100, 116, 2.6))
    body.append(dot(252, 136, 2.6))
    body.append(mt(100, 174, "a", 11, SUB))
    body.append(mt(252, 174, "b", 11, SUB))
    body.append(line(ox, 62, 170, 62, ACCENT, 1.0, dash="3 3"))
    body.append(dot(170, 62, 3.4, ACCENT))
    body.append(t(38, 58, "最大値", 10, ACCENT))
    return titled("最大値", body, "範囲に頂点が入れば頂点の値がそれになる")

def fig_最小値():
    ox, oy = 70, 168
    body = axes(ox, oy, -16, 230, -8, 116)
    body.append(path(_pparab(165, 132, 0.009, 88), INK, 1.8))
    body.append(line(165, 64, 165, oy, SUB, 1.0, dash="3 3"))
    body.append(mt(165, 180, "p", 11, SUB))
    body.append(line(ox, 132, 165, 132, ACCENT, 1.0, dash="3 3"))
    body.append(dot(165, 132, 3.4, ACCENT))
    body.append(t(38, 128, "最小値", 10, ACCENT))
    return titled("最小値", body, "平方完成すると頂点の値としてわかる")

def fig_命題():
    body = []
    body.append(rect(18, 44, 240, 40, SUB, 1.2, rx=6))
    body.append(t(138, 69, f'{_v_A("x = 2")} ならば {_v_A("x² = 4")}', 12.5))
    body.append(circle(285, 64, 13, INK, 1.3))
    body.append(t(285, 68, "真", 11, INK))
    body.append(rect(18, 96, 240, 40, SUB, 1.2, rx=6))
    body.append(t(138, 121, f'{_v_A("x² = 4")} ならば {_v_A("x = 2")}', 12.5))
    body.append(circle(285, 116, 13, ACCENT, 1.6))
    body.append(t(285, 120, "偽", 11, ACCENT))
    body.append(t(138, 158, f'反例 {_v_A("x = −2")}', 10.5, ACCENT))
    return titled("命題", body, "真か偽かがはっきり決まる文")

def _venn(accent_outer):
    """P ⊂ Q の入れ子ベン図。accent_outer=True なら外側を強調。"""
    g = []
    if accent_outer:
        g.append(circle(178, 112, 56, ACCENT, 2.4, fill=FILL2))
        g.append(circle(164, 124, 26, INK, 1.4, fill="#ffffff"))
        g.append(mt(178, 74, "q", 14, ACCENT))
        g.append(mt(164, 129, "p", 13, INK))
    else:
        g.append(circle(178, 112, 56, SUB, 1.6, fill=FILL))
        g.append(circle(164, 124, 26, ACCENT, 2.4, fill=FILL2))
        g.append(mt(178, 74, "q", 14, SUB))
        g.append(mt(164, 129, "p", 13, ACCENT))
    return g

def fig_必要条件():
    body = [mt(62, 62, "p ⇒ q", 16), t(62, 82, "が真のとき", 10, SUB)]
    body += _venn(True)
    return titled("必要条件", body, "q が成りたたなければ p も成りたたない")

def fig_十分条件():
    body = [mt(62, 62, "p ⇒ q", 16), t(62, 82, "が真のとき", 10, SUB)]
    body += _venn(False)
    return titled("十分条件", body, "p が成りたてば q は必ず成りたつ")

def fig_必要十分条件():
    body = [t(160, 50, "どちらの向きも成りたつ", 10, SUB)]
    body.append(rect(20, 78, 120, 36, SUB, 1.2, rx=6))
    body.append(mt(80, 102, "p ⇒ q", 15))
    body.append(t(160, 101, "かつ", 10, SUB))
    body.append(rect(180, 78, 120, 36, SUB, 1.2, rx=6))
    body.append(mt(240, 102, "q ⇒ p", 15))
    body.append(arrow(160, 120, 160, 140, SUB, 1.4))
    body.append(mt(160, 168, "p ⇔ q", 21, ACCENT))
    return titled("必要十分条件", body, "たがいに言いかえられる(同値)")

def fig_対偶():
    body = []
    body.append(rect(20, 46, 206, 40, SUB, 1.2, rx=6))
    body.append(t(123, 71, f'{_v_A("p")} ならば {_v_A("q")}', 12.5))
    body.append(rect(20, 116, 206, 40, SUB, 1.2, rx=6))
    body.append(t(123, 141, f'{_v_A("q")} でない ならば {_v_A("p")} でない', 12))
    body.append(arrow(123, 90, 123, 112, SUB, 1.3, head="both"))
    body.append(circle(266, 66, 13, ACCENT, 1.6))
    body.append(t(266, 70, "真", 11, ACCENT))
    body.append(circle(266, 136, 13, ACCENT, 1.6))
    body.append(t(266, 140, "真", 11, ACCENT))
    body.append(t(266, 105, "同じ", 9.5, SUB))
    return titled("対偶", body, "もとの命題と真偽がつねに一致する")

def fig_背理法():
    body = []
    rows = [(36, INK, None, INK, f'{_v_A("p")} を証明したい'),
            (74, INK, "4 3", INK, f'{_v_A("p")} でないと仮定する'),
            (112, ACCENT, None, ACCENT, "矛盾が起こる"),
            (150, INK, None, INK, f'よって {_v_A("p")} は正しい')]
    for y, stroke, dash, fill, label in rows:
        body.append(rect(52, y, 216, 28, stroke, 1.3, rx=5, dash=dash))
        body.append(t(160, y + 18, label, 11.5, fill))
    for y in (64, 102, 140):
        body.append(arrow(160, y, 160, y + 10, SUB, 1.3))
    return titled("背理法", body)

def fig_恒等式():
    body = [mt(160, 54, "(x + 1)² = x² + 2x + 1", 15)]
    x0, x1 = 78, 242
    cols = [78, 126, 184, 242]
    ys = [72, 94, 116, 138, 160]
    for y in ys:
        body.append(line(x0, y, x1, y, SUB, 1.0))
    for x in cols:
        body.append(line(x, ys[0], x, ys[-1], SUB, 1.0))
    body.append(mt(102, 88, "x", 11, SUB))
    body.append(t(155, 88, "左辺", 10, SUB))
    body.append(t(213, 88, "右辺", 10, SUB))
    for i, (xv, lhs, rhs) in enumerate([(0, 1, 1), (1, 4, 4), (2, 9, 9)]):
        y = 110 + 22 * i
        body.append(mt(102, y, str(xv), 12))
        body.append(mt(155, y, str(lhs), 12))
        body.append(mt(213, y, str(rhs), 12))
    return titled("恒等式", body, "どんな値を入れても両辺が等しい")

def fig_対称式():
    body = [t(160, 48, f'{_v_A("x")} と {_v_A("y")} を入れかえる', 10, SUB)]
    body.append(mt(104, 76, "x² + y²", 16))
    body.append(arrow(146, 71, 184, 71, SUB, 1.3))
    body.append(mt(228, 76, "y² + x²", 16))
    body.append(t(160, 98, "もとの式と同じ", 10, ACCENT))
    body.append(line(44, 112, 276, 112, SUB, 0.9, dash="4 4"))
    body.append(mt(150, 140, "x² + y²  =", 14, INK, "end"))
    body.append(mt(154, 140, "(x + y)²", 14, ACCENT, "start"))
    body.append(mt(212, 140, "−", 14, INK, "start"))
    body.append(mt(226, 140, "2xy", 14, ACCENT, "start"))
    body.append(t(180, 158, "和", 9.5, SUB))
    body.append(t(240, 158, "積", 9.5, SUB))
    return titled("対称式", body, "和と積がわかれば値が計算できる")

def fig_剰余の定理():
    body = [t(160, 52, f'{_v_A("P(x)")} を {_v_A("x − a")} で割った余りは', 11.5)]
    body.append(mt(160, 90, "P(a)", 27, ACCENT))
    body.append(line(50, 108, 270, 108, SUB, 0.9, dash="4 4"))
    body.append(t(160, 128, f'例  {_v_A("x² + 3x + 1")} を {_v_A("x − 2")} で割ると', 10, SUB))
    body.append(t(160, 154, f'余りは {_v_A("P(2) = 4 + 6 + 1 = 11")}', 12))
    return titled("剰余の定理", body, "割り算をしなくても代入だけで求まる")

def fig_解と係数の関係():
    body = [t(160, 50, f'{_v_A("ax² + bx + c = 0")} の解を {_v_A("α, β")} とすると', 11)]
    body.append(mt(146, 96, "α + β  =", 16, INK, "end"))
    body += _frac(168, 91, "−b", "a", 15, ACCENT)
    body.append(mt(146, 146, "αβ  =", 16, INK, "end"))
    body += _frac(168, 141, "c", "a", 15, ACCENT)
    return titled("解と係数の関係", body, "解を求めなくても和と積がわかる")

def fig_互いに素():
    body = []
    rows = [(70, "8 の約数", [1, 2, 4, 8]),
            (118, "15 の約数", [1, 3, 5, 15])]
    for cy, label, ds in rows:
        body.append(t(46, cy + 4, label, 10, SUB))
        for i, d in enumerate(ds):
            cx = 105 + 45 * i
            if d == 1:
                body.append(rect(cx - 16, cy - 14, 32, 27, ACCENT, 1.6, fill=FILL2, rx=5))
                body.append(mt(cx, cy + 4, str(d), 12.5, ACCENT))
            else:
                body.append(rect(cx - 16, cy - 14, 32, 27, SUB, 1.2, fill="#ffffff", rx=5))
                body.append(mt(cx, cy + 4, str(d), 12.5, INK))
    body.append(t(160, 160, f'共通の約数は {_v_A("1")} だけ', 11.5))
    return titled("互いに素", body, "2つの整数の最大公約数が 1 である関係")

# ---- figs_B_図形 ----------------------------------------------------

"""グループB(図形)の図版。

framework.py のヘルパだけで描く。各関数は引数なしで SVG 文字列を返す。
座標は目分量で置かず、交点・分点・中心・接点などをすべて計算して求める。
"""

def _v_B(s):
    """日本語まじりの文中に置く変数(斜体セリフの tspan)。"""
    return f'<tspan font-family="{MATHFONT}" font-style="italic">{s}</tspan>'

def _pts_path_B(pts, close=False):
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    return d + (" Z" if close else "")

def _sub_B(p, q):
    return (p[0] - q[0], p[1] - q[1])

def _add(p, q):
    return (p[0] + q[0], p[1] + q[1])

def _mul(p, k):
    return (p[0] * k, p[1] * k)

def _len(p):
    return math.hypot(p[0], p[1])

def _dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])

def _unit(p):
    n = _len(p)
    return (p[0] / n, p[1] / n)

def _lerp(p, q, s):
    return (p[0] + (q[0] - p[0]) * s, p[1] + (q[1] - p[1]) * s)

def _mid(p, q):
    return _lerp(p, q, 0.5)

def _rot(p, deg):
    """画面座標(y下向き)での回転。deg>0 は見た目の反時計回り。"""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c + p[1] * s, -p[0] * s + p[1] * c)

def _polar(c, r, deg):
    """中心 c から距離 r、数学の角度 deg(反時計回り)の点。"""
    a = math.radians(deg)
    return (c[0] + r * math.cos(a), c[1] - r * math.sin(a))

def _ang(c, p):
    """c から見た p の数学角度(度)。"""
    return math.degrees(math.atan2(-(p[1] - c[1]), p[0] - c[0]))

def _line_inter(p1, p2, q1, q2):
    """直線 p1p2 と q1q2 の交点。"""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = q1
    x4, y4 = q2
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    a = x1 * y2 - y1 * x2
    b = x3 * y4 - y3 * x4
    return ((a * (x3 - x4) - (x1 - x2) * b) / d,
            (a * (y3 - y4) - (y1 - y2) * b) / d)

def _foot(p, a, b):
    """点 p から直線 ab に下ろした垂線の足。"""
    d = _sub_B(b, a)
    s = ((p[0] - a[0]) * d[0] + (p[1] - a[1]) * d[1]) / (d[0] ** 2 + d[1] ** 2)
    return _add(a, _mul(d, s))

def _line_circle(p, d, c, r):
    """点 p から方向 d の直線と中心 c 半径 r の円の交点(近い順)。"""
    u = _unit(d)
    f = _sub_B(p, c)
    b = 2 * (f[0] * u[0] + f[1] * u[1])
    cc = f[0] ** 2 + f[1] ** 2 - r * r
    disc = math.sqrt(b * b - 4 * cc)
    ts = sorted([(-b - disc) / 2, (-b + disc) / 2])
    return [_add(p, _mul(u, s)) for s in ts]

def _tangent_points(p, c, r):
    """外部の点 p から円(c, r)への 2 接点。"""
    d = _dist(p, c)
    ang = math.degrees(math.acos(r / d))
    u = _unit(_sub_B(p, c))
    return [_add(c, _mul(_rot(u, ang), r)), _add(c, _mul(_rot(u, -ang), r))]

def _arc(c, r, a0, a1, stroke=INK, w=1.3, dash=None, fill="none"):
    """中心 c 半径 r、数学角 a0→a1 の円弧。"""
    p0 = _polar(c, r, a0)
    p1 = _polar(c, r, a1)
    large = 1 if abs(a1 - a0) > 180 else 0
    sweep = 0 if a1 > a0 else 1          # y下向きなので数学角が増える=sweep 0
    d = (f"M{p0[0]:.2f},{p0[1]:.2f} A{r:.2f},{r:.2f} 0 {large} {sweep} "
         f"{p1[0]:.2f},{p1[1]:.2f}")
    return path(d, stroke, w, fill, dash)

def _angle_mark(v, p, q, r=16, stroke=ACCENT, w=1.3, n=1, gap=3.5):
    """頂点 v の、辺 vp と vq がはさむ角の弧(短い方)。"""
    a0 = _ang(v, p)
    a1 = _ang(v, q)
    diff = (a1 - a0 + 180) % 360 - 180
    out = []
    for i in range(n):
        out.append(_arc(v, r + i * gap, a0, a0 + diff, stroke, w))
    return out

def _right_angle(v, p, q, s=8, stroke=SUB, w=1.2):
    """頂点 v の直角記号(vp, vq 方向)。"""
    u1 = _mul(_unit(_sub_B(p, v)), s)
    u2 = _mul(_unit(_sub_B(q, v)), s)
    a = _add(v, u1)
    b = _add(v, _add(u1, u2))
    c = _add(v, u2)
    return path(_pts_path_B([a, b, c]), stroke, w)

def _ticks(p, q, n=1, size=6, stroke=INK, w=1.4, gap=4.0, at=0.5):
    """線分 pq の等長印(斜線 n 本)。"""
    d = _unit(_sub_B(q, p))
    nm = (-d[1], d[0])
    m = _lerp(p, q, at)
    out = []
    for i in range(n):
        off = (i - (n - 1) / 2) * gap
        c = _add(m, _mul(d, off))
        out.append(line(c[0] - nm[0] * size / 2, c[1] - nm[1] * size / 2,
                        c[0] + nm[0] * size / 2, c[1] + nm[1] * size / 2,
                        stroke, w))
    return out

def _seg(p, q, stroke=INK, w=1.5, dash=None):
    return line(p[0], p[1], q[0], q[1], stroke, w, dash)

def _dbl(p, q, stroke=SUB, w=1.1):
    """両矢印。"""
    return (f'<line x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}" '
            f'stroke="{stroke}" stroke-width="{w}" marker-start="url(#ahs)" '
            f'marker-end="url(#ah)"/>')

def _circumcenter(a, b, c):
    return _line_inter(_mid(a, b), _add(_mid(a, b), _rot(_sub_B(b, a), 90)),
                       _mid(b, c), _add(_mid(b, c), _rot(_sub_B(c, b), 90)))

def _incenter(a, b, c):
    la, lb, lc = _dist(b, c), _dist(c, a), _dist(a, b)
    s = la + lb + lc
    return ((la * a[0] + lb * b[0] + lc * c[0]) / s,
            (la * a[1] + lb * b[1] + lc * c[1]) / s)

def _inradius(a, b, c):
    la, lb, lc = _dist(b, c), _dist(c, a), _dist(a, b)
    area = abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2
    return 2 * area / (la + lb + lc)

def _centroid(a, b, c):
    return ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3)

def _cube(ox, oy, u, n=1, dxk=0.45, dyk=0.30):
    """立方体の投影。(x右, y上, z奥) -> 画面座標。"""
    def pr(x, y, z):
        return (ox + u * x + dxk * u * z, oy - u * y - dyk * u * z)
    return pr

def fig_メネラウスの定理():
    A, B, C = (72, 50), (40, 152), (208, 152)
    P = _lerp(A, B, 0.45)                       # 辺AB上
    Q = _lerp(A, C, 0.75)                       # 辺AC上
    # 直線PQ と 直線BC の交点(BC の延長上に出る)
    R = _line_inter(P, Q, B, C)
    body = [poly([A, B, C], INK, 1.7, FILL),
            _seg(C, R, SUB, 1.2, "4 3"),
            _seg(_lerp(P, R, -0.10), _lerp(P, R, 1.06), ACCENT, 1.7)]
    for p in (A, B, C):
        body.append(dot(p[0], p[1], 2.6, INK))
    for p in (P, Q, R):
        body.append(dot(p[0], p[1], 3.0, ACCENT))
    body += [t(A[0], A[1] - 8, "A", 11), t(B[0] - 10, B[1] + 12, "B", 11),
             t(C[0] + 2, C[1] + 14, "C", 11), t(R[0] + 6, R[1] + 14, "R", 11, ACCENT),
             t(P[0] - 13, P[1] - 6, "P", 11, ACCENT),
             t(Q[0] + 1, Q[1] + 14, "Q", 11, ACCENT)]
    return titled("メネラウスの定理", body,
                  "AP:PB × BR:RC × CQ:QA の積は 1")

def fig_方べきの定理():
    O, r = (188, 104), 50
    P = (52, 120)
    A, B = _line_circle(P, _sub_B((258, 138), P), O, r)      # 割線
    T = min(_tangent_points(P, O, r), key=lambda p: p[1])  # 接線(上側)
    body = [circle(O[0], O[1], r, INK, 1.5, FILL),
            _seg(P, _lerp(P, B, 1.06), ACCENT, 1.6),
            _seg(P, _lerp(P, T, 1.04), ACCENT, 1.6),
            _right_angle(T, O, P, 7, SUB, 1.1),
            _seg(O, T, SUB, 1.0, "3 3"),
            dot(O[0], O[1], 2.2, SUB), dot(P[0], P[1], 3.2, INK),
            dot(A[0], A[1], 3.0, ACCENT), dot(B[0], B[1], 3.0, ACCENT),
            dot(T[0], T[1], 3.0, ACCENT),
            t(P[0] - 9, P[1] + 4, "P", 11),
            t(A[0] - 2, A[1] + 14, "A", 11), t(B[0] + 9, B[1] + 10, "B", 11),
            t(T[0] - 3, T[1] - 7, "T", 11), t(O[0] + 8, O[1] + 4, "O", 10, SUB)]
    return titled("方べきの定理", body, "PA・PB = PT²(点 P から引いた 2 直線)")

def fig_内分点():
    A, B = (52, 112), (272, 112)
    m, n = 2, 3
    P = _lerp(A, B, m / (m + n))
    body = [_seg(A, B, INK, 1.8)]
    for k in range(1, m + n):                       # 5等分の目盛り
        q = _lerp(A, B, k / (m + n))
        body.append(line(q[0], q[1] - 4, q[0], q[1] + 4, SUB, 1.0))
    body += [_dbl(_add(A, (0, -22)), _add(P, (0, -22))),
             _dbl(_add(P, (0, -22)), _add(B, (0, -22))),
             mt(_mid(A, P)[0], 82, "2", 12, SUB),
             mt(_mid(P, B)[0], 82, "3", 12, SUB),
             dot(A[0], A[1], 3.2), dot(B[0], B[1], 3.2),
             dot(P[0], P[1], 4.0, ACCENT),
             t(A[0], A[1] + 18, "A", 11), t(B[0], B[1] + 18, "B", 11),
             t(P[0], P[1] + 19, "P", 12, ACCENT),
             t(160, 152, "線分の内側にある", 10, SUB)]
    return titled("内分点", body, "A(a), B(b) のとき P = (3a + 2b) / 5")

def fig_外分点():
    A, B = (58, 112), (178, 112)
    m, n = 3, 1
    Q = _lerp(A, B, m / (m - n))                    # 外分点(延長上)
    body = [_seg(A, B, INK, 1.8),
            _seg(B, _lerp(B, Q, 1.12), SUB, 1.4, "5 4")]
    for k in range(1, 3):
        q = _lerp(A, Q, k / 3)
        body.append(line(q[0], q[1] - 4, q[0], q[1] + 4, SUB, 1.0))
    body += [_dbl(_add(A, (0, -24)), _add(Q, (0, -24))),
             mt(_mid(A, Q)[0], 80, "3", 12, SUB),
             _dbl(_add(B, (0, 24)), _add(Q, (0, 24))),
             mt(_mid(B, Q)[0], 150, "1", 12, SUB),
             dot(A[0], A[1], 3.2), dot(B[0], B[1], 3.2),
             dot(Q[0], Q[1], 4.0, ACCENT),
             t(A[0], A[1] + 18, "A", 11), t(B[0], B[1] + 18, "B", 11),
             t(Q[0] + 12, Q[1] + 4, "Q", 12, ACCENT),
             t(118, 152, "線分の外(延長上)にある", 10, SUB)]
    return titled("外分点", body, "A(a), B(b) のとき Q = (−a + 3b) / (3 − 1)")

def fig_点と直線の距離():
    L1, L2 = (36, 152), (282, 66)
    P = (108, 56)
    Hf = _foot(P, L1, L2)                    # 垂線の足
    d = _dist(P, Hf)
    body = [_seg(L1, L2, INK, 1.7),
            _seg(P, Hf, ACCENT, 1.7, "5 4"),
            _right_angle(Hf, P, L2, 9, SUB, 1.2),
            dot(P[0], P[1], 3.4, ACCENT), dot(Hf[0], Hf[1], 3.0, INK),
            mt(P[0] - 6, P[1] - 8, "P(x₀, y₀)", 11, ACCENT, "start"),
            t(Hf[0] + 9, Hf[1] + 13, "H", 11),
            mt(_mid(P, Hf)[0] - 8, _mid(P, Hf)[1], "d", 13, ACCENT, "end"),
            mt(L2[0] + 4, L2[1] - 6, "ℓ", 12, INK),
            mt(188, 132, "ax + by + c = 0", 11, SUB, "start")]
    assert abs(d - _dist(P, _foot(P, L1, L2))) < 1e-9
    return titled("点と直線の距離", body,
                  "d = |ax₀ + by₀ + c| / √(a² + b²)")

def fig_五心():
    # 3枚のパネル。三角形は共通、中心は計算で求める
    A0, B0, C0 = (52, 8), (6, 58), (84, 70)
    oy = 56
    out = []
    for i, (ox, lab) in enumerate([(14, "外心"), (112, "内心"), (210, "重心")]):
        A = (ox + A0[0], oy + A0[1])
        B = (ox + B0[0], oy + B0[1])
        C = (ox + C0[0], oy + C0[1])
        out.append(poly([A, B, C], INK, 1.5, FILL))
        if i == 0:
            O = _circumcenter(A, B, C)
            R = _dist(O, A)
            out.append(circle(O[0], O[1], R, SUB, 1.1))
            for p, q in ((A, B), (B, C), (C, A)):
                m = _mid(p, q)
                out.append(_seg(m, O, SUB, 1.0, "3 3"))
                out += _ticks(p, q, 1, 5, SUB, 1.0)
            ctr = O
        elif i == 1:
            I = _incenter(A, B, C)
            rr = _inradius(A, B, C)
            out.append(circle(I[0], I[1], rr, SUB, 1.1))
            for v, p, q in ((A, B, C), (B, C, A), (C, A, B)):
                out.append(_seg(v, I, SUB, 1.0, "3 3"))
                out += _angle_mark(v, p, q, 11, SUB, 1.0, 2, 3)
            ctr = I
        else:
            G = _centroid(A, B, C)
            for v, p, q in ((A, B, C), (B, C, A), (C, A, B)):
                m = _mid(p, q)
                out.append(_seg(v, m, SUB, 1.0))
                out += _ticks(p, m, 1, 5, SUB, 1.0)
                out += _ticks(m, q, 1, 5, SUB, 1.0)
            ctr = G
        out.append(dot(ctr[0], ctr[1], 3.4, ACCENT))
        out.append(t(ox + 45, 160, lab, 11, INK, "middle", FONT, "700"))
    return titled("五心", out, "このほかに垂心・傍心があり、あわせて五つ")

def fig_内接する四角形():
    O, r = (160, 103), 58
    A = _polar(O, r, 40)
    B = _polar(O, r, 115)
    C = _polar(O, r, 195)
    D = _polar(O, r, 300)
    body = [circle(O[0], O[1], r, SUB, 1.2),
            poly([A, B, C, D], INK, 1.6, FILL)]
    body += _angle_mark(A, B, D, 15, ACCENT, 1.4)
    body += _angle_mark(C, D, B, 15, ACCENT, 1.4)
    for p in (A, B, C, D):
        body.append(dot(p[0], p[1], 3.0, INK))
    body += [t(A[0] + 9, A[1] - 4, "A", 11, ACCENT),
             t(B[0] - 3, B[1] - 8, "B", 11),
             t(C[0] - 10, C[1] + 3, "C", 11, ACCENT),
             t(D[0] + 3, D[1] + 14, "D", 11),
             dot(O[0], O[1], 2.0, SUB),
             mt(A[0] - 17, A[1] + 17, "α", 11, ACCENT),
             mt(C[0] + 28, C[1] - 9, "180°−α", 10, ACCENT)]
    return titled("内接する四角形", body, "向かい合う角の和は 180°")

def fig_合同条件():
    A0, B0, C0 = (40, 6), (5, 60), (75, 60)
    oy = 58
    out = []
    panels = [(14, "三辺"), (112, "二辺と間の角"), (210, "一辺と両端の角")]
    for i, (ox, lab) in enumerate(panels):
        A = (ox + A0[0], oy + A0[1])
        B = (ox + B0[0], oy + B0[1])
        C = (ox + C0[0], oy + C0[1])
        out.append(poly([A, B, C], INK, 1.6, FILL))
        if i == 0:
            out += _ticks(A, B, 1, 7, ACCENT, 1.5)
            out += _ticks(B, C, 2, 7, ACCENT, 1.5)
            out += _ticks(C, A, 3, 7, ACCENT, 1.5)
        elif i == 1:
            out += _ticks(A, B, 1, 7, ACCENT, 1.5)
            out += _ticks(A, C, 2, 7, ACCENT, 1.5)
            out += _angle_mark(A, B, C, 14, ACCENT, 1.4)
        else:
            out += _ticks(B, C, 1, 7, ACCENT, 1.5)
            out += _angle_mark(B, C, A, 14, ACCENT, 1.4)
            out += _angle_mark(C, A, B, 13, ACCENT, 1.4, 2, 3.5)
        out.append(t(ox + 40, 140, lab, 10, INK, "middle", FONT, "700"))
    out.append(t(160, 160, "この 3 つのどれか 1 つが成り立てば合同", 10, SUB))
    return titled("合同条件", out)

def fig_面積比():
    # 相似比 1:2。大きい三角形は小さい三角形 4 つ分になるよう中点連結で分割
    s = 44.0
    h = 38.0
    a1 = [(30, 142), (30 + s, 142), (30 + s / 2, 142 - h)]
    bx, by = 140, 142
    a2 = [(bx, by), (bx + 2 * s, by), (bx + s, by - 2 * h)]
    m01 = _mid(a2[0], a2[1])
    m12 = _mid(a2[1], a2[2])
    m20 = _mid(a2[2], a2[0])
    body = [poly(a1, INK, 1.6, FILL2),
            poly(a2, INK, 1.6, FILL),
            _seg(m01, m12, SUB, 1.1), _seg(m12, m20, SUB, 1.1),
            _seg(m20, m01, SUB, 1.1),
            _dbl((30, 156), (30 + s, 156)),
            _dbl((bx, 156), (bx + 2 * s, 156)),
            mt(30 + s / 2, 169, "1", 12, SUB),
            mt(bx + s, 169, "2", 12, SUB),
            mt(30 + s / 2, 136, "1", 12, ACCENT),
            mt(bx + s, 122, "4", 13, ACCENT)]
    return titled("面積比", body, "相似比 1 : 2 なら面積比は 1² : 2² = 1 : 4")

def fig_体積比():
    body = []
    for ox, oy, n, u, lab in [(46, 146, 1, 34, "1"), (168, 146, 2, 34, "2")]:
        pr = _cube(ox, oy, u, n)
        e = [((0, 0, 0), (n, 0, 0)), ((n, 0, 0), (n, n, 0)),
             ((n, n, 0), (0, n, 0)), ((0, n, 0), (0, 0, 0)),
             ((0, n, 0), (0, n, n)), ((n, n, 0), (n, n, n)),
             ((n, 0, 0), (n, 0, n)), ((0, n, n), (n, n, n)),
             ((n, n, n), (n, 0, n))]
        fill_front = [pr(0, 0, 0), pr(n, 0, 0), pr(n, n, 0), pr(0, n, 0)]
        fill_top = [pr(0, n, 0), pr(n, n, 0), pr(n, n, n), pr(0, n, n)]
        fill_right = [pr(n, 0, 0), pr(n, n, 0), pr(n, n, n), pr(n, 0, n)]
        body.append(poly(fill_front, INK, 0.0, FILL))
        body.append(poly(fill_top, INK, 0.0, FILL2))
        body.append(poly(fill_right, INK, 0.0, FILL))
        if n == 2:                       # 単位立方体への分割線
            for k in range(1, n):
                body.append(_seg(pr(k, 0, 0), pr(k, n, 0), SUB, 1.0))
                body.append(_seg(pr(0, k, 0), pr(n, k, 0), SUB, 1.0))
                body.append(_seg(pr(k, n, 0), pr(k, n, n), SUB, 1.0))
                body.append(_seg(pr(0, n, k), pr(n, n, k), SUB, 1.0))
                body.append(_seg(pr(n, k, 0), pr(n, k, n), SUB, 1.0))
                body.append(_seg(pr(n, 0, k), pr(n, n, k), SUB, 1.0))
        for p, q in e:
            body.append(_seg(pr(*p), pr(*q), INK, 1.4))
        for p, q in [((0, 0, 0), (0, 0, n)), ((0, 0, n), (n, 0, n)),
                     ((0, 0, n), (0, n, n))]:
            body.append(_seg(pr(*p), pr(*q), SUB, 1.0, "3 3"))
        e0, e1 = pr(0, 0, 0), pr(n, 0, 0)
        body.append(_dbl(_add(e0, (0, 12)), _add(e1, (0, 12))))
        body.append(mt(_mid(e0, e1)[0], _mid(e0, e1)[1] + 24, lab, 12, SUB))
    return titled("体積比", body, "相似比 1 : 2 なら体積比は 1³ : 2³ = 1 : 8")

def fig_立体の切断():
    # 奥行きは左上へ(切断面 x+y+z=3/2 が視線と平行に近くならない向き)
    ox, oy, u = 142, 152, 76
    pr = _cube(ox, oy, u, 1, dxk=-0.45)
    V = {(x, y, z): pr(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)}
    solid = [((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (1, 1, 0)),
             ((1, 1, 0), (0, 1, 0)), ((0, 1, 0), (0, 0, 0)),
             ((0, 1, 0), (0, 1, 1)), ((1, 1, 0), (1, 1, 1)),
             ((0, 0, 0), (0, 0, 1)), ((0, 1, 1), (1, 1, 1)),
             ((0, 0, 1), (0, 1, 1))]
    hidden = [((1, 0, 0), (1, 0, 1)), ((1, 0, 1), (1, 1, 1)),
              ((0, 0, 1), (1, 0, 1))]
    # 平面 x+y+z = 3/2 による切り口(各辺の中点を通る正六角形)
    hexa = [(1, .5, 0), (.5, 1, 0), (0, 1, .5), (0, .5, 1), (.5, 0, 1), (1, 0, .5)]
    hp = [pr(*p) for p in hexa]
    body = []
    for p, q in hidden:
        body.append(_seg(V[p], V[q], SUB, 1.0, "4 3"))
    body.append(poly(hp, ACCENT, 1.8, FILL2))
    for p, q in solid:
        body.append(_seg(V[p], V[q], INK, 1.5))
    body.append(poly(hp, ACCENT, 1.8, "none"))
    for p in hp:
        body.append(dot(p[0], p[1], 2.4, ACCENT))
    body.append(t(266, 106, "切り口", 11, ACCENT))
    body.append(_seg((243, 104), (_lerp(hp[0], hp[5], 0.5)[0] + 8, 100), ACCENT, 1.0))
    return titled("立体の切断", body, "各辺の中点を通る平面で切ると切り口は正六角形")

def fig_球の体積():
    C, R = (98, 106), 52
    body = [circle(C[0], C[1], R, INK, 1.7, FILL)]
    ry = 17
    body.append(path(f"M{C[0]-R:.1f},{C[1]:.1f} A{R},{ry} 0 1 0 {C[0]+R:.1f},{C[1]:.1f}",
                     SUB, 1.2))
    body.append(path(f"M{C[0]-R:.1f},{C[1]:.1f} A{R},{ry} 0 1 1 {C[0]+R:.1f},{C[1]:.1f}",
                     SUB, 1.2, dash="4 3"))
    Pr = _polar(C, R, 55)
    body += [_seg(C, Pr, ACCENT, 1.6),
             dot(C[0], C[1], 2.6, INK),
             mt(_mid(C, Pr)[0] - 9, _mid(C, Pr)[1] - 2, "r", 13, ACCENT)]
    # V = (4/3)πr³
    fx = 232
    body += [mt(fx - 46, 112, "V =", 16, INK, "start"),
             mt(fx, 100, "4", 15), line(fx - 11, 106, fx + 11, 106, INK, 1.3),
             mt(fx, 122, "3", 15),
             mt(fx + 16, 112, "πr³", 16, INK, "start")]
    return titled("球の体積", body, "表面積は 4πr²")

def fig_面積図():
    x0, x1, x2 = 62, 172, 252          # a = 110, b = 80
    y0, y1, y2 = 54, 114, 154          # c = 60, d = 40
    body = [rect(x0, y0, x2 - x0, y2 - y0, INK, 1.6, FILL),
            _seg((x1, y0), (x1, y2), INK, 1.3),
            _seg((x0, y1), (x2, y1), INK, 1.3),
            mt((x0 + x1) / 2, y0 - 8, "a", 12, SUB),
            mt((x1 + x2) / 2, y0 - 8, "b", 12, SUB),
            mt(x0 - 8, (y0 + y1) / 2 + 4, "c", 12, SUB, "end"),
            mt(x0 - 8, (y1 + y2) / 2 + 4, "d", 12, SUB, "end"),
            mt((x0 + x1) / 2, (y0 + y1) / 2 + 5, "ac", 13),
            mt((x1 + x2) / 2, (y0 + y1) / 2 + 5, "bc", 13),
            mt((x0 + x1) / 2, (y1 + y2) / 2 + 5, "ad", 13),
            mt((x1 + x2) / 2, (y1 + y2) / 2 + 5, "bd", 13)]
    return titled("面積図", body, "(a + b)(c + d) = ac + ad + bc + bd")

def fig_軌跡():
    A, B = (80, 148), (204, 106)
    M = _mid(A, B)
    u = _unit(_rot(_sub_B(B, A), 90))          # 垂直二等分線の方向(画面の上向き)
    if u[1] > 0:
        u = _mul(u, -1)
    L1 = _add(M, _mul(u, 74))
    L2 = _add(M, _mul(u, -40))
    P = _add(M, _mul(u, 54))
    Q = _add(M, _mul(u, -28))
    body = [_seg(L1, L2, ACCENT, 1.8),
            _seg(A, B, INK, 1.5),
            _right_angle(M, B, P, 8, SUB, 1.1),
            _seg(P, A, SUB, 1.2, "4 3"), _seg(P, B, SUB, 1.2, "4 3"),
            _seg(Q, A, SUB, 1.0, "3 3"), _seg(Q, B, SUB, 1.0, "3 3")]
    body += _ticks(P, A, 1, 6, SUB, 1.2)
    body += _ticks(P, B, 1, 6, SUB, 1.2)
    body += _ticks(Q, A, 1, 6, SUB, 1.2)
    body += _ticks(Q, B, 1, 6, SUB, 1.2)
    body += [dot(A[0], A[1], 3.2), dot(B[0], B[1], 3.2),
             dot(M[0], M[1], 2.4, SUB),
             dot(P[0], P[1], 3.4, ACCENT), dot(Q[0], Q[1], 3.0, ACCENT),
             t(A[0] - 10, A[1] + 6, "A", 11), t(B[0] + 10, B[1] + 5, "B", 11),
             t(P[0] - 11, P[1] + 2, "P", 11, ACCENT),
             t(Q[0] + 11, Q[1] + 4, "Q", 11, ACCENT)]
    # PA = PB, QA = QB を計算で確認
    assert abs(_dist(P, A) - _dist(P, B)) < 1e-6
    assert abs(_dist(Q, A) - _dist(Q, B)) < 1e-6
    return titled("軌跡", body, "2 点 A, B から等距離にある点の軌跡は垂直二等分線")

def fig_領域():
    ox, oy, u = 140, 120, 16              # 原点と 1 目盛り
    def sc(x, y):
        return (ox + u * x, oy - u * y)
    # 直線 x + y = 3(画面では傾き +1)
    x_at = lambda ys: 140 + (ys - 72)      # 画面 y に対する画面 x
    top = (x_at(45), 45)
    bot = (x_at(165), 165)
    region = [top, (40, 45), (40, 165), bot]
    body = [poly(region, "none", 0.0, FILL),
            _seg(top, bot, ACCENT, 1.7, "6 4")]
    body += axes(ox, oy, -100, 140, -45, 75)
    body += [mt(84, 152, "x + y &lt; 3", 13, ACCENT),
             mt(232, 112, "x + y = 3", 10, SUB),
             dot(*sc(0, 3), 2.6, SUB), dot(*sc(3, 0), 2.6, SUB),
             mt(sc(0, 3)[0] - 8, sc(0, 3)[1] - 5, "3", 10, SUB),
             mt(sc(3, 0)[0] + 3, sc(3, 0)[1] + 13, "3", 10, SUB)]
    return titled("領域", body, "境界を含むときは実線、含まないときは破線")

def fig_直線の方程式():
    ox, oy, u = 110, 140, 18
    def sc(x, y):
        return (ox + u * x, oy - u * y)
    # y = (1/2)x + 2
    f = lambda x: 0.5 * x + 2
    p1, p2 = sc(-4, f(-4)), sc(6, f(6))
    yi = sc(0, 2)
    a, b, c = sc(0, 2), sc(2, 2), sc(2, 3)
    body = axes(ox, oy, -80, 170, -25, 94)
    body += [_seg(p1, p2, INK, 1.9),
             _seg(a, b, SUB, 1.2), _seg(b, c, SUB, 1.2),
             mt(_mid(a, b)[0], _mid(a, b)[1] + 13, "2", 11, SUB),
             mt(b[0] + 8, _mid(b, c)[1] + 4, "1", 11, SUB),
             dot(yi[0], yi[1], 3.4, ACCENT),
             mt(yi[0] - 8, yi[1] + 4, "2", 12, ACCENT, "end"),
             mt(p2[0] + 6, p2[1] + 2, "y = ½x + 2", 12, INK, "start")]
    return titled("直線の方程式", body, "傾き ½、y 切片 2")

def fig_準線():
    vx, vy, p = 160, 132, 24              # 頂点と 焦点までの距離 p
    F = (vx, vy - p)
    dy = vy + p                            # 準線 y = vy + p
    pts = []
    for i in range(61):
        X = -92 + 184 * i / 60
        pts.append((vx + X, vy - X * X / (4 * p)))
    P = (vx + 70, vy - 70 * 70 / (4 * p))
    Hf = (P[0], dy)
    body = [path(_pts_path_B(pts), INK, 1.8),
            line(30, dy, 292, dy, ACCENT, 1.8),
            _seg(P, F, SUB, 1.4), _seg(P, Hf, SUB, 1.4),
            _right_angle(Hf, P, (Hf[0] + 20, Hf[1]), 7, SUB, 1.1),
            dot(F[0], F[1], 3.4, INK), dot(P[0], P[1], 3.4, INK),
            dot(vx, vy, 2.2, SUB),
            _seg((vx, vy - 84), (vx, dy + 6), SUB, 0.9, "3 3")]
    body += _ticks(P, F, 1, 6, SUB, 1.2)
    body += _ticks(P, Hf, 1, 6, SUB, 1.2)
    body += [t(F[0] - 9, F[1] + 4, "F", 11), t(P[0] + 9, P[1] - 3, "P", 11),
             t(Hf[0] + 3, Hf[1] + 14, "H", 11, SUB),
             mt(48, dy - 7, "ℓ", 12, ACCENT)]
    assert abs(_dist(P, F) - (dy - P[1])) < 1e-6      # PF = PH
    return titled("準線", body, "放物線上の点は 焦点までの距離 = 準線までの距離")

def fig_極方程式():
    O = (84, 116)
    a = 42
    Cc = (O[0] + a, O[1])                  # r = 2a cosθ は中心(a,0)半径 a の円
    th = 40
    r = 2 * a * math.cos(math.radians(th))
    P = _polar(O, r, th)
    body = [circle(Cc[0], Cc[1], a, INK, 1.6, FILL),
            arrow(O[0], O[1], 258, O[1], SUB, 1.2),
            _seg(O, P, ACCENT, 1.8),
            _arc(O, 26, 0, th, ACCENT, 1.3),
            dot(O[0], O[1], 3.4, INK), dot(P[0], P[1], 3.4, ACCENT),
            t(O[0] - 11, O[1] + 14, "O", 11), t(O[0] - 11, O[1] + 27, "極", 9, SUB),
            t(250, O[1] + 15, "始線", 10, SUB),
            mt(_mid(O, P)[0] - 9, _mid(O, P)[1] - 2, "r", 13, ACCENT),
            mt(O[0] + 34, O[1] - 8, "θ", 12, ACCENT),
            t(P[0] + 8, P[1] - 5, "P", 11, ACCENT),
            mt(228, 168, "r = 2a cos θ", 13, INK)]
    assert abs(_dist(P, Cc) - a) < 1e-6     # P が円上にあること
    return titled("極方程式", body, "極 O からの距離 r と始線からの角 θ で点を表す")

# ---- figs_C_確率と統計 ----------------------------------------------------

"""確率と統計の語の図版(20語)。framework.py のヘルパだけで描く。"""

def _sub_C(s, size=12):
    """下付き文字の tspan。"""
    d = round(size * 0.24, 1)
    return (f'<tspan font-size="{round(size * 0.62, 1)}" dy="{d}">{s}</tspan>'
            f'<tspan font-size="{size}" dy="-{d}"></tspan>')

def _npr(n, sym, r, tail="", size=13, color=None):
    """nPr / nCr の形。左下と右下に添字。"""
    d = round(size * 0.24, 1)
    ss = round(size * 0.62, 1)
    c = f' fill="{color}"' if color else ""
    return (f'<tspan{c} font-size="{ss}" dy="{d}">{n}</tspan>'
            f'<tspan{c} font-size="{size}" dy="-{d}">{sym}</tspan>'
            f'<tspan{c} font-size="{ss}" dy="{d}">{r}</tspan>'
            f'<tspan font-size="{size}" dy="-{d}">{tail}</tspan>')

def _bar(s):
    """平均を表すバー付き文字(x̄ など)。"""
    return f'<tspan text-decoration="overline">{s}</tspan>'

def _pcond(size=12):
    """条件付き確率 P_A(B)。"""
    d = round(size * 0.24, 1)
    return ('P' + f'<tspan font-size="{round(size * 0.62, 1)}" dy="{d}">A</tspan>'
            f'<tspan font-size="{size}" dy="-{d}">(B)</tspan>')

ZMAX = 3.3

def _bell_pts(cx, base, hw, h, z0=-ZMAX, z1=ZMAX, n=40):
    """標準正規曲線の点列。x は z に比例、y は exp(-z^2/2) に比例(左右対称)。"""
    pts = []
    for i in range(n + 1):
        z = z0 + (z1 - z0) * i / n
        pts.append((cx + hw * z / ZMAX, base - h * math.exp(-z * z / 2)))
    return pts

def _smooth(pts, base=None):
    """点列を通る滑らかな3次ベジエ曲線。base を渡すと底辺で閉じる(塗り用)。"""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    n = len(pts)
    for i in range(n - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, n - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += (f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} "
              f"{p2[0]:.1f},{p2[1]:.1f}")
    if base is not None:
        d += f" L{pts[-1][0]:.1f},{base:.1f} L{pts[0][0]:.1f},{base:.1f} Z"
    return d

def _bell_x(cx, hw, z):
    return cx + hw * z / ZMAX

def _bell_y(base, h, z):
    return base - h * math.exp(-z * z / 2)

def fig_順列():
    b = []
    for i, ch in enumerate("ABC"):
        x = 118 + i * 30
        b.append(rect(x, 36, 24, 28, INK, 1.3, FILL, rx=3))
        b.append(t(x + 12, 55, ch, 13))
    b.append(t(160, 78, "3 枚から 2 枚をとって並べる", 9.5, SUB))
    for k, p in enumerate(["AB", "AC", "BA", "BC", "CA", "CB"]):
        x0 = 80 + (k % 3) * 72
        y0 = 86 + (k // 3) * 32
        for j, ch in enumerate(p):
            b.append(rect(x0 + j * 20, y0, 18, 24, INK, 1.1, "none", rx=3))
            b.append(t(x0 + j * 20 + 9, y0 + 17, ch, 11))
    b.append(mt(160, 166, _npr(3, "P", 2, " = 3 × 2 = 6", 13, ACCENT), 13))
    return titled("順列", b, "AB と BA は別のものとして数える")

def fig_組合せ():
    b = []
    for i, ch in enumerate("ABC"):
        x = 118 + i * 30
        b.append(rect(x, 36, 24, 28, INK, 1.3, FILL, rx=3))
        b.append(t(x + 12, 55, ch, 13))
    b.append(t(160, 82, "3 枚から 2 枚をとる", 9.5, SUB))
    for k, g in enumerate(["AB", "AC", "BC"]):
        x0 = 52 + k * 80
        b.append(rect(x0, 96, 56, 32, INK, 1.3, FILL, rx=16))
        b.append(t(x0 + 18, 117, g[0], 12))
        b.append(t(x0 + 38, 117, g[1], 12))
    b.append(mt(160, 162, _npr(3, "C", 2, " = 3", 13, ACCENT), 13))
    return titled("組合せ", b, "AB と BA は同じ ── 順序を考えない")

def fig_円順列():
    b = []
    for cx, seq in ((88, "ABCD"), (232, "DABC")):
        b.append(circle(cx, 108, 34, SUB, 1.3))
        for i, ch in enumerate(seq):
            ang = -90 + 90 * i
            x = cx + 26 * math.cos(math.radians(ang))
            y = 108 + 26 * math.sin(math.radians(ang)) + 4
            b.append(t(x, y, ch, 12))
            b.append(dot(cx + 34 * math.cos(math.radians(ang)),
                         108 + 34 * math.sin(math.radians(ang)), 2.4, SUB))
    b.append(path("M136,80 A28,28 0 0 1 184,80", ACCENT, 1.3))
    b.append(poly([(180, 74), (188, 79), (179, 85)], ACCENT, 1, ACCENT))
    b.append(t(160, 66, "90° 回す", 9, ACCENT))
    b.append(t(160, 114, "=", 15, INK))
    b.append(t(160, 166, "(4 − 1)! = 6 通り", 12))
    return titled("円順列", b, "回転して重なる並びは同じ 1 通りと数える")

def fig_重複順列():
    b = []
    b.append(t(118, 40, "1 回目", 9, SUB))
    b.append(t(200, 40, "2 回目", 9, SUB))
    b.append(dot(42, 108, 3))
    tops = (62, 108, 154)
    for gi, ch in enumerate("ABC"):
        y = tops[gi]
        b.append(line(48, 108, 110, y, INK, 1.2))
        b.append(t(118, y + 4, ch, 12))
        for li, ch2 in enumerate("ABC"):
            ly = y - 14 + li * 14
            b.append(line(126, y, 192, ly, INK, 1.1))
            b.append(t(200, ly + 4, ch2, 11))
    b.append(mt(266, 104, "3² = 9", 14, ACCENT))
    b.append(t(266, 122, "通り", 9, SUB))
    return titled("重複順列", b, "同じものを何度でも選んでよい")

def fig_事象():
    b = [rect(45, 44, 230, 110, INK, 1.3, "none"),
         mt(56, 58, "U", 10, SUB),
         t(68, 57, "起こりうる結果ぜんぶ", 8.5, SUB, anchor="start"),
         circle(115, 103, 40, ACCENT, 1.6, FILL),
         mt(64, 80, "A", 13, ACCENT)]
    for x, y, s in ((99, 92, "2"), (132, 100, "4"), (109, 128, "6")):
        b.append(mt(x, y, s, 12))
    for x, y, s in ((205, 74, "1"), (242, 106, "3"), (203, 140, "5")):
        b.append(mt(x, y, s, 12, SUB))
    b.append(t(160, 174, "さいころを投げて「偶数の目が出る」", 9.5, SUB))
    return titled("事象", b)

def fig_余事象():
    b = [rect(45, 44, 230, 104, INK, 1.3, FILL2),
         mt(56, 58, "U", 10, SUB),
         circle(120, 96, 40, INK, 1.4, FILL),
         mt(120, 101, "A", 14),
         mt(228, 100, _bar("A"), 15, ACCENT),
         mt(160, 170, "P(A) + P(" + _bar("A") + ") = 1", 13)]
    return titled("余事象", b, "A 以外の結果ぜんぶ(色のついた側)")

def fig_排反():
    b = [rect(40, 42, 240, 92, INK, 1.3, "none"),
         mt(50, 56, "U", 10, SUB),
         circle(105, 88, 33, INK, 1.4, FILL),
         circle(215, 88, 33, INK, 1.4, FILL),
         mt(105, 93, "A", 14),
         mt(215, 93, "B", 14),
         mt(160, 152, "A ∩ B = ∅", 12, ACCENT),
         mt(160, 172, "P(A ∪ B) = P(A) + P(B)", 13)]
    return titled("排反", b, "同時には起こらないので確率はそのまま足せる")

def fig_独立試行():
    b = [t(92, 40, "コイン", 9, SUB), t(186, 40, "さいころ", 9, SUB),
         dot(32, 105, 3)]
    b.append(line(38, 101, 82, 74, ACCENT, 1.5))
    b.append(line(38, 109, 82, 140, INK, 1.2))
    b.append(t(92, 74, "表", 11))
    b.append(t(92, 144, "裏", 11))
    b.append(mt(54, 80, "1/2", 9, SUB))
    b.append(mt(54, 132, "1/2", 9, SUB))
    rows = ((70, 48, 92), (140, 118, 162))
    for gi, (my, y1, y2) in enumerate(rows):
        for li, (ly, lab, p, q) in enumerate(((y1, "1 の目", "1/6", "1/12"),
                                              (y2, "1 以外", "5/6", "5/12"))):
            acc = (gi == 0 and li == 0)
            col = ACCENT if acc else INK
            b.append(line(104, my, 170, ly, col, 1.5 if acc else 1.1))
            b.append(t(186, ly + 4, lab, 10))
            b.append(mt(137, (my + ly) / 2 - 5, p, 9, SUB))
            b.append(mt(228, ly + 4, q, 10.5,
                        ACCENT if acc else SUB, anchor="start"))
    return titled("独立試行", b, "コインの結果はさいころに影響しない → 確率は掛け算")

def fig_反復試行():
    b = [t(160, 44, "コインを 3 回投げて表がちょうど 2 回", 9.5, SUB)]
    for r, pat in enumerate((("表", "表", "裏"), ("表", "裏", "表"),
                             ("裏", "表", "表"))):
        y = 56 + r * 30
        for c, ch in enumerate(pat):
            x = 124 + c * 25
            b.append(rect(x, y, 22, 24, INK, 1.2,
                          FILL if ch == "表" else "none", rx=3))
            b.append(t(x + 11, y + 17, ch, 10))
    b.append(mt(160, 166, _npr(3, "C", 2, " × (1/2)³ = 3/8", 13, ACCENT), 13))
    return titled("反復試行", b, "並び方が 3 通りあるので組合せの数を掛ける")

def fig_乗法定理():
    b = [rect(60, 50, 210, 80, INK, 1.3, "none"),
         rect(60, 50, 210, 30, INK, 1.2, FILL),
         rect(60, 50, 84, 30, ACCENT, 1.6, FILL2),
         mt(102, 69, "A ∩ B", 11, ACCENT),
         mt(213, 69, "A", 12),
         mt(264, 124, "U", 10, SUB)]
    # 左のかっこ: A の割合 P(A)
    b += [line(52, 50, 52, 80, SUB, 1.2), line(48, 50, 56, 50, SUB, 1.2),
          line(48, 80, 56, 80, SUB, 1.2),
          mt(44, 69, "P(A)", 10, SUB, anchor="end")]
    # 上のかっこ: A のうち B が起こる割合
    b += [line(60, 42, 144, 42, SUB, 1.2), line(60, 38, 60, 46, SUB, 1.2),
          line(144, 38, 144, 46, SUB, 1.2),
          mt(102, 36, _pcond(10), 10, SUB)]
    b.append(mt(160, 162, "P(A ∩ B) = P(A) × " + _pcond(12.5), 12.5))
    return titled("乗法定理", b, "A が起きたうえで B が起きる割合を掛ける")

def fig_期待値():
    b = [rect(40, 52, 240, 48, INK, 1.3, "none"),
         line(40, 76, 280, 76, INK, 1.1),
         line(100, 52, 100, 100, INK, 1.1),
         line(160, 52, 160, 100, SUB, 1.0),
         line(220, 52, 220, 100, SUB, 1.0),
         t(70, 69, "賞金(円)", 9, SUB),
         t(70, 93, "確率", 9, SUB)]
    for i, v in enumerate(("1000", "100", "0")):
        b.append(mt(130 + i * 60, 70, v, 12))
    for i, p in enumerate(("1/10", "3/10", "6/10")):
        b.append(mt(130 + i * 60, 94, p, 12))
    b.append(mt(160, 128, "1000 × 1/10 + 100 × 3/10 + 0 × 6/10", 11))
    b.append(t(160, 160, "= 130 円", 16, ACCENT, weight="700"))
    return titled("期待値", b, "値と確率を掛けて全部たすと平均的な値になる")

def fig_分散():
    b = axes(45, 150, -8, 240, -8, 105, "", "")
    b.append(line(45, 100, 278, 100, ACCENT, 1.3, dash="5 4"))
    b.append(t(60, 95, "平均", 9, ACCENT, anchor="start"))
    pts = ((75, 78), (115, 120), (155, 94), (195, 132), (235, 84))
    for x, y in pts:
        acc = (x == 235)
        b.append(line(x, y, x, 100, ACCENT if acc else SUB,
                      1.8 if acc else 1.2, dash=None if acc else "3 3"))
        b.append(dot(x, y, 3))
    b.append(rect(241, 84, 16, 16, ACCENT, 1.3, FILL2))
    b.append(t(261, 96, "2 乗", 9, ACCENT, anchor="start"))
    b.append(t(90, 62, "ずれ", 9, SUB))
    b.append(line(96, 66, 113, 112, SUB, 1.0))
    return titled("分散", b, "平均からのずれを 2 乗して平均したもの")

def fig_共分散():
    b = axes(50, 165, -8, 225, -8, 122, "x", "y")
    b.insert(0, rect(160, 48, 110, 57, "none", 0, FILL2))
    b.insert(0, rect(50, 105, 110, 60, "none", 0, FILL2))
    b += [line(160, 165, 160, 48, SUB, 1.1, dash="4 3"),
          line(50, 105, 270, 105, SUB, 1.1, dash="4 3"),
          mt(154, 60, _bar("x"), 11, SUB, anchor="end"),
          mt(44, 101, _bar("y"), 11, SUB, anchor="end")]
    for x, y, s in ((60, 62, "−"), (260, 62, "+"), (60, 158, "+"),
                    (260, 158, "−")):
        b.append(t(x, y, s, 15, INK))
    for x, y in ((72, 148), (92, 138), (108, 142), (124, 128), (140, 132),
                 (152, 118), (176, 106), (188, 96), (200, 100), (216, 88),
                 (234, 80), (250, 68)):
        b.append(dot(x, y, 3))
    return titled("共分散", b, "x のずれ × y のずれ の平均。色の側は積が正")

def fig_第一四分位数():
    x_min, q1, med, q3, x_max = 66, 105, 144, 196, 261
    b = [line(x_min, 95, q1, 95, INK, 1.3),
         line(q3, 95, x_max, 95, INK, 1.3),
         line(x_min, 80, x_min, 110, INK, 1.3),
         line(x_max, 80, x_max, 110, INK, 1.3),
         rect(q1, 74, q3 - q1, 42, INK, 1.4, FILL),
         line(med, 74, med, 116, INK, 1.4),
         line(q1, 74, q1, 116, ACCENT, 2.4)]
    for x, lab, col in ((x_min, "最小値", SUB), (med, "中央値", SUB),
                        (x_max, "最大値", SUB)):
        b.append(t(x, 132, lab, 8.5, col))
    b.append(mt(q1, 133, "Q" + _sub_C("1", 12), 12, ACCENT))
    b.append(mt(q3, 133, "Q" + _sub_C("3", 12), 12, SUB))
    b += [line(x_min, 148, q1, 148, ACCENT, 1.3),
          line(x_min, 144, x_min, 152, ACCENT, 1.3),
          line(q1, 144, q1, 152, ACCENT, 1.3),
          t((x_min + q1) / 2, 165, "全体の 1/4", 9, ACCENT)]
    return titled("第一四分位数", b)

def fig_仮説検定():
    cx, base, hw, h = 160, 152, 112, 86
    zc = 1.96
    b = [line(45, base, 275, base, SUB, 1.2)]
    b.append(path(_smooth(_bell_pts(cx, base, hw, h, -ZMAX, -zc), base),
                  ACCENT, 1.0, FILL2))
    b.append(path(_smooth(_bell_pts(cx, base, hw, h, zc, ZMAX), base),
                  ACCENT, 1.0, FILL2))
    b.append(path(_smooth(_bell_pts(cx, base, hw, h)), INK, 1.7))
    for s in (-1, 1):
        x = _bell_x(cx, hw, s * zc)
        b.append(line(x, base, x, _bell_y(base, h, zc), ACCENT, 1.1, dash="3 3"))
    b.append(t(160, 122, "よくある結果 95%", 9.5, SUB))
    b.append(t(58, 100, "棄却域", 9.5, ACCENT))
    b.append(t(262, 100, "棄却域", 9.5, ACCENT))
    b.append(arrow(62, 108, 82, 142, ACCENT, 1.1))
    b.append(arrow(258, 108, 238, 142, ACCENT, 1.1))
    return titled("仮説検定", b, "端の 5% に入るなら「偶然ではない」と判断する")

def fig_区間推定():
    cx, base, hw, h = 160, 138, 108, 76
    zc = 1.96
    xl, xr = _bell_x(cx, hw, -zc), _bell_x(cx, hw, zc)
    b = [line(45, base, 275, base, SUB, 1.2)]
    b.append(path(_smooth(_bell_pts(cx, base, hw, h, -zc, zc), base),
                  SUB, 1.0, FILL))
    b.append(path(_smooth(_bell_pts(cx, base, hw, h)), INK, 1.7))
    for x in (xl, xr):
        b.append(line(x, base, x, _bell_y(base, h, zc), SUB, 1.1, dash="3 3"))
    b.append(t(160, 108, "95%", 12, INK))
    b += [line(xl, 156, xr, 156, ACCENT, 1.8),
          line(xl, 151, xl, 161, ACCENT, 1.8),
          line(xr, 151, xr, 161, ACCENT, 1.8),
          dot(160, 156, 3, INK),
          mt(160, 149, _bar("x"), 11, INK),
          t(160, 174, "母平均はこの範囲にあると推定する", 9.5, ACCENT)]
    return titled("区間推定", b)

def _pop_sample(accent_pop):
    """母集団の大きな円と、そこから取り出した標本の小さな円。"""
    b = [t(95, 40, "母集団", 10, SUB), t(250, 40, "標本", 10, SUB),
         circle(95, 105, 52, INK, 1.5, FILL),
         circle(250, 105, 30, INK if accent_pop else ACCENT, 1.5, FILL2)]
    for i in range(22):
        r = 44 * math.sqrt((i + 0.5) / 22)
        a = i * 2.399963
        b.append(dot(95 + r * math.cos(a), 105 + r * math.sin(a), 2.3, SUB))
    for i in range(6):
        r = 19 * math.sqrt((i + 0.5) / 6)
        a = i * 2.399963
        b.append(dot(250 + r * math.cos(a), 105 + r * math.sin(a), 2.6, INK))
    return b

def fig_母平均():
    b = _pop_sample(True)
    b += [arrow(152, 95, 216, 95, SUB, 1.2),
          t(184, 87, "取り出す", 8.5, SUB),
          arrow(222, 126, 152, 126, ACCENT, 1.6),
          t(186, 143, "推定する", 8.5, ACCENT),
          mt(78, 174, "μ", 15, ACCENT, anchor="end"),
          t(83, 174, "全体の平均", 9, SUB, anchor="start"),
          mt(233, 174, _bar("x"), 14, SUB, anchor="end"),
          t(238, 174, "標本の平均", 9, SUB, anchor="start")]
    return titled("母平均", b)

def fig_標本平均():
    b = _pop_sample(False)
    b += [arrow(152, 105, 216, 105, ACCENT, 1.6),
          t(184, 96, "取り出す", 8.5, ACCENT),
          mt(78, 174, "μ", 15, SUB, anchor="end"),
          t(83, 174, "全体の平均", 9, SUB, anchor="start"),
          mt(233, 174, _bar("x"), 14, ACCENT, anchor="end"),
          t(238, 174, "標本の平均", 9, SUB, anchor="start")]
    return titled("標本平均", b)

def fig_降水確率():
    b = [rect(22, 44, 126, 100, SUB, 1.2, "none", rx=10)]
    for cx, cy, r in ((64, 76, 13), (83, 70, 17), (100, 78, 12)):
        b.append(circle(cx, cy, r, FILL, 1, FILL))
    b.append(rect(64, 78, 36, 10, FILL, 1, FILL))
    for x in (64, 76, 88, 100):
        b.append(line(x, 94, x - 4, 104, ACCENT, 1.6))
    b.append(t(85, 132, "70%", 22, ACCENT, weight="700"))
    b.append(t(232, 54, "同じ予報を 10 回出せば", 9, SUB))
    for i in range(10):
        cx = 180 + (i % 5) * 26
        cy = 80 + (i // 5) * 26
        if i < 7:
            b.append(path(f"M{cx},{cy - 10} C{cx + 7},{cy - 1} {cx + 8},{cy + 8} "
                          f"{cx},{cy + 8} C{cx - 8},{cy + 8} {cx - 7},{cy - 1} "
                          f"{cx},{cy - 10} Z", ACCENT, 1.3, FILL2))
        else:
            b.append(circle(cx, cy, 8, SUB, 1.2, "none", dash="3 3"))
    b.append(t(232, 126, "7 回くらいは雨", 9, ACCENT))
    return titled("降水確率", b, "1 mm 以上の雨が降ると見込まれる割合")

def fig_選挙速報():
    b = [t(44, 44, "開票率 20%", 9.5, SUB, anchor="start"),
         rect(44, 50, 236, 13, SUB, 1.2, "none", rx=2),
         rect(44, 50, 47, 13, SUB, 1.2, FILL, rx=2)]
    for lab, y, wdt, col, fl in (("A", 78, 140, ACCENT, FILL2),
                                 ("B", 106, 86, INK, FILL)):
        b.append(t(52, y + 13, lab, 12))
        b.append(rect(66, y, wdt, 20, col, 1.4, fl, rx=2))
        b.append(t(66 + wdt + 8, y + 14,
                   "62%" if lab == "A" else "38%", 10, SUB, anchor="start"))
    b.append(rect(96, 138, 128, 26, ACCENT, 1.6, "none", rx=4))
    b.append(t(160, 156, "A 当選確実", 14, ACCENT, weight="700"))
    return titled("選挙速報", b, "一部の開票結果から全体の結果を推測している")

# ---- figs_D_微積と数列 ----------------------------------------------------

"""グループD(微積分と数列)の図版。framework.py のヘルパだけで作図する。"""

def num(x, y, s, size=12, fill=INK, anchor="middle"):
    """数値・記号(立体セリフ)。"""
    return t(x, y, s, size, fill, anchor, MATHFONT)

def sub(x, y, base, idx, size=12, fill=INK):
    """a_n のように添字つきの記号を、中心 x に置く。"""
    bw = len(base) * size * 0.52
    iw = len(idx) * size * 0.72 * 0.52
    left = x - (bw + iw) / 2.0
    return [mt(left + bw, y, base, size, fill, "end"),
            mt(left + bw + 1, y + size * 0.28, idx, size * 0.72, fill, "start")]

def pl(pts):
    """点列を折れ線のパス文字列にする。"""
    return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

def ellipse(cx, cy, rx, ry, stroke=INK, w=1.3, fill="none", dash=None):
    d = (f"M {cx:.1f},{cy - ry:.1f} A {rx:.1f},{ry:.1f} 0 1,0 {cx:.1f},{cy + ry:.1f} "
         f"A {rx:.1f},{ry:.1f} 0 1,0 {cx:.1f},{cy - ry:.1f} Z")
    return path(d, stroke, w, fill, dash)

def strip(vals, cx0=40, dx=54, cy=100, r=16, hi=None):
    """数列の項を丸で横に並べる。戻り値は (部品list, 中心x list)。"""
    parts, xs = [], []
    for i, v in enumerate(vals):
        x = cx0 + dx * i
        xs.append(x)
        acc = (hi is not None and i == hi)
        parts.append(circle(x, cy, r, ACCENT if acc else SUB,
                            1.7 if acc else 1.3, FILL2 if acc else FILL))
        parts.append(num(x, cy + 5, v, 14, ACCENT if acc else INK))
    return parts, xs

def _curve_g(u):
    """図の中で使う共通の曲線(原点からの右向き距離 u に対する高さ)。"""
    return 0.0022 * u * u + 0.10 * u + 12.0

def _curve_pts(ox, oy, u0, u1, n=48):
    return [(ox + u0 + (u1 - u0) * i / n, oy - _curve_g(u0 + (u1 - u0) * i / n))
            for i in range(n + 1)]

def fig_平均変化率():
    ox, oy = 55, 158
    b = axes(ox, oy, -15, 215, -14, 120)
    b.append(path(pl(_curve_pts(ox, oy, 0, 190)), INK, 1.7))
    ax, ay = ox + 45, oy - _curve_g(45)          # (100, 137.0)
    bx, by = ox + 160, oy - _curve_g(160)        # (215, 73.7)
    b += [line(bx, by, bx, oy, SUB, 1.0, "3 3"),
          line(ax, ay, ax, oy, SUB, 1.0, "3 3"),
          line(ax, ay, bx, ay, SUB, 1.1, "3 3")]
    sl = (ay - by) / (bx - ax)
    b.append(line(ax - 15, ay + 15 * sl, bx + 20, by - 20 * sl, ACCENT, 1.8))
    b += [dot(ax, ay), dot(bx, by)]
    b += [mt(157, 149, "Δx", 10, SUB), mt(221, 108, "Δy", 10, SUB, "start"),
          mt(ax, 170, "a", 10, SUB), mt(bx, 170, "b", 10, SUB)]
    b += [mt(120, 62, "f(b) − f(a)", 11, ACCENT),
          line(83, 67, 157, 67, ACCENT, 1.1),
          mt(120, 82, "b − a", 11, ACCENT)]
    return titled("平均変化率", b, "2点を結ぶ直線の傾き")

def fig_接線の方程式():
    ox, oy = 55, 158
    b = axes(ox, oy, -15, 215, -14, 120)
    b.append(path(pl(_curve_pts(ox, oy, 0, 190)), INK, 1.7))
    u = 110.0
    px, py = ox + u, oy - _curve_g(u)            # (165, 108.4)
    sl = 0.0044 * u + 0.10                       # 0.584
    b.append(line(px - 60, py + 60 * sl, px + 80, py - 80 * sl, ACCENT, 1.8))
    b += [line(px, py, px, oy, SUB, 1.0, "3 3"), dot(px, py),
          mt(px, 170, "a", 10, SUB)]
    b.append(mt(160, 52, "y − f(a) = f ′(a)(x − a)", 12))
    return titled("接線の方程式", b, "傾きは接点での微分係数 f ′(a)")

def fig_増減表():
    b = []
    xs = [14, 58, 84, 110, 136, 162, 188]
    ys = [55, 85, 112, 145]
    for y in ys:
        b.append(line(xs[0], y, xs[-1], y, SUB, 1.0))
    for x in xs:
        b.append(line(x, ys[0], x, ys[-1], SUB, 1.0))
    b += [mt(36, 74, "x", 11), mt(36, 104, "f ′(x)", 11), mt(36, 134, "f(x)", 11)]
    cc = [71, 97, 123, 149, 175]
    for x, s in zip(cc, ["…", "−1", "…", "1", "…"]):
        b.append(num(x, 74, s, 11))
    for x, s in zip(cc, ["+", "0", "−", "0", "+"]):
        b.append(num(x, 104, s, 12))
    b += [arrow(cc[0] - 7, 139, cc[0] + 7, 119, INK, 1.3),
          num(cc[1], 134, "2", 11),
          arrow(cc[2] - 7, 119, cc[2] + 7, 139, INK, 1.3),
          num(cc[3], 134, "−2", 11),
          arrow(cc[4] - 7, 139, cc[4] + 7, 119, INK, 1.3)]
    gx, gy = 255, 110
    b += axes(gx, gy, -52, 52, -42, 42, None, None)
    pts = []
    for i in range(49):
        xv = -2.05 + 4.10 * i / 48
        pts.append((gx + 24 * xv, gy - 13 * (xv ** 3 - 3 * xv)))
    b.append(path(pl(pts), INK, 1.6))
    b += [dot(gx - 24, gy - 26, 2.6, ACCENT), dot(gx + 24, gy + 26, 2.6, ACCENT)]
    return titled("増減表", b, "符号が変わる所が極大・極小")

def fig_第二次導関数():
    cx, cy = 160, 108
    pts = []
    for i in range(61):
        u = -75 + 150 * i / 60
        pts.append((cx + u, cy - (u ** 3 / 12000.0 + 0.28 * u)))
    b = [line(cx, 44, cx, 172, SUB, 1.0, "3 3"),
         path(pl(pts), INK, 1.8),
         dot(cx, cy, 3.4, ACCENT),
         t(cx, 40, "変曲点", 9.5, ACCENT),
         t(112, 96, "上に凸", 9.5, SUB),
         mt(112, 80, "f ″(x) &lt; 0", 10, SUB),
         t(208, 134, "下に凸", 9.5, SUB),
         mt(208, 150, "f ″(x) &gt; 0", 10, SUB)]
    return titled("第二次導関数", b)

def _para(vx, vy, half, k, n=32):
    return [(vx - half + 2 * half * i / n, vy - (( -half + 2 * half * i / n) ** 2) / k)
            for i in range(n + 1)]

def fig_不定積分():
    b = [mt(160, 60, "∫ 2x dx = x² + C", 17)]
    b.append(line(160, 84, 160, 176, SUB, 1.0, "3 3"))
    for i, vy in enumerate([168, 148, 128]):
        b.append(path(pl(_para(160, vy, 78, 150.0)), INK if i == 0 else SUB, 1.5))
        b.append(mt(246, vy - 78 * 78 / 150.0 + 3.5, f"C = {i}", 10, SUB, "start"))
    return titled("不定積分", b, "C の値だけ上下にずれた曲線が、すべて答え")

def fig_積分定数():
    b = []
    base = 168
    for i, vy in enumerate([168, 144, 120, 96]):
        b.append(path(pl(_para(140, vy, 72, 160.0)), INK if i == 0 else SUB,
                      1.7 if i == 0 else 1.3))
    e0 = base - 72 * 72 / 160.0          # 135.6 : C=0 の右端
    e1 = 120 - 72 * 72 / 160.0           # 87.6  : もう1本の右端
    b += [mt(62, e0 + 3.5, "F(x)", 10, INK, "end"),
          mt(62, e1 + 3.5, "F(x) + C", 10, ACCENT, "end"),
          line(212, e0, 226, e0, SUB, 1.0, "3 3"),
          line(212, e1, 226, e1, SUB, 1.0, "3 3"),
          arrow(219, e0, 219, e1, ACCENT, 1.5, "both"),
          mt(229, (e0 + e1) / 2 + 4, "C", 13, ACCENT, "start")]
    return titled("積分定数", b, "どれを微分しても同じ関数にもどる")

def fig_原始関数():
    b = axes(70, 160, -35, 55, -8, 100)
    b.append(path(pl([(70 + u, 160 - u * u / 30.0)
                      for u in [-32 + 84 * i / 40 for i in range(41)]]), INK, 1.7))
    b.append(mt(100, 60, "F(x)", 12))
    b += axes(235, 118, -45, 45, -40, 45)
    b.append(line(190, 160, 280, 76, INK, 1.7))
    b.append(mt(272, 66, "f(x)", 12))
    b += [arrow(140, 112, 180, 112, ACCENT, 1.6),
          t(160, 104, "微分", 9.5, ACCENT)]
    return titled("原始関数", b, "F を微分すると f にもどる")

def fig_回転体の体積():
    ax = 118.0
    b = [arrow(40, ax, 292, ax, SUB, 1.2), mt(300, ax + 4, "x", 11, SUB)]

    def rad(x):
        return 18.0 + 28.0 * (((x - 75.0) / 175.0) ** 0.75)

    up = [(75 + 175 * i / 40, ax - rad(75 + 175 * i / 40)) for i in range(41)]
    dn = [(x, 2 * ax - y) for x, y in up]
    b += [path(pl(dn), SUB, 1.2), path(pl(up), INK, 1.9)]
    b += [ellipse(75, ax, 6.5, 18.0, SUB, 1.2),
          ellipse(250, ax, 8.0, rad(250), INK, 1.4)]
    dx = 185.0
    r = rad(dx)
    b += [ellipse(dx, ax, 7.0, r, ACCENT, 1.6, FILL2),
          line(dx, ax, dx, ax - r, ACCENT, 1.4),
          mt(dx - 13, ax - r / 2 + 4, "y", 11, ACCENT, "end"),
          arrow(dx - 7, 168, dx + 7, 168, ACCENT, 1.2, "both"),
          mt(dx, 163, "dx", 9.5, ACCENT)]
    return titled("回転体の体積", b, "V = π∫ y² dx")

def fig_曲線の長さ():
    def cx(s):
        return 35 + 250 * s

    def cy(s):
        return 118 - 55 * math.sin(3.4 * s + 0.2)

    b = [path(pl([(cx(i / 80), cy(i / 80)) for i in range(81)]), SUB, 1.4)]
    vs = [(cx(k / 8), cy(k / 8)) for k in range(9)]
    b.append(path(pl(vs), INK, 1.7))
    for x, y in vs:
        b.append(dot(x, y, 2.3))
    p, q = vs[7], vs[8]
    b += [line(p[0], p[1], q[0], q[1], ACCENT, 2.2),
          line(p[0], p[1], q[0], p[1], SUB, 1.1, "3 3"),
          line(q[0], p[1], q[0], q[1], SUB, 1.1, "3 3"),
          mt((p[0] + q[0]) / 2, p[1] - 6, "Δx", 9.5, SUB),
          mt(q[0] + 5, (p[1] + q[1]) / 2 + 4, "Δy", 9.5, SUB, "start"),
          dot(p[0], p[1], 2.8, ACCENT), dot(q[0], q[1], 2.8, ACCENT)]
    return titled("曲線の長さ", b, "細かい折れ線の長さの和の極限")

def fig_積の微分法():
    b = [rect(38, 66, 244, 66, SUB, 1.2, "none", 10),
         mt(160, 108, "( f g )′ = f ′g + f g′", 22)]
    return titled("積の微分法", b, "前を微分したもの + 後ろを微分したもの")

def fig_商の微分法():
    b = [rect(46, 62, 228, 76, SUB, 1.2, "none", 10),
         mt(74, 104, "(", 26),
         mt(90, 94, "f", 15), line(80, 99, 102, 99, INK, 1.1), mt(90, 116, "g", 15),
         mt(110, 104, ")", 26), mt(118, 94, "′", 15),
         mt(134, 104, "=", 16),
         mt(212, 96, "f ′g − f g′", 15),
         line(170, 102, 254, 102, INK, 1.1),
         mt(212, 120, "g²", 15)]
    return titled("商の微分法", b, "分母の2乗が出てくる")

def fig_対数微分法():
    b = [mt(160, 62, "y = (x+1)²(x+2)³", 15),
         t(160, 88, "両辺の対数をとる", 10, ACCENT),
         mt(160, 114, "log y = 2 log(x+1) + 3 log(x+2)", 13),
         t(160, 138, "両辺を微分する", 10, ACCENT),
         mt(160, 164, "y′/y = 2/(x+1) + 3/(x+2)", 13)]
    return titled("対数微分法", b, "累乗や積が多い式に効く")

def fig_置換積分法():
    b = [mt(160, 60, "x = g(t)", 17, ACCENT),
         arrow(160, 70, 160, 88, SUB, 1.3),
         mt(160, 106, "dx = g′(t) dt", 17),
         mt(160, 156, "∫ f (x) dx = ∫ f (g(t)) g′(t) dt", 14)]
    return titled("置換積分法", b, "dx の置きかえを忘れない")

def fig_部分積分法():
    b = [rect(28, 66, 264, 66, SUB, 1.2, "none", 10),
         mt(160, 108, "∫ f g′ dx = f g − ∫ f ′g dx", 19)]
    return titled("部分積分法", b, "片方を微分、もう片方を積分にまわす")

def fig_数列():
    b, xs = strip(["2", "5", "8", "11", "14"])
    b.append(num(296, 105, "…", 14, SUB))
    for i, x in enumerate(xs):
        b += sub(x, 134, "a", str(i + 1), 11, SUB)
    return titled("数列", b)

def fig_初項():
    b, xs = strip(["2", "5", "8", "11", "14"], hi=0)
    b.append(num(296, 105, "…", 14, SUB))
    for i, x in enumerate(xs):
        b += sub(x, 134, "a", str(i + 1), 11, ACCENT if i == 0 else SUB)
    b.append(arrow(xs[0], 62, xs[0], 80, ACCENT, 1.6))
    b += sub(xs[0], 55, "a", "1", 14, ACCENT)
    return titled("初項", b, "第1項ともいう")

def fig_公差():
    b, xs = strip(["2", "5", "8", "11", "14"])
    b.append(num(296, 105, "…", 14, SUB))
    for a, c in zip(xs, xs[1:]):
        m = (a + c) / 2
        b.append(path(f"M {a + 10:.1f},82 Q {m:.1f},58 {c - 10:.1f},82", ACCENT, 1.4))
        b.append(num(m, 64, "+3", 11, ACCENT))
    return titled("公差", b, "となり合う項の差はどこも同じ")

def fig_一般項():
    b, xs = strip(["2", "5", "8", "11"])
    b.append(num(238, 105, "…", 14, SUB))
    b += [circle(275, 100, 16, ACCENT, 1.5, FILL2, "4 3"),
          num(275, 104, "3n−1", 9.5, ACCENT)]
    for i, x in enumerate(xs):
        b += sub(x, 134, "a", str(i + 1), 11, SUB)
    b += sub(275, 134, "a", "n", 11, ACCENT)
    b += sub(125, 162, "a", "n", 15, ACCENT)
    b.append(mt(135, 162, "= 3n − 1", 15, ACCENT, "start"))
    return titled("一般項", b, "n に番号を入れると、その項の値になる")

def fig_階差数列():
    b, xs = strip(["1", "3", "7", "13", "21"], cx0=52, dx=58, cy=78, r=13)
    mids = [(a + c) / 2 for a, c in zip(xs, xs[1:])]
    for a, c, m in zip(xs, xs[1:], mids):
        b.append(line(a + 5, 90, m - 6, 130, SUB, 1.0))
        b.append(line(c - 5, 90, m + 6, 130, SUB, 1.0))
    d, _ = strip(["2", "4", "6", "8"], cx0=mids[0], dx=58, cy=142, r=12)
    b += [circle(m, 142, 12, ACCENT, 1.5, FILL2) for m in mids]
    b += [num(m, 147, v, 13, ACCENT) for m, v in zip(mids, ["2", "4", "6", "8"])]
    b += sub(20, 82, "a", "n", 11, SUB)
    b += sub(20, 146, "b", "n", 11, ACCENT)
    return titled("階差数列", b, "差の数列から、もとの数列がわかる")

def fig_シグマ記号():
    b = [t(72, 108, "Σ", 44, INK, "middle", MATHFONT),
         mt(72, 70, "n", 12),
         mt(72, 128, "k = 1", 11),
         t(72, 52, "終わりの番号", 8.5, SUB),
         t(72, 146, "はじめの番号", 8.5, SUB)]
    b += sub(108, 108, "a", "k", 17)
    b.append(mt(140, 108, "=", 15))
    b += sub(170, 108, "a", "1", 14)
    b.append(mt(190, 108, "+", 13))
    b += sub(210, 108, "a", "2", 14)
    b += [mt(230, 108, "+", 13), num(248, 108, "…", 13), mt(266, 108, "+", 13)]
    b += sub(288, 108, "a", "n", 14)
    return titled("シグマ記号", b, "1番目から n 番目までの和をまとめて書く")

def fig_漸化式():
    b = sub(86, 56, "a", "1", 14)
    b.append(mt(98, 56, "= 2", 14, INK, "start"))
    b += sub(160, 56, "a", "n+1", 14)
    b.append(mt(180, 56, "=", 14, INK, "start"))
    b += sub(202, 56, "a", "n", 14)
    b.append(mt(212, 56, "+ 3", 14, INK, "start"))
    s, xs = strip(["2", "5", "8", "11"], cx0=55, dx=55, cy=112, r=15)
    b += s
    b.append(num(262, 117, "…", 14, SUB))
    for a, c in zip(xs, xs[1:]):
        b.append(arrow(a + 17, 112, c - 17, 112, ACCENT, 1.4))
        b.append(num((a + c) / 2, 104, "+3", 10, ACCENT))
    b.append(arrow(xs[-1] + 17, 112, 250, 112, ACCENT, 1.4))
    for i, x in enumerate(xs):
        b += sub(x, 145, "a", str(i + 1), 11, SUB)
    return titled("漸化式", b, "初項とこの式で、すべての項が決まる")

def fig_収束():
    ox, oy = 50, 162
    b = axes(ox, oy, -14, 240, -12, 115, "n", None)
    lim = 95.0
    b += [line(44, lim, 286, lim, ACCENT, 1.4, "5 4"),
          mt(296, lim - 4, "α", 12, ACCENT)]
    pts = [(ox + 22 * n, lim + 62.0 / n) for n in range(1, 11)]
    b.append(path(pl(pts), SUB, 1.1))
    b += [dot(x, y, 2.6) for x, y in pts]
    return titled("収束", b, "n を大きくすると一定の値に近づく")

def fig_発散():
    ox, oy = 50, 162
    b = axes(ox, oy, -14, 240, -12, 115, "n", None)
    pts = [(ox + 22 * n, oy - 1.1 * (n ** 2.2)) for n in range(1, 9)]
    b.append(path(pl(pts), SUB, 1.1))
    b += [dot(x, y, 2.6) for x, y in pts]
    b += [arrow(233, 52, 272, 42, ACCENT, 1.6),
          mt(288, 52, "∞", 14, ACCENT)]
    return titled("発散", b, "どこまでも大きくなり、近づく値がない")

def fig_無限等比級数():
    b = [rect(40, 50, 56, 112, SUB, 1.0, FILL),
         rect(96, 50, 56, 56, SUB, 1.0, FILL2),
         rect(96, 106, 28, 56, SUB, 1.0, FILL),
         rect(124, 106, 28, 28, SUB, 1.0, FILL2),
         rect(124, 134, 14, 28, SUB, 1.0, FILL),
         rect(138, 134, 14, 14, SUB, 1.0, FILL2),
         rect(138, 148, 7, 14, SUB, 1.0, FILL),
         rect(40, 50, 112, 112, INK, 1.8),
         num(68, 112, "1/2", 13),
         num(124, 82, "1/4", 12),
         num(110, 140, "1/8", 10),
         mt(236, 96, "1/2 + 1/4 + 1/8 + …", 12),
         mt(240, 126, "= 1", 16, ACCENT)]
    return titled("無限等比級数", b, "|公比| &lt; 1 のとき一定の値に収束する")

# ---- figs_E_三角関数とベクトル ----------------------------------------------------

"""グループE(三角関数・ベクトル・複素数平面ほか)の図版。

各関数は引数なしで titled(語, body, note) の戻り値(SVG文字列)を返す。
ファイル末尾の FIGURES に担当語をすべて登録する。
"""

def _i(s):
    """数式の中の変数だけを斜体にする。"""
    return f'<tspan font-style="italic">{s}</tspan>'

def eq(x, y, s, size=14, fill=INK, anchor="middle", weight="400"):
    """立体セリフで数式を組む。変数は _i() で斜体にして混ぜる。"""
    return t(x, y, s, size, fill, anchor, MATHFONT, weight)

def card(x=20, y=46, w_=280, h_=104):
    """式を大きく置くためのカード。"""
    return rect(x, y, w_, h_, SUB, 1.2, FILL, rx=10)

def arc(cx, cy, r, a0, a1, stroke=INK, w=1.3):
    """中心(cx,cy)半径rの、角a0からa1(度・反時計回り)の弧。"""
    x0 = cx + r * math.cos(math.radians(a0))
    y0 = cy - r * math.sin(math.radians(a0))
    x1 = cx + r * math.cos(math.radians(a1))
    y1 = cy - r * math.sin(math.radians(a1))
    big = 1 if abs(a1 - a0) > 180 else 0
    return path(f"M{x0:.1f},{y0:.1f} A{r:.1f},{r:.1f} 0 {big} 1 {x1:.1f},{y1:.1f}",
                stroke, w)

def polyline(pts, stroke=INK, w=1.8, dash=None):
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return path(d, stroke, w, "none", dash)

def fig_周期():
    ox, oy = 46, 112
    amp, per = 34.0, 120.0
    body = axes(ox, oy, -16, 250, -46, 42, xlab="x", ylab="y")

    pts = [(ox + i, oy - amp * math.sin(2 * math.pi * i / per))
           for i in range(0, 241, 3)]
    body.append(polyline(pts, INK, 1.9))

    # 隣り合う山と山の間が1周期
    p1, p2 = ox + per / 4, ox + per / 4 + per          # 山の x 座標
    top = oy - amp
    for px in (p1, p2):
        body.append(line(px, top - 2, px, 62, SUB, 1.0, dash="3 3"))
        body.append(dot(px, top, 2.4, ACCENT))
    body.append(arrow(p1, 58, p2, 58, ACCENT, 1.4, head="both"))
    body.append(eq((p1 + p2) / 2, 50, "2" + _i("π"), 12, ACCENT))
    body.append(eq(272, 62, f'{_i("y")} = sin {_i("x")}', 11, SUB))
    return titled("周期", body, "同じ形がくり返すまでの幅")

def fig_加法定理():
    body = [card(20, 46, 280, 100)]
    a, b = _i("α"), _i("β")
    body.append(eq(160, 86,
                   f"sin({a} + {b}) = sin{a} cos{b} + cos{a} sin{b}", 13.5))
    body.append(eq(160, 122,
                   f"cos({a} + {b}) = cos{a} cos{b} &#8722; sin{a} sin{b}", 13.5))
    return titled("加法定理", body, "差のときは + と &#8722; を入れかえる")

def fig_二倍角の公式():
    body = [card(20, 46, 280, 104)]
    th = _i("θ")
    body.append(eq(160, 92, f"sin2{th} = 2 sin{th} cos{th}", 18))
    body.append(eq(160, 132, f"cos2{th} = cos²{th} &#8722; sin²{th}", 14))
    return titled("二倍角の公式", body, "加法定理で β = α とおくと得られる")

def fig_半角の公式():
    body = [card(20, 46, 280, 116)]
    th = _i("θ")
    # sin²(θ/2) = (1 − cosθ)/2
    body.append(eq(128, 100, f"sin²({th}/2)", 15, INK, "end"))
    body.append(eq(142, 100, "=", 15))
    body.append(eq(205, 88, f"1 &#8722; cos{th}", 13.5))
    body.append(line(176, 95, 234, 95, INK, 1.2))
    body.append(eq(205, 112, "2", 13.5))
    # cos²(θ/2) = (1 + cosθ)/2
    body.append(eq(128, 138, f"cos²({th}/2)", 15, INK, "end"))
    body.append(eq(142, 138, "=", 15))
    body.append(eq(205, 126, f"1 + cos{th}", 13.5))
    body.append(line(176, 133, 234, 133, INK, 1.2))
    body.append(eq(205, 150, "2", 13.5))
    return titled("半角の公式", body, "2乗を1次の式に直せる(次数下げ)")

def fig_三角関数の合成():
    a, b, r, th, al = _i("a"), _i("b"), _i("r"), _i("θ"), _i("α")
    body = [eq(160, 50, f"{a} sin{th} + {b} cos{th} = {r} sin({th} + {al})", 13.5)]

    O, A, B = (66, 152), (166, 152), (166, 92)   # a=100, b=60, r=116.6
    body.append(poly([O, A, B], INK, 1.6, FILL))
    body.append(line(O[0], O[1], B[0], B[1], ACCENT, 2.0))
    body.append(path("M154,152 L154,140 L166,140", SUB, 1.1))
    body.append(arc(O[0], O[1], 28, 0, 30.96, INK, 1.2))
    body.append(mt(99, 145, "α", 11))
    body.append(mt(116, 166, "a", 12))
    body.append(mt(178, 126, "b", 12))
    body.append(mt(107, 114, "r", 12, ACCENT))

    body.append(eq(214, 112, f"{r} =", 12, INK, "start"))
    body.append(path("M240,108 L243.5,114 L247.5,96 L284,96", INK, 1.2))
    body.append(eq(266, 111, f"{a}² + {b}²", 12))
    body.append(eq(214, 138, f"tan{al} = {b} / {a}", 12, INK, "start"))
    return titled("三角関数の合成", body, "最大値は r、最小値は &#8722;r")

def fig_累乗根():
    body = [card(20, 50, 280, 100)]
    body.append(mt(70, 104, "x", 18))
    body.append(mt(81, 95, "n", 11))
    body.append(eq(98, 104, "=", 16))
    body.append(mt(116, 104, "a", 18))
    body.append(eq(146, 104, "⇔", 15, SUB))
    body.append(mt(178, 104, "x", 18))
    body.append(eq(193, 104, "=", 16))
    body.append(mt(210, 90, "n", 10))
    body.append(path("M214,98 L218,105 L223,84 L258,84", INK, 1.4))
    body.append(mt(240, 102, "a", 16))
    return titled("累乗根", body, "2³ = 8 だから 8 の3乗根は 2")

def fig_底の変換公式():
    def logexpr(x, y, base, argv, size, fill=INK):
        w = size * 1.30
        parts = [t(x, y, "log", size, fill, "start", MATHFONT),
                 mt(x + w + 1, y + size * 0.26, base, size * 0.66, fill, "start"),
                 mt(x + w + 1 + size * 0.36, y, argv, size, fill, "start")]
        return parts, x + w + 1 + size * 0.36 + size * 0.55

    body = [card(20, 52, 280, 104)]
    left, _ = logexpr(108, 109, "a", "b", 15)
    body += left
    body.append(eq(154, 109, "=", 15))
    num, _ = logexpr(176, 98, "c", "b", 13)
    den, _ = logexpr(176, 126, "c", "a", 13)
    body += num + den
    body.append(line(171, 104, 212, 104, INK, 1.2))
    return titled("底の変換公式", body, "どんな底でも同じ底にそろえられる")

def fig_ベクトル():
    body = [arrow(70, 150, 230, 70, ACCENT, 2.4)]
    body.append(dot(70, 150, 3.0, ACCENT))
    body.append(mt(60, 160, "A", 11))
    body.append(mt(240, 64, "B", 11))
    # 長さ = 大きさ
    body.append(arrow(76.7, 163.4, 236.7, 83.4, SUB, 1.1, head="both"))
    body.append(t(150, 142, "大きさ", 9.5, SUB))
    body.append(t(266, 88, "向き", 9.5, SUB))
    body.append(mt(140, 96, "a", 13))
    return titled("ベクトル", body, "大きさと向きが同じならどこにあっても同じ")

def fig_位置ベクトル():
    O, A, B = (70, 158), (146, 72), (258, 108)
    body = [dot(*O, 3.0), mt(60, 168, "O", 11)]
    body.append(arrow(O[0], O[1], A[0], A[1], INK, 1.8))
    body.append(arrow(O[0], O[1], B[0], B[1], INK, 1.8))
    body.append(dot(*A, 2.8))
    body.append(dot(*B, 2.8))
    body.append(mt(140, 64, "A", 11))
    body.append(mt(268, 104, "B", 11))
    body.append(mt(97, 110, "a", 12))
    body.append(mt(167, 148, "b", 12))
    body.append(arrow(A[0], A[1], B[0], B[1], ACCENT, 1.6))
    body.append(eq(196, 80, f'{_i("b")} &#8722; {_i("a")}', 11.5, ACCENT))
    return titled("位置ベクトル", body, "基準の点 O からの矢で点の位置を表す")

def fig_成分表示():
    ox, oy, u = 80, 155, 30.0
    body = axes(ox, oy, -20, 200, -16, 110)
    for i in range(1, 6):
        body.append(line(ox + u * i, oy - 3, ox + u * i, oy + 3, SUB, 1.0))
    for i in range(1, 4):
        body.append(line(ox - 3, oy - u * i, ox + 3, oy - u * i, SUB, 1.0))

    px, py = ox + 4 * u, oy - 3 * u        # (4, 3)
    body.append(line(px, py, px, oy, SUB, 1.1, dash="4 4"))
    body.append(line(px, py, ox, py, SUB, 1.1, dash="4 4"))
    body.append(arrow(ox, oy, px, py, ACCENT, 2.2))
    body.append(dot(px, py, 2.8, ACCENT))
    body.append(mt(px, oy + 16, "4", 10.5, SUB))
    body.append(mt(ox - 12, py + 4, "3", 10.5, SUB))
    body.append(eq(250, 54, f'{_i("a")} = (4, 3)', 13.5))
    return titled("成分表示", body, "x 方向・y 方向の数の組で表す")

def fig_内積():
    a, b, th = _i("a"), _i("b"), _i("θ")
    body = [eq(160, 50, f"{a} · {b} = |{a}| |{b}| cos{th}", 14)]
    O = (64, 152)
    body.append(arrow(O[0], O[1], 250, 152, INK, 2.0))
    body.append(arrow(O[0], O[1], 176, 74, INK, 2.0))
    body.append(dot(*O, 3.0))
    body.append(arc(O[0], O[1], 36, 0, 34.85, ACCENT, 1.4))
    body.append(mt(112, 143, "θ", 12, ACCENT))
    body.append(mt(256, 156, "a", 12))
    body.append(mt(170, 66, "b", 12))
    # b の a 方向への影
    body.append(line(176, 74, 176, 152, SUB, 1.1, dash="4 4"))
    body.append(path("M164,152 L164,140 L176,140", SUB, 1.1))
    body.append(arrow(64, 168, 176, 168, SUB, 1.1, head="both"))
    body.append(eq(120, 180, f"|{b}| cos{th}", 10.5, SUB))
    return titled("内積", body)

def fig_偏角():
    ox, oy = 140, 132
    body = axes(ox, oy, -100, 130, -34, 80, xlab=None, ylab=None)
    body.append(t(268, 146, "実軸", 9, SUB))
    body.append(t(115, 58, "虚軸", 9, SUB))

    r, ang = 80.0, 52.0
    zx = ox + r * math.cos(math.radians(ang))
    zy = oy - r * math.sin(math.radians(ang))
    body.append(arrow(ox, oy, zx, zy, INK, 2.0))
    body.append(dot(zx, zy, 3.0, INK))
    body.append(mt(zx + 9, zy - 6, "z", 12))
    body.append(mt(153, 96, "r", 11))
    body.append(arc(ox, oy, 32, 0, ang, ACCENT, 1.4))
    body.append(mt(181, 118, "θ", 12, ACCENT))
    return titled("偏角", body, "極形式 z = r(cos θ + i sin θ)")

def fig_ドモアブルの定理():
    th = _i("θ")
    n = _i("n")
    body = [eq(72, 48, f"(cos{th} + {_i('i')} sin{th})", 13.5, INK, "start"),
            mt(152, 42, "n", 10),
            eq(157, 48, f" = cos{n}{th} + {_i('i')} sin{n}{th}", 13.5, INK, "start")]

    ox, oy, r = 150, 126, 56.0
    body.append(circle(ox, oy, r, SUB, 1.1, dash="4 4"))
    body.append(arrow(56, oy, 274, oy, SUB, 1.2))
    body.append(arrow(ox, 182, ox, 62, SUB, 1.2))
    body.append(mt(ox - 8, oy + 12, "O", 10, SUB))

    for ang, col, lab, lx, ly in ((32, INK, "z", 208, 94), (64, ACCENT, "z²", 182, 64)):
        px = ox + r * math.cos(math.radians(ang))
        py = oy - r * math.sin(math.radians(ang))
        body.append(arrow(ox, oy, px, py, col, 2.0))
        body.append(dot(px, py, 3.0, col))
        body.append(mt(lx, ly, lab, 12, col))
    body.append(arc(ox, oy, 26, 0, 32, INK, 1.2))
    body.append(mt(185, 121, "θ", 10.5))
    body.append(arc(ox, oy, 42, 0, 64, ACCENT, 1.2))
    body.append(mt(188, 91, "2θ", 10, ACCENT))
    return titled("ド・モアブルの定理", body, "n 乗すると偏角は n 倍になる")

def fig_瞬間の速さ():
    ox, oy = 62, 162
    body = [arrow(48, oy, 300, oy, SUB, 1.2), arrow(ox, 176, ox, 50, SUB, 1.2)]
    body.append(t(290, 176, "時間", 9, SUB))
    body.append(t(78, 48, "位置", 9, SUB))

    def X(u):
        return ox + 224 * u

    def Y(u):
        return oy - 104 * u * u

    body.append(polyline([(X(i / 50), Y(i / 50)) for i in range(51)], INK, 1.9))

    # 2点の間 → 平均の速さ
    u1, u2 = 0.15, 0.5
    body.append(line(X(u1), Y(u1), X(u2), Y(u2), SUB, 1.6, dash="5 4"))
    body.append(dot(X(u1), Y(u1), 2.8, SUB))
    body.append(dot(X(u2), Y(u2), 2.8, SUB))
    body.append(t(122, 130, "平均の速さ", 9.5, SUB))
    body.append(line(128, 134, 136, 145, SUB, 0.9))

    # 1点だけ → その瞬間
    u0 = 0.82
    x0, y0 = X(u0), Y(u0)
    s = 104 * 2 * u0 / 224.0
    body.append(line(x0 - 48, y0 + 48 * s, x0 + 48, y0 - 48 * s, ACCENT, 1.8))
    body.append(dot(x0, y0, 3.2, ACCENT))
    body.append(t(200, 66, "この点での速さ", 9.5, ACCENT))
    body.append(line(216, 70, 240, 88, ACCENT, 0.9))
    return titled("瞬間の速さ", body)

def fig_和算():
    body = []
    # 算額(奉納される絵馬形の額)
    body.append(poly([(24, 60), (100, 42), (176, 60)], INK, 1.5, FILL))
    body.append(rect(30, 60, 140, 102, INK, 1.4, "#ffffff"))
    A, B, C = (66, 142), (126, 142), (96, 90)
    body.append(poly([A, B, C], INK, 1.4))
    body.append(circle(96.0, 124.7, 17.3, ACCENT, 1.4))
    for x in (142, 151, 160):
        body.append(line(x, 72, x, 150, SUB, 1.1, dash="3 5"))
    body.append(t(100, 174, "算額", 9, SUB))

    # そろばん
    body.append(rect(190, 66, 110, 86, INK, 1.4, "#ffffff"))
    body.append(line(190, 88, 300, 88, INK, 1.3))
    for i in range(5):
        rx = 190 + 110 * (i + 0.5) / 5
        body.append(line(rx, 66, rx, 152, SUB, 1.0))
        for cy in (78, 112, 122, 132, 142):
            body.append(poly([(rx - 7, cy), (rx, cy - 4), (rx + 7, cy),
                              (rx, cy + 4)], INK, 1.0, FILL2))
    body.append(t(245, 174, "そろばん", 9, SUB))
    return titled("和算", body)

def fig_曲尺():
    pts = [(60, 60), (76, 60), (76, 144), (270, 144), (270, 160), (60, 160)]
    body = [poly(pts, INK, 1.6, FILL)]
    x = 86
    while x <= 266:
        long_ = (x - 66) % 50 == 0
        body.append(line(x, 160, x, 148 if long_ else 153, SUB, 1.0))
        x += 10
    y = 134
    while y >= 70:
        long_ = (144 - y) % 50 == 0
        body.append(line(60, y, 72 if long_ else 67, y, SUB, 1.0))
        y -= 10
    body.append(path("M78,130 L92,130 L92,144", ACCENT, 1.6))
    body.append(t(122, 122, "直角", 9.5, ACCENT))
    return titled("曲尺", body, "長さをはかると同時に直角を写せる")

def fig_ディオファントス():
    body = [path("M56,166 L56,84 Q56,54 160,54 Q264,54 264,84 L264,166 Z",
                 INK, 1.6, FILL)]
    body.append(rect(46, 166, 228, 8, INK, 1.4, FILL))
    body.append(t(160, 84, "生涯を表す式", 9.5, SUB))
    body.append(line(80, 94, 240, 94, SUB, 0.9))
    x = _i("x")
    body.append(eq(160, 122,
                   f"{x}/6 + {x}/12 + {x}/7 + 5 + {x}/2 + 4 = {x}", 12))
    body.append(eq(160, 148, f"{x} = 84", 14, ACCENT))
    return titled("ディオファントス", body, "墓碑の問題を解くと生涯の長さが出る")

def fig_立体模型():
    body = []
    # 展開図(立方体の展開図)
    s = 26
    for x, y in ((60, 58), (34, 84), (60, 84), (86, 84), (112, 84), (60, 110)):
        body.append(rect(x, y, s, s, INK, 1.3, FILL))
    body.append(t(86, 160, "展開図", 9.5, SUB))

    body.append(arrow(146, 100, 180, 100, ACCENT, 1.5))
    body.append(t(163, 90, "組み立て", 8.5, SUB))

    # 組み上がった立方体
    body.append(line(222, 114, 278, 114, SUB, 1.2, dash="4 3"))
    body.append(line(222, 58, 222, 114, SUB, 1.2, dash="4 3"))
    body.append(line(196, 140, 222, 114, SUB, 1.2, dash="4 3"))
    body.append(line(222, 58, 278, 58, INK, 1.5))
    body.append(line(278, 58, 278, 114, INK, 1.5))
    body.append(line(196, 84, 222, 58, INK, 1.5))
    body.append(line(252, 84, 278, 58, INK, 1.5))
    body.append(line(252, 140, 278, 114, INK, 1.5))
    body.append(rect(196, 84, 56, 56, INK, 1.6, FILL))
    body.append(t(237, 160, "組み立てた立体", 9.5, SUB))
    return titled("立体模型", body, "切り口や体積を確かめるのに使う")

# ---- 語と作図関数の対応 -------------------------------------------

FIGURES = {
    "平方完成": fig_平方完成,
    "判別式": fig_判別式,
    "最大値": fig_最大値,
    "最小値": fig_最小値,
    "命題": fig_命題,
    "必要条件": fig_必要条件,
    "十分条件": fig_十分条件,
    "必要十分条件": fig_必要十分条件,
    "対偶": fig_対偶,
    "背理法": fig_背理法,
    "恒等式": fig_恒等式,
    "対称式": fig_対称式,
    "剰余の定理": fig_剰余の定理,
    "解と係数の関係": fig_解と係数の関係,
    "互いに素": fig_互いに素,
    "メネラウスの定理": fig_メネラウスの定理,
    "方べきの定理": fig_方べきの定理,
    "内分点": fig_内分点,
    "外分点": fig_外分点,
    "点と直線の距離": fig_点と直線の距離,
    "五心": fig_五心,
    "内接する四角形": fig_内接する四角形,
    "合同条件": fig_合同条件,
    "面積比": fig_面積比,
    "体積比": fig_体積比,
    "立体の切断": fig_立体の切断,
    "球の体積": fig_球の体積,
    "面積図": fig_面積図,
    "軌跡": fig_軌跡,
    "領域": fig_領域,
    "直線の方程式": fig_直線の方程式,
    "準線": fig_準線,
    "極方程式": fig_極方程式,
    "順列": fig_順列,
    "組合せ": fig_組合せ,
    "円順列": fig_円順列,
    "重複順列": fig_重複順列,
    "事象": fig_事象,
    "余事象": fig_余事象,
    "排反": fig_排反,
    "独立試行": fig_独立試行,
    "反復試行": fig_反復試行,
    "乗法定理": fig_乗法定理,
    "期待値": fig_期待値,
    "分散": fig_分散,
    "共分散": fig_共分散,
    "第一四分位数": fig_第一四分位数,
    "仮説検定": fig_仮説検定,
    "標本平均": fig_標本平均,
    "母平均": fig_母平均,
    "区間推定": fig_区間推定,
    "降水確率": fig_降水確率,
    "選挙速報": fig_選挙速報,
    "平均変化率": fig_平均変化率,
    "接線の方程式": fig_接線の方程式,
    "増減表": fig_増減表,
    "第二次導関数": fig_第二次導関数,
    "不定積分": fig_不定積分,
    "積分定数": fig_積分定数,
    "原始関数": fig_原始関数,
    "回転体の体積": fig_回転体の体積,
    "曲線の長さ": fig_曲線の長さ,
    "積の微分法": fig_積の微分法,
    "商の微分法": fig_商の微分法,
    "対数微分法": fig_対数微分法,
    "置換積分法": fig_置換積分法,
    "部分積分法": fig_部分積分法,
    "数列": fig_数列,
    "公差": fig_公差,
    "初項": fig_初項,
    "一般項": fig_一般項,
    "シグマ記号": fig_シグマ記号,
    "階差数列": fig_階差数列,
    "漸化式": fig_漸化式,
    "収束": fig_収束,
    "発散": fig_発散,
    "無限等比級数": fig_無限等比級数,
    "周期": fig_周期,
    "加法定理": fig_加法定理,
    "二倍角の公式": fig_二倍角の公式,
    "半角の公式": fig_半角の公式,
    "三角関数の合成": fig_三角関数の合成,
    "累乗根": fig_累乗根,
    "底の変換公式": fig_底の変換公式,
    "ベクトル": fig_ベクトル,
    "位置ベクトル": fig_位置ベクトル,
    "成分表示": fig_成分表示,
    "内積": fig_内積,
    "偏角": fig_偏角,
    "ド・モアブルの定理": fig_ドモアブルの定理,
    "瞬間の速さ": fig_瞬間の速さ,
    "和算": fig_和算,
    "曲尺": fig_曲尺,
    "ディオファントス": fig_ディオファントス,
    "立体模型": fig_立体模型,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="SVGの出力先ディレクトリ")
    a = ap.parse_args()
    d = Path(a.out)
    d.mkdir(parents=True, exist_ok=True)
    for word, fn in FIGURES.items():
        (d / f"{key(word)}.svg").write_text(fn(), encoding="utf-8")
    print(f"{len(FIGURES)}枚を書き出した -> {d}")


if __name__ == "__main__":
    main()
