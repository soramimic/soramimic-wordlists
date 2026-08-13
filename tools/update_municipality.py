#!/usr/bin/env python3
"""municipality.csv(市区町村)を総務省・Wikidata・Wikipediaから生成する。

出典:
- 現存の市区町村・団体コード・都道府県・カナ: 総務省「全国地方公共団体コード」
  (政府標準利用規約。CC BY 4.0 互換)
- 廃止市区町村・QID・読み仮名・人口: Wikidata (CC0)
- description(記事冒頭のトリビア): ja.wikipedia (CC BY-SA 4.0)

方式:
- 1自治体 = 1グループ(id)。同じ id に表記バリエーションを並べる
  - type=full : 正式名称そのまま(札幌市)
  - type=short: 末尾の 市/区/町/村 を落とした形(札幌)。落として空になる・
    full と同じになる・同じ id 内で表層が重複する場合は行を作らない
- 現存(status=current)は総務省のコード表が母集団。政令指定都市の行政区は
  parent 列に親の市名を入れる(original は「中央区」で、親は「札幌市」)
- 廃止(status=former)は Wikidata の「廃止された日本の市町村」Q18663566 の
  サブクラス閉包。ラベルの括弧注記を落とし、末尾が市/区/町/村 の日本語名だけ
  を採る。現存と (名称, 都道府県) が一致する行は現存側を優先して落とす
- 既存行は劣化させない(ADR 00014)。id は既存CSVのキー(団体コード、無ければ
  QID、無ければ 都道府県+親+名称)から引き継ぎ、新規のみ連番を増やす。列の値は
  今回取得できたときだけ上書きする
- 総務省のコード表から消えた現存行は status=former に落とす(行は消さない)
- image / image_page は別の画像補完ツールが付与し、全件再生成時も保持する

取得結果は tools/.cache/municipality/(Git管理外)に保存し、再実行時は
そこから読む。全件引き直すときは --refresh。

usage: python3 tools/update_municipality.py [--refresh]
"""

import csv
import io
import json
import re
import sys
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import fetch_extracts, make_description, sparql_post  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "municipality.csv"
CACHE = Path(__file__).resolve().parent / ".cache" / "municipality"

UA = {"User-Agent": "soramimic-wordlists-updater/1.0 "
                    "(https://github.com/soramimic/soramimic-wordlists)"}
# 総務省「全国地方公共団体コード」現行コード表(Sheet1=都道府県+市区町村、
# Sheet2=政令指定都市とその行政区)。https://www.soumu.go.jp/denshijiti/code.html
SOUMU_CODE_XLSX = "https://www.soumu.go.jp/main_content/000925835.xlsx"
# e-Stat 令和2年(2020年)国勢調査「都道府県・市区町村別の主な結果」。
# 確定した過去の公表なので statInfId は変わらない(住民基本台帳のExcelは
# 公表のたびにファイルIDが変わるので直リンクにできない)。APIキー不要
ESTAT_CENSUS_XLSX = ("https://www.e-stat.go.jp/stat-search/file-download"
                     "?statInfId=000032143614&fileKind=0")
CENSUS_YEAR = "2020"
# 廃止された日本の市町村
FORMER_CLASS = "Q18663566"
# 都道府県(廃藩置県期の県も含むので、現行47都道府県の名前で絞る)
PREF_CLASS = "Q50337"

COLS = ["id", "original", "surface", "pronunciation", "type", "prefecture",
        "parent", "status", "population", "code", "description", "image",
        "image_page", "wikidata", "municipality_type"]

SUFFIXES = ("市", "区", "町", "村")
# 接尾辞のカナ。同じ漢字でも自治体ごとに読みが違う(町=チョウ/マチ、
# 村=ソン/ムラ)ので、出典のカナの末尾に一致したものを落とす
SUFFIX_KANA = {"市": ("シ",), "区": ("ク",), "町": ("チョウ", "マチ"),
               "村": ("ソン", "ムラ")}
KATAKANA_ONLY = re.compile(r"^[ァ-ヶー・]+$")
HIRA2KATA = str.maketrans({chr(k): chr(k + 0x60)
                           for k in range(ord("ぁ"), ord("ゖ") + 1)})
# ラベル末尾・途中の括弧注記(曖昧さ回避 / (旧) など)
PAREN = re.compile(r"[（(][^（）()]*[）)]")
# 自治体名として許す文字(漢字・かな・ヶヵ・々・長音)。英数字が混ざる行は捨てる
NAME_OK = re.compile(r"^[々〆一-鿿ぁ-ゖァ-ヶー]+$")
# 妥当性ガード(これを下回ったら取得失敗とみなして中断する)
MIN_CURRENT = 1700
MIN_FORMER = 8000

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NSR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


# --------------------------------------------------------------------------
# 取得ユーティリティ
# --------------------------------------------------------------------------
def http_bytes(url: str, retries: int = 4) -> bytes:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as res:
                return res.read()
        except Exception as ex:
            print(f"retry {attempt}: {ex}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"failed: {url}")


def cached(name: str, refresh: bool, build):
    """取得結果を tools/.cache/municipality/<name>.json に貯める。"""
    path = CACHE / f"{name}.json"
    if not refresh and path.exists():
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    data = build()
    CACHE.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    return data


def read_xlsx(data: bytes) -> dict:
    """xlsx(zip+XML)をシート名 -> 行(列文字 -> 値)の辞書で読む。

    openpyxl を入れずに標準ライブラリだけで読むための最小実装。ふりがな
    (rPh)は本文ではないので読み飛ばす(拾うと「熊本市西区クマモトシニシク」
    のように連結されてしまう)。"""
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(NS + "si"):
            parts = [t.text or "" for t in si.findall(NS + "t")]
            for r in si.findall(NS + "r"):
                parts += [t.text or "" for t in r.findall(NS + "t")]
            shared.append("".join(parts))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target")
            for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for sh in wb.find(NS + "sheets"):
        target = rels[sh.get(NSR + "id")]
        target = target.lstrip("/") if target.startswith("/") else "xl/" + target
        rows = []
        for row in ET.fromstring(z.read(target)).iter(NS + "row"):
            cells = {}
            for c in row.findall(NS + "c"):
                col = re.match(r"[A-Z]+", c.get("r")).group()
                if c.get("t") == "s":
                    v = c.find(NS + "v")
                    val = shared[int(v.text)] if v is not None else ""
                elif c.get("t") == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(NS + "t"))
                else:
                    v = c.find(NS + "v")
                    val = v.text if v is not None else ""
                cells[col] = val or ""
            rows.append(cells)
        out[sh.get("name")] = rows
    return out


# --------------------------------------------------------------------------
# 表記の正規化
# --------------------------------------------------------------------------
def to_kata(s: str) -> str:
    """半角カナ・ひらがなをカタカナに正規化。カタカナ以外が残ったら空。"""
    s = unicodedata.normalize("NFKC", s or "").translate(HIRA2KATA)
    s = re.sub(r"[\s　]+", "", s)
    return s if s and KATAKANA_ONLY.match(s) else ""


def as_int(v: str) -> str:
    """人口をカンマなしの整数文字列にする(Wikidataは小数で返すことがある)。"""
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return ""


def safe(s: str) -> str:
    """CSVを壊す文字を落とす(利用側はクオート非対応の素朴なsplit)。"""
    return (s or "").replace(",", "、").replace('"', "”").replace("\n", " ").strip()


def short_form(name: str, kana: str):
    """正式名称と読みから (短縮表層, 短縮読み) を返す。作れなければ None。"""
    if not name or name[-1] not in SUFFIXES:
        return None
    short = name[:-1]
    if not short or short == name:
        return None
    sk = ""
    for cand in SUFFIX_KANA[name[-1]]:
        if kana.endswith(cand) and len(kana) > len(cand):
            sk = kana[:-len(cand)]
            break
    return short, sk


def municipality_type(name: str) -> str:
    """正式名称から自治体種別(市/区/町/村)を返す。"""
    return name[-1] if name and name[-1] in SUFFIXES else ""


def clean_label(label: str) -> str:
    """Wikidataラベルの括弧注記((曖昧さ回避) など)を落とす。"""
    prev = None
    while prev != label:
        prev = label
        label = PAREN.sub("", label)
    return re.sub(r"[\s　]+", "", label)


# --------------------------------------------------------------------------
# 総務省: 現存の市区町村
# --------------------------------------------------------------------------
def fetch_current(refresh: bool) -> list:
    """[{code, original, pronunciation, prefecture, parent}] を返す。"""
    def build():
        sheets = read_xlsx(http_bytes(SOUMU_CODE_XLSX))
        names = list(sheets)
        if len(names) < 2:
            raise RuntimeError("総務省コード表のシート構成が想定と違う")
        plain, ordinance = sheets[names[0]], sheets[names[1]]
        rows, seen = [], set()
        for r in plain[1:]:
            code, pref, name = r.get("A", ""), r.get("B", ""), r.get("C", "")
            if not code or not name:  # 市区町村名が空の行は都道府県そのもの
                continue
            rows.append({"code": code, "original": name,
                         "pronunciation": to_kata(r.get("E", "")),
                         "prefecture": pref, "parent": ""})
            seen.add(code)
        # 政令指定都市シート: 市の行(Sheet1と重複)を親として、行政区を拾う
        cities = {}
        for r in ordinance[1:]:
            name = r.get("C", "")
            if name and not name.endswith("区"):
                cities[name] = to_kata(r.get("E", ""))
        for r in ordinance[1:]:
            code, pref, name = r.get("A", ""), r.get("B", ""), r.get("C", "")
            if not code or not name or code in seen or not name.endswith("区"):
                continue
            kana = to_kata(r.get("E", ""))
            parent = max((c for c in cities if name.startswith(c)),
                         key=len, default="")
            ward = name[len(parent):] if parent else name
            pkana = cities.get(parent, "")
            if pkana and kana.startswith(pkana):
                kana = kana[len(pkana):]
            rows.append({"code": code, "original": ward, "pronunciation": kana,
                         "prefecture": pref, "parent": parent})
            seen.add(code)
        return rows
    return cached("current", refresh, build)


# --------------------------------------------------------------------------
# e-Stat: 国勢調査の市区町村別人口
# --------------------------------------------------------------------------
def fetch_population(refresh: bool) -> dict:
    """標準地域コード(5桁) -> 総人口。政令指定都市の行政区も含む。"""
    def build():
        sheets = read_xlsx(http_bytes(ESTAT_CENSUS_XLSX))
        rows = next(iter(sheets.values()))
        pops = {}
        for r in rows:
            name, pop, kind = r.get("B", ""), r.get("E", ""), r.get("D", "")
            m = re.match(r"^(\d{5})_", name)
            # 地域識別コード a = 全国・都道府県の集計行なので落とす
            if not m or kind == "a" or not pop.isdigit():
                continue
            pops[m.group(1)] = pop
        return pops
    return cached("population", refresh, build)


# --------------------------------------------------------------------------
# Wikidata
# --------------------------------------------------------------------------
def wd_batches(qids: list, size: int, query: str):
    """VALUES ?x { ... } を size 件ずつ埋めて POST で投げる。"""
    for i in range(0, len(qids), size):
        chunk = qids[i:i + size]
        values = " ".join("wd:" + q for q in chunk)
        data = sparql_post(query % values)
        yield data["results"]["bindings"]
        print(f"  wikidata {min(i + size, len(qids))}/{len(qids)}")
        time.sleep(1.0)


def fetch_by_code(refresh: bool) -> dict:
    """全国地方公共団体コード -> {qid, title, pop, popyear}(現存の突合用)。"""
    def build():
        q = """SELECT ?x ?code ?title ?pop ?date WHERE {
  ?x wdt:P429 ?code .
  OPTIONAL { ?a schema:about ?x ; schema:isPartOf <https://ja.wikipedia.org/> ;
             schema:name ?title }
  OPTIONAL { ?x p:P1082 ?st . ?st ps:P1082 ?pop .
             OPTIONAL { ?st pq:P585 ?date } }
}"""
        out = {}
        for b in sparql_post(q)["results"]["bindings"]:
            code = b["code"]["value"]
            e = out.setdefault(code, {"qid": b["x"]["value"].rsplit("/", 1)[1],
                                      "title": "", "pop": "", "popyear": ""})
            if "title" in b:
                e["title"] = b["title"]["value"]
            if "pop" in b:
                year = b.get("date", {}).get("value", "")[:4]
                if year >= e["popyear"]:
                    e["pop"], e["popyear"] = b["pop"]["value"], year
        return out
    return cached("by_code", refresh, build)


def fetch_former(refresh: bool, cur_prefs: set) -> list:
    """廃止市区町村を [{qid, label, kana, dissolved, code, title, pop,
    prefecture}] で返す。prefecture は現行47都道府県に到達したものだけ。"""
    def build():
        d = sparql_post("SELECT ?x WHERE { ?x wdt:P31/wdt:P279* wd:%s }"
                        % FORMER_CLASS)
        qids = sorted({b["x"]["value"].rsplit("/", 1)[1]
                       for b in d["results"]["bindings"]},
                      key=lambda q: int(q[1:]))
        print(f"former candidates: {len(qids)}")
        detail = """SELECT ?x ?label ?kana ?dissolved ?code ?title ?pop ?date
                           ?prefLabel WHERE {
  VALUES ?x { %s }
  OPTIONAL { ?x rdfs:label ?label FILTER(LANG(?label)='ja') }
  OPTIONAL { ?x wdt:P1814 ?kana }
  OPTIONAL { ?x wdt:P576 ?dissolved }
  OPTIONAL { ?x wdt:P429 ?code }
  OPTIONAL { ?a schema:about ?x ; schema:isPartOf <https://ja.wikipedia.org/> ;
             schema:name ?title }
  OPTIONAL { ?x p:P1082 ?st . ?st ps:P1082 ?pop .
             OPTIONAL { ?st pq:P585 ?date } }
  OPTIONAL { ?x wdt:P131* ?pref . ?pref wdt:P31/wdt:P279* wd:%s .
             ?pref rdfs:label ?prefLabel FILTER(LANG(?prefLabel)='ja') }
}""" % ("%s", PREF_CLASS)
        ents = {}
        for bindings in wd_batches(qids, 250, detail):
            for b in bindings:
                q = b["x"]["value"].rsplit("/", 1)[1]
                e = ents.setdefault(q, {"qid": q, "label": "", "kana": "",
                                        "dissolved": "", "code": "", "title": "",
                                        "pop": "", "popyear": "", "prefs": []})
                for k in ("label", "kana", "code", "title"):
                    if k in b and not e[k]:
                        e[k] = b[k]["value"]
                if "dissolved" in b and not e["dissolved"]:
                    e["dissolved"] = b["dissolved"]["value"][:10]
                if "pop" in b:
                    year = b.get("date", {}).get("value", "")[:4]
                    if year >= e["popyear"]:
                        e["pop"], e["popyear"] = b["pop"]["value"], year
                if "prefLabel" in b:
                    p = b["prefLabel"]["value"]
                    if p not in e["prefs"]:
                        e["prefs"].append(p)
        out = []
        for e in ents.values():
            pref = next((p for p in e["prefs"] if p in cur_prefs), "")
            out.append({"qid": e["qid"], "label": e["label"], "kana": e["kana"],
                        "dissolved": e["dissolved"], "code": e["code"],
                        "title": e["title"], "pop": e["pop"],
                        "prefecture": pref})
        return out
    return cached("former", refresh, build)


# --------------------------------------------------------------------------
# Wikipedia: description
# --------------------------------------------------------------------------
def fetch_intros(titles: list, refresh: bool) -> dict:
    """記事タイトル -> 冒頭文。取得済みのタイトルは再取得しない。"""
    path = CACHE / "intros.json"
    have = {}
    if not refresh and path.exists():
        with path.open(encoding="utf-8") as fh:
            have = json.load(fh)
    todo = sorted({t for t in titles if t and t not in have})
    print(f"wikipedia intros: {len(have)} cached, {len(todo)} to fetch")
    CACHE.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(todo), 400):
        chunk = todo[i:i + 400]
        have.update({t: (v or "") for t, v in fetch_extracts(chunk, limit=400).items()})
        for t in chunk:
            have.setdefault(t, "")
        with path.open("w", encoding="utf-8") as fh:
            json.dump(have, fh, ensure_ascii=False)
        print(f"  wikipedia {min(i + 400, len(todo))}/{len(todo)}")
    return have


# --------------------------------------------------------------------------
# 組み立て
# --------------------------------------------------------------------------
def row_key(status: str, code: str, qid: str, pref: str, parent: str,
            original: str) -> str:
    """自治体グループの永続キー(id を引き継ぐための同一性)。

    現存は団体コード、廃止はQIDを主キーにする。**改称した自治体は旧名と新名で
    団体コードが同じ**(篠山市→丹波篠山市)なので、現存と廃止でキーの名前空間を
    分けないと衝突する。"""
    if status == "current" and code:
        return "c" + code
    if qid:
        return "q" + qid
    if code:
        return "c" + code
    return "n%s|%s|%s" % (pref, parent, original)


def load_existing() -> tuple:
    """既存CSVから キー -> {id, 行(type別)} と 次のid を取り出す。"""
    if not CSV_PATH.exists():
        return {}, 0
    with CSV_PATH.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    groups = {}
    for r in rows:
        key = row_key(r.get("status", ""), r.get("code", ""),
                      r.get("wikidata", ""), r.get("prefecture", ""),
                      r.get("parent", ""), r.get("original", ""))
        g = groups.setdefault(key, {"id": r["id"], "rows": {}})
        g["rows"][r.get("type", "full")] = r
    next_id = max((int(r["id"]) for r in rows), default=-1) + 1
    return groups, next_id


def keep(new: str, old: str) -> str:
    """今回取れた値だけを採用する(ADR 00014: 既存行を劣化させない)。"""
    return new if new else (old or "")


def build_group(g: dict, existing: dict) -> list:
    """1自治体分の行(full/short)を作る。"""
    old = existing.get("rows", {}) if existing else {}
    of, os_ = old.get("full", {}), old.get("short", {})
    base = {
        "id": existing["id"] if existing else g["id"],
        "original": safe(g["original"]) or of.get("original", ""),
        "prefecture": keep(safe(g["prefecture"]), of.get("prefecture", "")),
        "parent": keep(safe(g["parent"]), of.get("parent", "")),
        "status": g["status"],
        "population": keep(as_int(g["population"]), of.get("population", "")),
        "code": keep(g["code"], of.get("code", "")),
        "description": keep(safe(g["description"]), of.get("description", "")),
        "image": of.get("image", ""),
        "image_page": of.get("image_page", ""),
        "wikidata": keep(g["wikidata"], of.get("wikidata", "")),
        "municipality_type": municipality_type(safe(g["original"])),
    }
    kana = keep(g["pronunciation"], of.get("pronunciation", ""))
    rows = [dict(base, surface=base["original"], pronunciation=kana, type="full")]
    sf = short_form(base["original"], kana)
    if sf and sf[0] != base["original"]:
        rows.append(dict(base, surface=safe(sf[0]),
                         pronunciation=keep(sf[1], os_.get("pronunciation", "")),
                         type="short"))
    # 同一 id 内で表層が重複する行は作らない
    out, seen = [], set()
    for r in rows:
        if r["surface"] and r["surface"] not in seen:
            seen.add(r["surface"])
            out.append(r)
    return out


def main() -> int:
    refresh = "--refresh" in sys.argv

    current = fetch_current(refresh)
    print(f"総務省コード表: {len(current)} 市区町村(行政区を含む)")
    if len(current) < MIN_CURRENT:
        print(f"error: 現存市区町村が少なすぎる: {len(current)}", file=sys.stderr)
        return 1
    # 廃止自治体の P131 は廃藩置県期の県(飾磨県など)にも繋がるので、
    # prefecture 列に入れるのは現行47都道府県の名前だけにする
    pref_names = {c["prefecture"] for c in current if c["prefecture"]}
    by_code = fetch_by_code(refresh)
    pops = fetch_population(refresh)
    print(f"国勢調査({CENSUS_YEAR})の人口: {len(pops)} 市区町村")
    former = fetch_former(refresh, pref_names)
    print(f"Wikidata 廃止市区町村: {len(former)} 件(生)")
    if len(former) < MIN_FORMER:
        print(f"error: 廃止市区町村が少なすぎる: {len(former)}", file=sys.stderr)
        return 1

    groups, dropped = [], {"label": 0, "suffix": 0, "dup": 0, "current": 0}
    cur_names = set()
    for c in current:
        wd = by_code.get(c["code"], {})
        cur_names.add((c["original"], c["prefecture"]))
        # 人口は国勢調査を優先し、取れない行だけ Wikidata(P1082)で補う
        pop = pops.get(c["code"][:5]) or wd.get("pop", "")
        groups.append({"key": row_key("current", c["code"], "", "", "", ""),
                       "original": c["original"],
                       "pronunciation": c["pronunciation"],
                       "prefecture": c["prefecture"], "parent": c["parent"],
                       "status": "current", "population": pop,
                       "code": c["code"], "title": wd.get("title", ""),
                       "wikidata": wd.get("qid", ""), "sort": (0, c["code"])})

    seen_former = set()
    pref_order = {c["prefecture"]: i for i, c in enumerate(current)}
    for e in former:
        name = clean_label(e["label"])
        if not name or not NAME_OK.match(name):
            dropped["label"] += 1
            continue
        if name[-1] not in SUFFIXES:
            dropped["suffix"] += 1
            continue
        pref = e["prefecture"]
        if (name, pref) in cur_names:
            dropped["current"] += 1
            continue
        sig = (name, pref, e["dissolved"])
        if sig in seen_former:
            dropped["dup"] += 1
            continue
        seen_former.add(sig)
        groups.append({"key": row_key("former", e["code"], e["qid"], "", "", ""),
                       "original": name, "pronunciation": to_kata(e["kana"]),
                       "prefecture": pref, "parent": "", "status": "former",
                       "population": e["pop"], "code": e["code"],
                       "title": e["title"], "wikidata": e["qid"],
                       "sort": (1, "%04d" % pref_order.get(pref, 9999), name)})
    print(f"廃止から除外: ラベル不正 {dropped['label']} / "
          f"市区町村でない {dropped['suffix']} / 現存と同名 {dropped['current']} / "
          f"重複 {dropped['dup']}")

    intros = fetch_intros([g["title"] for g in groups], refresh)
    for g in groups:
        intro = intros.get(g["title"], "")
        desc = make_description(intro, "", g["original"]) if intro else ""
        g["description"] = "" if desc == "NA" else desc

    existing, next_id = load_existing()
    groups.sort(key=lambda g: g["sort"])
    rows = []
    for g in groups:
        ex = existing.pop(g["key"], None)
        if ex is None:
            g["id"] = str(next_id)
            next_id += 1
        rows.extend(build_group(g, ex))
    # 今回の母集団から消えた既存グループ(合併等)は status=former にして残す
    for key, ex in existing.items():
        for t in ("full", "short"):
            if t in ex["rows"]:
                r = dict(ex["rows"][t])
                r["status"] = "former"
                r["municipality_type"] = municipality_type(r.get("original", ""))
                rows.append(r)
        print(f"note: 母集団から消えたので former に落とす: "
              f"{ex['rows'].get('full', {}).get('original', key)}")

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n",
                       extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    # 末尾改行なしで書く(soramimic側のパーサが最終空行で落ちるため)
    CSV_PATH.write_text(buf.getvalue().rstrip("\n"), encoding="utf-8")

    n_cur = sum(1 for g in groups if g["status"] == "current")
    filled = {c: sum(1 for r in rows if r.get(c)) for c in
              ("pronunciation", "population", "code", "description", "wikidata")}
    print(f"municipality.csv: {len(rows)} 行 / {len(groups)} 自治体 "
          f"(現存 {n_cur} / 廃止 {len(groups) - n_cur})")
    for c, n in filled.items():
        print(f"  {c}: {n}/{len(rows)} ({n * 100 / len(rows):.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
