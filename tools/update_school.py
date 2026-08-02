#!/usr/bin/env python3
"""school.csv を文部科学省「学校コード」+ Wikidata + Wikipedia から再生成する。

出典:
- 学校の名簿(正式名称・校種・設置区分・所在地・学校コード・廃止): 文部科学省
  「学校コード」一覧 (政府標準利用規約2.0 / CC BY 互換)
- 読み仮名(P1814)・別名(altLabel)・QID: Wikidata (CC0)。学校コード P11127 で直接JOIN
- 通称・略称とその読み: ja.wikipedia の記事冒頭 (CC BY-SA 4.0)

方式:
- 1校 = 1グループ(id)。表層は type で 3 種類に展開する(重複する行は作らない)
  - common: 設置者接頭辞を落として校種語を短縮した通用形 例 札幌南高校
  - name  : 固有部分のみ                               例 札幌南
  - nick  : 口語的な通称・略称(出典から取れたものだけ)    例 札南
- 正式名称は全行の original 列に入るので、full の行は作らない
- common/name は機械生成。nick は Wikipedia 冒頭の「通称は〜」「略称は〜」と
  Wikidata の altLabel からしか作らない(詳細は ADR 00037)
- id は学校コードで固定する。既存 school.csv にある学校コードの id は変えず、
  新規の学校だけ末尾に追記する(ADR 00014)

usage: python3 tools/update_school.py [--refresh]
  --refresh を付けると tools/.cache/ の取得結果を捨てて引き直す
"""

import csv
import io
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = {"User-Agent": "soramimic-wordlists-updater/1.0 (https://github.com/soramimic/soramimic-wordlists)"}
MEXT_PAGE = "https://www.mext.go.jp/b_menu/toukei/mext_01087.html"
# ページから拾えなかったときのフォールバック(令和8年5月1日時点)
MEXT_FALLBACK = {
    "2": "https://www.mext.go.jp/content/20260529-mxt_chousa01-000011635_2.csv",
    "4": "https://www.mext.go.jp/content/20260529-mxt_chousa01-000011635_4.csv",
    "6": "https://www.mext.go.jp/content/20260529-mxt_chousa01-000011635_6.csv",
}
WDQS = "https://query.wikidata.org/sparql"
WP_API = "https://ja.wikipedia.org/w/api.php"

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "school.csv"
CACHE = Path(__file__).resolve().parent / ".cache"
COLS = ["id", "original", "surface", "pronunciation", "type", "school_type",
        "founder", "prefecture", "city", "status", "code", "wikidata"]

# 名簿の件数がこの範囲を外れたらソース異常とみなして中断する
MIN_SCHOOLS, MAX_SCHOOLS = 40000, 90000

SCHOOL_TYPE = {
    "A1": "幼稚園", "A2": "認定こども園", "B1": "小学校", "C1": "中学校",
    "C2": "義務教育学校", "D1": "高等学校", "D2": "中等教育学校",
    "E1": "特別支援学校", "F1": "大学", "F2": "短期大学", "G1": "高等専門学校",
    "H1": "専修学校", "H2": "各種学校",
}
FOUNDER = {"1": "国立", "2": "公立", "3": "私立"}
# Wikidataにsitelinkが無くても、正式名称でWikipediaを引き当てにいく校種
FALLBACK_KINDS = {"C1", "C2", "D1", "D2", "F1", "F2", "G1", "H1"}

PREFS = ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県",
         "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県", "富山県",
         "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県", "三重県",
         "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県", "鳥取県", "島根県",
         "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
         "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"]
# 「サイタマケンリツウラワコウトウガッコウ」のような接頭辞込みの読みから
# 接頭辞を落とすための表(都道府県立の学校だけ機械的に落とせる)
PREF_KANA = [
    "ホッカイドウ", "アオモリケン", "イワテケン", "ミヤギケン", "アキタケン", "ヤマガタケン",
    "フクシマケン", "イバラキケン", "トチギケン", "グンマケン", "サイタマケン", "チバケン",
    "トウキョウト", "カナガワケン", "ニイガタケン", "トヤマケン", "イシカワケン", "フクイケン",
    "ヤマナシケン", "ナガノケン", "ギフケン", "シズオカケン", "アイチケン", "ミエケン",
    "シガケン", "キョウトフ", "オオサカフ", "ヒョウゴケン", "ナラケン", "ワカヤマケン",
    "トットリケン", "シマネケン", "オカヤマケン", "ヒロシマケン", "ヤマグチケン",
    "トクシマケン", "カガワケン", "エヒメケン", "コウチケン", "フクオカケン", "サガケン",
    "ナガサキケン", "クマモトケン", "オオイタケン", "ミヤザキケン", "カゴシマケン",
    "オキナワケン"]

# 校種語の短縮(長いものから順に、最初に当たった1つだけ置換する)
SHORTEN = [
    ("高等専門学校", "高専"),
    ("中等教育学校", "中等"),
    ("小中学校", "小中"),
    ("高等学校", "高校"),
    ("短期大学", "短大"),
    ("中学校", "中"),
    ("小学校", "小"),
]
# name(固有部分)を作るときに落とす校種語。長いものから順に試す
TYPE_WORDS = [
    "幼保連携型認定こども園", "幼稚園型認定こども園", "保育所型認定こども園",
    "地方裁量型認定こども園", "認定こども園", "高等専門学校", "中等教育学校",
    "義務教育学校", "特別支援学校", "高等特別支援学校", "高等養護学校",
    "高等支援学校", "総合支援学校", "視覚支援学校", "聴覚支援学校",
    "高等専修学校", "専修学校", "専門学校", "各種学校", "短期大学部", "短期大学",
    "小中学校", "高等学校", "中学校", "小学校", "養護学校", "支援学校", "聾学校",
    "盲学校", "こども園", "保育園", "保育所", "幼稚園", "大学校", "大学",
    "高専", "中等", "高校", "短大", "小中", "小", "中",
]
# 校種語が名前の前に来る形(専門学校○○ / 認定こども園○○ など)
TYPE_PREFIX = ["幼保連携型認定こども園", "幼稚園型認定こども園", "保育所型認定こども園",
               "地方裁量型認定こども園", "認定こども園", "こども園", "高等専修学校",
               "専修学校", "専門学校", "各種学校"]
# 設置者の接頭辞(○○県立 / ○○市立 / ○○町外二ヶ村組合立 …)。
# 「国立音楽大学」「東京立正中学校」を壊さないよう、「立」の直前が
# 行政単位を表す字であることを必ず要求する
FOUNDER_PREFIX = re.compile(
    r"^(?:学校法人)?"
    r"(?:.{1,12}?(?:都|道|府|県|市|区|町|村|郡|組合|広域連合|事務組合|一部事務組合)立)?")
# 読みの校種語も同じ規則で短縮する
PRON_SHORTEN = [
    ("こうとうせんもんがっこう", "こうせん"),
    ("ちゅうとうきょういくがっこう", "ちゅうとう"),
    ("こうとうがっこう", "こうこう"),
    ("たんきだいがく", "たんだい"),
    ("ちゅうがっこう", "ちゅう"),
    ("しょうがっこう", "しょう"),
]
# 読みからも落とす校種語(name の読みを作るため)
PRON_TYPE_WORDS = [
    "こうとうせんもんがっこう", "ちゅうとうきょういくがっこう", "ぎむきょういくがっこう",
    "とくべつしえんがっこう", "こうとうようごがっこう", "こうとうしえんがっこう",
    "そうごうしえんがっこう", "せんしゅうがっこう", "せんもんがっこう", "かくしゅがっこう",
    "たんきだいがく", "しょうちゅうがっこう", "こうとうがっこう", "ちゅうがっこう",
    "しょうがっこう", "ようごがっこう", "しえんがっこう", "ろうがっこう", "もうがっこう",
    "にんていこどもえん", "こどもえん", "ほいくえん", "ようちえん", "だいがく",
    "こうせん", "ちゅうとう", "こうこう", "たんだい", "しょう", "ちゅう",
]
# 通称としては一般的すぎて単語リストの表層にならないもの
NICK_STOP = {"附属", "付属", "本校", "分校", "高校", "中学", "小学", "大学", "学園",
             "学院", "学校", "県立", "市立", "町立", "村立", "私立", "国立", "公立",
             "都立", "府立", "道立", "短大", "高専", "本館", "本部", "母校", "同校",
             "中等", "こども園", "幼稚園", "専門学校", "旧校名", "現在", "以前"}
SCHOOL_WORD = re.compile(r"学校|大学|学園|学院|幼稚園|こども園|保育園|高校|中学|"
                         r"小学|短大|高専|中等|スクール")
FOUNDER_WORDS = ("県立", "都立", "府立", "道立", "市立", "町立", "村立", "区立",
                 "私立", "国立", "公立", "組合立")

HIRA = re.compile(r"^[ぁ-ゖー・\s]+$")
KATA_ONLY = re.compile(r"^[ァ-ヴーゝゞヽヾ・]+$")
HIRA2KATA = str.maketrans({chr(k): chr(k + 0x60) for k in range(ord("ぁ"), ord("ゖ") + 1)})
# 読みはカタカナで持つので、上のひらがな定義をカタカナに直しておく
PRON_SHORTEN = [(a.translate(HIRA2KATA), b.translate(HIRA2KATA)) for a, b in PRON_SHORTEN]
PRON_TYPE_WORDS = [w.translate(HIRA2KATA) for w in PRON_TYPE_WORDS]
# 通称・略称の書き出し
NICK_MARK = re.compile(r"(?:通称|略称|愛称|略して)(?:は|:|：|、|，)?")
BRACKETED = re.compile(r"[「『]([^「」『』\n]{1,12})[」』]\s*(?:[（(]\s*([ぁ-ゖァ-ヴー・]{2,24})[^）)]*[）)])?")
BARE = re.compile(r"^\s*([^\s。、，,・「」『』（）()]{2,10})\s*(?:[（(]\s*([ぁ-ゖァ-ヴー・]{2,24})[^）)]*[）)])?")
# 記事冒頭の「正式名称（よみ、…）」
INTRO_YOMI = re.compile(r"^\s*[（(]\s*([ぁ-ゖー・\s]{4,60})\s*[、,）)]")


def to_kata(s: str) -> str:
    """半角カナ・ひらがなをカタカナに正規化する。カタカナ以外が残ったら空を返す"""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\s　]", "", s).translate(HIRA2KATA)
    s = s.replace("‐", "ー").replace("−", "ー").replace("-", "ー")
    return s if s and KATA_ONLY.match(s) else ""


def clean_field(s: str) -> str:
    """CSVを壊す文字を除く(素朴なsplit(',')のパーサ前提)"""
    s = s.replace("\r", "").replace("\n", "").replace(",", "、").replace('"', "”")
    s = re.sub(r"[\s　]+", " ", s).strip()
    return s


def http(url: str, retries: int = 4, wait: float = 8.0, binary: bool = False):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=300) as res:
                data = res.read()
            return data if binary else json.loads(data)
        except Exception as ex:
            print(f"retry {attempt}: {ex}", file=sys.stderr)
            time.sleep(wait * (attempt + 1))
    raise RuntimeError(f"failed: {url[:120]}")


# ---------------------------------------------------------------- 文部科学省
def mext_urls() -> dict:
    """学校コード一覧ページから最新版(日付が最大)のCSVのURLを拾う"""
    try:
        html = http(MEXT_PAGE, binary=True).decode("utf-8", "replace")
    except Exception as ex:
        print(f"warn: {MEXT_PAGE}: {ex} -> フォールバックURLを使う", file=sys.stderr)
        return dict(MEXT_FALLBACK)
    found = {}
    for m in re.finditer(r"content/(\d{8})-mxt_chousa01-000011635_(2|4|6)\.csv", html):
        date, part = m.group(1), m.group(2)
        if date >= found.get(part, ("",))[0]:
            found[part] = (date, "https://www.mext.go.jp/" + m.group(0))
    urls = {p: v[1] for p, v in found.items()}
    if set(urls) != {"2", "4", "6"}:
        print("warn: ページからURLを拾えなかった -> フォールバック", file=sys.stderr)
        return dict(MEXT_FALLBACK)
    print("mext: " + " ".join(sorted(u.rsplit("/", 1)[1] for u in urls.values())))
    return urls


def fetch_mext(refresh: bool) -> list:
    """[{code, kind, pref_no, founder, branch, name, address, closed}]"""
    urls = mext_urls()
    rows = []
    for part, url in sorted(urls.items()):
        path = CACHE / f"school_mext_{part}.csv"
        if refresh or not path.exists():
            path.write_bytes(http(url, binary=True))
            time.sleep(1)
        text = path.read_bytes().decode("cp932", "replace")
        rs = list(csv.reader(io.StringIO(text)))
        # 1行目はタイトル行、2行目がヘッダ
        for r in rs[2:]:
            if len(r) < 10 or not r[0].strip():
                continue
            rows.append({
                "code": clean_field(r[0]), "kind": r[1][:2], "pref_no": r[2][:2],
                "founder": r[3][:1], "branch": r[4][:1],
                "name": clean_field(r[5]), "address": clean_field(r[6]),
                "closed": bool(r[9].strip()),
            })
    return rows


# ---------------------------------------------------------------- Wikidata
WD_MAIN = """
SELECT ?item ?code ?kana ?title WHERE {
  ?item wdt:P11127 ?code .
  FILTER(STRSTARTS(?code, "%s"))
  OPTIONAL { ?item wdt:P1814 ?kana }
  OPTIONAL { ?a schema:about ?item ; schema:isPartOf <https://ja.wikipedia.org/> ; schema:name ?title }
}
"""
WD_ALT = """
SELECT ?code ?alt WHERE {
  ?item wdt:P11127 ?code ; skos:altLabel ?alt .
  FILTER(STRSTARTS(?code, "%s"))
  FILTER(LANG(?alt)="ja")
}
"""


def sparql(query: str) -> list:
    url = WDQS + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={**UA, "Accept": "application/sparql-results+json"})
            with urllib.request.urlopen(req, timeout=300) as res:
                return json.load(res)["results"]["bindings"]
        except Exception as ex:
            print(f"retry {attempt}: {ex}", file=sys.stderr)
            time.sleep(20 * (attempt + 1))
    raise RuntimeError("WDQS failed")


def fetch_wikidata(refresh: bool) -> dict:
    """学校コード -> {qid, kana[], alt[], title}"""
    path = CACHE / "school_wikidata.json"
    if not refresh and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for pre in sorted(SCHOOL_TYPE):
        for b in sparql(WD_MAIN % pre):
            code = b["code"]["value"]
            e = out.setdefault(code, {"qid": b["item"]["value"].rsplit("/", 1)[1],
                                      "kana": [], "alt": [], "title": ""})
            if "kana" in b and b["kana"]["value"] not in e["kana"]:
                e["kana"].append(b["kana"]["value"])
            if "title" in b:
                e["title"] = b["title"]["value"]
        time.sleep(2)
    for pre in sorted(SCHOOL_TYPE):
        for b in sparql(WD_ALT % pre):
            e = out.get(b["code"]["value"])
            if e is not None and b["alt"]["value"] not in e["alt"]:
                e["alt"].append(b["alt"]["value"])
        time.sleep(2)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"wikidata: {len(out)} items")
    return out


# ---------------------------------------------------------------- Wikipedia
def fetch_batch(batch: list) -> dict:
    """20件まとめて冒頭文を引く。リダイレクトは要求したタイトルに戻して返す"""
    url = WP_API + "?" + urllib.parse.urlencode({
        "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
        "exlimit": "max", "redirects": 1, "format": "json",
        "titles": "|".join(batch)})
    out = {t: "" for t in batch}
    try:
        data = http(url)
    except Exception as ex:
        print(f"skip batch: {ex}", file=sys.stderr)
        return {}
    redir = {r["to"]: r["from"] for r in data["query"].get("redirects", [])}
    for p in data["query"]["pages"].values():
        out[redir.get(p["title"], p["title"])] = (p.get("extract", "") or "")[:400]
    time.sleep(0.2)
    return out


def fetch_extracts(titles: list, refresh: bool) -> dict:
    """記事タイトル -> 冒頭文(400字)。取得済みはキャッシュから返す。
    2.6万記事あるので3並列で引く(逐次だと2時間かかる)"""
    path = CACHE / "school_extracts.json"
    cache = {} if refresh or not path.exists() else json.loads(path.read_text(encoding="utf-8"))
    todo = sorted(set(titles) - set(cache))
    print(f"wikipedia: {len(todo)} 件を取得(キャッシュ {len(cache)} 件)")
    batches = [todo[i:i + 20] for i in range(0, len(todo), 20)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for n, got in enumerate(pool.map(fetch_batch, batches)):
            cache.update(got)
            if n and n % 50 == 0:
                path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                print(f"  {n * 20}/{len(todo)}", file=sys.stderr)
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def split_yomi(cand: str, yomi: str) -> tuple:
    """「勿一(なこいち)」のように鉤括弧の中に読みが入っている形をほどく"""
    m = re.match(r"^([^（(]{1,12}?)\s*[（(]\s*([ぁ-ゖァ-ヴー・]{2,24})", cand)
    if m:
        return m.group(1), (yomi or m.group(2))
    return cand, yomi


def parse_nicks(text: str) -> list:
    """冒頭文から (通称, 読み or '') を集める"""
    out = []
    for m in NICK_MARK.finditer(text):
        window = text[m.end():m.end() + 80].split("。")[0]
        found = list(BRACKETED.finditer(window))
        if found:
            for b in found:
                # 「A」「B」のように連続する場合だけ拾う(離れた鉤括弧は別の話題)
                if b.start() > 2 and not window[:b.start()].rstrip().endswith(("」", "』", "、", "・")):
                    break
                out.append(split_yomi(b.group(1), b.group(2) or ""))
        else:
            b = BARE.match(window)
            if b:
                # 「上智短大やSJC」のような並列は先頭だけ採る
                cand = re.split(r"または|あるいは|および|もしくは|や(?=[A-Za-z])", b.group(1))[0]
                out.append(split_yomi(cand, b.group(2) or ""))
    return out


def lookup_title(rec: dict, w: dict) -> str:
    """冒頭文を引くための記事名。Wikidataのsitelinkを優先し、無い校種のうち
    通称が期待できるもの(中高・大学・専修)だけ正式名称で引き当てる
    (「灘高等学校」→リダイレクト→「灘中学校・高等学校」が拾える)"""
    return w.get("title") or (rec["name"] if rec["kind"] in FALLBACK_KINDS else "")


def intro_yomi(text: str, title: str) -> str:
    """「タイトル（よみ、…）」から正式名称の読みを取る"""
    if not text.startswith(title):
        return ""
    m = INTRO_YOMI.match(text[len(title):])
    return to_kata(m.group(1)) if m else ""


# ---------------------------------------------------------------- 表層の生成
def shorten(name: str) -> str:
    for long, short in SHORTEN:
        if long in name:
            return name.replace(long, short, 1)
    return name


def strip_founder(name: str) -> str:
    """設置者接頭辞(○○県立/○○市立/学校法人…)を落とす"""
    m = FOUNDER_PREFIX.match(name)
    rest = name[m.end():] if m else name
    return rest or name


def strip_type_words(name: str) -> str:
    """校種語(接頭・接尾どちらでも)を落として固有部分だけにする"""
    for w in TYPE_PREFIX:
        if name.startswith(w):
            name = name[len(w):]
            break
    for w in TYPE_WORDS:
        if name.endswith(w):
            return name[: -len(w)]
    return name


def drop_founder_prefix(full: str, pref: str, founder: str) -> str:
    """設置者接頭辞を落とす。北海道・宮城県・長野県のように「立」を付けずに
    「北海道札幌南高等学校」「宮城県名取高等学校」と名乗る県立校があるので、
    公立校が自分の都道府県名で始まる場合はその都道府県名も落とす"""
    s = strip_founder(full)
    if s != full:
        return s
    if founder == "公立" and pref and full.startswith(pref) and len(full) > len(pref) + 2:
        return full[len(pref):]
    return s


def core_name(full: str, pref: str, founder: str) -> str:
    """固有部分(設置者接頭辞も校種語も落とした残り)"""
    return strip_type_words(drop_founder_prefix(full, pref, founder)).strip(" 　・-")


def shorten_pron(p: str) -> str:
    for long, short in PRON_SHORTEN:
        if p.endswith(long):
            return p[: -len(long)] + short
    return p


def strip_pron_type(p: str) -> str:
    for w in PRON_TYPE_WORDS:
        if p.endswith(w) and len(p) > len(w):
            return p[: -len(w)]
    return ""


def parse_address(addr: str, pref_hint: str = "") -> tuple:
    """住所から (都道府県, 市区町村)。政令市は区を落として市に丸める
    (stations.csv の city 列と同じ粒度。東京23区は区のまま)"""
    pref = next((p for p in PREFS if addr.startswith(p)), "") or pref_hint
    # 「字北海道」のような小字を都道府県と誤認しないよう、先頭一致を優先する
    i = addr.find(pref) if pref else -1
    rest = addr[i + len(pref):] if i >= 0 else addr
    # 郡・支庁は落とす(郡山市の「郡」を誤って落とさないよう、郡名は2字以上・
    # 後ろに町村が続くことを要求する)
    m = re.match(r"^.{2,8}?郡(?=.{1,8}?[町村])|^.{2,6}?支庁", rest)
    if m:
        rest = rest[m.end():]
    # 「四日市市」「野々市市」を切らないよう貪欲に、ただし先頭8字までで探す
    for suffix in ("市", "区", "町", "村"):
        m = re.match(r"^(.{0,7}" + suffix + ")", rest)
        if m:
            return pref, m.group(1)
    return pref, ""


def plausible_pron(pron: str, surface: str) -> str:
    """読みの長さが表層と釣り合っているか(接頭辞込みの読みの取り違えを防ぐ)"""
    if not pron:
        return ""
    n = len(surface)
    return pron if n <= len(pron) <= n * 3.0 + 1 else ""


SUFFIX_KANA = [("大学校", "ダイガッコウ"), ("大学", "ダイガク"), ("高校", "コウコウ"),
               ("短大", "タンダイ"), ("高専", "コウセン"), ("中等", "チュウトウ"),
               ("こども園", "コドモエン"), ("幼稚園", "ヨウチエン"), ("保育園", "ホイクエン"),
               ("専門学校", "センモンガッコウ"), ("学校", "ガッコウ"),
               ("学園", "ガクエン"), ("学院", "ガクイン"), ("小中", "ショウチュウ"),
               ("中", "チュウ"), ("小", "ショウ")]


def suffix_ok(surface: str, kana: str) -> bool:
    """表層の校種語と読みの終わりが一致するか(通称の読みの取り違えを防ぐ。
    「京都大学」に P1814 の「きょうだい」が付くのを止める)"""
    for s, k in SUFFIX_KANA:
        if surface.endswith(s):
            return kana.endswith(k)
    return True


FOUNDER_KANA = re.compile(
    r"^.{2,10}?(?:シリツ|チョウリツ|ソンリツ|クリツ|グンリツ|クミアイリツ|ケンリツ|フリツ|トリツ|ドウリツ)")


def strip_pref_kana(kana: str, pref: str) -> str:
    """読みの先頭にある設置者(「サイタマケンリツ」「コウベシリツ」)を落とす。
    落とせなければそのまま返す"""
    if pref in PREFS:
        head = PREF_KANA[PREFS.index(pref)]
        for pre in (head + "リツ", head):
            if kana.startswith(pre) and len(kana) > len(pre) + 1:
                return kana[len(pre):]
    m = FOUNDER_KANA.match(kana)
    if m and len(kana) > m.end() + 1:
        return kana[m.end():]
    return kana


def char_subset(cand: str, pool: str) -> bool:
    """通称の全ての文字が正式名称・記事名に含まれるか(無関係な旧校名を落とす)"""
    return all(c in pool for c in cand)


def add_nick(add, cand: str, pool: str, yomi: str) -> None:
    """通称候補を検査してから追加する。
    - 2〜8文字。長い異表記(「県立○○高等学校」など)は採らない
    - 校種語で終わるものは通称ではなく正式名称の言い換えなので採らない
    - 全ての文字が正式名称・記事名に含まれること(旧校名・別の学校名を落とす)
    """
    if not (2 <= len(cand) <= 8) or cand in NICK_STOP:
        return
    if cand.endswith(("学校", "大学", "幼稚園", "こども園", "保育園", "学園", "学院")):
        return
    # 「埼玉県立浦和高校」「県立浦和」のような設置者付きの異表記は通称ではない
    if FOUNDER_PREFIX.match(cand).end() > 0 or cand.startswith(FOUNDER_WORDS):
        return
    if not char_subset(cand, pool):
        return
    add(cand, "nick", yomi)


def build_rows(rec: dict, wd: dict, extracts: dict, next_id: int, fixed_id) -> list:
    full = rec["name"]
    stype = SCHOOL_TYPE.get(rec["kind"], "")
    founder = FOUNDER.get(rec["founder"], "")
    no = int(rec["pref_no"]) if rec["pref_no"].isdigit() else 0
    hint = PREFS[no - 1] if 1 <= no <= 47 else ""
    pref, city = parse_address(rec["address"], hint)
    status = "former" if (rec["branch"] == "9" or rec["closed"]) else "current"
    w = wd.get(rec["code"], {})
    qid = w.get("qid", "")
    title = lookup_title(rec, w)
    text = extracts.get(title, "") if title else ""

    # ---- 読みの材料
    # 設置者接頭辞を落とした名称(common の素)と、その読み
    stripped = drop_founder_prefix(full, pref, founder)
    # P1814・ひらがなのaltLabel は「設置者を除いた名称」の読みであることが多い
    kana_cands = [to_kata(k) for k in w.get("kana", [])]
    kana_cands += [to_kata(a) for a in w.get("alt", []) if HIRA.match(a)]
    kana_cands = [k for k in kana_cands if k]
    if title == full:
        # 記事冒頭の「正式名称(よみ)」。接頭辞が付いた読みなので落としてから使う
        y = intro_yomi(text, title)
        if y:
            kana_cands.append(y)
    # 読みから接頭辞を落とすのは、表層側でも実際に接頭辞を落としたときだけ
    # (「東京都市大学」の読みを削らないため)
    if stripped != full:
        kana_cands = [strip_pref_kana(k, pref) for k in kana_cands]
    common = shorten(stripped)
    kana_common = next((k for k in (shorten_pron(c) for c in kana_cands)
                        if suffix_ok(common, k)), "")
    kana_core = next((c for c in (strip_pron_type(k) for k in kana_cands) if c), "")

    surfaces = []   # (surface, type, pronunciation)
    seen = set()

    def add(s, t, p=""):
        s = clean_field(s)
        if not s or s.isdigit() or s in seen:
            return
        seen.add(s)
        p = p if p and KATA_ONLY.match(p) else ""
        surfaces.append((s, t, plausible_pron(p, s)))

    core = core_name(full, pref, founder)
    if core:
        add(common, "common", kana_common)
    add(core, "name", kana_core)

    # ---- 通称(Wikipedia)
    pool = full + title + core
    for cand, yomi in parse_nicks(text):
        add_nick(add, clean_field(cand), pool, to_kata(yomi))
    # ---- 別名(Wikidata)
    for a in w.get("alt", []):
        a = clean_field(a)
        if a and not HIRA.match(a) and not re.search(r"[（()）「」旧称]", a):
            add_nick(add, a, pool, "")

    gid = fixed_id if fixed_id is not None else next_id
    return [{"id": str(gid), "original": full, "surface": s, "pronunciation": p,
             "type": t, "school_type": stype, "founder": founder,
             "prefecture": pref, "city": city, "status": status,
             "code": rec["code"], "wikidata": qid}
            for s, t, p in surfaces]


def main() -> int:
    refresh = "--refresh" in sys.argv
    CACHE.mkdir(exist_ok=True)

    records = fetch_mext(refresh)
    if not MIN_SCHOOLS <= len(records) <= MAX_SCHOOLS:
        print(f"error: implausible school count: {len(records)}", file=sys.stderr)
        return 1
    records = [r for r in records if r["name"] and r["kind"] in SCHOOL_TYPE]
    seen_codes = set()
    uniq = []
    for r in records:
        if r["code"] in seen_codes:
            continue
        seen_codes.add(r["code"])
        uniq.append(r)
    records = sorted(uniq, key=lambda r: r["code"])
    print(f"mext: {len(records)} schools")

    wd = fetch_wikidata(refresh)
    titles = sorted({t for t in (lookup_title(r, wd.get(r["code"], {})) for r in records) if t})
    extracts = fetch_extracts(titles, refresh)

    # 既存の id を学校コードで引き継ぐ(ADR 00014)
    old_ids, old_rows = {}, []
    if CSV_PATH.exists():
        with CSV_PATH.open(encoding="utf-8") as f:
            old_rows = list(csv.DictReader(f))
        for r in old_rows:
            if r.get("code"):
                old_ids.setdefault(r["code"], r["id"])
    next_id = max((int(v) for v in old_ids.values()), default=-1) + 1

    rows = []
    for rec in records:
        fixed = old_ids.get(rec["code"])
        rs = build_rows(rec, wd, extracts, next_id, int(fixed) if fixed else None)
        if fixed is None:
            next_id += 1
        rows.extend(rs)
    # 名簿から消えた学校の行は落とさずそのまま残す
    kept = [r for r in old_rows if r.get("code") and r["code"] not in seen_codes]
    rows.extend(kept)
    order = {"common": 0, "name": 1, "nick": 2}
    rows.sort(key=lambda r: (int(r["id"]), order.get(r["type"], 9)))

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    # 末尾改行なしで書く(soramimic側のパーサが最終空行で落ちるため)
    CSV_PATH.write_text(buf.getvalue().rstrip("\n"), encoding="utf-8")

    ids = {r["id"] for r in rows}
    npron = sum(1 for r in rows if r["pronunciation"])
    nnick = sum(1 for r in rows if r["type"] == "nick")
    print(f"school.csv: {len(ids)} schools / {len(rows)} rows "
          f"(pronunciation {npron}, nick {nnick}, kept {len(kept)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
