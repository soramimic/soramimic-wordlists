#!/usr/bin/env python3
"""公式のポートレート画像を**情報解析**して、本人の代表色(最大2色)を求める。

`fetch_youtuber_colors.py` が集めるのは「公式が色を公表している人」の色で、
カード対象712人のうち68人しか埋まらない。残りは事務所ハッシュ由来の機械的な
配色になり、同じ事務所の中では全員が同系色になってしまう。

ここでは**公式サイトのメンバーページに載っているポートレート画像を解析**して、
見た目の印象に近い2色(主色・副色)を機械的に取り出す。

## 法的な整理(著作権法30条の4)

著作物を**情報解析**の用に供する利用は、その著作物に表現された思想又は感情を
自ら享受し又は他人に享受させることを目的としない限り認められる(30条の4第2号)。
画像から代表色を求めるのは統計的な解析であり、出力される数個の16進値は元の
表現との実質的類似性を持たない。よって解析目的での取得・処理は問題ない。

守る制約は次のとおり(詳細は ADR 00018):

- **取得画像を再配布しない**。`tools/.cache/` 止まりで、リポジトリには置かない
- カードは引き続き**自作SVG(色と文字のみ)**。イラストの貼り込み・トレースはしない
- 出力するのは**最大2色**。細かいパレットを再現しない
- 出典URL(メンバーページ)を必ず記録する
- **公式が色そのものを公表している人は公式値を優先**し、解析値で上書きしない

## 対象を VTuber に限る理由

ポートレートが**デザインされたキャラクタービジュアル**である人(VTuber)は、
髪・衣装の主要色がそのまま「その人の色」として通じる。一方、実在YouTuberの
宣材写真から色を採ると、肌・髪(黒)・背景しか出ず、全員が似た茶褐色になって
情報量が増えない。よって `category=vtuber` の行だけを対象にする。

## 抽出の手順

1. 画像を長辺160pxに縮小(以降の処理はすべて決定的で、実行のたびに同じ値が出る)
2. **背景を落とす**。アルファがあれば透明部分、無ければ画像の縁から
   フラッドフィルして単色・グラデーションの背景を取り除く
3. 画素ごとに重みを付ける。**彩度が高いほど重く**し、アニメ塗りの
   **肌色帯・線画の黒・ハイライトの白は軽く**する(肌や影が主色にならないように)
4. CIELAB空間で重み付きk-means(k=6, 決定的な初期化)
5. 面積比(重み)の大きいクラスタを主色、そこから ΔE00 で十分離れた
   2番目に大きいクラスタを副色にする

usage:
  python3 tools/derive_youtuber_colors.py             # 取得して JSON を更新
  python3 tools/derive_youtuber_colors.py --validate  # 公式色が既知の人で検算
  python3 tools/derive_youtuber_colors.py --audit     # 抽出結果を全件表示
  python3 tools/derive_youtuber_colors.py --refresh   # キャッシュを捨てて取り直す
  python3 tools/derive_youtuber_colors.py --swatches out.html  # 目視確認用HTML

画像の解析には Pillow が要る(`pip install Pillow`)。無いときはエラーで止まる。
"""

import argparse
import colorsys
import csv
import hashlib
import io
import json
import math
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_youtuber_colors import fetch_bytes, norm_name  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "youtuber.csv"
COLORS_PATH = Path(__file__).resolve().parent / "youtuber_colors.json"
# 取得したポートレートの置き場。**Git管理外**(.gitignore 済み)。再配布しない
CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "youtuber_portraits"

SOURCE_TAG = "derived-portrait"     # 公式公表値(official*)と区別するための印

# --- 解析パラメータ(すべて決定的) ------------------------------------------
THUMB = 160          # 解析に使う画像の長辺
ALPHA_BG = 128       # これ未満のアルファは背景とみなす
FLOOD_LOCAL = 20     # フラッドフィルで「隣と同じ色」とみなすRGB距離
FLOOD_GLOBAL = 110   # 種(縁の画素)からどこまで離れた色まで背景と認めるか
MAX_BG_RATIO = 0.94  # 背景がこれを超えたら塗りつぶし過ぎとみなし、背景除去を諦める
MIN_FG_RATIO = 0.05  # 前景がこれ未満なら抽出しない(画像が壊れている等)
QUANT = 5            # 色ヒストグラムの量子化ビット数(チャンネルあたり)
KMEANS_K = 6
KMEANS_ITERS = 40
SECOND_MIN_DE = 22.0   # 副色は主色からこれ以上離れていること(ΔE00)
SECOND_MIN_SHARE = 0.08   # 副色は前景の重みのこれ以上を占めること


# --- 色空間 ------------------------------------------------------------------

def _srgb_lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_lab(rgb) -> tuple:
    """sRGB(0-255) -> CIELAB(D65)。"""
    r, g, b = (_srgb_lin(v / 255) for v in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e00(lab1, lab2) -> float:
    """CIEDE2000 色差。1〜2が「注意して見れば違いが分かる」程度。"""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    cbar = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(cbar ** 7 / (cbar ** 7 + 25 ** 7))) if cbar else 0.5
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0.0

    dlp = l2 - l1
    dcp = c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dHp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2)

    lbar = (l1 + l2) / 2
    cbarp = (c1p + c2p) / 2
    if c1p * c2p == 0:
        hbarp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbarp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbarp = (h1p + h2p + 360) / 2
    else:
        hbarp = (h1p + h2p - 360) / 2

    t = (1 - 0.17 * math.cos(math.radians(hbarp - 30))
         + 0.24 * math.cos(math.radians(2 * hbarp))
         + 0.32 * math.cos(math.radians(3 * hbarp + 6))
         - 0.20 * math.cos(math.radians(4 * hbarp - 63)))
    dtheta = 30 * math.exp(-(((hbarp - 275) / 25) ** 2))
    rc = 2 * math.sqrt(cbarp ** 7 / (cbarp ** 7 + 25 ** 7)) if cbarp else 0.0
    sl = 1 + (0.015 * (lbar - 50) ** 2) / math.sqrt(20 + (lbar - 50) ** 2)
    sc = 1 + 0.045 * cbarp
    sh = 1 + 0.015 * cbarp * t
    rt = -math.sin(math.radians(2 * dtheta)) * rc
    return math.sqrt((dlp / sl) ** 2 + (dcp / sc) ** 2 + (dHp / sh) ** 2
                     + rt * (dcp / sc) * (dHp / sh))


def hex_to_rgb(value: str):
    v = (value or "").strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        return None
    try:
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def rgb_to_hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in rgb)


# --- 背景除去 ----------------------------------------------------------------

def foreground_mask(im) -> list:
    """前景かどうかの真偽値を画素順に並べたリストを返す。

    アルファがあれば透明部分を背景にする。無ければ画像の**縁**から
    フラッドフィルして、単色・グラデーションの背景を取り除く。
    「隣の画素と近ければ背景を広げる」ので、グラデーション背景にも追随しつつ、
    キャラクターの輪郭線で止まる。内側にある白(白髪など)は残る。
    """
    w, h = im.size
    px = im.load()
    n = w * h
    alpha = [px[x, y][3] for y in range(h) for x in range(w)]
    if sum(1 for a in alpha if a < ALPHA_BG) > n * 0.02:
        return [a >= ALPHA_BG for a in alpha]

    rgb = [px[x, y][:3] for y in range(h) for x in range(w)]
    bg = [False] * n
    stack = []
    for x in range(w):
        for i in (x, (h - 1) * w + x):
            if not bg[i]:
                bg[i] = True
                stack.append((i, rgb[i]))
    for y in range(h):
        for i in (y * w, y * w + w - 1):
            if not bg[i]:
                bg[i] = True
                stack.append((i, rgb[i]))
    seeds = [rgb[i] for i, _ in stack]
    seed = (sum(c[0] for c in seeds) / len(seeds),
            sum(c[1] for c in seeds) / len(seeds),
            sum(c[2] for c in seeds) / len(seeds))
    while stack:
        i, cur = stack.pop()
        x, y = i % w, i // w
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            j = ny * w + nx
            if bg[j]:
                continue
            c = rgb[j]
            if (abs(c[0] - cur[0]) + abs(c[1] - cur[1]) + abs(c[2] - cur[2])
                    <= FLOOD_LOCAL * 3
                    and abs(c[0] - seed[0]) + abs(c[1] - seed[1])
                    + abs(c[2] - seed[2]) <= FLOOD_GLOBAL * 3):
                bg[j] = True
                stack.append((j, c))
    if sum(bg) > n * MAX_BG_RATIO:
        return [True] * n          # 塗りつぶし過ぎ。背景除去を諦める
    return [not b for b in bg]


# --- 画素の重み --------------------------------------------------------------

def is_skin(rgb) -> bool:
    """アニメ塗りの肌色(淡いオレンジ)か。

    彩度の上限を切ってあるので、オレンジ髪・赤髪のような**鮮やかな暖色**は
    肌とみなさない。
    """
    r, g, b = (v / 255 for v in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    sat = (mx - mn) / mx if mx else 0.0
    hue = colorsys.rgb_to_hsv(r, g, b)[0] * 360
    return 10 <= hue <= 45 and 0.05 <= sat <= 0.38 and mx >= 0.68


def pixel_weight(rgb) -> float:
    """その画素が「その人の色」をどれだけ代表するかの重み。

    - **彩度が高い画素を重く**する。淡い肌色や影が主色になるのを防ぐ
    - **肌色帯**は明示的に軽くする
    - **線画の黒**と**ハイライトの白**も軽くする(面積のわりに情報量が無い)
    """
    r, g, b = (v / 255 for v in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    chroma = mx - mn
    w = 0.22 + 1.7 * chroma
    if is_skin(rgb):
        w *= 0.10
    if mx < 0.16:
        w *= 0.35          # 線画・影
    elif mx > 0.94 and chroma < 0.06:
        w *= 0.45          # ハイライト・白目
    return w


# --- k-means -----------------------------------------------------------------

def histogram(im, mask) -> list:
    """前景の画素を量子化して [(重み, 画素数, 平均RGB), ...] にまとめる。

    重みは**ビンごとに1回だけ**求める(画素ごとに計算すると 160x160 でも
    無視できない時間になるため)。ビンは 2^QUANT 段階なので、同じビンの画素は
    どのみち同じ重みになる。
    """
    w, h = im.size
    px = im.load()
    shift = 8 - QUANT
    bins: dict = {}
    i = 0
    for y in range(h):
        for x in range(w):
            if mask[i]:
                r, g, b = px[x, y][:3]
                key = (r >> shift, g >> shift, b >> shift)
                slot = bins.get(key)
                if slot is None:
                    bins[key] = [1, r, g, b]
                else:
                    slot[0] += 1
                    slot[1] += r
                    slot[2] += g
                    slot[3] += b
            i += 1
    out = []
    for n, sr, sg, sb in bins.values():
        rgb = (sr / n, sg / n, sb / n)
        out.append((pixel_weight(rgb) * n, n, rgb))
    return out


def _sq(lab1, lab2) -> float:
    """CIELAB のユークリッド距離の2乗(ΔE76相当)。

    クラスタリングの内側は呼び出し回数が多いのでこちらを使う。知覚的な
    「離れているか」の判定(副色を主色と区別するところ)だけ ΔE00 を使う。
    """
    return ((lab1[0] - lab2[0]) ** 2 + (lab1[1] - lab2[1]) ** 2
            + (lab1[2] - lab2[2]) ** 2)


def kmeans(points: list, k: int) -> list:
    """重み付きk-means(CIELAB)。points は (weight, lab, rgb)。

    初期値は「重み最大の点」→「既存中心から離れていて重い点」の順に決定的に
    選ぶ(乱数を使わないので、同じ画像からは毎回同じ色が出る = 冪等)。
    """
    if not points:
        return []
    k = min(k, len(points))
    centers = [max(points, key=lambda p: (p[0], p[1]))[1]]
    while len(centers) < k:
        best = max(points, key=lambda p: (
            p[0] * min(_sq(p[1], c) for c in centers), p[1]))
        if best[1] in centers:
            break
        centers.append(best[1])
    assign = [0] * len(points)
    for _ in range(KMEANS_ITERS):
        moved = False
        for i, (_wt, lab, _rgb) in enumerate(points):
            j = min(range(len(centers)),
                    key=lambda c: _sq(lab, centers[c]))
            if j != assign[i]:
                assign[i] = j
                moved = True
        sums = [[0.0, 0.0, 0.0, 0.0] for _ in centers]
        for i, (wt, lab, _rgb) in enumerate(points):
            s = sums[assign[i]]
            s[0] += wt
            s[1] += wt * lab[0]
            s[2] += wt * lab[1]
            s[3] += wt * lab[2]
        for j, s in enumerate(sums):
            if s[0]:
                centers[j] = (s[1] / s[0], s[2] / s[0], s[3] / s[0])
        if not moved:
            break
    out = []
    for j in range(len(centers)):
        members = [points[i] for i in range(len(points)) if assign[i] == j]
        wt = sum(p[0] for p in members)
        if wt <= 0:
            continue
        # クラスタの代表色は**平均ではなく最頻の色**にする。平均を採ると
        # 「明るい髪 + その影」が混ざって、実際には画面のどこにも無い
        # くすんだ色になってしまう
        peak = max(members, key=lambda p: (p[0], p[2]))
        # 最頻色の近くにある色だけを平均して、量子化のがたつきをならす
        near = [p for p in members if _sq(p[1], peak[1]) <= 12 ** 2]
        nw = sum(p[0] for p in near)
        rgb = tuple(sum(p[0] * p[2][c] for p in near) / nw for c in range(3))
        out.append((wt, rgb))
    out.sort(key=lambda c: (-c[0], c[1]))
    return merge_close(out)


MERGE_DE = 12.0     # これより近いクラスタは同じ色とみなしてまとめる


def merge_close(clusters: list) -> list:
    """見分けが付かないほど近いクラスタをまとめる。

    k-means は「明るい髪」と「その少し暗い部分」を別クラスタに割ることがあり、
    そのまま面積比を比べると、割れなかった小さい色に順位を抜かれてしまう。
    重い方の代表色を残したまま重みだけ足す。
    """
    out: list = []
    for wt, rgb in clusters:      # 重い順に来る
        lab = rgb_to_lab(rgb)
        for i, (owt, orgb) in enumerate(out):
            if delta_e00(rgb_to_lab(orgb), lab) < MERGE_DE:
                out[i] = (owt + wt, orgb)
                break
        else:
            out.append((wt, rgb))
    out.sort(key=lambda c: (-c[0], c[1]))
    return out


def extract(data: bytes) -> dict | None:
    """画像バイト列 -> {"primary": "#..", "secondary": "#..", "clusters": [...]}。"""
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im = im.convert("RGBA")
    im.thumbnail((THUMB, THUMB), Image.LANCZOS)
    mask = foreground_mask(im)
    if sum(mask) < len(mask) * MIN_FG_RATIO:
        return None
    bins = histogram(im, mask)
    if not bins:
        return None
    points = [(wt, rgb_to_lab(rgb), rgb) for wt, _n, rgb in bins if wt > 0]
    clusters = kmeans(points, KMEANS_K)
    if not clusters:
        return None
    total = sum(wt for wt, _ in clusters)
    # 肌のクラスタは主色・副色の候補から外す。重みを下げるだけでは、顔の
    # 面積が大きい「顔アップ」のポートレートで肌が勝ってしまうことがある
    pick = [c for c in clusters if not is_skin(c[1])] or clusters
    primary = pick[0][1]
    plab = rgb_to_lab(primary)
    secondary = None
    for wt, rgb in pick[1:]:
        if wt < total * SECOND_MIN_SHARE:
            continue
        if delta_e00(plab, rgb_to_lab(rgb)) >= SECOND_MIN_DE:
            secondary = rgb
            break
    out = {"primary": rgb_to_hex(primary),
           "clusters": [(round(wt / total, 3), rgb_to_hex(rgb))
                        for wt, rgb in clusters],
           "fg_ratio": round(sum(mask) / len(mask), 3)}
    if secondary:
        out["secondary"] = rgb_to_hex(secondary)
    return out


# --- ポートレートの取得元 -----------------------------------------------------
#
# 1件=1事務所の公式メンバーページ。parse は HTML(str) を受け取り
# {表示名: 画像URL} を返す。**画像は解析にしか使わない**(再配布しない)。

def parse_nijisanji(html: str) -> dict:
    """にじさんじ公式の所属ライバー一覧(Next.js の __NEXT_DATA__)。

    `allLivers[].name` が日本語名、`images.head.url` が顔のポートレート。
    URLは画像プロキシへの相対パスなので、サイトのオリジンを足す。
    """
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">'
                  r'(.*?)</script>', html, re.S)
    if not m:
        return {}
    data = json.loads(m.group(1))
    out = {}
    for liver in data["props"]["pageProps"].get("allLivers", []):
        url = (liver.get("images") or {}).get("head", {}).get("url")
        if not url or not liver.get("name"):
            continue
        out[norm_name(liver["name"])] = urllib.parse.urljoin(
            "https://www.nijisanji.jp/", url)
    return out


def _wp_talent_list(html: str, host: str, seg: str) -> dict:
    """hololive系(WordPress)のタレント一覧。

    `<a href=".../talents/slug/"><figure><img src="...thumb.png"></figure>
     <h3>名前<span>English</span></h3></a>` の形。HOLOSTARS はパスが
    `/talent/` で、活動終了者に `【配信活動終了】` の前置きが付く。
    """
    pat = re.compile(
        r'<a href="https://' + re.escape(host) + "/" + re.escape(seg) +
        r'/[^"]+">\s*<figure>\s*<img[^>]*\ssrc="([^"]+)"[^>]*>\s*'
        r'</figure>\s*<h3>\s*(.+?)\s*</h3>', re.S)
    out = {}
    for url, name in pat.findall(html):
        name = re.sub(r"<span>.*", "", name, flags=re.S)
        name = re.sub(r"^【[^】]*】\s*", "", name).strip()
        if name:
            out.setdefault(norm_name(name), url)
    return out


def parse_hololive(html: str) -> dict:
    return _wp_talent_list(html, "hololive.hololivepro.com", "talents")


def parse_holostars(html: str) -> dict:
    return _wp_talent_list(html, "holostars.hololivepro.com", "talent")


def parse_vspo(html: str) -> dict:
    """ぶいすぽっ！公式トップ。`data-name` の要素の中にポートレートがある。"""
    out = {}
    for m in re.finditer(
            r'data-name="([^"]+)"(?:(?!data-name=).){0,4000}?'
            r'<img[^>]*\ssrc="([^"]+\.(?:png|jpg|jpeg|webp))"', html, re.S):
        out.setdefault(norm_name(m.group(1)),
                       urllib.parse.urljoin("https://vspo.jp/", m.group(2)))
    return out


def parse_aogiri(html: str) -> dict:
    """あおぎり高校公式トップ。メンバーへのリンクの中の img が立ち絵。

    HTMLに埋まっているパスには `/aogirihighschool` という接頭辞が付いているが、
    実際に配信されているのはそれを外したパス(ビルド時のbaseURLの名残)。
    """
    out = {}
    for m in re.finditer(
            r'href="/aogirihighschool/members/[a-z0-9_-]+"[^>]*>\s*'
            r'<img[^>]*\ssrc="([^"]+)"[^>]*\salt="([^"]+)"', html, re.S):
        path = re.sub(r"^/aogirihighschool/", "/", m.group(1))
        out.setdefault(norm_name(m.group(2)), urllib.parse.urljoin(
            "https://www.aogirihighschool.com/", path))
    return out


def parse_neoporte(html: str) -> dict:
    """Neo-Porte公式のメンバー一覧。"""
    out = {}
    for m in re.finditer(
            r'<img[^>]*\ssrc="([^"]+)"[^>]*\salt="([^"]+)"', html, re.S):
        if "/member" in m.group(1) or "/talent" in m.group(1):
            out.setdefault(norm_name(m.group(2)), urllib.parse.urljoin(
                "https://neo-porte.jp/member/", m.group(1)))
    return out


PORTRAIT_SOURCES = [
    {
        "key": "nijisanji",
        "name": "にじさんじ公式サイト 所属ライバー一覧",
        "url": "https://www.nijisanji.jp/talents",
        "parse": parse_nijisanji,
    },
    {
        "key": "hololive",
        "name": "ホロライブプロダクション公式サイト タレント一覧",
        "url": "https://hololive.hololivepro.com/talents/",
        "parse": parse_hololive,
    },
    {
        "key": "holostars",
        "name": "HOLOSTARS公式サイト タレント一覧",
        "url": "https://holostars.hololivepro.com/talent",
        "parse": parse_holostars,
    },
    {
        "key": "vspo",
        "name": "ぶいすぽっ！公式サイト",
        "url": "https://vspo.jp/",
        "parse": parse_vspo,
    },
    {
        "key": "aogiri",
        "name": "あおぎり高校公式サイト",
        "url": "https://www.aogirihighschool.com/",
        "parse": parse_aogiri,
    },
    {
        "key": "neoporte",
        "name": "Neo-Porte公式サイト",
        "url": "https://neo-porte.jp/member/",
        "parse": parse_neoporte,
    },
]


def collect_portraits(refresh: bool, verbose: bool) -> dict:
    """{名前: {"image", "source", "source_name", "source_url"}}。

    同じ名前が複数の事務所ページに出てきたら、**取り違えを避けるため捨てる**。
    """
    found: dict[str, list] = {}
    for src in PORTRAIT_SOURCES:
        html = fetch_bytes(src["url"], src["key"], "html", refresh,
                           CACHE_DIR).decode("utf-8", "replace")
        got = src["parse"](html)
        if not got:
            print(f"error: {src['name']} からポートレートを1件も取れなかった"
                  "(サイト構造が変わった可能性)", file=sys.stderr)
            return {}
        print(f"{src['name']}: {len(got)}人分のポートレート")
        if verbose:
            print("   " + ", ".join(sorted(got)[:8]) + " ...")
        for name, url in got.items():
            found.setdefault(name, []).append((src, url))

    out = {}
    for name, hits in sorted(found.items()):
        if len({s["key"] for s, _ in hits}) > 1:
            print(f"warn: {name} が複数の事務所ページに出てくる。曖昧なので使わない",
                  file=sys.stderr)
            continue
        src, url = hits[0]
        out[name] = {"image": url, "source_key": src["key"],
                     "source_name": src["name"], "source_url": src["url"]}
    return out


def load_targets() -> dict:
    """youtuber.csv の original -> category。"""
    with CSV_PATH.open(encoding="utf-8") as fh:
        return {r["original"]: r["category"] for r in csv.DictReader(fh)}


def load_colors() -> dict:
    data = json.loads(COLORS_PATH.read_text(encoding="utf-8"))
    return data


def portrait_bytes(name: str, entry: dict, refresh: bool) -> bytes | None:
    """ポートレートを取得する(`tools/.cache/` 止まり。再配布しない)。"""
    ext = Path(urllib.parse.urlparse(entry["image"]).path).suffix.lstrip(".")
    if ext.lower() not in ("png", "jpg", "jpeg", "webp", "gif"):
        ext = "img"
    # 名前をそのままファイル名にせず、決定的な英数キーにする(冪等)
    key = "{}_{}".format(
        entry["source_key"],
        hashlib.sha1(name.encode("utf-8")).hexdigest()[:12])
    try:
        return fetch_bytes(entry["image"], key, ext, refresh, CACHE_DIR)
    except SystemExit as ex:
        print(f"warn: {name} のポートレートを取得できない ({ex})", file=sys.stderr)
        return None


def swatch_html(rows: list) -> str:
    """目視確認用のHTML。**画像は貼らず**、抽出した色だけを並べる。"""
    parts = ["<!doctype html><meta charset='utf-8'>",
             "<style>body{font:14px system-ui;background:#fff}"
             "table{border-collapse:collapse}td{padding:4px 8px;"
             "border-bottom:1px solid #eee}.sw{display:inline-block;width:52px;"
             "height:26px;border:1px solid #0002;vertical-align:middle}</style>",
             "<h1>youtuber 抽出色(目視確認用)</h1><table>"]
    for name, primary, secondary, extra in rows:
        s2 = (f"<span class=sw style='background:{secondary}'></span> "
              f"{secondary}") if secondary else ""
        parts.append(
            f"<tr><td>{name}</td>"
            f"<td><span class=sw style='background:{primary}'></span> "
            f"{primary}</td><td>{s2}</td><td>{extra}</td></tr>")
    parts.append("</table>")
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true",
                    help="キャッシュを無視して取り直す")
    ap.add_argument("--audit", action="store_true",
                    help="抽出したクラスタを全件表示する")
    ap.add_argument("--validate", action="store_true",
                    help="公式色が既知の人にも抽出をかけ、ΔE00 で手法を検算する"
                         "(JSONは書き換えない)")
    ap.add_argument("--swatches", metavar="PATH",
                    help="抽出色を並べたHTMLを書き出す(目視確認用)")
    ap.add_argument("--limit", type=int, default=0,
                    help="先頭N人だけ処理する(動作確認用)")
    args = ap.parse_args()

    try:
        import PIL  # noqa: F401
    except ImportError:
        raise SystemExit("error: 画像の解析には Pillow が要る"
                         "(pip install Pillow)")

    targets = load_targets()
    data = load_colors()
    colors = data["colors"]
    official = {n for n, v in colors.items()
                if v.get("source", "").startswith("official")
                or v.get("source") == "manual"}

    portraits = collect_portraits(args.refresh, args.audit)
    if not portraits:
        return 1

    # CSVに載っている VTuber だけを相手にする(実在YouTuberの宣材写真からは
    # 肌と黒髪しか出ず、情報量が増えないため)
    hit = {n: e for n, e in portraits.items()
           if targets.get(n) == "vtuber"}
    print(f"\nyoutuber.csv の vtuber と一致: {len(hit)}人"
          f"(サイト側 {len(portraits)}人)")
    if args.validate:
        hit = {n: e for n, e in hit.items() if n in official}
        print(f"検算対象(公式色が既知): {len(hit)}人")
    else:
        skip = sorted(set(hit) & official)
        hit = {n: e for n, e in hit.items() if n not in official}
        print(f"公式色があるので触らない: {len(skip)}人 / 解析対象: {len(hit)}人")
    if args.limit:
        hit = dict(sorted(hit.items())[:args.limit])

    results = {}
    rows = []
    for i, (name, entry) in enumerate(sorted(hit.items()), 1):
        blob = portrait_bytes(name, entry, args.refresh)
        if blob is None:
            continue
        try:
            got = extract(blob)
        except Exception as ex:      # noqa: BLE001 (壊れた画像など)
            print(f"warn: {name} の解析に失敗 ({ex})", file=sys.stderr)
            continue
        if not got:
            print(f"warn: {name} は前景を取り出せなかった", file=sys.stderr)
            continue
        results[name] = (entry, got)
        rows.append((name, got["primary"], got.get("secondary", ""),
                     entry["source_key"]))
        if args.audit:
            print(f"  {name}: " + "  ".join(
                f"{c[1]}({c[0]:.2f})" for c in got["clusters"]))
        if i % 25 == 0:
            print(f"  {i}/{len(hit)}", flush=True)

    if args.swatches:
        Path(args.swatches).write_text(swatch_html(rows), encoding="utf-8")
        print(f"目視確認用HTML: {args.swatches}")

    if args.validate:
        return report_validation(results, colors)

    for name, (entry, got) in results.items():
        rec = {"primary": got["primary"]}
        if got.get("secondary"):
            rec["secondary"] = got["secondary"]
        rec.update({
            "source": SOURCE_TAG,
            "source_name": entry["source_name"],
            "source_url": entry["source_url"],
        })
        colors[name] = rec
    data["colors"] = dict(sorted(colors.items()))
    data["_readme"] = README
    COLORS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    n_derived = sum(1 for v in data["colors"].values()
                    if v.get("source") == SOURCE_TAG)
    print(f"\n{COLORS_PATH.relative_to(ROOT)}: 全{len(data['colors'])}人"
          f"(うち解析由来 {n_derived}人)")
    return 0


README = (
    "youtuber.csv の人物のイメージカラー。primary/secondary は16進表記。"
    "source=official は色をテキストで公表している公式サイト、"
    "official-penlight は公式ライブのペンライトカラー一覧画像、"
    "manual は人手で確認したもの(いずれも tools/fetch_youtuber_colors.py)。"
    "source=derived-portrait は公式ポートレート画像を情報解析(著作権法30条の4)"
    "して求めた代表色(tools/derive_youtuber_colors.py)。"
    "解析に使った画像は tools/.cache/ 止まりで再配布しておらず、"
    "カードは配色と文字だけの自作SVGのまま。"
    "詳細は docs/adr/00018-youtuber-images.md を参照。"
)


# ペンライト12色の「色相の系統」。LIGHT 付きは明度違いなので同じ系統にまとめる
PENLIGHT_FAMILY = {
    "RED": "赤", "ORANGE": "橙", "YELLOW": "黄",
    "GREEN": "緑", "LIGHT GREEN": "緑",
    "BLUE": "青", "LIGHT BLUE": "青",
    "PURPLE": "紫", "VIOLET": "紫",
    "PINK": "桃", "LIGHT PINK": "桃", "WHITE": "白",
}
# 色相の境界(度)。この上限までがその系統
HUE_BANDS = [(15, "赤"), (45, "橙"), (70, "黄"), (165, "緑"), (255, "青"),
             (290, "紫"), (345, "桃"), (360, "赤")]


def hue_family(rgb) -> str:
    """色を色相の系統に振り分ける。

    ΔE00 で12色パレットの最近傍を採ると**明度に強く引っ張られて**、暗い紺色が
    PURPLE に、暗い灰色が VIOLET に落ちる。系統の一致を見たいので色相で振る。
    """
    r, g, b = (v / 255 for v in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 0.10:
        return "白" if mx > 0.72 else "無彩色"
    hue = colorsys.rgb_to_hsv(r, g, b)[0] * 360
    return next(fam for hi, fam in HUE_BANDS if hue < hi)


def _stats(label: str, des: list) -> None:
    des = sorted(des)
    if not des:
        return
    print(f"\n{label}  n={len(des)}  中央値 {des[len(des) // 2]:.1f} / "
          f"平均 {sum(des) / len(des):.1f}")
    for th in (10, 20, 30):
        n = sum(1 for d in des if d <= th)
        print(f"    ΔE00 <= {th:2d}: {n}/{len(des)} ({n / len(des):.0%})")


def report_validation(results: dict, colors: dict) -> int:
    """公式色が既知の人で、抽出した色が公式値にどれだけ近いかを見る。

    公式値には性質の違う2種類が混ざっているので、分けて集計する。

    - `official`(公式サイトが**テキストで**書いている色)は、そのキャラクター
      デザインから決まった連続値なので、抽出結果と直接比較できる
    - `official-penlight` は12色の離散パレット(RED=#ff0100 など)への割り当て。
      イラストの中にその色が literally 存在するわけではないので、ΔE00 の
      絶対値は大きく出る。こちらは「**12色のうち正しい色に最も近く落ちるか**」
      という分類精度で見る
    """
    palette = {}
    for v in colors.values():
        if v.get("penlight_color"):
            palette.setdefault(v["penlight_color"], v["primary"])

    rows = []
    for name, (_entry, got) in sorted(results.items()):
        want = hex_to_rgb(colors[name]["primary"])
        if not want:
            continue
        wlab = rgb_to_lab(want)
        cands = [(delta_e00(wlab, rgb_to_lab(hex_to_rgb(got["primary"]))),
                  got["primary"], "主色")]
        if got.get("secondary"):
            cands.append(
                (delta_e00(wlab, rgb_to_lab(hex_to_rgb(got["secondary"]))),
                 got["secondary"], "副色"))
        best = min(cands)
        rows.append({
            "de": best[0], "which": best[2], "name": name,
            "want": colors[name]["primary"],
            "cname": colors[name].get("penlight_color", ""),
            "src": colors[name].get("source", ""),
            "primary": got["primary"], "secondary": got.get("secondary", ""),
            "de_primary": cands[0][0],
        })
    if not rows:
        print("検算できる人がいない")
        return 1
    rows.sort(key=lambda r: r["de"])
    print(f"\n{'ΔE00':>6}  {'公式':<9} {'色名':<12} {'主色':<9} {'副色':<9} "
          "近い方  名前")
    for r in rows:
        print(f"{r['de']:6.1f}  {r['want']:<9} {r['cname']:<12} "
              f"{r['primary']:<9} {r['secondary'] or '-':<9} "
              f"{r['which']}  {r['name']}")

    text = [r for r in rows if r["src"] == "official"]
    pen = [r for r in rows if r["src"] == "official-penlight"]
    _stats("公式がテキストで色を書いている人(主色のみ)",
           [r["de_primary"] for r in text])
    _stats("公式がテキストで色を書いている人(2色のうち近い方)",
           [r["de"] for r in text])
    _stats("ペンライトカラー(12色パレット・参考値。主色のみ)",
           [r["de_primary"] for r in pen])
    _stats("ペンライトカラー(12色パレット・参考値。2色のうち近い方)",
           [r["de"] for r in pen])

    if pen and palette:
        names = sorted(palette)
        ok = fam = 0
        wrong = []
        for r in pen:
            lab = rgb_to_lab(hex_to_rgb(r["primary"]))
            got = min(names, key=lambda n: delta_e00(
                rgb_to_lab(hex_to_rgb(palette[n])), lab))
            if got == r["cname"]:
                ok += 1
            want_fam = PENLIGHT_FAMILY.get(r["cname"])
            got_fam = [hue_family(hex_to_rgb(c))
                       for c in (r["primary"], r["secondary"]) if c]
            if want_fam in got_fam:
                fam += 1
            else:
                wrong.append(f"{r['name']}({want_fam}→{'/'.join(got_fam)})")
        n = len(pen)
        print("\n主色を12色パレットに最も近い色名へ寄せたとき:")
        print(f"  色名まで一致 {ok}/{n} ({ok / n:.0%})")
        print(f"抽出した2色のどちらかの色相の系統が公式色と一致: "
              f"{fam}/{n} ({fam / n:.0%})")
        if wrong:
            print("  外れた人: " + ", ".join(wrong))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
