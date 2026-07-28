#!/usr/bin/env python3
"""baseball.csv / football.csv の所属チームの「チームカラー」を集める。

生成カード(gen_player_cards.py)の配色に使う下ごしらえ。結果は
`tools/team_colors.json` に**出典URL付き**で書き出す。

## 何を取っていて、何を取っていないか(ADR 00020)

- 取るのは**チームカラーという事実(色の値)だけ**。色そのものは著作物ではない
- **ロゴ・エンブレム・マスコット・ユニフォームの意匠は一切扱わない**。画像の
  ダウンロードもしない(取得するのはWikipediaのウィキテキストだけ)
- 取得元は、色を**テキストとして**書いている記事のインフォボックスに限る
  - football: ja.wikipedia のクラブ記事の `| カラー = {{color box|#B8193F}} ディープレッド`
    (Jリーグ公式のクラブガイドを出典に持つ)
  - baseball: en.wikipedia の球団記事の `| colors = ... {{color box|#ed9e21}} ...`
    (ja.wikipedia の野球チームinfoboxには色の項目が無い)
- hex が無く色名だけの記事は、**基本色名 → 代表色**の対応表で hex にする
  (`赤` → `#e60012`)。これは「赤」という事実の描画方法を決めているだけで、
  クラブ固有の色を推測しているわけではない。`source` で区別できるようにする
- 球団名の短縮形(baseball の `巨人`)から記事名への対応は手動表(下の
  `BASEBALL_TEAM_ARTICLES`)。**消滅球団(阪急・南海・大洋・西鉄 等)は
  現行球団の記事にリダイレクトされてしまい、当時の色とは別物になる**ので
  表に載せない。載せない球団はカード側のフォールバック配色になる

usage:
  python3 tools/fetch_team_colors.py             # 取得して JSON を更新
  python3 tools/fetch_team_colors.py --report    # 取得できなかったチームを表示
  python3 tools/fetch_team_colors.py --refresh   # キャッシュを捨てて再取得
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
OUT_PATH = TOOLS / "team_colors.json"
CACHE_DIR = TOOLS / ".cache" / "team_colors"

UA = {"User-Agent": "soramimic-wordlists-updater/1.0 "
                    "(https://github.com/soramimic/soramimic-wordlists)"}
BATCH = 50          # 1リクエストあたりの記事数(APIの上限)
SLEEP = 1.0         # リクエスト間隔(秒)

README = (
    "baseball.csv / football.csv のチームカラー。tools/fetch_team_colors.py が生成する。"
    "出典はWikipediaのインフォボックスに**テキストで**書かれた色だけ("
    "source=wikipedia-hex は色見本テンプレートの16進値、"
    "wikipedia-colorname は色名しか書かれていないものを基本色に写像したもの、"
    "manual は人手で確認したもの)。"
    "ロゴ・エンブレム・ユニフォームの意匠は一切使っていない。"
    "詳細は docs/adr/00020-player-cards.md を参照。"
)

# --- baseball: 球団の短縮名 → en.wikipedia の記事名 --------------------------
#
# baseball.csv の team は「巨人-日本ハム」「大洋・横浜」のように球団の変遷を
# 連ねた文字列で、要素は短縮名。**現存する球団と、その球団自身の記事がある
# ものだけ**を載せる。消滅球団(阪急・南海・大洋・西鉄・東映・国鉄・ダイエー
# など)は記事が現行球団へのリダイレクトになっていて、色を引くと当時と違う色に
# なるので載せない(例: 南海ホークスは緑だが、リダイレクト先の
# 福岡ソフトバンクホークスは黄)。
BASEBALL_TEAM_ARTICLES = {
    "巨人": "Yomiuri Giants",
    "阪神": "Hanshin Tigers",
    "中日": "Chunichi Dragons",
    "広島": "Hiroshima Toyo Carp",
    "ヤクルト": "Tokyo Yakult Swallows",
    "DeNA": "Yokohama DeNA BayStars",
    # 横浜ベイスターズ(1993-2011)は同じ球団の旧称で、青×白のまま連続している
    "横浜": "Yokohama DeNA BayStars",
    "ロッテ": "Chiba Lotte Marines",
    "日本ハム": "Hokkaido Nippon-Ham Fighters",
    "西武": "Saitama Seibu Lions",
    "ソフトバンク": "Fukuoka SoftBank Hawks",
    "オリックス": "Orix Buffaloes",
    "楽天": "Tohoku Rakuten Golden Eagles",
    # 大阪近鉄バファローズは消滅球団だが独立した記事がある
    "近鉄": "Osaka Kintetsu Buffaloes",
}

# --- 色名 → 代表色 -----------------------------------------------------------
#
# 「チームカラー = 赤・白」のように色名しか書かれていない記事のための対応表。
# CSSの色名(color box テンプレートは名前も受け付ける)と、日本語の基本色名。
# **クラブ固有の色を当てているのではなく、基本色の描画色を決めているだけ**。
CSS_COLORS = {
    "white": "#ffffff", "black": "#000000", "red": "#e60012",
    "blue": "#0068b7", "green": "#009944", "yellow": "#ffe100",
    "orange": "#f39800", "purple": "#8f2d8b", "pink": "#e95098",
    "navy": "#0b1e5a", "gold": "#c9a227", "silver": "#b0b0b0",
    "gray": "#808080", "grey": "#808080", "brown": "#78552f",
    "skyblue": "#00a0e9", "lightblue": "#66c6ea", "maroon": "#7b1f2b",
    "crimson": "#a4123f", "darkblue": "#0b1e5a", "darkgreen": "#00612f",
}
JP_COLORS = {
    "赤": "#e60012", "青": "#0068b7", "黄": "#ffe100", "黄色": "#ffe100",
    "緑": "#009944", "白": "#ffffff", "黒": "#000000", "橙": "#f39800",
    "オレンジ": "#f39800", "紫": "#8f2d8b", "桃": "#e95098",
    "ピンク": "#e95098", "水色": "#66c6ea", "空色": "#00a0e9",
    "紺": "#0b1e5a", "臙脂": "#7b1f2b", "えんじ": "#7b1f2b",
    "金": "#c9a227", "銀": "#b0b0b0", "茶": "#78552f", "灰": "#808080",
    "群青": "#1b3f8b", "藍": "#1b3f8b", "朱": "#e8452a", "萌黄": "#8bc34a",
    "若草": "#8bc34a", "深緑": "#00612f", "濃紺": "#0b1e5a",
}
# 「赤と白」「青・赤」のような並びを切る区切り
JP_SPLIT = re.compile(r"[・、,，/／]|と|＆|&")

REF_RE = re.compile(r"<ref[^>]*/>|<ref.*?</ref>", re.S)
COLORBOX_RE = re.compile(r"\{\{\s*[Cc]olor ?box\s*\|\s*([^|}]+?)\s*[|}]")
HEX_RE = re.compile(r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")


def norm_hex(token: str):
    """color box の引数を16進表記にする。読めなければ None。"""
    t = token.strip()
    m = HEX_RE.fullmatch(t) or HEX_RE.fullmatch("#" + t)
    if m:
        v = m.group(1).lower()
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        return "#" + v
    return CSS_COLORS.get(t.lower().replace(" ", ""))


def field(text: str, names) -> str:
    """インフォボックスの `| 名前 = ...` を1行取り出す(<ref>は落とす)。"""
    for name in names:
        m = re.search(r"^\s*\|\s*%s\s*=([^\n]*)" % re.escape(name),
                      text, re.M)
        if m:
            return REF_RE.sub("", m.group(1)).strip()
    return ""


def colors_from_field(value: str):
    """色の並びを (色のリスト, source) で返す。取れなければ ([], "")。"""
    boxes = [norm_hex(t) for t in COLORBOX_RE.findall(value)]
    boxes = [c for c in boxes if c]
    if boxes:
        return boxes, "wikipedia-hex"
    plain = [m.group(0).lower() for m in HEX_RE.finditer(value)]
    if plain:
        return [norm_hex(c) for c in plain], "wikipedia-hex"
    # 色名だけの記事。テンプレート・リンク記法を落としてから語で切る
    text = re.sub(r"\{\{[^}]*\}\}", " ", value)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"[（(][^）)]*[）)]", " ", text)
    out = []
    for part in JP_SPLIT.split(text):
        part = part.strip().strip("色 ")
        hexv = JP_COLORS.get(part) or CSS_COLORS.get(part.lower())
        if hexv and hexv not in out:
            out.append(hexv)
    return (out, "wikipedia-colorname") if out else ([], "")


# --- Wikipedia API -----------------------------------------------------------

def fetch_batch(titles, lang: str) -> dict:
    """記事名 → ウィキテキスト。リダイレクトは追跡済みの本文が入る。"""
    data = urllib.parse.urlencode({
        "action": "query", "prop": "revisions", "rvprop": "content",
        "rvslots": "main", "format": "json", "formatversion": "2",
        "redirects": "1", "titles": "|".join(titles),
    }).encode()
    req = urllib.request.Request(f"https://{lang}.wikipedia.org/w/api.php",
                                 data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as fh:
        d = json.load(fh)
    q = d["query"]
    redirect = {}
    for key in ("normalized", "redirects"):
        for e in q.get(key, []):
            redirect[e["from"]] = e["to"]
    pages = {p["title"]: p["revisions"][0]["slots"]["main"]["content"]
             for p in q["pages"] if "revisions" in p}
    return redirect, pages


def load_pages(titles, lang: str, refresh: bool) -> dict:
    """記事名 → ウィキテキスト。`tools/.cache/` に保存して再開できるようにする。"""
    cache = CACHE_DIR / lang
    cache.mkdir(parents=True, exist_ok=True)
    store = cache / "pages.json"
    redir = cache / "redirects.json"
    pages = {} if refresh or not store.exists() else json.loads(
        store.read_text(encoding="utf-8"))
    redirect = {} if refresh or not redir.exists() else json.loads(
        redir.read_text(encoding="utf-8"))

    def resolve(t):
        seen = set()
        while t in redirect and t not in seen:
            seen.add(t)
            t = redirect[t]
        return t

    todo = [t for t in titles if resolve(t) not in pages and t not in redirect]
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        r, p = fetch_batch(chunk, lang)
        redirect.update(r)
        pages.update(p)
        # 記事が無いものも「引いた」と記録しないと毎回引き直しになる
        for t in chunk:
            if resolve(t) not in pages:
                redirect.setdefault(t, "")
        store.write_text(json.dumps(pages, ensure_ascii=False),
                         encoding="utf-8")
        redir.write_text(json.dumps(redirect, ensure_ascii=False),
                         encoding="utf-8")
        print(f"  {lang}: {min(i + BATCH, len(todo))}/{len(todo)}件")
        time.sleep(SLEEP)
    return {t: pages.get(resolve(t), "") for t in titles}


# --- チーム名の収集 ----------------------------------------------------------

def football_teams() -> list:
    """football.csv に出てくるクラブ名(空でないもの)。"""
    seen = []
    known = set()
    with (ROOT / "football.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = r.get("team", "")
            if t and t not in known:
                known.add(t)
                seen.append(t)
    return sorted(seen)


def baseball_team_names() -> Counter:
    """baseball.csv の team に出てくる球団の短縮名と、その出現人数。"""
    from gen_player_cards import team_names   # 同じ分解規則を使う
    c = Counter()
    seen = set()
    with (ROOT / "baseball.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["original"] in seen:
                continue
            seen.add(r["original"])
            for n in team_names(r.get("team", ""), career=True):
                c[n] += 1
    return c


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true",
                    help="キャッシュを捨てて取得しなおす")
    ap.add_argument("--report", action="store_true",
                    help="色が取れなかったチームを表示する")
    args = ap.parse_args()
    sys.path.insert(0, str(TOOLS))

    out = {"README": README, "sources": {
        "football": "ja.wikipedia のクラブ記事インフォボックスの「カラー」",
        "baseball": "en.wikipedia の球団記事インフォボックスの colors",
    }, "teams": {"baseball": {}, "football": {}}}

    # --- football ---
    teams = football_teams()
    print(f"football: {len(teams)}クラブ")
    pages = load_pages(teams, "ja", args.refresh)
    miss = []
    for t in teams:
        value = field(pages.get(t, ""), ("カラー", "クラブカラー", "チームカラー"))
        colors, source = colors_from_field(value)
        if not colors:
            miss.append(t)
            continue
        out["teams"]["football"][t] = {
            "primary": colors[0],
            "secondary": colors[1] if len(colors) > 1 else "",
            "source": source,
            "source_url": "https://ja.wikipedia.org/wiki/"
                          + urllib.parse.quote(t.replace(" ", "_")),
        }
    print(f"  色が取れたクラブ: {len(out['teams']['football'])}/{len(teams)}")
    if args.report and miss:
        print(f"  取れなかったクラブ({len(miss)}): {' / '.join(miss[:40])}")

    # --- baseball ---
    names = baseball_team_names()
    titles = sorted(set(BASEBALL_TEAM_ARTICLES.values()))
    print(f"baseball: {len(names)}球団名(うち対応表にあるのは "
          f"{sum(1 for n in names if n in BASEBALL_TEAM_ARTICLES)})")
    pages = load_pages(titles, "en", args.refresh)
    for short, title in BASEBALL_TEAM_ARTICLES.items():
        value = field(pages.get(title, ""), ("colors", "colours"))
        colors, source = colors_from_field(value)
        if not colors:
            print(f"  警告: {short}({title}) の色が取れない", file=sys.stderr)
            continue
        out["teams"]["baseball"][short] = {
            "primary": colors[0],
            "secondary": colors[1] if len(colors) > 1 else "",
            "source": source,
            "source_url": "https://en.wikipedia.org/wiki/"
                          + urllib.parse.quote(title.replace(" ", "_")),
        }
    got = out["teams"]["baseball"]
    if len(got) != len(BASEBALL_TEAM_ARTICLES):
        print("error: 対応表の球団の色が引けていない", file=sys.stderr)
        return 1
    covered = sum(v for n, v in names.items() if n in got)
    print(f"  色が取れた球団: {len(got)}/{len(BASEBALL_TEAM_ARTICLES)} "
          f"(のべ{covered}人ぶん)")
    if args.report:
        rest = [(n, v) for n, v in names.most_common() if n not in got]
        print("  対応表に無い球団(フォールバック配色になる): "
              + " / ".join(f"{n}:{v}" for n, v in rest[:30]))

    OUT_PATH.write_text(
        json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"-> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
