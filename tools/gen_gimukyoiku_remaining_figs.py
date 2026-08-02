#!/usr/bin/env python3
"""残存SD 69語を正確な教材SVGとして描く。

国語14語・音楽21語・数学34語。生成AIは使わず、既存の数学作図基盤と同じ
320x200の自己完結SVGをRelease配布用に生成する。
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

try:
    from . import gen_gimukyoiku_math_figs as g
except ImportError:
    import gen_gimukyoiku_math_figs as g

FIGURES: dict[str, callable] = {}


def register(word):
    def deco(fn):
        FIGURES[word] = fn
        return fn
    return deco


def box_label(x, y, w, h, text, *, fill="#ffffff", stroke=g.SUB, size=11, color=g.INK):
    return [g.rect(x, y, w, h, stroke, 1.2, fill, rx=6),
            g.t(x + w / 2, y + h / 2 + size * 0.35, text, size, color)]


def staff(y=112, x1=34, x2=286, gap=11):
    return [g.line(x1, y + i * gap, x2, y + i * gap, g.SUB, 1.0) for i in range(5)]


def note(x, y, *, stem=True, r=5.0, fill=g.INK, open_=False, up=True):
    body = [f'<ellipse cx="{x}" cy="{y}" rx="{r + 1.2}" ry="{r}" fill="{g.BG if open_ else fill}" stroke="{fill}" stroke-width="1.4" transform="rotate(-18 {x} {y})"/>']
    if stem:
        if up:
            body.append(g.line(x + r, y, x + r, y - 34, fill, 1.5))
        else:
            body.append(g.line(x - r, y, x - r, y + 34, fill, 1.5))
    return body


def arc_path(x1, y1, x2, y2, rise, *, stroke=g.INK, width=1.5):
    return g.path(f"M{x1},{y1} Q{(x1+x2)/2},{min(y1,y2)-rise} {x2},{y2}", stroke, width)


def poem_grid(word, cols, rows, note_text):
    cell = min(14, 150 / cols, 112 / rows)
    total_w, total_h = cols * cell, rows * cell
    x0, y0 = (320 - total_w) / 2, 42
    body = []
    for r in range(rows):
        for c in range(cols):
            body.append(g.rect(x0 + c * cell, y0 + r * cell, cell, cell, g.SUB, 0.8,
                               g.FILL2 if r % 2 else "#ffffff"))
    body += [g.t(34, 86, f"{cols}字", 11, g.ACCENT),
             g.t(286, 86, f"{rows}句", 11, g.ACCENT)]
    return g.titled(word, body, note_text)


# ---- 国語14語 ---------------------------------------------------------------

@register("七言律詩")
def fig_七言律詩():
    return poem_grid("七言律詩", 7, 8, "一行7字 × 8句（偶数句を中心に押韻）")


@register("五言絶句")
def fig_五言絶句():
    return poem_grid("五言絶句", 5, 4, "一行5字 × 4句の漢詩")


@register("五段活用")
def fig_五段活用():
    xs = [58, 108, 158, 208, 258]
    body = [g.t(160, 43, "「書く」の語尾", 10, g.SUB)]
    for x, vowel, kana in zip(xs, "aiueo", "かきくけこ", strict=True):
        body += box_label(x - 20, 62, 40, 42, kana, fill=g.FILL if vowel != "u" else g.FILL2,
                          size=18, color=g.ACCENT if vowel == "u" else g.INK)
        body.append(g.t(x, 119, f"{vowel}段", 9, g.SUB))
    body += [g.t(160, 144, "書かない・書きます・書く・書けば・書こう", 10.5)]
    return g.titled("五段活用", body, "語尾が五つの母音の段に変化する")


@register("下一段活用")
def fig_下一段活用():
    forms = [("未然", "受け"), ("連用", "受け"), ("終止", "受ける"),
             ("連体", "受ける"), ("仮定", "受けれ"), ("命令", "受けろ")]
    body = [g.t(160, 41, "「受ける」— エ段だけで活用", 10, g.SUB)]
    for i, (name, form) in enumerate(forms):
        x = 22 + (i % 3) * 98
        y = 55 + (i // 3) * 51
        body += box_label(x, y, 88, 34, form, fill="#ffffff", size=13)
        body.append(g.t(x + 44, y + 47, name, 8.5, g.SUB))
    body.append(g.t(160, 158, "受けない・受けます・受ける・受ければ", 10.5, g.ACCENT))
    return g.titled("下一段活用", body, "語幹の下につく語尾がエ段で変化する")


@register("未然形")
def fig_未然形():
    body = [g.t(160, 46, "まだ起きていないことにつなぐ形", 10, g.SUB)]
    examples = [("書か", "ない"), ("読ま", "ない"), ("食べ", "ない")]
    for i, (base, tail) in enumerate(examples):
        y = 72 + i * 36
        body += box_label(54, y - 20, 105, 30, base, fill=g.FILL2, size=14, color=g.ACCENT)
        body += box_label(161, y - 20, 105, 30, tail, fill="#ffffff", size=14)
    return g.titled("未然形", body, "「ない・う・よう」などが続く")


@register("接続助詞")
def fig_接続助詞():
    body = box_label(18, 58, 112, 38, "雨が降った", fill=g.FILL)
    body += box_label(139, 58, 42, 38, "が", fill=g.FILL2, size=15, color=g.ACCENT)
    body += box_label(190, 58, 112, 38, "試合をした", fill=g.FILL)
    body += [g.arrow(130, 77, 139, 77, g.SUB), g.arrow(181, 77, 190, 77, g.SUB),
             g.t(160, 127, "ので・けれど・ても・ながら", 12),
             g.t(160, 151, "前後の文節をつなぐ", 10, g.ACCENT)]
    return g.titled("接続助詞", body)


@register("文節")
def fig_文節():
    chunks = [("わたしは", 24, 82), ("学校へ", 116, 72), ("行きます", 198, 98)]
    body = []
    for text, x, w in chunks:
        body += box_label(x, 73, w, 42, text, fill=g.FILL)
    for x in (111, 193):
        body.append(g.line(x, 64, x, 128, g.ACCENT, 1.2, "4 3"))
        body.append(g.t(x, 144, "ね", 9, g.ACCENT))
    return g.titled("文節", body, "自然な区切りごとに「ね」を入れて確かめる")


@register("倒置法")
def fig_倒置法():
    body = [g.t(160, 48, "通常の語順", 9, g.SUB)]
    body += box_label(28, 58, 170, 34, "今日の夕焼けは", fill=g.FILL)
    body += box_label(207, 58, 84, 34, "美しい", fill=g.FILL2, color=g.ACCENT)
    body += [g.arrow(250, 101, 80, 122, g.ACCENT, 1.5), g.t(160, 116, "順序を入れ替える", 9, g.SUB)]
    body += box_label(28, 132, 84, 34, "美しい、", fill=g.FILL2, color=g.ACCENT)
    body += box_label(121, 132, 170, 34, "今日の夕焼けは。", fill=g.FILL)
    return g.titled("倒置法", body)


@register("反復法")
def fig_反復法():
    body = [g.t(160, 48, "同じ語句をくり返して強調", 10, g.SUB)]
    for i, word in enumerate(("走れ、", "走れ、", "ゴールまで。")):
        x, w = [(28, 72), (108, 72), (188, 104)][i]
        body += box_label(x, 82, w, 44, word, fill=g.FILL2 if i < 2 else g.FILL,
                          size=14, color=g.ACCENT if i < 2 else g.INK)
    body += [arc_path(42, 143, 148, 143, 25, stroke=g.ACCENT), g.t(95, 159, "反復", 9, g.ACCENT)]
    return g.titled("反復法", body)


@register("対句")
def fig_対句():
    body = [g.t(160, 44, "形の対応する二つの句", 10, g.SUB)]
    body += box_label(34, 60, 252, 40, "山 は 高く", fill=g.FILL)
    body += box_label(34, 112, 252, 40, "川 は 長い", fill=g.FILL2)
    for x in (90, 160, 230):
        body.append(g.line(x, 101, x, 111, g.ACCENT, 1.2))
    return g.titled("対句", body, "対応する構造を並べ、調子を整える")


@register("掛詞")
def fig_掛詞():
    body = box_label(114, 50, 92, 38, "まつ", fill=g.FILL2, size=17, color=g.ACCENT)
    body += [g.arrow(130, 91, 82, 119, g.SUB), g.arrow(190, 91, 238, 119, g.SUB)]
    body += box_label(28, 121, 108, 42, "松（植物）", fill=g.FILL)
    body += box_label(184, 121, 108, 42, "待つ（動作）", fill=g.FILL)
    return g.titled("掛詞", body, "同じ音に二つの意味を重ねる")


@register("枕詞")
def fig_枕詞():
    body = box_label(32, 70, 126, 48, "あしひきの", fill=g.FILL2, size=16, color=g.ACCENT)
    body += [g.arrow(162, 94, 202, 94, g.SUB, 1.5)]
    body += box_label(207, 70, 80, 48, "山", fill=g.FILL, size=20)
    body += [g.t(95, 141, "五音の決まった言葉", 9, g.SUB), g.t(247, 141, "特定の語", 9, g.SUB)]
    return g.titled("枕詞", body, "特定の語の前に置いて調子を整える")


@register("切れ字")
def fig_切れ字():
    body = [g.t(160, 47, "古池", 14), g.t(160, 78, "や", 19, g.ACCENT, weight="700"),
            g.line(72, 88, 248, 88, g.ACCENT, 1.5),
            g.t(160, 112, "蛙飛びこむ", 14), g.t(160, 139, "水の音", 14),
            g.t(270, 78, "切れ", 9, g.ACCENT)]
    return g.titled("切れ字", body, "「や・かな・けり」などで句を切り、余情を生む")


@register("類義語")
def fig_類義語():
    body = box_label(28, 66, 108, 48, "美しい", fill=g.FILL)
    body += [g.t(160, 98, "≒", 22, g.ACCENT)]
    body += box_label(184, 66, 108, 48, "きれい", fill=g.FILL)
    body += [g.t(160, 142, "意味がよく似ている", 11, g.SUB)]
    return g.titled("類義語", body, "文脈によって使い分ける")


# ---- 音楽21語 ---------------------------------------------------------------

def dynamics(word, mark, meaning, strength=1):
    body = [g.t(160, 105, mark, 64 if len(mark) == 1 else 54, g.INK, font=g.MATHFONT,
                weight="700", style="italic"), g.t(160, 148, meaning, 12, g.ACCENT)]
    for i in range(strength):
        body.append(arc_path(82 - i * 8, 107, 238 + i * 8, 107, 34 + i * 7, stroke=g.SUB, width=1.0))
    return g.titled(word, body)


@register("ピアニシモ")
def fig_pp(): return dynamics("ピアニシモ", "pp", "とても弱く", 1)

@register("フォルテ")
def fig_f(): return dynamics("フォルテ", "f", "強く", 2)

@register("フォルテシモ")
def fig_ff(): return dynamics("フォルテシモ", "ff", "とても強く", 3)


@register("クレッシェンド")
def fig_cresc():
    b = staff(119) + [g.line(62, 98, 260, 68, g.ACCENT, 2.2), g.line(62, 98, 260, 128, g.ACCENT, 2.2),
                      g.t(160, 157, "だんだん強く", 11, g.ACCENT)]
    return g.titled("クレッシェンド", b)


def diminuendo(word):
    b = staff(119) + [g.line(60, 68, 258, 98, g.ACCENT, 2.2), g.line(60, 128, 258, 98, g.ACCENT, 2.2),
                      g.t(160, 157, "だんだん弱く", 11, g.ACCENT)]
    return g.titled(word, b)

@register("ディミヌエンド")
def fig_dim(): return diminuendo("ディミヌエンド")

@register("デクレッシェンド")
def fig_decresc(): return diminuendo("デクレッシェンド")


@register("アッチェレランド")
def fig_accel():
    xs = [48, 91, 127, 157, 182, 203, 221, 237, 251, 264]
    b = staff(108)
    for x in xs: b += note(x, 130, r=4.4)
    b += [g.arrow(46, 66, 274, 66, g.ACCENT, 1.6), g.t(160, 55, "だんだん速く", 10.5, g.ACCENT),
          g.t(160, 172, "音の間隔が次第に短くなる", 9.5, g.SUB)]
    return g.titled("アッチェレランド", b)


@register("スタッカート")
def fig_staccato():
    b = staff(105)
    for x, y in zip((68, 128, 188, 248), (127, 116, 105, 116), strict=True):
        b += note(x, y)
        b.append(g.dot(x, y + 13, 2.4, g.ACCENT))
    b.append(g.t(160, 172, "一音ずつ短く切る", 10.5, g.ACCENT))
    return g.titled("スタッカート", b)


@register("タイ")
def fig_tie():
    b = staff(105)
    b += note(112, 127) + note(204, 127)
    b += [arc_path(105, 142, 211, 142, -4, stroke=g.ACCENT, width=2.2),
          g.t(160, 171, "同じ高さの二音をつなげて一音に", 9.8, g.ACCENT)]
    return g.titled("タイ", b)


@register("フェルマータ")
def fig_fermata():
    b = staff(111) + note(160, 133, open_=True)
    b += [g.path("M126,84 Q160,50 194,84", g.ACCENT, 2.4), g.dot(160, 78, 4.2, g.ACCENT),
          g.t(160, 171, "ほどよく延ばす", 10.5, g.ACCENT)]
    return g.titled("フェルマータ", b)


@register("三連符")
def fig_triplet():
    b = staff(112)
    for x, y in ((115, 134), (160, 123), (205, 112)): b += note(x, y)
    b += [g.line(121, 100, 211, 78, g.INK, 3.0), g.path("M108,67 L108,58 L212,58 L212,67", g.ACCENT, 1.6),
          g.t(160, 54, "3", 13, g.ACCENT), g.t(160, 173, "一拍を三等分", 10.5, g.ACCENT)]
    return g.titled("三連符", b)


@register("反復記号")
def fig_repeat():
    b = staff(104)
    b += [g.line(133, 90, 133, 158, g.INK, 1.5), g.line(140, 90, 140, 158, g.INK, 4.0),
          g.dot(153, 115, 3.5), g.dot(153, 137, 3.5),
          g.line(180, 90, 180, 158, g.INK, 4.0), g.line(187, 90, 187, 158, g.INK, 1.5),
          g.dot(167, 115, 3.5), g.dot(167, 137, 3.5),
          g.arrow(190, 70, 132, 70, g.ACCENT, 1.5), g.t(160, 60, "くり返す", 10, g.ACCENT)]
    return g.titled("反復記号", b)


def segno(x=160, y=102):
    return [g.path(f"M{x+25},{y-30} C{x-28},{y-45} {x-30},{y-3} {x+2},{y+2} C{x+34},{y+8} {x+27},{y+42} {x-25},{y+28}", g.INK, 3.0),
            g.line(x-35, y+35, x+35, y-35, g.INK, 2.2),
            g.dot(x-25, y-22, 3.2), g.dot(x+25, y+22, 3.2)]


@register("ダカーポ")
def fig_dc():
    b = staff(116) + [g.t(246, 82, "D.C.", 19, g.INK, font=g.MATHFONT, weight="700"),
                      g.arrow(260, 64, 55, 64, g.ACCENT, 1.7), g.t(160, 52, "最初へ戻る", 10, g.ACCENT),
                      g.line(55, 105, 55, 159, g.INK, 3.0)]
    return g.titled("ダカーポ", b)


@register("ダルセーニョ")
def fig_ds():
    b = segno(92, 112)
    b += [g.t(226, 96, "D.S.", 21, g.INK, font=g.MATHFONT, weight="700"),
          g.arrow(235, 111, 130, 111, g.ACCENT, 1.7), g.t(222, 140, "この記号へ戻る", 10, g.ACCENT)]
    return g.titled("ダルセーニョ", b)


def metronome(word, pendulum_x, meaning):
    b = [g.poly([(108, 156), (132, 58), (188, 58), (212, 156)], g.INK, 1.5, g.FILL),
         g.rect(101, 156, 118, 10, g.INK, 1.3, g.FILL2),
         g.line(160, 145, pendulum_x, 72, g.ACCENT, 2.2), g.dot(pendulum_x, 72, 4.2, g.ACCENT),
         g.t(160, 181, meaning, 10.5, g.ACCENT)]
    return g.titled(word, b)

@register("モデラート")
def fig_moderato(): return metronome("モデラート", 160, "中くらいの速さで")

@register("ラルゴ")
def fig_largo(): return metronome("ラルゴ", 125, "幅広く、ゆるやかに")


@register("ソナタ形式")
def fig_sonata():
    body = []
    blocks = [(20, "提示部", "A  B", g.FILL), (118, "展開部", "変化・発展", g.FILL2), (216, "再現部", "A  B", g.FILL)]
    for x, title, sub, fill in blocks:
        body += box_label(x, 65, 84, 72, title, fill=fill, size=13)
        body.append(g.t(x + 42, 122, sub, 9.5, g.ACCENT if x == 118 else g.SUB))
    body += [g.arrow(105, 101, 116, 101, g.SUB), g.arrow(203, 101, 214, 101, g.SUB),
             g.t(160, 158, "主題が提示され、展開し、戻ってくる", 9.5, g.SUB)]
    return g.titled("ソナタ形式", body)


def scale_figure(word, names, note_text):
    b = staff(102)
    ys = [146, 140, 134, 128, 122, 116, 110, 104]
    xs = [44 + i * 33 for i in range(8)]
    for x, y, name in zip(xs, ys, names, strict=True):
        b += note(x, y, stem=False, r=4.2)
        b.append(g.t(x, 166, name, 9.5, g.ACCENT if x == xs[0] else g.INK))
    b.append(g.arrow(42, 78, 278, 78, g.SUB, 1.2))
    return g.titled(word, b, note_text)

@register("長調")
def fig_major(): return scale_figure("長調", ["ド", "レ", "ミ", "ファ", "ソ", "ラ", "シ", "ド"], "明るい響きの音階（例：ハ長調）")

@register("短調")
def fig_minor(): return scale_figure("短調", ["ラ", "シ", "ド", "レ", "ミ", "ファ", "ソ", "ラ"], "短調の音階（例：イ短調）")

@register("階名")
def fig_solfege(): return scale_figure("階名", ["ド", "レ", "ミ", "ファ", "ソ", "ラ", "シ", "ド"], "音階の中の位置をド・レ・ミで表す")

@register("音階")
def fig_scale(): return scale_figure("音階", ["1","2","3","4","5","6","7","8"], "音を高さの順に並べたもの")


# ---- 数学34語 ---------------------------------------------------------------

@register("さくらんぼ計算")
def fig_cherry():
    b = [g.t(76, 72, "8 + 5", 18), g.arrow(111, 74, 142, 74, g.SUB), g.t(178, 72, "8 + 2 + 3", 16)]
    b += [g.circle(190, 108, 18, g.ACCENT, 1.5, g.FILL2), g.t(190, 114, "5", 15, g.ACCENT),
          g.line(180, 124, 158, 145, g.SUB, 1.3), g.line(200, 124, 222, 145, g.SUB, 1.3),
          g.circle(150, 154, 16, g.INK, 1.3, g.FILL), g.circle(230, 154, 16, g.INK, 1.3, g.FILL),
          g.t(150, 159, "2", 14), g.t(230, 159, "3", 14), g.t(62, 145, "8 + 2 = 10", 12, g.ACCENT),
          g.t(62, 166, "10 + 3 = 13", 12)]
    return g.titled("さくらんぼ計算", b, "一方の数を分けて10をつくる")


@register("ねじれの位置")
def fig_skew():
    A,B,C,D=(56,76),(166,76),(166,150),(56,150); E,F,G,H=(105,42),(215,42),(215,116),(105,116)
    b=[g.poly([A,B,C,D],g.SUB,1.2,"none"),g.poly([E,F,G,H],g.SUB,1.2,"none")]
    for p,q in ((A,E),(B,F),(C,G),(D,H)): b.append(g.line(*p,*q,g.SUB,1.1))
    b += [g.line(*D,*C,g.ACCENT,3.0), g.line(*F,*G,"#3d78b8",3.0),
          g.t(112,169,"辺①",9,g.ACCENT), g.t(234,80,"辺②",9,"#3d78b8")]
    return g.titled("ねじれの位置", b, "交わらず、平行でもない二直線（同一平面上にない）")


@register("もとにする量")
def fig_base_amount():
    b=[g.rect(38,70,240,34,g.INK,1.3,g.FILL),g.rect(38,70,144,34,"none",0,g.FILL2),
       g.t(110,92,"比べられる量 60",10,g.ACCENT),g.t(230,92,"",10),
       g.line(38,116,278,116,g.ACCENT,1.5),g.line(38,110,38,122,g.ACCENT,1.5),g.line(278,110,278,122,g.ACCENT,1.5),
       g.t(158,136,"もとにする量 100",11,g.ACCENT),g.t(160,160,"60 ÷ 0.6 = 100",13)]
    return g.titled("もとにする量",b,"比べられる量 ÷ 割合")


@register("代入")
def fig_substitute():
    b=box_label(30,61,76,42,"x = 3",fill=g.FILL2,size=15,color=g.ACCENT)
    b += [g.arrow(108,82,145,82,g.ACCENT,1.6)]
    b += box_label(150,55,140,54,"2x + 1",fill=g.FILL,size=17)
    b += [g.arrow(220,112,220,132,g.SUB,1.3),g.t(220,153,"2×3+1 = 7",16,g.ACCENT)]
    return g.titled("代入",b,"文字を数や式に置きかえる")


@register("作図")
def fig_construction():
    b=[g.line(62,141,258,141,g.INK,1.5),g.dot(112,141),g.dot(208,141),
       g.circle(112,141,70,g.SUB,1.0,"none","4 3"),g.circle(208,141,70,g.SUB,1.0,"none","4 3"),
       g.line(160,53,160,174,g.ACCENT,1.8),g.path("M153,141 L153,134 L160,134",g.ACCENT,1.2),
       g.t(112,160,"A",10),g.t(208,160,"B",10)]
    return g.titled("作図",b,"定規とコンパスで垂直二等分線をかく例")


def number_hops(word, step, common=None):
    x0,y=38,126; scale=17
    b=[g.arrow(x0,y,292,y,g.SUB,1.1)]
    for n in range(0,13):
        x=x0+n*scale;b += [g.line(x,y-5,x,y+5,g.SUB,1.0),g.t(x,y+20,str(n),8,g.SUB)]
    for n in range(0,13,step):
        x=x0+n*scale;b.append(g.dot(x,y,3.4,g.ACCENT));
        if n+step<=12:b.append(arc_path(x,y-7,x+step*scale,y-7,17,stroke=g.ACCENT,width=1.3))
    if common: b.append(g.t(160,57,common,11,g.ACCENT))
    return g.titled(word,b)

@register("倍数")
def fig_multiple(): return number_hops("倍数",3,"3の倍数：0, 3, 6, 9, 12 …")


@register("側面")
def fig_side_surface():
    b=[g.path("M45,73 Q85,51 125,73 L125,145 Q85,167 45,145 Z",g.INK,1.5,g.FILL2),
       g.path("M45,73 Q85,95 125,73 Q85,51 45,73",g.INK,1.2,"#ffffff"),
       g.path("M45,145 Q85,167 125,145",g.INK,1.2),g.arrow(139,109,178,109,g.ACCENT,1.5),
       g.rect(190,66,90,86,g.INK,1.5,g.FILL2),g.t(85,116,"側面",11,g.ACCENT),g.t(235,169,"開くと長方形",9,g.SUB)]
    return g.titled("側面",b,"立体の底面以外の面")


@register("公倍数")
def fig_common_multiple():
    b=[g.t(40,76,"3",11,g.ACCENT),g.t(40,137,"4",11,"#3d78b8")]
    for y,step,col in ((72,3,g.ACCENT),(133,4,"#3d78b8")):
        b.append(g.line(55,y,290,y,g.SUB,1.0))
        for n in range(0,13):
            x=58+n*18;b.append(g.line(x,y-3,x,y+3,g.SUB,.8))
            if n%step==0:b.append(g.dot(x,y,2.8,col))
    x=58+12*18;b += [g.line(x,53,x,151,g.ACCENT,1.3,"4 3"),g.t(x,45,"12",11,g.ACCENT)]
    return g.titled("公倍数",b,"3と4に共通する倍数：12, 24, …")


@register("公約数")
def fig_common_divisor():
    b=box_label(24,56,272,36,"12の約数：1, 2, 3, 4, 6, 12",fill=g.FILL)
    b+=box_label(24,101,272,36,"18の約数：1, 2, 3, 6, 9, 18",fill=g.FILL2)
    b += [g.t(160,160,"共通：1, 2, 3, 6",13,g.ACCENT)]
    return g.titled("公約数",b)


def speed_card(word, distance, time, unit, answer):
    b=[g.arrow(48,93,272,93,g.ACCENT,2.0),g.line(48,83,48,103,g.INK,1.3),g.line(272,83,272,103,g.INK,1.3),
       g.t(160,78,distance,11,g.SUB),g.t(160,124,f"{distance} ÷ {time}",14),g.t(160,151,f"= {answer} {unit}",16,g.ACCENT)]
    return g.titled(word,b)

@register("分速")
def fig_per_minute(): return speed_card("分速","240 m","3分","m/分","80")

@register("秒速")
def fig_per_second(): return speed_card("秒速","100 m","20秒","m/秒","5")


@register("割合")
def fig_ratio():
    b=[g.rect(36,70,250,42,g.INK,1.3,"#ffffff"),g.rect(36,70,100,42,"none",0,g.FILL2),
       g.t(86,96,"40",12,g.ACCENT),g.t(211,96,"100",12,g.SUB),g.t(160,139,"40 ÷ 100 = 0.4",15),
       g.t(160,162,"割合 = 比べられる量 ÷ もとにする量",9.5,g.ACCENT)]
    return g.titled("割合",b)


@register("単位換算")
def fig_conversion():
    b=box_label(24,59,112,46,"1 m",fill=g.FILL,size=18)
    b += [g.arrow(139,82,181,82,g.ACCENT,1.5,head="both")]
    b += box_label(184,59,112,46,"100 cm",fill=g.FILL2,size=17,color=g.ACCENT)
    b += box_label(24,119,112,40,"1 kg",fill=g.FILL,size=16)
    b += [g.arrow(139,139,181,139,g.ACCENT,1.5,head="both")]
    b += box_label(184,119,112,40,"1000 g",fill=g.FILL2,size=16,color=g.ACCENT)
    return g.titled("単位換算",b,"同じ量を別の単位で表す")


def triangle(cx,cy,s,fill="none"):
    h=s*.78; return [(cx-s/2,cy+h/2),(cx+s/2,cy+h/2),(cx,cy-h/2)]

@register("合同")
def fig_congruent():
    p1=triangle(88,110,88);p2=[(x+145,y) for x,y in p1]
    b=[g.poly(p1,g.INK,1.6,g.FILL),g.poly(p2,g.INK,1.6,g.FILL2),g.t(160,116,"≡",20,g.ACCENT)]
    for pts in (p1,p2): b.append(g.line(pts[0][0]+37,pts[0][1]-3,pts[0][0]+43,pts[0][1]+3,g.ACCENT,1.5))
    return g.titled("合同",b,"形も大きさも同じ（向きは変わってよい）")


@register("商")
def fig_quotient():
    b=[g.t(160,48,"12 ÷ 3 = 4",18,g.ACCENT)]
    for group in range(3):
        x=55+group*100;b.append(g.rect(x-26,68,72,72,g.SUB,1.1,g.FILL,rx=8))
        for i in range(4): b.append(g.dot(x+(i%2)*20,x*0+88+(i//2)*22,5,g.INK))
        b.append(g.t(x+10,157,"4個",9,g.SUB))
    return g.titled("商",b,"割り算の答え")


@register("四分位数")
def fig_quartile():
    y=105;b=[g.line(35,y,285,y,g.SUB,1.2),g.line(35,y-18,35,y+18,g.INK,1.2),g.line(285,y-18,285,y+18,g.INK,1.2),
             g.rect(88,y-28,145,56,g.INK,1.5,g.FILL),g.line(160,y-28,160,y+28,g.ACCENT,2.0)]
    for x,label in ((88,"Q1"),(160,"Q2（中央値）"),(233,"Q3")):
        b += [g.line(x,136,x,145,g.SUB,1.0),g.t(x,160,label,9,g.ACCENT if x==160 else g.INK)]
    return g.titled("四分位数",b,"データを小さい順に四つに分ける境目")


def perp_bisector(word):
    A,B=(95,130),(225,130);b=[g.line(*A,*B,g.INK,1.6),g.dot(*A),g.dot(*B)]
    for P in (A,B): b += [g.circle(*P,86,g.SUB,1.0,"none","4 3")]
    b += [g.line(160,35,160,176,g.ACCENT,1.8),g.path("M152,130 L152,122 L160,122",g.ACCENT,1.2),
          g.line(126,126,131,134,g.INK,1.3),g.line(189,126,194,134,g.INK,1.3),g.t(95,150,"A",9),g.t(225,150,"B",9)]
    return g.titled(word,b,"線分の中点を通り、線分に垂直な直線")

@register("垂直二等分線")
def fig_perp(): return perp_bisector("垂直二等分線")


@register("対称移動")
def fig_reflect():
    left=[(72,70),(122,92),(82,148)];right=[(248-x, y) for x,y in left]
    b=[g.line(160,42,160,166,g.ACCENT,1.4,"5 4"),g.poly(left,g.INK,1.5,g.FILL),g.poly(right,g.INK,1.5,g.FILL2)]
    for p,q in zip(left,right,strict=True): b.append(g.line(*p,*q,g.SUB,1.0,"3 3"))
    b.append(g.t(160,180,"対称の軸",9,g.ACCENT))
    return g.titled("対称移動",b,"対応する点は軸から等しい距離")


@register("小数")
def fig_decimal():
    b=[];x0,y0,w,h=75,57,170,90
    for i in range(10): b.append(g.rect(x0+i*w/10,y0,w/10,h,g.SUB,.8,g.FILL2 if i<3 else "#ffffff"))
    b += [g.t(160,169,"3/10 = 0.3",16,g.ACCENT)]
    return g.titled("小数",b,"1を10等分した三つ分")


@register("展開")
def fig_expand():
    x0,y0=60,62;aw,bw,ch,dh=90,55,55,42
    b=[g.rect(x0,y0,aw,ch,g.INK,1.2,g.FILL),g.rect(x0+aw,y0,bw,ch,g.INK,1.2,g.FILL2),
       g.rect(x0,y0+ch,aw,dh,g.INK,1.2,"#e7f2df"),g.rect(x0+aw,y0+ch,bw,dh,g.INK,1.2,"#f5e8b8"),
       g.t(x0+aw/2,y0+32,"ac",12),g.t(x0+aw+bw/2,y0+32,"bc",12),
       g.t(x0+aw/2,y0+ch+27,"ad",12),g.t(x0+aw+bw/2,y0+ch+27,"bd",12),
       g.t(160,174,"(a+b)(c+d) = ac+ad+bc+bd",11.5,g.ACCENT)]
    return g.titled("展開",b,"積の形を和の形にする")


@register("帯グラフ")
def fig_band():
    b=[];x=32;parts=[("A 40%",100,g.FILL2),("B 35%",87.5,g.FILL),("C 25%",62.5,"#e7f2df")]
    for label,w,fill in parts: b.append(g.rect(x,73,w,55,g.INK,1.0,fill));b.append(g.t(x+w/2,105,label,10));x+=w
    b += [g.t(32,151,"0%",9,g.SUB,"start"),g.t(288,151,"100%",9,g.SUB,"end")]
    return g.titled("帯グラフ",b,"全体を100%として割合を比べる")


@register("底面積")
def fig_base_area():
    top=[(90,54),(190,54),(235,82),(135,82)];bottom=[(90,128),(190,128),(235,156),(135,156)]
    b=[g.poly(bottom,g.ACCENT,1.8,g.FILL2),g.poly(top,g.INK,1.3,"#ffffff")]
    for p,q in zip(top,bottom,strict=True): b.append(g.line(*p,*q,g.INK,1.3))
    b += [g.t(162,151,"底面積 S",11,g.ACCENT),g.t(45,106,"高さ h",10,g.SUB),g.line(72,82,72,128,g.SUB,1.2),
          g.t(254,116,"体積 = S×h",10,g.INK)]
    return g.titled("底面積",b)


@register("拡大図")
def fig_enlarge():
    p1=triangle(78,115,58);p2=triangle(224,108,106)
    b=[g.poly(p1,g.INK,1.5,g.FILL),g.poly(p2,g.ACCENT,1.7,g.FILL2),g.arrow(112,108,158,108,g.SUB,1.3),
       g.t(78,160,"辺 3",9,g.SUB),g.t(224,169,"辺 6",9,g.ACCENT),g.t(137,96,"×2",11,g.ACCENT)]
    return g.titled("拡大図",b,"対応する長さの比がすべて同じ")


@register("正の数")
def fig_positive():
    y=111;b=[g.arrow(30,y,292,y,g.SUB,1.3)]
    for n in range(-4,6):
        x=143+n*24;b += [g.line(x,y-6,x,y+6,g.SUB,1.0),g.t(x,y+22,str(n),8.5,g.SUB)]
    b += [g.line(143,y,292,y,g.ACCENT,3.5),g.arrow(148,76,280,76,g.ACCENT,1.5),g.t(220,65,"正の向き",10,g.ACCENT),g.dot(215,y,4,g.ACCENT)]
    return g.titled("正の数",b,"0より大きい数")


@register("積")
def fig_product():
    b=[g.t(160,45,"3 × 4 = 12",18,g.ACCENT)]
    for r in range(3):
        for c in range(4): b.append(g.circle(105+c*36,75+r*34,8,g.INK,1.2,g.FILL))
    b += [g.line(92,67,92,151,g.SUB,1.0),g.t(80,112,"3行",9,g.SUB),g.line(97,164,221,164,g.SUB,1.0),g.t(160,180,"4列",9,g.SUB)]
    return g.titled("積",b,"かけ算の答え")


@register("等式の性質")
def fig_equation_property():
    b=[g.t(160,47,"a = b",17),g.arrow(160,56,160,78,g.SUB,1.3),g.t(160,96,"両辺に同じ数 c を加える",10,g.SUB),
       g.t(160,130,"a + c = b + c",18,g.ACCENT),g.line(70,151,250,151,g.INK,1.3),g.dot(160,151,4),
       g.line(110,151,90,170,g.INK,1.2),g.line(210,151,230,170,g.INK,1.2)]
    return g.titled("等式の性質",b,"両辺に同じ操作をしても等式は成り立つ")


@register("累積度数")
def fig_cumulative():
    vals=[2,3,4,2];cum=[];s=0
    for v in vals:s+=v;cum.append(s)
    b=[];x0,y0=52,157
    for i,v in enumerate(vals): b.append(g.rect(x0+i*45,y0-v*12,34,v*12,g.SUB,1.0,g.FILL))
    pts=[(x0+i*45+17,y0-c*8) for i,c in enumerate(cum)]
    b.append(g.path("M"+" L".join(f"{x},{y}" for x,y in pts),g.ACCENT,2.0))
    for x,y in pts:b.append(g.dot(x,y,3,g.ACCENT))
    b += [g.t(265,72,"2→5→9→11",9.5,g.ACCENT),g.t(160,177,"階級",9,g.SUB)]
    return g.titled("累積度数",b,"その階級までの度数を順に足した値")


@register("組み合わせ")
def fig_combination():
    labels="ABCD";b=[g.t(160,48,"4個から2個を選ぶ",11,g.SUB)]
    pairs=["AB","AC","AD","BC","BD","CD"]
    for i,p in enumerate(pairs):
        x=54+(i%3)*106;y=72+(i//3)*50;b+=box_label(x-31,y,62,34,p,fill=g.FILL2 if i%2 else g.FILL,size=13)
    b.append(g.t(160,176,"順序を区別しない：6通り",10.5,g.ACCENT))
    return g.titled("組み合わせ",b)


@register("繰り上がり")
def fig_carry():
    b=[g.t(85,64,"8 + 5",16),g.t(85,93,"= 13",18,g.ACCENT),g.arrow(119,87,162,87,g.SUB,1.4)]
    for i in range(10): b.append(g.rect(174+(i%5)*13,59+(i//5)*13,11,11,g.SUB,.8,g.FILL2))
    b += [g.arrow(208,91,208,118,g.ACCENT,1.4),g.rect(194,122,28,45,g.ACCENT,1.2,g.FILL2),g.t(208,181,"10個 → 1十",9,g.ACCENT),
          g.t(265,145,"+ 3個",10)]
    return g.titled("繰り上がり",b,"10個まとまったら一つ上の位へ")


@register("繰り下がり")
def fig_borrow():
    b=[g.t(72,65,"13 − 5",16),g.t(72,94,"= 8",18,g.ACCENT),g.rect(142,54,28,48,g.ACCENT,1.3,g.FILL2),
       g.arrow(174,77,205,77,g.ACCENT,1.4)]
    for i in range(10): b.append(g.rect(216+(i%5)*13,55+(i//5)*13,11,11,g.SUB,.8,g.FILL))
    b += [g.t(156,121,"1十",9,g.ACCENT),g.t(246,103,"10個",9,g.ACCENT),g.t(205,148,"10 + 3 − 5 = 8",12)]
    return g.titled("繰り下がり",b,"一つ上の位を10個に分ける")


@register("角の二等分線")
def fig_angle_bisector():
    O=(78,145);A=(270,145);B=(205,55);mid=(254,93)
    b=[g.line(*O,*A,g.INK,1.6),g.line(*O,*B,g.INK,1.6),g.line(*O,*mid,g.ACCENT,2.0),g.dot(*O)]
    b += [g.path("M120,145 A42,42 0 0 0 112,120",g.SUB,1.2),g.path("M112,120 A42,42 0 0 0 104,101",g.SUB,1.2),
          g.t(136,131,"α",11,g.ACCENT),g.t(130,106,"α",11,g.ACCENT)]
    return g.titled("角の二等分線",b,"一つの角を等しい二つの角に分ける")


@register("通分")
def fig_common_denominator():
    b=[g.t(57,70,"1/2",16),g.t(57,130,"1/3",16),g.arrow(91,70,140,70,g.SUB,1.3),g.arrow(91,130,140,130,g.SUB,1.3),
       g.t(174,70,"3/6",18,g.ACCENT),g.t(174,130,"2/6",18,g.ACCENT),g.t(252,100,"分母を6に",11,g.SUB)]
    for y,n in ((52,3),(112,2)):
        for i in range(6): b.append(g.rect(142+i*17,y,17,32,g.SUB,.7,g.FILL2 if i<n else "#ffffff"))
    return g.titled("通分",b,"分数の分母を同じ数にそろえる")


@register("連立方程式")
def fig_simultaneous():
    ox,oy=170,143;b=g.axes(ox,oy,-110,112,-18,94)
    b += [g.line(72,153,260,59,g.INK,1.7),g.line(72,63,260,157,g.ACCENT,1.7),g.dot(170,108,4,g.ACCENT),
          g.t(52,55,"x+y=5",9,g.ACCENT,"start"),g.t(235,171,"x−y=1",9,g.INK),g.t(190,101,"(3,2)",10,g.ACCENT,"start")]
    return g.titled("連立方程式",b,"二つの式を同時に満たす交点が解")


@register("面積")
def fig_area():
    b=[];x0,y0,s=82,54,30
    for r in range(3):
        for c in range(5): b.append(g.rect(x0+c*s,y0+r*s,s,s,g.SUB,.9,g.FILL2 if (r,c)==(0,0) else g.FILL))
    b += [g.t(157,161,"5 × 3 = 15",16,g.ACCENT)]
    return g.titled("面積",b,"図形が単位正方形いくつ分か")


EXPECTED = {
    "七言律詩", "下一段活用", "五段活用", "五言絶句", "倒置法", "切れ字", "反復法", "対句", "掛詞", "接続助詞", "文節", "未然形", "枕詞", "類義語",
    "アッチェレランド", "クレッシェンド", "スタッカート", "ソナタ形式", "タイ", "ダカーポ", "ダルセーニョ", "ディミヌエンド", "デクレッシェンド", "ピアニシモ", "フェルマータ", "フォルテ", "フォルテシモ", "モデラート", "ラルゴ", "三連符", "反復記号", "短調", "長調", "階名", "音階",
    "さくらんぼ計算", "ねじれの位置", "もとにする量", "代入", "作図", "倍数", "側面", "公倍数", "公約数", "分速", "割合", "単位換算", "合同", "商", "四分位数", "垂直二等分線", "対称移動", "小数", "展開", "帯グラフ", "底面積", "拡大図", "正の数", "秒速", "積", "等式の性質", "累積度数", "組み合わせ", "繰り上がり", "繰り下がり", "角の二等分線", "通分", "連立方程式", "面積",
}
assert set(FIGURES) == EXPECTED, (EXPECTED - set(FIGURES), set(FIGURES) - EXPECTED)
assert len(FIGURES) == 69


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for word, fn in FIGURES.items():
        svg = fn()
        if '<svg ' not in svg or f'>{word}</text>' not in svg:
            raise SystemExit(f"invalid SVG/title: {word}")
        (out / f"{g.key(word)}.svg").write_text(svg, encoding="utf-8")
    print(f"{len(FIGURES)}枚を書き出した -> {out}")


if __name__ == "__main__":
    main()
