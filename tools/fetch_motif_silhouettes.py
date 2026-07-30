#!/usr/bin/env python3
"""モチーフのシルエットSVGを PhyloPic から取得して images/pokemon_motifs/ に置く。

ポケモンのキャラクター造形は著作物なので使えない(ADR 00002)。代わりに
**モチーフになった生物の汎用シルエット**をカードに添える。ピカチュウなら
ネズミのシルエット、というように「一般的な生物の形」だけを使うので、
ポケモン自身の絵柄は一切複製しない。

- ラベル→学名の対応は tools/motif_taxa.json、ポケモン→ラベルは
  tools/pokemon_motifs.json(架空・非生物のラベルは学名が null で対象外)
- 学名で PhyloPic のノードを引き、そのクレードの画像から
  **パブリックドメイン(CC0 / PD Mark)のものだけ**を選ぶ。CC BY 系は
  帰属表示の義務がカード側に及ぶので採らない(採れなければシルエット無し)
- 取得したSVGは図形要素だけを抜き、座標を丸めて最小限のSVGに作り直す
  (カード1300枚に埋め込むのでサイズを詰める)。塗りはカード側で指定するため
  色は持たせない。**祖先の `<g transform>` は行列に畳んで保持する**
  (無視すると描画が枠外へ飛んで真っ白になる)
- PhyloPicの素材には「背景を白で塗って生物の形を抜く」書き方のものが混ざる。
  白塗りの図形は前景ではないので落とす(`simplify_svg` の mode)。それでも
  塗りが画面全面を覆う素材は単なる黒い矩形になるので、chromeでラスタライズ
  して塗り面積を測って弾く(`inspect_svg`)。線だけの素材や実質空の素材も
  同じ測り方で落とす。chromeが無い環境では検査を飛ばして警告を出すだけに
  する(検査は品質向上のためで、必須依存にしない)
- 出力物: images/pokemon_motifs/<sha1(ラベル)先頭10桁>.svg と、出典を記録した
  tools/motif_silhouettes.json(ラベル→ファイル名・学名・PhyloPicのUUID・
  ライセンス・作者・検査値)。ファイル名をラベルのハッシュにするのは、日本語の
  ファイル名を避けつつラベルと1対1に保つため
- **ドラゴンや妖精のような架空・非生物のモチーフは PhyloPic に無い**ので、
  台帳の `"source": "self"` のエントリだけは**このリポジトリの自作シルエット**
  (CC0)を手で置いている(tools/motif_taxa.json では学名 null のまま)。
  このスクリプトは `--refresh` でも自作エントリとファイルには一切触らない。
  自作素材の描き起こしについては ADR 00033 を参照

usage:
    python3 tools/fetch_motif_silhouettes.py            # 未取得分だけ取得
    python3 tools/fetch_motif_silhouettes.py --refresh  # 全ラベルを取り直す
    python3 tools/fetch_motif_silhouettes.py --only ネズミ,イヌ
    python3 tools/fetch_motif_silhouettes.py --sheet /tmp/sheet.png  # 一覧画像
"""

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAXA_PATH = ROOT / "tools" / "motif_taxa.json"
MANIFEST_PATH = ROOT / "tools" / "motif_silhouettes.json"
OUT_DIR = ROOT / "images" / "pokemon_motifs"

API = "https://api.phylopic.org"
ACCEPT = "application/vnd.phylopic.v2+json"
# パブリックドメインのみ採用する。CC BY / BY-SA は帰属や継承の義務が
# カード(=このリポジトリの配布物)側に及ぶので使わない
PD_LICENSES = {
    "https://creativecommons.org/publicdomain/zero/1.0/",
    "https://creativecommons.org/publicdomain/mark/1.0/",
}
# 1枚あたりのSVG上限。カード1300枚に埋め込むため、細密すぎる素材は使わない
MAX_SVG_BYTES = 24 * 1024
# 1ラベルにつき見る候補画像の数(先頭から順に試して最初に合格したものを採る)
CANDIDATE_LIMIT = 8
# 台帳の source。自作(SELF)のエントリはこのスクリプトの管理外で、消さない
PHYLOPIC_SOURCE = "phylopic"
SELF_SOURCE = "self"

# --- ラスタライズ検査のしきい値(いずれも塗り面積の比) ---
INSPECT_PX = 280
# 外部と繋がった背景がこれ未満 = 画面全面が塗り(白黒反転素材)
MIN_OPEN_RATIO = 0.04
# 塗りがこれ未満 = ほぼ空。取りこぼしか、シルエットにならない細線画
MIN_INK_RATIO = 0.055
# 塗り / (塗り + 囲まれた背景)。低いと「輪郭線だけ」の線画
MIN_SOLIDITY = 0.45

SVG_NS = "{http://www.w3.org/2000/svg}"
# path に変換して取り込む図形要素。取りこぼすと絵が欠ける
SHAPE_TAGS = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
# 参照されるまで描かれない要素・図でない要素は丸ごと飛ばす
SKIP_TAGS = {"defs", "clipPath", "mask", "symbol", "marker", "pattern",
             "filter", "metadata", "title", "desc", "style", "text", "use",
             "image", "switch", "foreignObject", "namedview", "RDF"}
WHITE = {"#fff", "#ffffff", "white"}
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def get_json(path: str) -> dict | list:
    url = path if path.startswith("http") else f"{API}{path}"
    req = urllib.request.Request(url, headers={"Accept": ACCEPT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                return json.loads(res.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 3:
                raise
            print(f"  retry {url}: {exc}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def build_id() -> int:
    return int(get_json("/")["build"])


def find_node(taxon: str, build: int) -> tuple[str, str] | None:
    """学名からノードを引く。(uuid, 表示名) を返す。"""
    q = urllib.parse.urlencode({"build": build, "filter_name": taxon.lower()})
    items = get_json(f"/nodes?{q}&page=0")["_links"].get("items", [])
    if not items:
        return None
    # 完全一致(大文字小文字無視)を優先。無ければ先頭
    best = next(
        (i for i in items if i.get("title", "").lower() == taxon.lower()),
        items[0],
    )
    uuid = best["href"].split("/nodes/", 1)[1].split("?", 1)[0]
    return uuid, best.get("title", taxon)


def pd_images(node_uuid: str, build: int,
              limit: int = CANDIDATE_LIMIT) -> Iterator[dict]:
    """ノードのクレードからパブリックドメインかつSVG素材の画像を順に出す。

    ノードの代表画像(primaryImage)を最優先し、以降はクレードの画像を順に見る。
    **元データがPNGしかない画像は採らない**(シルエットをカードのSVGに
    埋め込むので、ラスタでは使えない)。
    採用できる素材が見つかった時点で打ち切れるよう、遅延評価で1件ずつ返す
    (1件ごとにAPIを叩くので、先読みするとその分だけ遅くなる)。
    """
    node = get_json(f"/nodes/{node_uuid}?build={build}")
    hrefs: list[str] = []
    primary = node["_links"].get("primaryImage")
    if primary:
        hrefs.append(primary["href"])
    q = urllib.parse.urlencode({"build": build, "filter_clade": node_uuid})
    for page in range(3):
        listing = get_json(f"/images?{q}&page={page}")["_links"]
        hrefs += [i["href"] for i in listing.get("items", [])]
        if not listing.get("next"):
            break
    seen: set[str] = set()
    served = 0
    for href in hrefs:
        uuid = href.split("/images/", 1)[1].split("?", 1)[0]
        if uuid in seen:
            continue
        seen.add(uuid)
        img = get_json(href)
        if img["_links"].get("license", {}).get("href") not in PD_LICENSES:
            continue
        source = img["_links"].get("sourceFile") or {}
        if source.get("type") != "image/svg+xml":
            continue
        yield img
        served += 1
        if served >= limit:
            return


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"Accept": "image/svg+xml"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read().decode("utf-8", "replace")


# --------------------------------------------------------------------------
# SVGの解析・再構成
# --------------------------------------------------------------------------
def matmul(m: tuple[float, ...], n: tuple[float, ...]) -> tuple[float, ...]:
    """SVGの行列(a b c d e f)の積。m を適用したあとの座標系に n を掛ける。"""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def parse_transform(text: str) -> tuple[float, ...]:
    """transform 属性の文字列を1つの行列に畳む。"""
    mat = IDENTITY
    for name, args in re.findall(r"([a-zA-Z]+)\s*\(([^)]*)\)", text or ""):
        v = [float(x) for x in re.findall(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?\d+)?",
                                          args)]
        if not v:
            continue
        if name == "translate":
            mat = matmul(mat, (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0))
        elif name == "scale":
            sx = v[0]
            mat = matmul(mat, (sx, 0, 0, v[1] if len(v) > 1 else sx, 0, 0))
        elif name == "matrix" and len(v) >= 6:
            mat = matmul(mat, tuple(v[:6]))
        elif name == "rotate":
            rad = math.radians(v[0])
            cos, sin = math.cos(rad), math.sin(rad)
            rot: tuple[float, ...] = (cos, sin, -sin, cos, 0, 0)
            if len(v) >= 3:  # 回転中心つき
                rot = matmul(matmul((1, 0, 0, 1, v[1], v[2]), rot),
                             (1, 0, 0, 1, -v[1], -v[2]))
            mat = matmul(mat, rot)
        elif name == "skewX":
            mat = matmul(mat, (1, 0, math.tan(math.radians(v[0])), 1, 0, 0))
        elif name == "skewY":
            mat = matmul(mat, (1, math.tan(math.radians(v[0])), 0, 1, 0, 0))
    return mat


def presentation(el: ET.Element) -> dict[str, str]:
    """style 属性と属性値から、描画に効く指定だけを取り出す。"""
    out: dict[str, str] = {}
    for key, value in re.findall(r"([-\w]+)\s*:\s*([^;]+)", el.get("style", "")):
        out[key.strip()] = value.strip()
    for key in ("fill", "fill-rule", "stroke", "stroke-width", "stroke-linecap",
                "stroke-linejoin", "display", "visibility", "opacity"):
        if el.get(key) is not None:
            out.setdefault(key, el.get(key, ""))
    return out


def is_white(color: str | None) -> bool:
    return bool(color) and color.strip().lower() in WHITE


def shape_path(el: ET.Element, tag: str) -> str | None:
    """図形要素を path の d に変換する(path はそのまま)。"""
    if tag == "path":
        return el.get("d")

    def f(key: str) -> float:
        try:
            return float(el.get(key, 0) or 0)
        except ValueError:
            return 0.0

    if tag == "rect":
        x, y, w, h = f("x"), f("y"), f("width"), f("height")
        return f"M{x} {y}H{x + w}V{y + h}H{x}Z" if w > 0 and h > 0 else None
    if tag in ("circle", "ellipse"):
        cx, cy = f("cx"), f("cy")
        rx = f("r") if tag == "circle" else f("rx")
        ry = f("r") if tag == "circle" else f("ry")
        if rx <= 0 or ry <= 0:
            return None
        return (f"M{cx - rx} {cy}a{rx} {ry} 0 1 0 {2 * rx} 0"
                f"a{rx} {ry} 0 1 0 {-2 * rx} 0Z")
    if tag == "line":
        return f"M{f('x1')} {f('y1')}L{f('x2')} {f('y2')}"
    if tag in ("polyline", "polygon"):
        pts = re.findall(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?\d+)?",
                         el.get("points", ""))
        if len(pts) < 4:
            return None
        body = "L".join(f"{pts[i]} {pts[i + 1]}"
                        for i in range(2, len(pts) - 1, 2))
        return f"M{pts[0]} {pts[1]}L{body}" + ("Z" if tag == "polygon" else "")
    return None


def view_box_of(root: ET.Element) -> str | None:
    box = root.get("viewBox")
    if box:
        return " ".join(box.split())
    w, h = root.get("width"), root.get("height")
    if not (w and h):
        return None
    num = r"[-+]?[0-9]*\.?[0-9]+"
    mw, mh = re.match(num, w), re.match(num, h)
    return f"0 0 {mw.group()} {mh.group()}" if mw and mh else None


def collect_shapes(src: str) -> tuple[str, list[tuple[str, tuple[float, ...],
                                                      dict[str, str]]]] | None:
    """SVGを解析して (viewBox, [(d, 行列, 描画指定), ...]) を返す。

    `<g transform>` の入れ子を行列に畳んで各図形に持たせる。正規表現で path を
    拾うだけでは transform が落ちて絵が枠外に飛ぶので、XMLとして辿る。
    """
    try:
        root = ET.fromstring(src)
    except ET.ParseError:
        return None
    box = view_box_of(root)
    if not box:
        return None
    shapes: list[tuple[str, tuple[float, ...], dict[str, str]]] = []

    def walk(el: ET.Element, mat: tuple[float, ...], inherited: dict[str, str]) -> None:
        tag = el.tag.split("}")[-1]
        if tag in SKIP_TAGS:
            return
        style = dict(inherited)
        style.update(presentation(el))
        if style.get("display") == "none" or style.get("visibility") == "hidden":
            return
        if el.get("transform"):
            mat = matmul(mat, parse_transform(el.get("transform", "")))
        if tag in SHAPE_TAGS:
            d = shape_path(el, tag)
            if d and d.strip():
                shapes.append((d, mat, style))
        for child in el:
            walk(child, mat, style)

    walk(root, IDENTITY, {})
    return (box, shapes) if shapes else None


def fmt_num(value: float, precision: int) -> str:
    """座標を丸めて文字列にする。整数部の 0 を消さないよう小数点の有無を見る。"""
    text = f"{value:.{precision}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


NUMBER = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
TOKEN = re.compile(rf"{NUMBER.pattern}|[A-Za-z]")


def squeeze_path(d: str, precision: int) -> str:
    """path の d を丸めて詰める(1300枚に埋め込むので容量を削る)。

    数字とコマンド文字に分解して組み直す。丸めた結果が小数点を失うと
    `.04 .5` が `00.5`(=1つの数)に化けるので、数字が続くところには
    区切りを入れ直す。コマンド文字と符号は区切りを兼ねるので詰めてよい。
    """
    out: list[str] = []
    prev_num = False
    for token in TOKEN.findall(d):
        if token.isalpha():
            out.append(token)
            prev_num = False
            continue
        text = fmt_num(float(token), precision)
        if prev_num and text[0] not in "-+":
            out.append(" ")
        out.append(text)
        prev_num = True
    return "".join(out)


def simplify_svg(src: str, precision: int = 1,
                 mode: str = "dark") -> tuple[str, str] | None:
    """PhyloPicのSVGから (viewBox, 図形群) を抜いて最小構成に作り直す。

    塗りの色は持たせない(カード側で fill を与える)。線だけで描かれた図形は
    `stroke="currentColor"` にして、色の指定をカード側に委ねる。

    PhyloPicには「背景を白で塗って生物の形を抜く」書き方の素材が混ざる。
    色を捨てると生物ではなく背景が塗られてしまうので、
    - `mode="dark"`: 白塗りの図形を落とす(通常。白い抜きが上に乗る素材向け)
    - `mode="light"`: 白塗りの図形だけを残す(背景を黒で塗る素材向け)
    の2通りを作れるようにして、呼び出し側が描画結果を見て選ぶ。
    """
    collected = collect_shapes(src)
    if not collected:
        return None
    box, shapes = collected
    parts: list[str] = []
    current: tuple[float, ...] | None = None
    for d, mat, style in shapes:
        fill = (style.get("fill") or "#000").strip().lower()
        stroke = (style.get("stroke") or "none").strip().lower()
        want_white = mode == "light"
        filled = fill != "none" and is_white(fill) == want_white
        stroked = stroke != "none" and is_white(stroke) == want_white
        if not filled and not stroked:
            continue
        if mat != current:
            if current is not None and current != IDENTITY:
                parts.append("</g>")
            if mat != IDENTITY:
                parts.append('<g transform="matrix(%s)">' % ",".join(
                    fmt_num(v, 5 if i < 4 else 2) for i, v in enumerate(mat)))
            current = mat
        attrs = [f'd="{squeeze_path(d, precision)}"']
        if style.get("fill-rule") == "evenodd":
            attrs.append('fill-rule="evenodd"')
        if not filled:
            attrs.append('fill="none"')
        if stroked:
            attrs.append('stroke="currentColor"')
            for key in ("stroke-width", "stroke-linecap", "stroke-linejoin"):
                if style.get(key):
                    attrs.append(f'{key}="{style[key]}"')
        parts.append("<path " + " ".join(attrs) + "/>")
    if current is not None and current != IDENTITY:
        parts.append("</g>")
    body = "".join(parts)
    return (box, body) if "<path" in body else None


def render_svg(view_box: str, paths: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{view_box}">{paths}</svg>\n')


def best_svg(src: str, mode: str = "dark") -> str | None:
    """元SVGを最小構成に詰める。大きすぎるものは座標の精度を落とす。

    シルエットはカード上で 100px 程度に縮小して描くので、座標の小数は
    ほぼ効かない。それでも上限を超えるものは諦める(呼び出し側が次の候補へ)。
    """
    for precision in (1, 0):
        simplified = simplify_svg(src, precision, mode)
        if not simplified:
            return None
        svg = render_svg(*simplified)
        if len(svg.encode("utf-8")) <= MAX_SVG_BYTES:
            return svg
    return None


# --------------------------------------------------------------------------
# ラスタライズ検査(chromeがあるときだけ動く)
# --------------------------------------------------------------------------
def chrome_bin() -> str | None:
    for name in ("google-chrome", "chromium", "chromium-browser",
                 "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    return None


def screenshot(html: str, width: int, height: int, out: Path) -> bool:
    """HTMLをchromeでPNGにする。chromeが無ければ False。"""
    chrome = chrome_bin()
    if not chrome:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(html, encoding="utf-8")
        try:
            subprocess.run(
                [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                 "--hide-scrollbars", f"--screenshot={out}",
                 f"--window-size={width},{height}", str(page)],
                capture_output=True, timeout=180, check=False,
            )
        except subprocess.TimeoutExpired:
            return False
    return out.exists()


def ink_ratios(path: Path, threshold: int = 200) -> dict[str, float] | None:
    """PNGの塗り面積・外部背景・囲まれた背景の比を測る。

    塗り(ink)が全面に近ければ白黒反転素材、極端に小さければ実質欠け。
    外部と繋がっていない背景(enclosed)が塗りより多ければ輪郭線だけの線画。
    """
    try:
        from PIL import Image  # noqa: PLC0415 - 検査は任意機能なので遅延import
    except ImportError:
        return None
    with Image.open(path) as src:
        img = src.convert("L")
    w, h = img.size
    px = img.load()
    ink = [[px[x, y] <= threshold for x in range(w)] for y in range(h)]
    n_ink = sum(sum(row) for row in ink)
    # 画像の縁から背景を塗りつぶし、外に繋がっていない背景を数える
    seen = [[False] * w for _ in range(h)]
    stack: list[tuple[int, int]] = []
    edges = [(x, y) for x in range(w) for y in (0, h - 1)]
    edges += [(x, y) for y in range(h) for x in (0, w - 1)]
    for x, y in edges:
        if not ink[y][x] and not seen[y][x]:
            seen[y][x] = True
            stack.append((x, y))
    while stack:
        x, y = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and not ink[ny][nx]:
                seen[ny][nx] = True
                stack.append((nx, ny))
    total = w * h
    n_open = sum(sum(row) for row in seen)
    n_enclosed = total - n_ink - n_open
    return {
        "ink": round(n_ink / total, 3),
        "open": round(n_open / total, 3),
        "solidity": round(n_ink / max(n_ink + n_enclosed, 1), 3),
    }


def inspect_svg(svg: str, size: int = INSPECT_PX) -> dict[str, float] | None:
    """シルエットSVGをラスタライズして塗り面積の比を測る。

    viewBox を正方形いっぱいに引き伸ばして描く。アフィン変換は面積比を
    変えないので、縦横比を無視しても「viewBoxの何割が塗りか」は正しく出る。
    """
    match = re.search(r'viewBox="([^"]+)"', svg)
    if not match:
        return None
    body = svg[svg.index(">", svg.index("<svg")) + 1:svg.rindex("</svg>")]
    html = (
        '<body style="margin:0;background:#fff">'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{match.group(1)}"'
        f' width="{size}" height="{size}" preserveAspectRatio="none"'
        f' fill="#000" color="#000">{body}</svg></body>'
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "shot.png"
        if not screenshot(html, size, size, out):
            return None
        return ink_ratios(out)


def reject_reason(metrics: dict[str, float]) -> str | None:
    """検査値から不採用の理由を返す(合格なら None)。"""
    if metrics["open"] < MIN_OPEN_RATIO:
        return f"白黒反転(塗り{metrics['ink']:.0%}が全面)"
    if metrics["ink"] < MIN_INK_RATIO:
        return f"ほぼ空(塗り{metrics['ink']:.1%})"
    if metrics["solidity"] < MIN_SOLIDITY:
        return f"輪郭線のみ(充実度{metrics['solidity']:.2f})"
    return None


def pick_svg(img: dict, inspect: bool = True) -> tuple[str, dict[str, float], str]:
    """候補画像1件から、採用できるシルエットSVGを作る。

    白塗り前提の素材(背景が黒で生物が白抜き)は塗りが全面になるので、
    その場合は白い図形だけを残した版を作り直して測り直す。
    戻り値は (SVG, 検査値, 却下理由) で、採用できないときは理由だけを返す。
    """
    src = fetch_text(img["_links"]["sourceFile"]["href"])
    reason = "容量超過/図形無し"
    for mode in ("dark", "light"):
        svg = best_svg(src, mode)
        if not svg:
            continue
        if not inspect:
            return svg, {}, ""
        metrics = inspect_svg(svg)
        if metrics is None:  # ラスタライズできなかった。検査は諦めて採る
            return svg, {}, ""
        bad = reject_reason(metrics)
        if not bad:
            return svg, metrics, ""
        reason = bad
        if metrics["open"] >= MIN_OPEN_RATIO:
            break  # 反転ではないので白抜き版を試す意味がない
    return "", {}, reason


def contact_sheet(manifest: dict[str, dict], out: Path, columns: int = 9) -> bool:
    """全シルエットを1枚のPNGに並べる(目視確認用)。"""
    cells = []
    for label in sorted(manifest):
        svg = OUT_DIR / manifest[label]["file"]
        if not svg.exists():
            continue
        body = svg.read_text(encoding="utf-8")
        body = re.sub(r'<svg ', '<svg fill="#111" color="#111" ', body, count=1)
        cells.append(f'<figure><div>{body}</div><figcaption>{label}</figcaption>'
                     f'</figure>')
    if not cells:
        return False
    cell, rows = 150, (len(cells) + columns - 1) // columns
    html = (
        '<body style="margin:0;background:#fff;font:11px sans-serif">'
        f'<div style="display:grid;grid-template-columns:repeat({columns},{cell}px)">'
        + "".join(cells) +
        "</div><style>figure{margin:0;border:1px solid #ddd;padding:2px}"
        f"figure div{{height:{cell - 24}px;display:flex;align-items:center;"
        "justify-content:center}figure svg{max-width:100%;max-height:100%}"
        "figcaption{text-align:center;color:#333}</style></body>"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    return screenshot(html, cell * columns + 24, cell * rows + 24, out)


def label_key(label: str) -> str:
    return hashlib.sha1(label.encode("utf-8")).hexdigest()[:10]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true",
                    help="既に取得済みのラベルも取り直す(--only と併用できる)")
    ap.add_argument("--only", default="",
                    help="対象ラベルをカンマ区切りで限定する(デバッグ用)")
    ap.add_argument("--no-inspect", action="store_true",
                    help="ラスタライズ検査をしない(chromeを使わない)")
    ap.add_argument("--sheet", default="",
                    help="取得後、全シルエットを並べたPNGをここに書く")
    args = ap.parse_args()

    taxa: dict[str, str | None] = json.loads(TAXA_PATH.read_text("utf-8"))
    manifest: dict[str, dict] = {}
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text("utf-8"))
    # 自作素材のラベル。PhyloPicの取得対象から外し、掃除や上書きの対象にもしない
    own = {k for k, v in manifest.items() if v.get("source") == SELF_SOURCE}

    targets = {k: v for k, v in taxa.items() if v and k not in own}
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        unknown = want - set(taxa)
        if unknown:
            print(f"error: 未知のラベル {sorted(unknown)}", file=sys.stderr)
            return 1
        targets = {k: v for k, v in targets.items() if k in want}

    inspect = not args.no_inspect
    if inspect and not chrome_bin():
        print("warning: chromeが無いのでラスタライズ検査を飛ばす"
              "(白黒反転や線画の素材が混ざる)", file=sys.stderr)
        inspect = False

    if not args.only:
        # 学名が null になったラベルの残骸を掃除する(--only のときは触らない)。
        # 自作素材は学名が null のまま置いてあるので掃除の対象外
        for label in [k for k in manifest if k not in targets and k not in own]:
            stale = OUT_DIR / manifest.pop(label)["file"]
            stale.unlink(missing_ok=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    build = build_id()
    todo = [k for k in targets if args.refresh or k not in manifest]
    print(f"build {build}: {len(todo)}/{len(targets)} ラベルを取得する")

    missing: list[str] = []
    for i, label in enumerate(sorted(todo), 1):
        taxon = targets[label]
        head = f"[{i}/{len(todo)}] {label} ({taxon})"
        try:
            found = find_node(taxon, build)
            if not found:
                print(f"{head}: ノード無し")
                missing.append(label)
                continue
            node_uuid, node_title = found
            chosen: tuple[dict, str, dict[str, float]] | None = None
            notes: list[str] = []
            for cand in pd_images(node_uuid, build):
                svg, metrics, bad = pick_svg(cand, inspect)
                if bad or not svg:
                    notes.append(bad or "図形無し")
                    continue
                chosen = (cand, svg, metrics)
                break
            if not chosen:
                if not notes:
                    print(f"{head}: PD+SVGの画像無し")
                else:
                    print(f"{head}: 使えるSVG無し(候補{len(notes)}件: "
                          f"{'、'.join(notes)})")
                missing.append(label)
                continue
            img, svg, metrics = chosen
            uuid = img["_links"]["self"]["href"].split("/images/", 1)[1].split("?")[0]
            filename = f"{label_key(label)}.svg"
            (OUT_DIR / filename).write_text(svg, encoding="utf-8")
            manifest[label] = {
                "file": filename,
                "source": PHYLOPIC_SOURCE,
                "taxon": taxon,
                "node": node_title,
                "phylopic": uuid,
                "license": img["_links"]["license"]["href"],
                "contributor": img["_links"]["contributor"]["title"],
                "title": img["_links"]["self"].get("title", node_title),
            }
            if metrics:
                manifest[label]["ink"] = metrics
            size = (OUT_DIR / filename).stat().st_size
            skipped = f" (候補{len(notes)}件を却下)" if notes else ""
            print(f"{head} -> {node_title} {size / 1024:.1f}KB{skipped}")
        except Exception as exc:  # noqa: BLE001 - 1件の失敗で全体を止めない
            print(f"{head}: {exc}", file=sys.stderr)
            missing.append(label)
        time.sleep(0.2)

    for label in missing:
        manifest.pop(label, None)
    MANIFEST_PATH.write_text(
        json.dumps({k: manifest[k] for k in sorted(manifest)},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    no_taxon = sum(1 for v in taxa.values() if not v)
    print(f"\n{len(manifest)}/{len(taxa)} ラベルにシルエットあり "
          f"(PhyloPic {len(manifest) - len(own)}件 / 自作 {len(own)}件、"
          f"学名なし {no_taxon}件のうち {len(own)}件を自作素材で埋めている)")
    lost = sorted(label for label in own
                  if not (OUT_DIR / manifest[label]["file"]).exists())
    if lost:
        print(f"warning: 自作素材のファイルが無い {len(lost)}件: "
              f"{'、'.join(lost)}", file=sys.stderr)
    if missing:
        print(f"未取得 {len(missing)}件: {'、'.join(sorted(missing))}")
    if args.sheet:
        if contact_sheet(manifest, Path(args.sheet)):
            print(f"一覧画像: {args.sheet}")
        else:
            print("warning: 一覧画像を作れなかった", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
