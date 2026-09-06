#!/usr/bin/env python3
"""youtuber.csv / vtuber.csv の人物の「イメージカラー」を公式サイトから集める。

生成カード(gen_youtuber_cards.py)の配色に本人の色を反映するための下ごしらえ。
結果は `tools/youtuber_colors.json` に**出典URL付き**で書き出す。

## 何を取っていて、何を取っていないか(ADR 00018)

- 取るのは**色そのもの(16進値)というテキスト情報だけ**。色はアイデア・事実の
  領域で著作物ではないので、イラストの複製とは別物として扱える
- 取得元は2種類。どちらも「タレント名と色の対応表」を公式が公表しているもの:
  1. 色を**テキスト**で書いている公式サイト(HTMLのdata属性・CSS変数・inline style)
  2. 公式ライブの**ペンライトカラー一覧画像**。これは対応表を画像で提示している
     だけで表現ではないので、色見本の矩形から代表色を読み取ってよい
- **キャラクターイラスト/アバターからのパレット抽出は一切しない**。イラストは
  創作的表現であり、そこから色を採ると表現に依拠している疑いが残る
- 取得した画像は `tools/.cache/`(Git管理外)止まり。**リポジトリに置かない・
  再配布しない**。コミットするのは色の値だけ
- ファンwikiやまとめサイトは出典にしない(公式の発表ではないため)
- **youtuber.csv / vtuber.csv に載っている人の分だけを保存する**。事務所のメンバー一覧を
  丸ごと複製する形にはしない

## 取得できないことが分かっているもの

- **にじさんじ**: 公式ペンライトカラーはライブの日程ごとの公式X投稿の本文でしか
  公表されておらず、にじフェスの特設サイトには記載自体が無い。しかも公表されるのは
  「HOT PINK」のような色名だけで、色名と実際の色の対応表(色見本)も公式には
  出ていないので hex にできない
- **ホロスターズ / KAMITSUBAKI / ドズル社 / のりプロ**: 公式サイトにタレント色
  の記載が無い(WordPress既定パレットの色しか出てこない)
- **774inc. / .LIVE(vrlive.party)**: メンバー一覧がクライアントサイドJSで
  描画されるため、HTMLを取ってきても色が入っていない。ヘッドレスブラウザを
  持ち込んでまで取りにはいかない
- Wikidata の P462(色) / P465(sRGB) は対象者に1件も付いていない

usage:
  python3 tools/fetch_youtuber_colors.py            # 取得して JSON を更新
  python3 tools/fetch_youtuber_colors.py --report   # 照合結果を1件ずつ表示
  python3 tools/fetch_youtuber_colors.py --audit    # 画像から読んだ色を全件表示
  python3 tools/fetch_youtuber_colors.py --refresh  # キャッシュを捨てて再取得

ペンライトカラー一覧画像の読み取りには Pillow が要る(`pip install Pillow`)。
無いときはエラーで止まる。黙って飛ばすとJSONから色が静かに消えるため。
"""

import argparse
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

from creator_csv import CSV_PATHS, read_creator_csvs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = Path(__file__).resolve().parent / "youtuber_colors.json"
CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "youtuber_colors"

UA = {"User-Agent": "soramimic-wordlists-updater/1.0 "
                    "(https://github.com/soramimic/soramimic-wordlists)"}

README = (
    "youtuber.csv / vtuber.csv の人物のイメージカラー。tools/fetch_youtuber_colors.py が生成する。"
    "出典は公式が公表している『タレント名と色の対応表』のみ("
    "source=official は色をテキストで書いている公式サイト、"
    "official-penlight は公式ライブのペンライトカラー一覧画像、"
    "manual は人手で確認したもの)。"
    "にじさんじの公式プロフィール色は tools/update_nijisanji.py が補完する。"
    "キャラクターイラストからの色抽出はしていない。primary/secondary は16進表記。"
    "詳細は docs/adr/00018-youtuber-images.md を参照。"
)


def norm_name(name: str) -> str:
    """公式サイトの表記を youtuber.csv / vtuber.csv の original に寄せる(空白除去)。"""
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

# --- 公式ライブのペンライトカラー一覧画像 ------------------------------------
#
# 「タレント名 → ペンライトの色」の対応表を1枚の画像で公表しているもの。
# 画像は行×列のカードが並んだ表で、各カードの左側に色見本(色名を白抜きした
# 単色の矩形)が置かれている。その矩形の代表色(最頻色)を読み取る。
#
# CELLS はカードの並び順そのままの (行, 列, タレント名, 色名)。**タレント名と
# 色名は画像を目視して書き写したもの**で、色名は読み取り精度の検算に使う
# (同じ色名のカードから違う色が出たら、座標がずれているのでエラーにする)。
HOLOLIVE_7TH_FES = {
    "key": "hololive7thfes",
    "name": "hololive 7th fes. Ridin' on Dreams 公式ペンライトカラー",
    "url": "https://hololivesuperexpo.hololivepro.com/2026/fes/cast/",
    "image": "https://hololivesuperexpo.hololivepro.com/2026/wp-content/"
             "themes/expofes2026/images/contents/"
             "7thfes_penlightcolors_banner_260114.webp",
    "ext": "webp",
    # 色見本の矩形。x0,y0 は左上のカードの矩形の左上角、px,py はカードの間隔
    "grid": {"x0": 45, "y0": 52, "px": 265.0, "py": 111.14, "w": 80, "h": 88},
    "cells": [
        (0, 2, "ときのそら", "BLUE"),
        (0, 3, "ロボ子さん", "PINK"),
        (0, 4, "AZKi", "PINK"),
        (0, 5, "さくらみこ", "LIGHT PINK"),
        (0, 6, "星街すいせい", "BLUE"),
        (1, 0, "アキ・ローゼンタール", "LIGHT GREEN"),
        (1, 1, "白上フブキ", "WHITE"),
        (1, 2, "夏色まつり", "ORANGE"),
        (1, 3, "百鬼あやめ", "RED"),
        (1, 4, "癒月ちょこ", "PINK"),
        (1, 5, "大空スバル", "YELLOW"),
        (1, 6, "大神ミオ", "GREEN"),
        (2, 0, "猫又おかゆ", "PURPLE"),
        (2, 1, "兎田ぺこら", "LIGHT BLUE"),
        (2, 2, "不知火フレア", "ORANGE"),
        (2, 3, "白銀ノエル", "WHITE"),
        (2, 4, "宝鐘マリン", "RED"),
        (2, 5, "角巻わため", "YELLOW"),
        (2, 6, "常闇トワ", "VIOLET"),
        (3, 0, "姫森ルーナ", "LIGHT PINK"),
        (3, 1, "雪花ラミィ", "LIGHT BLUE"),
        (3, 2, "桃鈴ねね", "ORANGE"),
        (3, 3, "獅白ぼたん", "WHITE"),
        (3, 4, "尾丸ポルカ", "RED"),
        (3, 5, "ラプラス・ダークネス", "PURPLE"),
        (3, 6, "鷹嶺ルイ", "RED"),
        (4, 0, "博衣こより", "LIGHT PINK"),
        (4, 1, "風真いろは", "LIGHT GREEN"),
        (4, 2, "アユンダ・リス", "LIGHT PINK"),
        (4, 3, "ムーナ・ホシノヴァ", "PURPLE"),
        (4, 4, "アイラニ・イオフィフティーン", "GREEN"),
        (4, 5, "クレイジー・オリー", "RED"),
        (4, 6, "アーニャ・メルフィッサ", "YELLOW"),
        (5, 0, "パヴォリア・レイネ", "BLUE"),
        (5, 1, "ベスティア・ゼータ", "WHITE"),
        (5, 2, "カエラ・コヴァルスキア", "RED"),
        (5, 3, "こぼ・かなえる", "LIGHT BLUE"),
        (5, 4, "森カリオペ", "LIGHT PINK"),
        (5, 5, "小鳥遊キアラ", "ORANGE"),
        (5, 6, "一伊那尓栖", "VIOLET"),
        (6, 0, "IRyS", "PINK"),
        (6, 1, "オーロ・クロニー", "BLUE"),
        (6, 2, "ハコス・ベールズ", "RED"),
        (6, 3, "シオリ・ノヴェラ", "WHITE"),
        (6, 4, "古石ビジュー", "PURPLE"),
        (6, 5, "ネリッサ・レイヴンクロフト", "BLUE"),
        (6, 6, "フワワ・アビスガード", "LIGHT BLUE"),
        (7, 0, "モココ・アビスガード", "LIGHT PINK"),
        (7, 1, "エリザベス・ローズ・ブラッドフレイム", "RED"),
        (7, 2, "ジジ・ムリン", "ORANGE"),
        (7, 3, "セシリア・イマーグリーン", "GREEN"),
        (7, 4, "ラオーラ・パンテーラ", "PINK"),
        (7, 5, "音乃瀬奏", "YELLOW"),
        (7, 6, "一条莉々華", "PINK"),
        (8, 0, "儒烏風亭らでん", "GREEN"),
        (8, 1, "轟はじめ", "PURPLE"),
        (8, 2, "響咲リオナ", "PINK"),
        (8, 3, "虎金妃笑虎", "RED"),
        (8, 4, "水宮枢", "LIGHT BLUE"),
        (8, 5, "輪堂千速", "LIGHT GREEN"),
        (8, 6, "綺々羅々ヴィヴィ", "LIGHT PINK"),
    ],
}

# 6th fes.(1年前)。7th fes. に出ていない人を埋めるために併用する。色見本が
# カードの右側にあるレイアウトで、行列の刻みも違うので grid は別に持つ
HOLOLIVE_6TH_FES = {
    "key": "hololive6thfes",
    "name": "hololive 6th fes. Color Rise Harmony 公式ペンライトカラー",
    "url": "https://hololivesuperexpo2025.hololivepro.com/fes/cast",
    "image": "https://hololivesuperexpo2025.hololivepro.com/wp-content/"
             "themes/hololiveexpofes2025/images/penlight_fix_02.webp",
    "ext": "webp",
    "grid": {"x0": 214, "y0": 80, "px": 262.17, "py": 104.86,
             "w": 78, "h": 80},
    "cells": [
        (0, 3, "ときのそら", "BLUE"),
        (0, 4, "ロボ子さん", "PINK"),
        (0, 5, "AZKi", "PINK"),
        (0, 6, "さくらみこ", "LIGHT PINK"),
        (1, 0, "星街すいせい", "BLUE"),
        (1, 1, "アキ・ローゼンタール", "LIGHT GREEN"),
        (1, 2, "赤井はあと", "RED"),
        (1, 3, "白上フブキ", "WHITE"),
        (1, 4, "夏色まつり", "ORANGE"),
        (1, 5, "紫咲シオン", "PURPLE"),
        (1, 6, "百鬼あやめ", "RED"),
        (2, 0, "癒月ちょこ", "PINK"),
        (2, 1, "大空スバル", "YELLOW"),
        (2, 2, "大神ミオ", "GREEN"),
        (2, 3, "猫又おかゆ", "PURPLE"),
        (2, 4, "戌神ころね", "YELLOW"),
        (2, 5, "兎田ぺこら", "LIGHT BLUE"),
        (2, 6, "不知火フレア", "ORANGE"),
        (3, 0, "白銀ノエル", "WHITE"),
        (3, 1, "宝鐘マリン", "RED"),
        (3, 2, "天音かなた", "LIGHT BLUE"),
        (3, 3, "角巻わため", "YELLOW"),
        (3, 4, "常闇トワ", "VIOLET"),
        (3, 5, "姫森ルーナ", "LIGHT PINK"),
        (3, 6, "雪花ラミィ", "LIGHT BLUE"),
        (4, 0, "桃鈴ねね", "ORANGE"),
        (4, 1, "獅白ぼたん", "WHITE"),
        (4, 2, "尾丸ポルカ", "RED"),
        (4, 3, "ラプラス・ダークネス", "PURPLE"),
        (4, 4, "鷹嶺ルイ", "RED"),
        (4, 5, "博衣こより", "LIGHT PINK"),
        (4, 6, "風真いろは", "LIGHT GREEN"),
        (5, 0, "アユンダ・リス", "LIGHT PINK"),
        (5, 1, "ムーナ・ホシノヴァ", "PURPLE"),
        (5, 2, "アイラニ・イオフィフティーン", "GREEN"),
        (5, 3, "クレイジー・オリー", "RED"),
        (5, 4, "アーニャ・メルフィッサ", "YELLOW"),
        (5, 5, "パヴォリア・レイネ", "BLUE"),
        (5, 6, "ベスティア・ゼータ", "WHITE"),
        (6, 0, "カエラ・コヴァルスキア", "RED"),
        (6, 1, "こぼ・かなえる", "LIGHT BLUE"),
        (6, 2, "森カリオペ", "LIGHT PINK"),
        (6, 3, "小鳥遊キアラ", "ORANGE"),
        (6, 4, "一伊那尓栖", "VIOLET"),
        (6, 5, "がうる・ぐら", "BLUE"),
        (6, 6, "IRyS", "VIOLET"),
        (7, 0, "オーロ・クロニー", "BLUE"),
        (7, 1, "七詩ムメイ", "LIGHT GREEN"),
        (7, 2, "ハコス・ベールズ", "RED"),
        (7, 3, "シオリ・ノヴェラ", "WHITE"),
        (7, 4, "古石ビジュー", "PURPLE"),
        (7, 5, "ネリッサ・レイヴンクロフト", "BLUE"),
        (7, 6, "フワワ・アビスガード", "LIGHT BLUE"),
        (8, 0, "モココ・アビスガード", "LIGHT PINK"),
        (8, 1, "火威青", "BLUE"),
        (8, 2, "音乃瀬奏", "YELLOW"),
        (8, 3, "一条莉々華", "PINK"),
        (8, 4, "儒烏風亭らでん", "GREEN"),
        (8, 5, "轟はじめ", "PURPLE"),
        (8, 6, "ReGLOSS", "WHITE"),     # ユニット枠。人名ではないので一致しない
    ],
}

# 新しい方を先に置く。ペンライトカラーは公演ごとの割り当てなので稀に変わり
# (例: IRyS は 6th=VIOLET, 7th=PINK)、先に入った方を残す
PENLIGHT_SOURCES = [HOLOLIVE_7TH_FES, HOLOLIVE_6TH_FES]
SWATCH_TOLERANCE = 12   # 同じ色名から読んだ色のチャンネル差の許容値

# 自動取得できないが、公式の**テキスト**の記載を人手で確認できたもの。
# 形式: original -> {"primary": "#rrggbb", "secondary": "#rrggbb"(任意),
#                    "source_name": "...", "source_url": "..."}
# 推測色・ファンwiki由来の色は入れないこと(空のままでよい)。
MANUAL: dict[str, dict] = {}


def fetch(url: str, key: str, refresh: bool) -> str:
    """HTMLを取得する(`tools/.cache/` に保存して再開可能・冪等)。"""
    return fetch_bytes(url, key, "html", refresh).decode("utf-8", "replace")


def fetch_bytes(url: str, key: str, ext: str, refresh: bool,
                cache_dir: Path = CACHE_DIR) -> bytes:
    """URLの中身を取得する(`tools/.cache/` に保存して再開可能・冪等)。

    `cache_dir` は取得元ごとに分けられるようにしてある(derive_youtuber_colors.py
    はポートレートを別のディレクトリに貯める)。
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{key}.{ext}"
    if cache.exists() and not refresh:
        return cache.read_bytes()
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as res:
                body = res.read()
            break
        except urllib.error.HTTPError as ex:
            if ex.code == 404:
                raise SystemExit(f"error: 見つからない: {url}")  # 待っても無駄
            print(f"retry {attempt}: {url} ({ex})", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
        except Exception as ex:      # noqa: BLE001 (ネットワーク全般)
            print(f"retry {attempt}: {url} ({ex})", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    else:
        raise SystemExit(f"error: 取得に失敗: {url}")
    cache.write_bytes(body)
    time.sleep(1)                    # 連続アクセスを避ける
    return body


def read_penlight(src: dict, refresh: bool) -> dict:
    """ペンライトカラー一覧画像から「タレント名 -> (色, 色名)」を読み取る。

    各カードの色見本の矩形を少し内側に切って最頻色を採る(色名が白抜きで
    乗っているので、平均ではなく最頻色を使う)。同じ色名のカードからは同じ色が
    出るはずなので、それを検算にして座標ずれを検出する。
    """
    try:
        from PIL import Image
    except ImportError:
        # ここで黙って飛ばすと、JSONから46人分の色が静かに消えてしまう
        raise SystemExit(
            f"error: {src['name']} の読み取りには Pillow が要る"
            "(pip install Pillow)")
    data = fetch_bytes(src["image"], src["key"], src["ext"], refresh)
    im = Image.open(io.BytesIO(data)).convert("RGB")
    g = src["grid"]
    px = im.load()
    samples: dict[str, list] = {}
    for row, col, name, colorname in src["cells"]:
        x0, y0 = int(g["x0"] + col * g["px"]), int(g["y0"] + row * g["py"])
        # 縁の丸み・枠線を避けるため矩形を内側に寄せる
        cnt = Counter(px[x, y]
                      for x in range(x0 + 6, x0 + g["w"] - 6)
                      for y in range(y0 + 8, y0 + g["h"] - 8))
        samples.setdefault(colorname, []).append((name, cnt.most_common(1)[0][0]))

    out = {}
    for colorname, got in sorted(samples.items()):
        rgbs = [rgb for _, rgb in got]
        base = Counter(rgbs).most_common(1)[0][0]
        for name, rgb in got:
            if max(abs(a - b) for a, b in zip(rgb, base)) > SWATCH_TOLERANCE:
                raise SystemExit(
                    f"error: {src['name']} の読み取りがずれている: "
                    f"{name} は {colorname} のはずだが #{rgb[0]:02x}"
                    f"{rgb[1]:02x}{rgb[2]:02x} を読んだ(基準は "
                    f"#{base[0]:02x}{base[1]:02x}{base[2]:02x})")
            out[norm_name(name)] = ("#%02x%02x%02x" % base, colorname)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true",
                    help="キャッシュを無視して取り直す")
    ap.add_argument("--report", action="store_true",
                    help="サイト側にいてCSVに載っていない名前も表示する")
    ap.add_argument("--audit", action="store_true",
                    help="ペンライトカラー画像から読んだ色を全件表示する"
                         "(画像と見比べて検算するため)")
    args = ap.parse_args()

    _, rows = read_creator_csvs(CSV_PATHS)
    originals = {r["original"] for r in rows}

    # 公式名簿updaterが保存したプロフィール色は、このスクリプト単独の再生成でも
    # 落とさない。名簿側が対象の追加・削除を管理する。
    colors: dict[str, dict] = {}
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8")).get("colors", {})
        colors.update({name: entry for name, entry in existing.items()
                       if entry.get("source_name") ==
                       "にじさんじ公式タレントプロフィール"})
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
              f"youtuber.csv / vtuber.csv と一致 {len(hit)}人")
        if args.report and miss:
            print(f"  CSVに居ない(保存しない): {', '.join(miss)}")

    for src in PENLIGHT_SOURCES:
        found = read_penlight(src, args.refresh)
        hit = {n: v for n, v in found.items() if n in originals}
        miss = sorted(set(found) - set(hit))
        for name, (hexcolor, colorname) in sorted(hit.items()):
            # テキストで色を公表しているソースの方が細かいので上書きしない
            colors.setdefault(name, {
                "primary": hexcolor,
                "source": "official-penlight",
                "source_name": src["name"],
                "source_url": src["url"],
                "penlight_color": colorname,
            })
        print(f"{src['name']}: 一覧 {len(found)}人 -> "
              f"youtuber.csv / vtuber.csv と一致 {len(hit)}人")
        if args.report and miss:
            print(f"  CSVに居ない(保存しない): {', '.join(miss)}")
        if args.audit:
            for name, (hexcolor, colorname) in sorted(found.items()):
                mark = " " if name in hit else "-"
                print(f"  {mark} {hexcolor}  {colorname:<12} {name}")

    for name, entry in MANUAL.items():
        if name not in originals:
            print(f"warn: MANUAL の {name} は youtuber.csv / vtuber.csv に居ない",
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
