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


# ---- 黒背景カードで消える画像の差し替え図版 --------------------------------
#
# Commons の作図SVGは「黒線+透明背景」が多く、soramimic-video の黒背景カード
# (gimukyoiku_card)では実質見えない。これらはこのツールで白背景の図版SVGに
# 置き換える(既存の数学作図と同形式)。


@register("正三角形")
def fig_正三角形():
    pts = [(70, 150), (250, 150), (160, 52)]
    b = [g.poly(pts, g.INK, 2.0, g.FILL),
         g.line(160, 52, 160, 150, g.ACCENT, 1.2, dash="4 3")]
    for x, label in ((95, "60°"), (205, "60°"), (160, "60°")):
        b.append(g.t(x, 164, label, 10.5, g.ACCENT))
    b.append(g.t(160, 42, "3辺の長さが等しい", 10, g.SUB))
    b.append(g.t(160, 116, "h = √3/2 × 一辺", 11, g.INK))
    b.append(g.t(160, 188, "3つの角はすべて60°", 9.5, g.SUB))
    return g.titled("正三角形", b)


@register("直角三角形")
def fig_直角三角形():
    b = [g.poly([(60, 152), (250, 152), (60, 66)], g.INK, 2.0, g.FILL),
         g.path("M60,152 L78,152 L78,134 Z", g.INK, 1.2, g.ACCENT),
         g.line(60, 66, 104, 66, g.ACCENT, 1.1, dash="3 3"),
         g.t(80, 58, "高さ", 10, g.ACCENT),
         g.line(60, 152, 60, 116, g.ACCENT, 1.1, dash="3 3"),
         g.t(32, 134, "底辺", 10, g.ACCENT),
         g.t(160, 170, "面積 = 底辺 × 高さ ÷ 2", 11.5)]
    return g.titled("直角三角形", b)


@register("平行四辺形")
def fig_平行四辺形():
    b = [g.poly([(50, 140), (190, 140), (230, 78), (90, 78)], g.INK, 2.0, g.FILL),
         g.line(190, 140, 190, 78, g.ACCENT, 1.2, dash="4 3"),
         g.t(200, 112, "高さ", 10, g.ACCENT),
         g.t(120, 156, "底辺", 10, g.ACCENT),
         g.t(160, 178, "向かい合う2組の辺が平行", 10, g.SUB),
         g.t(160, 190, "面積 = 底辺 × 高さ", 11)]
    return g.titled("平行四辺形", b)


@register("台形")
def fig_台形():
    b = [g.poly([(50, 145), (110, 145), (170, 70), (40, 70)], g.INK, 2.0, g.FILL),
         g.line(110, 145, 110, 70, g.ACCENT, 1.2, dash="4 3"),
         g.t(120, 112, "高さ", 10, g.ACCENT),
         g.line(70, 154, 160, 154, g.INK, 1.0),
         g.line(70, 60, 130, 60, g.INK, 1.0),
         g.t(70, 166, "上底 a", 10, g.INK), g.t(130, 52, "下底 b", 10, g.INK),
         g.t(160, 190, "面積 = (上底 + 下底) × 高さ ÷ 2", 10.5)]
    return g.titled("台形", b)


@register("長方形")
def fig_長方形():
    b = [g.rect(70, 65, 180, 85, g.INK, 2.0, g.FILL),
         g.line(70, 65, 250, 65, g.ACCENT, 1.1, dash="3 3"),
         g.t(160, 57, "横", 10, g.ACCENT),
         g.line(250, 65, 250, 150, g.ACCENT, 1.1, dash="3 3"),
         g.t(258, 112, "縦", 10, g.ACCENT),
         g.t(160, 170, "4つの角がすべて90°", 10.5, g.SUB),
         g.t(160, 185, "面積 = 縦 × 横", 11)]
    return g.titled("長方形", b)


@register("中点")
def fig_中点():
    b = [g.line(70, 130, 250, 130, g.INK, 2.0),
         g.dot(70, 130, 3.2), g.dot(250, 130, 3.2),
         g.dot(160, 130, 4.0, g.ACCENT),
         g.t(64, 122, "A", 11, g.INK), g.t(246, 122, "B", 11, g.INK),
         g.t(160, 122, "M", 11, g.ACCENT),
         g.t(115, 146, "AM", 10, g.ACCENT), g.t(205, 146, "MB", 10, g.ACCENT),
         g.t(160, 172, "線分ABを2等分する点", 10.5),
         g.t(160, 186, "AM = MB", 11, g.ACCENT)]
    return g.titled("中点", b)


@register("円周率")
def fig_円周率():
    b = [g.circle(160, 105, 62, g.INK, 2.0),
         g.line(160, 105, 222, 105, g.ACCENT, 1.4),
         g.t(194, 98, "半径 r", 10, g.ACCENT),
         g.line(98, 105, 222, 105, g.SUB, 1.0, dash="3 3"),
         g.t(160, 94, "直径", 9.5, g.SUB),
         g.t(160, 180, "円周 ÷ 直径 = π ≈ 3.14", 11.5, g.ACCENT),
         g.t(160, 194, "円周 = 2πr", 10.5)]
    return g.titled("円周率", b)


@register("根号")
def fig_根号():
    b = [g.t(160, 78, "√", 52, g.INK, "middle", g.MATHFONT, "700"),
         g.line(188, 78, 188, 118, g.INK, 2.0),
         g.line(188, 118, 232, 118, g.INK, 2.0),
         g.t(210, 108, "a", 14, g.ACCENT, "middle", g.MATHFONT, "400", "italic"),
         g.t(160, 152, "√a は2乗すると a になる数(正)", 11),
         g.t(160, 174, "√4 = 2,  √9 = 3", 11, g.ACCENT),
         g.t(160, 190, "ルート記号", 9.5, g.SUB)]
    return g.titled("根号", b)


@register("等号")
def fig_等号():
    b = [g.rect(105, 62, 110, 16, g.ACCENT, 0, "#f3ddd3", 4),
         g.rect(105, 92, 110, 16, g.ACCENT, 0, "#f3ddd3", 4),
         g.t(160, 44, "左辺", 10, g.SUB), g.t(160, 128, "右辺", 10, g.SUB),
         g.t(160, 76, "=", 22, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 166, "左右の値が等しいことを表す", 11),
         g.t(160, 188, "例: 3 + 2 = 5", 11.5, g.ACCENT)]
    return g.titled("等号", b)


@register("百分率")
def fig_百分率():
    b = [g.rect(118, 58, 84, 84, g.INK, 2.0, g.FILL),
         g.t(160, 106, "%", 42, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 170, "全体を100として割合を表す", 11),
         g.t(160, 186, "50% = 半分,  100% = 全部", 10.5, g.ACCENT)]
    return g.titled("百分率", b)


@register("点対称")
def fig_点対称():
    b = [g.line(70, 90, 250, 90, g.SUB, 1.0, dash="3 3"),
         g.line(160, 40, 160, 150, g.SUB, 1.0, dash="3 3"),
         g.dot(160, 95, 4.0, g.ACCENT),
         g.t(154, 76, "O", 10, g.ACCENT),
         g.poly([(105, 62), (125, 62), (125, 82), (105, 82)], g.INK, 1.5, g.FILL),
         g.poly([(215, 108), (195, 108), (195, 128), (215, 128)], g.INK, 1.5, g.FILL),
         g.t(96, 50, "P", 10.5), g.t(226, 138, "P'", 10.5),
         g.line(105, 72, 215, 118, g.ACCENT, 1.0, dash="3 3"),
         g.t(160, 172, "点Oを中心に180°回転して重なる", 10.5),
         g.t(160, 188, "OP = OP'", 11, g.ACCENT)]
    return g.titled("点対称", b)


@register("素因数分解")
def fig_素因数分解():
    b = [g.t(160, 42, "60", 15, g.INK),
         g.line(130, 48, 112, 62, g.INK, 1.2), g.line(190, 48, 208, 62, g.INK, 1.2),
         g.t(104, 70, "2", 12, g.ACCENT), g.t(214, 70, "30", 12, g.INK),
         g.line(196, 76, 184, 88, g.INK, 1.2), g.line(226, 76, 240, 88, g.INK, 1.2),
         g.t(176, 96, "2", 12, g.ACCENT), g.t(246, 96, "15", 12, g.INK),
         g.line(236, 102, 224, 114, g.INK, 1.2), g.line(258, 102, 270, 114, g.INK, 1.2),
         g.t(216, 122, "3", 12, g.ACCENT), g.t(278, 122, "5", 12, g.ACCENT),
         g.t(160, 156, "60 = 2 × 2 × 3 × 5", 12.5, g.ACCENT),
         g.t(160, 178, "素数のかけ算だけに分解する", 10.5),
         g.t(160, 192, "2² × 3 × 5", 11, g.INK)]
    return g.titled("素因数分解", b)


@register("整数")
def fig_整数():
    b = [g.line(55, 110, 265, 110, g.INK, 1.8),
         g.arrow(55, 110, 268, 110, g.INK, 1.2),
         g.t(272, 113, "→", 12, g.INK)]
    for i, x in enumerate(range(55, 270, 26)):
        b.append(g.line(x, 104, x, 116, g.INK, 1.2))
        b.append(g.t(x, 128, str(i - 4), 10, g.ACCENT if i == 4 else g.INK))
    b.append(g.t(160, 152, "…, −2, −1, 0, 1, 2, …", 12.5))
    b.append(g.t(160, 174, "自然数・0・負の整数を合わせた数", 10.5))
    b.append(g.t(160, 190, "小数や分数は含まない", 10, g.ACCENT))
    return g.titled("整数", b)


@register("有理数")
def fig_有理数():
    b = [g.line(55, 105, 265, 105, g.INK, 1.8),
         g.arrow(55, 105, 268, 105, g.INK, 1.2)]
    for i, x in enumerate(range(55, 270, 26)):
        b.append(g.line(x, 99, x, 111, g.INK, 1.2))
        b.append(g.t(x, 122, str(i - 4), 9.5, g.INK))
    marks = [(81, "−1/2"), (134, "1/4"), (160, "0.5"), (213, "3/2")]
    for x, lab in marks:
        b.append(g.dot(x, 105, 3.0, g.ACCENT))
        b.append(g.t(x, 88, lab, 9, g.ACCENT))
    b.append(g.t(160, 148, "分数で表せる数(整数も含む)", 11))
    b.append(g.t(160, 166, "例: 1/2, 0.75, −3", 11, g.ACCENT))
    b.append(g.t(160, 186, "循環小数も有理数", 9.5, g.SUB))
    return g.titled("有理数", b)


@register("単位円")
def fig_単位円():
    ox, oy = 160, 105
    b = g.axes(ox, oy, -86, 96, -80, 88)
    b.append(g.circle(ox, oy, 66, g.INK, 1.8))
    b.append(g.line(ox, oy, ox + 55, oy - 36, g.ACCENT, 2.0))
    b.append(g.t(ox + 62, oy - 36, "1", 10, g.ACCENT))
    b.append(g.t(ox + 30, oy - 18, "θ", 11, g.ACCENT, "middle", g.MATHFONT, "400", "italic"))
    b.append(g.dot(ox + 55, oy - 36, 3.2, g.ACCENT))
    b.append(g.t(ox + 8, oy - 78, "sin θ", 10, g.SUB))
    b.append(g.t(ox + 84, oy + 14, "cos θ", 10, g.SUB))
    b.append(g.t(160, 178, "半径1の円で角度と三角比を表す", 10.5))
    b.append(g.t(160, 192, "sin²θ + cos²θ = 1", 11, g.ACCENT))
    return g.titled("単位円", b)


@register("二項定理")
def fig_二項定理():
    b = [g.t(160, 44, "(a + b)²", 16, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 68, "= a² + 2ab + b²", 14, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.rect(40, 96, 104, 52, g.INK, 1.4, g.FILL),
         g.rect(176, 96, 104, 52, g.INK, 1.4, g.FILL2),
         g.t(92, 118, "a²", 13, g.INK, "middle", g.MATHFONT, "700"),
         g.t(92, 136, "a×a", 9.5, g.SUB),
         g.t(228, 118, "b²", 13, g.INK, "middle", g.MATHFONT, "700"),
         g.t(228, 136, "b×b", 9.5, g.SUB),
         g.t(160, 172, "2ab は (a+b)² を展開した中央の項", 10.5),
         g.t(160, 188, "(a+b)³ は a³+3a²b+3ab²+b³", 10.5, g.ACCENT)]
    return g.titled("二項定理", b)


@register("パスカルの三角形")
def fig_パスカルの三角形():
    rows = [[1], [1, 1], [1, 2, 1], [1, 3, 3, 1], [1, 4, 6, 4, 1]]
    b = []
    for r, row in enumerate(rows):
        y = 44 + r * 27
        for c, v in enumerate(row):
            x = 160 + (c - r / 2) * 34
            b.append(g.t(x, y, str(v), 12, g.ACCENT if r == 4 and c == 2 else g.INK))
    b.append(g.t(160, 178, "上の2つの数の和が下の数になる", 10.5))
    b.append(g.t(160, 192, "(a+b)ⁿ の係数と一致", 10.5, g.ACCENT))
    return g.titled("パスカルの三角形", b)


@register("合成関数")
def fig_合成関数():
    b = [g.t(58, 105, "x", 13, g.INK, "middle", g.MATHFONT, "400", "italic"),
         g.t(160, 105, "f(x)", 13, g.ACCENT, "middle", g.MATHFONT, "400", "italic"),
         g.t(262, 105, "g(f(x))", 12, g.ACCENT, "middle", g.MATHFONT, "400", "italic"),
         g.rect(92, 80, 52, 48, g.INK, 1.4, g.FILL),
         g.rect(192, 80, 58, 48, g.INK, 1.4, g.FILL),
         g.arrow(68, 105, 90, 105, g.INK, 1.4),
         g.arrow(148, 105, 188, 105, g.INK, 1.4),
         g.t(160, 160, "f の結果に g をかける", 11),
         g.t(160, 178, "(g ∘ f)(x) = g(f(x))", 11.5, g.ACCENT),
         g.t(160, 192, "x → f → g の順に合成", 9.5, g.SUB)]
    return g.titled("合成関数", b)


@register("空間ベクトル")
def fig_空間ベクトル():
    b = [g.line(60, 150, 210, 150, g.INK, 1.4), g.line(60, 150, 60, 52, g.INK, 1.4),
         g.line(60, 150, 250, 112, g.INK, 1.4),
         g.arrow(60, 150, 180, 66, g.ACCENT, 2.2),
         g.t(30, 48, "z", 10, g.SUB), g.t(214, 154, "x", 10, g.SUB),
         g.t(254, 108, "y", 10, g.SUB),
         g.t(126, 100, "a", 12, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 172, "3次元空間の向きと大きさをもつ量", 10.5),
         g.t(160, 188, "a = (a₁, a₂, a₃)", 11, g.ACCENT, "middle", g.MATHFONT, "400", "italic")]
    return g.titled("空間ベクトル", b)


@register("不定方程式")
def fig_不定方程式():
    ox, oy = 90, 150
    b = g.axes(ox, oy, -35, 200, -40, 105, "x", "y")
    b.append(g.line(40, 66, 270, 150, g.ACCENT, 2.0))
    for x in (60, 90, 120, 150, 180):
        y = 150 - (x - 60) * 0.5
        b.append(g.dot(x, y, 3.2, g.INK))
    b.append(g.t(242, 130, "2x + 3y = 7", 12, g.ACCENT, "middle", g.MATHFONT, "700"))
    b.append(g.t(160, 172, "解が無数にある方程式", 11))
    b.append(g.t(160, 188, "整数解: (2, 1), (5, −1), …", 10.5))
    return g.titled("不定方程式", b)


# ---- 理科 ------------------------------------------------------------


def _chem_box(x, y, w, h, text, *, size=12, fill="#ffffff", stroke=g.INK, color=g.INK, rx=6):
    return [g.rect(x, y, w, h, stroke, 1.2, fill, rx),
            g.t(x + w / 2, y + h / 2 + size * 0.35, text, size, color)]


@register("尿素")
def fig_尿素():
    b = []
    b += _chem_box(138, 52, 44, 34, "C", size=14)
    b += _chem_box(92, 112, 52, 34, "NH₂", size=11)
    b += _chem_box(176, 112, 52, 34, "NH₂", size=11)
    b += [g.line(138, 86, 118, 112, g.INK, 1.6), g.line(182, 86, 202, 112, g.INK, 1.6),
          g.line(160, 86, 160, 46, g.INK, 1.6),
          g.t(172, 44, "O", 11, g.ACCENT, "middle", g.MATHFONT, "700")]
    b.append(g.t(160, 172, "CO(NH₂)₂ — 肥料・プラスチックの原料", 10.5))
    b.append(g.t(160, 188, "炭素・酸素・窒素・水素からなる有機化合物", 9.5, g.SUB))
    return g.titled("尿素", b)


@register("カルボン酸")
def fig_カルボン酸():
    b = []
    b += _chem_box(58, 96, 74, 40, "R", size=14)
    b += _chem_box(176, 96, 86, 40, "COOH", size=13, fill=g.FILL2, color=g.ACCENT)
    b += [g.line(132, 116, 176, 116, g.INK, 1.8),
          g.t(160, 160, "R–COOH の −COOH が酸性を示す", 11),
          g.t(160, 178, "例: 酢酸 CH₃COOH, ギ酸 HCOOH", 10.5),
          g.t(160, 192, "炭素鎖の末端に COOH をもつ", 9.5, g.SUB)]
    return g.titled("カルボン酸", b)


@register("エステル")
def fig_エステル():
    b = []
    b += _chem_box(48, 92, 60, 38, "R", size=13)
    b += _chem_box(158, 92, 64, 38, "COO", size=13, fill=g.FILL2, color=g.ACCENT)
    b += _chem_box(258, 92, 60, 38, "R'", size=13)
    b += [g.line(108, 111, 158, 111, g.INK, 1.6), g.line(222, 111, 258, 111, g.INK, 1.6),
          g.t(160, 158, "酸とアルコールから水がとれてできる", 10.5),
          g.t(160, 176, "R–COO–R' — 果物の香りの成分", 11, g.ACCENT),
          g.t(160, 192, "例: 酢酸エチル CH₃COOC₂H₅", 10, g.SUB)]
    return g.titled("エステル", b)


@register("炭酸水素ナトリウム")
def fig_炭酸水素ナトリウム():
    b = []
    b += _chem_box(92, 48, 136, 40, "NaHCO₃", size=15, fill=g.FILL, color=g.INK)
    b += [g.arrow(160, 96, 160, 116, g.ACCENT, 1.6),
          g.t(160, 90, "加熱", 9.5, g.ACCENT)]
    b += _chem_box(34, 128, 88, 34, "Na₂CO₃", size=12)
    b += _chem_box(128, 128, 62, 34, "H₂O", size=12)
    b += _chem_box(196, 128, 62, 34, "CO₂", size=12, fill=g.FILL2, color=g.ACCENT)
    b.append(g.t(160, 178, "重曹 — ベーキングパウダー・胃薬", 10.5))
    b.append(g.t(160, 192, "2NaHCO₃ → Na₂CO₃ + H₂O + CO₂", 10.5, g.ACCENT))
    return g.titled("炭酸水素ナトリウム", b)


@register("アドレナリン")
def fig_アドレナリン():
    b = [g.poly([(70, 132), (110, 132), (126, 96), (110, 60), (70, 60), (54, 96)], g.INK, 1.6, g.FILL),
         g.line(90, 60, 90, 42, g.INK, 1.6),
         g.t(100, 38, "OH", 9.5, g.ACCENT),
         g.line(70, 96, 44, 96, g.INK, 1.6),
         g.t(34, 102, "OH", 9.5, g.ACCENT),
         g.line(126, 96, 160, 96, g.INK, 1.6),
         g.line(160, 96, 196, 74, g.INK, 1.6),
         g.line(196, 74, 232, 74, g.INK, 1.6),
         g.t(214, 68, "NH", 10, g.ACCENT),
         g.t(160, 172, "副腎髄質から出るホルモン", 11),
         g.t(160, 188, "心拍・血圧を上げ、闘争か逃走の反応", 10, g.SUB)]
    return g.titled("アドレナリン", b)


@register("配位結合")
def fig_配位結合():
    b = []
    b += _chem_box(60, 88, 76, 40, "N", size=16, fill=g.FILL)
    b += _chem_box(188, 88, 80, 40, "H⁺", size=14, fill=g.FILL2, color=g.ACCENT)
    b += [g.arrow(140, 108, 184, 108, g.ACCENT, 2.0),
          g.t(162, 100, "非共有電子対", 9, g.ACCENT),
          g.t(160, 156, "窒素の非共有電子対を H⁺ に与える結合", 10.5),
          g.t(160, 174, "NH₃ + H⁺ → NH₄⁺", 12, g.ACCENT),
          g.t(160, 192, "電子対の提供者と受容者の結合", 9.5, g.SUB)]
    return g.titled("配位結合", b)


@register("直列回路")
def fig_直列回路():
    b = [g.rect(48, 44, 44, 66, g.INK, 1.4, g.FILL2),
         g.t(70, 82, "電池", 9, g.ACCENT),
         g.line(48, 66, 24, 66, g.INK, 1.6), g.line(24, 66, 24, 150, g.INK, 1.6),
         g.line(24, 150, 296, 150, g.INK, 1.6), g.line(296, 150, 296, 66, g.INK, 1.6),
         g.line(296, 66, 92, 66, g.INK, 1.6),
         g.circle(130, 110, 15, g.INK, 1.5, g.FILL), g.circle(210, 110, 15, g.INK, 1.5, g.FILL),
         g.t(130, 140, "豆電球", 8.5, g.SUB), g.t(210, 140, "豆電球", 8.5, g.SUB),
         g.arrow(160, 162, 200, 162, g.ACCENT, 1.4),
         g.t(180, 172, "電流", 9.5, g.ACCENT),
         g.t(160, 192, "1本の道すじ — どこか1か所切れると消える", 10)]
    return g.titled("直列回路", b)


@register("並列回路")
def fig_並列回路():
    b = [g.rect(48, 44, 44, 66, g.INK, 1.4, g.FILL2),
         g.t(70, 82, "電池", 9, g.ACCENT),
         g.line(48, 66, 24, 66, g.INK, 1.6), g.line(24, 66, 24, 150, g.INK, 1.6),
         g.line(24, 150, 296, 150, g.INK, 1.6), g.line(296, 150, 296, 66, g.INK, 1.6),
         g.line(296, 66, 92, 66, g.INK, 1.6),
         g.line(108, 66, 108, 150, g.INK, 1.5), g.line(232, 66, 232, 150, g.INK, 1.5),
         g.circle(130, 108, 14, g.INK, 1.4, g.FILL), g.circle(210, 108, 14, g.INK, 1.4, g.FILL),
         g.t(130, 138, "豆電球", 8.5, g.SUB), g.t(210, 138, "豆電球", 8.5, g.SUB),
         g.t(160, 192, "枝分かれした道 — 片方だけ消してももう片方はつく", 9.5)]
    return g.titled("並列回路", b)


# ---- 音楽(記譜) ---------------------------------------------------------


@register("五線譜")
def fig_五線譜():
    b = staff(112)
    b += note(160, 126)
    b.append(g.t(160, 172, "音の高さを表す5本の線", 11))
    b.append(g.t(160, 188, "下から 第1線・第2線…第5線", 10, g.ACCENT))
    return g.titled("五線譜", b)


@register("音符")
def fig_音符():
    b = staff(108)
    b += note(108, 122)
    b += note(190, 122, open_=True)
    b.append(g.t(108, 148, "四分音符", 9, g.SUB))
    b.append(g.t(190, 148, "二分音符", 9, g.SUB))
    b.append(g.t(160, 174, "音の長さを表す記号", 11))
    b.append(g.t(160, 190, "四分音符 = 1拍", 10.5, g.ACCENT))
    return g.titled("音符", b)


@register("八分音符")
def fig_八分音符():
    b = staff(108)
    b += note(108, 122)
    b += [g.line(118, 122, 118, 88, g.INK, 1.5),
          g.path("M118,88 Q130,74 142,84", g.INK, 1.5)]
    b += note(196, 132, stem=False)
    b += [g.line(196, 122, 196, 88, g.INK, 1.5),
          g.path("M196,88 Q208,74 220,84", g.INK, 1.5)]
    b.append(g.t(160, 174, "符尾(はた)がついた音符", 11))
    b.append(g.t(160, 190, "八分音符 = 1/2拍", 10.5, g.ACCENT))
    return g.titled("八分音符", b)


@register("メロディー")
def fig_メロディー():
    b = staff(108)
    for x, y in ((90, 130), (128, 118), (166, 124), (204, 108), (242, 116)):
        b += note(x, y)
    b.append(g.t(160, 172, "歌や主役の音の並び", 11))
    b.append(g.t(160, 188, "ドレミの音の高さのつながり", 10, g.ACCENT))
    return g.titled("メロディー", b)


@register("主旋律")
def fig_主旋律():
    b = staff(105)
    for x, y in ((82, 124), (118, 112), (154, 118), (190, 102), (226, 110)):
        b += note(x, y, fill=g.ACCENT)
    b.append(g.line(80, 160, 240, 160, g.SUB, 1.0))
    b.append(g.t(160, 174, "曲の中心になる目立つ旋律", 11))
    b.append(g.t(160, 190, "伴奏にのって歌われる", 10, g.ACCENT))
    return g.titled("主旋律", b)


@register("旋律")
def fig_旋律():
    b = staff(108)
    for x, y in ((96, 126), (134, 112), (172, 120), (210, 104)):
        b += note(x, y)
    b.append(g.t(160, 172, "音の高さと長さの組み合わせ", 11))
    b.append(g.t(160, 188, "音楽の表情をつくる音の流れ", 10, g.ACCENT))
    return g.titled("旋律", b)


@register("スラー")
def fig_スラー():
    b = staff(108)
    b += note(110, 128) + note(176, 118) + note(242, 128)
    b += [arc_path(104, 142, 182, 132, -6, stroke=g.ACCENT, width=2.2),
          arc_path(170, 132, 248, 142, -6, stroke=g.ACCENT, width=2.2)]
    b.append(g.t(160, 174, "弧線で結ばれた音をなめらかに歌う", 10.5))
    b.append(g.t(160, 190, "息継ぎせずにつなげる", 10, g.ACCENT))
    return g.titled("スラー", b)


@register("レガート")
def fig_レガート():
    b = staff(108)
    for x, y in ((92, 126), (138, 114), (184, 122), (230, 110)):
        b += note(x, y)
    b += [arc_path(86, 140, 144, 128, -5, stroke=g.ACCENT, width=2.0),
          arc_path(132, 128, 190, 136, -5, stroke=g.ACCENT, width=2.0),
          arc_path(178, 136, 236, 124, -5, stroke=g.ACCENT, width=2.0)]
    b.append(g.t(160, 174, "音を切らずなめらかに演奏する", 11))
    b.append(g.t(160, 190, "「レガート」= 滑らかに", 10, g.ACCENT))
    return g.titled("レガート", b)


@register("ハ長調")
def fig_ハ長調():
    b = staff(100)
    scale = [(88, 124), (118, 112), (148, 116), (178, 100), (208, 108), (238, 96), (268, 104)]
    for x, y in scale:
        b += note(x, y, fill=g.INK, up=True)
    b.append(g.t(160, 150, "ドレミファソラシド", 11))
    b.append(g.t(160, 168, "♯も♭も使わない長調", 10.5, g.ACCENT))
    b.append(g.t(160, 186, "ピアノの白鍵だけで弾ける音階", 9.5, g.SUB))
    return g.titled("ハ長調", b)


@register("イ短調")
def fig_イ短調():
    b = staff(100)
    scale = [(88, 124), (118, 112), (148, 120), (178, 104), (208, 112), (238, 100), (268, 108)]
    for x, y in scale:
        b += note(x, y, fill=g.INK, up=True)
    b.append(g.t(160, 150, "ラシドレミファソ#ラ", 11))
    b.append(g.t(160, 168, "ハ長調の平行調(関係調)", 10.5, g.ACCENT))
    b.append(g.t(160, 186, "短調は暗く悲しい響き", 9.5, g.SUB))
    return g.titled("イ短調", b)


@register("君が代")
def fig_君が代():
    b = staff(106)
    for x, y in ((96, 128), (134, 112), (172, 120), (210, 104), (248, 116)):
        b += note(x, y)
    b.append(g.t(160, 172, "日本の国歌(旋律は1880年制定)", 10.5))
    b.append(g.t(160, 188, "「君が代は」の出だし", 10, g.ACCENT))
    return g.titled("君が代", b)


@register("サンタルチア")
def fig_サンタルチア():
    b = staff(106)
    for x, y in ((92, 112), (130, 122), (168, 104), (206, 116), (244, 104)):
        b += note(x, y)
    b.append(g.t(160, 172, "ナポリの民謡(舟歌)", 11))
    b.append(g.t(160, 188, "6/8拍子のゆったりした曲", 10, g.ACCENT))
    return g.titled("サンタルチア", b)


@register("対位法")
def fig_対位法():
    b = staff(88)
    for x, y in ((88, 108), (136, 96), (184, 104), (232, 92)):
        b += note(x, y)
    b += staff(140)
    for x, y in ((100, 160), (148, 148), (196, 156), (244, 144)):
        b += note(x, y)
    b.append(g.t(160, 180, "独立した複数の旋律を重ねる技法", 10.5))
    b.append(g.t(160, 194, "バッハのフーガなど", 10, g.ACCENT))
    return g.titled("対位法", b)


# ---- 技術・家庭 / 英語 / 保健体育 -----------------------------------------


@register("型紙")
def fig_型紙():
    b = [g.poly([(70, 70), (150, 70), (165, 150), (55, 150)], g.INK, 1.8, g.FILL),
         g.poly([(200, 66), (268, 66), (268, 120), (200, 132)], g.INK, 1.8, g.FILL2),
         g.line(70, 84, 150, 84, g.ACCENT, 1.1, dash="4 3"),
         g.line(200, 78, 268, 78, g.ACCENT, 1.1, dash="4 3"),
         g.arrow(200, 96, 268, 96, g.ACCENT, 1.4, "both"),
         g.t(234, 88, "布目", 8.5, g.ACCENT),
         g.t(110, 168, "身頃", 10, g.SUB), g.t(234, 148, "袖", 10, g.SUB),
         g.t(160, 186, "布に写すための型(実線=裁ち線・破線=出来上がり線)", 9.5)]
    return g.titled("型紙", b)


@register("電気用図記号")
def fig_電気用図記号():
    b = [g.rect(28, 52, 44, 62, g.INK, 1.3, g.FILL2),
         g.t(50, 128, "電池", 8.5, g.SUB),
         g.line(120, 66, 166, 66, g.INK, 1.6),
         g.rect(146, 60, 18, 22, g.INK, 1.3, g.ACCENT),
         g.line(164, 66, 210, 66, g.INK, 1.6),
         g.t(165, 128, "抵抗", 8.5, g.SUB),
         g.line(230, 84, 252, 84, g.INK, 1.6), g.line(252, 84, 252, 66, g.INK, 1.6),
         g.line(252, 66, 274, 66, g.INK, 1.6), g.line(274, 66, 274, 84, g.INK, 1.6),
         g.line(274, 84, 296, 84, g.INK, 1.6), g.t(263, 100, "スイッチ", 8.5, g.SUB),
         g.t(160, 160, "回路を図で表す共通の記号", 11),
         g.t(160, 178, "電池・抵抗・スイッチ・電球など", 10, g.ACCENT),
         g.t(160, 194, "回路図の読み書きに使う", 9.5, g.SUB)]
    return g.titled("電気用図記号", b)


@register("IPアドレス")
def fig_IPアドレス():
    octets = ["192", "168", "0", "1"]
    b = []
    for i, o in enumerate(octets):
        x = 32 + i * 70
        b += _chem_box(x, 62, 52, 40, o, size=14, fill=g.FILL)
        if i < 3:
            b.append(g.t(x + 58, 88, ".", 16, g.ACCENT, "middle", g.MATHFONT, "700"))
    b.append(g.t(160, 132, "0〜255 の数4つを「.」で区切る", 10.5))
    b.append(g.t(160, 150, "例: 192.168.0.1", 11, g.ACCENT))
    b.append(g.t(160, 172, "ネットワーク上の機器を識別する番号", 10.5))
    b.append(g.t(160, 190, "IPv4 は約43億個(現在はIPv6も併用)", 9.5, g.SUB))
    return g.titled("IPアドレス", b)


@register("商標権")
def fig_商標権():
    b = [g.t(105, 95, "™", 52, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(220, 95, "®", 52, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(105, 136, "商標(登録前)", 9.5, g.SUB),
         g.t(220, 136, "登録商標", 9.5, g.SUB),
         g.t(160, 168, "商品・サービスを見分ける標識を守る権利", 10.5),
         g.t(160, 186, "特許庁への登録で発生する", 10.5, g.ACCENT)]
    return g.titled("商標権", b)


@register("共通鍵暗号")
def fig_共通鍵暗号():
    b = [g.t(60, 84, "送信者", 10, g.INK),
         g.t(60, 122, "A", 14, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.rect(150, 104, 20, 18, g.INK, 1.4, g.FILL2),
         g.path("M146,104 A14,14 0 0 1 174,104", g.INK, 1.8),
         g.t(160, 112, "同じ鍵", 11, g.ACCENT),
         g.t(260, 84, "受信者", 10, g.INK),
         g.t(260, 122, "A", 14, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.arrow(84, 103, 118, 103, g.INK, 1.4),
         g.arrow(204, 103, 238, 103, g.INK, 1.4),
         g.t(160, 164, "暗号化と復号に同じ鍵を使う方式", 10.5),
         g.t(160, 182, "鍵をどう渡すかが課題", 10.5, g.ACCENT)]
    return g.titled("共通鍵暗号", b)


@register("クライアントサーバシステム")
def fig_クライアントサーバシステム():
    b = [g.rect(118, 42, 84, 58, g.INK, 1.6, g.FILL2),
         g.t(160, 66, "サーバ", 12, g.ACCENT),
         g.t(160, 84, "データ提供", 9, g.SUB),
         g.rect(40, 138, 64, 42, g.INK, 1.3, g.FILL),
         g.rect(128, 138, 64, 42, g.INK, 1.3, g.FILL),
         g.rect(216, 138, 64, 42, g.INK, 1.3, g.FILL),
         g.t(72, 162, "クライアント", 8.5, g.INK),
         g.t(160, 162, "クライアント", 8.5, g.INK),
         g.t(248, 162, "クライアント", 8.5, g.INK),
         g.line(160, 100, 84, 136, g.INK, 1.3), g.line(160, 100, 160, 136, g.INK, 1.3),
         g.line(160, 100, 236, 136, g.INK, 1.3),
         g.t(160, 194, "サービスを求める側と提供する側に分かれる構成", 9.5)]
    return g.titled("クライアントサーバシステム", b)


@register("アポストロフィ")
def fig_アポストロフィ():
    b = []
    b += _chem_box(52, 76, 84, 42, "do not", size=13)
    b += _chem_box(160, 76, 108, 42, "don't", size=14, fill=g.FILL2, color=g.ACCENT)
    b += [g.arrow(140, 97, 156, 97, g.ACCENT, 1.6),
          g.t(214, 66, "'", 30, g.ACCENT, "middle", g.MATHFONT, "700"),
          g.t(160, 150, "短縮形で抜けた文字の代わりに置く", 10.5),
          g.t(160, 170, "例: I am → I'm, it is → it's", 11, g.ACCENT),
          g.t(160, 190, "所有を表す 's とは別の使い方", 9.5, g.SUB)]
    return g.titled("アポストロフィ", b)


@register("コンマ")
def fig_コンマ():
    b = [g.t(160, 84, "A, B, and C", 22, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 140, "文中の区切り・並べるときに使う「,」", 11),
         g.t(160, 162, "例: apples, oranges, and bananas", 10.5, g.ACCENT),
         g.t(160, 186, "数字の位取りにも使う(1,000)", 10, g.SUB)]
    return g.titled("コンマ", b)


@register("立ち泳ぎ")
def fig_立ち泳ぎ():
    b = [g.rect(40, 150, 240, 4, g.INK, 0, g.FILL),
         g.line(160, 52, 160, 150, g.INK, 2.2),
         g.circle(160, 40, 12, g.INK, 2.0, g.FILL),
         g.line(160, 64, 130, 82, g.INK, 2.0), g.line(160, 64, 190, 82, g.INK, 2.0),
         g.line(160, 96, 130, 78, g.INK, 2.0), g.line(160, 96, 190, 78, g.INK, 2.0),
         g.line(160, 118, 138, 142, g.INK, 2.0), g.line(160, 118, 182, 142, g.INK, 2.0),
         g.t(160, 172, "水に立った姿勢で頭を出して泳ぐ", 10.5),
         g.t(160, 188, "手と足を動かして浮き続ける", 10, g.ACCENT)]
    return g.titled("立ち泳ぎ", b)


# ---- 国語 / 社会 -------------------------------------------------------


@register("形声文字")
def fig_形声文字():
    b = []
    b += _chem_box(52, 66, 76, 52, "氵", size=20, fill=g.FILL)
    b += _chem_box(160, 66, 76, 52, "青", size=20, fill=g.FILL2, color=g.ACCENT)
    b += _chem_box(268, 66, 44, 52, "清", size=20, fill="#ffffff", stroke=g.ACCENT, color=g.ACCENT)
    b += [g.line(132, 92, 156, 92, g.ACCENT, 1.4), g.line(240, 92, 264, 92, g.ACCENT, 1.4),
          g.t(90, 134, "意味(形)", 9.5, g.INK),
          g.t(198, 134, "音(声)", 9.5, g.ACCENT),
          g.t(160, 164, "意味を表す部分と音を表す部分でできた漢字", 10.5),
          g.t(160, 182, "例: 清・晴・情(青は音を表す)", 10.5, g.ACCENT),
          g.t(160, 196, "漢字の約8割が形声文字", 9.5, g.SUB)]
    return g.titled("形声文字", b)


@register("春望")
def fig_春望():
    lines = ["国破山河在", "城春草木深", "感時花濺涙", "恨別鳥驚心",
             "烽火連三月", "家書抵万金", "白頭掻更短", "渾欲不勝簪"]
    b = [g.t(160, 42, "杜甫「春望」", 11, g.SUB)]
    for i, ln in enumerate(lines):
        x = 74 + (i % 4) * 58
        y = 70 + (i // 4) * 40
        b += _chem_box(x, y - 14, 46, 30, ln, size=10)
    b.append(g.t(160, 172, "五言律詩 — 五文字×八句", 11))
    b.append(g.t(160, 190, "乱世の悲しみを春の景色に重ねて詠む", 10, g.ACCENT))
    return g.titled("春望", b)


@register("字形")
def fig_字形():
    b = []
    b += _chem_box(52, 62, 80, 44, "へん", size=13, fill=g.FILL)
    b += _chem_box(52, 118, 80, 44, "つくり", size=13, fill=g.FILL2, color=g.ACCENT)
    b += _chem_box(180, 62, 80, 44, "かんむり", size=12, fill=g.FILL)
    b += _chem_box(180, 118, 80, 44, "あし", size=12, fill=g.FILL2, color=g.ACCENT)
    b += [g.t(160, 172, "漢字の組み立て方(部分の形)", 11),
          g.t(160, 190, "例: 「清」= 氵(へん) + 青(つくり)", 10.5, g.ACCENT)]
    return g.titled("字形", b)


@register("点画")
def fig_点画():
    b = [g.path("M70,70 L210,70", g.INK, 5),
         g.t(140, 86, "横画", 9.5, g.SUB),
         g.path("M150,60 L150,150", g.INK, 5),
         g.t(162, 106, "縦画", 9.5, g.SUB),
         g.path("M60,120 Q90,120 120,92", g.INK, 4),
         g.t(52, 132, "払い", 9.5, g.SUB),
         g.path("M230,110 Q238,86 252,80", g.INK, 5),
         g.t(246, 122, "点", 9.5, g.SUB),
         g.t(160, 172, "漢字を構成する線の一つ一つ", 11),
         g.t(160, 190, "横画・縦画・払い・はね・点など", 10.5, g.ACCENT)]
    return g.titled("点画", b)


@register("比較生産費説")
def fig_比較生産費説():
    b = [g.t(80, 40, "ポルトガル", 10, g.INK),
         g.t(240, 40, "イギリス", 10, g.INK),
         g.t(80, 60, "布 1 | 酒 1", 9, g.SUB),
         g.t(240, 60, "布 2 | 酒 1/2", 9, g.SUB),
         g.line(48, 80, 112, 80, g.INK, 1.4), g.line(208, 80, 272, 80, g.INK, 1.4),
         g.rect(48, 90, 64, 60, g.INK, 1.3, g.FILL),
         g.rect(208, 90, 64, 60, g.INK, 1.3, g.FILL2),
         g.t(80, 116, "布に特化", 10, g.ACCENT),
         g.t(240, 116, "酒に特化", 10, g.ACCENT),
         g.arrow(120, 120, 200, 120, g.ACCENT, 1.8),
         g.t(160, 134, "交換", 9.5, g.ACCENT),
         g.t(160, 172, "両国が得意な財に特化して交換すると得", 10.5),
         g.t(160, 190, "リカードの国際分業論", 10.5, g.ACCENT)]
    return g.titled("比較生産費説", b)


@register("鎌倉幕府")
def fig_鎌倉幕府():
    b = [g.t(160, 40, "将軍", 13, g.INK),
         g.arrow(160, 50, 160, 68, g.INK, 1.4),
         g.t(160, 84, "御家人", 12, g.ACCENT),
         g.rect(52, 100, 216, 30, g.INK, 1.2, g.FILL),
         g.t(160, 120, "奉公(いざ鎌倉)・御恩(領地)", 9.5, g.ACCENT),
         g.rect(40, 148, 72, 28, g.INK, 1.2, g.FILL2),
         g.rect(124, 148, 72, 28, g.INK, 1.2, g.FILL2),
         g.rect(208, 148, 72, 28, g.INK, 1.2, g.FILL2),
         g.t(76, 166, "侍所", 9.5), g.t(160, 166, "問注所", 9.5), g.t(244, 166, "政所", 9.5),
         g.t(160, 192, "御恩と奉公の主従関係で成り立つ", 10, g.SUB)]
    return g.titled("鎌倉幕府", b)


if __name__ == "__main__":
    main()
