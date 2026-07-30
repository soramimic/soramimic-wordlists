#!/usr/bin/env python3
"""pokemon.csv から「型色カード」SVGを生成し、GitHub Releaseへアップロードする。

ポケモンのキャラクター造形は著作物なので画像として複製できない。代わりに
**タイプの配色と文字だけ**で1匹1枚のカードを描く(公式アセット・キャラクター
造形は一切使わない)。

意匠は「図鑑端末の画面」。生成り色の本体の上に黒いベゼル帯を敷き、左に赤・黄・
緑のLEDランプ、右端に monospace の図鑑番号を置く。その下、左半分がタイプ2色の
縦グラデーションで塗られた「画面」パネルで、中にモチーフのシルエットを白の透かし
として敷く。右半分は ぶんるい/たかさ/おもさ の3行のデータ表。最下部に名前と
タイプチップ、rarity があれば右にバッジを置く。右下のチップ脇の余白には、
表に出ていない事実として「初登場 <バージョン対>」と「<進化前>から進化」を
小さく2行で添える(進化前が無い行は1行)。

シルエットは**モチーフになった生物の汎用的な形**(ピカチュウならネズミ)であって
ポケモン自身の造形ではない。素材はPhyloPicのパブリックドメインのものだけ。

- 1 id につき1枚。同一idの表記ゆれ行(ライチュウ/アローラライチュウ/…)は
  同じカードを共有する
- **ファイル名は名前(original)から決定的に導出する**: `pkm_<sha1(original)の
  先頭10桁>.svg`。id はフォーム分が新種追加のたびに振り直される(ADR 00002)ので
  永続キーに使えない。名前をキーにすれば id がずれてもURLは同じカードを指し、
  「別のポケモンのカードが表示される」静かな誤表示が起きない。名前が変われば
  別ファイル名になり、未生成なら404になる(誤表示より安全)
- 図鑑番号は**その名前が指す種の全国図鑑No**を出す。フォーム(id≥種数)は
  括弧前の種名 / 「メガ」を外した名前から種を引いて、その種の番号を表示する
  (アローラライチュウ → 026)。引けなければ番号を出さない
- SVGは自己完結(外部フォント・画像を参照しない)。日本語を含むので
  font-family は sans-serif の汎用指定にしており、字形は環境依存
- GitHub Release は1リリースあたり1000アセットが上限なので、ハッシュの
  先頭バイトで RELEASE_BUCKETS 個のリリースへ振り分ける
  (`pokemon-typecard-v2` / `pokemon-typecard-v2b`)。振り分けも名前で決まるので
  既存カードのリリースが後から動くことはない

usage:
    # 生成のみ(既定の出力先は build/pokemon_typecards/)
    python3 tools/gen_pokemon_typecards.py --out build/pokemon_typecards

    # 生成してリリースへアップロード(gh CLIが必要。リリースは作成済みのこと)
    python3 tools/gen_pokemon_typecards.py --out build/pokemon_typecards \
        --upload

    # CSVの全 original に対応するアセットがReleaseに存在するか検査する
    python3 tools/gen_pokemon_typecards.py --verify

新ポケモン(新種・新フォーム)が追加されたら本スクリプトを再実行して
Release を更新する。ファイル名が名前由来なので**増えた分だけ**送ればよく
(`--upload --only-missing`)、既存カードの作り直しは不要。取りこぼしは
`--verify` で検出できる。
"""

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "pokemon.csv"
MOTIF_PATH = ROOT / "tools" / "pokemon_motifs.json"
SILHOUETTE_PATH = ROOT / "tools" / "motif_silhouettes.json"
SILHOUETTE_DIR = ROOT / "images" / "pokemon_motifs"

# Release のタグと画像URL(update_pokemon.py からも参照する)
IMAGE_TAG = "pokemon-typecard-v2"
RELEASE_BASE = "https://github.com/soramimic/soramimic-wordlists/releases"
# アセットを振り分けるリリースの数。1リリース1000アセットが上限なので、
# 総枚数が 1000*RELEASE_BUCKETS に近づいたら増やす(増やすと既存カードの
# 配置が変わるので、その際はタグを v3 に上げて全枚数を再アップロードする)
RELEASE_BUCKETS = 2

# タイプ配色(コミュニティ慣習の色。公式アセットではない)
TYPE_COLORS = {
    "ノーマル": "#9199a2",
    "ほのお": "#ff6b3d",
    "みず": "#3d9bff",
    "でんき": "#f4c62a",
    "くさ": "#4fbe5c",
    "こおり": "#5fd3d3",
    "かくとう": "#d8492f",
    "どく": "#a45cc4",
    "じめん": "#c9a227",
    "ひこう": "#8fa8e8",
    "エスパー": "#ff6f9c",
    "むし": "#93b525",
    "いわ": "#b0a06a",
    "ゴースト": "#6a5aa8",
    "ドラゴン": "#5b53d6",
    "あく": "#5a5049",
    "はがね": "#8fa3b0",
    "フェアリー": "#f099c8",
}
FALLBACK_COLOR = "#999999"

# 世代 -> 初登場のバージョン対。PokéAPIの version_names から引くと日本の初代が
# 「赤・青」(海外版の対)になってしまうため、日本の慣習に合わせてハードコードする。
# 各世代の代表的な2バージョン(対になるソフト)のみを載せる。
# **もとは update_pokemon.py にあったが、カード側でも初登場の表示に使うため
# こちらへ移した**(update_pokemon.py が本モジュールを import しているので、
# 逆向きに import すると循環参照になる)
GENERATION_VERSIONS = {
    "1": "赤・緑",
    "2": "金・銀",
    "3": "ルビー・サファイア",
    "4": "ダイヤモンド・パール",
    "5": "ブラック・ホワイト",
    "6": "X・Y",
    "7": "サン・ムーン",
    "8": "ソード・シールド",
    "9": "スカーレット・バイオレット",
}

# カード寸法(固定viewBox)。図鑑端末風レイアウトの座標はすべてこの 320x200 系
W, H = 320, 200
PAD = 14
RADIUS = 14
FONT = "'Hiragino Sans','Noto Sans JP','Yu Gothic',sans-serif"

# 端末の外装
BODY_BG = "#f2efe6"      # 生成り色の本体
BEZEL_H = 30             # 上部の黒いベゼル帯
BEZEL_BG = "#2f2c28"
INK = "#2f2c28"          # 本文の墨色
LABEL_INK = "#8a8478"    # データ表の小さいラベル
RULE_INK = "#ddd8c9"     # データ表の区切り線
BORDER_INK = "#d9d4c4"   # 外周の細枠

# 左の「画面」パネル(タイプ色の縦グラデーション)とその中のシルエット枠
SCREEN_BOX = (12, 38, 126, 94)  # x, y, w, h
SIL_BOX = (18, 44, 114, 82)     # 画面の内側に少し余白を残す
SIL_OPACITY = 0.42

# 右のデータ表。ラベルのベースラインを DATA_TOP から DATA_STEP 刻みで置き、
# 値はその 16 下、区切り線は 22 下
DATA_X = 150
DATA_W = 156             # DATA_X + DATA_W == W - PAD
DATA_TOP = 50
DATA_STEP = 30
LABEL_FONT = 9.5
VALUE_SIZES = (14, 12.5, 11, 10)  # 値が DATA_W を超えるなら順に縮める

# 名前(1行で入らなければ2行に折り返す)
NAME_SIZES_1LINE = (21, 19, 17, 15, 13, 11.5)
NAME_SIZES_2LINE = (13, 11.5, 10)
NAME_BASE_1LINE = 161.0  # 1行のときのベースライン
NAME_BASE_2LINE = 165.0  # 2行のときの**2行目**のベースライン

# タイプチップ
CHIP_FONT = 12.0
CHIP_H = 21
CHIP_TOP = 172
CHIP_PAD = 10
CHIP_GAP = 6

# rarity バッジ(名前の右)。名前はこの幅ぶん狭めて重なりを避ける
BADGE_FONT = 10.5
BADGE_H = 18
BADGE_TOP = 143
BADGE_PAD = 8
BADGE_GAP = 10           # バッジと名前のあいだの最小の隙間

# 右下の小さな補足(初登場 / 進化元)。タイプチップの右の余白に右揃えで置く。
# データ表・rarityバッジ・名前・タイプチップと重ならないよう、
# ベースラインはチップ帯(CHIP_TOP〜)の中に収め、左端はチップの右端から取る
FACT_SIZES = (10.5, 10, 9.5)
FACT_BASE_LAST = 191.0   # 下の行(2行なら2行目)のベースライン
FACT_LINE_STEP = 12.5    # 行送り
FACT_GAP = 8             # タイプチップとのあいだの最小の隙間
FACT_MIN_W = 40          # これより狭ければ補足を出さない


def asset_key(name: str) -> str:
    """名前から決定的に導く10桁のキー。id には依存しない。"""
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]


def asset_name(name: str) -> str:
    return f"pkm_{asset_key(name)}.svg"


def release_tag(name: str) -> str:
    """名前が属するリリースのタグ。ハッシュ先頭バイトで振り分ける。"""
    bucket = int(asset_key(name)[:2], 16) * RELEASE_BUCKETS // 256
    return IMAGE_TAG if bucket == 0 else f"{IMAGE_TAG}{chr(ord('a') + bucket)}"


def image_url(name: str) -> str:
    return f"{RELEASE_BASE}/download/{release_tag(name)}/{asset_name(name)}"


def image_page_url(name: str) -> str:
    return f"{RELEASE_BASE}/tag/{release_tag(name)}"


def text_width(text: str, size: float) -> float:
    """描画幅の見積り。CJK・かなは1em、ASCIIは0.6em(多めに見る)。"""
    return sum(0.6 if ord(c) < 128 else 1.0 for c in text) * size


def wrap_two(text: str, size: float, max_w: float) -> list[str] | None:
    """max_w に収まる2行へ分割する(行長が均等になる位置を選ぶ)。無理ならNone。"""
    best: tuple[float, list[str]] | None = None
    for cut in range(1, len(text)):
        head, tail = text[:cut], text[cut:]
        wh, wt = text_width(head, size), text_width(tail, size)
        if wh > max_w or wt > max_w:
            continue
        if best is None or abs(wh - wt) < best[0]:
            best = (abs(wh - wt), [head, tail])
    return best[1] if best else None


def fit_size(text: str, max_w: float, sizes: tuple[float, ...]) -> float:
    """max_w に収まる最大の font-size を sizes から選ぶ。無理なら最小値。"""
    for size in sizes:
        if text_width(text, size) <= max_w:
            return size
    return sizes[-1]


def layout_name(name: str, max_w: float) -> tuple[float, list[tuple[str, float]]]:
    """(font_size, [(行テキスト, ベースラインy), ...]) を返す。

    max_w は名前に使える幅。rarity バッジがある行では狭くなる。
    「リザードン（キョダイマックスのすがた）」のような長い名前は縮小し、
    それでも入らなければ2行に折り返す(2行目の下端がタイプチップに触れない
    ように、2行目のベースラインを固定して上へ伸ばす)。
    """
    for size in NAME_SIZES_1LINE:
        if text_width(name, size) <= max_w:
            return size, [(name, NAME_BASE_1LINE)]
    for size in NAME_SIZES_2LINE:
        lines = wrap_two(name, size, max_w)
        if lines:
            step = size * 1.25
            return size, [(lines[0], NAME_BASE_2LINE - step),
                          (lines[1], NAME_BASE_2LINE)]
    # ここには来ない想定(最小サイズでも2行に割れない極端な名前)
    size = NAME_SIZES_2LINE[-1]
    half = len(name) // 2 or 1
    step = size * 1.25
    return size, [(name[:half], NAME_BASE_2LINE - step),
                  (name[half:], NAME_BASE_2LINE)]


def layout_facts(entry: "Entry", max_w: float) -> list[tuple[str, float, float]]:
    """右下の補足(初登場 / 進化元)を [(テキスト, ベースラインy, font-size)] で返す。

    max_w はタイプチップの右端から枠までの幅。入らないときは段階的に諦める:
    font-size を下げる(10.5→10→9.5) → 進化の行が無ければ「初登場」と版名を
    2行に分ける → 進化の行があって2行が埋まっているなら「初登場」を落として
    版名だけにする → それでも入らない行は出さない(枠からはみ出させない)。
    """
    if max_w < FACT_MIN_W:
        return []
    debut = GENERATION_VERSIONS.get(entry.generation, "")
    evo = [f"{entry.evolves_from}から進化"] if entry.evolves_from else []
    # 行の組み合わせの候補(上が優先)。「初登場 スカーレット・バイオレット」は
    # 幅の広いチップが2つ並ぶ行では最小サイズでも1行に入らないので、
    # 空いている行があれば2行に分け、無ければラベルを落とす
    layouts: list[list[str]] = []
    if debut:
        layouts.append([f"初登場 {debut}"] + evo)
        if not evo:
            layouts.append(["初登場", debut])
        layouts.append([debut] + evo)
    elif evo:
        layouts.append(evo)
    if not layouts:
        return []

    def place(texts: list[str], size: float) -> list[tuple[str, float, float]]:
        if len(texts) == 1:
            # 1行だけならチップ帯の中央あたりに置く
            return [(texts[0], FACT_BASE_LAST - FACT_LINE_STEP / 2, size)]
        return [
            (texts[0], FACT_BASE_LAST - FACT_LINE_STEP, size),
            (texts[1], FACT_BASE_LAST, size),
        ]

    # 上位の候補から順に試す。同じ候補内では縮小を先にする(情報を落とさない)
    for lines in layouts:
        for size in FACT_SIZES:
            if all(text_width(t, size) <= max_w for t in lines):
                return place(lines, size)
    # どの候補でも全行そろわない: 最小サイズで入る行だけ出す
    size = FACT_SIZES[-1]
    texts = [t for t in layouts[-1] if text_width(t, size) <= max_w]
    return place(texts, size) if texts else []


def chip_svg(label: str, color: str, x: float) -> tuple[str, float]:
    w = text_width(label, CHIP_FONT) + CHIP_PAD * 2
    baseline = CHIP_TOP + CHIP_H / 2 + CHIP_FONT * 0.36
    svg = (
        f'<rect x="{x:.1f}" y="{CHIP_TOP}" width="{w:.1f}" height="{CHIP_H}" '
        f'rx="{CHIP_H / 2}" fill="{color}"/>'
        f'<text x="{x + w / 2:.1f}" y="{baseline:.1f}" text-anchor="middle" '
        f'font-size="{CHIP_FONT}" font-weight="700" fill="#ffffff">'
        f"{escape(label)}</text>"
    )
    return svg, x + w + CHIP_GAP


def load_silhouettes() -> dict[str, str]:
    """モチーフラベル -> シルエットSVGの中身(path群)。

    シルエットは**モチーフの汎用的な形**(ピカチュウならネズミ)で、ポケモン自身の
    造形ではない。素材はPhyloPicのパブリックドメインのものと、PhyloPicに無い
    架空・非生物のモチーフ(ドラゴン等)についてはこのリポジトリ自作のCC0のもの
    (取得は tools/fetch_motif_silhouettes.py、出所は motif_silhouettes.json の
    `source`)。ファイルが無ければ空を返し、シルエット無しのカードになる。
    """
    if not SILHOUETTE_PATH.exists():
        return {}
    manifest = json.loads(SILHOUETTE_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for label, info in manifest.items():
        path = SILHOUETTE_DIR / info["file"]
        if path.exists():
            out[label] = path.read_text(encoding="utf-8")
    return out


def load_motifs() -> dict[int, str]:
    """全国図鑑No -> モチーフラベル。"""
    if not MOTIF_PATH.exists():
        return {}
    data = json.loads(MOTIF_PATH.read_text(encoding="utf-8"))
    return {int(dex): info["motif"] for dex, info in data.items()}


def silhouette_svg(svg: str) -> str | None:
    """シルエットSVGを SIL_BOX(左の画面パネルの内側)に収まる透かしにする。"""
    m = re.search(r'viewBox="([^"]+)"', svg)
    if not m:
        return None
    try:
        min_x, min_y, vw, vh = (float(v) for v in m.group(1).split())
    except ValueError:
        return None
    if vw <= 0 or vh <= 0:
        return None
    bx, by, bw, bh = SIL_BOX
    scale = min(bw / vw, bh / vh)
    # 枠の中央へ置く
    tx = bx + (bw - vw * scale) / 2 - min_x * scale
    ty = by + (bh - vh * scale) / 2 - min_y * scale
    body = svg[svg.index(">", svg.index("<svg")) + 1:svg.rindex("</svg>")]
    # 線だけで描かれた素材は stroke="currentColor" になっているので color も渡す
    return (f'<g transform="translate({tx:.1f} {ty:.1f}) scale({scale:.4f})" '
            f'fill="#ffffff" color="#ffffff" fill-opacity="{SIL_OPACITY}" '
            f'stroke-opacity="{SIL_OPACITY}">{body}</g>')


def build_card(entry: "Entry", silhouette: str | None = None) -> str:
    """1匹分の図鑑端末風カードSVGを組む。

    上からベゼル帯(LED+図鑑番号) / 左に画面パネル+シルエットの透かし・右に
    データ表 / 最下部に名前とタイプチップ(右にrarityバッジと初登場・進化の
    補足)、という3段構成。
    """
    name = entry.name
    c1 = TYPE_COLORS.get(entry.type1, FALLBACK_COLOR)
    c2 = TYPE_COLORS.get(entry.type2, c1) if entry.type2 else c1
    # 名前由来のキーをSVG内の要素idにも入れる。複数枚をHTMLへインライン展開しても
    # グラデーション定義やクリップパスが衝突しないようにするため
    key = asset_key(name)
    gid = f"pkmg{key}"
    cid = f"pkmc{key}"
    sx, sy, sw, sh = SCREEN_BOX

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" '
        f'aria-label="{escape(name)}">',
        "<defs>",
        # 画面パネルは上から type1 色 → type2 色の縦グラデーション
        # (単タイプなら同色2点なので単色べた塗りになる)
        f'<linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">',
        f'<stop offset="0" stop-color="{c1}"/>',
        f'<stop offset="1" stop-color="{c2}"/>',
        "</linearGradient>",
        f'<clipPath id="{cid}"><rect x="0" y="0" width="{W}" height="{H}" '
        f'rx="{RADIUS}"/></clipPath>',
        "</defs>",
        f'<g clip-path="url(#{cid})" font-family="{FONT}">',
        # 端末の本体
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="{BODY_BG}"/>',
        # 上部ベゼル帯(機械らしさを出す)
        f'<rect x="0" y="0" width="{W}" height="{BEZEL_H}" fill="{BEZEL_BG}"/>',
        # 左に赤・黄・緑のLEDランプ(赤だけ大きく、白いハイライトを乗せる)
        '<circle cx="17" cy="15" r="7" fill="#e8483c"/>'
        '<circle cx="14.5" cy="12.5" r="2.2" fill="#ffffff" '
        'fill-opacity="0.55"/>'
        '<circle cx="34" cy="15" r="3.2" fill="#f4c62a"/>'
        '<circle cx="45" cy="15" r="3.2" fill="#4fbe5c"/>',
    ]

    # 図鑑番号(ベゼルの右端)。実在する番号が分からない(種を引けないフォーム)
    # ときは出さない
    if entry.dex_no is not None:
        parts.append(
            f'<text x="{W - PAD}" y="20" text-anchor="end" '
            'font-family="monospace" font-size="14" font-weight="700" '
            f'fill="{BODY_BG}">No.{entry.dex_no:04d}</text>'
        )

    # 左: タイプ色の「画面」パネル
    parts.append(
        f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="8" '
        f'fill="url(#{gid})"/>'
    )
    # モチーフのシルエットを白の透かしとして画面に敷く。素材が無いポケモンは
    # 「データ未取得」の意で白い ? を出す
    if silhouette:
        parts.append(silhouette)
    else:
        parts.append(
            f'<text x="{sx + sw / 2:.1f}" y="{sy + sh / 2 + 11:.1f}" '
            'text-anchor="middle" font-size="30" font-weight="700" '
            'fill="#ffffff" fill-opacity="0.4">?</text>'
        )

    # 右: ぶんるい / たかさ / おもさ のデータ表
    rows = (
        ("ぶんるい", entry.genus or "―"),
        ("たかさ", f"{entry.height_m}m"),
        ("おもさ", f"{entry.weight_kg}kg"),
    )
    for i, (label, value) in enumerate(rows):
        y = DATA_TOP + DATA_STEP * i
        # 「りんごあめポケモン」のような長い値は表の幅に入るまで縮める
        vsize = fit_size(value, DATA_W, VALUE_SIZES)
        parts.append(
            f'<text x="{DATA_X}" y="{y}" font-size="{LABEL_FONT}" '
            f'fill="{LABEL_INK}" letter-spacing="0.5">{escape(label)}</text>'
            f'<text x="{DATA_X}" y="{y + 16}" font-size="{vsize}" '
            f'font-weight="700" fill="{INK}">{escape(value)}</text>'
            f'<rect x="{DATA_X}" y="{y + 22}" width="{DATA_W}" height="1" '
            f'fill="{RULE_INK}"/>'
        )

    # rarity バッジ(名前の右)。先に幅を決めて名前の使える幅から引く
    name_max_w = float(W - PAD * 2)
    if entry.rarity:
        bw = text_width(entry.rarity, BADGE_FONT) + BADGE_PAD * 2
        bx = W - PAD - bw
        parts.append(
            f'<rect x="{bx:.1f}" y="{BADGE_TOP}" width="{bw:.1f}" '
            f'height="{BADGE_H}" rx="4" fill="{BEZEL_BG}"/>'
            f'<text x="{bx + bw / 2:.1f}" '
            f'y="{BADGE_TOP + BADGE_H / 2 + BADGE_FONT * 0.36:.1f}" '
            f'text-anchor="middle" font-size="{BADGE_FONT}" '
            f'font-weight="700" fill="#f4c62a">{escape(entry.rarity)}</text>'
        )
        name_max_w = bx - BADGE_GAP - PAD

    # 名前
    size, lines = layout_name(name, name_max_w)
    for line, y in lines:
        parts.append(
            f'<text x="{PAD}" y="{y:.1f}" font-size="{size}" font-weight="700" '
            f'fill="{INK}">{escape(line)}</text>'
        )

    # タイプチップ
    x = float(PAD)
    for label in (entry.type1, entry.type2):
        if not label:
            continue
        chip, x = chip_svg(label, TYPE_COLORS.get(label, FALLBACK_COLOR), x)
        parts.append(chip)
    chip_end = x - CHIP_GAP if x > PAD else float(PAD)

    # 右下の補足(初登場 / 進化元)。チップの右の余白に右揃えで置く。
    # データ表より下、rarityバッジと名前より下の帯に入るので重ならない
    for text, y, size in layout_facts(entry, (W - PAD) - chip_end - FACT_GAP):
        parts.append(
            f'<text x="{W - PAD}" y="{y:.1f}" text-anchor="end" '
            f'font-size="{size}" fill="{LABEL_INK}">{escape(text)}</text>'
        )

    parts.append("</g>")
    parts.append(
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" '
        f'rx="{RADIUS - 0.5}" fill="none" stroke="{BORDER_INK}"/>'
    )
    parts.append("</svg>")
    return "".join(parts) + "\n"


def base_species_name(name: str, names: dict[str, int]) -> str | None:
    """フォーム名から元の種の名前を引く。引けなければ None。

    - 「ライチュウ（アローラのすがた）」→ 括弧の前
    - 「メガリザードンX」→ 「メガ」を外し、末尾のX/Y等も外して探す
    """
    if "（" in name:
        base = name.split("（", 1)[0]
        return base if base in names else None
    if name.startswith("メガ"):
        for cand in (name[2:], name[2:-1]):
            if cand in names:
                return cand
    return None


class Entry(NamedTuple):
    """カード1枚分のデータ(CSVの1 id 分)。

    genus / rarity / height_m / weight_kg はその行のCSV値をそのまま使う。
    フォーム行(メガ・地方のすがた・キョダイマックス)にはフォーム固有の体格が
    入っているので、種の値で上書きしてはいけない。
    """

    pid: int
    name: str
    type1: str
    type2: str          # 単タイプなら空文字
    dex_no: int | None  # 全国図鑑No(引けなければ None)
    genus: str
    rarity: str         # 伝説/幻/ウルトラビースト。該当なしなら空文字
    height_m: str
    weight_kg: str
    generation: str     # 登場世代("1"〜"9")。フォームはフォームの導入世代
    evolves_from: str   # 進化前の種名。進化前が無いなら空文字


def load_groups() -> list[Entry]:
    """カード1枚分のデータを id 順で返す(同一idの表記ゆれ行は先頭だけ採る)。

    図鑑Noは種なら id+1(id=全国図鑑No-1)。フォームは元の種の番号を名前から
    引いて使う(フォームの id は連番でしかなく実在の図鑑Noではない)。
    種とフォームの境目は「フォームらしくない行の最大 id」から求める
    (フォーム行は必ず種の後ろに並ぶ ADR 00002)。定数で持たないので
    新種が増えても手当てがいらない。
    """
    seen: set[str] = set()
    rows: list[Entry] = []
    with CSV_PATH.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            rows.append(Entry(
                pid=int(row["id"]),
                name=row["original"],
                type1=row["type1"],
                type2="" if row["type2"] in ("NA", "") else row["type2"],
                dex_no=None,  # 種数が確定してから下で埋める
                genus="" if row["genus"] == "NA" else row["genus"],
                rarity="" if row["rarity"] == "NA" else row["rarity"],
                height_m=row["height_m"],
                weight_kg=row["weight_kg"],
                generation=row["generation"],
                evolves_from=(
                    "" if row["evolves_from"] == "NA" else row["evolves_from"]
                ),
            ))
    rows.sort(key=lambda e: e.pid)

    all_names = {e.name: e.pid for e in rows}
    # 種の数 = 「フォームらしくない行」の最大id+1
    n_species = max(
        e.pid for e in rows if base_species_name(e.name, all_names) is None
    ) + 1
    species_no = {e.name: e.pid + 1 for e in rows if e.pid < n_species}

    out: list[Entry] = []
    for e in rows:
        if e.pid < n_species:
            dex: int | None = e.pid + 1
        else:
            base = base_species_name(e.name, species_no)
            dex = species_no[base] if base else None
        out.append(e._replace(dex_no=dex))
    return out


def existing_assets(tag: str) -> set[str]:
    """リリースにアップロード済みのアセット名。"""
    res = subprocess.run(
        ["gh", "release", "view", tag, "--json", "assets",
         "-q", ".assets[].name"],
        capture_output=True, text=True,
    )
    return set(res.stdout.split()) if res.returncode == 0 else set()


def upload(tag: str, files: list[Path], batch: int = 40,
           retries: int = 6) -> int:
    """gh release upload --clobber でアップロードする。失敗数を返す。

    枚数が多いとGitHubの二次レート制限(HTTP 403)に当たるので、バッチごとに
    少し待ち、失敗したら指数バックオフで再試行する。
    """
    failed = 0
    for i in range(0, len(files), batch):
        chunk = files[i:i + batch]
        cmd = ["gh", "release", "upload", tag, *[str(p) for p in chunk],
               "--clobber"]
        for attempt in range(retries):
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                print(f"  ok {tag} {i + len(chunk)}/{len(files)}", flush=True)
                break
            wait = 60 * (attempt + 1)
            print(f"  retry {tag} {i}-{i + len(chunk) - 1} in {wait}s: "
                  f"{res.stderr.strip()[:160]}", file=sys.stderr, flush=True)
            time.sleep(wait)
        else:
            failed += len(chunk)
            print(f"  NG {tag} {i}-{i + len(chunk) - 1}", file=sys.stderr)
        time.sleep(2)
    return failed


def verify(groups: list[Entry]) -> int:
    """CSVの全 original に対応するアセットがReleaseにあるか確かめる。"""
    want: dict[str, dict[str, str]] = {}
    for e in groups:
        want.setdefault(release_tag(e.name), {})[asset_name(e.name)] = e.name
    ng = 0
    for tag, wanted in sorted(want.items()):
        have = existing_assets(tag)
        if not have:
            print(f"error: {tag} のアセットを取得できない", file=sys.stderr)
            ng += len(wanted)
            continue
        missing = sorted(n for n in wanted if n not in have)
        extra = sorted(have - set(wanted))
        print(f"{tag}: {len(wanted) - len(missing)}/{len(wanted)} ok"
              f"{f', 未生成 {len(missing)}' if missing else ''}"
              f"{f', 余分 {len(extra)}' if extra else ''}")
        for n in missing[:20]:
            print(f"  missing {n} ({wanted[n]})", file=sys.stderr)
        ng += len(missing)
    if ng:
        print(f"error: {ng}件のカードがReleaseに無い。--upload --only-missing "
              "で送ること", file=sys.stderr)
        return 1
    print("all assets present")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "build" / "pokemon_typecards"),
                    help="SVGの出力先ディレクトリ")
    ap.add_argument("--upload", action="store_true",
                    help="生成後に gh release upload --clobber でアップロードする"
                         "(リリースは作成済みであること)")
    ap.add_argument("--only-missing", action="store_true",
                    help="未アップロードのアセットだけ送る(レート制限で中断した"
                         "ときの再開用。内容を差し替えたいときは使わないこと)")
    ap.add_argument("--verify", action="store_true",
                    help="CSVの全 original に対応するアセットがReleaseに"
                         "存在するか検査して終了する(生成もアップロードもしない)")
    args = ap.parse_args()

    groups = load_groups()
    unknown = sorted({t for e in groups for t in (e.type1, e.type2)
                      if t and t not in TYPE_COLORS})
    if unknown:
        print(f"warn: 配色未定義のタイプ {unknown} (灰色で描画)", file=sys.stderr)

    if args.verify:
        return verify(groups)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # モチーフのシルエット。ラベルは種単位なのでフォームも種の図鑑Noで引く
    motifs = load_motifs()
    silhouettes = load_silhouettes()
    embedded = {label: silhouette_svg(svg) for label, svg in silhouettes.items()}

    by_tag: dict[str, list[Path]] = {}
    n = 0
    n_sil = 0
    for e in groups:
        sil = (embedded.get(motifs.get(e.dex_no, ""))
               if e.dex_no is not None else None)
        n_sil += sil is not None
        path = out_dir / asset_name(e.name)
        path.write_text(build_card(e, sil), encoding="utf-8")
        by_tag.setdefault(release_tag(e.name), []).append(path)
        n += 1
    if len({p.name for files in by_tag.values() for p in files}) != n:
        print("error: アセット名が衝突している", file=sys.stderr)
        return 1
    no_dex = [e.name for e in groups if e.dex_no is None]
    print(f"{n} cards -> {out_dir}")
    print(f"  シルエットあり: {n_sil}/{n} ({n_sil / n * 100:.0f}%)")
    if no_dex:
        print(f"  図鑑番号なし: {len(no_dex)}枚 (例 {no_dex[:3]})")
    for tag, files in by_tag.items():
        print(f"  {tag}: {len(files)} assets")

    if args.upload:
        failed = 0
        for tag, files in by_tag.items():
            if args.only_missing:
                done = existing_assets(tag)
                files = [p for p in files if p.name not in done]
                if not files:
                    print(f"{tag}: すべてアップロード済み")
                    continue
            print(f"uploading to {tag} ({len(files)} files) ...", flush=True)
            failed += upload(tag, files)
        if failed:
            print(f"error: {failed}件のアップロードに失敗", file=sys.stderr)
            return 1
        print(f"uploaded {n} assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
