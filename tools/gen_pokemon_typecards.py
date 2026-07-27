#!/usr/bin/env python3
"""pokemon.csv から「型色カード」SVGを生成し、GitHub Releaseへアップロードする。

ポケモンのキャラクター造形は著作物なので画像として複製できない。代わりに
**タイプの配色と文字だけ**で1匹1枚のカードを描く(公式アセット・キャラクター
造形は一切使わない)。意匠は上部にタイプ2色の対角グラデーション、その右下に
図鑑番号、下部に名前とタイプチップ。

- 1 id につき1枚。同一idの表記ゆれ行(ライチュウ/アローラライチュウ/…)は
  同じカードを共有する
- ファイル名は `pkm_<id4桁>.svg`(id=0 → pkm_0000.svg)
- SVGは自己完結(外部フォント・画像を参照しない)。日本語を含むので
  font-family は sans-serif の汎用指定にしており、字形は環境依存
- GitHub Release は1リリースあたり1000アセットが上限なので、id 1000枚ごとに
  リリースを分ける(`pokemon-typecard-v1` / `pokemon-typecard-v1b` / …)。
  fictional-daily-anime-character-v1 / -v1b と同じ命名

usage:
    # 生成のみ(既定の出力先は build/pokemon_typecards/)
    python3 tools/gen_pokemon_typecards.py --out build/pokemon_typecards

    # 生成してリリースへアップロード(gh CLIが必要。リリースは作成済みのこと)
    python3 tools/gen_pokemon_typecards.py --out build/pokemon_typecards \
        --upload

**新ポケモン(新種・新フォーム)が追加されたら、本スクリプトを再実行して
Release を更新すること。** pokemon.csv の image 列は id から機械的に組み立てる
ので(tools/update_pokemon.py)、アセットが無い id は 404 になる。加えてフォームの
id は種が増えると振り直される(ADR 00002)ため、**新種追加時は差分だけでなく
全枚数を作り直して --clobber で上書きする**必要がある。作り直したら、下の
ASSET_MAX_ID も出力される値に更新する。
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "pokemon.csv"

# Release のタグと画像URL(update_pokemon.py からも参照する)
IMAGE_TAG = "pokemon-typecard-v1"
RELEASE_BASE = "https://github.com/soramimic/soramimic-wordlists/releases"
# GitHub Release の1リリースあたりのアセット上限
ASSETS_PER_RELEASE = 1000
# Release にアセットを生成済みの最大 id。再生成のたびに更新する
ASSET_MAX_ID = 1202

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

# カード寸法(固定viewBox)
W, H = 320, 200
HERO_H = 112
PAD = 16
RADIUS = 16
FONT = "'Hiragino Sans','Noto Sans JP','Yu Gothic',sans-serif"
NAME_SIZES_1LINE = (23, 21, 19)   # 1行に収まるなら大きい方から採用
NAME_SIZES_2LINE = (18, 16, 14, 12)  # 収まらなければ2行に折り返す
CHIP_FONT = 12.5
CHIP_H = 22
CHIP_TOP = 166
CHIP_PAD = 10
CHIP_GAP = 6


def asset_name(pokemon_id: int | str) -> str:
    return f"pkm_{int(pokemon_id):04d}.svg"


def release_tag(pokemon_id: int | str) -> str:
    """id が属するリリースのタグ。1000枚ごとに v1 / v1b / v1c … と分ける。"""
    chunk = int(pokemon_id) // ASSETS_PER_RELEASE
    return IMAGE_TAG if chunk == 0 else f"{IMAGE_TAG}{chr(ord('a') + chunk)}"


def image_url(pokemon_id: int | str) -> str:
    tag = release_tag(pokemon_id)
    return f"{RELEASE_BASE}/download/{tag}/{asset_name(pokemon_id)}"


def image_page_url(pokemon_id: int | str) -> str:
    return f"{RELEASE_BASE}/tag/{release_tag(pokemon_id)}"


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


def layout_name(name: str) -> tuple[float, list[tuple[str, float]]]:
    """(font_size, [(行テキスト, ベースラインy), ...]) を返す。"""
    max_w = W - PAD * 2
    for size in NAME_SIZES_1LINE:
        if text_width(name, size) <= max_w:
            return size, [(name, 143.0)]
    for size in NAME_SIZES_2LINE:
        lines = wrap_two(name, size, max_w)
        if lines:
            step = size * 1.25
            first = 150.0 - step
            return size, [(lines[0], first), (lines[1], first + step)]
    # ここには来ない想定(最小サイズでも2行に割れない極端な名前)
    size = NAME_SIZES_2LINE[-1]
    half = len(name) // 2 or 1
    step = size * 1.25
    return size, [(name[:half], 150.0 - step), (name[half:], 150.0)]


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


def build_card(pokemon_id: int, name: str, type1: str, type2: str) -> str:
    c1 = TYPE_COLORS.get(type1, FALLBACK_COLOR)
    c2 = TYPE_COLORS.get(type2, c1) if type2 else c1
    # id をSVG内の要素idにも入れる。複数枚をHTMLへインライン展開しても
    # グラデーション定義が衝突しないようにするため
    gid = f"g{pokemon_id:04d}"
    cid = f"c{pokemon_id:04d}"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" '
        f'aria-label="{escape(name)}">',
        "<defs>",
        # CSS の linear-gradient(135deg, c1 0 50%, c2 50% 100%) と同じ向き・
        # 同じハードストップ(中心を通る45度の分割線)
        f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
        'x1="52" y1="-52" x2="268" y2="164">',
        f'<stop offset="0.5" stop-color="{c1}"/>',
        f'<stop offset="0.5" stop-color="{c2}"/>',
        "</linearGradient>",
        f'<clipPath id="{cid}"><rect x="0" y="0" width="{W}" height="{H}" '
        f'rx="{RADIUS}"/></clipPath>',
        "</defs>",
        f'<g clip-path="url(#{cid})" font-family="{FONT}">',
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>',
        f'<rect x="0" y="0" width="{W}" height="{HERO_H}" fill="url(#{gid})"/>',
        # 図鑑番号(右下)。影を1pxずらして重ねる
        f'<text x="{W - 13}" y="{HERO_H - 12}" text-anchor="end" '
        'font-family="monospace" font-size="15" font-weight="700" '
        'fill="#000000" fill-opacity="0.28">'
        f"{pokemon_id + 1:04d}</text>",
        f'<text x="{W - 14}" y="{HERO_H - 13}" text-anchor="end" '
        'font-family="monospace" font-size="15" font-weight="700" '
        'fill="#ffffff" fill-opacity="0.9">'
        f"{pokemon_id + 1:04d}</text>",
    ]

    size, lines = layout_name(name)
    for line, y in lines:
        parts.append(
            f'<text x="{PAD}" y="{y:.1f}" font-size="{size}" font-weight="700" '
            f'fill="#1a1a19">{escape(line)}</text>'
        )

    x = float(PAD)
    for label in (type1, type2):
        if not label:
            continue
        chip, x = chip_svg(label, TYPE_COLORS.get(label, FALLBACK_COLOR), x)
        parts.append(chip)

    parts.append("</g>")
    parts.append(
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" '
        f'rx="{RADIUS - 0.5}" fill="none" stroke="#e3e1db"/>'
    )
    parts.append("</svg>")
    return "".join(parts) + "\n"


def load_groups() -> list[tuple[int, str, str, str]]:
    seen: set[str] = set()
    out: list[tuple[int, str, str, str]] = []
    with CSV_PATH.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            t2 = "" if row["type2"] in ("NA", "") else row["type2"]
            out.append((int(row["id"]), row["original"], row["type1"], t2))
    out.sort(key=lambda r: r[0])
    return out


def upload(tag: str, files: list[Path], batch: int = 40) -> int:
    """gh release upload --clobber でアップロードする。失敗数を返す。"""
    failed = 0
    for i in range(0, len(files), batch):
        chunk = files[i:i + batch]
        cmd = ["gh", "release", "upload", tag, *[str(p) for p in chunk],
               "--clobber"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            failed += len(chunk)
            print(f"  NG {tag} {i}-{i + len(chunk) - 1}: "
                  f"{res.stderr.strip()[:300]}", file=sys.stderr)
        else:
            print(f"  ok {tag} {i + len(chunk)}/{len(files)}", flush=True)
    return failed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "build" / "pokemon_typecards"),
                    help="SVGの出力先ディレクトリ")
    ap.add_argument("--upload", action="store_true",
                    help="生成後に gh release upload --clobber でアップロードする"
                         "(リリースは作成済みであること)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    groups = load_groups()
    unknown = sorted({t for _, _, t1, t2 in groups for t in (t1, t2)
                      if t and t not in TYPE_COLORS})
    if unknown:
        print(f"warn: 配色未定義のタイプ {unknown} (灰色で描画)", file=sys.stderr)

    by_tag: dict[str, list[Path]] = {}
    n = 0
    for pid, name, t1, t2 in groups:
        path = out_dir / asset_name(pid)
        path.write_text(build_card(pid, name, t1, t2), encoding="utf-8")
        by_tag.setdefault(release_tag(pid), []).append(path)
        n += 1
    print(f"{n} cards -> {out_dir}")
    print(f"ASSET_MAX_ID = {groups[-1][0]} (定数を更新すること)")
    for tag, files in by_tag.items():
        print(f"  {tag}: {len(files)} assets")

    if args.upload:
        failed = 0
        for tag, files in by_tag.items():
            print(f"uploading to {tag} ...", flush=True)
            failed += upload(tag, files)
        if failed:
            print(f"error: {failed}件のアップロードに失敗", file=sys.stderr)
            return 1
        print(f"uploaded {n} assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
