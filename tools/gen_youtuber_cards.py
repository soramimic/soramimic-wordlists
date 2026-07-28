#!/usr/bin/env python3
"""youtuber.csv の実写が無い行に割り当てる「象徴カード」SVGを生成する。

YouTuber/VTuberのチャンネルアイコン・サムネイル・キャラクターイラストは本人/
事務所の著作物なので使えない(詳細は ADR 00018)。自由ライセンスの実写が取れる
のは1割弱なので、残りには**配色と文字だけで描いた記号的なカード**を割り当てる。
pokemon の「型色カード」(ADR 00002)と同じ考え方で、素材は一切借りない。

- 1人1枚。同じ人物の複数行(full/family/given)は同じ `original` なので同じ
  カードを共有する
- **ファイル名は名前(original)から決定的に導出する**: `yt_<sha1(original)の
  先頭10桁>.svg`。id は将来の再採番に耐えないので使わない
- 配色は**本人のイメージカラー**を最優先で使う(`tools/youtuber_colors.json`。
  出典URL付きで管理し、公式が公表している色は `tools/fetch_youtuber_colors.py`、
  公式ポートレートの情報解析で求めた色は `tools/derive_youtuber_colors.py` が
  更新する)。主色・副色の2色があれば、主色を帯に、副色を帯下のラインと
  頭文字ディスクに使う。
  色が分からない人は従来どおり `category` と `org` から決める:
  youtuberは暖色(赤〜橙)、vtuberは寒色(青紫)の帯に分け、**同じ事務所は同じ
  色相**になるよう org の表示名から決定的に色相を振る。所属なし(NA)は基準色
- **使うのは色という事実だけ**で、イラストそのものはリポジトリに入らない。
  解析に使った画像は `tools/.cache/` 止まりで再配布しない(詳細は ADR 00018, 00019)
- 中央には名前の頭文字、下部にフルネーム、上部にカテゴリと所属を描く。実写と
  誤認されないよう右上に「イメージ」の札を必ず入れる
- 自己完結SVG(外部フォント・画像を参照しない)。viewBox は 320x200 固定
- **生成物はリポジトリ内(`images/youtuber/`)に置き**、CSVからは raw URL で
  参照する。枚数が1000枚弱と少なく、1枚1KB程度なのでReleaseを介す必要がない

usage:
  # 生成してCSVのimage/image_pageを埋める(実写のある行は触らない)
  python3 tools/gen_youtuber_cards.py

  # 生成だけ(CSVを書き換えない)
  python3 tools/gen_youtuber_cards.py --no-apply

  # CSVから参照されなくなったSVGを消す
  python3 tools/gen_youtuber_cards.py --prune
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
from wpnames import write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "youtuber.csv"
OUT_DIR = ROOT / "images" / "youtuber"
REL_DIR = "images/youtuber"
# 本人のイメージカラー(出典URL付き)。tools/fetch_youtuber_colors.py が更新する
COLORS_PATH = Path(__file__).resolve().parent / "youtuber_colors.json"

RAW_BASE = "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/main"
BLOB_BASE = "https://github.com/soramimic/soramimic-wordlists/blob/main"
# 生成カードのURLはこの接頭辞で始まる(実写かどうかの判定に使う)
URL_PREFIX = f"{RAW_BASE}/{REL_DIR}/"

W, H = 320, 200
HERO_H = 112
PAD = 16
RADIUS = 16
FONT = "'Hiragino Sans','Noto Sans JP','Yu Gothic',sans-serif"
NAME_SIZES_1LINE = (23, 21, 19)
NAME_SIZES_2LINE = (17, 15, 13, 11)

# カテゴリごとの基準色相と、org で振る色相の幅(度)。範囲が重ならないので
# youtuber(暖色)と vtuber(青紫)はひと目で見分けられる
CATEGORY_STYLE = {
    "youtuber": {"label": "YouTuber", "hue": 8, "spread": 30},
    "vtuber": {"label": "VTuber", "hue": 268, "spread": 40},
}
DEFAULT_STYLE = {"label": "YouTuber", "hue": 8, "spread": 30}
ORG_MAX = 13   # 所属名の表示上限(全角換算)

# 減量版(--style minimal)の頭文字ディスク。帯(y=112)の境目にまたがる位置に
# 置くと、上下どちらの領域にも属さない「記号」として読める
MIN_DISC_CY = 100
MIN_DISC_R = 48
MIN_MARK_SIZES = (56, 44)   # (1文字, 2文字)


def asset_key(name: str) -> str:
    """名前から決定的に導く10桁のキー。id には依存しない。"""
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]


def asset_name(name: str) -> str:
    return f"yt_{asset_key(name)}.svg"


def image_url(name: str) -> str:
    return f"{URL_PREFIX}{asset_name(name)}"


def image_page_url(name: str) -> str:
    return f"{BLOB_BASE}/{REL_DIR}/{asset_name(name)}"


def hsl(h: float, s: float, lum: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, lum, s)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def parse_hex(value: str):
    """`#rgb` / `#rrggbb` -> (色相[度], 彩度, 明度, 鮮やかさ)。読めなければ None。

    4つ目の「鮮やかさ」は RGB の最大-最小(chroma)。HLSの彩度は淡い水色でも
    1.0 になってしまうので、「どちらの色が主役向きか」の比較にはこちらを使う。
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


def org_key(org: str) -> str:
    """org列(スラッシュ区切り多値)から色と表示に使う1つの所属を選ぶ。

    多値には事務所とその中のユニット・期生が混ざる(`ROF-MAO/にじさんじ`,
    `ホロライブ/ホロライブ3期生`)。**最も短い要素**を採ると事務所側が残るので、
    「同じ事務所は同系色」が期待通りに効く。同長は辞書順で決定的に選ぶ。
    """
    if not org or org == "NA":
        return ""
    parts = [p.strip() for p in org.split("/") if p.strip()]
    return min(parts, key=lambda p: (len(p), p)) if parts else ""


def org_label(org: str) -> str:
    """カードに描く所属名(長すぎるものは切り詰める)。無ければ空。"""
    head = org_key(org)
    if head and text_width(head, 1.0) > ORG_MAX:
        while head and text_width(head + "…", 1.0) > ORG_MAX:
            head = head[:-1]
        head += "…"
    return head


def fallback_hue(category: str, org: str) -> float:
    """イメージカラーが分からない人の色相。category と org から決定的に決める。"""
    st = CATEGORY_STYLE.get(category, DEFAULT_STYLE)
    key = org_key(org)
    if not key:
        return st["hue"]        # 所属なしはカテゴリの基準色
    # 事務所名のハッシュで色相を振る。切り詰め前の名前から決めるので、
    # 表示が「ホロライブプ…」に縮んでも同じ事務所は同じ色になる
    seed = int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:8], 16)
    return st["hue"] + seed % (st["spread"] * 2 + 1) - st["spread"]


ACHROMATIC = 0.06   # chroma がこれ未満なら白・黒・灰(色相に意味が無い)
LIGHT_BAND = 0.62   # 帯の明るさがこれを超えたら、帯の上の文字を濃色に切り替える


def _hex(parsed) -> str:
    h, s, lum, _chroma = parsed
    return hsl(h, s, lum)


def perceived(h: float, s: float, lum: float) -> float:
    """人の目に見える明るさ(0..1)。帯の上に白と濃色のどちらを置くかの判定用。"""
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, lum, s)
    return 0.299 * r + 0.587 * g + 0.114 * b


def palette(category: str, org: str, color: dict | None = None) -> dict:
    """カードの配色を決める。

    `color` に本人のイメージカラー(`{"primary": "#rrggbb", "secondary": ...}`)が
    あればそれを使う。2色あるときは**鮮やかな方を帯**に、もう一方を帯下のラインに
    回す(「白+ピンク」ならピンクの帯に白のライン、「白+青」なら青の帯に白のライン)。

    帯の色は**色相・彩度をほぼそのまま残す**。淡い色でも暗く沈めたりせず、代わりに
    帯の上の文字を白/濃色に切り替えて読めるようにする(`light` フラグ)。
    こうしないと「淡いピンク」が「赤」になってしまい、イメージカラーの意味が消える。

    色が無い人は従来どおり category と org のハッシュから色相を決める。
    """
    st = CATEGORY_STYLE.get(category, DEFAULT_STYLE)
    given = [c for c in (parse_hex((color or {}).get("primary", "")),
                         parse_hex((color or {}).get("secondary", "")))
             if c is not None]
    given.sort(key=lambda c: -c[3])      # 鮮やかな方を帯に回す
    line = _hex(given[1]) if len(given) > 1 else ""

    if given:
        h, s, lum, chroma = given[0]
        s = 0.0 if chroma < ACHROMATIC else clamp(s, 0.25, 0.85)
        lum = clamp(lum, 0.30, 0.86)     # 真っ黒/真っ白だけは寄せる
    else:
        h, s, lum = fallback_hue(category, org), 0.50, 0.40
    light = perceived(h, s, lum) > LIGHT_BAND
    # 頭文字ディスクは帯と明暗を逆にする(淡い帯には濃いディスク)。
    # 淡い色をディスクに使うときだけ副色の色相を借りる(濃いディスクを副色の
    # 色相で塗ると、副色が白のときに無関係な灰色の丸になってしまう)
    hd, sd = (given[1][0], given[1][1]) if len(given) > 1 else (h, s)
    if len(given) > 1 and given[1][3] < ACHROMATIC:
        sd = 0.0
    dark_ink = hsl(h, min(s, 0.45), 0.22)
    if light:
        disc, mark = hsl(h, min(s, 0.55), 0.30), hsl(h, min(s, 0.25), 0.95)
    else:
        disc, mark = hsl(hd, clamp(sd, 0.0, 0.46), 0.94), hsl(h, s, 0.40)
    return {
        "label": st["label"],
        "org": org_label(org),
        "light": light,
        "bg": hsl(h, min(s, 0.42), 0.965),
        "accent": hsl(h, s, lum),
        "accent2": hsl(h + 16, min(s + 0.04, 0.88), min(lum + 0.08, 0.92)),
        "band": line,
        "disc": disc,
        "mark": mark,
        "fg": dark_ink if light else "#ffffff",
        "chip_bg": dark_ink if light else "#ffffff",
        "chip_fg": "#ffffff" if light else hsl(h, s, min(lum, 0.42)),
        "ink": hsl(h, min(s, 0.30), 0.20),
        "edge": hsl(h, min(s, 0.25), 0.88),
    }


def text_width(text: str, size: float) -> float:
    """描画幅の見積り。CJK・かなは1em、ASCIIは0.6em(多めに見る)。"""
    return sum(0.6 if ord(c) < 128 else 1.0 for c in text) * size


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
    max_w = W - PAD * 2
    for size in NAME_SIZES_1LINE:
        if text_width(name, size) <= max_w:
            return size, [(name, 163.0)]
    for size in NAME_SIZES_2LINE:
        lines = wrap_two(name, size, max_w)
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


def build_card(name: str, category: str, org: str,
               color: dict | None = None, minimal: bool = False) -> str:
    """カードのSVGを組む。

    `minimal=True` は**文字情報を落とした減量版**(試作)。soramimic-video の
    `youtuber_card` レイアウトが `{original}`(名前)と `{org}`(所属)を
    テキストで描くので、カードにも同じ文字が入っていると画面内で二重になる。
    残すのは
    「配色(イメージカラー)+頭文字+『イメージ』の札」だけで、名前・区分・
    所属は描かない。youtuber(暖色)と vtuber(青紫)の別は色相が担うので、
    区分の文字を落としても見分けは付く。「イメージ」の札は実写と誤認され
    ないための表示なので減量版でも必ず残す。
    """
    p = palette(category, org, color)
    key = asset_key(name)
    gid, cid = f"g{key}", f"c{key}"
    mark = initials(name)
    mark_size = 34 if len(mark) > 1 else 40

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" '
        f'aria-label="{escape(name)}のイメージ画像">',
        f"<title>{escape(name)}のイメージ画像</title>",
        ("<desc>本人の写真・チャンネルアイコン・キャラクターデザインは一切"
         "使っていない、配色と頭文字だけの記号的なカードです。"
         "実写ではありません。</desc>" if minimal else
         "<desc>本人の写真・チャンネルアイコン・キャラクターデザインは一切"
         "使っていない、配色と文字だけの記号的なカードです。実写ではありません。"
         "</desc>"),
        "<defs>",
        f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
        f'x1="0" y1="0" x2="{W}" y2="{HERO_H}">',
        f'<stop offset="0" stop-color="{p["accent"]}"/>',
        f'<stop offset="1" stop-color="{p["accent2"]}"/>',
        "</linearGradient>",
        f'<clipPath id="{cid}"><rect x="0" y="0" width="{W}" height="{H}" '
        f'rx="{RADIUS}"/></clipPath>',
        "</defs>",
        f'<g clip-path="url(#{cid})" font-family="{FONT}">',
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="{p["bg"]}"/>',
        f'<rect x="0" y="0" width="{W}" height="{HERO_H}" fill="url(#{gid})"/>',
    ]
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
            f'y="{MIN_DISC_CY + mark_size * 0.36:.1f}" text-anchor="middle" '
            f'font-size="{mark_size}" font-weight="700" fill="{p["mark"]}">'
            f"{escape(mark)}</text>",
        ]
    else:
        parts += [
            # 頭文字のディスク
            f'<circle cx="58" cy="60" r="36" fill="{p["disc"]}"/>',
            f'<text x="58" y="{60 + mark_size * 0.36:.1f}" '
            f'text-anchor="middle" font-size="{mark_size}" font-weight="700" '
            f'fill="{p["mark"]}">{escape(mark)}</text>',
            # 区分と所属。帯が淡い色のときは白ではなく濃色で書く
            f'<text x="108" y="56" font-size="19" font-weight="700" '
            f'fill="{p["fg"]}">{escape(p["label"])}</text>',
        ]
        if p["org"]:
            parts.append(
                f'<text x="108" y="80" font-size="13" fill="{p["fg"]}" '
                f'fill-opacity="0.85">{escape(p["org"])}</text>')
    # 実写と誤認されないための札。減量版でも必ず残す
    parts += [
        f'<rect x="240" y="10" width="70" height="22" rx="11" '
        f'fill="{p["chip_bg"]}" fill-opacity="0.9"/>',
        f'<text x="275" y="26" text-anchor="middle" font-size="13" '
        f'font-weight="600" fill="{p["chip_fg"]}">イメージ</text>',
    ]
    if not minimal:
        size, lines = layout_name(name)
        for line, y in lines:
            parts.append(
                f'<text x="{W / 2:g}" y="{y:.1f}" text-anchor="middle" '
                f'font-size="{size}" font-weight="700" fill="{p["ink"]}">'
                f"{escape(line)}</text>")
    parts.append("</g>")
    parts.append(
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" '
        f'rx="{RADIUS - 0.5}" fill="none" stroke="{p["edge"]}"/>')
    parts.append("</svg>")
    return "".join(parts) + "\n"


def load_people() -> list:
    """(original, category, org) を CSV の行順で重複なく返す。"""
    seen = set()
    out = []
    with CSV_PATH.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["original"] in seen:
                continue
            seen.add(r["original"])
            out.append((r["original"], r["category"], r.get("org", "")))
    return out


def load_colors() -> dict:
    """`tools/youtuber_colors.json` の colors 部分。無ければ空。"""
    if not COLORS_PATH.exists():
        return {}
    data = json.loads(COLORS_PATH.read_text(encoding="utf-8"))
    return data.get("colors", {})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT_DIR), help="SVGの出力先")
    ap.add_argument("--no-apply", action="store_true",
                    help="CSVのimage/image_pageを書き換えない(生成のみ)")
    ap.add_argument("--prune", action="store_true",
                    help="CSVから参照されなくなったSVGを削除する")
    ap.add_argument("--style", choices=("full", "minimal"), default="full",
                    help="minimal は名前・区分・所属の文字を描かない減量版")
    args = ap.parse_args()
    minimal = args.style == "minimal"

    people = load_people()
    colors = load_colors()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    wanted = set()
    n_color = 0
    for name, category, org in people:
        color = colors.get(name)
        if color and color.get("primary"):
            n_color += 1
        path = out_dir / asset_name(name)
        path.write_text(build_card(name, category, org, color, minimal),
                        encoding="utf-8")
        wanted.add(path.name)
    if len(wanted) != len(people):
        print("error: アセット名が衝突している", file=sys.stderr)
        return 1
    unused = sorted(set(colors) - {n for n, _, _ in people})
    print(f"{len(people)}枚を生成 -> {out_dir}"
          f"(イメージカラーあり {n_color}人 / 事務所ハッシュ由来 "
          f"{len(people) - n_color}人)")
    if unused:
        print(f"注意: CSVに居ない人の色定義が {len(unused)}件 "
              f"({'/'.join(unused[:5])})")

    stale = sorted(p for p in out_dir.glob("yt_*.svg") if p.name not in wanted)
    if stale:
        if args.prune:
            for p in stale:
                p.unlink()
            print(f"参照されなくなったSVGを削除: {len(stale)}枚")
        else:
            print(f"注意: CSVから参照されないSVGが {len(stale)}枚ある "
                  f"(--prune で削除)")

    if args.no_apply:
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
    print(f"youtuber.csv: カードを付与 +{filled}行, 貼り替え {rebound}行, "
          f"実写あり {photo}行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
