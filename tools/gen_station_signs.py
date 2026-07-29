#!/usr/bin/env python3
"""stations.csv の写真が無い行に割り当てる「駅名標」SVGを生成する。

駅の写真は Commons によく揃っているが、それでも160駅(9,467行のうち160行)は
画像が空のままだった。ソラミミ動画は単語ごとに1枚絵を出すので、画像が無い
行だけ他のリストと同じ見せ方ができない。

そこで、**どの鉄道会社のものでもない汎用の駅名標**を描いて割り当てる。

- 1行1枚。同じ駅名でも会社が違えば別の駅なので(神戸三宮は阪急と阪神で
  2行ある)、人物リストのように名前で共有はしない
- ファイル名は行の同定情報から決定的に導出する:
  `st_<sha1(キー)の先頭10桁>.svg`。キーは Wikidata QID(あれば)、無ければ
  駅名・都道府県・市区町村・路線をつないだ文字列。id は将来の再採番に
  耐えないので使わない
- **実在の鉄道会社の意匠は使わない。** ロゴ・社章・路線記号(ナンバリングの
  丸)・専用書体・ラインカラーの再現はしない。白地の板に駅名とかな読みを
  置き、上下に帯を敷いた、どこの会社のものでもない看板を描く
- **帯の色は路線名のハッシュから決める。** このリポジトリは路線の実カラーを
  持っておらず、推測で塗ると実在のラインカラーの再現になってしまうため。
  同じ路線の駅が同じ色になる以上の意味は無い(路線名が空の行は都道府県、
  それも空なら駅名から振る)。詳細は ADR 00026
- 実写と誤認されないよう右上に「イメージ」の札を必ず入れる
- 駅名の文字は**看板に書かれているもの**なので、ADR 00024 の「カードに文字を
  描かない」の例外にする。駅名標は駅名が書かれていて初めて駅名標であり、
  実写の駅写真にも同じ文字が写っている。soramimic-video の `station_card`
  レイアウトは画像の外に駅名を描くので、画面内で重なることもない
- 自己完結SVG(外部フォント・画像を参照しない)。viewBox は 320x200 固定で、
  ほかの生成カードと同じ。Material Symbols は使っていないので、この画像に
  Apache License 2.0 の帰属義務は生じない
- **生成物はリポジトリ内(`images/station/`)に置き**、CSVからは raw URL で
  参照する(youtuber/baseball/football/scientist と同じ)

usage:
  # 生成してCSVのimage/image_pageを埋める(写真のある行は触らない)
  python3 tools/gen_station_signs.py

  # 生成だけ(CSVを書き換えない)
  python3 tools/gen_station_signs.py --no-apply

  # CSVから参照されなくなったSVGを消す
  python3 tools/gen_station_signs.py --prune
"""

import argparse
import colorsys
import csv
import hashlib
import sys
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "stations.csv"
REL_DIR = "images/station"
OUT_DIR = ROOT / REL_DIR
PREFIX = "st_"

RAW_BASE = "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/main"
BLOB_BASE = "https://github.com/soramimic/soramimic-wordlists/blob/main"
# 生成画像のURLはこの接頭辞で始まる(写真かどうかの判定に使う)
URL_PREFIX = f"{RAW_BASE}/{REL_DIR}/"

W, H = 320, 200
RADIUS = 16
FONT = "'Hiragino Sans','Noto Sans JP','Yu Gothic',sans-serif"

# 看板の板。上に帯、下に細い帯を敷く
BOARD = (16, 30, 288, 124)      # x, y, w, h
BOARD_R = 10
TOP_BAND_H = 16
BOTTOM_BAND_H = 12   # 角丸(BOARD_R)より低いと下端の帯のパスが破綻する
# 文字の大きさ(枠に収まるよう、長い名前は縮める)
NAME_MAX, NAME_MIN = 46, 10
KANA_MAX, KANA_MIN = 16, 7
NAME_BOX = 248                  # 駅名に使ってよい幅
KANA_BOX = 264

# 帯の彩度・明度。実在のラインカラーの再現ではないので、原色は避けて
# 落ち着いた範囲に固定し、色相だけをハッシュで振る
BAND_SAT, BAND_LUM = 0.40, 0.36


def hsl(h: float, s: float, lum: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, lum, s)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def row_key(row: dict) -> str:
    """行を一意に指す文字列。Wikidata QIDがあればそれ、無ければ同定情報。"""
    if row.get("wikidata"):
        return row["wikidata"]
    return "|".join(row.get(c, "") for c in
                    ("original", "prefecture", "city", "lines"))


def asset_key(row: dict) -> str:
    return hashlib.sha1(row_key(row).encode("utf-8")).hexdigest()[:10]


def asset_name(row: dict) -> str:
    return f"{PREFIX}{asset_key(row)}.svg"


def image_url(row: dict) -> str:
    return f"{URL_PREFIX}{asset_name(row)}"


def image_page_url(row: dict) -> str:
    return f"{BLOB_BASE}/{REL_DIR}/{asset_name(row)}"


def band_seed(row: dict) -> str:
    """帯の色を決める種。路線名(先頭)、無ければ都道府県、無ければ駅名。

    `lines` は `JR西日本 山陽新幹線／JR西日本 山陽本線` のように `／` 区切りの
    多値。先頭だけ使うので、乗り入れが増えても既存の駅の色は変わらない。
    """
    lines = row.get("lines", "")
    if lines:
        return lines.split("／")[0].strip()
    return row.get("prefecture", "") or row.get("original", "")


def palette(row: dict) -> dict:
    """看板の配色。色相だけを種のハッシュから振る(ADR 00026)。"""
    seed = int(hashlib.sha1(band_seed(row).encode("utf-8")).hexdigest()[:8], 16)
    h = seed % 360
    return {
        "bg": hsl(h, 0.20, 0.93),
        "band": hsl(h, BAND_SAT, BAND_LUM),
        "band_light": hsl(h, BAND_SAT, min(BAND_LUM + 0.30, 0.80)),
        "board": "#ffffff",
        "name": hsl(h, 0.10, 0.15),
        "kana": hsl(h, 0.10, 0.36),
        "post": hsl(h, 0.06, 0.60),
        "edge": hsl(h, 0.18, 0.86),
        "chip_bg": hsl(h, BAND_SAT, 0.22),
    }


def text_units(text: str) -> float:
    """文字列のおおよその幅(全角1文字=1)。フォントに依らない当たりを取る。

    cairosvg が使うフォントは環境によって違うので、正確な計測はできない。
    東アジアの文字は全角、それ以外は半角として**多めに**見積もり、
    はみ出しではなく小さめに出る側へ倒す。
    """
    total = 0.0
    for ch in text:
        total += 1.0 if unicodedata.east_asian_width(ch) in "WFA" else 0.55
    return total or 1.0


def fit_size(text: str, box: float, hi: float, lo: float) -> float:
    """`box` の幅に収まる文字サイズ。長い駅名は縮める。"""
    return round(max(lo, min(hi, box / text_units(text))), 1)


def num(x: float) -> str:
    """SVGに書く数値(整数なら小数点を落とす)。"""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def top_band_path() -> str:
    """板の上端の帯。上の2角だけ板と同じ角丸にする。"""
    x, y, w, _h = BOARD
    r = BOARD_R
    return (f"M{x} {y + TOP_BAND_H}V{y + r}a{r} {r} 0 0 1 {r}-{r}"
            f"h{w - r * 2}a{r} {r} 0 0 1 {r} {r}v{TOP_BAND_H - r}Z")


def bottom_band_path() -> str:
    """板の下端の帯。下の2角だけ板と同じ角丸にする。"""
    x, y, w, h = BOARD
    r = BOARD_R
    b = y + h
    return (f"M{x} {b - BOTTOM_BAND_H}h{w}v{BOTTOM_BAND_H - r}"
            f"a{r} {r} 0 0 1 -{r} {r}h-{w - r * 2}"
            f"a{r} {r} 0 0 1 -{r}-{r}Z")


def build_sign(name: str, kana: str, row: dict) -> str:
    """駅名標のSVGを組む。

    白地の板に駅名とかな読み、上下に帯。**実在の鉄道会社のロゴ・社章・
    路線記号・専用書体・ラインカラーは使っていない。**
    """
    p = palette(row)
    x, y, w, h = BOARD
    name_size = fit_size(name, NAME_BOX, NAME_MAX, NAME_MIN)
    kana_size = fit_size(kana, KANA_BOX, KANA_MAX, KANA_MIN)
    # 駅名は板の中央よりやや上、かなはその下に置く
    name_y = y + TOP_BAND_H + (h - TOP_BAND_H - BOTTOM_BAND_H) * 0.46 \
        + name_size * 0.36
    kana_y = y + h - BOTTOM_BAND_H - 16

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}">',
        f"<title>{escape(name)}駅のイメージ画像</title>",
        "<desc>駅名とかな読みを置いただけの、どの鉄道会社のものでもない"
        "駅名標のイメージです。写真ではなく、実在の社章・路線記号・"
        "ラインカラーも使っていません。帯の色は路線名から機械的に"
        "決めたものです。</desc>",
        f'<g font-family="{FONT}">',
        f'<rect x="0" y="0" width="{W}" height="{H}" rx="{RADIUS}" '
        f'fill="{p["bg"]}"/>',
        # 看板を支える柱(板の後ろに描くので、板の下端から下だけが見える)
        f'<g fill="{p["post"]}">'
        f'<rect x="94" y="{y + h - 8}" width="10" height="42" rx="3"/>'
        f'<rect x="216" y="{y + h - 8}" width="10" height="42" rx="3"/></g>',
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{BOARD_R}" '
        f'fill="{p["board"]}" stroke="{p["band"]}" stroke-width="2"/>',
        f'<path d="{top_band_path()}" fill="{p["band"]}"/>',
        f'<path d="{bottom_band_path()}" fill="{p["band_light"]}"/>',
        f'<text x="{W / 2:g}" y="{num(name_y)}" text-anchor="middle" '
        f'font-size="{num(name_size)}" font-weight="700" '
        f'fill="{p["name"]}">{escape(name)}</text>',
        f'<text x="{W / 2:g}" y="{num(kana_y)}" text-anchor="middle" '
        f'font-size="{num(kana_size)}" fill="{p["kana"]}">'
        f'{escape(kana)}</text>',
        # 実写と誤認されないための札
        f'<rect x="240" y="4" width="70" height="22" rx="11" '
        f'fill="{p["chip_bg"]}"/>',
        '<text x="275" y="20" text-anchor="middle" font-size="13" '
        'font-weight="600" fill="#ffffff">イメージ</text>',
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" '
        f'rx="{RADIUS - 0.5}" fill="none" stroke="{p["edge"]}"/>',
        "</g></svg>",
    ]
    return "".join(parts) + "\n"


# --- 入出力 ------------------------------------------------------------------

def load_rows() -> tuple:
    """(CSVの全行, 列名) を読む。"""
    with CSV_PATH.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [dict(r) for r in reader]
        cols = list(reader.fieldnames)
    return rows, cols


def run(apply: bool, prune: bool) -> int:
    rows, cols = load_rows()
    for c in ("image", "image_page"):
        if c not in cols:
            cols.append(c)
    # 写真(=生成画像以外のURL)がある行は対象外
    targets = [r for r in rows
               if not r.get("image") or r["image"].startswith(URL_PREFIX)]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    wanted = set()
    for r in targets:
        path = OUT_DIR / asset_name(r)
        path.write_text(build_sign(r["original"], r.get("pronunciation", ""), r),
                        encoding="utf-8")
        wanted.add(path.name)
    if len(wanted) != len(targets):
        print("error: アセット名が衝突している(行の同定情報が同じ行がある)",
              file=sys.stderr)
        return 1
    n_lines = sum(1 for r in targets if r.get("lines"))
    print(f"stations: {len(targets)}枚を生成 -> {REL_DIR} "
          f"(帯色の由来: 路線名 {n_lines}件 / 都道府県・駅名 "
          f"{len(targets) - n_lines}件 / 写真があるので不要 "
          f"{len(rows) - len(targets)}件)")

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

    filled = rebound = photo = 0
    for r in rows:
        for c in cols:
            r.setdefault(c, "")
        cur = r["image"]
        if cur and not cur.startswith(URL_PREFIX):
            photo += 1
            continue          # 写真がある行は絶対に触らない
        url = image_url(r)
        if cur == url:
            continue          # 既に同じ画像(冪等)
        if cur:
            rebound += 1      # 同定情報が変わってファイル名がずれた場合
        else:
            filled += 1
        r["image"], r["image_page"] = url, image_page_url(r)

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    print(f"  stations.csv: 駅名標を付与 +{filled}行, 貼り替え {rebound}行, "
          f"写真あり {photo}行")
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
