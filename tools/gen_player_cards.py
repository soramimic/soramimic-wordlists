#!/usr/bin/env python3
"""baseball.csv / football.csv の実写が無い行に割り当てる「選手カード」SVGを生成する。

両リストとも自由ライセンスの実写が取れるのは一部だけで(baseball 37%,
football 9%)、残りは画像が空のままだった。ソラミミ動画は単語ごとに1枚絵を出す
ので、画像が無い行は他のリストと同じ見せ方ができない。

youtuber の象徴カード(ADR 00018)と同じ考え方で、**素材を一切借りずに配色と
文字と自作の図形だけで**描いたカードを割り当てる。

- 1人1枚。同じ人物の複数行(full/family/given)は同じ `original` なので同じ
  カードを共有する
- ファイル名は名前から決定的に導出する: `bb_<sha1(original)の先頭10桁>.svg` /
  `fb_...`。id は将来の再採番に耐えないので使わない
- 配色は**所属チームのチームカラー**(`tools/team_colors.json`)。色は公表された
  事実で著作物ではないので使える。**ロゴ・エンブレム・マスコットは使わない**し、
  ユニフォームの意匠(縦縞など)も模倣しない。帯とラインだけの単純な構成にする
- チームカラーが分からないチームは、チーム名のハッシュから色相を振る
  (youtuber の事務所ハッシュと同じ考え方)
- 中央左に名前の頭文字、下部にフルネーム、上部に区分と所属チームを描く。
  実写と誤認されないよう右上に「イメージ」の札を必ず入れる
- 図版は**抽象的な人型のシルエット**(円と自作パスだけ)と**競技のボール**
  (野球=円と縫い目の曲線、サッカー=円と正五角形)のみ。実在のロゴ・ピクトグラム
  は参照していない
- 自己完結SVG(外部フォント・画像を参照しない)。viewBox は 320x200 固定
- **生成物はリポジトリ内(`images/baseball/`, `images/football/`)に置き**、
  CSVからは raw URL で参照する(youtuber と同じ。詳細は ADR 00020)

usage:
  # 生成してCSVのimage/image_pageを埋める(実写のある行は触らない)
  python3 tools/gen_player_cards.py

  # 片方だけ
  python3 tools/gen_player_cards.py --list baseball

  # 生成だけ(CSVを書き換えない)
  python3 tools/gen_player_cards.py --no-apply

  # CSVから参照されなくなったSVGを消す
  python3 tools/gen_player_cards.py --prune
"""

import argparse
import colorsys
import csv
import hashlib
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from silhouettes import silhouette_svg  # noqa: E402
from wpnames import write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COLORS_PATH = Path(__file__).resolve().parent / "team_colors.json"

RAW_BASE = "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/main"
BLOB_BASE = "https://github.com/soramimic/soramimic-wordlists/blob/main"

W, H = 320, 200
HERO_H = 112
PAD = 16
RADIUS = 16
FONT = "'Hiragino Sans','Noto Sans JP',sans-serif"
NAME_SIZES_1LINE = (23, 21, 19)
NAME_SIZES_2LINE = (17, 15, 13, 11)
NAME_MAX_W = 232        # 右下のボールを避けるぶん、youtuberより狭い
HEAD_MAX_W = 136        # 帯の上の区分・チーム名が使える幅(x=108からボールまで)
TEAM_MAX = 10           # チーム名の表示上限(全角換算)

# 減量版(--style minimal)の頭文字ディスク。帯(y=112)の境目にまたがる位置に
# 置くと、上下どちらの領域にも属さない「記号」として読める
MIN_DISC_CY = 100
MIN_DISC_R = 48
MIN_MARK_SIZES = (56, 44)   # (1文字, 2文字)
# 職業シルエットは帯の左側に敷く。右端(x=12+90=102)がディスクのハロー
# (x=107から)に触れない大きさにしてある
MIN_SIL_BOX = (12, 10, 90)  # (x, y, 一辺)

# リストごとの設定。`hue` はチームカラーが分からないときの基準色相
LISTS = {
    "baseball": {
        "csv": "baseball.csv",
        "dir": "images/baseball",
        "prefix": "bb_",
        "hue": 18,          # 土のような橙
        "spread": 40,
        "ball": "baseball",
        "career": True,     # team列が「巨人-日本ハム」のような球団変遷の文字列
        "label": lambda row: "プロ野球選手",
        # 減量版に敷く職業シルエット。baseball は区分の列が無いので全員打者
        "sil": lambda row: "baseball_batter",
    },
    "football": {
        "csv": "football.csv",
        "dir": "images/football",
        "prefix": "fb_",
        "hue": 150,         # 芝のような緑
        "spread": 60,
        "ball": "football",
        "career": False,    # team列は単一のクラブ名(`横浜F・マリノス` など)
        "label": lambda row: {
            "manager": "サッカー監督",
            "mascot": "クラブマスコット",
        }.get(row.get("category", ""), "サッカー選手"),
        "sil": lambda row: {
            "manager": "manager",
            "mascot": "mascot",
        }.get(row.get("category", ""), "football_player"),
    },
}


def team_names(team: str, career: bool = False) -> list:
    """team列から「色を引く候補のチーム名」を先頭の所属ぶんだけ取り出す。

    baseball(`career=True`)の team は球団の変遷を連ねた文字列で、`-` が移籍、
    `・` が改称を表す(`巨人-日本ハム`, `大洋・横浜`, `西鉄・太平洋・クラウン-阪神`)。
    色は**最初の所属**から取るので、先頭の `-` 区切り要素だけを見て、その中の
    改称名を古い順に返す。

    football の team は単一のクラブ名で、`横浜F・マリノス` のように `・` を
    含む名前があるため**区切り文字として扱ってはいけない**。そのまま1件返す。
    """
    if not team:
        return []
    if not career:
        return [team]
    first = team.split("-")[0]
    return [p for p in (x.strip() for x in first.split("・")) if p]


def team_label(team: str, career: bool = False) -> str:
    """カードに描く所属チーム名。移籍がある場合は「ほか」を付ける。"""
    if not team:
        return ""
    head = team
    if career:
        parts = team.split("-")
        head = parts[0]
        if len(parts) > 1:
            head += "ほか"
    if text_width(head, 1.0) > TEAM_MAX:
        while head and text_width(head + "…", 1.0) > TEAM_MAX:
            head = head[:-1]
        head += "…"
    return head


def asset_key(name: str) -> str:
    """名前から決定的に導く10桁のキー。id には依存しない。"""
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]


def asset_name(cfg: dict, name: str) -> str:
    return f"{cfg['prefix']}{asset_key(name)}.svg"


def image_url(cfg: dict, name: str) -> str:
    return f"{RAW_BASE}/{cfg['dir']}/{asset_name(cfg, name)}"


def image_page_url(cfg: dict, name: str) -> str:
    return f"{BLOB_BASE}/{cfg['dir']}/{asset_name(cfg, name)}"


def url_prefix(cfg: dict) -> str:
    """生成カードのURLの接頭辞(実写かどうかの判定に使う)。"""
    return f"{RAW_BASE}/{cfg['dir']}/"


# --- 配色 --------------------------------------------------------------------

ACHROMATIC = 0.06   # chroma がこれ未満なら白・黒・灰(色相に意味が無い)
LIGHT_BAND = 0.62   # 帯の明るさがこれを超えたら、帯の上の文字を濃色に切り替える


def hsl(h: float, s: float, lum: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, lum, s)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def parse_hex(value: str):
    """`#rgb` / `#rrggbb` -> (色相[度], 彩度, 明度, 鮮やかさ)。読めなければ None。

    4つ目の「鮮やかさ」は RGB の最大-最小(chroma)。HLSの彩度は淡い水色でも
    1.0 になるので、「どちらの色が主役向きか」の比較にはこちらを使う。
    """
    v = (value or "").strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        return None
    try:
        r, g, b = (int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return None
    h, lum, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s, lum, max(r, g, b) - min(r, g, b)


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def perceived(h: float, s: float, lum: float) -> float:
    """人の目に見える明るさ(0..1)。帯の上に白と濃色のどちらを置くかの判定用。"""
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, lum, s)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _hex(parsed) -> str:
    h, s, lum, _chroma = parsed
    return hsl(h, s, lum)


def fallback_hue(cfg: dict, team: str) -> float:
    """チームカラーが分からないときの色相。チーム名から決定的に決める。"""
    names = team_names(team, cfg["career"])
    if not names:
        return cfg["hue"]
    seed = int(hashlib.sha1(names[0].encode("utf-8")).hexdigest()[:8], 16)
    return cfg["hue"] + seed % (cfg["spread"] * 2 + 1) - cfg["spread"]


def palette(cfg: dict, team: str, color: dict | None = None) -> dict:
    """カードの配色を決める(youtuber の象徴カードと同じ方針)。

    `color` にチームカラー(`{"primary": "#rrggbb", "secondary": ...}`)があれば
    それを使う。**出典に書かれている順をそのまま使い**、主色を帯に、副色を帯下の
    ラインに回す(阪神なら黄の帯に黒のライン、FC東京なら紺の帯に赤のライン)。
    鮮やかさで並べ替えたりはしない。Wikipediaのインフォボックスはチームカラーを
    公式の順で並べており、鮮やかな方が主色とは限らないため(FC東京の紺×赤、
    ヤクルトの紺×赤は、鮮やかな赤を主色にすると別のチームに見えてしまう)。

    帯の色は**色相・彩度をほぼそのまま残す**。淡い色を暗く沈めるとチームカラーの
    意味が消えるので、代わりに帯の上の文字を白/濃色に切り替える(`light`)。
    """
    given = [c for c in (parse_hex((color or {}).get("primary", "")),
                         parse_hex((color or {}).get("secondary", "")))
             if c is not None]
    line = _hex(given[1]) if len(given) > 1 else ""

    if given:
        h, s, lum, chroma = given[0]
        s = 0.0 if chroma < ACHROMATIC else clamp(s, 0.25, 0.85)
        lum = clamp(lum, 0.30, 0.86)     # 真っ黒/真っ白だけは寄せる
    else:
        h, s, lum = fallback_hue(cfg, team), 0.50, 0.40
    light = perceived(h, s, lum) > LIGHT_BAND
    # 頭文字ディスクは帯と明暗を逆にする。淡い色をディスクに使うときだけ
    # 副色の色相を借りる(濃いディスクを副色の色相で塗ると、副色が白のときに
    # 無関係な灰色の丸になってしまう)
    hd, sd = (given[1][0], given[1][1]) if len(given) > 1 else (h, s)
    if len(given) > 1 and given[1][3] < ACHROMATIC:
        sd = 0.0
    dark_ink = hsl(h, min(s, 0.45), 0.22)
    if light:
        disc, mark = hsl(h, min(s, 0.55), 0.30), hsl(h, min(s, 0.25), 0.95)
    else:
        disc, mark = hsl(hd, clamp(sd, 0.0, 0.46), 0.94), hsl(h, s, 0.40)
    return {
        "light": light,
        "bg": hsl(h, min(s, 0.42), 0.965),
        "accent": hsl(h, s, lum),
        "band": line,
        "disc": disc,
        "mark": mark,
        "fg": dark_ink if light else "#ffffff",
        "chip_bg": dark_ink if light else "#ffffff",
        "chip_fg": "#ffffff" if light else hsl(h, s, min(lum, 0.42)),
        "ink": hsl(h, min(s, 0.30), 0.20),
        "edge": hsl(h, min(s, 0.25), 0.88),
    }


# --- 文字組み ----------------------------------------------------------------

def text_width(text: str, size: float) -> float:
    """描画幅の見積り。CJK・かなは1em、ASCIIは0.6em(多めに見る)。"""
    return sum(0.6 if ord(c) < 128 else 1.0 for c in text) * size


def fit_size(text: str, sizes, max_w: float) -> float:
    for s in sizes:
        if text_width(text, s) <= max_w:
            return s
    return sizes[-1]


def wrap_two(text: str, size: float, max_w: float):
    """max_w に収まる2行へ分割する(行長が均等になる位置を選ぶ)。無理ならNone。"""
    best = None
    for cut in range(1, len(text)):
        head, tail = text[:cut], text[cut:]
        wh, wt = text_width(head, size), text_width(tail, size)
        if wh > max_w or wt > max_w:
            continue
        if best is None or abs(wh - wt) < best[0]:
            best = (abs(wh - wt), [head, tail])
    return best[1] if best else None


def layout_name(name: str):
    """(font_size, [(行テキスト, ベースラインy), ...]) を返す。"""
    for size in NAME_SIZES_1LINE:
        if text_width(name, size) <= NAME_MAX_W:
            return size, [(name, 163.0)]
    for size in NAME_SIZES_2LINE:
        lines = wrap_two(name, size, NAME_MAX_W)
        if lines:
            step = size * 1.3
            first = 168.0 - step
            return size, [(lines[0], first), (lines[1], first + step)]
    size = NAME_SIZES_2LINE[-1]
    half = len(name) // 2 or 1
    step = size * 1.3
    return size, [(name[:half], 168.0 - step), (name[half:], 168.0)]


def initials(name: str) -> str:
    """カードの中央に置く頭文字。ラテン文字名は2文字、それ以外は1文字。"""
    first = name[0]
    if first.isascii() and first.isalnum():
        return name[:2].upper()
    return first


# --- 自作の図形 --------------------------------------------------------------
#
# 実在のロゴ・エンブレム・マスコット・公式ピクトグラムは参照していない。
# 円と自分で書いたパスだけで組んだ、一般的な「人型」と「ボール」である。

# 抽象的な人型(頭 + 肩から上)。帯の右側に薄く敷く背景装飾
FIGURE = ('<circle cx="266" cy="48" r="20"/>'
          '<path d="M266 69c-27 0-48 18-52 43h104c-4-25-25-43-52-43Z"/>')

# 野球のボール: 円 + 縫い目の曲線2本(破線にすると縫い目に見える)
BALL_BASEBALL = ('<path stroke-dasharray="2 3" d="M284.5 165q-9 10 0 20'
                 'M297.5 165q9 10 0 20"/>')
# サッカーボール: 円 + 中央の正五角形 + そこから外へ伸びる線
BALL_FOOTBALL = (
    '<path d="M291 168.8 296.9 173.1 294.7 180 287.4 180 285.1 173.1Z'
    'M291 168.8V162.5M296.9 173.1 302.9 171.1M294.7 180 298.4 185.1'
    'M287.4 180 283.7 185.1M285.1 173.1 279.1 171.1"/>')


def ball_svg(kind: str, ink: str) -> str:
    """右下に置く競技のボール。線は ink(チームカラー由来の濃色)で描く。"""
    inner = BALL_BASEBALL if kind == "baseball" else BALL_FOOTBALL
    return (f'<g fill="none" stroke="{ink}" stroke-width="1.5">'
            f'<circle cx="291" cy="175" r="13" fill="#fff"/>'
            f"{inner}</g>")


# 帯(上半分)。上の2角だけ角丸にした自作パス。矩形+clipPath でも描けるが、
# 1万枚超あるのでclipPathぶんのバイト数を節約している
HERO_PATH = (f"M0 {HERO_H}V{RADIUS}a{RADIUS} {RADIUS} 0 0 1 {RADIUS}-{RADIUS}"
             f"h{W - RADIUS * 2}a{RADIUS} {RADIUS} 0 0 1 {RADIUS} {RADIUS}"
             f"v{HERO_H - RADIUS}Z")


def num(x: float) -> str:
    """SVGに書く数値(整数なら小数点を落とす)。"""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def build_card(cfg: dict, name: str, team: str, label: str,
               color: dict | None = None, minimal: bool = False,
               sil: str = "") -> str:
    """カードのSVGを組む。

    `minimal=True` は**文字情報を落とした減量版**(試作)。soramimic-video の
    `player_card` レイアウトが `{original}`(名前)と `{team}`(所属)を
    テキストで描くので、カードにも同じ文字が入っていると画面内で二重になる。
    残すのは
    「配色(チームカラー)+頭文字+職業シルエット+『イメージ』の札+
    競技のボール」だけで、名前・区分・所属チームは描かない。
    区分の文字を落とす代わりに、帯の左へ職業シルエット(`sil`)を薄く敷いて
    選手・監督・マスコットを見分けられるようにする。「イメージ」の札は実写と
    誤認されないための表示なので減量版でも必ず残す。
    """
    p = palette(cfg, team, color)
    mark = initials(name)
    mark_size = 34 if len(mark) > 1 else 40
    tlabel = team_label(team, cfg["career"])
    label_size = fit_size(label, (19, 18, 17, 16, 15), HEAD_MAX_W)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}">',
        f"<title>{escape(name)}のイメージ画像</title>",
        ("<desc>チームカラーの配色と頭文字、職業を表す人型のシルエットだけで"
         "描いたカードです。写真・ロゴは使っていません。</desc>" if minimal else
         "<desc>チームカラーの配色と文字だけで描いたカードです。"
         "写真・ロゴは使っていません。</desc>"),
        f'<g font-family="{FONT}">',
        f'<rect x="0" y="0" width="{W}" height="{H}" rx="{RADIUS}" '
        f'fill="{p["bg"]}"/>',
        # 帯はチームカラーのベタ塗り。グラデーションにすると1枚あたり200バイト
        # 増え、1万枚超では2MB以上効いてくるので使わない
        f'<path d="{HERO_PATH}" fill="{p["accent"]}"/>',
    ]
    if minimal:
        # 区分の文字の代わりに職業シルエット。帯の中に薄く敷く
        parts.append(silhouette_svg(sil or cfg["sil"]({}), p["fg"],
                                    *MIN_SIL_BOX))
    else:
        # 抽象的な人型。帯の中に薄く敷くだけなので文字の可読性を下げない
        parts.append(f'<g fill="{p["fg"]}" fill-opacity=".16">{FIGURE}</g>')
    if p["band"]:
        # 副色のライン。帯の下端に置くので、白のような淡い副色でもはっきり出る
        parts.append(f'<rect x="0" y="{HERO_H - 8}" width="{W}" height="8" '
                     f'fill="{p["band"]}"/>')
    if minimal:
        # 頭文字のディスクだけを帯の境目にまたがるように大きく置く。
        # ディスクは淡い色にも濃い色にもなるので、地(bg)のハローと
        # 主色のリングで、帯の上でも下地の上でも輪郭が消えないようにする
        mark_size = MIN_MARK_SIZES[1] if len(mark) > 1 else MIN_MARK_SIZES[0]
        parts += [
            f'<circle cx="{W / 2:g}" cy="{MIN_DISC_CY}" '
            f'r="{MIN_DISC_R + 5}" fill="{p["bg"]}"/>',
            f'<circle cx="{W / 2:g}" cy="{MIN_DISC_CY}" r="{MIN_DISC_R}" '
            f'fill="{p["disc"]}" stroke="{p["accent"]}" stroke-width="2.5"/>',
            f'<text x="{W / 2:g}" '
            f'y="{num(MIN_DISC_CY + mark_size * 0.36)}" '
            f'text-anchor="middle" font-size="{mark_size}" font-weight="700" '
            f'fill="{p["mark"]}">{escape(mark)}</text>',
        ]
    else:
        parts += [
            # 頭文字のディスク
            f'<circle cx="58" cy="60" r="36" fill="{p["disc"]}"/>',
            f'<text x="58" y="{num(60 + mark_size * 0.36)}" '
            f'text-anchor="middle" font-size="{mark_size}" font-weight="700" '
            f'fill="{p["mark"]}">{escape(mark)}</text>',
            # 区分と所属。帯が淡い色のときは白ではなく濃色で書く
            f'<text x="108" y="56" font-size="{label_size:g}" '
            f'font-weight="700" fill="{p["fg"]}">{escape(label)}</text>',
        ]
        if tlabel:
            parts.append(
                f'<text x="108" y="80" font-size="13" fill="{p["fg"]}">'
                f'{escape(tlabel)}</text>')
    # 実写と誤認されないための札。減量版でも必ず残す
    parts += [
        f'<rect x="240" y="10" width="70" height="22" rx="11" '
        f'fill="{p["chip_bg"]}"/>',
        f'<text x="275" y="26" text-anchor="middle" font-size="13" '
        f'font-weight="600" fill="{p["chip_fg"]}">イメージ</text>',
        ball_svg(cfg["ball"], p["ink"]),
    ]
    if not minimal:
        size, lines = layout_name(name)
        for line, y in lines:
            parts.append(
                f'<text x="{W / 2:g}" y="{num(y)}" text-anchor="middle" '
                f'font-size="{size}" font-weight="700" fill="{p["ink"]}">'
                f"{escape(line)}</text>")
    parts.append(
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" '
        f'rx="{RADIUS - 0.5}" fill="none" stroke="{p["edge"]}"/>')
    parts.append("</g></svg>")
    return "".join(parts) + "\n"


# --- 入出力 ------------------------------------------------------------------

def load_people(cfg: dict) -> tuple:
    """(カード対象の人リスト, 実写がある人数) を返す。

    カードは**実写が無い人だけ**に作る。実写がある人まで作ると、使われない
    SVGが数千枚リポジトリに残る。実写の有無は行ではなく人(original)単位で
    見る(同じ人の full/family/given 行は必ず同じ画像を持つ)。
    """
    prefix = url_prefix(cfg)
    rows_by_name = {}
    order = []
    with (ROOT / cfg["csv"]).open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            name = r["original"]
            if name not in rows_by_name:
                rows_by_name[name] = r
                order.append(name)
            # 実写(=生成カード以外のURL)が1行でもあれば、その人は対象外
            img = r.get("image", "")
            if img and not img.startswith(prefix):
                rows_by_name[name] = None
    out = [(n, rows_by_name[n].get("team", ""), cfg["label"](rows_by_name[n]),
            cfg["sil"](rows_by_name[n]))
           for n in order if rows_by_name[n] is not None]
    return out, len(order) - len(out)


def load_colors(key: str) -> dict:
    """`tools/team_colors.json` の該当リストぶん。無ければ空。"""
    if not COLORS_PATH.exists():
        return {}
    data = json.loads(COLORS_PATH.read_text(encoding="utf-8"))
    return data.get("teams", {}).get(key, {})


def team_color(cfg: dict, colors: dict, team: str):
    """先頭の所属チームのうち、色が分かる最初のものを返す。無ければ None。"""
    for name in team_names(team, cfg["career"]):
        c = colors.get(name)
        if c and c.get("primary"):
            return c
    return None


def run(key: str, apply: bool, prune: bool, minimal: bool = False) -> int:
    cfg = LISTS[key]
    people, n_photo = load_people(cfg)
    colors = load_colors(key)
    out_dir = ROOT / cfg["dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    wanted = set()
    n_color = 0
    for name, team, label, sil in people:
        color = team_color(cfg, colors, team)
        if color:
            n_color += 1
        path = out_dir / asset_name(cfg, name)
        path.write_text(
            build_card(cfg, name, team, label, color, minimal, sil),
            encoding="utf-8")
        wanted.add(path.name)
    if len(wanted) != len(people):
        print(f"error: {key}: アセット名が衝突している", file=sys.stderr)
        return 1
    print(f"{key}: {len(people)}枚を生成 -> {cfg['dir']} "
          f"(チームカラーあり {n_color}人 / ハッシュ由来 "
          f"{len(people) - n_color}人 / 実写があるのでカード不要 {n_photo}人)")

    stale = sorted(p for p in out_dir.glob(f"{cfg['prefix']}*.svg")
                   if p.name not in wanted)
    if stale:
        if prune:
            for p in stale:
                p.unlink()
            print(f"  参照されなくなったSVGを削除: {len(stale)}枚")
        else:
            print(f"  注意: CSVから参照されないSVGが {len(stale)}枚ある "
                  f"(--prune で削除)")

    if not apply:
        return 0

    csv_path = ROOT / cfg["csv"]
    with csv_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [dict(r) for r in reader]
        cols = list(reader.fieldnames)
    for c in ("image", "image_page"):
        if c not in cols:
            cols.append(c)
    prefix = url_prefix(cfg)
    filled = rebound = photo = 0
    for r in rows:
        for c in cols:
            r.setdefault(c, "")
        cur = r["image"]
        if cur and not cur.startswith(prefix):
            photo += 1
            continue          # 実写がある行は絶対に触らない
        url = image_url(cfg, r["original"])
        if cur == url:
            continue          # 既に同じカード(冪等)
        if cur:
            rebound += 1      # 名前が変わった等でファイル名がずれた場合の貼り替え
        else:
            filled += 1
        r["image"], r["image_page"] = url, image_page_url(cfg, r["original"])

    write_csv_no_trailing_newline(csv_path, cols, rows)
    print(f"  {cfg['csv']}: カードを付与 +{filled}行, 貼り替え {rebound}行, "
          f"実写あり {photo}行")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", choices=sorted(LISTS), action="append",
                    help="対象のリスト(既定は両方)")
    ap.add_argument("--no-apply", action="store_true",
                    help="CSVのimage/image_pageを書き換えない(生成のみ)")
    ap.add_argument("--prune", action="store_true",
                    help="CSVから参照されなくなったSVGを削除する")
    ap.add_argument("--style", choices=("full", "minimal"), default="full",
                    help="minimal は名前・区分・所属の文字を描かない減量版")
    args = ap.parse_args()
    for key in (args.list or sorted(LISTS)):
        rc = run(key, not args.no_apply, args.prune, args.style == "minimal")
        if rc:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
