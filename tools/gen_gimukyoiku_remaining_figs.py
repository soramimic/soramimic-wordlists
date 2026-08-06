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


# ---- 理科(画像なし32語) ----------------------------------------------------


@register("酸化")
def fig_酸化():
    b = []
    b += _chem_box(70, 56, 96, 46, "銅 Cu", size=13, fill=g.FILL)
    b += _chem_box(70, 126, 96, 46, "酸化銅 CuO", size=12, fill=g.FILL2, color=g.ACCENT)
    b += [g.arrow(70, 80, 70, 122, g.ACCENT, 1.6),
          g.t(88, 102, "酸素と化合", 9, g.ACCENT),
          g.t(170, 79, "O₂", 13, g.ACCENT, "middle", g.MATHFONT, "700"),
          g.t(160, 176, "物質が酸素と結びつく反応", 10.5),
          g.t(160, 192, "例: 燃焼・錆び(鉄の酸化)", 10.5, g.ACCENT)]
    return g.titled("酸化", b)


@register("下降気流")
def fig_下降気流():
    b = [g.rect(60, 40, 200, 130, g.INK, 1.3, g.FILL),
         g.t(160, 176, "下降気流", 10, g.SUB)]
    for x in (95, 160, 225):
        b.append(g.arrow(x, 52, x, 156, g.ACCENT, 2.2))
    b.append(g.t(160, 92, "空気が", 10.5, g.INK))
    b.append(g.t(160, 112, "下へ動く", 10.5, g.INK))
    b.append(g.t(160, 194, "晴れやすい・高気圧の中心付近", 10, g.ACCENT))
    return g.titled("下降気流", b)


@register("運動方程式")
def fig_運動方程式():
    b = [g.rect(96, 84, 88, 52, g.INK, 2.0, g.FILL),
         g.t(140, 116, "m", 18, g.INK, "middle", g.MATHFONT, "700"),
         g.arrow(196, 110, 252, 110, g.ACCENT, 3.0),
         g.t(236, 102, "F", 15, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 158, "F = ma", 16, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 178, "力 = 質量 × 加速度", 10.5),
         g.t(160, 194, "物体に力が働くと加速度が生じる", 9.5, g.SUB)]
    return g.titled("運動方程式", b)


@register("等速円運動")
def fig_等速円運動():
    b = [g.circle(160, 100, 62, g.INK, 1.8),
         g.dot(160, 100, 3.0, g.ACCENT),
         g.t(148, 92, "O", 10, g.ACCENT),
         g.arrow(160, 100, 210, 60, g.INK, 1.5),
         g.t(196, 52, "v", 11, g.INK, "middle", g.MATHFONT, "700"),
         g.arrow(210, 60, 230, 96, g.ACCENT, 1.6),
         g.t(232, 92, "速さ一定", 9, g.ACCENT),
         g.t(160, 180, "速さは変わらず向きが変わる運動", 10.5),
         g.t(160, 194, "向きの変化 = 円の中心への加速度", 10, g.ACCENT)]
    return g.titled("等速円運動", b)


@register("向心力")
def fig_向心力():
    b = [g.circle(160, 100, 60, g.INK, 1.8),
         g.dot(160, 100, 3.0, g.ACCENT),
         g.t(148, 92, "O", 10, g.ACCENT),
         g.dot(210, 70, 3.2, g.INK),
         g.arrow(210, 70, 172, 93, g.ACCENT, 2.2),
         g.t(196, 70, "向心力", 9.5, g.ACCENT),
         g.arrow(210, 70, 232, 42, g.INK, 1.4),
         g.t(230, 40, "v", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 178, "円運動を続けさせる中心向きの力", 10.5),
         g.t(160, 194, "例: ひもの先の玉・惑星の公転", 10, g.ACCENT)]
    return g.titled("向心力", b)


@register("静電誘導")
def fig_静電誘導():
    b = [g.rect(40, 76, 96, 44, g.INK, 1.4, "#ffffff"),
         g.rect(184, 76, 96, 44, g.INK, 1.4, "#ffffff"),
         g.t(88, 84, "−", 13, g.ACCENT), g.t(88, 106, "+", 13, g.ACCENT),
         g.t(232, 84, "−", 13, g.ACCENT), g.t(232, 106, "+", 13, g.ACCENT),
         g.t(160, 80, "導体", 10, g.INK),
         g.rect(214, 56, 34, 14, g.ACCENT, 0, "#f3ddd3"),
         g.t(231, 50, "＋", 12, g.ACCENT),
         g.t(160, 148, "帯電体を近づけると", 10.5),
         g.t(160, 166, "反対の電荷が近い側に現れる", 10.5, g.ACCENT),
         g.t(160, 188, "接地すると帯電体と同符号が逃げる", 9.5, g.SUB)]
    return g.titled("静電誘導", b)


@register("キルヒホッフの法則")
def fig_キルヒホッフの法則():
    b = [g.line(80, 110, 120, 110, g.INK, 2.0),
         g.line(120, 110, 120, 58, g.INK, 2.0), g.line(120, 110, 120, 162, g.INK, 2.0),
         g.line(120, 58, 240, 58, g.INK, 2.0), g.line(120, 162, 240, 162, g.INK, 2.0),
         g.line(240, 58, 240, 110, g.INK, 2.0), g.line(240, 162, 240, 110, g.INK, 2.0),
         g.line(240, 110, 280, 110, g.INK, 2.0),
         g.arrow(90, 110, 116, 110, g.ACCENT, 1.6),
         g.arrow(122, 62, 122, 104, g.ACCENT, 1.6),
         g.arrow(122, 158, 122, 116, g.ACCENT, 1.6),
         g.t(88, 122, "I₁", 11, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(136, 76, "I₂", 11, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(136, 144, "I₃", 11, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 178, "I₁ = I₂ + I₃(電流の保存)", 11, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 194, "回路の任意の閉路で電圧の和は0", 10, g.SUB)]
    return g.titled("キルヒホッフの法則", b)


@register("自己誘導")
def fig_自己誘導():
    b = [g.path("M60,100 C120,40 200,40 260,100 C200,160 120,160 60,100", g.INK, 2.0),
         g.arrow(60, 100, 44, 100, g.ACCENT, 1.8),
         g.t(34, 108, "I", 11, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 52, "コイル", 10.5, g.INK),
         g.t(160, 172, "流れる電流の変化を妨げる向きに", 10.5),
         g.t(160, 188, "起電力が生じる現象", 10.5, g.ACCENT),
         g.t(160, 202, "インダクタンス(コイルの性質)", 9.5, g.SUB)]
    return g.titled("自己誘導", b)


@register("モル濃度")
def fig_モル濃度():
    b = [g.rect(70, 50, 120, 110, g.INK, 1.6, g.FILL),
         g.line(70, 78, 190, 78, g.INK, 1.0),
         g.t(130, 66, "溶質 n mol", 10, g.ACCENT),
         g.t(130, 118, "溶液 V L", 10, g.INK),
         g.t(160, 176, "モル濃度 = n / V (mol/L)", 11.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 194, "1Lの溶液に溶けている物質量", 10, g.SUB)]
    return g.titled("モル濃度", b)


@register("電気陰性度")
def fig_電気陰性度():
    b = [g.rect(58, 44, 204, 92, g.INK, 1.3, g.FILL),
         g.t(160, 68, "周期表で右上ほど大きい", 10.5),
         g.t(160, 100, "F > O > N > Cl…", 13, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.arrow(160, 116, 160, 148, g.ACCENT, 1.8),
         g.t(176, 134, "大きい方へ電子が引き寄せられる", 9.5, g.ACCENT),
         g.t(160, 180, "共有電子対を引きつける強さ", 10.5),
         g.t(160, 194, "差が大きいとイオン結合に近づく", 9.5, g.SUB)]
    return g.titled("電気陰性度", b)


@register("還元剤")
def fig_還元剤():
    b = [g.t(160, 54, "Zn → Zn²⁺ + 2e⁻", 13, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.arrow(160, 70, 160, 96, g.INK, 1.6),
         g.t(160, 88, "電子を渡す", 9.5, g.ACCENT),
         g.t(160, 118, "相手を還元する物質", 11.5),
         g.rect(78, 136, 164, 40, g.INK, 1.3, g.FILL),
         g.t(160, 158, "自身は酸化される(Zn → Zn²⁺)", 10.5),
         g.t(160, 192, "例: 亜鉛・鉄・硫化水素", 10, g.SUB)]
    return g.titled("還元剤", b)


@register("イオン化傾向")
def fig_イオン化傾向():
    order = "K Ca Na Mg Al Zn Fe Ni Sn Pb (H) Cu Hg Ag Pt Au"
    b = [g.rect(36, 52, 248, 34, g.INK, 1.3, g.FILL),
         g.t(160, 73, "大きい ← イオン化傾向 → 小さい", 10.5, g.INK),
         g.t(160, 106, order, 12, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 132, "左ほどイオンになりやすい(錆びやすい)", 10.5),
         g.t(160, 152, "右の金属は左の金属のイオンを析出させる", 10),
         g.t(160, 176, "H より左: 酸と反応して水素を発生", 10, g.ACCENT),
         g.t(160, 194, "Cu Hg Ag Pt Au はイオン化しにくい(貴金属)", 9.5, g.SUB)]
    return g.titled("イオン化傾向", b)


@register("酸化還元滴定")
def fig_酸化還元滴定():
    b = [g.rect(236, 44, 44, 52, g.INK, 1.2, "#ffffff"),
         g.rect(238, 48, 40, 8, g.INK, 0, g.FILL),
         g.path("M216,100 L300,100 L286,96", g.INK, 1.4),
         g.path("M286,96 Q280,104 274,96", g.INK, 1.2),
         g.line(258, 96, 258, 110, g.INK, 1.2),
         g.rect(64, 110, 192, 52, g.INK, 1.5, g.FILL),
         g.t(160, 132, "被滴定液(還元剤)", 10, g.INK),
         g.t(160, 148, "色の変化で終点を判断", 10, g.ACCENT),
         g.t(160, 180, "酸化剤の滴下量から濃度を求める", 10.5),
         g.t(160, 196, "例: 過マンガン酸カリウム滴定", 10, g.ACCENT)]
    return g.titled("酸化還元滴定", b)


@register("電離平衡")
def fig_電離平衡():
    b = [g.t(160, 54, "CH₃COOH ⇌ CH₃COO⁻ + H⁺", 13.5, g.INK, "middle", g.MATHFONT, "700"),
         g.arrow(108, 84, 152, 84, g.INK, 1.6), g.arrow(168, 84, 212, 84, g.INK, 1.6),
         g.t(130, 78, "電離", 9.5, g.ACCENT), g.t(190, 78, "再結合", 9.5, g.ACCENT),
         g.t(160, 118, "電離と再結合が釣り合った状態", 10.5),
         g.t(160, 140, "弱酸・弱塩基では電離が一部だけ進む", 10),
         g.t(160, 164, "H⁺の濃度でpHが決まる", 10, g.ACCENT),
         g.t(160, 192, "例: 酢酸・アンモニア水", 9.5, g.SUB)]
    return g.titled("電離平衡", b)


@register("緩衝液")
def fig_緩衝液():
    b = [g.rect(60, 48, 200, 64, g.INK, 1.5, g.FILL),
         g.t(160, 76, "緩衝液", 12, g.INK),
         g.t(160, 96, "pHがほぼ一定", 10.5, g.ACCENT),
         g.arrow(84, 124, 84, 152, g.ACCENT, 1.6),
         g.arrow(236, 124, 236, 152, g.ACCENT, 1.6),
         g.t(60, 142, "酸(H⁺)を加えても", 9.5, g.ACCENT),
         g.t(250, 142, "塩基を加えても", 9.5, g.ACCENT),
         g.t(160, 176, "pHの急変を抑える溶液", 11),
         g.t(160, 192, "例: 血液・酢酸+酢酸ナトリウム", 10, g.ACCENT)]
    return g.titled("緩衝液", b)


@register("ルシャトリエの原理")
def fig_ルシャトリエの原理():
    b = [g.t(160, 48, "N₂ + 3H₂ ⇌ 2NH₃", 13, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 76, 240, 52, g.INK, 1.3, g.FILL),
         g.t(160, 96, "平衡にある系に変化(圧力・温度等)を加えると", 9.5),
         g.t(160, 114, "その変化を打ち消す向きに平衡が移動", 10.5, g.ACCENT),
         g.t(160, 150, "高圧 → 分子数が減る向き(NH₃側)へ", 10.5),
         g.t(160, 172, "低温 → 発熱の向きへ", 10.5),
         g.t(160, 194, "化学工業(ハーバー法など)の原理", 10, g.SUB)]
    return g.titled("ルシャトリエの原理", b)


@register("平衡定数")
def fig_平衡定数():
    b = [g.t(160, 56, "aA + bB ⇌ cC + dD", 13, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 96, "[C]ᶜ [D]ᵈ", 16, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 124, "K = ───────", 16, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 150, "[A]ᵃ [B]ᵇ", 16, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 176, "温度一定なら濃度によらず一定", 10.5),
         g.t(160, 194, "Kが大きいほど生成物側に偏る", 10, g.ACCENT)]
    return g.titled("平衡定数", b)


@register("官能基")
def fig_官能基():
    b = []
    for i, (group, name, ex) in enumerate([("−OH", "ヒドロキシ基", "アルコール"),
                                           ("−COOH", "カルボキシ基", "カルボン酸"),
                                           ("−CHO", "ホルミル基", "アルデヒド")]):
        x = 46 + i * 90
        b += _chem_box(x, 56, 72, 40, group, size=12, fill=g.FILL)
        b += [g.t(x + 36, 112, name, 9.5, g.INK), g.t(x + 36, 128, ex, 9, g.ACCENT)]
    b += [g.t(160, 162, "化合物の性質を決める特徴的な原子団", 10.5),
          g.t(160, 182, "アミノ基(−NH₂)・カルボニル基(−CO−)など", 10, g.ACCENT)]
    return g.titled("官能基", b)


@register("芳香族化合物")
def fig_芳香族化合物():
    b = [g.poly([(120, 62), (158, 44), (196, 62), (196, 104), (158, 122), (120, 104)], g.INK, 1.8, g.FILL),
         g.circle(158, 83, 18, g.ACCENT, 1.5),
         g.t(158, 154, "ベンゼン環(六角形)", 10.5),
         g.t(158, 174, "独特の芳香をもつ炭化水素", 10.5),
         g.t(158, 192, "例: ベンゼン・ナフタレン・トルエン", 10, g.ACCENT)]
    return g.titled("芳香族化合物", b)


@register("ATP")
def fig_ATP():
    b = [g.rect(48, 44, 224, 44, g.INK, 1.4, g.FILL),
         g.t(160, 60, "アデニン + リボース", 10, g.INK),
         g.t(160, 78, "〜P 〜P 〜P(高エネルギーリン酸結合)", 10, g.ACCENT),
         g.arrow(160, 96, 160, 122, g.ACCENT, 1.8),
         g.t(176, 112, "加水分解でエネルギー放出", 9.5, g.ACCENT),
         g.t(160, 146, "ATP → ADP + リン酸 + エネルギー", 10.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 172, "細胞のエネルギー通貨", 11),
         g.t(160, 192, "筋肉・合成反応などに使われる", 10, g.SUB)]
    return g.titled("ATP", b)


@register("恒常性")
def fig_恒常性():
    b = [g.rect(34, 42, 64, 40, g.INK, 1.3, g.FILL),
         g.rect(128, 42, 64, 40, g.INK, 1.3, g.FILL),
         g.rect(222, 42, 64, 40, g.INK, 1.3, g.FILL),
         g.t(66, 60, "変化", 9.5), g.t(66, 74, "(刺激)", 8.5, g.SUB),
         g.t(160, 60, "受容器", 9.5), g.t(160, 74, "(検出)", 8.5, g.SUB),
         g.t(254, 60, "調節", 9.5), g.t(254, 74, "(応答)", 8.5, g.SUB),
         g.arrow(102, 62, 124, 62, g.INK, 1.4), g.arrow(196, 62, 218, 62, g.INK, 1.4),
         g.t(160, 110, "体内の状態を一定に保つ働き", 10.5),
         g.t(160, 132, "例: 体温・血糖・水分量の調節", 10, g.ACCENT),
         g.t(160, 156, "ホルモンと神経が協力して行う", 10),
         g.t(160, 180, "フィードバック調節(負の)が基本", 10, g.ACCENT),
         g.t(160, 198, "ホメオスタシス", 9.5, g.SUB)]
    return g.titled("恒常性", b)


@register("グルカゴン")
def fig_グルカゴン():
    b = [g.rect(38, 50, 104, 52, g.INK, 1.3, g.FILL),
         g.rect(178, 50, 104, 52, g.INK, 1.3, g.FILL2),
         g.t(90, 70, "血糖値が", 9.5), g.t(90, 86, "低い", 9.5, g.ACCENT),
         g.t(230, 70, "グルカゴン分泌", 9.5), g.t(230, 86, "(すい臓α細胞)", 9, g.SUB),
         g.arrow(146, 76, 174, 76, g.ACCENT, 1.8),
         g.t(160, 118, "肝臓のグリコーゲンを分解", 10.5, g.ACCENT),
         g.t(160, 140, "→ 血糖値を上げるホルモン", 10.5),
         g.t(160, 166, "インスリン(下げる)と対になる", 10),
         g.t(160, 188, "すい臓から分泌され血糖を調節", 10, g.SUB)]
    return g.titled("グルカゴン", b)


@register("フィードバック調節")
def fig_フィードバック調節():
    b = [g.rect(40, 56, 96, 44, g.INK, 1.3, g.FILL),
         g.rect(184, 56, 96, 44, g.INK, 1.3, g.FILL),
         g.t(88, 78, "変化を感知", 10), g.t(232, 78, "もとに戻す", 10, g.ACCENT),
         g.arrow(140, 78, 180, 78, g.INK, 1.8),
         g.path("M232,100 Q232,150 88,150 Q44,150 44,110", g.ACCENT, 1.4, dash="4 3"),
         g.t(160, 164, "結果が入力を打ち消す仕組み", 10.5),
         g.t(160, 184, "負のフィードバック(恒常性の土台)", 10.5, g.ACCENT),
         g.t(160, 202, "例: 体温調節・血糖調節", 9.5, g.SUB)]
    return g.titled("フィードバック調節", b)


@register("抗原抗体反応")
def fig_抗原抗体反応():
    b = [g.circle(80, 84, 26, g.INK, 1.8, g.FILL2),
         g.t(80, 88, "抗原", 9.5, g.ACCENT),
         g.t(160, 60, "抗体", 9.5, g.SUB),
         g.path("M160,60 L118,88 M160,60 L118,104", g.INK, 1.5),
         g.path("M160,60 L210,62 M160,60 L214,74", g.INK, 1.5),
         g.t(160, 132, "抗体が抗原に特異的に結合", 10.5),
         g.t(160, 154, "抗原を無毒化・排除する", 10.5, g.ACCENT),
         g.t(160, 178, "免疫のしくみ(鍵と鍵穴)", 10),
         g.t(160, 198, "ワクチンは抗体産生を促す", 9.5, g.SUB)]
    return g.titled("抗原抗体反応", b)


@register("窒素固定")
def fig_窒素固定():
    b = [g.t(160, 44, "N₂(空気中)", 11, g.INK),
         g.arrow(160, 54, 160, 76, g.ACCENT, 1.6),
         g.t(176, 66, "根粒菌など", 9, g.ACCENT),
         g.t(160, 96, "NH₃ / 硝酸", 12, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.arrow(160, 106, 160, 128, g.INK, 1.6),
         g.t(160, 146, "植物が吸収 → タンパク質に", 10.5),
         g.t(160, 170, "空気中の窒素を利用できる形に変える", 10.5),
         g.t(160, 192, "マメ科植物の根粒菌・放電・化学肥料", 10, g.ACCENT)]
    return g.titled("窒素固定", b)


@register("放射年代")
def fig_放射年代():
    b = [g.line(50, 130, 270, 130, g.SUB, 1.2),
         g.line(50, 130, 50, 60, g.SUB, 1.2),
         g.t(42, 52, "親核種", 9, g.SUB), g.t(278, 134, "時間", 9, g.SUB),
         g.path("M50,126 Q120,80 250,74", g.ACCENT, 2.2),
         g.dot(50, 126, 3.0, g.ACCENT),
         g.line(150, 130, 150, 76, g.INK, 1.0, dash="3 3"),
         g.t(138, 66, "半減期", 9.5, g.ACCENT),
         g.t(160, 168, "放射性同位体が半分に減る時間", 10.5),
         g.t(160, 188, "例: 炭素14(約5730年)・ウラン", 10, g.ACCENT),
         g.t(160, 204, "化石・岩石の年代測定に使う", 9.5, g.SUB)]
    return g.titled("放射年代", b)


@register("絶対等級")
def fig_絶対等級():
    b = [g.dot(90, 96, 4.0, g.ACCENT), g.dot(230, 96, 3.0, g.ACCENT),
         g.line(60, 120, 260, 120, g.INK, 1.2),
         g.t(90, 84, "明るい", 9.5, g.ACCENT), g.t(230, 84, "暗い", 9.5, g.ACCENT),
         g.t(90, 110, "10パーセク(約32.6光年)", 9, g.SUB),
         g.t(160, 146, "どの星も同じ距離(10pc)に置いたと", 10.5),
         g.t(160, 164, "仮定したときの明るさ", 10.5, g.ACCENT),
         g.t(160, 186, "見かけの等級と区別する", 10),
         g.t(160, 204, "星本来の明るさの比較に使う", 9.5, g.SUB)]
    return g.titled("絶対等級", b)


@register("原子の構造")
def fig_原子の構造():
    b = [g.circle(160, 95, 16, g.INK, 1.5, g.FILL2),
         g.t(160, 100, "+", 13, g.ACCENT),
         g.circle(160, 95, 62, g.INK, 1.2)]
    for x, y in [(118, 58), (218, 74), (232, 128), (88, 148), (98, 60), (222, 154)]:
        b.append(g.circle(x, y, 4.0, g.INK, 1.0, g.ACCENT))
        b.append(g.t(x, y - 8, "e⁻", 8, g.ACCENT))
    b.append(g.t(160, 66, "原子核(陽子+中性子)", 9.5, g.INK))
    b.append(g.t(160, 176, "中心に原子核、周りを電子が回る", 10.5))
    b.append(g.t(160, 194, "陽子の数 = 電子の数(電気的に中性)", 10, g.ACCENT))
    return g.titled("原子の構造", b)


@register("原子量")
def fig_原子量():
    b = [g.t(160, 52, "¹²C = 12 を基準", 12, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 84, "H = 1.0,  O = 16,  Cl = 35.5", 12, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 118, "相対質量の平均値", 11),
         g.t(160, 142, "同位体の存在比を考慮", 10.5, g.ACCENT),
         g.t(160, 170, "例: 塩素 Cl = 35Cl(75%) + 37Cl(25%)", 10),
         g.t(160, 194, "→ 35.5 になる", 10, g.ACCENT, "middle", g.MATHFONT, "700")]
    return g.titled("原子量", b)


@register("音色")
def fig_音色():
    b = [g.path("M40,110 Q90,50 140,110 Q190,170 240,110", g.INK, 2.0),
         g.path("M40,150 Q90,110 140,150 Q190,190 240,150", g.ACCENT, 2.0),
         g.t(140, 70, "波形の形の違い", 9.5, g.ACCENT),
         g.t(160, 176, "同じ高さ・大きさでも", 10.5),
         g.t(160, 194, "波形が違うと音色が変わる", 10.5, g.ACCENT),
         g.t(160, 210, "倍音の含まれ方の違い", 9.5, g.SUB)]
    return g.titled("音色", b)


@register("ニホニウム")
def fig_ニホニウム():
    b = [g.rect(150, 40, 48, 48, g.INK, 1.6, g.FILL2),
         g.t(174, 56, "113", 13, g.ACCENT),
         g.t(174, 76, "Nh", 15, g.INK, "middle", g.MATHFONT, "700"),
         g.t(174, 112, "ニホニウム", 10, g.INK),
         g.t(160, 144, "日本で発見された最初の元素", 10.5),
         g.t(160, 164, "理化学研究所(2004年合成)", 10),
         g.t(160, 186, "2016年に正式名称が「ニホニウム」に", 10, g.ACCENT),
         g.t(160, 204, "人工元素・超重元素", 9.5, g.SUB)]
    return g.titled("ニホニウム", b)


@register("水酸化物イオン")
def fig_水酸化物イオン():
    b = [g.circle(108, 92, 24, g.INK, 1.6, g.FILL2),
         g.t(108, 97, "O", 13, g.INK, "middle", g.MATHFONT, "700"),
         g.circle(176, 92, 13, g.INK, 1.4, g.FILL),
         g.t(176, 97, "H", 11, g.INK, "middle", g.MATHFONT, "700"),
         g.line(132, 92, 163, 92, g.INK, 2.0),
         g.t(160, 60, "OH⁻", 17, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 128, "1価の陰イオン", 10.5),
         g.t(160, 150, "塩基性(アルカリ性)の原因", 10.5, g.ACCENT),
         g.t(160, 174, "酸とはH⁺と結合して水になる", 10),
         g.t(160, 194, "例: NaOH → Na⁺ + OH⁻", 10, g.ACCENT, "middle", g.MATHFONT, "700")]
    return g.titled("水酸化物イオン", b)


# ---- 保健体育(画像なし17語) -------------------------------------------------


@register("ストレス対処")
def fig_ストレス対処():
    b = [g.t(160, 46, "ストレス(心身への負担)", 11, g.INK),
         g.arrow(160, 58, 160, 82, g.INK, 1.6),
         g.rect(40, 88, 80, 44, g.INK, 1.3, g.FILL),
         g.rect(120, 88, 80, 44, g.INK, 1.3, g.FILL),
         g.rect(200, 88, 80, 44, g.INK, 1.3, g.FILL2),
         g.t(80, 108, "運動・趣味", 10, g.ACCENT),
         g.t(160, 108, "休息・睡眠", 10, g.ACCENT),
         g.t(240, 108, "相談する", 10, g.ACCENT),
         g.t(160, 156, "自分に合った方法で発散・対処する", 10.5),
         g.t(160, 178, "ストレスをためすぎない生活", 10),
         g.t(160, 198, "コーピング(対処法)の工夫", 9.5, g.SUB)]
    return g.titled("ストレス対処", b)


@register("職業病")
def fig_職業病():
    b = [g.rect(44, 52, 96, 52, g.INK, 1.4, g.FILL),
         g.rect(180, 52, 96, 52, g.INK, 1.4, g.FILL2),
         g.t(92, 74, "職場の環境", 10, g.INK), g.t(92, 90, "(騒音・粉じん等)", 8.5, g.SUB),
         g.t(228, 74, "健康被害", 10, g.ACCENT), g.t(228, 90, "(難聴・じん肺等)", 8.5, g.SUB),
         g.arrow(144, 78, 176, 78, g.ACCENT, 1.8),
         g.t(160, 126, "仕事に起因して起こる病気", 10.5),
         g.t(160, 148, "例: じん肺・騒音性難聴・腰痛", 10, g.ACCENT),
         g.t(160, 172, "労災認定の対象", 10),
         g.t(160, 194, "予防: 作業環境の改善・保護具", 9.5, g.SUB)]
    return g.titled("職業病", b)


@register("ヘルスプロモーション")
def fig_ヘルスプロモーション():
    b = [g.rect(30, 44, 84, 88, g.INK, 1.3, g.FILL),
         g.rect(118, 44, 84, 88, g.INK, 1.3, g.FILL),
         g.rect(206, 44, 84, 88, g.INK, 1.3, g.FILL2),
         g.t(72, 78, "健康な", 9.5), g.t(72, 94, "環境づくり", 9.5, g.ACCENT),
         g.t(160, 78, "住民参加", 9.5), g.t(160, 94, "(ヘルスケア)", 9, g.ACCENT),
         g.t(248, 78, "個人の", 9.5), g.t(248, 94, "能力向上", 9.5, g.ACCENT),
         g.t(160, 156, "人々が健康を管理・改善できるように", 10.5),
         g.t(160, 176, "社会全体で支援する考え方", 10.5, g.ACCENT),
         g.t(160, 198, "WHOが提唱(1986年オタワ憲章)", 9.5, g.SUB)]
    return g.titled("ヘルスプロモーション", b)


@register("過負荷の原則")
def fig_過負荷の原則():
    b = [g.rect(70, 52, 64, 88, g.INK, 1.3, g.FILL),
         g.rect(166, 40, 64, 100, g.INK, 1.3, g.FILL2),
         g.rect(228, 28, 64, 112, g.INK, 1.3, g.FILL),
         g.t(102, 122, "今の負荷", 9.5), g.t(198, 122, "少し上げる", 9, g.ACCENT),
         g.t(260, 122, "慣れてきたら", 9, g.ACCENT),
         g.t(160, 160, "ふだんより強い負荷をかけると", 10.5),
         g.t(160, 180, "体力が向上する", 10.5, g.ACCENT),
         g.t(160, 200, "トレーニングの3原理の一つ", 9.5, g.SUB)]
    return g.titled("過負荷の原則", b)


@register("漸進性の原則")
def fig_漸進性の原則():
    b = [g.line(50, 140, 270, 140, g.SUB, 1.2),
         g.line(50, 140, 50, 52, g.SUB, 1.2),
         g.t(30, 46, "負荷", 9, g.SUB),
         g.path("M50,136 L86,124 L122,108 L158,92 L194,74 L230,62 L266,54", g.ACCENT, 2.2),
         g.t(160, 166, "負荷を少しずつ段階的に上げる", 10.5),
         g.t(160, 186, "急に上げすぎると故障のもと", 10, g.ACCENT),
         g.t(160, 206, "トレーニングの3原理の一つ", 9.5, g.SUB)]
    return g.titled("漸進性の原則", b)


@register("特異性の原則")
def fig_特異性の原則():
    b = [g.rect(44, 50, 104, 52, g.INK, 1.3, g.FILL),
         g.rect(172, 50, 104, 52, g.INK, 1.3, g.FILL2),
         g.t(96, 72, "鍛えた能力", 10, g.INK), g.t(96, 88, "(例: 持久力)", 9, g.SUB),
         g.t(224, 72, "その能力が伸びる", 10, g.ACCENT),
         g.arrow(152, 76, 168, 76, g.ACCENT, 1.8),
         g.t(160, 126, "トレーニングの効果は", 10.5),
         g.t(160, 146, "行った内容に固有", 10.5, g.ACCENT),
         g.t(160, 170, "目的に合った種目を選ぶ", 10),
         g.t(160, 192, "トレーニングの3原理の一つ", 9.5, g.SUB)]
    return g.titled("特異性の原則", b)


@register("戦術")
def fig_戦術():
    b = [g.rect(50, 44, 220, 74, g.INK, 1.4, g.FILL),
         g.t(160, 66, "試合の目的を達成するための", 10),
         g.t(160, 88, "チーム・個人の作戦", 10.5, g.ACCENT),
         g.t(160, 130, "例: 攻撃の組み立て・守備の陣形", 10),
         g.t(160, 152, "相手の動きに応じて判断する", 10),
         g.t(160, 176, "状況に応じたプレーの選択", 10.5, g.ACCENT),
         g.t(160, 198, "技術と組み合わせて効果を発揮", 9.5, g.SUB)]
    return g.titled("戦術", b)


@register("生活習慣")
def fig_生活習慣():
    b = [g.circle(160, 98, 62, g.INK, 1.6),
         g.t(160, 40, "食事", 10.5, g.ACCENT),
         g.t(230, 68, "運動", 10.5, g.ACCENT),
         g.t(232, 128, "睡眠", 10.5, g.ACCENT),
         g.t(88, 128, "休養", 10.5, g.ACCENT),
         g.t(90, 68, "入浴", 10.5, g.ACCENT),
         g.t(160, 178, "毎日のくり返しが健康の土台", 10.5),
         g.t(160, 198, "生活習慣病の予防につながる", 10, g.ACCENT)]
    return g.titled("生活習慣", b)


@register("止血法")
def fig_止血法():
    b = [g.rect(70, 50, 120, 56, g.INK, 1.5, g.FILL2),
         g.t(130, 74, "傷口", 10, g.ACCENT),
         g.path("M70,66 Q120,44 170,62", g.ACCENT, 3.0),
         g.rect(40, 118, 180, 34, g.INK, 1.3, g.FILL),
         g.t(130, 136, "清潔な布で直接圧迫", 10, g.INK),
         g.t(160, 170, "止血の基本は直接圧迫", 10.5),
         g.t(160, 190, "圧迫止血法 → 医師の処置へ", 10, g.ACCENT),
         g.t(160, 208, "止血帯は専門家の指示で", 9.5, g.SUB)]
    return g.titled("止血法", b)


@register("保健機関")
def fig_保健機関():
    b = [g.rect(36, 42, 72, 44, g.INK, 1.3, g.FILL),
         g.rect(124, 42, 72, 44, g.INK, 1.3, g.FILL),
         g.rect(212, 42, 72, 44, g.INK, 1.3, g.FILL2),
         g.t(72, 60, "保健所", 9.5), g.t(72, 76, "(地域保健)", 8.5, g.SUB),
         g.t(160, 60, "保健センター", 9), g.t(160, 76, "(市町村)", 8.5, g.SUB),
         g.t(248, 60, "医療機関", 9.5), g.t(248, 76, "(診療)", 8.5, g.SUB),
         g.t(160, 110, "健康相談・検診・予防接種", 10),
         g.t(160, 132, "住民の健康を支える公的機関", 10.5, g.ACCENT),
         g.t(160, 156, "学校保健・産業保健も連携", 10),
         g.t(160, 180, "例: 保健所・市町村保健センター", 10, g.ACCENT),
         g.t(160, 202, "感染症対策や母子保健も担う", 9.5, g.SUB)]
    return g.titled("保健機関", b)


@register("し尿")
def fig_し尿():
    b = [g.rect(44, 50, 88, 52, g.INK, 1.4, g.FILL),
         g.rect(188, 50, 88, 52, g.INK, 1.4, g.FILL2),
         g.t(88, 72, "トイレ・浄化槽", 9.5), g.t(88, 88, "(し尿処理)", 8.5, g.SUB),
         g.t(232, 72, "きれいな水に", 9.5), g.t(232, 88, "(下水処理場)", 8.5, g.SUB),
         g.arrow(136, 76, 184, 76, g.ACCENT, 1.8),
         g.t(160, 124, "排出物を衛生的に処理する", 10.5),
         g.t(160, 146, "水質汚染の防止につながる", 10.5, g.ACCENT),
         g.t(160, 170, "浄化槽・下水道のしくみ", 10),
         g.t(160, 194, "健康と環境を守る公衆衛生", 9.5, g.SUB)]
    return g.titled("し尿", b)


@register("行動嗜癖")
def fig_行動嗜癖():
    b = [g.t(160, 48, "ゲーム・スマホ・買い物など", 10.5, g.INK),
         g.path("M160,66 Q90,84 160,102 Q230,120 160,138 Q90,156 160,166", g.ACCENT, 2.0),
         g.t(160, 178, "やめたくてもやめられない状態", 10.5, g.ACCENT),
         g.t(160, 198, "生活や健康に支障が出る", 10, g.SUB),
         g.t(160, 214, "物質(薬物)ではなく行動への依存", 9.5, g.SUB)]
    return g.titled("行動嗜癖", b)


@register("自己形成")
def fig_自己形成():
    b = [g.circle(160, 90, 30, g.INK, 1.6, g.FILL),
         g.t(160, 95, "自分", 11, g.INK),
         g.arrow(160, 126, 160, 150, g.INK, 1.6),
         g.rect(52, 154, 72, 34, g.INK, 1.2, g.FILL),
         g.rect(132, 154, 72, 34, g.INK, 1.2, g.FILL),
         g.rect(212, 154, 72, 34, g.INK, 1.2, g.FILL2),
         g.t(88, 172, "家族", 9.5), g.t(168, 172, "友人", 9.5), g.t(248, 172, "社会", 9.5),
         g.line(142, 160, 118, 122, g.SUB, 1.0, dash="3 3"),
         g.line(178, 160, 202, 122, g.SUB, 1.0, dash="3 3"),
         g.t(160, 206, "他者との関わりの中で自分をつくる", 9.5)]
    return g.titled("自己形成", b)


@register("リラクセーション")
def fig_リラクセーション():
    b = [g.path("M90,110 Q120,60 160,110 Q200,60 230,110", g.INK, 2.2),
         g.line(70, 132, 250, 132, g.SUB, 1.2, dash="3 3"),
         g.t(160, 74, "ゆったりとした呼吸", 10, g.ACCENT),
         g.t(160, 158, "心身の緊張をほぐす方法", 10.5),
         g.t(160, 180, "深呼吸・ストレッチ・入浴など", 10, g.ACCENT),
         g.t(160, 202, "ストレス解消に効果的", 9.5, g.SUB)]
    return g.titled("リラクセーション", b)


@register("休養")
def fig_休養():
    b = [g.rect(44, 56, 96, 44, g.INK, 1.3, g.FILL),
         g.rect(180, 56, 96, 44, g.INK, 1.3, g.FILL2),
         g.t(92, 78, "活動", 10), g.t(228, 78, "休養", 10, g.ACCENT),
         g.arrow(144, 78, 176, 78, g.ACCENT, 1.8),
         g.arrow(228, 104, 92, 104, g.SUB, 1.4, "both"),
         g.t(160, 124, "体と心の回復・疲労回復", 10.5),
         g.t(160, 146, "睡眠・休息・気分転換", 10, g.ACCENT),
         g.t(160, 170, "活動と休養のバランスが大切", 10),
         g.t(160, 194, "休養も健康づくりの一部", 9.5, g.SUB)]
    return g.titled("休養", b)


@register("体温調節")
def fig_体温調節():
    b = [g.rect(60, 44, 200, 44, g.INK, 1.3, g.FILL),
         g.t(160, 62, "体温(約36〜37℃)を維持", 10, g.INK),
         g.t(160, 78, "産熱と放熱のバランス", 10, g.ACCENT),
         g.t(160, 108, "暑いとき: 汗をかく・血管拡張", 10.5, g.ACCENT),
         g.t(160, 132, "寒いとき: ふるえ・血管収縮", 10.5, g.ACCENT),
         g.t(160, 158, "視床下部が調節の中枢", 10),
         g.t(160, 182, "体温の恒常性(ホメオスタシス)", 10, g.ACCENT),
         g.t(160, 204, "熱中症・低体温症は調節の破綻", 9.5, g.SUB)]
    return g.titled("体温調節", b)


@register("クオリティオブライフ")
def fig_クオリティオブライフ():
    b = [g.circle(160, 88, 54, g.INK, 1.5, g.FILL),
         g.t(160, 92, "QOL", 15, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(70, 66, "健康", 9.5, g.ACCENT), g.t(250, 66, "仕事", 9.5, g.ACCENT),
         g.t(250, 116, "家庭", 9.5, g.ACCENT), g.t(70, 116, "趣味", 9.5, g.ACCENT),
         g.t(160, 158, "生活の質・人生の豊かさ", 10.5),
         g.t(160, 180, "病気の治療でも QOL を大切にする", 10, g.ACCENT),
         g.t(160, 202, "身体的・精神的・社会的に満たされた状態", 9.5, g.SUB)]
    return g.titled("クオリティオブライフ", b)


# ---- 技術・家庭(画像なし36語) ---------------------------------------------


@register("産業財産権")
def fig_産業財産権():
    b = [g.t(160, 38, "知的財産権", 11.5, g.INK),
         g.line(130, 48, 90, 66, g.INK, 1.2), g.line(190, 48, 230, 66, g.INK, 1.2),
         g.rect(44, 70, 92, 64, g.INK, 1.4, g.FILL2),
         g.rect(184, 70, 92, 64, g.INK, 1.4, g.FILL),
         g.t(90, 90, "産業財産権", 10.5, g.ACCENT),
         g.t(90, 108, "特許・実用新案", 9), g.t(90, 122, "意匠・商標", 9),
         g.t(230, 90, "著作権", 10.5),
         g.t(230, 112, "文芸・音楽・", 9), g.t(230, 126, "ソフトウェア等", 9),
         g.t(160, 160, "発明やデザインなどの", 10.5),
         g.t(160, 178, "産業上の権利を保護する", 10.5, g.ACCENT),
         g.t(160, 198, "特許庁への登録で発生", 9.5, g.SUB)]
    return g.titled("産業財産権", b)


@register("意匠権")
def fig_意匠権():
    b = [g.rect(70, 50, 90, 60, g.INK, 2.0, g.FILL),
         g.rect(160, 62, 90, 60, g.INK, 2.0, g.FILL2),
         g.t(115, 84, "形・模様", 10, g.ACCENT),
         g.t(205, 84, "色彩", 10, g.ACCENT),
         g.t(160, 140, "物品のデザイン(意匠)を保護", 10.5),
         g.t(160, 162, "登録から最長25年", 10),
         g.t(160, 184, "まねした製品の販売を止められる", 10, g.ACCENT),
         g.t(160, 206, "産業財産権の一つ", 9.5, g.SUB)]
    return g.titled("意匠権", b)


@register("著作者人格権")
def fig_著作者人格権():
    rights = [("公表権", "発表するか決める"),
              ("氏名表示権", "名前の出し方"),
              ("同一性保持権", "勝手に変えさせない")]
    b = []
    for i, (name, note) in enumerate(rights):
        x = 36 + i * 92
        b += _chem_box(x, 50, 76, 38, name, size=12, fill=g.FILL2, color=g.ACCENT)
        b.append(g.t(x + 38, 104, note, 9, g.INK))
    b += [g.t(160, 136, "著作者自身の人格を守る権利", 10.5),
          g.t(160, 158, "財産権と違い譲渡・放棄できない", 10, g.ACCENT),
          g.t(160, 182, "著作者が死亡後も保護される", 10),
          g.t(160, 206, "著作権法による保護", 9.5, g.SUB)]
    return g.titled("著作者人格権", b)


@register("著作隣接権")
def fig_著作隣接権():
    b = [g.t(160, 42, "実演家・レコード製作者・放送事業者", 10.5, g.INK),
         g.rect(40, 58, 240, 44, g.INK, 1.4, g.FILL2),
         g.t(160, 82, "著作物を伝える人の権利", 10.5, g.ACCENT),
         g.t(160, 124, "歌手の歌声・CD・放送を保護", 10.5),
         g.t(160, 146, "著作権とは別に認められる", 10),
         g.t(160, 170, "例: レコードの複製・送信の規制", 10, g.ACCENT),
         g.t(160, 194, "権利の保護期間は実演・録音から50年", 9.5, g.SUB)]
    return g.titled("著作隣接権", b)


@register("情報格差")
def fig_情報格差():
    b = [g.rect(44, 46, 104, 60, g.INK, 1.4, g.FILL2),
         g.rect(172, 46, 104, 60, g.INK, 1.4, g.FILL),
         g.t(96, 70, "情報機器・", 10), g.t(96, 88, "ネット利用可", 10, g.ACCENT),
         g.t(224, 70, "利用できない", 10), g.t(224, 88, "・使いこなせない", 9, g.ACCENT),
         g.t(160, 130, "情報を使える人と使えない人の差", 10.5),
         g.t(160, 152, "デジタルデバイド", 10.5, g.ACCENT),
         g.t(160, 176, "教育・環境・年齢などが原因", 10),
         g.t(160, 200, "誰もが使える環境づくりが課題", 9.5, g.SUB)]
    return g.titled("情報格差", b)


@register("電子証明書")
def fig_電子証明書():
    b = [g.rect(40, 46, 80, 46, g.INK, 1.3, g.FILL),
         g.rect(120, 46, 80, 46, g.INK, 1.3, g.FILL2),
         g.rect(200, 46, 80, 46, g.INK, 1.3, g.FILL),
         g.t(80, 66, "認証局", 9.5, g.ACCENT), g.t(80, 82, "(CA)", 9, g.SUB),
         g.t(160, 66, "証明書", 9.5, g.ACCENT), g.t(160, 82, "(本人確認)", 8.5, g.SUB),
         g.t(240, 66, "サーバ・", 9.5), g.t(240, 82, "利用者", 9.5),
         g.arrow(124, 69, 116, 69, g.INK, 1.4), g.arrow(204, 69, 196, 69, g.INK, 1.4),
         g.t(160, 116, "「この相手は本物」を電子的に証明", 10.5),
         g.t(160, 138, "なりすまし防止に使う", 10.5, g.ACCENT),
         g.t(160, 162, "HTTPS(鍵マーク)も証明書による確認", 10),
         g.t(160, 186, "マイナンバーカード・電子署名にも", 9.5, g.SUB)]
    return g.titled("電子証明書", b)


@register("論理回路")
def fig_論理回路():
    b = [g.t(58, 92, "AND", 10, g.INK), g.rect(40, 76, 44, 34, g.INK, 1.3, g.FILL),
         g.t(148, 92, "OR", 10, g.INK), g.rect(130, 76, 44, 34, g.INK, 1.3, g.FILL),
         g.t(238, 92, "NOT", 10, g.INK), g.rect(220, 76, 44, 34, g.INK, 1.3, g.FILL2),
         g.t(160, 132, "0と1の信号を組み合わせる回路", 10.5),
         g.t(160, 154, "AND: 両方1で1 / OR: どちらか1で1", 10, g.ACCENT),
         g.t(160, 178, "NOT: 0と1を反転", 10),
         g.t(160, 200, "コンピュータ内部の基本部品", 9.5, g.SUB)]
    return g.titled("論理回路", b)


@register("真理値表")
def fig_真理値表():
    rows = [("0", "0", "0"), ("0", "1", "0"), ("1", "0", "0"), ("1", "1", "1")]
    b = [g.rect(80, 40, 160, 26, g.INK, 1.4, g.FILL2),
         g.t(160, 56, "A | B | A AND B", 10.5, g.ACCENT)]
    for i, (a, bb, out) in enumerate(rows):
        y = 66 + i * 24
        b.append(g.rect(80, y, 160, 24, g.INK, 1.0, "#ffffff" if i % 2 == 0 else g.FILL))
        b.append(g.t(160, y + 16, f"{a} | {bb} | {out}", 10))
    b.append(g.t(160, 176, "入力の組合せと出力の対応表", 10.5))
    b.append(g.t(160, 196, "論理回路の動作を表す", 10, g.ACCENT))
    return g.titled("真理値表", b)


@register("半加算回路")
def fig_半加算回路():
    b = [g.t(48, 66, "A", 12, g.INK, "middle", g.MATHFONT, "700"),
         g.t(48, 106, "B", 12, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(64, 48, 44, 34, g.INK, 1.3, g.FILL2),
         g.t(86, 70, "XOR", 9.5, g.ACCENT),
         g.rect(64, 92, 44, 34, g.INK, 1.3, g.FILL),
         g.t(86, 114, "AND", 9.5, g.ACCENT),
         g.line(112, 65, 200, 65, g.INK, 1.4), g.line(112, 109, 200, 109, g.INK, 1.4),
         g.t(236, 65, "S(和)", 10, g.ACCENT), g.t(236, 109, "C(繰り上がり)", 9.5, g.ACCENT),
         g.arrow(200, 65, 224, 65, g.INK, 1.2), g.arrow(200, 109, 224, 109, g.INK, 1.2),
         g.t(160, 146, "1ビットの足し算をする回路", 10.5),
         g.t(160, 168, "XORで和・ANDで繰り上がり", 10, g.ACCENT),
         g.t(160, 190, "加算器の基本ユニット", 10),
         g.t(160, 212, "全加算器は繰り上がり入力も扱う", 9.5, g.SUB)]
    return g.titled("半加算回路", b)


@register("符号化")
def fig_符号化():
    b = [g.rect(40, 56, 80, 52, g.INK, 1.4, g.FILL),
         g.rect(200, 56, 80, 52, g.INK, 1.4, g.FILL2),
         g.t(80, 76, "文字・画像", 10), g.t(80, 92, "(アナログ情報)", 8.5, g.SUB),
         g.t(240, 76, "0と1の列", 10, g.ACCENT), g.t(240, 92, "(デジタル)", 8.5, g.SUB),
         g.arrow(124, 82, 196, 82, g.ACCENT, 2.0),
         g.t(160, 74, "2進数", 9.5, g.ACCENT),
         g.t(160, 130, "情報をコンピュータが扱える形に", 10.5),
         g.t(160, 152, "変換すること", 10.5, g.ACCENT),
         g.t(160, 176, "例: 文字コード(ASCII・UTF-8)", 10),
         g.t(160, 200, "音声・画像も符号化でデジタル化", 9.5, g.SUB)]
    return g.titled("符号化", b)


@register("可逆圧縮")
def fig_可逆圧縮():
    b = [g.rect(36, 50, 72, 44, g.INK, 1.3, g.FILL),
         g.rect(124, 50, 72, 44, g.INK, 1.3, g.FILL2),
         g.rect(212, 50, 72, 44, g.INK, 1.3, g.FILL),
         g.t(72, 68, "元のデータ", 9.5), g.t(72, 82, "(大きい)", 8.5, g.SUB),
         g.t(160, 68, "圧縮", 9.5, g.ACCENT), g.t(160, 82, "(小さく)", 8.5, g.SUB),
         g.t(248, 68, "復元", 9.5, g.ACCENT), g.t(248, 82, "(元どおり)", 8.5, g.SUB),
         g.arrow(112, 72, 120, 72, g.INK, 1.4), g.arrow(200, 72, 208, 72, g.INK, 1.4),
         g.t(160, 118, "圧縮しても元のデータに完全に戻せる", 10.5),
         g.t(160, 140, "情報が失われない", 10.5, g.ACCENT),
         g.t(160, 164, "例: ZIP・PNG・FLAC", 10, g.ACCENT),
         g.t(160, 188, "非可逆圧縮(JPEG等)は画質が落ちる", 9.5, g.SUB)]
    return g.titled("可逆圧縮", b)


@register("引数")
def fig_引数():
    b = [g.rect(40, 60, 72, 44, g.INK, 1.3, g.FILL),
         g.rect(150, 60, 80, 44, g.INK, 1.3, g.FILL2),
         g.t(76, 78, "呼び出し側", 9.5), g.t(76, 94, "f(3)", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(190, 78, "関数", 9.5), g.t(190, 94, "f(x) = x×2", 9, g.ACCENT),
         g.arrow(116, 82, 146, 82, g.ACCENT, 1.8),
         g.t(131, 74, "3", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 126, "関数に渡す値(入力)", 10.5),
         g.t(160, 148, "f(3) の 3 が引数", 10.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 172, "プログラムの部品化で使う", 10),
         g.t(160, 196, "引数によって処理を変えられる", 9.5, g.SUB)]
    return g.titled("引数", b)


@register("戻り値")
def fig_戻り値():
    b = [g.rect(40, 56, 80, 48, g.INK, 1.3, g.FILL),
         g.rect(200, 56, 80, 48, g.INK, 1.3, g.FILL2),
         g.t(80, 74, "関数", 9.5), g.t(80, 90, "(計算)", 9, g.SUB),
         g.t(240, 74, "呼び出し側", 9.5), g.t(240, 90, "(結果を受け取る)", 8.5, g.SUB),
         g.arrow(124, 80, 196, 80, g.ACCENT, 2.0),
         g.t(160, 72, "結果", 9.5, g.ACCENT),
         g.t(160, 126, "関数が処理の結果として返す値", 10.5),
         g.t(160, 148, "return で返す", 10.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 172, "例: 足し算の結果・検索の結果", 10),
         g.t(160, 196, "引数と対になる概念", 9.5, g.SUB)]
    return g.titled("戻り値", b)


@register("線形探索")
def fig_線形探索():
    b = []
    vals = ["3", "7", "1", "9", "5"]
    for i, v in enumerate(vals):
        x = 48 + i * 52
        b += _chem_box(x, 56, 40, 40, v, size=14, fill=g.FILL2 if v == "9" else g.FILL)
    b += [g.t(68, 114, "先頭から順に調べる", 9.5, g.ACCENT),
          g.arrow(68, 106, 232, 106, g.ACCENT, 1.4),
          g.t(160, 142, "「9」を先頭から順番に探す", 10.5),
          g.t(160, 164, "見つかるまで要素を1つずつ比較", 10.5, g.ACCENT),
          g.t(160, 188, "データが多くても単純に探せる", 10),
          g.t(160, 212, "二分探索より遅いが実装は簡単", 9.5, g.SUB)]
    return g.titled("線形探索", b)


@register("順次構造")
def fig_順次構造():
    b = [g.rect(110, 40, 100, 32, g.INK, 1.4, g.FILL),
         g.t(160, 61, "処理1", 10.5),
         g.arrow(160, 76, 160, 92, g.INK, 1.4),
         g.rect(110, 96, 100, 32, g.INK, 1.4, g.FILL),
         g.t(160, 117, "処理2", 10.5),
         g.arrow(160, 132, 160, 148, g.INK, 1.4),
         g.rect(110, 152, 100, 32, g.INK, 1.4, g.FILL2),
         g.t(160, 173, "処理3", 10.5, g.ACCENT),
         g.t(160, 204, "上から順番に実行する基本構造", 9.5)]
    return g.titled("順次構造", b)


@register("選択構造")
def fig_選択構造():
    b = [g.rect(118, 38, 84, 32, g.INK, 1.4, g.FILL),
         g.t(160, 59, "条件を判定", 10),
         g.arrow(160, 74, 160, 88, g.INK, 1.4),
         g.poly([(160, 92), (190, 118), (160, 144), (130, 118)], g.INK, 1.5, g.FILL2),
         g.t(160, 122, "条件?", 9.5, g.ACCENT),
         g.line(130, 118, 74, 118, g.INK, 1.3), g.arrow(74, 118, 62, 118, g.INK, 1.3),
         g.t(84, 110, "はい", 8.5, g.ACCENT),
         g.line(190, 118, 246, 118, g.INK, 1.3), g.arrow(246, 118, 258, 118, g.INK, 1.3),
         g.t(236, 110, "いいえ", 8.5, g.ACCENT),
         g.rect(40, 150, 52, 30, g.INK, 1.2, g.FILL), g.t(66, 170, "処理A", 9),
         g.rect(228, 150, 52, 30, g.INK, 1.2, g.FILL), g.t(254, 170, "処理B", 9),
         g.t(160, 200, "条件によって実行を分岐する", 9.5),
         g.t(160, 218, "フローチャートのひし形が分岐", 9, g.SUB)]
    return g.titled("選択構造", b)


@register("反復構造")
def fig_反復構造():
    b = [g.rect(118, 38, 84, 32, g.INK, 1.4, g.FILL),
         g.t(160, 59, "処理を実行", 10),
         g.arrow(160, 74, 160, 92, g.INK, 1.4),
         g.poly([(160, 96), (190, 124), (160, 152), (130, 124)], g.INK, 1.5, g.FILL2),
         g.t(160, 128, "続ける?", 9.5, g.ACCENT),
         g.line(130, 124, 74, 124, g.INK, 1.3), g.arrow(74, 124, 62, 124, g.INK, 1.3),
         g.t(84, 116, "はい", 8.5, g.ACCENT),
         g.path("M74,124 Q44,96 74,68 Q104,44 118,54", g.ACCENT, 1.4, dash="4 3"),
         g.line(190, 124, 258, 124, g.INK, 1.3),
         g.t(236, 116, "いいえ", 8.5, g.ACCENT),
         g.t(160, 176, "条件を満たす間、繰り返し実行", 10),
         g.t(160, 196, "ループとも呼ぶ", 10, g.ACCENT),
         g.t(160, 216, "回数指定・条件指定の2種類", 9.5, g.SUB)]
    return g.titled("反復構造", b)


@register("プロトコル")
def fig_プロトコル():
    b = [g.rect(40, 52, 88, 52, g.INK, 1.3, g.FILL),
         g.rect(192, 52, 88, 52, g.INK, 1.3, g.FILL),
         g.t(84, 72, "コンピュータA", 9.5), g.t(84, 88, "(送信)", 8.5, g.SUB),
         g.t(236, 72, "コンピュータB", 9.5), g.t(236, 88, "(受信)", 8.5, g.SUB),
         g.arrow(132, 62, 188, 62, g.ACCENT, 1.6),
         g.arrow(188, 94, 132, 94, g.ACCENT, 1.6),
         g.t(160, 74, "共通の取り決め", 9, g.ACCENT),
         g.t(160, 130, "通信の手順・形式の約束ごと", 10.5),
         g.t(160, 152, "例: HTTP・TCP/IP・SMTP", 10.5, g.ACCENT),
         g.t(160, 176, "同じプロトコル同士で通信できる", 10),
         g.t(160, 200, "「通信の共通言語」", 9.5, g.SUB)]
    return g.titled("プロトコル", b)


@register("主キー")
def fig_主キー():
    b = [g.rect(40, 42, 240, 26, g.INK, 1.3, g.FILL2),
         g.t(160, 59, "会員ID | 名前 | 住所", 10, g.ACCENT)]
    for i, (mid, name) in enumerate([("001", "佐藤"), ("002", "鈴木"), ("003", "高橋")]):
        y = 68 + i * 30
        b.append(g.rect(40, y, 240, 30, g.INK, 1.0, g.FILL if i % 2 == 0 else "#ffffff"))
        b.append(g.t(160, y + 20, f"{mid} | {name} | …", 9.5))
    b.append(g.t(160, 170, "行を1つに特定する列", 10.5))
    b.append(g.t(160, 192, "重複しない・空にしない(ID)", 10.5, g.ACCENT))
    b.append(g.t(160, 214, "リレーショナルデータベースの基礎", 9.5, g.SUB))
    return g.titled("主キー", b)


@register("外部キー")
def fig_外部キー():
    b = [g.rect(40, 44, 110, 88, g.INK, 1.3, g.FILL),
         g.rect(170, 44, 110, 88, g.INK, 1.3, g.FILL2),
         g.t(95, 68, "注文表", 9.5, g.ACCENT),
         g.t(95, 88, "注文ID | 会員ID", 9),
         g.t(225, 68, "会員表", 9.5, g.ACCENT),
         g.t(225, 88, "会員ID | 名前", 9),
         g.line(150, 88, 170, 88, g.ACCENT, 1.8),
         g.t(160, 80, "参照", 9, g.ACCENT),
         g.t(160, 150, "別の表の主キーを指す列", 10.5),
         g.t(160, 172, "表と表を関連づける", 10.5, g.ACCENT),
         g.t(160, 196, "会員IDで注文と会員を結びつける", 9.5, g.SUB)]
    return g.titled("外部キー", b)


@register("クロス集計")
def fig_クロス集計():
    b = [g.rect(60, 42, 200, 24, g.INK, 1.3, g.FILL2),
         g.t(160, 58, "項目A ＼ 項目B", 9.5, g.ACCENT)]
    for i, row in enumerate([("A1 | B1 | 12", "A1 | B2 | 8"),
                             ("A2 | B1 | 5", "A2 | B2 | 15")]):
        y = 66 + i * 34
        b.append(g.rect(60, y, 96, 34, g.INK, 1.0, g.FILL if i % 2 == 0 else "#ffffff"))
        b.append(g.rect(164, y, 96, 34, g.INK, 1.0, g.FILL if i % 2 == 0 else "#ffffff"))
        b.append(g.t(108, y + 20, row[0], 9))
        b.append(g.t(212, y + 20, row[1], 9))
    b.append(g.t(160, 130, "2つの項目をかけ合わせて集計", 10.5))
    b.append(g.t(160, 152, "縦×横の表で傾向を見る", 10.5, g.ACCENT))
    b.append(g.t(160, 176, "アンケート分析などに使う", 10))
    b.append(g.t(160, 200, "ピボットテーブルとも", 9.5, g.SUB))
    return g.titled("クロス集計", b)


@register("確定モデル")
def fig_確定モデル():
    b = [g.rect(50, 52, 80, 44, g.INK, 1.3, g.FILL),
         g.rect(190, 52, 80, 44, g.INK, 1.3, g.FILL2),
         g.t(90, 70, "同じ入力", 9.5), g.t(90, 86, "(条件)", 8.5, g.SUB),
         g.t(230, 70, "同じ結果", 9.5, g.ACCENT), g.t(230, 86, "(一通り)", 8.5, g.SUB),
         g.arrow(134, 74, 186, 74, g.ACCENT, 1.8),
         g.t(160, 118, "偶然の要素を含まないモデル", 10.5),
         g.t(160, 140, "結果が一通りに決まる", 10.5, g.ACCENT),
         g.t(160, 164, "例: 計算式・アルゴリズム", 10),
         g.t(160, 188, "乱数を使う確率モデルとは対照的", 9.5, g.SUB)]
    return g.titled("確定モデル", b)


@register("トレードオフ")
def fig_トレードオフ():
    b = [g.line(60, 140, 260, 140, g.INK, 1.4),
         g.line(60, 140, 60, 52, g.INK, 1.4),
         g.t(36, 46, "性能", 9, g.SUB),
         g.path("M60,132 L130,100 L200,74 L260,56", g.ACCENT, 2.2),
         g.path("M60,60 L130,96 L200,124 L260,138", g.INK, 2.0),
         g.t(60, 152, "一方をとると", 9.5, g.SUB),
         g.t(160, 168, "もう一方が犠牲になる関係", 10.5, g.ACCENT),
         g.t(160, 190, "例: 画質とデータ量・速度と安全性", 10),
         g.t(160, 212, "どちらを優先するか判断が必要", 9.5, g.SUB)]
    return g.titled("トレードオフ", b)


@register("生涯発達")
def fig_生涯発達():
    b = [g.line(50, 140, 270, 140, g.SUB, 1.2),
         g.line(50, 140, 50, 52, g.SUB, 1.2),
         g.t(30, 46, "発達", 9, g.SUB),
         g.path("M50,132 Q110,60 160,64 Q210,68 270,56", g.ACCENT, 2.2),
         g.t(160, 84, "乳幼児期", 9, g.SUB), g.t(160, 104, "青年期", 9, g.SUB),
         g.t(160, 128, "成人期", 9, g.SUB), g.t(160, 152, "老年期", 9, g.SUB),
         g.t(160, 172, "生涯を通じて発達し続ける", 10.5),
         g.t(160, 194, "発達は年齢だけでなく環境の影響も受ける", 10, g.ACCENT),
         g.t(160, 216, "ライフステージごとの課題がある", 9.5, g.SUB)]
    return g.titled("生涯発達", b)


@register("家計")
def fig_家計():
    b = [g.circle(160, 92, 58, g.INK, 1.5),
         g.path("M160,92 L160,34 A58,58 0 0 1 211,66 L160,92 Z", g.ACCENT, 1.2, g.FILL2),
         g.path("M160,92 L211,66 A58,58 0 0 1 218,92 L160,92 Z", g.INK, 1.2, g.FILL),
         g.path("M160,92 L218,92 A58,58 0 0 1 160,150 L160,92 Z", g.ACCENT, 1.2, g.FILL),
         g.t(192, 70, "食費", 8.5), g.t(196, 108, "住居費", 8.5), g.t(150, 120, "その他", 8.5),
         g.t(160, 166, "収入と支出のやりくり", 10.5),
         g.t(160, 188, "収入: 給料・年金 ／ 支出: 消費・貯蓄", 9.5, g.ACCENT),
         g.t(160, 210, "ライフステージで構成が変わる", 9.5, g.SUB)]
    return g.titled("家計", b)


@register("公的年金")
def fig_公的年金():
    b = [g.rect(44, 48, 92, 48, g.INK, 1.3, g.FILL),
         g.rect(184, 48, 92, 48, g.INK, 1.3, g.FILL2),
         g.t(90, 68, "現役世代", 9.5), g.t(90, 84, "(保険料を納める)", 8.5, g.SUB),
         g.t(230, 68, "高齢者", 9.5), g.t(230, 84, "(年金を受け取る)", 8.5, g.SUB),
         g.arrow(140, 72, 180, 72, g.ACCENT, 1.8),
         g.t(160, 64, "支え合い", 9, g.ACCENT),
         g.t(160, 120, "現役世代が納めた保険料を", 10.5),
         g.t(160, 142, "高齢者に給付する仕組み", 10.5, g.ACCENT),
         g.t(160, 166, "国民年金(基礎年金)・厚生年金", 10),
         g.t(160, 190, "少子高齢化で負担と給付の見直しが課題", 9.5, g.SUB)]
    return g.titled("公的年金", b)


@register("消費者市民社会")
def fig_消費者市民社会():
    b = [g.rect(44, 46, 92, 52, g.INK, 1.3, g.FILL),
         g.rect(184, 46, 92, 52, g.INK, 1.3, g.FILL2),
         g.t(90, 66, "消費者の選択", 9.5), g.t(90, 82, "(買う・買わない)", 8.5, g.SUB),
         g.t(230, 66, "社会のあり方", 9.5), g.t(230, 82, "(環境・人権)", 8.5, g.SUB),
         g.arrow(140, 72, 180, 72, g.ACCENT, 1.8),
         g.t(160, 120, "消費行動が社会を変えうる", 10.5),
         g.t(160, 142, "「買い物は投票」", 10.5, g.ACCENT),
         g.t(160, 166, "エシカル消費・フェアトレード", 10),
         g.t(160, 190, "環境や社会に配慮した消費", 9.5, g.SUB)]
    return g.titled("消費者市民社会", b)


@register("基礎代謝量")
def fig_基礎代謝量():
    b = [g.t(160, 48, "生命維持のためのエネルギー", 10.5, g.INK),
         g.rect(60, 64, 200, 44, g.INK, 1.4, g.FILL2),
         g.t(160, 84, "心臓・呼吸・体温維持など", 10, g.ACCENT),
         g.t(160, 128, "何もしなくても消費するエネルギー", 10.5),
         g.t(160, 150, "1日の消費の約6割を占める", 10.5, g.ACCENT),
         g.t(160, 174, "筋肉量が多いほど大きい", 10),
         g.t(160, 196, "年齢・性別・体格で異なる", 9.5, g.SUB)]
    return g.titled("基礎代謝量", b)


@register("食事摂取基準")
def fig_食事摂取基準():
    b = [g.rect(90, 44, 140, 30, g.INK, 1.3, g.FILL2),
         g.t(160, 64, "エネルギー・栄養素の量", 9.5, g.ACCENT),
         g.t(160, 92, "推定平均必要量・推奨量", 10),
         g.t(160, 114, "目安量・上限量など", 10, g.ACCENT),
         g.t(160, 140, "年齢・性別・身体活動レベル別", 10.5),
         g.t(160, 164, "食事の計画・評価に使う基準", 10.5, g.ACCENT),
         g.t(160, 190, "「日本人の食事摂取基準」", 10),
         g.t(160, 212, "5年ごとに改定", 9.5, g.SUB)]
    return g.titled("食事摂取基準", b)


@register("被服の機能")
def fig_被服の機能():
    b = []
    for i, (name, note) in enumerate([("保温・放熱", "体温の調節"),
                                      ("保護", "けが・汚れから守る"),
                                      ("表現", "自分を伝える")]):
        x = 36 + i * 92
        b += _chem_box(x, 48, 76, 38, name, size=11, fill=g.FILL2, color=g.ACCENT)
        b.append(g.t(x + 38, 100, note, 9, g.INK))
    b += [g.t(160, 130, "衣服の役割(生理的・社会的機能)", 10.5),
          g.t(160, 152, "季節や場面に合わせて選ぶ", 10, g.ACCENT),
          g.t(160, 176, "清潔に保つことも機能の一部", 10),
          g.t(160, 200, "着心地・動きやすさも大切", 9.5, g.SUB)]
    return g.titled("被服の機能", b)


@register("繊維の性能")
def fig_繊維の性能():
    b = []
    for i, (name, note) in enumerate([("吸湿性", "汗を吸い取る"),
                                      ("強度", "引き裂きにくい"),
                                      ("伸縮性", "よく伸びる")]):
        x = 36 + i * 92
        b += _chem_box(x, 48, 76, 38, name, size=11, fill=g.FILL, color=g.INK)
        b.append(g.t(x + 38, 100, note, 9, g.ACCENT))
    b += [g.t(160, 128, "素材(綿・麻・化学繊維)の特性", 10.5),
          g.t(160, 150, "用途に合わせて素材を選ぶ", 10, g.ACCENT),
          g.t(160, 174, "例: 綿は吸湿・麻は涼しい", 10),
          g.t(160, 198, "ラベル表示で素材を確認", 9.5, g.SUB)]
    return g.titled("繊維の性能", b)


@register("探索行動")
def fig_探索行動():
    b = [g.circle(100, 78, 22, g.INK, 1.5, g.FILL),
         g.t(100, 83, "子", 12, g.INK),
         g.line(100, 100, 100, 140, g.INK, 1.8),
         g.line(100, 110, 72, 130, g.INK, 1.6), g.line(100, 110, 128, 130, g.INK, 1.6),
         g.rect(170, 56, 90, 60, g.INK, 1.3, g.FILL2),
         g.t(215, 78, "物・場所", 9.5), g.t(215, 94, "(未知のもの)", 8.5, g.SUB),
         g.arrow(128, 100, 166, 92, g.ACCENT, 1.8),
         g.t(148, 86, "触る・見る", 8.5, g.ACCENT),
         g.t(160, 152, "新しい環境を確かめる行動", 10.5),
         g.t(160, 174, "子どもの発達に重要", 10, g.ACCENT),
         g.t(160, 196, "知る・学ぶための基本", 9.5, g.SUB)]
    return g.titled("探索行動", b)


@register("栄養素")
def fig_栄養素():
    b = []
    for i, (name, note) in enumerate([("炭水化物", "エネルギーの源"),
                                      ("タンパク質", "体をつくる"),
                                      ("脂質", "エネルギーの貯蔵"),
                                      ("ビタミン", "調節"),
                                      ("無機質", "骨・歯など")]):
        x = 20 + i * 58
        b += _chem_box(x, 46, 50, 44, name, size=9, fill=g.FILL2 if i == 2 else g.FILL, color=g.INK)
        b.append(g.t(x + 25, 104, note, 8, g.ACCENT))
    b += [g.t(160, 130, "5大栄養素", 10.5),
          g.t(160, 152, "バランスよくとることが大切", 10, g.ACCENT),
          g.t(160, 176, "水も生命維持に欠かせない", 10),
          g.t(160, 200, "食事バランスガイドが参考になる", 9.5, g.SUB)]
    return g.titled("栄養素", b)


@register("住空間")
def fig_住空間():
    b = [g.rect(40, 42, 240, 100, g.INK, 1.6, g.FILL),
         g.rect(54, 54, 64, 44, g.INK, 1.2, "#ffffff"),
         g.rect(134, 54, 64, 44, g.INK, 1.2, g.FILL2),
         g.rect(210, 54, 56, 44, g.INK, 1.2, "#ffffff"),
         g.t(86, 76, "居間", 9), g.t(166, 76, "台所", 9), g.t(238, 76, "寝室", 9),
         g.rect(54, 110, 212, 20, g.INK, 1.0, "#ffffff"),
         g.t(160, 124, "廊下", 8.5),
         g.t(160, 160, "家族の生活に合わせた空間づくり", 10.5),
         g.t(160, 182, "動線・安全・採光・通風を考える", 10, g.ACCENT),
         g.t(160, 206, "バリアフリーも住空間の課題", 9.5, g.SUB)]
    return g.titled("住空間", b)


@register("衣食住")
def fig_衣食住():
    b = [g.rect(40, 48, 76, 76, g.INK, 1.4, g.FILL),
         g.rect(122, 48, 76, 76, g.INK, 1.4, g.FILL),
         g.rect(204, 48, 76, 76, g.INK, 1.4, g.FILL2),
         g.t(78, 84, "衣", 12, g.ACCENT), g.t(160, 84, "食", 12, g.ACCENT),
         g.t(242, 84, "住", 12, g.ACCENT),
         g.t(78, 104, "(衣服)", 8.5, g.SUB), g.t(160, 104, "(食事)", 8.5, g.SUB),
         g.t(242, 104, "(住まい)", 8.5, g.SUB),
         g.t(160, 148, "生活の3つの基本", 10.5),
         g.t(160, 170, "健康で文化的な生活の土台", 10, g.ACCENT),
         g.t(160, 194, "家庭科で総合的に学ぶ領域", 9.5, g.SUB)]
    return g.titled("衣食住", b)


@register("作業の安全")
def fig_作業の安全():
    b = [g.circle(160, 58, 28, g.INK, 2.0, g.FILL),
         g.t(160, 63, "安全", 12, g.ACCENT),
         g.rect(52, 100, 216, 46, g.INK, 1.4, g.FILL2),
         g.t(160, 120, "保護具・確認・正しい手順", 10, g.ACCENT),
         g.t(160, 140, "(ヘルメット・手袋・安全靴など)", 9, g.SUB),
         g.t(160, 168, "作業前に安全を確認する", 10.5),
         g.t(160, 190, "けがや事故を防ぐ基本", 10, g.ACCENT),
         g.t(160, 212, "「安全第一」の心がけ", 9.5, g.SUB)]
    return g.titled("作業の安全", b)


# ---- 国語(古典文法・助動詞・詩形・語彙) ------------------------------------


def _katsuyou(word, base, forms, note):
    """活用表の図。forms は (活用形名, 語形) の6つ組。"""
    b = [g.t(160, 40, base, 12, g.INK)]
    for i, (name, form) in enumerate(forms):
        x = 20 + (i % 3) * 100
        y = 54 + (i // 3) * 46
        b += _chem_box(x, y, 88, 32, form, size=12,
                       fill=g.FILL2 if i == 4 else g.FILL, color=g.ACCENT if i == 4 else g.INK)
        b.append(g.t(x + 44, y + 42, name, 9, g.SUB))
    b.append(g.t(160, 156, note, 10.5, g.ACCENT))
    b.append(g.t(160, 178, word, 10, g.SUB))
    return g.titled(word, b)


@register("四段活用")
def fig_四段活用():
    return _katsuyou("四段活用", "「書く」— ア・イ・ウ・エの4段",
                     [("未然", "書か"), ("連用", "書き"), ("終止", "書く"),
                      ("連体", "書く"), ("仮定", "書け"), ("命令", "書け")],
                     "語尾がカ・キ・ク・ケと4段に変わる")


@register("上二段活用")
def fig_上二段活用():
    return _katsuyou("上二段活用", "「起く」— イ・ウの2段",
                     [("未然", "起き"), ("連用", "起き"), ("終止", "起く"),
                      ("連体", "起くる"), ("仮定", "起くれ"), ("命令", "起きよ")],
                     "語尾がイ段・ウ段の2段で変化する")


@register("下二段活用")
def fig_下二段活用():
    return _katsuyou("下二段活用", "「受く」— エ・ウの2段",
                     [("未然", "受け"), ("連用", "受け"), ("終止", "受く"),
                      ("連体", "受くる"), ("仮定", "受くれ"), ("命令", "受けよ")],
                     "語尾がエ段・ウ段の2段で変化する")


@register("ナ行変格活用")
def fig_ナ行変格活用():
    return _katsuyou("ナ行変格活用", "「死ぬ」— ナ行の変格",
                     [("未然", "死な"), ("連用", "死に"), ("終止", "死ぬ"),
                      ("連体", "死ぬる"), ("仮定", "死ぬれ"), ("命令", "死ね")],
                     "「死ぬ」だけの不規則な活用")


@register("ラ行変格活用")
def fig_ラ行変格活用():
    return _katsuyou("ラ行変格活用", "「あり」— ラ行の変格",
                     [("未然", "あら"), ("連用", "あり"), ("終止", "あり"),
                      ("連体", "ある"), ("仮定", "あれ"), ("命令", "あれ")],
                     "「あり・をり・侍り・いまそかり」の活用")


@register("ナリ活用")
def fig_ナリ活用():
    return _katsuyou("ナリ活用", "「静かなり」— ナリ型の形容動詞",
                     [("未然", "なら"), ("連用", "なり"), ("終止", "なり"),
                      ("連体", "なる"), ("仮定", "なれ"), ("命令", "なれ")],
                     "断定の助動詞「なり」と同じ形で活用")


def _joshi(word, forms, note):
    b = []
    for i, (name, form) in enumerate(forms):
        x = 36 + (i % 3) * 92
        y = 46 + (i // 3) * 52
        b += _chem_box(x, y, 76, 34, form, size=12, fill=g.FILL2, color=g.ACCENT)
        b.append(g.t(x + 38, y + 44, name, 9, g.SUB))
    b.append(g.t(160, 160, note, 10.5))
    b.append(g.t(160, 186, word, 10, g.SUB))
    return g.titled(word, b)


@register("なり")
def fig_なり():
    return _joshi("なり", [("断定", "〜である"), ("伝聞・推定", "〜そうだ")],
                  "例: 花咲く里なり(断定)")


@register("めり")
def fig_めり():
    return _joshi("めり", [("推定(視覚)", "〜ようだ"), ("婉曲", "〜のようだ")],
                  "見た感じからの推定に使う")


@register("べし")
def fig_べし():
    return _joshi("べし", [("推量", "〜だろう"), ("意志", "〜しよう"),
                           ("当然", "〜はずだ"), ("命令", "〜せよ")],
                  "意味が多い助動詞(文脈で判断)")


@register("まし")
def fig_まし():
    return _joshi("まし", [("反実仮想", "〜だったらなあ"), ("ためらい", "〜しようか")],
                  "実際とは違うことを仮に想定する")


@register("けり")
def fig_けり():
    return _joshi("けり", [("詠嘆", "〜たなあ"), ("回想", "〜た")],
                  "過去の出来事を回想・詠嘆する")


@register("らむ")
def fig_らむ():
    return _joshi("らむ", [("現在推量", "〜ているだろう"), ("原因推量", "〜からだ")],
                  "現在のことを推量する")


@register("けむ")
def fig_けむ():
    return _joshi("けむ", [("過去推量", "〜ただろう")],
                  "過去のことを推量する")


@register("まじ")
def fig_まじ():
    return _joshi("まじ", [("打消推量", "〜ないだろう"), ("打消意志", "〜まい")],
                  "「べし」の打消しの意味")


@register("推量")
def fig_推量():
    return _joshi("推量", [("む・らむ・けむ", "〜だろう"), ("べし・まじ", "〜はず")],
                  "確かでないことを推しはかる意味")


@register("完了")
def fig_完了():
    return _joshi("完了", [("つ", "〜てしまう"), ("ぬ", "〜てしまう"),
                           ("たり・り", "〜ている")],
                  "動作が完了したことを表す")


@register("断定")
def fig_断定():
    return _joshi("断定", [("なり", "〜である"), ("たり", "〜である")],
                  "きっぱりと決めつける意味")


@register("意志")
def fig_意志():
    return _joshi("意志", [("む", "〜しよう"), ("べし", "〜せねばならぬ")],
                  "話し手の意志を表す")


@register("使役")
def fig_使役():
    return _joshi("使役", [("す", "〜させる"), ("さす", "〜させる"),
                           ("しむ", "〜させる")],
                  "人に動作をさせる意味")


@register("受身")
def fig_受身():
    return _joshi("受身", [("る", "〜れる"), ("らる", "〜られる")],
                  "動作を受ける側に立つ意味")


@register("推定")
def fig_推定():
    return _joshi("推定", [("なり・めり", "〜ようだ"), ("らむ・けむ", "〜だろう")],
                  "根拠に基づいて推しはかる")


@register("婉曲")
def fig_婉曲():
    return _joshi("婉曲", [("めり", "〜のようだ"), ("む", "〜であろう")],
                  "断定を避けて遠回しに言う")


@register("反実仮想")
def fig_反実仮想():
    return _joshi("反実仮想", [("まし", "〜だったらなあ"), ("せば〜まし", "〜なら〜だろうに")],
                  "現実と反対のことを仮定する")


@register("詠嘆")
def fig_詠嘆():
    return _joshi("詠嘆", [("けり", "〜たなあ"), ("かな", "〜だなあ")],
                  "感動・感慨を表す")


@register("係助詞")
def fig_係助詞():
    b = [g.t(160, 44, "ぞ・なむ・や・か・こそ", 12.5, g.ACCENT),
         g.rect(44, 58, 232, 34, g.INK, 1.3, g.FILL),
         g.t(160, 80, "文末の活用形を変える(係り結び)", 10.5),
         g.t(160, 112, "ぞ・なむ → 連体形", 10.5, g.ACCENT),
         g.t(160, 134, "こそ → 已然形", 10.5, g.ACCENT),
         g.t(160, 160, "や・か → 連体形(疑問・反語)", 10),
         g.t(160, 186, "例: 花ぞ咲ける(「咲く」が連体形に)", 10, g.ACCENT)]
    return g.titled("係助詞", b)


@register("已然形")
def fig_已然形():
    b = [g.t(160, 46, "「書く」の活用の第5形", 10.5, g.INK),
         g.rect(60, 60, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 84, "書け(ば)", 15, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 120, "係り結びの「こそ」と呼応", 10.5, g.ACCENT),
         g.t(160, 144, "「ば」が続くと仮定・確定条件に", 10),
         g.t(160, 168, "已然形 + ば → 確定条件", 10, g.ACCENT),
         g.t(160, 192, "例: 山高ければ(「高し」の已然形)", 10, g.SUB)]
    return g.titled("已然形", b)


@register("呼応の副詞")
def fig_呼応の副詞():
    b = [g.t(160, 44, "あたかも・ゆめ・な・など", 11.5, g.INK),
         g.rect(50, 56, 220, 36, g.INK, 1.3, g.FILL),
         g.t(160, 78, "副詞と呼応する表現", 10.5, g.ACCENT),
         g.t(160, 108, "あたかも 〜ごとし(比喩)", 10, g.ACCENT),
         g.t(160, 130, "ゆめ 〜な(禁止)", 10),
         g.t(160, 152, "な 〜そ(禁止)", 10),
         g.t(160, 176, "副詞が決まった言い方と呼応する", 10, g.ACCENT),
         g.t(160, 200, "例: あたかも花のごとし", 9.5, g.SUB)]
    return g.titled("呼応の副詞", b)


@register("係り結びの流れ")
def fig_係り結びの流れ():
    b = [g.rect(40, 44, 100, 42, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 42, g.INK, 1.3, g.FILL2),
         g.t(90, 62, "係助詞", 10, g.INK), g.t(90, 78, "(ぞ・なむ・こそ)", 8.5, g.SUB),
         g.t(230, 62, "結び", 10, g.ACCENT), g.t(230, 78, "(活用形が変わる)", 8.5, g.SUB),
         g.arrow(144, 65, 176, 65, g.ACCENT, 1.8),
         g.t(160, 57, "呼応", 9, g.ACCENT),
         g.t(160, 104, "ぞ・なむ → 連体形", 10.5, g.ACCENT),
         g.t(160, 126, "こそ → 已然形", 10.5, g.ACCENT),
         g.t(160, 150, "文末の形が係助詞に従う", 10),
         g.t(160, 174, "例: 花ぞ咲ける", 10, g.ACCENT),
         g.t(160, 198, "古文の読解で重要なきまり", 9.5, g.SUB)]
    return g.titled("係り結びの流れ", b)


@register("結びの省略")
def fig_結びの省略():
    b = [g.t(160, 46, "「か・や」で文末が省略される", 10.5, g.INK),
         g.rect(40, 60, 240, 40, g.INK, 1.4, g.FILL),
         g.t(160, 84, "誰か来た(る)か(らむ)…", 11, g.ACCENT),
         g.t(160, 120, "疑問・反語の余韻を残す", 10.5, g.ACCENT),
         g.t(160, 144, "文末の動詞・助動詞が省略される", 10),
         g.t(160, 168, "例: 「かかる名をや(残す)」", 10, g.ACCENT),
         g.t(160, 192, "和歌・物語でよく使われる", 9.5, g.SUB)]
    return g.titled("結びの省略", b)


@register("ウ音便")
def fig_ウ音便():
    b = [g.t(160, 44, "「買ひて」→「買うて」", 12, g.ACCENT),
         g.rect(40, 58, 240, 36, g.INK, 1.3, g.FILL),
         g.t(160, 80, "音が「う」に変わる音便", 10.5),
         g.t(160, 110, "例: 思ひて → 思うて", 10, g.ACCENT),
         g.t(160, 132, "問ひて → 問うて", 10),
         g.t(160, 156, "ハ行音がウに変化", 10, g.ACCENT),
         g.t(160, 180, "イ音便(書いて)・促音便(買って)もある", 9.5, g.SUB)]
    return g.titled("ウ音便", b)


@register("置き字")
def fig_置き字():
    b = [g.t(160, 44, "漢文の「置き字」", 11, g.INK),
         g.rect(50, 56, 220, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 80, "読まないが書き添える字", 10.5, g.ACCENT),
         g.t(160, 110, "例: 也・矣・焉(文末)", 10, g.ACCENT),
         g.t(160, 132, "而(接続)・于・於(場所)", 10),
         g.t(160, 156, "訓読しない漢字", 10, g.ACCENT),
         g.t(160, 180, "返り点と一緒に使う", 9.5, g.SUB)]
    return g.titled("置き字", b)


@register("反語")
def fig_反語():
    b = [g.t(160, 44, "「〜や(いな)」→ 〜ではないか", 11, g.INK),
         g.rect(50, 56, 220, 40, g.INK, 1.3, g.FILL),
         g.t(160, 80, "疑問の形で強く否定を表す", 10.5, g.ACCENT),
         g.t(160, 110, "例: 何か恐るべきや", 10, g.ACCENT),
         g.t(160, 132, "→ 恐るべきことはない", 10),
         g.t(160, 156, "「や・か」で問いかけて否定を強調", 10, g.ACCENT),
         g.t(160, 180, "相手に強く訴える表現", 9.5, g.SUB)]
    return g.titled("反語", b)


@register("本動詞")
def fig_本動詞():
    b = [g.t(160, 44, "「走る」の本動詞", 11, g.INK),
         g.rect(50, 56, 220, 40, g.INK, 1.3, g.FILL),
         g.t(160, 80, "その動作そのものを表す", 10.5, g.ACCENT),
         g.t(160, 110, "「鳥が走る」", 10, g.ACCENT),
         g.t(160, 132, "「走っている」の「いる」は補助動詞", 10),
         g.t(160, 156, "本来の意味で使われる動詞", 10, g.ACCENT),
         g.t(160, 180, "補助動詞と対になる概念", 9.5, g.SUB)]
    return g.titled("本動詞", b)


@register("補助動詞")
def fig_補助動詞():
    b = [g.t(160, 44, "「〜ている」「〜てくれる」", 11, g.INK),
         g.rect(50, 56, 220, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 80, "前の動詞に意味を添える", 10.5, g.ACCENT),
         g.t(160, 110, "例: 読んでいる・教えてくれる", 10, g.ACCENT),
         g.t(160, 132, "「〜ておく」「〜てみる」など", 10),
         g.t(160, 156, "本来の意味が薄れている", 10, g.ACCENT),
         g.t(160, 180, "文法的な働きをする動詞", 9.5, g.SUB)]
    return g.titled("補助動詞", b)


@register("最高敬語")
def fig_最高敬語():
    b = [g.t(160, 44, "「たまふ」「おはします」", 11.5, g.INK),
         g.rect(50, 56, 220, 40, g.INK, 1.3, g.FILL),
         g.t(160, 80, "天皇や貴族に対する敬語", 10.5, g.ACCENT),
         g.t(160, 110, "例: 「帝おはします」", 10, g.ACCENT),
         g.t(160, 132, "「〜たまふ」で動作を尊敬", 10),
         g.t(160, 156, "身分の高い人への敬意", 10, g.ACCENT),
         g.t(160, 180, "古文の敬語の最高位", 9.5, g.SUB)]
    return g.titled("最高敬語", b)


@register("七五調")
def fig_七五調():
    b = [g.rect(60, 52, 82, 44, g.INK, 1.3, g.FILL),
         g.rect(172, 52, 82, 44, g.INK, 1.3, g.FILL2),
         g.t(101, 70, "7音", 12, g.ACCENT), g.t(101, 86, "(七)", 9, g.SUB),
         g.t(213, 70, "5音", 12, g.ACCENT), g.t(213, 86, "(五)", 9, g.SUB),
         g.t(160, 116, "7音と5音をくり返すリズム", 10.5),
         g.t(160, 140, "例: うさぎおいし かのやま(7-5)", 10, g.ACCENT),
         g.t(160, 164, "唱歌・詩に多い調べ", 10),
         g.t(160, 188, "五七調と対になる", 9.5, g.SUB)]
    return g.titled("七五調", b)


@register("五七調")
def fig_五七調():
    b = [g.rect(60, 52, 82, 44, g.INK, 1.3, g.FILL2),
         g.rect(172, 52, 82, 44, g.INK, 1.3, g.FILL),
         g.t(101, 70, "5音", 12, g.ACCENT), g.t(101, 86, "(五)", 9, g.SUB),
         g.t(213, 70, "7音", 12, g.ACCENT), g.t(213, 86, "(七)", 9, g.SUB),
         g.t(160, 116, "5音と7音をくり返すリズム", 10.5),
         g.t(160, 140, "例: かぞへて きけば(5-7)", 10, g.ACCENT),
         g.t(160, 164, "和歌・短歌に近い調べ", 10),
         g.t(160, 188, "七五調と対になる", 9.5, g.SUB)]
    return g.titled("五七調", b)


@register("叙景詩")
def fig_叙景詩():
    b = [g.rect(40, 44, 240, 70, g.INK, 1.3, g.FILL),
         g.path("M80,100 Q120,50 160,100 Q200,50 240,100", g.INK, 1.8),
         g.circle(230, 56, 12, g.ACCENT, 1.4, g.FILL2),
         g.t(160, 134, "風景を描き出す詩", 10.5),
         g.t(160, 156, "自然の情景をうたう", 10.5, g.ACCENT),
         g.t(160, 180, "叙情詩の一種", 10),
         g.t(160, 204, "例: 俳句・写生文にも通じる", 9.5, g.SUB)]
    return g.titled("叙景詩", b)


@register("口語自由詩")
def fig_口語自由詩():
    b = [g.rect(40, 44, 240, 44, g.INK, 1.3, g.FILL),
         g.t(160, 62, "口語で書かれた詩", 10.5),
         g.t(160, 78, "(話し言葉・現代語)", 9.5, g.ACCENT),
         g.rect(40, 96, 240, 30, g.INK, 1.0, g.FILL2),
         g.t(160, 116, "定型にとらわれない自由な形", 10, g.ACCENT),
         g.t(160, 144, "文語定型詩と対になる", 10.5),
         g.t(160, 168, "例: 口語で書かれた自由詩", 10, g.ACCENT),
         g.t(160, 192, "近代以降に広まった", 9.5, g.SUB)]
    return g.titled("口語自由詩", b)


@register("文語定型詩")
def fig_文語定型詩():
    b = [g.rect(40, 44, 240, 44, g.INK, 1.3, g.FILL),
         g.t(160, 62, "文語で書かれた詩", 10.5),
         g.t(160, 78, "(書き言葉・古典語)", 9.5, g.ACCENT),
         g.rect(40, 96, 240, 30, g.INK, 1.0, g.FILL2),
         g.t(160, 116, "五・七などの定型で書く", 10, g.ACCENT),
         g.t(160, 144, "例: 短歌・俳句・漢詩", 10.5, g.ACCENT),
         g.t(160, 168, "口語自由詩と対になる", 10),
         g.t(160, 192, "古典の詩歌の伝統", 9.5, g.SUB)]
    return g.titled("文語定型詩", b)


@register("七言絶句")
def fig_七言絶句():
    lines = ["春眠暁を覚えず", "処処啼鳥を聞く", "夜来風雨の声", "花落つること知んぬ多少ぞ"]
    b = [g.t(160, 40, "七文字 × 4句", 11, g.SUB)]
    for i, ln in enumerate(lines):
        b += _chem_box(54, 54 + i * 32, 212, 26, ln, size=11, fill=g.FILL)
    b.append(g.t(160, 194, "漢詩の形の一つ(4句で完結)", 10))
    return g.titled("七言絶句", b)


@register("五言律詩")
def fig_五言律詩():
    lines = ["国破山河在", "城春草木深", "感時花濺涙", "恨別鳥驚心",
             "烽火連三月", "家書抵万金", "白頭掻更短", "渾欲不勝簪"]
    b = [g.t(160, 40, "五文字 × 8句", 11, g.SUB)]
    for i, ln in enumerate(lines):
        b += _chem_box(74 + (i % 4) * 56, 54 + (i // 4) * 34, 46, 26, ln, size=9.5, fill=g.FILL)
    b.append(g.t(160, 136, "漢詩の形の一つ(8句で完結)", 10))
    b.append(g.t(160, 158, "例: 杜甫「春望」", 10, g.ACCENT))
    b.append(g.t(160, 182, "中間の4句が対句になる", 9.5, g.SUB))
    return g.titled("五言律詩", b)


@register("連文節")
def fig_連文節():
    b = [g.t(160, 40, "「大きな 白い 花が 咲く」", 11, g.INK),
         g.rect(50, 54, 92, 34, g.INK, 1.2, g.FILL2),
         g.rect(160, 54, 108, 34, g.INK, 1.2, g.FILL),
         g.t(96, 75, "大きな白い花が", 9.5, g.ACCENT),
         g.t(214, 75, "咲く", 9.5),
         g.t(160, 104, "文節がまとまって一つのまとまりに", 10.5),
         g.t(160, 126, "主語・述語などの成分になる", 10, g.ACCENT),
         g.t(160, 150, "文節と文節の関係をとらえる", 10),
         g.t(160, 174, "修飾・被修飾の関係をまとめる", 9.5, g.SUB)]
    return g.titled("連文節", b)


@register("和語")
def fig_和語():
    b = [g.t(160, 44, "「やまとことば」", 11, g.INK),
         g.rect(50, 56, 220, 40, g.INK, 1.3, g.FILL),
         g.t(160, 80, "日本古来の言葉", 10.5, g.ACCENT),
         g.t(160, 110, "例: 山・川・花・見る・美しい", 10, g.ACCENT),
         g.t(160, 134, "訓読みのことが多い", 10),
         g.t(160, 158, "漢語・外来語と対になる", 10, g.ACCENT),
         g.t(160, 182, "「和語」= 大和言葉", 9.5, g.SUB)]
    return g.titled("和語", b)


@register("外来語")
def fig_外来語():
    b = [g.t(160, 44, "外国から入った言葉", 11, g.INK),
         g.rect(50, 56, 220, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 80, "例: コンピューター・パン", 10.5, g.ACCENT),
         g.t(160, 110, "カタカナで書くことが多い", 10),
         g.t(160, 134, "英語由来が多いが他言語も", 10, g.ACCENT),
         g.t(160, 158, "例: ズボン(仏)・ランドセル(蘭)", 10),
         g.t(160, 182, "漢語(中国由来)は含まない", 9.5, g.SUB)]
    return g.titled("外来語", b)


@register("同訓異字")
def fig_同訓異字():
    b = [g.t(160, 44, "同じ訓でも漢字が違う", 11, g.INK),
         g.rect(50, 56, 220, 40, g.INK, 1.3, g.FILL),
         g.t(160, 80, "上がる・挙がる・揚がる", 10.5, g.ACCENT),
         g.t(160, 110, "のぼる: 登る・昇る・上る", 10, g.ACCENT),
         g.t(160, 134, "意味の違いに注意", 10),
         g.t(160, 158, "使い分けが国語の課題", 10, g.ACCENT),
         g.t(160, 182, "「あがる」は読みが同じ", 9.5, g.SUB)]
    return g.titled("同訓異字", b)


@register("方言")
def fig_方言():
    b = [g.t(160, 44, "地域によって異なる言葉", 11, g.INK),
         g.rect(50, 56, 220, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 80, "例: 関西「ほんま」・東北「んだ」", 10, g.ACCENT),
         g.t(160, 110, "発音・語彙・文法の違い", 10),
         g.t(160, 134, "共通語と対になる", 10, g.ACCENT),
         g.t(160, 158, "地域の文化の一つ", 10),
         g.t(160, 182, "方言と共通語の使い分け", 9.5, g.SUB)]
    return g.titled("方言", b)


@register("共通語")
def fig_共通語():
    b = [g.t(160, 44, "全国で通じる言葉", 11, g.INK),
         g.rect(50, 56, 220, 40, g.INK, 1.3, g.FILL),
         g.t(160, 80, "標準語とも呼ばれる", 10.5, g.ACCENT),
         g.t(160, 110, "放送・教育で使われる", 10),
         g.t(160, 134, "方言と対になる", 10, g.ACCENT),
         g.t(160, 158, "場面に応じて使い分ける", 10),
         g.t(160, 182, "相手に伝わりやすい言葉", 9.5, g.SUB)]
    return g.titled("共通語", b)


@register("話し言葉")
def fig_話し言葉():
    b = [g.t(160, 44, "話すときに使う言葉", 11, g.INK),
         g.rect(50, 56, 220, 40, g.INK, 1.3, g.FILL),
         g.t(160, 80, "「ほんとに」「〜だよね」", 10, g.ACCENT),
         g.t(160, 110, "くだけた言い方", 10),
         g.t(160, 134, "書き言葉と対になる", 10, g.ACCENT),
         g.t(160, 158, "場面によって使い分ける", 10),
         g.t(160, 182, "音声による伝達", 9.5, g.SUB)]
    return g.titled("話し言葉", b)


@register("書き言葉")
def fig_書き言葉():
    b = [g.t(160, 44, "書くときに使う言葉", 11, g.INK),
         g.rect(50, 56, 220, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 80, "「本当に」「〜である」", 10, g.ACCENT),
         g.t(160, 110, "整った言い方", 10),
         g.t(160, 134, "話し言葉と対になる", 10, g.ACCENT),
         g.t(160, 158, "文書・文章で使う", 10),
         g.t(160, 182, "正確さが求められる", 9.5, g.SUB)]
    return g.titled("書き言葉", b)


@register("複合語")
def fig_複合語():
    b = [g.t(160, 44, "山 + 道 = 山道", 12, g.ACCENT),
         g.rect(50, 56, 90, 40, g.INK, 1.3, g.FILL),
         g.rect(180, 56, 90, 40, g.INK, 1.3, g.FILL2),
         g.t(95, 76, "山", 13, g.INK), g.t(225, 76, "道", 13, g.ACCENT),
         g.t(145, 76, "+", 14, g.INK), g.t(160, 116, "二つ以上の語が結びついた語", 10.5),
         g.t(160, 138, "例: 花見・読み物・目玉焼き", 10, g.ACCENT),
         g.t(160, 162, "意味が組み合わさる", 10),
         g.t(160, 186, "熟語も複合語の一種", 9.5, g.SUB)]
    return g.titled("複合語", b)


@register("接続語")
def fig_接続語():
    b = [g.t(160, 40, "「しかし」「また」「だから」", 10.5, g.INK),
         g.rect(40, 54, 240, 40, g.INK, 1.3, g.FILL),
         g.t(160, 78, "文と文をつなぐ言葉", 10.5, g.ACCENT),
         g.t(160, 108, "順接: だから・それで", 10, g.ACCENT),
         g.t(160, 130, "逆接: しかし・けれども", 10),
         g.t(160, 152, "並立: また・そして", 10, g.ACCENT),
         g.t(160, 176, "接続語で文章のつながりがわかる", 9.5, g.SUB)]
    return g.titled("接続語", b)


@register("敬語")
def fig_敬語():
    b = [g.t(160, 40, "相手を敬う言い方", 11, g.INK)]
    for i, (name, ex) in enumerate([("尊敬語", "おっしゃる"), ("謙譲語", "申す"), ("丁寧語", "です・ます")]):
        x = 28 + i * 96
        b += _chem_box(x, 50, 80, 38, name, size=11, fill=g.FILL2, color=g.ACCENT)
        b.append(g.t(x + 40, 102, ex, 10, g.INK))
    b += [g.t(160, 132, "相手や話題の人物への敬意を表す", 10.5),
          g.t(160, 154, "場面や関係によって使い分ける", 10, g.ACCENT),
          g.t(160, 178, "仕事の場面では特に重要", 10),
          g.t(160, 202, "美化語(お酒・ご飯)もある", 9.5, g.SUB)]
    return g.titled("敬語", b)


# ---- 音楽(構造語) -----------------------------------------------------------


@register("提示部")
def fig_提示部():
    b = [g.rect(36, 44, 248, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 66, "第1主題・第2主題を提示する部分", 10, g.ACCENT),
         g.rect(36, 96, 72, 40, g.INK, 1.2, g.FILL),
         g.rect(124, 96, 72, 40, g.INK, 1.2, g.FILL),
         g.rect(212, 96, 72, 40, g.INK, 1.2, g.FILL2),
         g.t(72, 116, "提示部", 9, g.ACCENT), g.t(160, 116, "展開部", 9), g.t(248, 116, "再現部", 9),
         g.t(160, 156, "ソナタ形式の最初の部分", 10.5),
         g.t(160, 178, "主題がはっきり示される", 10, g.ACCENT),
         g.t(160, 200, "「聞かせる」役割", 9.5, g.SUB)]
    return g.titled("提示部", b)


@register("展開部")
def fig_展開部():
    b = [g.rect(36, 96, 72, 40, g.INK, 1.2, g.FILL),
         g.rect(124, 96, 72, 40, g.INK, 1.2, g.FILL2),
         g.rect(212, 96, 72, 40, g.INK, 1.2, g.FILL),
         g.t(72, 116, "提示部", 9), g.t(160, 116, "展開部", 9, g.ACCENT), g.t(248, 116, "再現部", 9),
         g.t(160, 60, "主題を変化・発展させる部分", 10, g.ACCENT),
         g.t(160, 156, "ソナタ形式の中央部分", 10.5),
         g.t(160, 178, "転調・モチーフの変形で盛り上げる", 10, g.ACCENT),
         g.t(160, 200, "「葛藤・発展」の役割", 9.5, g.SUB)]
    return g.titled("展開部", b)


@register("再現部")
def fig_再現部():
    b = [g.rect(36, 96, 72, 40, g.INK, 1.2, g.FILL),
         g.rect(124, 96, 72, 40, g.INK, 1.2, g.FILL),
         g.rect(212, 96, 72, 40, g.INK, 1.2, g.FILL2),
         g.t(72, 116, "提示部", 9), g.t(160, 116, "展開部", 9), g.t(248, 116, "再現部", 9, g.ACCENT),
         g.t(160, 60, "主題が再び現れる部分", 10, g.ACCENT),
         g.t(160, 156, "ソナタ形式の最後の部分", 10.5),
         g.t(160, 178, "提示部の主題を主調で再現", 10, g.ACCENT),
         g.t(160, 200, "「帰ってくる」安心感", 9.5, g.SUB)]
    return g.titled("再現部", b)


@register("変奏曲")
def fig_変奏曲():
    b = [g.t(160, 44, "主題", 11, g.INK),
         g.rect(60, 54, 200, 28, g.INK, 1.2, g.FILL2),
         g.arrow(160, 88, 160, 106, g.INK, 1.4),
         g.rect(40, 112, 52, 30, g.INK, 1.2, g.FILL),
         g.rect(134, 112, 52, 30, g.INK, 1.2, g.FILL),
         g.rect(228, 112, 52, 30, g.INK, 1.2, g.FILL2),
         g.t(66, 130, "変奏1", 8.5), g.t(160, 130, "変奏2", 8.5), g.t(254, 130, "変奏3…", 8.5),
         g.t(160, 160, "主題をリズム・旋律・和声などで", 10.5),
         g.t(160, 182, "様々に変化させて展開する曲", 10.5, g.ACCENT),
         g.t(160, 206, "例: ベートーヴェンの変奏曲", 9.5, g.SUB)]
    return g.titled("変奏曲", b)


@register("形式")
def fig_形式():
    b = [g.t(160, 44, "曲のまとまり・構造", 11, g.INK),
         g.rect(40, 58, 52, 40, g.INK, 1.2, g.FILL),
         g.rect(134, 58, 52, 40, g.INK, 1.2, g.FILL),
         g.rect(228, 58, 52, 40, g.INK, 1.2, g.FILL2),
         g.t(66, 78, "A", 11), g.t(160, 78, "B", 11), g.t(254, 78, "A", 11, g.ACCENT),
         g.t(160, 112, "二部形式・三部形式など", 10, g.ACCENT),
         g.t(160, 136, "A-B-A は「三部形式」", 10.5),
         g.t(160, 160, "繰り返し・対比の組み立て方", 10, g.ACCENT),
         g.t(160, 184, "楽曲の構造(フレーズのまとまり)", 9.5, g.SUB)]
    return g.titled("形式", b)


@register("リズムパターン")
def fig_リズムパターン():
    b = [g.line(60, 120, 260, 120, g.SUB, 1.2),
         g.line(60, 120, 60, 60, g.SUB, 1.2),
         g.t(44, 54, "強", 9, g.ACCENT),
         g.line(84, 120, 84, 84, g.INK, 2.0),
         g.line(128, 120, 128, 100, g.INK, 1.2),
         g.line(172, 120, 172, 100, g.INK, 1.2),
         g.line(216, 120, 216, 84, g.INK, 2.0),
         g.line(260, 120, 260, 100, g.INK, 1.2),
         g.t(160, 148, "強弱・長短の組み合わせのくり返し", 10.5),
         g.t(160, 170, "ジャンルごとに特徴的なパターン", 10, g.ACCENT),
         g.t(160, 194, "例: ロックの8ビート・ワルツの3拍子", 9.5, g.SUB)]
    return g.titled("リズムパターン", b)


@register("祭囃子")
def fig_祭囃子():
    b = [g.rect(40, 48, 240, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 68, "祭りで奏でるお囃子(和太鼓・笛など)", 9.5, g.ACCENT),
         g.rect(70, 104, 40, 26, g.INK, 1.2, g.FILL),
         g.rect(140, 104, 40, 26, g.INK, 1.2, g.FILL),
         g.rect(210, 104, 40, 26, g.INK, 1.2, g.FILL),
         g.t(90, 122, "太鼓", 8.5), g.t(160, 122, "笛", 8.5), g.t(230, 122, "鉦", 8.5),
         g.t(160, 150, "祭礼の雰囲気をつくる音楽", 10.5),
         g.t(160, 172, "地域ごとに特徴的なリズム", 10, g.ACCENT),
         g.t(160, 196, "神輿や山車とともに奏でられる", 9.5, g.SUB)]
    return g.titled("祭囃子", b)


@register("寄せの合方")
def fig_寄せの合方():
    b = [g.rect(40, 48, 240, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 68, "謡や舞の合間に奏でる囃子", 9.5, g.ACCENT),
         g.rect(60, 100, 200, 34, g.INK, 1.2, g.FILL),
         g.t(160, 122, "太鼓・笛・小鼓・大鼓", 9.5),
         g.t(160, 150, "能や狂言の演奏形式の一つ", 10.5),
         g.t(160, 172, "場面の転換・盛り上げに使う", 10, g.ACCENT),
         g.t(160, 196, "「合方」= 囃子だけの部分", 9.5, g.SUB)]
    return g.titled("寄せの合方", b)


@register("唱歌")
def fig_唱歌():
    b = [g.rect(40, 48, 240, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 68, "学校教育のために作られた歌", 9.5, g.ACCENT),
         g.t(160, 104, "明治期の「唱歌」に始まる", 10.5),
         g.t(160, 126, "例: ふるさと・朧月夜・茶摘", 10, g.ACCENT),
         g.t(160, 150, "文部省唱歌として普及", 10),
         g.t(160, 174, "現在の教科書にも掲載", 10, g.ACCENT),
         g.t(160, 198, "日本独自の歌曲文化", 9.5, g.SUB)]
    return g.titled("唱歌", b)


@register("現代音楽")
def fig_現代音楽():
    b = [g.rect(40, 48, 240, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 68, "20世紀以降の多様な音楽", 9.5, g.ACCENT),
         g.t(160, 104, "無調・12音技法・電子音など", 10, g.ACCENT),
         g.t(160, 126, "従来の枠にとらわれない表現", 10.5),
         g.t(160, 150, "例: シェーンベルク・ケージ", 10, g.ACCENT),
         g.t(160, 174, "現代の作曲技法を学ぶ", 10),
         g.t(160, 198, "ポピュラー音楽とも相互に影響", 9.5, g.SUB)]
    return g.titled("現代音楽", b)


@register("民族音楽")
def fig_民族音楽():
    b = [g.rect(40, 48, 240, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 68, "各地域で伝えられてきた音楽", 9.5, g.ACCENT),
         g.t(160, 104, "民族ごとの楽器・音階・リズム", 10, g.ACCENT),
         g.t(160, 126, "例: ガムラン・フラメンコ・雅楽", 10),
         g.t(160, 150, "生活や祭りと結びつく", 10.5),
         g.t(160, 174, "口承で伝わる音楽", 10, g.ACCENT),
         g.t(160, 198, "世界の音楽を学ぶ際の柱", 9.5, g.SUB)]
    return g.titled("民族音楽", b)


@register("ポピュラー音楽")
def fig_ポピュラー音楽():
    b = [g.rect(40, 48, 240, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 68, "大衆に親しまれる音楽", 9.5, g.ACCENT),
         g.t(160, 104, "ポップス・ロック・ジャズなど", 10, g.ACCENT),
         g.t(160, 126, "幅広い世代に親しまれる", 10.5),
         g.t(160, 150, "J-POPの背景として学ぶ", 10, g.ACCENT),
         g.t(160, 174, "メディアとともに発展", 10),
         g.t(160, 198, "クラシック・民族音楽と対比される", 9.5, g.SUB)]
    return g.titled("ポピュラー音楽", b)


@register("天球図")
def fig_天球図():
    b = [g.circle(160, 92, 58, g.INK, 1.6),
         g.circle(160, 92, 44, g.INK, 1.0, g.FILL),
         g.circle(160, 92, 24, g.INK, 1.0),
         g.line(102, 92, 218, 92, g.INK, 1.0),
         g.line(160, 34, 160, 150, g.INK, 1.0),
         g.dot(160, 92, 3.0, g.ACCENT),
         g.t(160, 84, "★", 10, g.ACCENT),
         g.t(160, 164, "天体の位置を表した図", 10.5),
         g.t(160, 186, "天球を球として描く", 10, g.ACCENT),
         g.t(160, 208, "星座早見盤にもつながる", 9.5, g.SUB)]
    return g.titled("天球図", b)


# ---- 美術 ---------------------------------------------------------------


@register("伝統色")
def fig_伝統色():
    cols = [("#a8d8ea", "水色"), ("#7b6c9e", "藤色"), ("#e78b8b", "珊瑚色"),
            ("#9fae5c", "若草色"), ("#e8b9c3", "桜色"), ("#3b3b3b", "墨色")]
    b = []
    for i, (c, name) in enumerate(cols):
        x = 28 + (i % 3) * 96
        y = 46 + (i // 3) * 52
        b += [g.rect(x, y, 76, 32, g.INK, 1.0, c, rx=4),
              g.t(x + 38, y + 44, name, 9.5)]
    b += [g.t(160, 156, "日本で親しまれてきた色の名前", 10.5),
          g.t(160, 178, "自然や暮らしから生まれた", 10, g.ACCENT),
          g.t(160, 200, "例: 藍色・茜色・山吹色", 9.5, g.SUB)]
    return g.titled("伝統色", b)


@register("パッケージ")
def fig_パッケージ():
    b = [g.rect(100, 44, 120, 76, g.INK, 1.8, g.FILL2),
         g.path("M100,44 L130,60 L130,120", g.INK, 1.2),
         g.path("M220,44 L190,60 L190,120", g.INK, 1.2),
         g.line(100, 44, 130, 60, g.INK, 1.2), g.line(220, 44, 190, 60, g.INK, 1.2),
         g.t(160, 92, "商品", 11, g.ACCENT),
         g.t(160, 140, "商品を包む容器・デザイン", 10.5),
         g.t(160, 162, "保護・運搬・表示の機能", 10, g.ACCENT),
         g.t(160, 186, "購入意欲にも影響する", 10),
         g.t(160, 210, "意匠・ユニバーサルデザインも関連", 9.5, g.SUB)]
    return g.titled("パッケージ", b)


@register("デペイズマン")
def fig_デペイズマン():
    b = [g.circle(90, 92, 30, g.INK, 1.6, g.FILL),
         g.t(90, 97, "林檎", 9.5),
         g.t(160, 66, "×", 16, g.ACCENT),
         g.rect(200, 52, 64, 80, g.INK, 1.6, g.FILL2),
         g.t(232, 92, "机", 9.5),
         g.t(160, 148, "異なるものを組み合わせて", 10.5),
         g.t(160, 170, "違和感を生み出す表現", 10.5, g.ACCENT),
         g.t(160, 194, "シュルレアリスムの手法", 10),
         g.t(160, 218, "「非日常化」による驚き", 9.5, g.SUB)]
    return g.titled("デペイズマン", b)


@register("量感")
def fig_量感():
    b = [g.circle(160, 90, 46, g.INK, 1.6, g.FILL),
         g.circle(160, 90, 30, g.INK, 1.0, g.FILL2),
         g.circle(160, 90, 14, g.INK, 1.0),
         g.path("M114,90 Q160,40 206,90", g.ACCENT, 1.4),
         g.t(160, 150, "立体としての重み・存在感", 10.5),
         g.t(160, 172, "陰影や明暗で表す", 10, g.ACCENT),
         g.t(160, 196, "彫刻・デッサンで大切", 10),
         g.t(160, 220, "「かさ」の感じ", 9.5, g.SUB)]
    return g.titled("量感", b)


@register("造形")
def fig_造形():
    b = [g.rect(50, 44, 100, 70, g.INK, 1.4, g.FILL),
         g.circle(200, 70, 30, g.INK, 1.4, g.FILL2),
         g.line(150, 90, 170, 82, g.INK, 1.2),
         g.t(160, 136, "形や色・材料を工夫して", 10.5),
         g.t(160, 158, "作品をつくること", 10.5, g.ACCENT),
         g.t(160, 182, "平面(絵)・立体(彫刻)・工芸", 10),
         g.t(160, 206, "バランス・構成を考える", 9.5, g.SUB)]
    return g.titled("造形", b)


@register("修復")
def fig_修復():
    b = [g.rect(60, 44, 90, 80, g.INK, 1.5, g.FILL),
         g.path("M70,50 L96,72 M96,50 L70,72", g.ACCENT, 2.2),
         g.rect(190, 44, 90, 80, g.INK, 1.5, g.FILL2),
         g.path("M200,60 L214,88 M228,60 L214,88", g.INK, 1.2),
         g.t(105, 140, "壊れた作品", 9.5), g.t(235, 140, "元の姿へ", 9.5, g.ACCENT),
         g.t(160, 162, "傷んだ文化財・美術品を", 10.5),
         g.t(160, 184, "元の状態に近づけて直す", 10.5, g.ACCENT),
         g.t(160, 208, "文化財の保護活動", 9.5, g.SUB)]
    return g.titled("修復", b)


@register("躍動感")
def fig_躍動感():
    b = [g.path("M60,110 Q100,60 140,110 Q180,60 220,110", g.ACCENT, 3.0),
         g.path("M60,140 Q110,100 160,140 Q210,100 260,140", g.INK, 2.0),
         g.t(160, 168, "動き・勢いを感じさせる表現", 10.5),
         g.t(160, 190, "曲線・斜め・リズムで表す", 10, g.ACCENT),
         g.t(160, 214, "スポーツ・動物などの描写に", 9.5, g.SUB)]
    return g.titled("躍動感", b)


@register("仮名書道")
def fig_仮名書道():
    b = [g.t(160, 78, "かな", 34, g.INK, "middle", "Noto Serif CJK JP,Noto Serif JP,Hiragino Mincho ProN,serif", "400"),
         g.t(160, 122, "ひらがなを中心に書く書道", 10.5),
         g.t(160, 146, "流れるような線・余白の美", 10, g.ACCENT),
         g.t(160, 170, "漢字書道と対になる日本の書", 10),
         g.t(160, 194, "色紙・短冊にも用いられる", 9.5, g.SUB)]
    return g.titled("仮名書道", b)


# ---- 英語(文型・段落構造) ---------------------------------------------------


def _bunkei(word, s, v, o, c, note):
    b = []
    labels = [("S", "主語", s), ("V", "動詞", v), ("O", "目的語", o), ("C", "補語", c)]
    x0 = 40
    for i, (sym, name, ex) in enumerate(labels):
        if ex is None:
            continue
        x = x0 + i * 62
        b += _chem_box(x, 46, 50, 40, sym, size=16, fill=g.FILL2 if sym == "V" else g.FILL,
                       color=g.ACCENT if sym == "V" else g.INK)
        b.append(g.t(x + 25, 98, name, 9, g.SUB))
    b += [g.t(160, 122, note, 11, g.ACCENT),
          g.t(160, 146, word, 10.5),
          g.t(160, 170, "5文型の基本となる形", 10),
          g.t(160, 194, "例文で語順を確認する", 9.5, g.SUB)]
    return g.titled(word, b)


@register("第一文型")
def fig_第一文型():
    return _bunkei("第一文型", "S", "V", None, None, "S V — 主語 + 動詞")


@register("第二文型")
def fig_第二文型():
    return _bunkei("第二文型", "S", "V", None, "C", "S V C — 主語 = 補語")


@register("第三文型")
def fig_第三文型():
    return _bunkei("第三文型", "S", "V", "O", None, "S V O — 主語 + 動詞 + 目的語")


@register("第四文型")
def fig_第四文型():
    return _bunkei("第四文型", "S", "V", "O(人)", "O(物)", "S V O O — 人に物を与える")


@register("第五文型")
def fig_第五文型():
    return _bunkei("第五文型", "S", "V", "O", "C", "S V O C — 目的語 = 補語")


@register("文の要素")
def fig_文の要素():
    b = []
    for i, (sym, name, ex) in enumerate([("S", "主語", "誰が・何が"),
                                         ("V", "動詞", "する・である"),
                                         ("O", "目的語", "〜を(に)"),
                                         ("C", "補語", "主語=補語")]):
        x = 30 + i * 70
        b += _chem_box(x, 46, 56, 40, sym, size=16, fill=g.FILL2 if sym == "V" else g.FILL,
                       color=g.ACCENT if sym == "V" else g.INK)
        b.append(g.t(x + 28, 98, name, 9, g.SUB))
        b.append(g.t(x + 28, 112, ex, 8, g.ACCENT))
    b += [g.t(160, 136, "文を組み立てる4つの働き", 10.5),
          g.t(160, 158, "S V O C の並びで文型が決まる", 10, g.ACCENT),
          g.t(160, 182, "文型判断の基礎", 10),
          g.t(160, 206, "例: I (S) love (V) music (O)", 9.5, g.SUB)]
    return g.titled("文の要素", b)


@register("二重目的語")
def fig_二重目的語():
    b = [g.t(160, 44, "She gave me a book.", 12, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 66, "V        O(人)     O(物)", 10.5, g.ACCENT),
         g.t(160, 92, "「人に物を〜する」", 10.5),
         g.t(160, 114, "人と物の2つの目的語をとる", 10.5, g.ACCENT),
         g.t(160, 138, "to/for + 人 に書き換え可能", 10),
         g.t(160, 162, "例: gave the book to me", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 186, "第四文型の特徴", 9.5, g.SUB)]
    return g.titled("二重目的語", b)


@register("形式主語")
def fig_形式主語():
    b = [g.t(160, 44, "It is important to study.", 11.5, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 60, 36, g.INK, 1.3, g.FILL2),
         g.rect(220, 56, 60, 36, g.INK, 1.3, g.FILL),
         g.t(70, 78, "It(形式主語)", 9.5, g.ACCENT),
         g.t(250, 78, "to study(真主語)", 9, g.ACCENT),
         g.t(160, 110, "長い主語を文末に回す", 10.5),
         g.t(160, 132, "It is 〜 to … の構文", 10.5, g.ACCENT),
         g.t(160, 156, "文のバランスを整える", 10),
         g.t(160, 180, "形式目的語 it もある", 9.5, g.SUB)]
    return g.titled("形式主語", b)


@register("主節")
def fig_主節():
    b = [g.t(160, 44, "I think that he is kind.", 11.5, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 90, 40, g.INK, 1.3, g.FILL2),
         g.rect(150, 56, 130, 40, g.INK, 1.3, g.FILL),
         g.t(85, 78, "主節", 10, g.ACCENT), g.t(215, 78, "従属節(that節)", 9.5, g.ACCENT),
         g.t(160, 114, "文の中心になる節", 10.5),
         g.t(160, 136, "従属節を支える骨組み", 10.5, g.ACCENT),
         g.t(160, 160, "従属節は主節の一部になる", 10),
         g.t(160, 184, "複文の基本構造", 9.5, g.SUB)]
    return g.titled("主節", b)


@register("従属節")
def fig_従属節():
    b = [g.t(160, 44, "I think that he is kind.", 11.5, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 90, 40, g.INK, 1.3, g.FILL),
         g.rect(150, 56, 130, 40, g.INK, 1.3, g.FILL2),
         g.t(85, 78, "主節", 10), g.t(215, 78, "従属節(that節)", 9.5, g.ACCENT),
         g.t(160, 114, "主節の中で働く節", 10.5),
         g.t(160, 136, "名詞節・形容詞節・副詞節がある", 10.5, g.ACCENT),
         g.t(160, 160, "接続詞・関係詞で導かれる", 10),
         g.t(160, 184, "単独では文にならない", 9.5, g.SUB)]
    return g.titled("従属節", b)


@register("名詞節")
def fig_名詞節():
    b = [g.t(160, 44, "I know that he is busy.", 11.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "that節 = 「〜ということ」", 10.5, g.ACCENT),
         g.t(160, 96, "文の中で名詞の働き(S・O・C)", 10.5),
         g.t(160, 120, "例: What he said is true.", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 144, "what 節も名詞節", 10),
         g.t(160, 168, "主語・目的語・補語になれる", 10, g.ACCENT),
         g.t(160, 192, "間接疑問(if/whether)も同類", 9.5, g.SUB)]
    return g.titled("名詞節", b)


@register("形容詞節")
def fig_形容詞節():
    b = [g.t(160, 44, "The book which I read is good.", 10.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "which節 = 「私が読んだ」", 10.5, g.ACCENT),
         g.t(160, 96, "文の中で形容詞の働き(名詞を修飾)", 10.5),
         g.t(160, 120, "関係代名詞・関係副詞で導く", 10, g.ACCENT),
         g.t(160, 144, "先行詞の説明をする", 10),
         g.t(160, 168, "例: the boy who runs fast", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 192, "制限用法・非制限用法がある", 9.5, g.SUB)]
    return g.titled("形容詞節", b)


@register("副詞節")
def fig_副詞節():
    b = [g.t(160, 44, "Because it rained, I stayed home.", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "because節 = 「雨が降ったので」", 10, g.ACCENT),
         g.t(160, 96, "文の中で副詞の働き(動詞を修飾)", 10.5),
         g.t(160, 120, "時・理由・条件・譲歩などを表す", 10, g.ACCENT),
         g.t(160, 144, "例: when / if / although 節", 10),
         g.t(160, 168, "主節の前後どちらにも置ける", 10, g.ACCENT),
         g.t(160, 192, "文頭に置くとコンマを使う", 9.5, g.SUB)]
    return g.titled("副詞節", b)


@register("パラグラフライティング")
def fig_パラグラフライティング():
    b = [g.rect(90, 42, 140, 28, g.INK, 1.3, g.FILL2),
         g.t(160, 61, "トピックセンテンス", 9.5, g.ACCENT),
         g.rect(50, 76, 220, 34, g.INK, 1.2, g.FILL),
         g.t(160, 97, "サポーティングセンテンス①", 9),
         g.rect(50, 112, 220, 34, g.INK, 1.2, g.FILL),
         g.t(160, 133, "サポーティングセンテンス②", 9),
         g.rect(50, 148, 220, 28, g.INK, 1.2, g.FILL2),
         g.t(160, 167, "まとめ(結論)", 9, g.ACCENT),
         g.t(160, 196, "段落を「序論→本論→結論」で構成", 9.5)]
    return g.titled("パラグラフライティング", b)


@register("トピックセンテンス")
def fig_トピックセンテンス():
    b = [g.rect(40, 44, 240, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "段落の中心となる文", 10.5, g.ACCENT),
         g.t(160, 76, "(たいてい段落の最初)", 8.5, g.SUB),
         g.t(160, 104, "「何について書くか」を示す", 10.5),
         g.t(160, 128, "後ろの文で具体化される", 10, g.ACCENT),
         g.t(160, 152, "段落全体の要約になる", 10),
         g.t(160, 176, "書く前に決めると構成しやすい", 10, g.ACCENT),
         g.t(160, 200, "パラグラフライティングの要", 9.5, g.SUB)]
    return g.titled("トピックセンテンス", b)


@register("サポーティングセンテンス")
def fig_サポーティングセンテンス():
    b = [g.rect(40, 44, 240, 36, g.INK, 1.3, g.FILL2),
         g.t(160, 66, "トピックセンテンスを支える文", 10, g.ACCENT),
         g.rect(40, 86, 240, 30, g.INK, 1.2, g.FILL),
         g.t(160, 105, "具体例・理由・説明", 9.5),
         g.rect(40, 118, 240, 30, g.INK, 1.2, g.FILL),
         g.t(160, 137, "データ・体験談など", 9.5),
         g.t(160, 166, "トピック文を具体化する役割", 10.5),
         g.t(160, 190, "複数並べて段落を充実させる", 10, g.ACCENT),
         g.t(160, 214, "トピック文と矛盾しない内容に", 9.5, g.SUB)]
    return g.titled("サポーティングセンテンス", b)


@register("比較構文")
def fig_比較構文():
    b = [g.rect(50, 50, 70, 40, g.INK, 1.3, g.FILL),
         g.rect(150, 34, 70, 56, g.INK, 1.3, g.FILL2),
         g.rect(230, 60, 40, 30, g.INK, 1.3, g.FILL),
         g.t(85, 72, "A", 11), g.t(185, 58, "B", 11, g.ACCENT), g.t(250, 78, "C", 11),
         g.t(160, 110, "as 〜 as(同級)", 10, g.ACCENT),
         g.t(160, 132, "比較級: A is bigger than B", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 156, "最上級: the biggest of C", 10),
         g.t(160, 180, "3つの級で程度を表す", 10, g.ACCENT),
         g.t(160, 204, "倍数表現・クジラ構文とも関連", 9.5, g.SUB)]
    return g.titled("比較構文", b)


@register("倍数表現")
def fig_倍数表現():
    b = [g.rect(50, 50, 60, 40, g.INK, 1.3, g.FILL),
         g.rect(140, 26, 60, 64, g.INK, 1.3, g.FILL2),
         g.t(80, 72, "A", 11), g.t(170, 56, "2倍のB", 10, g.ACCENT),
         g.t(160, 108, "twice as 〜 as / three times as 〜 as", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 132, "「AはBの○倍〜」を表す", 10.5),
         g.t(160, 156, "例: This is twice as long as that.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 180, "as 〜 as の形で倍数を前におく", 10),
         g.t(160, 204, "比較構文の応用", 9.5, g.SUB)]
    return g.titled("倍数表現", b)


@register("クジラ構文")
def fig_クジラ構文():
    b = [g.t(160, 44, "A whale is no more a fish than a horse is.", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「クジラが魚でないように、〜も…ない」", 9.5, g.ACCENT),
         g.t(160, 96, "no more 〜 than … の構文", 10.5),
         g.t(160, 120, "than の後は主語+動詞で終わる", 10, g.ACCENT),
         g.t(160, 144, "「どちらも〜でない」の比較", 10),
         g.t(160, 168, "例: He is no more a poet than I am.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 192, "英語の難構文の代表", 9.5, g.SUB)]
    return g.titled("クジラ構文", b)


@register("倒置")
def fig_倒置():
    b = [g.t(160, 44, "Never have I seen such a sight.", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 68, "否定語を文頭に出すと", 10.5),
         g.t(160, 90, "主語と動詞が入れ替わる", 10.5, g.ACCENT),
         g.t(160, 114, "例: Here comes the bus.", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 138, "強調・語順の変化", 10),
         g.t(160, 162, "「〜が…に」の倒置もある", 10, g.ACCENT),
         g.t(160, 186, "文のリズム・強調の技法", 9.5, g.SUB)]
    return g.titled("倒置", b)


@register("強調構文")
def fig_強調構文():
    b = [g.t(160, 44, "It is Tom that I like.", 11, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(50, 56, 90, 36, g.INK, 1.3, g.FILL2),
         g.t(95, 78, "強調したい語", 9.5, g.ACCENT),
         g.t(160, 96, "「私が好きなのはトムだ」", 10.5),
         g.t(160, 120, "It is 〜 that … の構文", 10.5, g.ACCENT),
         g.t(160, 144, "that の後は元の文の残り", 10),
         g.t(160, 168, "例: It was yesterday that …", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 192, "形式主語の it とは別物", 9.5, g.SUB)]
    return g.titled("強調構文", b)


@register("省略")
def fig_省略():
    b = [g.t(160, 44, "(You) Come here.", 11.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "前後の文脈から分かる語を省く", 10.5, g.ACCENT),
         g.t(160, 94, "命令文の主語 You の省略", 10.5),
         g.t(160, 118, "例: (I) hope so.", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 142, "比較構文の than 以下も省略される", 10),
         g.t(160, 166, "自然で簡潔な表現になる", 10, g.ACCENT),
         g.t(160, 190, "文脈が省略を許す", 9.5, g.SUB)]
    return g.titled("省略", b)


# ---- 社会(制度・地理の概念図) ---------------------------------------------


@register("租庸調")
def fig_租庸調():
    b = []
    for i, (name, note, ex) in enumerate([("租", "米の税", "収穫の約3%"),
                                          ("庸", "労役", "都で年10日働く"),
                                          ("調", "特産物", "絹・布などを納める")]):
        x = 30 + i * 96
        b += _chem_box(x, 46, 80, 40, name, size=16, fill=g.FILL2, color=g.ACCENT)
        b.append(g.t(x + 40, 100, note, 9.5, g.INK))
        b.append(g.t(x + 40, 114, ex, 8.5, g.SUB))
    b += [g.t(160, 140, "律令国家の3つの税", 10.5),
          g.t(160, 162, "人民に課された税・労役", 10, g.ACCENT),
          g.t(160, 186, "班田収授の法とセット", 10),
          g.t(160, 210, "奈良・平安時代の税制", 9.5, g.SUB)]
    return g.titled("租庸調", b)


@register("大宝律令")
def fig_大宝律令():
    b = [g.rect(50, 44, 90, 40, g.INK, 1.3, g.FILL2),
         g.rect(180, 44, 90, 40, g.INK, 1.3, g.FILL),
         g.t(95, 62, "律(刑法)", 10.5, g.ACCENT), g.t(225, 62, "令(行政法)", 10.5, g.ACCENT),
         g.t(160, 100, "701年に制定", 10.5),
         g.t(160, 122, "律令国家の基本法典", 10.5, g.ACCENT),
         g.t(160, 146, "天皇中心の政治のしくみ", 10),
         g.t(160, 170, "大宝 → 養老律令へ引き継がれる", 10, g.ACCENT),
         g.t(160, 194, "日本最初の本格的な律令", 9.5, g.SUB)]
    return g.titled("大宝律令", b)


@register("三世一身法")
def fig_三世一身法():
    b = [g.t(160, 44, "723年 — 墾田の私有を許可", 10.5, g.INK),
         g.rect(40, 58, 240, 40, g.INK, 1.3, g.FILL),
         g.t(160, 80, "新しく開いた田は三代まで私有可", 10, g.ACCENT),
         g.t(160, 112, "灌漑施設(溝・池)を作れば三代", 10),
         g.t(160, 134, "それ以外は一代", 10, g.ACCENT),
         g.t(160, 158, "農地開発を促すための法", 10.5),
         g.t(160, 182, "しかし私有の範囲が広がる原因に", 10, g.ACCENT),
         g.t(160, 206, "後に墾田永年私財法(743年)へ", 9.5, g.SUB)]
    return g.titled("三世一身法", b)


@register("荘園公領制")
def fig_荘園公領制():
    b = [g.rect(40, 46, 100, 80, g.INK, 1.3, g.FILL2),
         g.rect(180, 46, 100, 80, g.INK, 1.3, g.FILL),
         g.t(90, 70, "荘園", 10.5, g.ACCENT),
         g.t(90, 88, "(貴族・寺社の領地)", 8.5, g.SUB),
         g.t(230, 70, "公領(国衙領)", 10.5),
         g.t(230, 88, "(国司が支配)", 8.5, g.SUB),
         g.t(160, 148, "土地の支配が二つに分かれた", 10.5),
         g.t(160, 170, "荘園は不輸不入の権で保護", 10, g.ACCENT),
         g.t(160, 194, "院政期の支配の基礎", 10),
         g.t(160, 218, "荘園と公領が並立した体制", 9.5, g.SUB)]
    return g.titled("荘園公領制", b)


@register("不輸不入の権")
def fig_不輸不入の権():
    b = [g.rect(50, 46, 100, 44, g.INK, 1.3, g.FILL2),
         g.rect(170, 46, 100, 44, g.INK, 1.3, g.FILL),
         g.t(100, 64, "不輸の権", 10, g.ACCENT),
         g.t(100, 80, "(税を納めない)", 8.5, g.SUB),
         g.t(220, 64, "不入の権", 10, g.ACCENT),
         g.t(220, 80, "(役人が入れない)", 8.5, g.SUB),
         g.t(160, 110, "荘園を国司の支配から守る権利", 10.5),
         g.t(160, 132, "荘園領主が朝廷から認められた", 10, g.ACCENT),
         g.t(160, 156, "荘園の増加につながった", 10),
         g.t(160, 180, "荘園公領制の成立要因", 10, g.ACCENT),
         g.t(160, 204, "院政期に広く認められた", 9.5, g.SUB)]
    return g.titled("不輸不入の権", b)


@register("地頭")
def fig_地頭():
    b = [g.rect(50, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.rect(170, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.t(100, 60, "守護", 10, g.ACCENT), g.t(100, 76, "(国ごと)", 8.5, g.SUB),
         g.t(220, 60, "地頭", 10, g.ACCENT), g.t(220, 76, "(荘園・公領ごと)", 8.5, g.SUB),
         g.t(160, 104, "鎌倉幕府が設置した役職", 10.5),
         g.t(160, 126, "土地の管理・年貢の取り立て", 10, g.ACCENT),
         g.t(160, 150, "御家人が任命された", 10),
         g.t(160, 174, "荘園の支配者として力を強めた", 10, g.ACCENT),
         g.t(160, 198, "承久の乱後は西国にも広がる", 9.5, g.SUB)]
    return g.titled("地頭", b)


@register("執権")
def fig_執権():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "将軍を補佐する最高職", 10, g.ACCENT),
         g.t(160, 76, "(北条氏が世襲)", 8.5, g.SUB),
         g.t(160, 104, "鎌倉幕府の政治の実権を握った", 10.5),
         g.t(160, 126, "初代執権: 北条時政", 10, g.ACCENT),
         g.t(160, 150, "承久の乱後は北条氏の支配が確立", 10),
         g.t(160, 174, "執権政治が行われる", 10, g.ACCENT),
         g.t(160, 198, "得宗(北条氏嫡流)がさらに実権", 9.5, g.SUB)]
    return g.titled("執権", b)


@register("守護大名")
def fig_守護大名():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "室町幕府の守護から成長", 10, g.ACCENT),
         g.t(160, 76, "(守護 → 守護大名)", 8.5, g.SUB),
         g.t(160, 104, "領国(分国)を支配する大名", 10.5),
         g.t(160, 126, "土地・人民を掌握して力を持つ", 10, g.ACCENT),
         g.t(160, 150, "守護請・半済などで支配を強化", 10),
         g.t(160, 174, "応仁の乱後は戦国大名へ", 10, g.ACCENT),
         g.t(160, 198, "例: 細川氏・大内氏・島津氏", 9.5, g.SUB)]
    return g.titled("守護大名", b)


@register("惣村")
def fig_惣村():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "村の自治組織", 10, g.ACCENT),
         g.t(160, 76, "(惣・寄合・掟)", 8.5, g.SUB),
         g.t(160, 104, "農民が団結して自治を行う", 10.5),
         g.t(160, 126, "用水の管理・年貢の割り当て", 10, g.ACCENT),
         g.t(160, 150, "惣掟(村のきまり)を定めた", 10),
         g.t(160, 174, "一揆の主体にもなった", 10, g.ACCENT),
         g.t(160, 198, "室町時代に全国各地で成立", 9.5, g.SUB)]
    return g.titled("惣村", b)


@register("分国法")
def fig_分国法():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "戦国大名の領国法", 10, g.ACCENT),
         g.t(160, 76, "(分国=領国)", 8.5, g.SUB),
         g.t(160, 104, "領国支配のきまりを定めた法律", 10.5),
         g.t(160, 126, "例: 今川仮名目録・大内家壁書", 10, g.ACCENT),
         g.t(160, 150, "所領の相続・喧嘩の禁止など", 10),
         g.t(160, 174, "大名の権力強化の手段", 10, g.ACCENT),
         g.t(160, 198, "戦国時代の法体系", 9.5, g.SUB)]
    return g.titled("分国法", b)


@register("兵農分離")
def fig_兵農分離():
    b = [g.t(160, 44, "武士と農民を分ける", 10.5, g.INK),
         g.rect(40, 56, 100, 40, g.INK, 1.3, g.FILL2),
         g.rect(180, 56, 100, 40, g.INK, 1.3, g.FILL),
         g.t(90, 74, "武士", 10, g.ACCENT), g.t(90, 90, "(城下町に住む)", 8.5, g.SUB),
         g.t(230, 74, "農民", 10, g.ACCENT), g.t(230, 90, "(村に住む)", 8.5, g.SUB),
         g.t(160, 114, "身分を明確に分けた政策", 10.5),
         g.t(160, 136, "刀狩りで農民の武装を禁止", 10, g.ACCENT),
         g.t(160, 160, "検地で土地の支配を確立", 10),
         g.t(160, 184, "豊臣秀吉の政策が代表", 10, g.ACCENT),
         g.t(160, 208, "近世の身分制度の基礎", 9.5, g.SUB)]
    return g.titled("兵農分離", b)


@register("幕藩体制")
def fig_幕藩体制():
    b = [g.rect(110, 40, 100, 36, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "幕府", 10.5, g.ACCENT),
         g.line(130, 82, 100, 100, g.INK, 1.2), g.line(190, 82, 220, 100, g.INK, 1.2),
         g.rect(40, 104, 100, 40, g.INK, 1.2, g.FILL),
         g.rect(180, 104, 100, 40, g.INK, 1.2, g.FILL),
         g.t(90, 122, "藩(大名)", 10), g.t(230, 122, "藩(大名)", 10),
         g.t(160, 160, "幕府と約250の藩が", 10.5),
         g.t(160, 182, "支配を分担した体制", 10.5, g.ACCENT),
         g.t(160, 206, "幕府は全国、藩は領地を支配", 9.5, g.SUB)]
    return g.titled("幕藩体制", b)


@register("版籍奉還")
def fig_版籍奉還():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.rect(180, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.t(90, 60, "版(土地)", 10, g.ACCENT), g.t(90, 76, "(版図)", 8.5, g.SUB),
         g.t(230, 60, "籍(人民)", 10, g.ACCENT), g.t(230, 76, "(戸籍)", 8.5, g.SUB),
         g.arrow(144, 64, 176, 64, g.ACCENT, 1.8),
         g.t(160, 104, "1869年、大名が土地と人民を", 10.5),
         g.t(160, 126, "天皇に返還した", 10.5, g.ACCENT),
         g.t(160, 150, "中央集権国家への第一歩", 10),
         g.t(160, 174, "藩知事に任命されて支配を続けた", 10, g.ACCENT),
         g.t(160, 198, "後の廃藩置県(1871年)へ", 9.5, g.SUB)]
    return g.titled("版籍奉還", b)


@register("秩禄処分")
def fig_秩禄処分():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "家禄(知行)を廃止", 10, g.ACCENT),
         g.t(160, 104, "1876年、士族への給与を打ち切り", 10.5),
         g.t(160, 126, "代わりに金禄公債証書を交付", 10, g.ACCENT),
         g.t(160, 150, "政府の財政負担を減らすため", 10),
         g.t(160, 174, "士族の不満 → 士族反乱の一因", 10, g.ACCENT),
         g.t(160, 198, "西南戦争(1877年)へつながる", 9.5, g.SUB)]
    return g.titled("秩禄処分", b)


@register("自由党")
def fig_自由党():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "1881年結成の政党", 10, g.ACCENT),
         g.t(160, 104, "板垣退助が中心", 10.5),
         g.t(160, 126, "自由民権運動の政党", 10, g.ACCENT),
         g.t(160, 150, "「自由と民権」を掲げた", 10),
         g.t(160, 174, "国会開設の要求を主導", 10, g.ACCENT),
         g.t(160, 198, "後の立憲政友会へつながる", 9.5, g.SUB)]
    return g.titled("自由党", b)


@register("立憲主義")
def fig_立憲主義():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "憲法で政治の権力を制限", 10, g.ACCENT),
         g.t(160, 104, "国民の権利を保障する考え方", 10.5),
         g.t(160, 126, "憲法が国家の最高法規", 10, g.ACCENT),
         g.t(160, 150, "権力の分立(三権分立)", 10),
         g.t(160, 174, "日本国憲法も立憲主義に立つ", 10, g.ACCENT),
         g.t(160, 198, "法の支配の考え方", 9.5, g.SUB)]
    return g.titled("立憲主義", b)


@register("違憲立法審査権")
def fig_違憲立法審査権():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.t(90, 60, "法律", 10), g.t(90, 76, "(国会が制定)", 8.5, g.SUB),
         g.t(230, 60, "憲法に合うか審査", 10, g.ACCENT),
         g.arrow(144, 64, 176, 64, g.ACCENT, 1.8),
         g.t(160, 104, "最高裁判所の権限", 10.5),
         g.t(160, 126, "違憲と判断すれば法律を無効に", 10, g.ACCENT),
         g.t(160, 150, "「憲法の番人」", 10),
         g.t(160, 174, "日本では違憲判決は少数", 10, g.ACCENT),
         g.t(160, 198, "付随的審査制をとる", 9.5, g.SUB)]
    return g.titled("違憲立法審査権", b)


@register("象徴天皇制")
def fig_象徴天皇制():
    b = [g.rect(90, 44, 140, 44, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "日本国の象徴", 11, g.ACCENT),
         g.t(160, 78, "(日本国民統合の象徴)", 8.5, g.SUB),
         g.t(160, 104, "国政に関する権能を持たない", 10.5),
         g.t(160, 126, "憲法第1条に定められる", 10, g.ACCENT),
         g.t(160, 150, "内閣の助言と承認による国事行為", 10),
         g.t(160, 174, "天皇の地位は主権者の意思による", 10, g.ACCENT),
         g.t(160, 198, "日本国憲法の基本原理", 9.5, g.SUB)]
    return g.titled("象徴天皇制", b)


@register("集団的自衛権")
def fig_集団的自衛権():
    b = [g.rect(50, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.rect(170, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.t(100, 60, "個別的", 10), g.t(100, 76, "(自国を守る)", 8.5, g.SUB),
         g.t(220, 60, "集団的", 10, g.ACCENT), g.t(220, 76, "(同盟国と共に)", 8.5, g.SUB),
         g.t(160, 104, "国連憲章で認められる権利", 10.5),
         g.t(160, 126, "日本は2014年から限定的に行使", 10, g.ACCENT),
         g.t(160, 150, "他国への武力攻撃を共同で防ぐ", 10),
         g.t(160, 174, "憲法9条との関係が論点", 10, g.ACCENT),
         g.t(160, 198, "安全保障政策の重要テーマ", 9.5, g.SUB)]
    return g.titled("集団的自衛権", b)


@register("公共の福祉")
def fig_公共の福祉():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "みんなの利益・社会全体の利益", 10, g.ACCENT),
         g.t(160, 104, "人権の行使を制限できる根拠", 10.5),
         g.t(160, 126, "憲法で「公共の福祉による」制約", 10, g.ACCENT),
         g.t(160, 150, "他人の権利と衝突する場合に調整", 10),
         g.t(160, 174, "例: 感染症対策・騒音規制", 10, g.ACCENT),
         g.t(160, 198, "人権尊重と社会全体の利益の調和", 9.5, g.SUB)]
    return g.titled("公共の福祉", b)


@register("環境権")
def fig_環境権():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "健康で快適な環境で暮らす権利", 9.5, g.ACCENT),
         g.t(160, 104, "きれいな空気・水・自然", 10.5),
         g.t(160, 126, "公害・環境破壊からの保護", 10, g.ACCENT),
         g.t(160, 150, "憲法に明文はないが判例で注目", 10),
         g.t(160, 174, "環境基本法・環境アセスメント", 10, g.ACCENT),
         g.t(160, 198, "公害問題から生まれた権利", 9.5, g.SUB)]
    return g.titled("環境権", b)


@register("情報公開制度")
def fig_情報公開制度():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.t(90, 60, "行政機関", 10), g.t(90, 76, "(情報を持つ)", 8.5, g.SUB),
         g.t(230, 60, "国民", 10, g.ACCENT), g.t(230, 76, "(開示請求)", 8.5, g.SUB),
         g.arrow(144, 64, 176, 64, g.ACCENT, 1.8),
         g.t(160, 104, "行政の情報を開示する制度", 10.5),
         g.t(160, 126, "行政の説明責任を果たす", 10, g.ACCENT),
         g.t(160, 150, "国民の知る権利を保障", 10),
         g.t(160, 174, "情報公開法(2001年施行)", 10, g.ACCENT),
         g.t(160, 198, "開かれた行政への手段", 9.5, g.SUB)]
    return g.titled("情報公開制度", b)


@register("景気循環")
def fig_景気循環():
    b = [g.line(50, 140, 270, 140, g.SUB, 1.2),
         g.line(50, 140, 50, 52, g.SUB, 1.2),
         g.t(34, 48, "景気", 9, g.SUB),
         g.path("M50,118 Q80,80 110,100 Q140,120 170,96 Q200,72 230,92 Q260,110 270,106", g.ACCENT, 2.2),
         g.t(82, 72, "好況", 9, g.ACCENT), g.t(188, 128, "後退", 9, g.ACCENT),
         g.t(250, 118, "回復", 9, g.ACCENT),
         g.t(160, 164, "好況・後退・不況・回復をくり返す", 10.5),
         g.t(160, 186, "経済活動の波(景気の山と谷)", 10, g.ACCENT),
         g.t(160, 210, "金融政策・財政政策で調整する", 9.5, g.SUB)]
    return g.titled("景気循環", b)


@register("寡占")
def fig_寡占():
    b = [g.rect(50, 44, 80, 44, g.INK, 1.3, g.FILL2),
         g.rect(140, 44, 80, 44, g.INK, 1.3, g.FILL2),
         g.rect(230, 44, 40, 44, g.INK, 1.3, g.FILL),
         g.t(90, 66, "A社", 10, g.ACCENT), g.t(180, 66, "B社", 10, g.ACCENT),
         g.t(250, 66, "…", 10),
         g.t(160, 104, "少数の大企業が市場を支配", 10.5),
         g.t(160, 126, "価格競争が起きにくい", 10, g.ACCENT),
         g.t(160, 150, "値下げより品質・広告で競争", 10),
         g.t(160, 174, "独占禁止法で規制される", 10, g.ACCENT),
         g.t(160, 198, "例: 自動車・電機・通信", 9.5, g.SUB)]
    return g.titled("寡占", b)


@register("ビルトインスタビライザー")
def fig_ビルトインスタビライザー():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "景気を自動的に安定させる仕組み", 9.5, g.ACCENT),
         g.t(160, 104, "不況時: 税収減・失業給付増", 10.5),
         g.t(160, 126, "好況時: 税収増が自動的に", 10, g.ACCENT),
         g.t(160, 150, "政府の裁量なしで働く", 10),
         g.t(160, 174, "例: 累進課税・失業保険", 10, g.ACCENT),
         g.t(160, 198, "財政の自動安定化装置", 9.5, g.SUB)]
    return g.titled("ビルトインスタビライザー", b)


@register("預金準備率操作")
def fig_預金準備率操作():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.rect(180, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.t(90, 60, "日銀", 10, g.ACCENT), g.t(90, 76, "(預金準備率)", 8.5, g.SUB),
         g.t(230, 60, "民間銀行", 10), g.t(230, 76, "(貸出し)", 8.5, g.SUB),
         g.arrow(144, 64, 176, 64, g.ACCENT, 1.8),
         g.t(160, 104, "準備率を上げる → 貸出し抑制", 10.5),
         g.t(160, 126, "準備率を下げる → 貸出し拡大", 10, g.ACCENT),
         g.t(160, 150, "世の中のお金の量を調整", 10),
         g.t(160, 174, "金融政策の手段の一つ", 10, g.ACCENT),
         g.t(160, 198, "公開市場操作・公定歩合と並ぶ", 9.5, g.SUB)]
    return g.titled("預金準備率操作", b)


@register("労働三権")
def fig_労働三権():
    b = []
    for i, (name, note) in enumerate([("団結権", "組合をつくる"),
                                      ("団体交渉権", "交渉できる"),
                                      ("団体行動権", "ストライキ")]):
        x = 28 + i * 96
        b += _chem_box(x, 46, 80, 40, name, size=11, fill=g.FILL2, color=g.ACCENT)
        b.append(g.t(x + 40, 100, note, 9.5, g.INK))
    b += [g.t(160, 132, "労働者が使用者と対等になる権利", 10.5),
          g.t(160, 154, "憲法第28条で保障", 10, g.ACCENT),
          g.t(160, 178, "労働組合の活動の基礎", 10),
          g.t(160, 202, "労働基本権の一つ", 9.5, g.SUB)]
    return g.titled("労働三権", b)


@register("ノーマライゼーション")
def fig_ノーマライゼーション():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "障害があっても普通の生活を", 9.5, g.ACCENT),
         g.t(160, 104, "障害者も地域で共に暮らす", 10.5),
         g.t(160, 126, "特別扱いではなく当たり前に", 10, g.ACCENT),
         g.t(160, 150, "バリアフリー・合理的配慮", 10),
         g.t(160, 174, "共生社会の考え方の土台", 10, g.ACCENT),
         g.t(160, 198, "福祉・教育・雇用に広がる", 9.5, g.SUB)]
    return g.titled("ノーマライゼーション", b)


@register("功利主義")
def fig_功利主義():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "「最大多数の最大幸福」", 10, g.ACCENT),
         g.t(160, 104, "幸福を最大にすることが正義", 10.5),
         g.t(160, 126, "ベンサム・J.S.ミルが提唱", 10, g.ACCENT),
         g.t(160, 150, "結果(効用)で行為を判断", 10),
         g.t(160, 174, "現代の政策判断にも影響", 10, g.ACCENT),
         g.t(160, 198, "義務論(カント)と対比される", 9.5, g.SUB)]
    return g.titled("功利主義", b)


@register("定言命法")
def fig_定言命法():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "カントの道徳の法則", 10, g.ACCENT),
         g.t(160, 104, "条件なしに「せよ」と命じる", 10.5),
         g.t(160, 126, "「君がしてほしいことを他者にも」", 10, g.ACCENT),
         g.t(160, 150, "目的を手段として扱わない", 10),
         g.t(160, 174, "義務に基づく行為", 10, g.ACCENT),
         g.t(160, 198, "功利主義と対比される", 9.5, g.SUB)]
    return g.titled("定言命法", b)


@register("四大公害病")
def fig_四大公害病():
    b = []
    for i, (name, place) in enumerate([("水俣病", "熊本・新潟"),
                                       ("イタイイタイ病", "富山"),
                                       ("四日市ぜんそく", "三重"),
                                       ("新潟水俣病", "新潟")]):
        x = 30 + (i % 2) * 140
        y = 44 + (i // 2) * 52
        b += _chem_box(x, y, 124, 36, name, size=11, fill=g.FILL2, color=g.ACCENT)
        b.append(g.t(x + 62, y + 46, place, 9, g.SUB))
    b += [g.t(160, 156, "高度経済成長期の公害", 10.5),
          g.t(160, 178, "健康被害と環境汚染の教訓", 10, g.ACCENT),
          g.t(160, 202, "公害対策基本法のきっかけ", 9.5, g.SUB)]
    return g.titled("四大公害病", b)


@register("所得倍増計画")
def fig_所得倍増計画():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 62, "1960年 池田内閣の経済計画", 9.5, g.ACCENT),
         g.t(160, 104, "10年で国民所得を2倍に", 10.5, g.ACCENT),
         g.t(160, 126, "高度経済成長の目標になった", 10),
         g.t(160, 150, "所得倍増を掲げて経済発展", 10, g.ACCENT),
         g.t(160, 174, "実際には約10年で達成", 10),
         g.t(160, 198, "公害・格差などの課題も生んだ", 9.5, g.SUB)]
    return g.titled("所得倍増計画", b)


@register("ホイットルセーの農業区分")
def fig_ホイットルセーの農業区分():
    b = [g.rect(40, 44, 100, 44, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 44, g.INK, 1.3, g.FILL2),
         g.t(90, 62, "自給的農業", 10), g.t(90, 78, "(焼畑・移動式)", 8.5, g.SUB),
         g.t(230, 62, "商業的農業", 10, g.ACCENT),
         g.t(230, 78, "(プランテーション等)", 8.5, g.SUB),
         g.t(160, 104, "気候と結びついた農業区分", 10.5),
         g.t(160, 126, "熱帯・温帯で農業の型が違う", 10, g.ACCENT),
         g.t(160, 150, "例: 焼畑農業・稲作・牧畜", 10),
         g.t(160, 174, "地理の農業分類の一つ", 10, g.ACCENT),
         g.t(160, 198, "自給→商業への変化も見る", 9.5, g.SUB)]
    return g.titled("ホイットルセーの農業区分", b)


@register("ウェーバーの工業立地論")
def fig_ウェーバーの工業立地論():
    b = [g.rect(40, 44, 100, 44, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 44, g.INK, 1.3, g.FILL2),
         g.t(90, 62, "原料地", 10), g.t(90, 78, "(原料の重さ)", 8.5, g.SUB),
         g.t(230, 62, "市場", 10, g.ACCENT), g.t(230, 78, "(消費地)", 8.5, g.SUB),
         g.dot(160, 66, 3.0, g.ACCENT),
         g.line(140, 66, 118, 66, g.SUB, 1.0, dash="3 3"),
         g.line(180, 66, 202, 66, g.SUB, 1.0, dash="3 3"),
         g.t(160, 84, "工場", 9.5, g.ACCENT),
         g.t(160, 110, "輸送費を最小にする立地を考える", 10.5),
         g.t(160, 132, "原料と製品の重さで立地が決まる", 10, g.ACCENT),
         g.t(160, 156, "原料指向・市場指向の考え方", 10),
         g.t(160, 180, "工業立地論の古典", 10, g.ACCENT),
         g.t(160, 204, "→ 原料指向型・市場指向型工業", 9.5, g.SUB)]
    return g.titled("ウェーバーの工業立地論", b)


@register("原料指向型工業")
def fig_原料指向型工業():
    b = [g.rect(40, 44, 100, 44, g.INK, 1.3, g.FILL2),
         g.rect(180, 44, 100, 44, g.INK, 1.3, g.FILL),
         g.t(90, 62, "原料産地", 10, g.ACCENT), g.t(90, 78, "(鉱山・港)", 8.5, g.SUB),
         g.t(230, 62, "工場", 10, g.ACCENT), g.t(230, 78, "(原料の近く)", 8.5, g.SUB),
         g.arrow(144, 66, 176, 66, g.ACCENT, 1.8),
         g.t(160, 104, "原料の輸送費を節約する立地", 10.5),
         g.t(160, 126, "原料の減量・重量が大きい工業", 10, g.ACCENT),
         g.t(160, 150, "例: 鉄鋼・セメント・製糖", 10),
         g.t(160, 174, "臨海部に立地することが多い", 10, g.ACCENT),
         g.t(160, 198, "市場指向型工業と対になる", 9.5, g.SUB)]
    return g.titled("原料指向型工業", b)


@register("市場指向型工業")
def fig_市場指向型工業():
    b = [g.rect(40, 44, 100, 44, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 44, g.INK, 1.3, g.FILL2),
         g.t(90, 62, "工場", 10), g.t(90, 78, "(都市の近く)", 8.5, g.SUB),
         g.t(230, 62, "市場(消費地)", 10, g.ACCENT),
         g.arrow(144, 66, 176, 66, g.ACCENT, 1.8),
         g.t(160, 104, "消費地の近くに立地する工業", 10.5),
         g.t(160, 126, "製品が重い・傷みやすい工業", 10, g.ACCENT),
         g.t(160, 150, "例: パン・飲料・家具", 10),
         g.t(160, 174, "大都市圏に集まる", 10, g.ACCENT),
         g.t(160, 198, "原料指向型工業と対になる", 9.5, g.SUB)]
    return g.titled("市場指向型工業", b)


@register("外来河川")
def fig_外来河川():
    b = [g.path("M40,150 Q90,70 160,110 Q210,140 280,80", g.ACCENT, 2.6),
         g.t(90, 88, "本流(外来)", 9.5, g.ACCENT),
         g.path("M90,70 Q100,50 110,42", g.INK, 1.4),
         g.path("M150,108 Q160,130 170,138", g.INK, 1.4),
         g.t(118, 44, "支流", 9, g.SUB), g.t(178, 144, "支流", 9, g.SUB),
         g.t(160, 166, "本流と支流の関係", 10.5),
         g.t(160, 188, "支流が合流して本流になる", 10, g.ACCENT),
         g.t(160, 212, "地形と水の流れの理解に重要", 9.5, g.SUB)]
    return g.titled("外来河川", b)


@register("古期造山帯")
def fig_古期造山帯():
    b = [g.path("M50,100 Q160,60 270,100", g.ACCENT, 2.4),
         g.t(160, 84, "古い山地(古期造山帯)", 9.5, g.ACCENT),
         g.path("M50,140 Q160,120 270,140", g.INK, 1.6),
         g.t(160, 152, "新しい山地(新期造山帯)", 9.5),
         g.t(160, 172, "古い山地は侵食が進みなだらか", 10.5),
         g.t(160, 194, "例: アパラチア・ウラル・中国山地", 10, g.ACCENT),
         g.t(160, 218, "新期造山帯(ヒマラヤ等)は高く険しい", 9.5, g.SUB)]
    return g.titled("古期造山帯", b)


# ---- 社会(残り: 類似語に既に画像があるもの) ---------------------------------


@register("関白")
def fig_関白():
    b = [g.t(160, 42, "摂政・関白", 11.5, g.INK),
         g.rect(60, 56, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 78, "天皇に代わって政治を行う役職", 10, g.ACCENT),
         g.t(160, 112, "藤原氏が独占した", 10.5),
         g.t(160, 134, "摂政: 幼少の天皇 / 関白: 成人の天皇", 10, g.ACCENT),
         g.t(160, 158, "摂関政治の中心", 10),
         g.t(160, 182, "例: 藤原道長・藤原頼通", 10, g.ACCENT),
         g.t(160, 206, "平安時代の政治を担った", 9.5, g.SUB)]
    return g.titled("関白", b)


@register("郡司")
def fig_郡司():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "郡(こおり)の長官", 10, g.ACCENT),
         g.t(160, 78, "(律令制の地方官)", 8.5, g.SUB),
         g.t(160, 104, "国司の下で郡を治めた", 10.5),
         g.t(160, 126, "戸籍の管理・税の取り立て", 10, g.ACCENT),
         g.t(160, 150, "現地の有力豪族が任命された", 10),
         g.t(160, 174, "国司(中央から派遣)と対になる", 10, g.ACCENT),
         g.t(160, 198, "平安後期には形骸化した", 9.5, g.SUB)]
    return g.titled("郡司", b)


@register("防人")
def fig_防人():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "九州の沿岸を守る兵士", 10, g.ACCENT),
         g.t(160, 78, "(奈良時代の防衛制度)", 8.5, g.SUB),
         g.t(160, 104, "東国から派遣された農民", 10.5),
         g.t(160, 126, "防人の歌(万葉集)が残る", 10, g.ACCENT),
         g.t(160, 150, "大陸からの侵攻に備えた", 10),
         g.t(160, 174, "「さきもり」とも読む", 10, g.ACCENT),
         g.t(160, 198, "律令国家の軍事制度", 9.5, g.SUB)]
    return g.titled("防人", b)


@register("知行国")
def fig_知行国():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.t(90, 60, "国司の任命権", 10), g.t(90, 76, "(朝廷)", 8.5, g.SUB),
         g.t(230, 60, "知行国主", 10, g.ACCENT), g.t(230, 76, "(貴族・寺社)", 8.5, g.SUB),
         g.arrow(144, 64, 176, 64, g.ACCENT, 1.8),
         g.t(160, 104, "国の収入を自分のものにする", 10.5),
         g.t(160, 126, "知行国主が国司を推薦", 10, g.ACCENT),
         g.t(160, 150, "荘園とともに支配の基盤に", 10),
         g.t(160, 174, "院政期に広がった制度", 10, g.ACCENT),
         g.t(160, 198, "国司の任命と税収を独占", 9.5, g.SUB)]
    return g.titled("知行国", b)


@register("永仁の徳政令")
def fig_永仁の徳政令():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "1297年 鎌倉幕府の法令", 10, g.ACCENT),
         g.t(160, 104, "御家人の土地の売買を禁止", 10.5),
         g.t(160, 126, "売った土地を無償で取り戻せる", 10, g.ACCENT),
         g.t(160, 150, "借金の返済義務を免除", 10),
         g.t(160, 174, "御家人を救済するための法令", 10, g.ACCENT),
         g.t(160, 198, "しかし効果は限定的だった", 9.5, g.SUB)]
    return g.titled("永仁の徳政令", b)


@register("上げ米の制")
def fig_上げ米の制():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "享保の改革(徳川吉宗)", 10, g.ACCENT),
         g.t(160, 104, "大名に1万石につき100石を", 10.5),
         g.t(160, 126, "江戸へ納めさせる制度", 10.5, g.ACCENT),
         g.t(160, 150, "幕府の収入を増やすため", 10),
         g.t(160, 174, "参勤交代の費用を肩代わり", 10, g.ACCENT),
         g.t(160, 198, "大名の負担増となった", 9.5, g.SUB)]
    return g.titled("上げ米の制", b)


@register("公事方御定書")
def fig_公事方御定書():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "1742年 江戸幕府の法典", 10, g.ACCENT),
         g.t(160, 104, "裁判の基準を示した法律", 10.5),
         g.t(160, 126, "罪の重さによる刑罰を定めた", 10, g.ACCENT),
         g.t(160, 150, "享保の改革の一環", 10),
         g.t(160, 174, "「御定書」は秘密とされた", 10, g.ACCENT),
         g.t(160, 198, "江戸時代の基本法典", 9.5, g.SUB)]
    return g.titled("公事方御定書", b)


@register("棄捐令")
def fig_棄捐令():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "1789年 寛政の改革", 10, g.ACCENT),
         g.t(160, 104, "旗本・御家人の借金を", 10.5),
         g.t(160, 126, "帳消しにする法令", 10.5, g.ACCENT),
         g.t(160, 150, "武士を救済するため", 10),
         g.t(160, 174, "札差(金融業者)の打撃に", 10, g.ACCENT),
         g.t(160, 198, "松平定信の政策", 9.5, g.SUB)]
    return g.titled("棄捐令", b)


@register("囲米")
def fig_囲米():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "凶作に備えて米を蓄える", 10, g.ACCENT),
         g.t(160, 104, "大名・町人に米を備蓄させた", 10.5),
         g.t(160, 126, "天明の飢饉の後、寛政の改革で", 10, g.ACCENT),
         g.t(160, 150, "飢饉に備える政策", 10),
         g.t(160, 174, "「囲い米」「囲米」の制度", 10, g.ACCENT),
         g.t(160, 198, "農民救済の備蓄", 9.5, g.SUB)]
    return g.titled("囲米", b)


@register("人返しの法")
def fig_人返しの法():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "江戸の人口を減らす政策", 10, g.ACCENT),
         g.t(160, 104, "農村から江戸へ出た者を", 10.5),
         g.t(160, 126, "出身地へ戻す法令", 10.5, g.ACCENT),
         g.t(160, 150, "農業の担い手を確保するため", 10),
         g.t(160, 174, "化政文化の頃の政策", 10, g.ACCENT),
         g.t(160, 198, "田沼意次の時代の後", 9.5, g.SUB)]
    return g.titled("人返しの法", b)


@register("上知令")
def fig_上知令():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "幕府領を増やす政策", 10, g.ACCENT),
         g.t(160, 104, "大名・旗本の領地を", 10.5),
         g.t(160, 126, "幕府に返させる法令", 10.5, g.ACCENT),
         g.t(160, 150, "天保の改革(水野忠邦)", 10),
         g.t(160, 174, "大名の反発で失敗", 10, g.ACCENT),
         g.t(160, 198, "「上知(あげち)」の強行", 9.5, g.SUB)]
    return g.titled("上知令", b)


@register("異国船打払令")
def fig_異国船打払令():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "1825年 外国船を打ち払う", 10, g.ACCENT),
         g.t(160, 104, "沿岸に来た外国船を", 10.5),
         g.t(160, 126, "砲撃して追い払う法令", 10.5, g.ACCENT),
         g.t(160, 150, "鎖国を守るための政策", 10),
         g.t(160, 174, "モリソン号事件の原因に", 10, g.ACCENT),
         g.t(160, 198, "後に薪水給与令へ緩和(1842年)", 9.5, g.SUB)]
    return g.titled("異国船打払令", b)


@register("大逆事件")
def fig_大逆事件():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "1910年 幸徳事件", 10, g.ACCENT),
         g.t(160, 104, "天皇暗殺の計画があるとして", 10.5),
         g.t(160, 126, "社会主義者を逮捕・処刑", 10.5, g.ACCENT),
         g.t(160, 150, "幸徳秋水ら12人が処刑", 10),
         g.t(160, 174, "社会運動への弾圧を強めた", 10, g.ACCENT),
         g.t(160, 198, "「国家と社会主義」の対立", 9.5, g.SUB)]
    return g.titled("大逆事件", b)


@register("特需景気")
def fig_特需景気():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "朝鮮戦争による好景気", 10, g.ACCENT),
         g.t(160, 104, "1950年 朝鮮戦争の特需", 10.5),
         g.t(160, 126, "軍需品の生産で経済が活性化", 10, g.ACCENT),
         g.t(160, 150, "「特需」= 特別な需要", 10),
         g.t(160, 174, "戦後日本の復興を後押し", 10, g.ACCENT),
         g.t(160, 198, "高度経済成長の入口", 9.5, g.SUB)]
    return g.titled("特需景気", b)


@register("ロック")
def fig_ロック():
    b = [g.path("M70,60 L130,60 L150,100 L150,150 L90,150 L70,100 Z", g.INK, 1.8, g.FILL),
         g.path("M150,60 L190,52 L210,100 L210,150 L150,150 Z", g.INK, 1.6, g.FILL2),
         g.path("M190,52 L230,70 L210,100", g.INK, 1.4),
         g.line(150, 60, 150, 150, g.SUB, 1.0, dash="3 3"),
         g.t(160, 170, "岩石(がんせき)", 10.5),
         g.t(160, 192, "マグマ・堆積物・変成でできる", 10, g.ACCENT),
         g.t(160, 216, "火成岩・堆積岩・変成岩の3種", 9.5, g.SUB)]
    return g.titled("ロック", b)


@register("ルソー")
def fig_ルソー():
    b = [g.rect(70, 44, 180, 52, g.INK, 1.4, g.FILL),
         g.t(160, 62, "『社会契約論』", 11, g.ACCENT),
         g.t(160, 80, "(1762年)", 9, g.SUB),
         g.t(160, 112, "人民主権を唱えた", 10.5),
         g.t(160, 134, "「一般意志」による政治", 10, g.ACCENT),
         g.t(160, 158, "フランス革命に影響", 10),
         g.t(160, 182, "18世紀フランスの思想家", 10, g.ACCENT),
         g.t(160, 206, "啓蒙思想の一人", 9.5, g.SUB)]
    return g.titled("ルソー", b)


@register("基本的人権")
def fig_基本的人権():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "生まれながらに持つ権利", 10, g.ACCENT),
         g.t(160, 104, "自由権・平等権・社会権など", 10.5),
         g.t(160, 126, "国家も侵すことができない", 10, g.ACCENT),
         g.t(160, 150, "憲法第11条「侵すことのできない」", 10),
         g.t(160, 174, "日本国憲法の基本原理", 10, g.ACCENT),
         g.t(160, 198, "国民主権・平和主義と並ぶ", 9.5, g.SUB)]
    return g.titled("基本的人権", b)


@register("五人組")
def fig_五人組():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.rect(110, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.t(90, 62, "農民", 10), g.t(160, 62, "農民", 10), g.t(230, 62, "農民…", 10, g.ACCENT),
         g.line(144, 60, 106, 60, g.SUB, 1.2), g.line(214, 60, 184, 60, g.SUB, 1.2),
         g.t(160, 104, "村の5戸前後を組にした制度", 10.5),
         g.t(160, 126, "年貢の連帯責任・犯罪の監視", 10, g.ACCENT),
         g.t(160, 150, "江戸幕府の農民統制", 10),
         g.t(160, 174, "五人組帳(連判状)も作られた", 10, g.ACCENT),
         g.t(160, 198, "村社会の相互監視の仕組み", 9.5, g.SUB)]
    return g.titled("五人組", b)


@register("慶安の御触書")
def fig_慶安の御触書():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "1649年 農民統制の法令", 10, g.ACCENT),
         g.t(160, 104, "農民の生活を細かく規制", 10.5),
         g.t(160, 126, "倹約・勤勉・本業への専念", 10, g.ACCENT),
         g.t(160, 150, "贅沢の禁止・怠けの戒め", 10),
         g.t(160, 174, "幕府の農政の基本", 10, g.ACCENT),
         g.t(160, 198, "実際は各地の御触書の集成", 9.5, g.SUB)]
    return g.titled("慶安の御触書", b)


@register("株仲間")
def fig_株仲間():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.t(90, 62, "商人の組合", 10), g.t(230, 62, "営業の独占", 10, g.ACCENT),
         g.arrow(144, 64, 176, 64, g.ACCENT, 1.8),
         g.t(160, 104, "株(営業権)を持つ商人の組合", 10.5),
         g.t(160, 126, "幕府に株仲間の結成を認めさせる", 10, g.ACCENT),
         g.t(160, 150, "営業を独占して利益を得る", 10),
         g.t(160, 174, "江戸時代の商業統制", 10, g.ACCENT),
         g.t(160, 198, "天保の改革では一時解散させられた", 9.5, g.SUB)]
    return g.titled("株仲間", b)


@register("領事裁判権")
def fig_領事裁判権():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.t(90, 62, "外国人", 10), g.t(90, 78, "(領事が裁判)", 8.5, g.SUB),
         g.t(230, 62, "日本の裁判権", 10, g.ACCENT), g.t(230, 78, "(及ばない)", 8.5, g.SUB),
         g.arrow(144, 64, 176, 64, g.ACCENT, 1.8),
         g.t(160, 104, "外国人が自国の領事の裁判を受ける", 10.5),
         g.t(160, 126, "治外法権の一つ", 10, g.ACCENT),
         g.t(160, 150, "幕末の不平等条約で認めた", 10),
         g.t(160, 174, "条約改正で撤廃(1899年)", 10, g.ACCENT),
         g.t(160, 198, "日本も欧米で同様の権利を得た", 9.5, g.SUB)]
    return g.titled("領事裁判権", b)


@register("農地改革")
def fig_農地改革():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.t(90, 62, "地主", 10), g.t(90, 78, "(小作料で収入)", 8.5, g.SUB),
         g.t(230, 62, "小作人", 10, g.ACCENT), g.t(230, 78, "(農地を買い取る)", 8.5, g.SUB),
         g.arrow(144, 64, 176, 64, g.ACCENT, 1.8),
         g.t(160, 104, "戦後(1946年)の農地改革", 10.5),
         g.t(160, 126, "地主の農地を政府が買い上げ", 10, g.ACCENT),
         g.t(160, 150, "小作人に安く売り渡した", 10),
         g.t(160, 174, "自作農を増やし農業を安定化", 10, g.ACCENT),
         g.t(160, 198, "占領政策の一つ", 9.5, g.SUB)]
    return g.titled("農地改革", b)


@register("北洋漁業")
def fig_北洋漁業():
    b = [g.path("M40,60 Q160,90 280,60", g.ACCENT, 1.6, dash="4 4"),
         g.t(160, 52, "北の海(北洋)", 9.5, g.ACCENT),
         g.path("M60,110 Q160,80 260,110", g.INK, 1.4, g.FILL),
         g.t(160, 130, "船団で操業する漁業", 10.5),
         g.t(160, 152, "サケ・マス・カニなど", 10, g.ACCENT),
         g.t(160, 176, "北海道・東北の水産業の中心", 10),
         g.t(160, 200, "200海里問題の影響を受けた", 9.5, g.SUB)]
    return g.titled("北洋漁業", b)


@register("フロンガス")
def fig_フロンガス():
    b = [g.rect(50, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.rect(170, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.t(100, 62, "冷蔵庫・エアコン", 10, g.ACCENT),
         g.t(230, 62, "オゾン層を破壊", 10, g.ACCENT),
         g.arrow(154, 64, 166, 64, g.ACCENT, 1.8),
         g.t(160, 104, "かつて冷媒などに使われたガス", 10.5),
         g.t(160, 126, "オゾン層破壊の原因とされた", 10, g.ACCENT),
         g.t(160, 150, "モントリオール議定書で規制", 10),
         g.t(160, 174, "代替フロンへの転換が進んだ", 10, g.ACCENT),
         g.t(160, 198, "代替フロンは温室効果が課題", 9.5, g.SUB)]
    return g.titled("フロンガス", b)


@register("惣")
def fig_惣():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "惣村の団結・自治組織", 10, g.ACCENT),
         g.t(160, 104, "農民が「惣」として結束", 10.5),
         g.t(160, 126, "寄合で村のきまり(惣掟)を決める", 10, g.ACCENT),
         g.t(160, 150, "用水の管理・年貢の分担", 10),
         g.t(160, 174, "一揆の主体にもなった", 10, g.ACCENT),
         g.t(160, 198, "惣村の自治の仕組み", 9.5, g.SUB)]
    return g.titled("惣", b)


# ---- 英語(文法の構造図: 類似語に既に図があるもの) ----------------------------


@register("分詞構文")
def fig_分詞構文():
    b = [g.t(160, 44, "Because I was tired, I slept.", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.arrow(160, 56, 160, 74, g.INK, 1.4),
         g.t(160, 90, "Being tired, I slept.", 10.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 116, "接続詞+主語+動詞 → 分詞で始める", 10.5),
         g.t(160, 140, "理由・時・条件などを表す", 10, g.ACCENT),
         g.t(160, 164, "意味上の主語が文の主語と一致", 10),
         g.t(160, 188, "例: Walking home, I met him.", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 212, "英語の重要構文", 9.5, g.SUB)]
    return g.titled("分詞構文", b)


@register("独立分詞構文")
def fig_独立分詞構文():
    b = [g.t(160, 44, "Weather permitting, we will go.", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 110, 36, g.INK, 1.2, g.FILL2),
         g.rect(170, 56, 110, 36, g.INK, 1.2, g.FILL),
         g.t(95, 78, "Weather(意味上の主語)", 9, g.ACCENT),
         g.t(225, 78, "permitting(分詞)", 9, g.ACCENT),
         g.t(160, 108, "文の主語と異なる主語を持つ分詞構文", 10.5),
         g.t(160, 132, "「天気がよければ」", 10, g.ACCENT),
         g.t(160, 156, "主語を省略しない分詞構文", 10),
         g.t(160, 180, "例: The sun having set, it got dark.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 204, "書き言葉で使われる", 9.5, g.SUB)]
    return g.titled("独立分詞構文", b)


@register("懸垂分詞")
def fig_懸垂分詞():
    b = [g.t(160, 44, "Looking up, the sky was blue.", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「空が空を見上げた」= 意味がおかしい", 9.5, g.ACCENT),
         g.t(160, 96, "分詞の主語が文の主語と一致しない", 10.5),
         g.t(160, 120, "誤りとされる分詞構文の用法", 10, g.ACCENT),
         g.t(160, 144, "正しくは Looking up, I saw the sky.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "dangling participle", 10, g.ACCENT),
         g.t(160, 192, "文法的にぶら下がった分詞", 9.5, g.SUB)]
    return g.titled("懸垂分詞", b)


@register("完了形分詞構文")
def fig_完了形分詞構文():
    b = [g.t(160, 44, "Having finished work, I went home.", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「仕事を終えてから家へ帰った」", 9.5, g.ACCENT),
         g.t(160, 96, "Having + 過去分詞 の形", 10.5),
         g.t(160, 120, "主節より先の動作を表す", 10, g.ACCENT),
         g.t(160, 144, "例: Having seen the movie, I slept.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "完了・経験の分詞構文", 10, g.ACCENT),
         g.t(160, 192, "時間の前後関係を明示する", 9.5, g.SUB)]
    return g.titled("完了形分詞構文", b)


@register("付帯状況")
def fig_付帯状況():
    b = [g.t(160, 44, "He sat with his eyes closed.", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「目を閉じたまま座っていた」", 9.5, g.ACCENT),
         g.t(160, 96, "with + 目的語 + 分詞/前置詞句", 10.5),
         g.t(160, 120, "同時に起きる状況を添える", 10, g.ACCENT),
         g.t(160, 144, "例: with a bag in his hand", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "「〜したまま」「〜を持って」", 10, g.ACCENT),
         g.t(160, 192, "分詞構文に似た付帯表現", 9.5, g.SUB)]
    return g.titled("付帯状況", b)


def _katei(word, cond, main, note):
    b = [g.rect(40, 44, 100, 44, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 44, g.INK, 1.3, g.FILL2),
         g.t(90, 62, "条件節", 10), g.t(90, 78, "(if節)", 8.5, g.SUB),
         g.t(230, 62, "帰結節", 10, g.ACCENT), g.t(230, 78, "(主節)", 8.5, g.SUB),
         g.arrow(144, 66, 176, 66, g.ACCENT, 1.8)]
    b += [g.t(160, 106, cond, 10, g.ACCENT, "middle", g.MATHFONT, "700"),
          g.t(160, 128, main, 9.5, g.INK, "middle", g.MATHFONT, "700"),
          g.t(160, 152, note, 10.5, g.ACCENT)]
    return g.titled(word, b)


@register("仮定法過去完了")
def fig_仮定法過去完了():
    return _katei("仮定法過去完了", "If I had known,", "I would have helped.",
                  "「知っていたら手伝ったのに」(過去の事実と反対)")


@register("仮定法未来")
def fig_仮定法未来():
    return _katei("仮定法未来", "If it should rain,", "the game will be off.",
                  "「万一雨が降れば」(可能性が低い未来)")


@register("仮定法現在")
def fig_仮定法現在():
    return _katei("仮定法現在", "If that be true,", "I am sorry.",
                  "「万一それが本当なら」(文語的・公式)")


@register("混合仮定法")
def fig_混合仮定法():
    return _katei("混合仮定法", "If I had studied,", "I would be happy now.",
                  "「勉強していたら今幸せなのに」(過去条件+現在帰結)")


@register("仮定法の倒置")
def fig_仮定法の倒置():
    b = [g.t(160, 44, "If I were you, → Were I you,", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "if を省略して倒置する形", 10.5, g.ACCENT),
         g.t(160, 96, "Had I known, = If I had known", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 120, "Should it rain, = If it should rain", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 144, "助動詞を文頭に置く", 10),
         g.t(160, 168, "形式ばった書き言葉", 10, g.ACCENT),
         g.t(160, 192, "if節の省略による強調", 9.5, g.SUB)]
    return g.titled("仮定法の倒置", b)


@register("帰結節")
def fig_帰結節():
    return _katei("帰結節", "If it rains,", "I will stay home.",
                  "条件節(if節)に対する主節の部分")


@register("条件節")
def fig_条件節():
    return _katei("条件節", "If it rains,", "I will stay home.",
                  "「もし〜なら」の条件を表す節(if節)")


@register("完了不定詞")
def fig_完了不定詞():
    b = [g.t(160, 44, "to have + 過去分詞", 10.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "例: He seems to have been ill.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 96, "主節より前の動作を表す", 10.5),
         g.t(160, 120, "「〜したように思われる」", 10, g.ACCENT),
         g.t(160, 144, "例: I am glad to have met you.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "完了の意味を持つ不定詞", 10, g.ACCENT),
         g.t(160, 192, "seem・happen などとよく使う", 9.5, g.SUB)]
    return g.titled("完了不定詞", b)


@register("原形不定詞")
def fig_原形不定詞():
    b = [g.t(160, 44, "make + 人 + 動詞の原形", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "例: make him go", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 96, "to の付かない不定詞", 10.5),
         g.t(160, 120, "使役動詞・知覚動詞の後", 10, g.ACCENT),
         g.t(160, 144, "例: I saw him run.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "「人に〜させる」「〜するのを見る」", 10, g.ACCENT),
         g.t(160, 192, "受身では to が付く", 9.5, g.SUB)]
    return g.titled("原形不定詞", b)


@register("独立不定詞")
def fig_独立不定詞():
    b = [g.t(160, 44, "To tell the truth, I don't know.", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「実を言うと、知らない」", 9.5, g.ACCENT),
         g.t(160, 96, "文全体に注釈を添える不定詞", 10.5),
         g.t(160, 120, "主語は文の主語とは無関係", 10, g.ACCENT),
         g.t(160, 144, "例: to be frank / to be sure", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "「〜と言えば」「〜してみると」", 10, g.ACCENT),
         g.t(160, 192, "文頭に置いて使う", 9.5, g.SUB)]
    return g.titled("独立不定詞", b)


@register("代不定詞")
def fig_代不定詞():
    b = [g.t(160, 44, "Do you want to go? — I'd love to.", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「行きたい？— 行きたいです」", 9.5, g.ACCENT),
         g.t(160, 96, "不定詞のくり返しを避ける", 10.5),
         g.t(160, 120, "to だけ残して動詞を省く", 10, g.ACCENT),
         g.t(160, 144, "例: I want to (go).", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "代用不定詞(pro-form)", 10, g.ACCENT),
         g.t(160, 192, "会話でよく使われる", 9.5, g.SUB)]
    return g.titled("代不定詞", b)


@register("意味上の主語")
def fig_意味上の主語():
    b = [g.t(160, 44, "I want him to come.", 10.5, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 70, 36, g.INK, 1.2, g.FILL),
         g.rect(210, 56, 70, 36, g.INK, 1.2, g.FILL2),
         g.t(75, 78, "him", 10, g.ACCENT), g.t(245, 78, "to come", 9.5, g.ACCENT),
         g.t(160, 108, "不定詞の動作をする人(意味上の主語)", 10.5),
         g.t(160, 132, "for + 人 で表すこともある", 10, g.ACCENT),
         g.t(160, 156, "例: It is important for you to study.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 180, "文の主語と一致しない場合", 10),
         g.t(160, 204, "to の前に置く", 9.5, g.SUB)]
    return g.titled("意味上の主語", b)


@register("名詞的用法")
def fig_名詞的用法():
    b = [g.t(160, 44, "To study is important.", 10.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「勉強することは大切だ」", 9.5, g.ACCENT),
         g.t(160, 96, "不定詞が名詞の働き(主語・目的語)", 10.5),
         g.t(160, 120, "to + 動詞の原形", 10, g.ACCENT),
         g.t(160, 144, "例: I want to study.", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "「〜すること」", 10, g.ACCENT),
         g.t(160, 192, "形容詞的用法・副詞的用法と並ぶ", 9.5, g.SUB)]
    return g.titled("名詞的用法", b)


@register("形容詞的用法")
def fig_形容詞的用法():
    b = [g.t(160, 44, "I have a book to read.", 10.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「読む本を持っている」", 9.5, g.ACCENT),
         g.t(160, 96, "名詞を修飾する不定詞", 10.5),
         g.t(160, 120, "「〜するための」「〜すべき」", 10, g.ACCENT),
         g.t(160, 144, "例: something to drink", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "名詞の直後に置く", 10, g.ACCENT),
         g.t(160, 192, "名詞的用法・副詞的用法と並ぶ", 9.5, g.SUB)]
    return g.titled("形容詞的用法", b)


@register("副詞的用法")
def fig_副詞的用法():
    b = [g.t(160, 44, "I went there to see him.", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「彼に会うためにそこへ行った」", 9.5, g.ACCENT),
         g.t(160, 96, "動詞を修飾する不定詞", 10.5),
         g.t(160, 120, "目的・原因・結果・理由を表す", 10, g.ACCENT),
         g.t(160, 144, "「〜するために」", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "例: I'm glad to hear that.", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 192, "名詞的用法・形容詞的用法と並ぶ", 9.5, g.SUB)]
    return g.titled("副詞的用法", b)


@register("関係副詞")
def fig_関係副詞():
    b = [g.t(160, 44, "the house where I lived", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 80, 36, g.INK, 1.2, g.FILL),
         g.rect(200, 56, 80, 36, g.INK, 1.2, g.FILL2),
         g.t(80, 78, "先行詞", 9.5), g.t(240, 78, "where節", 9.5, g.ACCENT),
         g.t(160, 108, "場所・時・理由を表す関係詞", 10.5),
         g.t(160, 132, "where / when / why など", 10, g.ACCENT),
         g.t(160, 156, "関係代名詞と違い副詞の働き", 10),
         g.t(160, 180, "例: the day when we met", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 204, "先行詞+関係詞節で名詞を修飾", 9.5, g.SUB)]
    return g.titled("関係副詞", b)


@register("制限用法")
def fig_制限用法():
    b = [g.t(160, 44, "The boy who runs fast is my friend.", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「速く走る少年は私の友達だ」", 9.5, g.ACCENT),
         g.t(160, 96, "関係詞節で名詞を限定する", 10.5),
         g.t(160, 120, "どの人かを特定する", 10, g.ACCENT),
         g.t(160, 144, "コンマを置かない", 10),
         g.t(160, 168, "非制限用法と対になる", 10, g.ACCENT),
         g.t(160, 192, "限定用法とも呼ぶ", 9.5, g.SUB)]
    return g.titled("制限用法", b)


@register("非制限用法")
def fig_非制限用法():
    b = [g.t(160, 44, "My brother, who lives in Tokyo, is 20.", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「東京に住んでいる兄は20歳だ」", 9.5, g.ACCENT),
         g.t(160, 96, "補足説明を添える関係詞節", 10.5),
         g.t(160, 120, "コンマで区切って書く", 10, g.ACCENT),
         g.t(160, 144, "名詞を特定せず情報を加える", 10),
         g.t(160, 168, "制限用法と対になる", 10, g.ACCENT),
         g.t(160, 192, "続き用法・非限定用法とも", 9.5, g.SUB)]
    return g.titled("非制限用法", b)


@register("形式目的語")
def fig_形式目的語():
    b = [g.t(160, 44, "I find it easy to study.", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 60, 36, g.INK, 1.2, g.FILL2),
         g.rect(220, 56, 60, 36, g.INK, 1.2, g.FILL),
         g.t(70, 78, "it(形式目的語)", 9, g.ACCENT),
         g.t(250, 78, "to study(真目的語)", 8.5, g.ACCENT),
         g.t(160, 108, "長い目的語を文末に回す", 10.5),
         g.t(160, 132, "find/think/make + it + 補語 + to …", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 156, "「〜するのは簡単だと分かる」", 10, g.ACCENT),
         g.t(160, 180, "形式主語 it と対になる", 10),
         g.t(160, 204, "第5文型の応用", 9.5, g.SUB)]
    return g.titled("形式目的語", b)


@register("使役動詞")
def fig_使役動詞():
    b = [g.t(160, 44, "make / have / let + 人 + 原形", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "make him go(行かせる)", 10, g.ACCENT),
         g.t(160, 96, "「人に〜させる」を表す動詞", 10.5),
         g.t(160, 120, "make: 強制 / have: 依頼 / let: 許可", 10, g.ACCENT),
         g.t(160, 144, "例: I had him carry it.", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "原形不定詞をとる", 10, g.ACCENT),
         g.t(160, 192, "get は to不定詞をとる", 9.5, g.SUB)]
    return g.titled("使役動詞", b)


@register("知覚動詞")
def fig_知覚動詞():
    b = [g.t(160, 44, "I saw him run(ning).", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「彼が走るのを見た」", 9.5, g.ACCENT),
         g.t(160, 96, "see / hear / feel など", 10.5),
         g.t(160, 120, "知覚の対象を動詞の原形で表す", 10, g.ACCENT),
         g.t(160, 144, "原形: 動作全体 / -ing: 進行中の動作", 9.5, g.ACCENT),
         g.t(160, 168, "例: I heard her sing.", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 192, "原形不定詞をとる", 9.5, g.SUB)]
    return g.titled("知覚動詞", b)


@register("句動詞")
def fig_句動詞():
    b = [g.t(160, 44, "give up / look after / turn on", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 100, 36, g.INK, 1.2, g.FILL),
         g.rect(180, 56, 100, 36, g.INK, 1.2, g.FILL2),
         g.t(90, 78, "動詞", 9.5), g.t(230, 78, "前置詞・副詞", 9.5, g.ACCENT),
         g.t(160, 108, "動詞+前置詞(副詞)で1語のように使う", 10.5),
         g.t(160, 132, "例: give up = あきらめる", 10, g.ACCENT),
         g.t(160, 156, "句全体で意味が決まる", 10),
         g.t(160, 180, "群動詞とも呼ぶ", 10, g.ACCENT),
         g.t(160, 204, "受身・名詞化されることもある", 9.5, g.SUB)]
    return g.titled("句動詞", b)


@register("群動詞")
def fig_群動詞():
    b = [g.t(160, 44, "take care of / make use of", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 240, 36, g.INK, 1.2, g.FILL2),
         g.t(160, 78, "動詞+名詞+前置詞で1つの動詞の働き", 9.5, g.ACCENT),
         g.t(160, 108, "例: take care of = 世話をする", 10, g.ACCENT),
         g.t(160, 132, "句動詞の一種", 10),
         g.t(160, 156, "受身: The baby is taken care of.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 180, "「まとめて1動詞」と考える", 10, g.ACCENT),
         g.t(160, 204, "前置詞を忘れないことが重要", 9.5, g.SUB)]
    return g.titled("群動詞", b)


@register("群前置詞")
def fig_群前置詞():
    b = [g.t(160, 44, "in front of / because of / instead of", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 240, 36, g.INK, 1.2, g.FILL),
         g.t(160, 78, "複数の語で1つの前置詞の働き", 9.5, g.ACCENT),
         g.t(160, 108, "例: in front of = 〜の前に", 10, g.ACCENT),
         g.t(160, 132, "because of = 〜のために", 10),
         g.t(160, 156, "後ろに名詞(句)をとる", 10, g.ACCENT),
         g.t(160, 180, "複合前置詞とも呼ぶ", 10, g.ACCENT),
         g.t(160, 204, "句前置詞", 9.5, g.SUB)]
    return g.titled("群前置詞", b)


@register("名詞構文")
def fig_名詞構文():
    b = [g.t(160, 44, "the arrival of spring", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「春の到来」", 9.5, g.ACCENT),
         g.t(160, 96, "動詞・形容詞を名詞に変えて表現", 10.5),
         g.t(160, 120, "動詞 arrive → 名詞 arrival", 10, g.ACCENT),
         g.t(160, 144, "例: the use of the computer", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "「〜の使用」", 10, g.ACCENT),
         g.t(160, 192, "書き言葉で簡潔に表せる", 9.5, g.SUB)]
    return g.titled("名詞構文", b)


@register("準動詞")
def fig_準動詞():
    b = [g.rect(40, 44, 72, 40, g.INK, 1.2, g.FILL),
         g.rect(124, 44, 72, 40, g.INK, 1.2, g.FILL),
         g.rect(208, 44, 72, 40, g.INK, 1.2, g.FILL2),
         g.t(76, 62, "不定詞", 9.5), g.t(160, 62, "動名詞", 9.5), g.t(244, 62, "分詞", 9.5, g.ACCENT),
         g.t(160, 104, "動詞から派生して", 10.5),
         g.t(160, 126, "名詞・形容詞・副詞の働きをする", 10, g.ACCENT),
         g.t(160, 150, "to不定詞・-ing形・過去分詞", 10),
         g.t(160, 174, "動詞の性質も残す", 10, g.ACCENT),
         g.t(160, 198, "動詞を文中で使い回す道具", 9.5, g.SUB)]
    return g.titled("準動詞", b)


@register("分詞形容詞")
def fig_分詞形容詞():
    b = [g.t(160, 44, "a broken window / an interesting book", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「割れた窓」「おもしろい本」", 9.5, g.ACCENT),
         g.t(160, 96, "分詞が形容詞のように名詞を修飾", 10.5),
         g.t(160, 120, "過去分詞: 〜された / 現在分詞: 〜させる", 10, g.ACCENT),
         g.t(160, 144, "例: excited(興奮した) / exciting(興奮させる)", 9, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "感情を表す分詞は特に重要", 10, g.ACCENT),
         g.t(160, 192, "限定用法(名詞の前)が中心", 9.5, g.SUB)]
    return g.titled("分詞形容詞", b)


@register("等位接続詞")
def fig_等位接続詞():
    b = [g.rect(40, 44, 90, 36, g.INK, 1.2, g.FILL),
         g.rect(230, 44, 50, 36, g.INK, 1.2, g.FILL2),
         g.t(85, 66, "A", 10), g.t(255, 66, "B", 10, g.ACCENT),
         g.t(160, 58, "and / or / but", 9, g.ACCENT),
         g.t(160, 100, "対等な語句・文をつなぐ", 10.5),
         g.t(160, 124, "A and B / A or B / A but B", 10, g.ACCENT),
         g.t(160, 148, "従属接続詞と対になる", 10),
         g.t(160, 172, "例: I like tea and coffee.", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 196, "対等の関係で結ぶ", 9.5, g.SUB)]
    return g.titled("等位接続詞", b)


@register("従属接続詞")
def fig_従属接続詞():
    b = [g.rect(40, 44, 90, 36, g.INK, 1.2, g.FILL),
         g.rect(230, 44, 50, 36, g.INK, 1.2, g.FILL2),
         g.t(85, 66, "主節", 10), g.t(255, 66, "従属節", 10, g.ACCENT),
         g.t(160, 58, "because / if / when", 8.5, g.ACCENT),
         g.t(160, 100, "従属節を導く接続詞", 10.5),
         g.t(160, 124, "「なぜなら」「もし」「〜のとき」", 10, g.ACCENT),
         g.t(160, 148, "等位接続詞と対になる", 10),
         g.t(160, 172, "例: I stayed home because it rained.", 9, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 196, "従属節は文の一部", 9.5, g.SUB)]
    return g.titled("従属接続詞", b)


@register("相関接続詞")
def fig_相関接続詞():
    b = [g.t(160, 44, "both A and B / either A or B", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 90, 36, g.INK, 1.2, g.FILL),
         g.rect(190, 56, 90, 36, g.INK, 1.2, g.FILL2),
         g.t(85, 78, "A", 10), g.t(235, 78, "B", 10, g.ACCENT),
         g.t(160, 108, "2語で1組になってつなぐ", 10.5),
         g.t(160, 132, "both…and / either…or / neither…nor", 9, g.ACCENT),
         g.t(160, 156, "「AもBも」「AかBか」", 10, g.ACCENT),
         g.t(160, 180, "例: either tea or coffee", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 204, "対になる語をセットで使う", 9.5, g.SUB)]
    return g.titled("相関接続詞", b)


@register("接続副詞")
def fig_接続副詞():
    b = [g.t(160, 44, "however / therefore / besides", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「しかし」「それゆえ」「そのうえ」", 9.5, g.ACCENT),
         g.t(160, 96, "文と文のつながりを示す副詞", 10.5),
         g.t(160, 120, "接続詞と違い文を従属させない", 10, g.ACCENT),
         g.t(160, 144, "例: It rained. However, we went.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "コンマやセミコロンと使う", 10, g.ACCENT),
         g.t(160, 192, "文頭・文中に置ける", 9.5, g.SUB)]
    return g.titled("接続副詞", b)


@register("譲歩構文")
def fig_譲歩構文():
    b = [g.t(160, 44, "Although it was cold, he went out.", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「寒かったけれど彼は出かけた」", 9.5, g.ACCENT),
         g.t(160, 96, "「〜にもかかわらず」を表す", 10.5),
         g.t(160, 120, "although / though / even if など", 10, g.ACCENT),
         g.t(160, 144, "例: though it is hard", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "予想に反する結果をつなぐ", 10, g.ACCENT),
         g.t(160, 192, "逆接の構文", 9.5, g.SUB)]
    return g.titled("譲歩構文", b)


@register("二重否定")
def fig_二重否定():
    b = [g.t(160, 44, "not + 否定語 = 強い肯定", 10, g.INK),
         g.t(160, 70, "I don't have no money.(くだけた言い方)", 9, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 96, "文法的には「お金がない」", 10, g.ACCENT),
         g.t(160, 120, "It is not impossible. = 不可能ではない", 10),
         g.t(160, 144, "not uncommon = 珍しくない", 10, g.ACCENT),
         g.t(160, 168, "二つの否定で肯定を強調", 10),
         g.t(160, 192, "標準英語では not…no は避ける", 9.5, g.SUB)]
    return g.titled("二重否定", b)


@register("全体否定")
def fig_全体否定():
    b = [g.t(160, 44, "None of them came.", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「彼らは誰も来なかった」", 9.5, g.ACCENT),
         g.t(160, 96, "全部を否定する表現", 10.5),
         g.t(160, 120, "none / nothing / nobody / neither", 9.5, g.ACCENT),
         g.t(160, 144, "例: Nothing is certain.", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "部分否定(not all)と対になる", 10, g.ACCENT),
         g.t(160, 192, "「まったく〜ない」", 9.5, g.SUB)]
    return g.titled("全体否定", b)


@register("準否定語")
def fig_準否定語():
    b = [g.t(160, 44, "hardly / scarcely / seldom", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「ほとんど〜ない」「めったに〜ない」", 9.5, g.ACCENT),
         g.t(160, 96, "否定に近い意味を持つ語", 10.5),
         g.t(160, 120, "形は否定語ではないが否定の意味", 10, g.ACCENT),
         g.t(160, 144, "例: I hardly know him.", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "半否定語とも呼ぶ", 10, g.ACCENT),
         g.t(160, 192, "付加疑問などは肯定形で受ける", 9.5, g.SUB)]
    return g.titled("準否定語", b)


@register("文修飾副詞")
def fig_文修飾副詞():
    b = [g.t(160, 44, "Fortunately, I passed the exam.", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「幸運にも、試験に合格した」", 9.5, g.ACCENT),
         g.t(160, 96, "文全体にコメントを添える副詞", 10.5),
         g.t(160, 120, "fortunately / actually / probably", 9.5, g.ACCENT),
         g.t(160, 144, "文頭に置かれることが多い", 10, g.ACCENT),
         g.t(160, 168, "動詞だけを修飾する副詞と区別", 10),
         g.t(160, 192, "コンマで区切ることもある", 9.5, g.SUB)]
    return g.titled("文修飾副詞", b)


@register("談話標識")
def fig_談話標識():
    b = [g.t(160, 44, "well / you know / I mean", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "話の流れを整える表現", 9.5, g.ACCENT),
         g.t(160, 96, "意味は薄いが会話のつなぎに使う", 10.5),
         g.t(160, 120, "「えーと」「つまり」「あのー」", 10, g.ACCENT),
         g.t(160, 144, "聞き手への合図にもなる", 10, g.ACCENT),
         g.t(160, 168, "ディスコースマーカー", 10, g.ACCENT),
         g.t(160, 192, "話し言葉で多用される", 9.5, g.SUB)]
    return g.titled("談話標識", b)


@register("ディスコースマーカー")
def fig_ディスコースマーカー():
    b = [g.t(160, 44, "however / first / in conclusion", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "文章のつながりを示す表現", 9.5, g.ACCENT),
         g.t(160, 96, "段落・文の関係を明示する", 10.5),
         g.t(160, 120, "「しかし」「まず」「結論として」", 10, g.ACCENT),
         g.t(160, 144, "談話標識の一種", 10, g.ACCENT),
         g.t(160, 168, "英文ライティングで重要", 10),
         g.t(160, 192, "読み手を誘導する記号", 9.5, g.SUB)]
    return g.titled("ディスコースマーカー", b)


@register("パラフレーズ")
def fig_パラフレーズ():
    b = [g.rect(40, 44, 100, 44, g.INK, 1.2, g.FILL),
         g.rect(180, 44, 100, 44, g.INK, 1.2, g.FILL2),
         g.t(90, 62, "元の表現", 9.5), g.t(90, 78, "(難しい語)", 8.5, g.SUB),
         g.t(230, 62, "言い換え", 9.5, g.ACCENT), g.t(230, 78, "(分かりやすい語)", 8.5, g.SUB),
         g.arrow(144, 66, 176, 66, g.ACCENT, 1.8),
         g.t(160, 104, "別の言葉で表現し直すこと", 10.5),
         g.t(160, 128, "意味を保ったまま言い換える", 10, g.ACCENT),
         g.t(160, 152, "読解・作文の技術", 10),
         g.t(160, 176, "英作文で単語の繰り返しを避ける", 10, g.ACCENT),
         g.t(160, 200, "要約の基礎にもなる", 9.5, g.SUB)]
    return g.titled("パラフレーズ", b)


@register("コロケーション")
def fig_コロケーション():
    b = [g.t(160, 44, "make a decision / take a bath", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 240, 36, g.INK, 1.2, g.FILL2),
         g.t(160, 78, "「決断する」「入浴する」", 9.5, g.ACCENT),
         g.t(160, 108, "自然な語の組合せ", 10.5),
         g.t(160, 132, "決まった結びつきで使う", 10, g.ACCENT),
         g.t(160, 156, "例: heavy rain(強い雨)・strong tea", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 180, "直訳では不自然になることがある", 10, g.ACCENT),
         g.t(160, 204, "語彙学習の重要な要素", 9.5, g.SUB)]
    return g.titled("コロケーション", b)


@register("無冠詞")
def fig_無冠詞():
    b = [g.rect(40, 44, 110, 40, g.INK, 1.2, g.FILL),
         g.rect(190, 44, 90, 40, g.INK, 1.2, g.FILL2),
         g.t(95, 62, "冠詞なし", 10), g.t(95, 78, "(a/an/the が付かない)", 8, g.SUB),
         g.t(235, 62, "慣用的表現", 10, g.ACCENT),
         g.t(160, 104, "冠詞を使わない表現", 10.5),
         g.t(160, 126, "go to school / by car / at home", 9, g.ACCENT),
         g.t(160, 150, "名詞の意味が抽象的・一般的", 10, g.ACCENT),
         g.t(160, 174, "「学校へ行く(本来の目的)」", 10),
         g.t(160, 198, "冠詞の使い分けの一部", 9.5, g.SUB)]
    return g.titled("無冠詞", b)


# ---- 国語(四字熟語・文学概念・論理・活動・古典) -----------------------------


@register("一石二鳥")
def fig_一石二鳥():
    b = [g.circle(70, 100, 12, g.INK, 1.2, g.FILL),
         g.t(70, 132, "石", 9),
         g.path("M70,112 Q160,96 250,60", g.ACCENT, 2.0),
         g.t(160, 88, "投げた石", 8.5, g.ACCENT),
         g.circle(250, 52, 12, g.INK, 1.2, g.FILL2),
         g.circle(230, 62, 10, g.INK, 1.2, g.FILL2),
         g.t(250, 36, "2羽の鳥", 8.5, g.SUB),
         g.t(160, 152, "1つの行いで2つの利益を得る", 10.5),
         g.t(160, 176, "「一挙両得」と同様の意味", 10, g.ACCENT),
         g.t(160, 200, "英語: kill two birds with one stone", 9, g.SUB)]
    return g.titled("一石二鳥", b)


@register("馬耳東風")
def fig_馬耳東風():
    b = [g.circle(170, 62, 24, g.INK, 1.4, g.FILL),
         g.path("M170,62 Q150,60 146,74 Q142,88 150,96", g.INK, 1.8),
         g.path("M146,74 Q130,70 120,74", g.INK, 1.4),
         g.path("M120,74 Q96,64 84,74 Q60,86 46,76", g.ACCENT, 1.8),
         g.t(58, 92, "東風", 9, g.ACCENT),
         g.t(160, 126, "他人の意見を聞き流すこと", 10.5),
         g.t(160, 148, "「馬の耳に風」が由来", 10, g.ACCENT),
         g.t(160, 172, "「馬耳東風」= 聞き入れない", 10),
         g.t(160, 196, "「馬の耳に念仏」も同様の意味", 9, g.SUB)]
    return g.titled("馬耳東風", b)


@register("我田引水")
def fig_我田引水():
    b = [g.line(50, 60, 270, 60, g.INK, 1.4),
         g.path("M90,60 L130,60 L130,120 L70,120 L70,60", g.ACCENT, 1.8, g.FILL2),
         g.t(100, 142, "自分の田んぼ", 9, g.ACCENT),
         g.path("M200,60 L240,60 L240,110 L170,110", g.SUB, 1.2, g.FILL),
         g.t(205, 126, "他人の田", 8.5, g.SUB),
         g.arrow(130, 90, 176, 90, g.ACCENT, 1.6),
         g.t(160, 168, "自分の都合のよいように", 10.5),
         g.t(160, 190, "物事を運ぼうとすること", 10.5, g.ACCENT),
         g.t(160, 214, "「水利を我田に引く」が由来", 9.5, g.SUB)]
    return g.titled("我田引水", b)


@register("五里霧中")
def fig_五里霧中():
    b = [g.rect(40, 44, 240, 100, g.INK, 1.2, g.FILL),
         g.path("M60,60 Q160,110 260,56", g.INK, 1.0, dash="4 4"),
         g.path("M60,90 Q160,130 260,86", g.INK, 1.0, dash="4 4"),
         g.t(160, 72, "？", 18, g.ACCENT),
         g.circle(150, 96, 14, g.INK, 1.4, g.FILL),
         g.t(160, 162, "霧の中で方角が分からないように", 10.5),
         g.t(160, 184, "見通しが立たないこと", 10.5, g.ACCENT),
         g.t(160, 208, "「五里の霧」が由来", 9.5, g.SUB)]
    return g.titled("五里霧中", b)


@register("暗中模索")
def fig_暗中模索():
    b = [g.rect(40, 44, 240, 100, g.INK, 1.2, "#232323"),
         g.t(160, 70, "？", 16, g.ACCENT),
         g.path("M80,140 Q100,110 120,140", g.INK, 2.0),
         g.path("M140,140 Q160,110 180,140", g.INK, 2.0),
         g.path("M200,140 Q220,110 240,140", g.INK, 2.0),
         g.circle(150, 96, 13, g.INK, 1.4, g.FILL),
         g.t(160, 164, "手がかりのないまま", 10.5),
         g.t(160, 186, "あれこれ探りながら進むこと", 10.5, g.ACCENT),
         g.t(160, 210, "「暗い中を手さぐりで探す」", 9.5, g.SUB)]
    return g.titled("暗中模索", b)


@register("十人十色")
def fig_十人十色():
    cols = ["#e78b8b", "#e8b9c3", "#a8d8ea", "#7b6c9e", "#9fae5c",
            "#f0c987", "#b9a7e8", "#7fc9a8", "#e8907b", "#8ba7c9"]
    b = []
    for i, c in enumerate(cols):
        x = 30 + (i % 5) * 56
        y = 44 + (i // 5) * 52
        b += [g.circle(x + 16, y + 16, 14, g.INK, 1.0, c),
              g.path(f"M{x+16},{y+30} L{x+16},{y+46} L{x+4},{y+56} M{x+16},{y+46} L{x+28},{y+56}", g.INK, 1.2)]
    b += [g.t(160, 156, "考え方・好みは人それぞれ", 10.5),
          g.t(160, 178, "十人いれば十通りの違いがある", 10.5, g.ACCENT),
          g.t(160, 202, "「十人十色」= 個性を認める", 9.5, g.SUB)]
    return g.titled("十人十色", b)


@register("弱肉強食")
def fig_弱肉強食():
    b = [g.path("M40,120 Q70,60 110,100 Q150,40 200,90 Q240,50 270,110 L270,140 L40,140 Z", g.INK, 1.5, g.FILL),
         g.path("M90,140 L120,96 L140,140 Z", g.INK, 1.2, g.FILL2),
         g.t(160, 158, "強い者が弱い者を食うこと", 10.5),
         g.t(160, 180, "弱い者が滅びる厳しい世界", 10.5, g.ACCENT),
         g.t(160, 204, "「弱い肉は強い者のえじき」", 9.5, g.SUB)]
    return g.titled("弱肉強食", b)


@register("以心伝心")
def fig_以心伝心():
    b = [g.circle(90, 82, 20, g.INK, 1.4, g.FILL),
         g.circle(230, 82, 20, g.INK, 1.4, g.FILL),
         g.path("M110,82 Q160,52 210,82", g.ACCENT, 2.0),
         g.path("M110,82 Q160,112 210,82", g.ACCENT, 1.4, dash="3 3"),
         g.t(160, 74, "心", 11, g.ACCENT),
         g.t(160, 112, "通じ合う", 8.5, g.ACCENT),
         g.t(160, 128, "言葉にしなくても気持ちが伝わる", 10.5),
         g.t(160, 150, "「心から心へ伝える」", 10, g.ACCENT),
         g.t(160, 174, "以心伝心の以 = もって", 9.5, g.SUB)]
    return g.titled("以心伝心", b)


@register("自然主義")
def fig_自然主義():
    b = [g.rect(60, 44, 200, 44, g.INK, 1.3, g.FILL),
         g.t(160, 62, "現実をありのまま描く", 10, g.ACCENT),
         g.t(160, 78, "(理想化しない)", 8.5, g.SUB),
         g.t(160, 106, "明治後期の文学運動", 10.5),
         g.t(160, 128, "人間の内面を率直に描く", 10, g.ACCENT),
         g.t(160, 152, "例: 島崎藤村『破戒』", 10, g.ACCENT),
         g.t(160, 176, "田山花袋『蒲団』", 10),
         g.t(160, 200, "私小説の成立につながる", 9.5, g.SUB)]
    return g.titled("自然主義", b)


@register("私小説")
def fig_私小説():
    b = [g.circle(160, 60, 24, g.INK, 1.4, g.FILL),
         g.t(160, 65, "作者", 10, g.ACCENT),
         g.arrow(160, 88, 160, 108, g.INK, 1.4),
         g.rect(60, 112, 200, 44, g.INK, 1.3, g.FILL2),
         g.t(160, 132, "自分自身の体験を", 10, g.ACCENT),
         g.t(160, 148, "主人公として描く小説", 10, g.ACCENT),
         g.t(160, 176, "作者=主人公の視点", 10.5),
         g.t(160, 200, "自然主義から生まれた形式", 9.5, g.SUB)]
    return g.titled("私小説", b)


@register("写生文")
def fig_写生文():
    b = [g.rect(50, 44, 100, 90, g.INK, 1.3, g.FILL),
         g.path("M70,70 Q100,50 130,70 Q100,90 70,70", g.ACCENT, 1.6),
         g.line(70, 100, 130, 100, g.INK, 1.2),
         g.line(70, 112, 120, 112, g.INK, 1.2),
         g.rect(180, 44, 90, 90, g.INK, 1.3, g.FILL2),
         g.t(225, 66, "見たまま", 9.5, g.ACCENT),
         g.t(225, 84, "感じたまま", 9.5, g.ACCENT),
         g.t(225, 102, "文章に", 9.5, g.ACCENT),
         g.t(160, 152, "実際に見たものを", 10.5),
         g.t(160, 174, "ありのまま文章に表す", 10.5, g.ACCENT),
         g.t(160, 198, "正岡子規らが提唱", 9.5, g.SUB)]
    return g.titled("写生文", b)


@register("言文一致")
def fig_言文一致():
    b = [g.t(160, 44, "話し言葉 = 書き言葉", 11, g.INK),
         g.rect(40, 56, 110, 40, g.INK, 1.3, g.FILL),
         g.rect(170, 56, 110, 40, g.INK, 1.3, g.FILL2),
         g.t(95, 74, "「〜である」", 9.5), g.t(225, 74, "「〜だ」", 9.5, g.ACCENT),
         g.line(150, 76, 170, 76, g.ACCENT, 1.8),
         g.t(160, 112, "話し言葉と書き言葉を一致させる", 10.5),
         g.t(160, 134, "明治期の言文一致運動", 10, g.ACCENT),
         g.t(160, 158, "二葉亭四迷『浮雲』など", 10, g.ACCENT),
         g.t(160, 182, "近代文学の成立に貢献", 10),
         g.t(160, 206, "現代の「です・ます体」へつながる", 9.5, g.SUB)]
    return g.titled("言文一致", b)


@register("象徴詩")
def fig_象徴詩():
    b = [g.circle(160, 70, 26, g.INK, 1.4, g.FILL2),
         g.t(160, 75, "象徴", 9.5, g.ACCENT),
         g.path("M134,70 Q90,50 80,100 Q70,140 110,150", g.INK, 1.2),
         g.path("M186,70 Q230,50 240,100 Q250,140 210,150", g.INK, 1.2),
         g.t(90, 160, "意味の連想", 8.5, g.SUB),
         g.t(230, 160, "意味の連想", 8.5, g.SUB),
         g.t(160, 180, "直接言わず象徴で表現する詩", 10.5),
         g.t(160, 204, "例: 萩原朔太郎・三好達治", 10, g.ACCENT),
         g.t(160, 228, "フランス象徴主義の影響", 9.5, g.SUB)]
    return g.titled("象徴詩", b)


@register("もののあはれ")
def fig_もののあはれ():
    b = [g.path("M60,120 Q160,40 260,120", g.ACCENT, 2.0),
         g.circle(110, 86, 6, g.ACCENT, 0, "#f3ddd3"),
         g.circle(160, 74, 6, g.ACCENT, 0, "#f3ddd3"),
         g.circle(210, 86, 6, g.ACCENT, 0, "#f3ddd3"),
         g.t(160, 136, "しみじみとした情趣", 10.5),
         g.t(160, 158, "物事の美しさ・はかなさに", 10),
         g.t(160, 180, "心を動かされること", 10, g.ACCENT),
         g.t(160, 204, "本居宣長が『源氏物語』で説いた", 9.5, g.SUB)]
    return g.titled("もののあはれ", b)


@register("無常観")
def fig_無常観():
    b = [g.path("M60,120 Q160,50 260,120", g.ACCENT, 2.0),
         g.circle(110, 90, 6, g.ACCENT, 0, g.FILL2),
         g.circle(160, 76, 6, g.ACCENT, 0, g.FILL2),
         g.circle(210, 92, 6, g.ACCENT, 0, g.FILL2),
         g.t(160, 136, "すべてのものは移り変わる", 10.5),
         g.t(160, 158, "「諸行無常」の考え方", 10, g.ACCENT),
         g.t(160, 182, "『平家物語』『方丈記』に通じる", 10),
         g.t(160, 206, "仏教的な世界観", 9.5, g.SUB)]
    return g.titled("無常観", b)


@register("演繹")
def fig_演繹():
    b = [g.rect(80, 44, 160, 34, g.INK, 1.3, g.FILL),
         g.t(160, 66, "一般論(大前提)", 10, g.ACCENT),
         g.arrow(160, 82, 160, 98, g.INK, 1.4),
         g.rect(80, 100, 160, 34, g.INK, 1.3, g.FILL),
         g.t(160, 122, "個別の事実(小前提)", 10),
         g.arrow(160, 138, 160, 154, g.INK, 1.4),
         g.rect(80, 156, 160, 34, g.INK, 1.3, g.FILL2),
         g.t(160, 178, "結論", 10, g.ACCENT),
         g.t(160, 204, "一般から個別を導く論理", 9.5)]
    return g.titled("演繹", b)


@register("帰納")
def fig_帰納():
    b = [g.rect(40, 44, 70, 34, g.INK, 1.2, g.FILL),
         g.rect(125, 44, 70, 34, g.INK, 1.2, g.FILL),
         g.rect(210, 44, 70, 34, g.INK, 1.2, g.FILL),
         g.t(75, 66, "例1", 9.5), g.t(160, 66, "例2", 9.5), g.t(245, 66, "例3…", 9.5),
         g.line(75, 82, 160, 102, g.INK, 1.2), g.line(160, 82, 160, 102, g.INK, 1.2),
         g.line(245, 82, 160, 102, g.INK, 1.2),
         g.rect(80, 104, 160, 40, g.INK, 1.3, g.FILL2),
         g.t(160, 128, "共通する結論(一般化)", 10, g.ACCENT),
         g.t(160, 164, "個別の例から一般を導く", 10.5),
         g.t(160, 188, "「データ→法則」の考え方", 10, g.ACCENT),
         g.t(160, 212, "演繹と対になる論理", 9.5, g.SUB)]
    return g.titled("帰納", b)


@register("アナロジー")
def fig_アナロジー():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.2, g.FILL),
         g.rect(180, 44, 100, 40, g.INK, 1.2, g.FILL2),
         g.t(90, 62, "A(既知)", 10), g.t(90, 78, "性質α", 8.5, g.SUB),
         g.t(230, 62, "B(未知)", 10, g.ACCENT), g.t(230, 78, "性質α?", 8.5, g.SUB),
         g.arrow(144, 64, 176, 64, g.ACCENT, 1.8),
         g.t(160, 104, "似ている点から推測する", 10.5),
         g.t(160, 128, "類推・たとえ", 10, g.ACCENT),
         g.t(160, 152, "例: 水の流れ=電流のたとえ", 10, g.ACCENT),
         g.t(160, 176, "説明・発想に使う思考法", 10),
         g.t(160, 200, "アナロジー思考", 9.5, g.SUB)]
    return g.titled("アナロジー", b)


@register("二項対立")
def fig_二項対立():
    b = [g.rect(40, 44, 100, 44, g.INK, 1.3, g.FILL2),
         g.rect(180, 44, 100, 44, g.INK, 1.3, g.FILL),
         g.t(90, 62, "昼", 10, g.ACCENT), g.t(90, 78, "光", 8.5, g.SUB),
         g.t(230, 62, "夜", 10, g.ACCENT), g.t(230, 78, "闇", 8.5, g.SUB),
         g.t(160, 58, "vs", 11, g.ACCENT),
         g.t(160, 108, "対になる2つの概念", 10.5),
         g.t(160, 132, "「善と悪」「男と女」など", 10, g.ACCENT),
         g.t(160, 156, "対比で物事をとらえる", 10),
         g.t(160, 180, "評論の読み方の基本", 10, g.ACCENT),
         g.t(160, 204, "対立関係の構造を見つける", 9.5, g.SUB)]
    return g.titled("二項対立", b)


@register("川柳")
def fig_川柳():
    b = [g.rect(40, 44, 240, 60, g.INK, 1.3, g.FILL),
         g.t(160, 62, "5・7・5(俳句と同じ形)", 10, g.ACCENT),
         g.t(160, 82, "例: 「朝寝して 叱られて 起きる」", 9.5),
         g.t(160, 120, "季語がなく、人間の生活を", 10.5),
         g.t(160, 142, "おかしみをもって詠む", 10.5, g.ACCENT),
         g.t(160, 166, "俳句との違い: 季語・切れ字がない", 10),
         g.t(160, 190, "江戸の川柳点から発展", 10, g.ACCENT),
         g.t(160, 214, "風刺・ユーモアの文芸", 9.5, g.SUB)]
    return g.titled("川柳", b)


@register("句会")
def fig_句会():
    b = [g.rect(40, 44, 240, 40, g.INK, 1.3, g.FILL),
         g.t(160, 62, "俳句を持ち寄って選び合う会", 10, g.ACCENT),
         g.rect(50, 96, 60, 34, g.INK, 1.2, g.FILL),
         g.rect(130, 96, 60, 34, g.INK, 1.2, g.FILL),
         g.rect(210, 96, 60, 34, g.INK, 1.2, g.FILL2),
         g.t(80, 114, "句①", 9), g.t(160, 114, "句②", 9), g.t(240, 114, "句③", 9),
         g.t(160, 148, "互選で秀句を決める", 10.5),
         g.t(160, 170, "鑑賞・批評の場", 10, g.ACCENT),
         g.t(160, 194, "句会の作法: 出句・披講・選句", 9.5, g.SUB)]
    return g.titled("句会", b)


@register("要約")
def fig_要約():
    b = [g.rect(40, 44, 110, 90, g.INK, 1.3, g.FILL),
         g.t(95, 66, "長い文章", 10), g.t(95, 84, "(全体)", 9, g.SUB),
         g.rect(40, 84, 110, 50, g.INK, 1.0, g.FILL2),
         g.line(52, 96, 138, 96, g.INK, 0.8), g.line(52, 106, 130, 106, g.INK, 0.8),
         g.arrow(154, 80, 182, 80, g.ACCENT, 1.8),
         g.rect(190, 56, 90, 48, g.INK, 1.3, g.FILL2),
         g.t(235, 76, "要点だけ", 10, g.ACCENT),
         g.t(235, 92, "短くまとめる", 9, g.SUB),
         g.t(160, 152, "大切な内容を落とさず", 10.5),
         g.t(160, 174, "短くまとめること", 10.5, g.ACCENT),
         g.t(160, 198, "要約力は国語の基礎技能", 9.5, g.SUB)]
    return g.titled("要約", b)


@register("対比")
def fig_対比():
    b = [g.rect(40, 44, 100, 44, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 44, g.INK, 1.3, g.FILL2),
         g.t(90, 62, "A", 10), g.t(90, 78, "特徴a", 8.5, g.SUB),
         g.t(230, 62, "B", 10, g.ACCENT), g.t(230, 78, "特徴b", 8.5, g.SUB),
         g.t(160, 58, "vs", 10, g.ACCENT),
         g.t(160, 108, "二つのものを比べて違いを明確に", 10.5),
         g.t(160, 132, "共通点・相違点を読み取る", 10, g.ACCENT),
         g.t(160, 156, "説明文・評論の技法", 10),
         g.t(160, 180, "対比で特徴が際立つ", 10, g.ACCENT),
         g.t(160, 204, "読み取り・作文どちらでも重要", 9.5, g.SUB)]
    return g.titled("対比", b)


@register("語り手")
def fig_語り手():
    b = [g.circle(70, 60, 18, g.INK, 1.3, g.FILL),
         g.path("M70,78 L70,104 M70,84 L52,96 M70,84 L88,96", g.INK, 1.4),
         g.rect(120, 44, 160, 44, g.INK, 1.3, g.FILL2),
         g.t(200, 62, "物語を語る視点", 10, g.ACCENT),
         g.t(200, 78, "(誰の目から見るか)", 8.5, g.SUB),
         g.arrow(94, 78, 116, 72, g.ACCENT, 1.6),
         g.t(160, 110, "一人称「私」・三人称など", 10.5),
         g.t(160, 134, "語り手によって見え方が変わる", 10, g.ACCENT),
         g.t(160, 158, "「語り手=作者」とは限らない", 10),
         g.t(160, 182, "小説の読み取りの重要ポイント", 10, g.ACCENT),
         g.t(160, 206, "人称・視点に注目する", 9.5, g.SUB)]
    return g.titled("語り手", b)


@register("硬筆")
def fig_硬筆():
    b = [g.line(60, 80, 260, 80, g.INK, 1.2),
         g.line(60, 100, 260, 100, g.INK, 1.2),
         g.line(60, 120, 260, 120, g.INK, 1.2),
         g.line(100, 72, 100, 128, g.INK, 0.8),
         g.t(80, 96, "鉛筆で書く", 9.5, g.ACCENT),
         g.t(160, 140, "筆記具(鉛筆等)で書く書写", 10.5),
         g.t(160, 162, "毛筆(習字)と対になる", 10, g.ACCENT),
         g.t(160, 186, "文字の形・正しい書き方", 10),
         g.t(160, 210, "日常生活の文字を整える", 9.5, g.SUB)]
    return g.titled("硬筆", b)


@register("ビブリオバトル")
def fig_ビブリオバトル():
    b = [g.rect(160, 40, 40, 34, g.INK, 1.3, g.FILL2),
         g.t(180, 56, "本", 10, g.ACCENT),
         g.rect(40, 88, 72, 36, g.INK, 1.2, g.FILL),
         g.rect(124, 88, 72, 36, g.INK, 1.2, g.FILL),
         g.rect(208, 88, 72, 36, g.INK, 1.2, g.FILL),
         g.t(76, 106, "発表者A", 9), g.t(160, 106, "発表者B", 9), g.t(244, 106, "発表者C", 9),
         g.line(180, 76, 110, 86, g.INK, 1.0), g.line(180, 76, 160, 86, g.INK, 1.0),
         g.line(180, 76, 220, 86, g.INK, 1.0),
         g.t(160, 142, "本を紹介して一番読みたい本を", 10.5),
         g.t(160, 164, "投票で決める書評合戦", 10.5, g.ACCENT),
         g.t(160, 188, "「読書の格闘技」", 10, g.ACCENT),
         g.t(160, 212, "国語の言語活動で取り組まれる", 9.5, g.SUB)]
    return g.titled("ビブリオバトル", b)


@register("十訓抄")
def fig_十訓抄():
    b = [g.rect(90, 44, 140, 90, g.INK, 1.6, g.FILL),
         g.line(90, 64, 230, 64, g.INK, 1.0),
         g.t(160, 80, "『十訓抄』", 12, g.ACCENT),
         g.t(160, 100, "鎌倉時代の説話集", 10),
         g.t(160, 120, "(教訓を説く)", 9.5, g.SUB),
         g.t(160, 152, "十の教訓に説話を配した", 10.5),
         g.t(160, 176, "「少年老いやすく学成りがたし」", 10, g.ACCENT),
         g.t(160, 200, "教科書教材としても登場", 9.5, g.SUB)]
    return g.titled("十訓抄", b)


@register("風姿花伝")
def fig_風姿花伝():
    b = [g.rect(90, 44, 140, 90, g.INK, 1.6, g.FILL),
         g.line(90, 64, 230, 64, g.INK, 1.0),
         g.t(160, 80, "『風姿花伝』", 12, g.ACCENT),
         g.t(160, 100, "世阿弥の能楽論", 10),
         g.t(160, 120, "(1400年頃)", 9.5, g.SUB),
         g.t(160, 152, "能の芸術論・稽古の心得", 10.5),
         g.t(160, 176, "「秘すれば花」の名言", 10, g.ACCENT),
         g.t(160, 200, "日本最古の演劇論", 9.5, g.SUB)]
    return g.titled("風姿花伝", b)


@register("唐詩選")
def fig_唐詩選():
    b = [g.rect(90, 44, 140, 90, g.INK, 1.6, g.FILL),
         g.line(90, 64, 230, 64, g.INK, 1.0),
         g.t(160, 80, "『唐詩選』", 12, g.ACCENT),
         g.t(160, 100, "中国・唐の詩の選集", 10),
         g.t(160, 120, "(漢詩集)", 9.5, g.SUB),
         g.t(160, 152, "李白・杜甫らの名詩を収録", 10.5),
         g.t(160, 176, "日本でも漢文教材として使われた", 10, g.ACCENT),
         g.t(160, 200, "唐詩選の「絶句」「律詩」", 9.5, g.SUB)]
    return g.titled("唐詩選", b)


# ---- 音楽(伝統曲・公有楽曲のカード図) ---------------------------------------


def _song(word, genre, desc):
    """歌のカード図(装飾的な五線+ジャンル・説明)。旋律の正確さは主張しない。"""
    b = staff(96)
    for x, y in ((96, 112), (134, 100), (172, 108), (210, 92), (248, 100)):
        b += note(x, y)
    b += [g.t(160, 146, genre, 10.5, g.ACCENT),
          g.t(160, 168, desc, 10.5),
          g.t(160, 192, word, 10, g.SUB)]
    return g.titled(word, b)


@register("仰げば尊し")
def fig_仰げば尊し():
    return _song("仰げば尊し", "卒業式の唱歌(1884年)", "別れを惜しみ教えに感謝する歌")


@register("アニー・ローリー")
def fig_アニーローリー():
    return _song("アニー・ローリー", "スコットランド民謡", "別れの恋を歌う抒情的な曲")


@register("かりぼし切り歌")
def fig_かりぼし切り歌():
    return _song("かりぼし切り歌", "民謡(刈干切り唄)", "刈り干す作業と恋を詠う仕事歌")


@register("聖者の行進")
def fig_聖者の行進():
    return _song("聖者の行進", "アメリカの伝統曲", "When the Saints Go Marching In")


@register("ロング・ロング・アゴー")
def fig_ロングロングアゴー():
    return _song("ロング・ロング・アゴー", "アメリカの歌(1833年)", "遠い昔の思い出を歌う")


@register("こきりこ節")
def fig_こきりこ節():
    return _song("こきりこ節", "富山県の民謡", "こきりこ(竹の楽器)を打ちながら歌う")


@register("星の世界")
def fig_星の世界():
    return _song("星の世界", "賛美歌", "星の美しさをたたえる歌")


@register("シチリアーナ")
def fig_シチリアーナ():
    return _song("シチリアーナ", "イタリアの古典曲", "シチリア風のゆったりした舞曲")


@register("モルダウ")
def fig_モルダウ():
    return _song("モルダウ", "スメタナの交響詩(1874年)", "『わが祖国』の中の川の情景")


@register("巣鶴鈴慕")
def fig_巣鶴鈴慕():
    return _song("巣鶴鈴慕", "尺八曲(琴古流)", "鶴の巣立ちを描く古典本曲")


@register("鹿の遠音")
def fig_鹿の遠音():
    return _song("鹿の遠音", "尺八曲(琴古流)", "遠くの鹿の声を交わす本曲")


@register("トリステーザ")
def fig_トリステーザ():
    return _song("トリステーザ", "イタリアの歌(トスティ)", "哀愁を帯びたナポリの歌")


@register("新版歌祭文")
def fig_新版歌祭文():
    return _song("新版歌祭文", "浄瑠璃(義太夫節)", "お染久松の恋をうたう人形浄瑠璃")


@register("野崎村")
def fig_野崎村():
    return _song("野崎村", "文楽・浄瑠璃", "お染久松の悲恋を描く段物")


@register("執心鐘入")
def fig_執心鐘入():
    return _song("執心鐘入", "能の曲", "鐘の中の鬼女を描く能")


# ---- 英語(残り20語の構造図) --------------------------------------------------


@register("完了動名詞")
def fig_完了動名詞():
    b = [g.t(160, 44, "having + 過去分詞", 10.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "例: I regret having said that.", 9, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 96, "「言ったことを後悔している」", 9.5, g.ACCENT),
         g.t(160, 120, "動詞の時制より前の動作", 10.5),
         g.t(160, 144, "動名詞の完了形", 10, g.ACCENT),
         g.t(160, 168, "regret/remember などと使う", 10),
         g.t(160, 192, "完了不定詞と似た働き", 9.5, g.SUB)]
    return g.titled("完了動名詞", b)


@register("複合関係詞")
def fig_複合関係詞():
    b = [g.t(160, 44, "what / whatever / whoever", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「〜するもの(こと)」「〜でも」", 9.5, g.ACCENT),
         g.t(160, 96, "先行詞を含む関係詞", 10.5),
         g.t(160, 120, "what = the thing which", 10, g.ACCENT),
         g.t(160, 144, "例: What he said is true.", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "関係代名詞+ever の形もある", 10, g.ACCENT),
         g.t(160, 192, "複合関係代名詞・複合関係副詞を含む", 9.5, g.SUB)]
    return g.titled("複合関係詞", b)


@register("複合関係代名詞")
def fig_複合関係代名詞():
    b = [g.t(160, 44, "what / whatever / whoever / whomever", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "先行詞を含む関係代名詞", 10, g.ACCENT),
         g.t(160, 96, "what = the thing which", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 120, "whoever = anyone who", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 144, "例: Whoever said that is wrong.", 9, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "「〜する人(もの)は誰でも」", 10, g.ACCENT),
         g.t(160, 192, "複合関係詞の中心", 9.5, g.SUB)]
    return g.titled("複合関係代名詞", b)


@register("複合関係副詞")
def fig_複合関係副詞():
    b = [g.t(160, 44, "wherever / whenever / however", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「どこでも」「いつでも」「どんなに〜でも」", 9, g.ACCENT),
         g.t(160, 96, "先行詞を含む関係副詞", 10.5),
         g.t(160, 120, "wherever = at any place where", 9, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 144, "例: Wherever you go, I'll follow.", 9, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "「どこへ行こうと」", 10, g.ACCENT),
         g.t(160, 192, "譲歩の意味を表すこともある", 9.5, g.SUB)]
    return g.titled("複合関係副詞", b)


@register("連鎖関係代名詞")
def fig_連鎖関係代名詞():
    b = [g.t(160, 44, "There is no one but knows it.", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「それを知らない人はいない」", 9.5, g.ACCENT),
         g.t(160, 96, "but = who … not(〜しない人)", 10, g.ACCENT),
         g.t(160, 120, "no … but の構文", 10.5),
         g.t(160, 144, "「〜しない…はない」", 10, g.ACCENT),
         g.t(160, 168, "but が関係代名詞の働き", 10),
         g.t(160, 192, "準否定の関係代名詞", 9.5, g.SUB)]
    return g.titled("連鎖関係代名詞", b)


@register("話法")
def fig_話法():
    b = [g.rect(40, 44, 100, 44, g.INK, 1.2, g.FILL),
         g.rect(180, 44, 100, 44, g.INK, 1.2, g.FILL2),
         g.t(90, 62, "直接話法", 9.5), g.t(90, 78, "(そのまま引用)", 8.5, g.SUB),
         g.t(230, 62, "間接話法", 9.5, g.ACCENT), g.t(230, 78, "(言い換えて伝達)", 8.5, g.SUB),
         g.arrow(144, 66, 176, 66, g.ACCENT, 1.8),
         g.t(160, 104, "人の言葉を伝える表現方法", 10.5),
         g.t(160, 128, "直接: He said, \"I am busy.\"", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 152, "間接: He said (that) he was busy.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 176, "時制・人称が変わる", 10, g.ACCENT),
         g.t(160, 200, "描出話法もある", 9.5, g.SUB)]
    return g.titled("話法", b)


@register("直接話法")
def fig_直接話法():
    b = [g.t(160, 44, "He said, \"I am busy.\"", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「彼は『忙しい』と言った」", 9.5, g.ACCENT),
         g.t(160, 96, "発言をそのまま引用符で表す", 10.5),
         g.t(160, 120, "クォーテーションマーク「\"」を使う", 10, g.ACCENT),
         g.t(160, 144, "例: She asked, \"Are you OK?\"", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "間接話法と対になる", 10, g.ACCENT),
         g.t(160, 192, "会話文・引用文", 9.5, g.SUB)]
    return g.titled("直接話法", b)


@register("間接話法")
def fig_間接話法():
    b = [g.t(160, 44, "He said (that) he was busy.", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「彼は忙しいと言った」", 9.5, g.ACCENT),
         g.t(160, 96, "発言を言い換えて伝える", 10.5),
         g.t(160, 120, "that節や疑問詞節で表す", 10, g.ACCENT),
         g.t(160, 144, "時制の一致で am → was に変化", 9.5, g.ACCENT),
         g.t(160, 168, "直接話法と対になる", 10, g.ACCENT),
         g.t(160, 192, "伝達動詞 said/told/asked と使う", 9.5, g.SUB)]
    return g.titled("間接話法", b)


@register("描出話法")
def fig_描出話法():
    b = [g.t(160, 44, "He was tired. He had to rest.", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "地の文に人物の心の声を混ぜる", 9.5, g.ACCENT),
         g.t(160, 96, "引用符もthatも使わない", 10.5),
         g.t(160, 120, "小説で人物の心情を表す技法", 10, g.ACCENT),
         g.t(160, 144, "自由間接話法とも呼ぶ", 10, g.ACCENT),
         g.t(160, 168, "日本語の「〜だろうと思った」に近い", 10),
         g.t(160, 192, "直接話法と間接話法の中間", 9.5, g.SUB)]
    return g.titled("描出話法", b)


@register("時制の一致")
def fig_時制の一致():
    b = [g.rect(40, 44, 100, 44, g.INK, 1.2, g.FILL),
         g.rect(180, 44, 100, 44, g.INK, 1.2, g.FILL2),
         g.t(90, 62, "主節が過去", 9.5), g.t(90, 78, "(said)", 8.5, g.SUB),
         g.t(230, 62, "従属節も過去", 9.5, g.ACCENT), g.t(230, 78, "(was)", 8.5, g.SUB),
         g.arrow(144, 66, 176, 66, g.ACCENT, 1.8),
         g.t(160, 104, "主節の時制に従属節が合わせられる", 10.5),
         g.t(160, 128, "am/is → was / will → would", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 152, "不変の真理は一致しない", 10, g.ACCENT),
         g.t(160, 176, "例: He said (that) he was busy.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 200, "間接話法の基本ルール", 9.5, g.SUB)]
    return g.titled("時制の一致", b)


@register("大過去")
def fig_大過去():
    b = [g.line(50, 90, 270, 90, g.INK, 1.2),
         g.t(60, 76, "過去(過去完了より前)", 9, g.ACCENT),
         g.t(180, 104, "過去完了", 9.5, g.ACCENT),
         g.line(180, 90, 180, 74, g.INK, 1.0, dash="3 3"),
         g.t(160, 122, "過去のある時点より前の動作", 10.5),
         g.t(160, 144, "had + 過去分詞", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "例: He had left before I came.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 192, "「〜する前に〜していた」", 10, g.ACCENT),
         g.t(160, 216, "過去完了形の用法の一つ", 9.5, g.SUB)]
    return g.titled("大過去", b)


@register("過去完了形")
def fig_過去完了形():
    b = [g.t(160, 44, "had + 過去分詞", 10.5, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "例: I had finished it by noon.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 96, "「正午までに終えていた」", 9.5, g.ACCENT),
         g.t(160, 120, "過去のある時点での完了・経験・継続", 10.5),
         g.t(160, 144, "大過去(過去より前)の表現", 10, g.ACCENT),
         g.t(160, 168, "had は have の過去形", 10),
         g.t(160, 192, "時制の一致でも使う", 9.5, g.SUB)]
    return g.titled("過去完了形", b)


@register("未来完了形")
def fig_未来完了形():
    b = [g.t(160, 44, "will have + 過去分詞", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "例: I will have finished by then.", 9, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 96, "「その頃には終えているだろう」", 9.5, g.ACCENT),
         g.t(160, 120, "未来のある時点での完了を表す", 10.5),
         g.t(160, 144, "by 〜(までに)とよく使う", 10, g.ACCENT),
         g.t(160, 168, "未来の完了・経験・継続", 10, g.ACCENT),
         g.t(160, 192, "will have + 過去分詞の形", 9.5, g.SUB)]
    return g.titled("未来完了形", b)


@register("過去完了進行形")
def fig_過去完了進行形():
    b = [g.t(160, 44, "had been + -ing", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "例: I had been studying for 3 hours.", 8.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 96, "「3時間勉強し続けていた」", 9.5, g.ACCENT),
         g.t(160, 120, "過去のある時点まで続いていた動作", 10.5),
         g.t(160, 144, "継続の意味を強調する", 10, g.ACCENT),
         g.t(160, 168, "had been + 現在分詞", 10, g.ACCENT),
         g.t(160, 192, "過去完了形の進行形", 9.5, g.SUB)]
    return g.titled("過去完了進行形", b)


@register("未来進行形")
def fig_未来進行形():
    b = [g.t(160, 44, "will be + -ing", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "例: I will be waiting for you.", 9, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 96, "「待っているでしょう」", 9.5, g.ACCENT),
         g.t(160, 120, "未来のある時点で進行中の動作", 10.5),
         g.t(160, 144, "「きっと〜している」", 10, g.ACCENT),
         g.t(160, 168, "予定・見込みの意味もある", 10),
         g.t(160, 192, "will be + 現在分詞", 9.5, g.SUB)]
    return g.titled("未来進行形", b)


@register("無生物主語")
def fig_無生物主語():
    b = [g.t(160, 44, "The news surprised me.", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.t(160, 70, "「その知らせに私は驚いた」", 9.5, g.ACCENT),
         g.t(160, 96, "物事が主語になる構文", 10.5),
         g.t(160, 120, "日本語では「〜に」と訳す", 10, g.ACCENT),
         g.t(160, 144, "例: This book made me happy.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 168, "英語らしい表現の一つ", 10, g.ACCENT),
         g.t(160, 192, "原因・理由を主語にする", 9.5, g.SUB)]
    return g.titled("無生物主語", b)


@register("同格")
def fig_同格():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.2, g.FILL),
         g.rect(180, 44, 100, 40, g.INK, 1.2, g.FILL2),
         g.t(90, 62, "名詞", 9.5), g.t(90, 78, "(Mr. Smith)", 8.5, g.SUB),
         g.t(230, 62, "説明する語", 9.5, g.ACCENT), g.t(230, 78, "(the teacher)", 8.5, g.SUB),
         g.t(160, 58, "=", 11, g.ACCENT),
         g.t(160, 104, "同じものを別の語で言い換える", 10.5),
         g.t(160, 128, "例: Mr. Smith, the teacher, came.", 9, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 152, "「同格の名詞」", 10, g.ACCENT),
         g.t(160, 176, "that節と同格の名詞(idea/fact)もある", 9.5, g.ACCENT),
         g.t(160, 200, "コンマで区切って置く", 9.5, g.SUB)]
    return g.titled("同格", b)


@register("同格節")
def fig_同格節():
    b = [g.t(160, 44, "the fact that he came", 9.5, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(40, 56, 90, 36, g.INK, 1.2, g.FILL),
         g.rect(190, 56, 90, 36, g.INK, 1.2, g.FILL2),
         g.t(85, 78, "名詞", 9.5), g.t(235, 78, "that節", 9.5, g.ACCENT),
         g.t(160, 108, "名詞の内容を説明する that節", 10.5),
         g.t(160, 132, "idea / fact / news などと使う", 9.5, g.ACCENT),
         g.t(160, 156, "「〜という(知らせ・事実)」", 10, g.ACCENT),
         g.t(160, 180, "例: the news that he won", 10, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 204, "名詞+同格のthat節", 9.5, g.SUB)]
    return g.titled("同格節", b)


@register("挿入句")
def fig_挿入句():
    b = [g.t(160, 44, "He is, I think, honest.", 10, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(60, 56, 90, 36, g.INK, 1.2, g.FILL),
         g.rect(170, 56, 90, 36, g.INK, 1.2, g.FILL2),
         g.t(105, 78, "文の中心", 9.5), g.t(215, 78, "I think(挿入)", 9, g.ACCENT),
         g.t(160, 108, "文の中に差し挟む語句", 10.5),
         g.t(160, 132, "「〜だと思う」「〜によれば」", 10, g.ACCENT),
         g.t(160, 156, "コンマで区切って挿入", 10),
         g.t(160, 180, "例: This is, of course, true.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 204, "文修飾の働き", 9.5, g.SUB)]
    return g.titled("挿入句", b)


@register("挿入節")
def fig_挿入節():
    b = [g.t(160, 44, "The book, I believe, is good.", 9, g.INK, "middle", g.MATHFONT, "700"),
         g.rect(50, 56, 90, 36, g.INK, 1.2, g.FILL),
         g.rect(180, 56, 90, 36, g.INK, 1.2, g.FILL2),
         g.t(95, 78, "文の中心", 9.5), g.t(225, 78, "I believe(挿入節)", 8.5, g.ACCENT),
         g.t(160, 108, "文の中に差し挟む節(主語+動詞)", 10.5),
         g.t(160, 132, "「〜だと信じる」などのコメント", 10, g.ACCENT),
         g.t(160, 156, "コンマで区切る", 10),
         g.t(160, 180, "例: She is, it seems, angry.", 9.5, g.ACCENT, "middle", g.MATHFONT, "700"),
         g.t(160, 204, "挿入句が節になったもの", 9.5, g.SUB)]
    return g.titled("挿入節", b)


# ---- 国語(四字熟語・古典作品・概念の残り) -------------------------------------


@register("絶体絶命")
def fig_絶体絶命():
    b = [g.path("M80,140 L160,70 L240,140 Z", g.ACCENT, 1.4, g.FILL),
         g.t(160, 66, "崖", 9, g.ACCENT),
         g.circle(160, 110, 12, g.INK, 1.4, g.FILL),
         g.t(160, 164, "逃げ場のない状態", 10.5),
         g.t(160, 186, "「絶体」「絶命」= 身動きがとれない", 10, g.ACCENT),
         g.t(160, 210, "危機的な状況を強調する四字熟語", 9.5, g.SUB)]
    return g.titled("絶体絶命", b)


@register("危機一髪")
def fig_危機一髪():
    b = [g.line(160, 40, 160, 90, g.ACCENT, 1.2),
         g.circle(160, 92, 8, g.INK, 1.2, g.FILL),
         g.path("M160,100 L160,150", g.INK, 1.0),
         g.line(120, 150, 200, 150, g.INK, 1.2),
         g.t(160, 130, "糸一本", 9, g.ACCENT),
         g.t(160, 168, "あと少しで危険な状態", 10.5),
         g.t(160, 190, "「髪一本の差」が由来", 10, g.ACCENT),
         g.t(160, 214, "間一髪の危機", 9.5, g.SUB)]
    return g.titled("危機一髪", b)


@register("大器晩成")
def fig_大器晩成():
    b = [g.rect(80, 44, 160, 30, g.INK, 1.2, g.FILL2),
         g.t(160, 64, "大きな器", 10, g.ACCENT),
         g.arrow(160, 82, 160, 104, g.INK, 1.4),
         g.rect(80, 108, 160, 30, g.INK, 1.2, g.FILL),
         g.t(160, 128, "できるまで時間がかかる", 10),
         g.t(160, 156, "大人物は大成するのが遅い", 10.5),
         g.t(160, 178, "才能はあとから開花する", 10, g.ACCENT),
         g.t(160, 202, "「大きな器は完成が遅い」", 9.5, g.SUB)]
    return g.titled("大器晩成", b)


@register("本末転倒")
def fig_本末転倒():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.2, g.FILL2),
         g.rect(180, 44, 100, 40, g.INK, 1.2, g.FILL),
         g.t(90, 62, "本(大切なこと)", 10, g.ACCENT),
         g.t(230, 62, "末(枝葉のこと)", 10),
         g.arrow(90, 90, 90, 110, g.INK, 1.2), g.arrow(230, 90, 230, 110, g.INK, 1.2),
         g.t(90, 132, "下に", 8.5, g.ACCENT), g.t(230, 132, "上に", 8.5, g.ACCENT),
         g.t(160, 160, "大事なこととどうでもいいことが", 10.5),
         g.t(160, 182, "逆になってしまうこと", 10.5, g.ACCENT),
         g.t(160, 206, "「本と末が転倒する」", 9.5, g.SUB)]
    return g.titled("本末転倒", b)


@register("自業自得")
def fig_自業自得():
    b = [g.t(160, 44, "自分の行い", 10.5, g.INK),
         g.arrow(160, 56, 160, 78, g.ACCENT, 1.6),
         g.rect(80, 82, 160, 36, g.INK, 1.3, g.FILL2),
         g.t(160, 104, "自分の受ける報い", 10, g.ACCENT),
         g.t(160, 136, "自分の行いの結果を", 10.5),
         g.t(160, 158, "自分で受けること", 10.5, g.ACCENT),
         g.t(160, 182, "悪い結果は身から出た錆", 10),
         g.t(160, 206, "「自ら業(ごう)を自ら得る」", 9.5, g.SUB)]
    return g.titled("自業自得", b)


@register("自画自賛")
def fig_自画自賛():
    b = [g.rect(70, 44, 120, 80, g.INK, 1.3, g.FILL),
         g.circle(160, 70, 8, g.ACCENT, 0, g.FILL2),
         g.t(160, 100, "自分の絵", 9.5),
         g.path("M190,120 Q210,80 230,90", g.INK, 1.2),
         g.t(222, 76, "「上手い」", 9, g.ACCENT),
         g.t(160, 144, "自分の作品・行いを", 10.5),
         g.t(160, 166, "自分でほめること", 10.5, g.ACCENT),
         g.t(160, 190, "「自分の絵に自分で賛を書く」", 9.5, g.SUB)]
    return g.titled("自画自賛", b)


@register("異口同音")
def fig_異口同音():
    b = [g.circle(60, 70, 14, g.INK, 1.2, g.FILL),
         g.circle(130, 70, 14, g.INK, 1.2, g.FILL),
         g.circle(200, 70, 14, g.INK, 1.2, g.FILL),
         g.circle(270, 70, 14, g.INK, 1.2, g.FILL),
         g.t(60, 96, "A", 9), g.t(130, 96, "B", 9), g.t(200, 96, "C", 9), g.t(270, 96, "D", 9),
         g.t(160, 124, "「同じだ」", 12, g.ACCENT),
         g.t(160, 150, "大勢が同じことを言う", 10.5),
         g.t(160, 172, "「口をそろえて」", 10, g.ACCENT),
         g.t(160, 196, "人々の意見が一致する様子", 9.5, g.SUB)]
    return g.titled("異口同音", b)


@register("疑心暗鬼")
def fig_疑心暗鬼():
    b = [g.circle(100, 80, 18, g.INK, 1.3, g.FILL),
         g.t(100, 85, "？", 11, g.ACCENT),
         g.path("M118,80 Q180,40 240,80", g.INK, 1.4, dash="4 4"),
         g.path("M118,80 Q180,120 240,80", g.INK, 1.4, dash="4 4"),
         g.t(160, 108, "疑いの心", 9.5, g.ACCENT),
         g.t(160, 132, "疑い始めると何でも疑わしく見える", 10.5),
         g.t(160, 154, "「疑う心が闇を生む」", 10, g.ACCENT),
         g.t(160, 178, "疑心暗鬼に陥る", 9.5, g.SUB)]
    return g.titled("疑心暗鬼", b)


@register("支離滅裂")
def fig_支離滅裂():
    b = [g.rect(40, 44, 70, 30, g.INK, 1.0, g.FILL),
         g.rect(120, 44, 70, 30, g.INK, 1.0, g.FILL),
         g.rect(200, 44, 70, 30, g.INK, 1.0, g.FILL2),
         g.line(90, 52, 120, 52, g.SUB, 1.0, dash="3 3"),
         g.line(160, 52, 200, 52, g.SUB, 1.0, dash="3 3"),
         g.path("M80,120 Q120,100 160,120 Q200,100 240,120", g.ACCENT, 1.6, dash="4 3"),
         g.t(160, 140, "ばらばらに砕けた状態", 10.5),
         g.t(160, 162, "話・文章のつじつまが合わない", 10, g.ACCENT),
         g.t(160, 186, "「支離」「滅裂」= ばらばら", 9.5, g.SUB)]
    return g.titled("支離滅裂", b)


@register("東奔西走")
def fig_東奔西走():
    b = [g.circle(160, 62, 14, g.INK, 1.3, g.FILL),
         g.path("M160,76 L160,140", g.INK, 1.4),
         g.path("M160,84 L120,100 M160,84 L200,100 M160,104 L124,120 M160,104 L196,120", g.INK, 1.4),
         g.path("M80,150 Q120,130 160,150 Q200,130 240,150", g.ACCENT, 1.8, dash="4 3"),
         g.t(160, 168, "あちこち忙しくかけ回る", 10.5),
         g.t(160, 190, "「東へ走り西へ走る」", 10, g.ACCENT),
         g.t(160, 214, "忙しい様子の四字熟語", 9.5, g.SUB)]
    return g.titled("東奔西走", b)


@register("無我夢中")
def fig_無我夢中():
    b = [g.circle(160, 60, 16, g.INK, 1.3, g.FILL),
         g.t(160, 65, "夢中", 9, g.ACCENT),
         g.path("M160,78 Q90,90 160,120 Q230,140 160,158", g.ACCENT, 2.0),
         g.t(160, 138, "他のことを忘れる", 9, g.ACCENT),
         g.t(160, 178, "自分を忘れて一つのことに", 10.5),
         g.t(160, 200, "打ち込むこと", 10.5, g.ACCENT),
         g.t(160, 224, "「無我」= 我を忘れる", 9.5, g.SUB)]
    return g.titled("無我夢中", b)


@register("玉石混交")
def fig_玉石混交():
    b = [g.circle(70, 80, 14, g.ACCENT, 0, g.FILL2),
         g.circle(120, 96, 10, g.INK, 1.0, g.FILL),
         g.circle(170, 76, 13, g.ACCENT, 0, g.FILL2),
         g.circle(220, 94, 10, g.INK, 1.0, g.FILL),
         g.circle(260, 70, 9, g.INK, 1.0, g.FILL),
         g.t(160, 126, "良いものと悪いものが", 10.5),
         g.t(160, 148, "入り混じっていること", 10.5, g.ACCENT),
         g.t(160, 172, "「玉(宝石)と石が混ざる」", 10, g.ACCENT),
         g.t(160, 196, "人材や作品の質がまちまち", 9.5, g.SUB)]
    return g.titled("玉石混交", b)


@register("古今著聞集")
def fig_古今著聞集():
    b = [g.rect(90, 44, 140, 90, g.INK, 1.6, g.FILL),
         g.line(90, 64, 230, 64, g.INK, 1.0),
         g.t(160, 80, "『古今著聞集』", 12, g.ACCENT),
         g.t(160, 100, "鎌倉時代の説話集", 10),
         g.t(160, 120, "(橘成季編)", 9.5, g.SUB),
         g.t(160, 152, "「古今」の事柄を集めた説話集", 10.5),
         g.t(160, 176, "和歌・仏教・説話など幅広く収録", 10, g.ACCENT),
         g.t(160, 200, "十訓抄と並ぶ鎌倉説話集", 9.5, g.SUB)]
    return g.titled("古今著聞集", b)


@register("堤中納言物語")
def fig_堤中納言物語():
    b = [g.rect(90, 44, 140, 90, g.INK, 1.6, g.FILL),
         g.line(90, 64, 230, 64, g.INK, 1.0),
         g.t(160, 80, "『堤中納言物語』", 12, g.ACCENT),
         g.t(160, 100, "平安時代の物語", 10),
         g.t(160, 120, "(短編物語集)", 9.5, g.SUB),
         g.t(160, 152, "『虫めづる姫君』など10編", 10.5),
         g.t(160, 176, "風刺・ユーモアあふれる短編", 10, g.ACCENT),
         g.t(160, 200, "教科書教材としても登場", 9.5, g.SUB)]
    return g.titled("堤中納言物語", b)


@register("増鏡")
def fig_増鏡():
    b = [g.rect(90, 44, 140, 90, g.INK, 1.6, g.FILL),
         g.line(90, 64, 230, 64, g.INK, 1.0),
         g.t(160, 80, "『増鏡』", 12, g.ACCENT),
         g.t(160, 100, "南北朝時代の歴史物語", 10),
         g.t(160, 120, "(鎌倉時代〜)", 9.5, g.SUB),
         g.t(160, 152, "承久の乱から鎌倉幕府の滅亡まで", 10.5),
         g.t(160, 176, "『大鏡』『水鏡』など「四鏡」の一つ", 10, g.ACCENT),
         g.t(160, 200, "歴史を鏡にたとえた物語", 9.5, g.SUB)]
    return g.titled("増鏡", b)


@register("十八史略")
def fig_十八史略():
    b = [g.rect(90, 44, 140, 90, g.INK, 1.6, g.FILL),
         g.line(90, 64, 230, 64, g.INK, 1.0),
         g.t(160, 80, "『十八史略』", 12, g.ACCENT),
         g.t(160, 100, "中国の歴史書", 10),
         g.t(160, 120, "(宋代の編纂)", 9.5, g.SUB),
         g.t(160, 152, "中国の18の史書の要約", 10.5),
         g.t(160, 176, "日本でも漢文教材として読まれた", 10, g.ACCENT),
         g.t(160, 200, "「十八史略」の故事成語も多い", 9.5, g.SUB)]
    return g.titled("十八史略", b)


@register("世阿弥")
def fig_世阿弥():
    b = [g.circle(160, 58, 24, g.INK, 1.4, g.FILL2),
         g.t(160, 63, "能面", 10, g.ACCENT),
         g.line(160, 82, 160, 96, g.INK, 1.2),
         g.rect(100, 96, 120, 40, g.INK, 1.3, g.FILL),
         g.t(160, 114, "『風姿花伝』", 10.5, g.ACCENT),
         g.t(160, 128, "(能楽論)", 9, g.SUB),
         g.t(160, 154, "能の大成者(観阿弥の子)", 10.5),
         g.t(160, 178, "「秘すれば花」を説く", 10, g.ACCENT),
         g.t(160, 202, "室町時代の能役者・芸術論者", 9.5, g.SUB)]
    return g.titled("世阿弥", b)


@register("抽象化")
def fig_抽象化():
    b = [g.rect(40, 44, 100, 40, g.INK, 1.3, g.FILL),
         g.rect(180, 44, 100, 40, g.INK, 1.3, g.FILL2),
         g.t(90, 62, "具体的な物事", 10), g.t(90, 78, "(りんご・みかん)", 8.5, g.SUB),
         g.t(230, 62, "共通する性質", 10, g.ACCENT), g.t(230, 78, "(果物)", 8.5, g.SUB),
         g.arrow(144, 64, 176, 64, g.ACCENT, 1.8),
         g.t(160, 104, "共通点を取り出して", 10.5),
         g.t(160, 126, "まとめること", 10.5, g.ACCENT),
         g.t(160, 150, "プログラミングでは重要", 10, g.ACCENT),
         g.t(160, 174, "個別の例から概念をつくる", 10),
         g.t(160, 198, "具象化と対になる", 9.5, g.SUB)]
    return g.titled("抽象化", b)


@register("アイデンティティ")
def fig_アイデンティティ():
    b = [g.circle(160, 70, 30, g.INK, 1.4, g.FILL),
         g.t(160, 75, "自分", 10, g.ACCENT),
         g.t(160, 116, "「自分は何者か」という", 10.5),
         g.t(160, 138, "自己の認識・確信", 10.5, g.ACCENT),
         g.t(160, 162, "家族・社会との関わりで形成", 10),
         g.t(160, 186, "アイデンティティの確立(青年期の課題)", 9.5, g.ACCENT),
         g.t(160, 210, "自己同一性とも訳す", 9.5, g.SUB)]
    return g.titled("アイデンティティ", b)


@register("禁中並公家諸法度")
def fig_禁中並公家諸法度():
    b = [g.rect(60, 44, 200, 40, g.INK, 1.4, g.FILL2),
         g.t(160, 62, "1615年 朝廷・公家への法令", 9.5, g.ACCENT),
         g.t(160, 104, "天皇・公家の行動を規制", 10.5),
         g.t(160, 126, "「朝廷は学問を第一に」", 10, g.ACCENT),
         g.t(160, 150, "幕府が朝廷を統制した", 10),
         g.t(160, 174, "武家諸法度と対になる", 10, g.ACCENT),
         g.t(160, 198, "江戸幕府の支配体制の一環", 9.5, g.SUB)]
    return g.titled("禁中並公家諸法度", b)


if __name__ == "__main__":
    main()
