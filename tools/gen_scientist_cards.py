#!/usr/bin/env python3
"""scientist.csv の実写が無い行に割り当てる「象徴カード」SVGを生成する。

科学者は自由ライセンスの肖像が Commons にある人が多いが、それでも289人
(6,450行のうち556行)は画像が空のままだった。ソラミミ動画は単語ごとに
1枚絵を出すので、画像が無い行だけ他のリストと同じ見せ方ができない。

youtuber の象徴カード(ADR 00018)・baseball/football の選手カード
(ADR 00020)と同じ考え方で、**肖像画・肖像写真を一切借りずに、配色と
頭文字と汎用の図形だけで**描いたカードを割り当てる。

- 1人1枚。同じ人物の複数行(family/full)は同じ `original` なので同じ
  カードを共有する
- ファイル名は名前から決定的に導出する: `sc_<sha1(original)の先頭10桁>.svg`。
  id は将来の再採番に耐えないので使わない
- 配色は**分野**(`field` 列)。物理・化学・数学・天文学・生物学・
  計算機科学・地学の7分野に固有の色を割り当てる。`物理/数学` のような
  スラッシュ多値は**先頭を主分野**として帯の色に使い、2つめの分野の色を
  帯下のラインに回す(兼ねている分野があることが色で分かる)
- 中央に名前の頭文字だけを大きく置く。**名前・分野・国の文字は描かない**。
  soramimic-video の `scientist_card` レイアウトが名前・分野・業績を
  テキストで描くので、カードにも入れると画面内で二重になるため
  (詳細は ADR 00024)。頭文字は姓(`type=family` の行の `surface`)から
  取る。「チャールズ・キッテル」は「チ」より「キ」の方が人物の手がかりに
  なるため
- 文字で書かない分野の代わりに、**分野のアイコン**をカードの地紋
  (ウォーターマーク)として敷く。アイコンは Material Symbols
  (Apache License 2.0)で、同じ分野の人が何十人も並ぶので、分野ごとに
  用意した6個の図と反転・回転・拡縮・上下のゆらぎを**人物IDのハッシュ**で
  決定的に散らす(帰属は `<desc>` とリポジトリのLICENSE/README。
  詳細は ADR 00024, 00025)
- 実写と誤認されないよう右上に「イメージ」の札を必ず入れる
- ノーベル賞受賞者(`nobel=yes`)だけ右下に**自作の星**を置く。ノーベル財団の
  メダルの意匠・エンブレム・名称は使っていない、ただの5芒星である
- 自己完結SVG(外部フォント・画像を参照しない)。viewBox は 320x200 固定で、
  ほかの生成カードと同じ
- **生成物はリポジトリ内(`images/scientist/`)に置き**、CSVからは raw URL で
  参照する(youtuber/baseball/football と同じ。詳細は ADR 00025)

usage:
  # 生成してCSVのimage/image_pageを埋める(実写のある行は触らない)
  python3 tools/gen_scientist_cards.py

  # 生成だけ(CSVを書き換えない)
  python3 tools/gen_scientist_cards.py --no-apply

  # CSVから参照されなくなったSVGを消す
  python3 tools/gen_scientist_cards.py --prune
"""

import argparse
import colorsys
import csv
import hashlib
import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from silhouettes import ATTRIBUTION, silhouette_card_svg  # noqa: E402
from wpnames import write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "scientist.csv"
REL_DIR = "images/scientist"
OUT_DIR = ROOT / REL_DIR
PREFIX = "sc_"

RAW_BASE = "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/main"
BLOB_BASE = "https://github.com/soramimic/soramimic-wordlists/blob/main"
# 生成カードのURLはこの接頭辞で始まる(実写かどうかの判定に使う)
URL_PREFIX = f"{RAW_BASE}/{REL_DIR}/"

W, H = 320, 200
HERO_H = 112
RADIUS = 16
FONT = "'Hiragino Sans','Noto Sans JP','Yu Gothic',sans-serif"

# 頭文字ディスク。帯(y=112)の境目にまたがる位置に置くと、上下どちらの領域にも
# 属さない「記号」として読める
DISC_CY = 100
DISC_R = 48
MARK_SIZES = (56, 44)   # (1文字, 2文字)
# 分野アイコンの配置(silhouettes.SIL_PLACEMENTS のキー)
SIL_STYLE = "water"

# 分野 -> 帯の色(色相・彩度・明度)と地紋のアイコン。
#
# **選手カードのチームカラーと違って、この色に出典は無い**。分野に公式の色は
# 存在しないので、7分野が並んだときに互いに見分けられることだけを狙って
# 決めている(物理=青、化学=橙、数学=紫、天文学=夜空の濃紺、生物学=緑、
# 計算機科学=青緑、地学=土の茶)。色は分類の手がかりであって、学問分野を
# 表す標準的な配色ではない。
FIELD_STYLE = {
    "物理": {"hue": 218, "sat": 0.55, "lum": 0.42, "sil": "field_physics"},
    "化学": {"hue": 28, "sat": 0.72, "lum": 0.46, "sil": "field_chemistry"},
    "数学": {"hue": 282, "sat": 0.42, "lum": 0.44, "sil": "field_math"},
    "天文学": {"hue": 248, "sat": 0.50, "lum": 0.32, "sil": "field_astronomy"},
    "生物学": {"hue": 140, "sat": 0.48, "lum": 0.34, "sil": "field_biology"},
    "計算機科学": {"hue": 174, "sat": 0.60, "lum": 0.30, "sil": "field_cs"},
    "地学": {"hue": 24, "sat": 0.34, "lum": 0.30, "sil": "field_earth"},
}
# field が空・`NA`・未知の分野のときの見た目。地紋は敷かない(嘘の分野を
# 描くくらいなら何も描かない方がよい)
DEFAULT_STYLE = {"hue": 205, "sat": 0.18, "lum": 0.38, "sil": ""}

LIGHT_BAND = 0.62   # 帯の明るさがこれを超えたら、帯の上の文字を濃色に切り替える


def asset_key(name: str) -> str:
    """名前から決定的に導く10桁のキー。id には依存しない。"""
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]


def asset_name(name: str) -> str:
    return f"{PREFIX}{asset_key(name)}.svg"


def image_url(name: str) -> str:
    return f"{URL_PREFIX}{asset_name(name)}"


def image_page_url(name: str) -> str:
    return f"{BLOB_BASE}/{REL_DIR}/{asset_name(name)}"


# --- 配色 --------------------------------------------------------------------

def hsl(h: float, s: float, lum: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, lum, s)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def perceived(h: float, s: float, lum: float) -> float:
    """人の目に見える明るさ(0..1)。帯の上に白と濃色のどちらを置くかの判定用。"""
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, lum, s)
    return 0.299 * r + 0.587 * g + 0.114 * b


def fields(field: str) -> list:
    """`物理/数学` のような多値を分野のリストにする(先頭が主分野)。"""
    return [p for p in (x.strip() for x in (field or "").split("/")) if p]


def style_of(field: str) -> dict:
    return FIELD_STYLE.get(field, DEFAULT_STYLE)


def palette(field: str) -> dict:
    """カードの配色を決める(youtuber/選手カードと同じ組み立て)。

    主分野の色を帯に、2つめの分野の色を帯下のラインに回す。3つめ以降は
    描かない(細い帯を3本引いても読み取れないので、兼任は「もう1分野ある」
    ことだけ示す)。
    """
    parts = fields(field)
    st = style_of(parts[0] if parts else "")
    h, s, lum = st["hue"], st["sat"], st["lum"]
    line = ""
    if len(parts) > 1:
        st2 = style_of(parts[1])
        line = hsl(st2["hue"], st2["sat"], min(st2["lum"] + 0.18, 0.86))
    light = perceived(h, s, lum) > LIGHT_BAND
    dark_ink = hsl(h, min(s, 0.45), 0.22)
    if light:
        disc, mark = hsl(h, min(s, 0.55), 0.30), hsl(h, min(s, 0.25), 0.95)
    else:
        disc, mark = hsl(h, min(s, 0.46), 0.94), hsl(h, s, 0.40)
    return {
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
        "sil": st["sil"],
    }


# --- 頭文字 ------------------------------------------------------------------

def initials(name: str) -> str:
    """カードの中央に置く頭文字。ラテン文字名は2文字、それ以外は1文字。"""
    first = name[0]
    if first.isascii() and first.isalnum():
        return name[:2].upper()
    return first


# --- 自作の図形 --------------------------------------------------------------

def star_path(cx: float, cy: float, outer: float, inner: float) -> str:
    """5芒星のパス。ノーベル賞受賞者の印に使う。

    **ノーベル財団のメダルの意匠・エンブレム・名称は使っていない。**
    半径の比だけで作図した、ごく一般的な星形である。
    """
    pts = []
    for i in range(10):
        r = outer if i % 2 == 0 else inner
        t = math.radians(-90 + 36 * i)
        pts.append(f"{cx + r * math.cos(t):.1f} {cy + r * math.sin(t):.1f}")
    return "M" + "L".join(pts) + "Z"


def nobel_svg(ink: str) -> str:
    """右下に置くノーベル賞の印(白丸の中の星)。"""
    return (f'<g stroke="{ink}" stroke-width="1.5">'
            f'<circle cx="291" cy="175" r="13" fill="#fff"/>'
            f'<path d="{star_path(291, 175, 8.6, 3.6)}" fill="{ink}" '
            f'stroke="none"/></g>')


# 帯(上半分)。上の2角だけ角丸にした自作パス
HERO_PATH = (f"M0 {HERO_H}V{RADIUS}a{RADIUS} {RADIUS} 0 0 1 {RADIUS}-{RADIUS}"
             f"h{W - RADIUS * 2}a{RADIUS} {RADIUS} 0 0 1 {RADIUS} {RADIUS}"
             f"v{HERO_H - RADIUS}Z")


def num(x: float) -> str:
    """SVGに書く数値(整数なら小数点を落とす)。"""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def build_card(name: str, field: str, mark_name: str = "",
               nobel: str = "", sil_style: str = SIL_STYLE) -> str:
    """カードのSVGを組む。

    描くのは「分野の配色 + 頭文字 + 分野アイコン + 『イメージ』の札
    (+ノーベル賞なら星)」だけで、**名前・分野・国の文字は描かない**
    (詳細は ADR 00024)。
    """
    p = palette(field)
    key = asset_key(name)
    mark = initials(mark_name or name)
    mark_size = MARK_SIZES[1] if len(mark) > 1 else MARK_SIZES[0]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}">',
        f"<title>{escape(name)}のイメージ画像</title>",
        "<desc>研究分野の配色と頭文字、分野を表すアイコンだけで描いた"
        "カードです。写真・肖像画は使っていません。"
        f"{ATTRIBUTION}</desc>",
        f'<g font-family="{FONT}">',
        f'<rect x="0" y="0" width="{W}" height="{H}" rx="{RADIUS}" '
        f'fill="{p["bg"]}"/>',
        f'<path d="{HERO_PATH}" fill="{p["accent"]}"/>',
    ]
    if p["sil"]:
        parts.append(silhouette_card_svg(p["sil"], p["fg"], p["accent"],
                                         HERO_H, W, H, sil_style, key))
    if p["band"]:
        # 2つめの分野のライン。帯の下端に置くので淡い色でもはっきり出る
        parts.append(f'<rect x="0" y="{HERO_H - 8}" width="{W}" height="8" '
                     f'fill="{p["band"]}"/>')
    parts += [
        f'<circle cx="{W / 2:g}" cy="{DISC_CY}" '
        f'r="{DISC_R + 5}" fill="{p["bg"]}"/>',
        f'<circle cx="{W / 2:g}" cy="{DISC_CY}" r="{DISC_R}" '
        f'fill="{p["disc"]}" stroke="{p["accent"]}" stroke-width="2.5"/>',
        f'<text x="{W / 2:g}" y="{num(DISC_CY + mark_size * 0.36)}" '
        f'text-anchor="middle" font-size="{mark_size}" font-weight="700" '
        f'fill="{p["mark"]}">{escape(mark)}</text>',
        # 実写と誤認されないための札
        f'<rect x="240" y="10" width="70" height="22" rx="11" '
        f'fill="{p["chip_bg"]}"/>',
        f'<text x="275" y="26" text-anchor="middle" font-size="13" '
        f'font-weight="600" fill="{p["chip_fg"]}">イメージ</text>',
    ]
    if nobel == "yes":
        parts.append(nobel_svg(p["ink"]))
    parts.append(
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" '
        f'rx="{RADIUS - 0.5}" fill="none" stroke="{p["edge"]}"/>')
    parts.append("</g></svg>")
    return "".join(parts) + "\n"


# --- 入出力 ------------------------------------------------------------------

def load_people() -> tuple:
    """(カード対象の人リスト, 実写がある人数) を返す。

    カードは**実写が無い人だけ**に作る。実写の有無は行ではなく人
    (`original`)単位で見る(同じ人の family/full 行は必ず同じ画像を持つ)。
    頭文字に使う姓は `type=family` の行の `surface` から取る。
    """
    rows_by_name = {}
    surname = {}
    order = []
    with CSV_PATH.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            name = r["original"]
            if name not in rows_by_name:
                rows_by_name[name] = r
                order.append(name)
            if r.get("type") == "family" and r.get("surface"):
                surname.setdefault(name, r["surface"])
            # 実写(=生成カード以外のURL)が1行でもあれば、その人は対象外
            img = r.get("image", "")
            if img and not img.startswith(URL_PREFIX):
                rows_by_name[name] = None
    out = [(n, rows_by_name[n].get("field", ""), surname.get(n, n),
            rows_by_name[n].get("nobel", ""))
           for n in order if rows_by_name[n] is not None]
    return out, len(order) - len(out)


def run(apply: bool, prune: bool) -> int:
    people, n_photo = load_people()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    wanted = set()
    n_known = 0
    for name, field, surface, nobel in people:
        if fields(field) and fields(field)[0] in FIELD_STYLE:
            n_known += 1
        path = OUT_DIR / asset_name(name)
        path.write_text(build_card(name, field, surface, nobel),
                        encoding="utf-8")
        wanted.add(path.name)
    if len(wanted) != len(people):
        print("error: アセット名が衝突している", file=sys.stderr)
        return 1
    print(f"scientist: {len(people)}枚を生成 -> {REL_DIR} "
          f"(分野が分かる {n_known}人 / 既定の配色 {len(people) - n_known}人 / "
          f"実写があるのでカード不要 {n_photo}人)")

    stale = sorted(p for p in OUT_DIR.glob(f"{PREFIX}*.svg")
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

    with CSV_PATH.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [dict(r) for r in reader]
        cols = list(reader.fieldnames)
    for c in ("image", "image_page"):
        if c not in cols:
            cols.append(c)
    filled = rebound = photo = 0
    for r in rows:
        for c in cols:
            r.setdefault(c, "")
        cur = r["image"]
        if cur and not cur.startswith(URL_PREFIX):
            photo += 1
            continue          # 実写がある行は絶対に触らない
        url = image_url(r["original"])
        if cur == url:
            continue          # 既に同じカード(冪等)
        if cur:
            rebound += 1      # 名前が変わった等でファイル名がずれた場合の貼り替え
        else:
            filled += 1
        r["image"], r["image_page"] = url, image_page_url(r["original"])

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    print(f"  scientist.csv: カードを付与 +{filled}行, 貼り替え {rebound}行, "
          f"実写あり {photo}行")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-apply", action="store_true",
                    help="CSVのimage/image_pageを書き換えない(生成のみ)")
    ap.add_argument("--prune", action="store_true",
                    help="CSVから参照されなくなったSVGを削除する")
    args = ap.parse_args()
    return run(not args.no_apply, args.prune)


if __name__ == "__main__":
    raise SystemExit(main())
