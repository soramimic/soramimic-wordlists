#!/usr/bin/env python3
"""youtuber.csv の人物の「イメージカラー」を公式サイトから集める。

生成カード(gen_youtuber_cards.py)の配色に本人の色を反映するための下ごしらえ。
結果は `tools/youtuber_colors.json` に**出典URL付き**で書き出す。

## 何を取っていて、何を取っていないか(ADR 00018)

- 取るのは**色そのもの(16進値)というテキスト情報だけ**。色はアイデア・事実の
  領域で著作物ではないので、イラストの複製とは別物として扱える
- **イラスト画像のダウンロードやパレット抽出は一切しない**。取得元は「色を
  テキストとして公表している公式サイト」に限る(HTMLのdata属性・CSS変数・
  inline style)。画像の中にしか色が無いものは**取得不可として諦める**
- ファンwikiやまとめサイトは出典にしない(公式の発表ではないため)
- **youtuber.csv に載っている人の分だけを保存する**。事務所のメンバー一覧を
  丸ごと複製する形にはしない

## 取得できないことが分かっているもの

- **ホロライブ / にじさんじ**: 公式が発表しているのは大型ライブの「公式ペン
  ライトカラー」だが、実体は1枚のバナー画像で、HTML/CSS/JSONに色のテキストが
  無い。タレント個別ページや共通CSSにもタレント色のフックが無い。画像からの
  抽出はしない方針なので**取得しない**(推測色は入れない)
- **ホロスターズ / KAMITSUBAKI / ドズル社 / のりプロ**: 公式サイトにタレント色
  の記載が無い(WordPress既定パレットの色しか出てこない)
- **774inc. / .LIVE(vrlive.party)**: メンバー一覧がクライアントサイドJSで
  描画されるため、HTMLを取ってきても色が入っていない。ヘッドレスブラウザを
  持ち込んでまで取りにはいかない
- Wikidata の P462(色) / P465(sRGB) は対象者に1件も付いていない

usage:
  python3 tools/fetch_youtuber_colors.py            # 取得して JSON を更新
  python3 tools/fetch_youtuber_colors.py --report   # 照合結果を1件ずつ表示
  python3 tools/fetch_youtuber_colors.py --refresh  # HTMLキャッシュを捨てて再取得
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "youtuber.csv"
OUT_PATH = Path(__file__).resolve().parent / "youtuber_colors.json"
CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "youtuber_colors"

UA = {"User-Agent": "soramimic-wordlists-updater/1.0 "
                    "(https://github.com/soramimic/soramimic-wordlists)"}

README = (
    "youtuber.csv の人物のイメージカラー。tools/fetch_youtuber_colors.py が生成する。"
    "色は公式サイトがテキストで公表している値のみを収録し、イラストからの抽出はしていない。"
    "primary/secondary は16進表記。source が manual の項目は人手で確認したもの。"
    "詳細は docs/adr/00018-youtuber-images.md を参照。"
)


def norm_name(name: str) -> str:
    """公式サイトの表記を youtuber.csv の original に寄せる(空白除去)。"""
    return name.replace("　", "").replace(" ", "").strip()


def parse_vspo(html: str) -> dict:
    """ぶいすぽっ！公式トップのメンバー一覧。

    `data-name="花芽 すみれ" data-color="#beccff"` の形で、日本語名と色が
    同じ要素の属性に入っている。
    """
    out = {}
    for m in re.finditer(
            r'data-name="([^"]+)"\s+data-color="\s*(#[0-9a-fA-F]{3,6})\s*"', html):
        out[norm_name(m.group(1))] = m.group(2).lower()
    return out


def parse_aogiri(html: str) -> dict:
    """あおぎり高校公式トップのメンバー一覧。

    メンバーページへのリンクに `style="background-color:#00a0af;"` が付き、
    中の `<img alt="萌実">` が日本語名になっている。
    """
    out = {}
    for m in re.finditer(
            r'href="/aogirihighschool/members/[a-z0-9_-]+"[^>]*'
            r'style="background-color:\s*(#[0-9a-fA-F]{3,6})\s*;?"[^>]*>\s*'
            r'<img[^>]*alt="([^"]+)"', html):
        out[norm_name(m.group(2))] = m.group(1).lower()
    return out


def parse_neoporte(html: str) -> dict:
    """Neo-Porte公式のメンバー一覧。

    `<li ... style="--c-key: #f79428;">` の中に `<img alt="渋谷 ハル">` が入る。
    """
    out = {}
    for m in re.finditer(
            r'style="--c-key:\s*(#[0-9a-fA-F]{3,6})\s*;?"[^>]*>.{0,600}?'
            r'<img[^>]*alt="([^"]+)"', html, re.S):
        out[norm_name(m.group(2))] = m.group(1).lower()
    return out


# 取得元。1件=1サイト。色をテキストで公表している公式サイトだけを並べる
SOURCES = [
    {
        "key": "vspo",
        "name": "ぶいすぽっ！公式サイト",
        "url": "https://vspo.jp/",
        "how": "メンバー一覧の data-name / data-color 属性",
        "parse": parse_vspo,
    },
    {
        "key": "aogiri",
        "name": "あおぎり高校公式サイト",
        "url": "https://www.aogirihighschool.com/",
        "how": "メンバー一覧リンクの background-color と img の alt",
        "parse": parse_aogiri,
    },
    {
        "key": "neoporte",
        "name": "Neo-Porte公式サイト",
        "url": "https://neo-porte.jp/member/",
        "how": "メンバー一覧の CSS変数 --c-key と img の alt",
        "parse": parse_neoporte,
    },
]

# 自動取得できないが、公式の**テキスト**の記載を人手で確認できたもの。
# 形式: original -> {"primary": "#rrggbb", "secondary": "#rrggbb"(任意),
#                    "source_name": "...", "source_url": "..."}
# 推測色・ファンwiki由来の色は入れないこと(空のままでよい)。
MANUAL: dict[str, dict] = {}


def fetch(url: str, key: str, refresh: bool) -> str:
    """HTMLを取得する(`tools/.cache/` に保存して再開可能・冪等)。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{key}.html"
    if cache.exists() and not refresh:
        return cache.read_text(encoding="utf-8")
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as res:
                html = res.read().decode("utf-8", "replace")
            break
        except Exception as ex:      # noqa: BLE001 (ネットワーク全般)
            print(f"retry {attempt}: {url} ({ex})", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    else:
        raise SystemExit(f"error: 取得に失敗: {url}")
    cache.write_text(html, encoding="utf-8")
    time.sleep(1)                    # 連続アクセスを避ける
    return html


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true",
                    help="HTMLキャッシュを無視して取り直す")
    ap.add_argument("--report", action="store_true",
                    help="サイト側にいてCSVに載っていない名前も表示する")
    args = ap.parse_args()

    originals = {r["original"] for r in
                 csv.DictReader(CSV_PATH.open(encoding="utf-8"))}

    colors: dict[str, dict] = {}
    for src in SOURCES:
        html = fetch(src["url"], src["key"], args.refresh)
        found = src["parse"](html)
        if not found:
            print(f"error: {src['name']} から色を1件も取れなかった"
                  "(サイト構造が変わった可能性)", file=sys.stderr)
            return 1
        hit = {n: c for n, c in found.items() if n in originals}
        miss = sorted(set(found) - set(hit))
        for name, hexcolor in hit.items():
            colors[name] = {
                "primary": hexcolor,
                "source": "official",
                "source_name": src["name"],
                "source_url": src["url"],
            }
        print(f"{src['name']}: サイト側 {len(found)}人 -> "
              f"youtuber.csv と一致 {len(hit)}人")
        if args.report and miss:
            print(f"  CSVに居ない(保存しない): {', '.join(miss)}")

    for name, entry in MANUAL.items():
        if name not in originals:
            print(f"warn: MANUAL の {name} は youtuber.csv に居ない",
                  file=sys.stderr)
            continue
        colors[name] = {**entry, "source": "manual"}
    if MANUAL:
        print(f"人手で確認した色: {len(MANUAL)}人")

    OUT_PATH.write_text(
        json.dumps({"_readme": README,
                    "colors": dict(sorted(colors.items()))},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"\n{OUT_PATH.relative_to(ROOT)}: {len(colors)}人分の色を書き出した")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
