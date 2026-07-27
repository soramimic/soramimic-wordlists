#!/usr/bin/env python3
"""pokemon.csv から「型色カード」SVGを生成し、GitHub Releaseへアップロードする。

ポケモンのキャラクター造形は著作物なので画像として複製できない。代わりに
**タイプの配色と文字だけ**で1匹1枚のカードを描く(公式アセット・キャラクター
造形は一切使わない)。意匠は上部にタイプ2色の対角グラデーション、その右下に
図鑑番号、下部に名前とタイプチップ。

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
import subprocess
import sys
import time
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "pokemon.csv"

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


def build_card(name: str, type1: str, type2: str, dex_no: int | None) -> str:
    c1 = TYPE_COLORS.get(type1, FALLBACK_COLOR)
    c2 = TYPE_COLORS.get(type2, c1) if type2 else c1
    # 名前由来のキーをSVG内の要素idにも入れる。複数枚をHTMLへインライン展開しても
    # グラデーション定義が衝突しないようにするため
    key = asset_key(name)
    gid = f"g{key}"
    cid = f"c{key}"

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
    ]

    # 図鑑番号(右下)。影を1pxずらして重ねる。実在する番号が分からない
    # (種を引けないフォーム)ときは出さない
    if dex_no is not None:
        parts += [
            f'<text x="{W - 13}" y="{HERO_H - 12}" text-anchor="end" '
            'font-family="monospace" font-size="15" font-weight="700" '
            'fill="#000000" fill-opacity="0.28">'
            f"{dex_no:04d}</text>",
            f'<text x="{W - 14}" y="{HERO_H - 13}" text-anchor="end" '
            'font-family="monospace" font-size="15" font-weight="700" '
            'fill="#ffffff" fill-opacity="0.9">'
            f"{dex_no:04d}</text>",
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


def load_groups() -> list[tuple[int, str, str, str, int | None]]:
    """(id, original, type1, type2, 図鑑No or None) を id 順で返す。

    図鑑Noは種なら id+1(id=全国図鑑No-1)。フォームは元の種の番号を名前から
    引いて使う(フォームの id は連番でしかなく実在の図鑑Noではない)。
    種とフォームの境目は「フォームらしくない行の最大 id」から求める
    (フォーム行は必ず種の後ろに並ぶ ADR 00002)。定数で持たないので
    新種が増えても手当てがいらない。
    """
    seen: set[str] = set()
    rows: list[tuple[int, str, str, str]] = []
    with CSV_PATH.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            t2 = "" if row["type2"] in ("NA", "") else row["type2"]
            rows.append((int(row["id"]), row["original"], row["type1"], t2))
    rows.sort(key=lambda r: r[0])

    all_names = {name: pid for pid, name, _, _ in rows}
    # 種の数 = 「フォームらしくない行」の最大id+1
    n_species = max(
        pid for pid, name, _, _ in rows
        if base_species_name(name, all_names) is None
    ) + 1
    species_no = {name: pid + 1 for pid, name, _, _ in rows if pid < n_species}

    out: list[tuple[int, str, str, str, int | None]] = []
    for pid, name, t1, t2 in rows:
        if pid < n_species:
            dex: int | None = pid + 1
        else:
            base = base_species_name(name, species_no)
            dex = species_no[base] if base else None
        out.append((pid, name, t1, t2, dex))
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


def verify(groups: list[tuple[int, str, str, str, int | None]]) -> int:
    """CSVの全 original に対応するアセットがReleaseにあるか確かめる。"""
    want: dict[str, dict[str, str]] = {}
    for _, name, _, _, _ in groups:
        want.setdefault(release_tag(name), {})[asset_name(name)] = name
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
    unknown = sorted({t for _, _, t1, t2, _ in groups for t in (t1, t2)
                      if t and t not in TYPE_COLORS})
    if unknown:
        print(f"warn: 配色未定義のタイプ {unknown} (灰色で描画)", file=sys.stderr)

    if args.verify:
        return verify(groups)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    by_tag: dict[str, list[Path]] = {}
    n = 0
    for _, name, t1, t2, dex in groups:
        path = out_dir / asset_name(name)
        path.write_text(build_card(name, t1, t2, dex), encoding="utf-8")
        by_tag.setdefault(release_tag(name), []).append(path)
        n += 1
    if len({p.name for files in by_tag.values() for p in files}) != n:
        print("error: アセット名が衝突している", file=sys.stderr)
        return 1
    no_dex = [name for _, name, _, _, dex in groups if dex is None]
    print(f"{n} cards -> {out_dir}")
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
