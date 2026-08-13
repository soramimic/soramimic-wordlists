#!/usr/bin/env python3
"""myoji.csv(日本の名字)を生成・更新する。

出典と、その組み合わせを選んだ理由(詳細は docs/adr/00038):

- **母集団と読み**: SudachiDict(Works Applications, **Apache License 2.0**)の
  辞書ソース `small_lex.csv` / `core_lex.csv` / `notcore_lex.csv` から、品詞が
  `名詞,固有名詞,人名,姓` のエントリを抜く。表記と読み(カタカナ)がそのまま取れる
- **rank**: Wikidata(CC0)の「日本国籍の人物(P31=Q5 かつ P27=Q17)の姓(P734)」を
  日本語ラベルごとに数えた **著名人ベースの参考順位**
- **description**: ja.wikipedia(CC BY-SA 4.0)の姓記事の冒頭。「東 (姓)」
  「佐藤氏」「近衛家」のように姓そのものを説明している記事名を優先して探し、
  由来・分布(「〜に多い」「発祥」)の文があればそれを拾う
- **wikidata**: rank の集計に使った姓アイテムの QID(CC0)
- **verified**: このリポジトリの実在人名リスト(baseball/football/scientist/
  youtuber の type=family)、Web NDL Authorities、Wikidataの人物に使われる姓、
  または公式人物ページの確認台帳に同じ(表記, 読み)があるか。SudachiDict には破格の
  読み(`伊藤 イロウ` `井上 イトウ` `星野 コシノ`)が混ざるので、**行は消さずに
  フラグで絞れるようにする**。`no` は誤りとは限らず裏が取れなかっただけ
- **evidence_sources**: 読みを裏付けたソース。`person_lists` / `ndl` /
  `wikidata_person` / `official_web` は実在人名、`jmnedict` は辞書収録の裏付け。
  JMnedict 単独では verified=yes にしない

**rank は世帯数・人口順位ではない。** 日本には姓別の公的統計が無く、世帯数・順位を
持つ民間サイト(名字由来net・日本の苗字七千傑等)は利用規約でスクレイピング・再配布
を禁じているので使わない。本リストの rank は「Wikidata に人物項目がある著名人に
その姓が何人いるか」の順位で、実際の人口順位とは別物(芸名・筆名の偏り、Wikidata の
整備状況の偏りをそのまま含む)。用途は「よく見る姓を上から取る」程度の目安に限る。

差分方針(ADR 00014):
- 既存行の id・表記・読みは絶対に書き換えない。新しい(表記, 読み)の組だけ追記する
- description / wikidata は**空欄の補完のみ**行い、既に入っている値は書き換えない
- **rank だけは毎回全行を再計算して上書きする**(youtuber の subscribers と同じ
  明示的な例外)。順位は集計のスナップショットなので、一部だけ更新すると同じ列の中で
  基準時点が混ざって順位として読めなくなるため

環境変数:
- `MYOJI_CACHE`: SudachiDict の zip を置くディレクトリ(開発用)。指定すると
  2回目以降はダウンロードを省略する。CI では未設定=毎回取得

usage: python3 tools/update_myoji.py
"""

import csv
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import (
    HIRA2KATA,
    UA,
    _sanitize_desc,
    api,
    clean_ws,
    make_description,
    sparql,
    write_csv_no_trailing_newline,
)

CSV_PATH = Path(__file__).resolve().parent.parent / "myoji.csv"
OFFICIAL_EVIDENCE_PATH = Path(__file__).resolve().parent / "myoji_official_evidence.jsonl"
CACHE_DIR = os.environ.get("MYOJI_CACHE")

# 既存利用側の位置依存を壊しにくいよう、新しい列は末尾に追加する。
COLS = ["id", "original", "surface", "pronunciation", "verified", "rank",
        "description", "wikidata", "evidence_sources"]

# verified の判定に使う「実在の日本人の名簿」。このリポジトリ内の実在人名リストの
# type=family 行(姓とその読み)を突き合わせる。架空のリスト(fictional_*)は
# 実在の裏付けにならないので使わない
PERSON_LISTS = ("baseball.csv", "football.csv", "scientist.csv",
                "youtuber.csv")

# ---- SudachiDict --------------------------------------------------------
# 辞書ソースCSVは git から外れて S3 配布になっている(GitHub の
# src/main/text/ には synonyms.txt しか残っていない)。バージョン付きの
# ディレクトリが並んでいるので、最新の日付を選んで取る。
S3_BUCKET = "https://sudachi.s3-ap-northeast-1.amazonaws.com/"
S3_PREFIX = "sudachidict-raw/"
LEX_FILES = ["small_lex.zip", "core_lex.zip", "notcore_lex.zip"]
# 辞書ソースCSVの列位置(0始まり)。0=見出し(TRIE), 4=表記, 5-10=品詞1-6, 11=読み
COL_SURFACE, COL_POS1, COL_YOMI = 4, 5, 11
POS_SURNAME = ("名詞", "固有名詞", "人名", "姓")

# 収録する表記の条件。漢字を1文字以上含み、日本語の文字だけでできていること。
# ローマ字表記(Yamada/ENDO)とかな書きだけの見出しは、同じ名字の別表記でしか
# なく漢字表記の行と重複するので落とす(詳細は ADR 00038)
KANJI = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0002FFFF]")
JP_ONLY = re.compile(r"^[㐀-䶿一-鿿豈-﫿\U00020000-\U0002FFFF々〆ヶノぁ-ゖァ-ヶー]+$")
KATAKANA_ONLY = re.compile(r"^[ァ-ヶー]+$")
MAX_LEN = 8  # 表記の上限文字数(実測の最大は5)

# 妥当性ガード。取得が壊れた回に myoji.csv を空にしないための下限
MIN_SURNAME_ROWS = 50000
MIN_RANK_LABELS = 3000
MIN_NDL_PAIRS = 50000
MIN_JMNEDICT_PAIRS = 100000
MIN_WIKIDATA_PERSON_PAIRS = 4000

# 読みの裏付け。並び順を固定し、月次更新で不要な差分を出さない。
EVIDENCE_ORDER = ("person_lists", "ndl", "wikidata_person", "official_web",
                  "jmnedict")
HUMAN_EVIDENCE = frozenset(
    ("person_lists", "ndl", "wikidata_person", "official_web"))
OFFICIAL_SOURCE_TYPES = frozenset(
    ("official_person_profile", "official_org_directory", "official_roster",
     "official_authority"))

# Web NDL Authorities は個人名典拠を一括配布していないため SPARQL で取得する。
# 公式の姓抽出例と同じく、コンマ前を姓・姓読みとして扱う。
NDL_SPARQL = "https://id.ndl.go.jp/auth/ndla/sparql"
NDL_PAGE_SIZE = 1000
NDL_QUERY = """
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>
PREFIX ndl: <http://ndl.go.jp/dcndl/terms/>
SELECT DISTINCT ?surname ?yomi WHERE {
  ?auth skos:inScheme <http://id.ndl.go.jp/auth#personalNames> ;
        xl:prefLabel ?labelnode .
  ?labelnode xl:literalForm ?label ; ndl:transcription ?transcription .
  FILTER(lang(?transcription) = "ja-Kana")
  FILTER(regex(str(?label), "^[^,]+, [^0-9]") &&
         regex(str(?transcription), "^[^,]+, [^0-9０-９]"))
  BIND(strbefore(str(?label), ",") AS ?surname)
  BIND(strbefore(str(?transcription), ",") AS ?yomi)
}
"""

JMNEDICT_URL = "https://www.edrdg.org/pub/Nihongo/JMnedict.xml.gz"
JMNEDICT_SURNAME = "family or surname"

# ja.wikipedia の記事が「姓の説明」かどうかの判定語。同じ表記の記事が地名・
# 曖昧さ回避のことが多いので、冒頭文の中身で採否を決める(ADR 00038)
SURNAME_WORDS = ("姓", "名字", "苗字", "氏族")
# 曖昧さ回避の箇条書き(「上杉氏（うえすぎし） - 室町時代の…」「山東壽‐1874年…」)
# を弾く目印。U+2010 は人物一覧の生没年区切りにしか出ないので単独で弾く
BULLET = (" - ", " – ", " — ", "‐")
MIN_DESC_LEN = 12  # 「佐藤。」のような中身の無い説明を落とす
PAREN = re.compile(r"[（(][^）)]*[）)]")
# 説明文の主語がこれで終わるものは姓の説明ではない(「吹田城は、大阪府…」)
NON_SURNAME_HEAD = ("城", "駅", "市", "町", "村", "川", "山", "湖", "藩",
                    "大学", "神社", "寺", "空港", "公園", "大字")
NON_SURNAME_WORDS = ("株式会社", "有限会社", "郵便番号", "麻雀", "の格式")
# **説明文のどこか**にこれが無ければ姓・氏族の説明ではないとみなす(ADR 00038)。
# 由緒から書き出して氏族の語が2文目以降に来る記事(金子・小山)を取りこぼさない
# よう、最初の一文ではなく全体で見る。姓・氏族を指す語のゆるい形も含める
CLAN_WORDS = ("姓", "名字", "苗字", "氏族", "一族", "氏は", "家は", "武家",
              "華族", "氏の", "氏を", "氏流", "豪族", "名族", "国人")
# 「江口 光清は、安土桃山時代の…武将。最上氏の家臣。」のような人物記事を弾く。
# ja.wikipedia の人物記事名は「姓 名」で主語に空白が入るが、姓・氏族の記事の
# 主語(「佐藤氏」「日本の氏族」)には入らない
PERSON_HEAD = re.compile(r"\S+\s\S")
# 「〜を参照のこと。」「〜は次のとおりである。」のような誘導文は情報が無いので
# description に採らない
POINTER = re.compile(r"参照|詳細は|下記|次のとおり|次の通り|次のような"
                     r"|以下のとおり|以下の通り|以下のような|次に記す")
# 「名越流北条氏は、鎌倉時代の北条氏の分流。」のように、その姓ではなく**別の氏の
# 支流**を説明している記事の見出し。姓の説明として採らない
BRANCH_HEAD = re.compile(r".+流.+[氏家]$")
# 「どこに多いか・由来」のトリビア。この語を含む文を優先して拾う
TRIVIA_WORDS = ("由来", "発祥", "起源", "に多い", "分布", "多く見られる",
                "多い姓", "多い名字", "多い苗字")
DESC_MAX = 130  # トリビアの1文を足すときの上限(通常は make_description の90字)


def http_get(url: str, timeout: int = 300) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def latest_sudachi_version() -> str:
    """S3 のバケット一覧から最新の辞書バージョン(YYYYMMDD)を選ぶ。"""
    url = S3_BUCKET + "?" + urllib.parse.urlencode(
        {"list-type": "2", "prefix": S3_PREFIX, "delimiter": "/"})
    xml = http_get(url, timeout=60).decode("utf-8")
    vers = sorted(set(re.findall(
        re.escape(S3_PREFIX) + r"(\d{8})/", xml)))
    if not vers:
        raise RuntimeError("SudachiDict のバージョン一覧が取れない")
    return vers[-1]


def lex_bytes(version: str, name: str) -> bytes:
    url = f"{S3_BUCKET}{S3_PREFIX}{version}/{name}"
    if not CACHE_DIR:
        print(f"  取得中: {url}", flush=True)
        return http_get(url)
    cache = Path(CACHE_DIR) / f"{version}-{name}"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        print(f"  キャッシュ: {cache}", flush=True)
        return cache.read_bytes()
    print(f"  取得中: {url}", flush=True)
    data = http_get(url)
    cache.write_bytes(data)
    return data


def fetch_surnames() -> dict:
    """SudachiDict から 表記 -> ソート済みの読みリスト を作る。"""
    version = latest_sudachi_version()
    print(f"SudachiDict 辞書ソース(Apache-2.0) version={version}", flush=True)
    pairs = set()
    raw = 0
    for name in LEX_FILES:
        blob = lex_bytes(version, name)
        n = 0
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            member = next(m for m in zf.namelist() if m.endswith(".csv"))
            with zf.open(member) as fh:
                # SudachiDict の辞書ソースはクオート付きフィールドを含むので
                # split(",") ではなく csv モジュールで読む
                for row in csv.reader(io.TextIOWrapper(fh, encoding="utf-8")):
                    if len(row) <= COL_YOMI:
                        continue
                    if tuple(row[COL_POS1:COL_POS1 + 4]) != POS_SURNAME:
                        continue
                    raw += 1
                    surface = row[COL_SURFACE].strip()
                    yomi = row[COL_YOMI].strip()
                    if not clean_surname(surface, yomi):
                        continue
                    pairs.add((surface, yomi))
                    n += 1
        print(f"  {name}: 採用 {n}件", flush=True)
    print(f"姓エントリ {raw}件 -> 採用 {len(pairs)}組"
          f"(表記 {len({s for s, _ in pairs})}種)", flush=True)
    if len(pairs) < MIN_SURNAME_ROWS:
        raise RuntimeError(f"姓エントリが少なすぎる: {len(pairs)}")
    out = {}
    for surface, yomi in pairs:
        out.setdefault(surface, set()).add(yomi)
    return {s: sorted(y) for s, y in out.items()}


def clean_surname(surface: str, yomi: str) -> bool:
    """明らかなゴミを落とす。判断に迷うものは残す(広く収録してから絞る方針)。"""
    if not surface or not yomi:
        return False
    if len(surface) > MAX_LEN or len(yomi) > 16:
        return False
    if not JP_ONLY.match(surface) or not KANJI.search(surface):
        return False
    return bool(KATAKANA_ONLY.match(yomi))


# ---- Wikidata: 著名人ベースの参考順位 + 姓アイテムのQID ------------------
RANK_QUERY = """
SELECT ?fn ?fnLabel (COUNT(DISTINCT ?p) AS ?cnt) WHERE {
  ?p wdt:P31 wd:Q5 ; wdt:P27 wd:Q17 ; wdt:P734 ?fn .
  ?fn rdfs:label ?fnLabel . FILTER(LANG(?fnLabel) = "ja")
}
GROUP BY ?fn ?fnLabel
"""

WIKIDATA_PERSON_READING_QUERY = """
SELECT DISTINCT ?fnLabel ?kana WHERE {
  ?person wdt:P31 wd:Q5 ; wdt:P27 wd:Q17 ; wdt:P734 ?fn .
  ?fn wdt:P1814 ?kana ; rdfs:label ?fnLabel .
  FILTER(LANG(?fnLabel) = "ja")
}
"""


def fetch_rank() -> tuple:
    """(表記 -> rank, 表記 -> QID) を返す。rank は1始まり・同数は同順位。

    **QIDではなく日本語ラベルで名寄せして合算する**。Wikidata には同じ姓の項目が
    複数あり(「佐藤」だけで6項目)、QID単位で数えると人数がばらけるため。
    `wikidata` 列に入れるQIDは、そのラベルの項目のうち**実際に人物の姓として
    最も多く使われている項目**(同数ならQID番号の小さい方)を決定的に選ぶ。
    """
    data = sparql(RANK_QUERY)
    counts, best = {}, {}
    for b in data["results"]["bindings"]:
        label = b["fnLabel"]["value"].strip()
        qid = b["fn"]["value"].rsplit("/", 1)[1]
        c = int(b["cnt"]["value"])
        counts[label] = counts.get(label, 0) + c
        cur = best.get(label)
        if (cur is None or c > cur[1]
                or (c == cur[1] and int(qid[1:]) < int(cur[0][1:]))):
            best[label] = (qid, c)
    print(f"Wikidata: 姓ラベル {len(counts)}種 / 延べ {sum(counts.values())}人",
          flush=True)
    if len(counts) < MIN_RANK_LABELS:
        raise RuntimeError(f"Wikidata の集計が少なすぎる: {len(counts)}")
    # 同数は同順位(1,2,2,4...)。同数内の並びは表記順で決定的にする
    ranks, prev_cnt, prev_rank = {}, None, 0
    for i, (label, c) in enumerate(
            sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])), start=1):
        if c != prev_cnt:
            prev_cnt, prev_rank = c, i
        ranks[label] = prev_rank
    return ranks, {label: q for label, (q, _) in best.items()}


def fetch_wikidata_person_pairs() -> set:
    """日本人のP734として使われる姓item自身のP1814から読みを得る。

    人物のフルネームP1814を姓名分割するのではなく、姓itemに直接記録された読みだけを
    採る。姓名順や空白の揺れによる誤分割を避けるため。
    """
    cache = (Path(CACHE_DIR) / "wikidata-person-surname-pairs.json"
             if CACHE_DIR else None)
    if cache and cache.exists():
        print(f"  キャッシュ: {cache}", flush=True)
        pairs = {tuple(p) for p in json.loads(cache.read_text(encoding="utf-8"))}
    else:
        pairs = parse_wikidata_person_json(
            sparql(WIKIDATA_PERSON_READING_QUERY))
    if len(pairs) < MIN_WIKIDATA_PERSON_PAIRS:
        raise RuntimeError(f"Wikidata の人物姓読みが少なすぎる: {len(pairs)}")
    if cache and not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(sorted(pairs), ensure_ascii=False),
                         encoding="utf-8")
    print(f"Wikidata の人物に使われる(姓, 読み) {len(pairs)}組", flush=True)
    return pairs


def parse_wikidata_person_json(data: dict) -> set:
    """WDQS応答を検査し、正規化済みの姓・読みだけを返す。"""
    pairs = set()
    for binding in data.get("results", {}).get("bindings", []):
        surface = str(binding.get("fnLabel", {}).get("value", "")).strip()
        yomi = (str(binding.get("kana", {}).get("value", ""))
                .replace(" ", "").strip().translate(HIRA2KATA))
        if clean_surname(surface, yomi):
            pairs.add((surface, yomi))
    return pairs


# ---- ja.wikipedia: 姓記事の冒頭 -----------------------------------------
def title_candidates(surface: str) -> list:
    """姓の説明が載っていそうな記事名を、姓そのものの説明に近い順に並べる。

    「佐藤」「田中」の素の記事は人物の曖昧さ回避ページで由来が書かれていない。
    曖昧さ回避サフィックス付き(「東 (姓)」)がいちばん姓そのものの記事で、次が
    氏族記事「佐藤氏」、家の記事「近衛家」、最後が素の記事。
    """
    return [f"{surface} (姓)", f"{surface} (名字)", f"{surface}氏",
            f"{surface}家", surface]


def existing_titles(titles: list) -> set:
    """実在する記事名だけに絞る(1リクエスト50件)。

    候補は表記あたり5件あるので、冒頭文(1リクエスト20件)を全候補に投げると
    問い合わせが5倍になる。存在確認は軽いので先に落としてから冒頭文を取る。
    """
    cache = Path(CACHE_DIR) / "exists.json" if CACHE_DIR else None
    if cache and cache.exists():
        return set(json.loads(cache.read_text(encoding="utf-8")))
    ok = set()
    for i in range(0, len(titles), 50):
        data = api({"action": "query", "titles": "|".join(titles[i:i + 50])})
        q = data.get("query", {})
        back = {n["to"]: n["from"] for n in q.get("normalized", [])}
        for p in q.get("pages", {}).values():
            if "missing" in p or "invalid" in p:
                continue
            t = p["title"]
            ok.add(back.get(t, t))
        time.sleep(0.3)
        if i and i % 10000 == 0:
            print(f"  存在確認 {i}/{len(titles)}", flush=True)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(sorted(ok), ensure_ascii=False),
                         encoding="utf-8")
    return ok


def fetch_intros(titles: list) -> dict:
    """記事タイトル -> (実際に開いた記事名, 冒頭文)。

    `wpnames.fetch_extracts` と違ってリダイレクト先の記事名も返す。「塙氏」が
    人物記事「祥光院」へ、「下村氏」が「由利十二頭」へ飛ぶといった、姓と無関係な
    記事に着地したケースを呼び出し側で落とせるようにするため。
    """
    cache = Path(CACHE_DIR) / "intros.json" if CACHE_DIR else None
    if cache and cache.exists():
        print(f"  キャッシュ: {cache}", flush=True)
        return {k: tuple(v) for k, v in
                json.loads(cache.read_text(encoding="utf-8")).items()}
    out = {}
    for i in range(0, len(titles), 20):
        data = api({"action": "query", "prop": "extracts", "exintro": 1,
                    "explaintext": 1, "exlimit": "max", "redirects": 1,
                    "titles": "|".join(titles[i:i + 20])})
        q = data.get("query", {})
        back = {r["to"]: r["from"] for r in q.get("redirects", [])}
        back.update({n["to"]: n["from"] for n in q.get("normalized", [])})
        for p in q.get("pages", {}).values():
            target = p["title"]
            out[back.get(target, target)] = (target, p.get("extract", "")[:300])
        time.sleep(0.5)
        if i and i % 4000 == 0:
            print(f"  記事冒頭 {i}/{len(titles)}", flush=True)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out, ensure_ascii=False),
                         encoding="utf-8")
    return out


def pick_paragraph(intro: str) -> str:
    """記事冒頭から「姓の説明になっている段落」を選ぶ。

    ja.wikipedia の姓記事は「佐藤（さとう）」だけの曖昧さ回避ページが多く、
    そのまま連結すると人物の箇条書きが説明文になってしまう。カッコ(読み)を
    除いた実質の長さが十分ある段落だけを残し、姓の語を含む段落があればそこから
    後ろを使う。
    """
    paras = [p.strip() for p in intro.split("\n")]
    subst = [p for p in paras if len(PAREN.sub("", p).strip()) >= MIN_DESC_LEN]
    if not subst:
        return ""
    # 「姓の語 + 由来・分布の語」を含む段落 > 姓の語だけの段落 > 先頭、の順
    for want_trivia in (True, False):
        for i, p in enumerate(subst):
            if not any(w in p for w in SURNAME_WORDS):
                continue
            if want_trivia and not any(t in p for t in TRIVIA_WORDS):
                continue
            return "\n".join(subst[i:])
    return "\n".join(subst)


def drop_pointers(text: str) -> str:
    """「〜を参照のこと。」のような誘導文を落とす。全部落ちたら空を返す。"""
    keep = [s for s in text.split("。") if s.strip() and not POINTER.search(s)]
    return "。".join(keep) + "。" if keep else ""


def add_trivia(desc: str, text: str) -> str:
    """説明に由来・分布の話が無ければ、後ろの文から1つだけ足す。"""
    if any(w in desc for w in TRIVIA_WORDS):
        return desc
    for s in clean_ws(text).split("。"):
        if not s.strip() or not any(w in s for w in TRIVIA_WORDS):
            continue
        cand = _sanitize_desc(s).strip()
        if cand and cand not in desc and len(desc) + len(cand) + 1 <= DESC_MAX:
            return desc + cand + "。"
        break
    return desc


def build_description(intro: str, title: str) -> str:
    text = drop_pointers(pick_paragraph(intro))
    if not text:
        return "NA"
    desc = make_description(text, "", title)
    return desc if desc == "NA" else add_trivia(desc, text)


def accept_description(desc: str, surface: str) -> bool:
    """曖昧さ回避の箇条書き・姓の説明でないものを落とす。"""
    if desc == "NA" or len(desc) < MIN_DESC_LEN:
        return False
    if any(b in desc for b in BULLET):
        return False
    if any(w in desc for w in NON_SURNAME_WORDS):
        return False
    # 主語が「吹田城」「◯◯駅」なら地物の記事に着地している
    head = desc.split("は、")[0] if "は、" in desc[:30] else desc.split("。")[0]
    if head.endswith(NON_SURNAME_HEAD):
        return False
    # 主語が「名越流北条氏」= 別の氏の支流の説明なら、その姓の説明ではない
    if BRANCH_HEAD.match(head) and not head.endswith(
            (surface + "氏", surface + "家")):
        return False
    # 主語が「江口 光清」なら人物記事。「最上氏の家臣」等で下の条件を通ってしまう
    if PERSON_HEAD.match(head):
        return False
    # 説明文のどこかが姓・氏族の話になっていること。記事名が「東 (姓)」でも中身が
    # 麻雀の説明だったり(東)、「新家」という公家の格式の記事だったり(新)するので、
    # 記事名ではなく本文で判定する
    return any(w in desc for w in CLAN_WORDS)


def fetch_articles(surfaces: list) -> dict:
    """表記 -> description。姓そのものの記事に近い順に候補を試す。"""
    cands = {s: title_candidates(s) for s in surfaces}
    all_titles = sorted({t for v in cands.values() for t in v})
    print(f"姓記事の候補 {len(all_titles)}件の存在確認中...", flush=True)
    exist = existing_titles(all_titles)
    want = sorted(t for t in all_titles if t in exist)
    print(f"  実在する記事 {len(want)}件の冒頭を取得中...", flush=True)
    intros = fetch_intros(want)
    desc_of, stats = {}, {}
    for s in surfaces:
        for title in cands[s]:
            target, intro = intros.get(title, ("", ""))
            if not intro:
                continue
            # 「塙氏」→「祥光院」のように姓と無関係な記事へのリダイレクトは捨てる
            if target != title and not target.startswith(s):
                continue
            desc = build_description(intro, title)
            if accept_description(desc, s):
                desc_of[s] = desc
                kind = "素の記事" if title == s else title[len(s):] or "-"
                stats[kind] = stats.get(kind, 0) + 1
                break
    detail = " / ".join(f"{k}:{v}" for k, v in sorted(stats.items(),
                                                     key=lambda kv: -kv[1]))
    print(f"description採用 {len(desc_of)}件 ({detail})", flush=True)
    return desc_of


# ---- verified(実在人名リストで読みの裏が取れたか)------------------------
def fetch_verified_pairs() -> set:
    """このリポジトリの実在人名リストから (姓の表記, カタカナ読み) を集める。

    SudachiDict の姓エントリには実在の読みに混じって破格の読み(`伊藤 イロウ`
    `井上 イトウ` `星野 コシノ`)が入っている。空耳では pronunciation が変換の
    キーなので、**行を消さずに** 裏が取れたかどうかを `verified` 列で示す
    (ADR 00038)。判定に使うのは実在人物の名簿だけで、架空リストは使わない。
    """
    root = CSV_PATH.parent
    pairs = set()
    for name in PERSON_LISTS:
        path = root / name
        if not path.exists():
            print(f"  {name}: 見つからないのでスキップ", flush=True)
            continue
        n = 0
        for r in csv.DictReader(path.open(encoding="utf-8")):
            if r.get("type") != "family":
                continue
            surface = (r.get("surface") or "").strip()
            # 人名リストの読みはカタカナが基本だがひらがなの行もあるので揃える
            yomi = (r.get("pronunciation") or "").strip().translate(HIRA2KATA)
            if surface and yomi and KATAKANA_ONLY.match(yomi):
                pairs.add((surface, yomi))
                n += 1
        print(f"  {name}: type=family {n}行", flush=True)
    print(f"実在人名リストの(姓, 読み) {len(pairs)}組", flush=True)
    return pairs


def parse_ndl_csv(data: bytes) -> set:
    """NDL SPARQL のCSV応答を (姓, カタカナ読み) にする。"""
    rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    if rows.fieldnames is None or not {"surname", "yomi"} <= set(rows.fieldnames):
        raise RuntimeError("Web NDL Authorities の応答形式が不正")
    pairs = set()
    for row in rows:
        surface = (row.get("surname") or "").strip()
        yomi = ((row.get("yomi") or "").replace(" ", "").strip()
                .translate(HIRA2KATA))
        if clean_surname(surface, yomi):
            pairs.add((surface, yomi))
    return pairs


def fetch_ndl_pairs() -> set:
    """Web NDL Authorities の個人名典拠から姓と読みを集める。"""
    cache = Path(CACHE_DIR) / "ndl-person-surname-pairs.json" if CACHE_DIR else None
    if cache and cache.exists():
        print(f"  キャッシュ: {cache}", flush=True)
        pairs = {tuple(p) for p in json.loads(cache.read_text(encoding="utf-8"))}
        if len(pairs) < MIN_NDL_PAIRS:
            raise RuntimeError(
                f"NDLキャッシュの姓読みが少なすぎる: {len(pairs)}")
        return pairs

    pairs = set()
    offset = 0
    while True:
        query = NDL_QUERY + f"LIMIT {NDL_PAGE_SIZE} OFFSET {offset}"
        url = NDL_SPARQL + "?" + urllib.parse.urlencode(
            {"query": query, "format": "csv"})
        last_error = None
        for attempt in range(5):
            try:
                raw_page = http_get(url, timeout=180)
                record_count = len(list(csv.DictReader(io.StringIO(
                    raw_page.decode("utf-8-sig")))))
                page = parse_ndl_csv(raw_page)
                last_error = None
                break
            except (OSError, UnicodeError, csv.Error, RuntimeError) as exc:
                last_error = exc
                time.sleep(2 ** attempt)
        if last_error is not None:
            raise RuntimeError(
                f"Web NDL Authorities の取得に失敗(offset={offset})") from last_error
        pairs.update(page)
        if offset and offset % 10000 == 0:
            print(f"  NDL {offset + len(page)}件取得", flush=True)
        if record_count < NDL_PAGE_SIZE:
            break
        offset += NDL_PAGE_SIZE
        time.sleep(0.3)
    if len(pairs) < MIN_NDL_PAIRS:
        raise RuntimeError(f"Web NDL Authorities の姓読みが少なすぎる: {len(pairs)}")
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(sorted(pairs), ensure_ascii=False), encoding="utf-8")
    print(f"Web NDL Authorities の(姓, 読み) {len(pairs)}組", flush=True)
    return pairs


def parse_jmnedict(blob: bytes) -> set:
    """JMnedict gzip XMLから surname と明記された表記・読みだけを取る。"""
    pairs = set()
    with gzip.GzipFile(fileobj=io.BytesIO(blob)) as fh:
        for _, entry in ET.iterparse(fh, events=("end",)):
            if entry.tag != "entry":
                continue
            is_surname = any(
                (node.text or "") == JMNEDICT_SURNAME
                for node in entry.findall("./trans/name_type"))
            if is_surname:
                surfaces = [n.text for n in entry.findall("./k_ele/keb") if n.text]
                for reading in entry.findall("./r_ele"):
                    yomi = (reading.findtext("reb") or "").translate(HIRA2KATA)
                    restricted = [n.text for n in reading.findall("re_restr") if n.text]
                    for surface in restricted or surfaces:
                        if clean_surname(surface, yomi):
                            pairs.add((surface, yomi))
            entry.clear()
    return pairs


def fetch_jmnedict_pairs() -> set:
    """JMnedictの姓コードから辞書上の裏付けを集める。"""
    cache = Path(CACHE_DIR) / "JMnedict.xml.gz" if CACHE_DIR else None
    if cache and cache.exists():
        print(f"  キャッシュ: {cache}", flush=True)
        blob = cache.read_bytes()
    else:
        print(f"  取得中: {JMNEDICT_URL}", flush=True)
        blob = http_get(JMNEDICT_URL)
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(blob)
    pairs = parse_jmnedict(blob)
    if len(pairs) < MIN_JMNEDICT_PAIRS:
        raise RuntimeError(f"JMnedict の姓読みが少なすぎる: {len(pairs)}")
    print(f"JMnedict の(姓, 読み) {len(pairs)}組", flush=True)
    return pairs


def load_official_evidence(path: Path = OFFICIAL_EVIDENCE_PATH) -> set:
    """レビュー済み公式ページ台帳から (姓, 読み) を得る。

    元ページの名簿や文章は再配布せず、確認結果と監査用メタデータだけをJSONLで持つ。
    """
    if not path.exists():
        return set()
    pairs = set()
    required = {"surface", "pronunciation", "status", "source_url",
                "source_type", "source_title", "retrieved_on",
                "observed_surface", "observed_reading", "locator"}
    seen = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{path.name}:{lineno}: JSONが不正") from exc
        missing = required - set(record)
        if missing:
            raise RuntimeError(
                f"{path.name}:{lineno}: 必須キー不足: {sorted(missing)}")
        surface = str(record["surface"]).strip()
        yomi = str(record["pronunciation"]).strip().translate(HIRA2KATA)
        if not clean_surname(surface, yomi):
            raise RuntimeError(f"{path.name}:{lineno}: 姓・読みが不正")
        pair = (surface, yomi)
        if pair in seen:
            raise RuntimeError(f"{path.name}:{lineno}: 姓・読みが重複")
        seen.add(pair)
        if record["status"] not in ("verified", "rejected", "review"):
            raise RuntimeError(f"{path.name}:{lineno}: statusが不正")
        if record["source_type"] not in OFFICIAL_SOURCE_TYPES:
            raise RuntimeError(f"{path.name}:{lineno}: source_typeが不正")
        if not str(record["source_title"]).strip() or not str(record["locator"]).strip():
            raise RuntimeError(f"{path.name}:{lineno}: 表題・確認箇所が空")
        if not re.fullmatch(r"https://[^\s]+", str(record["source_url"])):
            raise RuntimeError(f"{path.name}:{lineno}: HTTPS URLでない")
        try:
            retrieved = date.fromisoformat(str(record["retrieved_on"]))
        except ValueError as exc:
            raise RuntimeError(f"{path.name}:{lineno}: 確認日が不正") from exc
        if retrieved > datetime.now(ZoneInfo("Asia/Tokyo")).date():
            raise RuntimeError(f"{path.name}:{lineno}: 確認日が不正")
        observed_surface = str(record["observed_surface"]).strip()
        observed_yomi = str(record["observed_reading"]).strip().translate(HIRA2KATA)
        if (observed_surface, observed_yomi) != pair:
            raise RuntimeError(f"{path.name}:{lineno}: 掲載表記・読みと候補が不一致")
        if record["status"] == "verified":
            pairs.add(pair)
    print(f"公式人物ページ台帳の(姓, 読み) {len(pairs)}組", flush=True)
    return pairs


def evidence_for(pair: tuple, person_pairs: set, ndl_pairs: set,
                 wikidata_person_pairs: set, official_pairs: set,
                 jmnedict_pairs: set) -> set:
    sources = set()
    if pair in person_pairs:
        sources.add("person_lists")
    if pair in ndl_pairs:
        sources.add("ndl")
    if pair in wikidata_person_pairs:
        sources.add("wikidata_person")
    if pair in official_pairs:
        sources.add("official_web")
    if pair in jmnedict_pairs:
        sources.add("jmnedict")
    return sources


def parse_evidence(value: str) -> set:
    return {s for s in (value or "").split("|") if s in EVIDENCE_ORDER}


def format_evidence(sources: set) -> str:
    return "|".join(s for s in EVIDENCE_ORDER if s in sources)


def is_human_verified(sources: set) -> bool:
    return bool(HUMAN_EVIDENCE & sources)


# ---- CSV の組み立て -----------------------------------------------------
def sort_key(ranks: dict):
    """参考順位の上位から、順位が無い表記は表記順で後ろに並べる。"""
    return lambda s: (ranks.get(s, 10**9), s)


def make_row(rid: str, surface: str, yomi: str, ranks: dict, qids: dict,
             descs: dict, evidence: dict) -> dict:
    sources = evidence.get((surface, yomi), set())
    return {
        "id": rid, "original": surface, "surface": surface,
        "pronunciation": yomi,
        "verified": "yes" if is_human_verified(sources) else "no",
        "rank": str(ranks[surface]) if surface in ranks else "",
        "description": descs.get(surface, ""),
        "wikidata": qids.get(surface, ""),
        "evidence_sources": format_evidence(sources),
    }


def yomi_order(surface: str, yomis: list, evidence: dict) -> list:
    """同じ id の中では裏が取れた読みを先に置く(鈴木ならスズキ > ススキ)。"""
    return sorted(yomis, key=lambda y: (
        0 if is_human_verified(evidence.get((surface, y), set())) else 1, y))


def build_rows(surnames: dict, ranks: dict, qids: dict, descs: dict,
               evidence: dict) -> list:
    """初回生成。"""
    rows = []
    for i, surface in enumerate(sorted(surnames, key=sort_key(ranks)), start=1):
        for yomi in yomi_order(surface, surnames[surface], evidence):
            rows.append(make_row(str(i), surface, yomi, ranks, qids, descs,
                                 evidence))
    return rows


def is_blank(v) -> bool:
    return v is None or v.strip() in ("", "NA")


def merge_rows(old_rows: list, surnames: dict, ranks: dict, qids: dict,
               descs: dict, evidence: dict) -> list:
    """2回目以降。既存行を保ちつつ rank を全件更新し、新しい組を追記する。"""
    id_of = {}
    for r in old_rows:
        id_of.setdefault(r["original"], r["id"])
    seen = {(r["original"], r["pronunciation"]) for r in old_rows}

    changed_rank = filled = verified_up = evidence_up = 0
    for r in old_rows:
        # rank は毎回全行を上書きする(集計のスナップショットなので部分更新できない)
        fresh = str(ranks[r["original"]]) if r["original"] in ranks else ""
        if r.get("rank", "") != fresh:
            r["rank"] = fresh
            changed_rank += 1
        # verified は no -> yes の一方向だけ更新する。人名リストの行が減った回に
        # yes を no へ落とすと、いったん取れた裏付けが消えてしまうため
        pair = (r["original"], r["pronunciation"])
        old_sources = parse_evidence(r.get("evidence_sources", ""))
        # evidence_sources 導入前の yes は実在人名リスト由来なので出典を復元する。
        if r.get("verified") == "yes" and not old_sources:
            old_sources.add("person_lists")
        new_sources = old_sources | evidence.get(pair, set())
        if new_sources != old_sources:
            evidence_up += 1
        r["evidence_sources"] = format_evidence(new_sources)
        if r.get("verified") != "yes":
            r["verified"] = "yes" if is_human_verified(new_sources) else "no"
            verified_up += r["verified"] == "yes"
        for col, val in (("description", descs.get(r["original"], "")),
                         ("wikidata", qids.get(r["original"], ""))):
            if is_blank(r.get(col)) and val:
                r[col] = val
                filled += 1
    print(f"既存 {len(old_rows)}行: rank更新 {changed_rank}行 / "
          f"verified no->yes {verified_up}行 / evidence追加 {evidence_up}行 / "
          f"空欄補完 {filled}セル", flush=True)

    next_id = max(int(r["id"]) for r in old_rows) + 1 if old_rows else 1
    new_surfaces = sorted(set(surnames) - set(id_of), key=sort_key(ranks))
    for surface in new_surfaces:
        id_of[surface] = str(next_id)
        next_id += 1
    added = []
    for surface in sorted(surnames, key=sort_key(ranks)):
        for yomi in yomi_order(surface, surnames[surface], evidence):
            if (surface, yomi) not in seen:
                added.append(make_row(id_of[surface], surface, yomi, ranks,
                                      qids, descs, evidence))
    print(f"新規追記 {len(added)}行(うち新しい表記 {len(new_surfaces)}種)",
          flush=True)
    return old_rows + added


def main() -> int:
    surnames = fetch_surnames()
    print("実在人名リストから読みの裏付けを収集中...", flush=True)
    person_pairs = fetch_verified_pairs()
    print("Web NDL Authoritiesから人物典拠を収集中...", flush=True)
    ndl_pairs = fetch_ndl_pairs()
    print("Wikidataから人物に使われる姓読みを収集中...", flush=True)
    wikidata_person_pairs = fetch_wikidata_person_pairs()
    print("公式人物ページの確認台帳を読込中...", flush=True)
    official_pairs = load_official_evidence()
    print("JMnedictから辞書上の裏付けを収集中...", flush=True)
    jmnedict_pairs = fetch_jmnedict_pairs()
    evidence = {}
    for surface, yomis in surnames.items():
        for yomi in yomis:
            pair = (surface, yomi)
            sources = evidence_for(pair, person_pairs, ndl_pairs,
                                   wikidata_person_pairs, official_pairs,
                                   jmnedict_pairs)
            if sources:
                evidence[pair] = sources
    ranks, qids = fetch_rank()
    # 記事を引くのは参考順位が付いた表記だけにする。順位の無い表記は
    # ja.wikipedia に姓記事がほぼ無く、9万件分の問い合わせに見合わない
    targets = sorted((s for s in surnames if s in ranks), key=sort_key(ranks))
    descs = fetch_articles(targets)
    qids = {s: q for s, q in qids.items() if s in surnames}

    if CSV_PATH.exists():
        old_rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
        for r in old_rows:
            for c in COLS:
                r.setdefault(c, "")
        rows = merge_rows(old_rows, surnames, ranks, qids, descs, evidence)
    else:
        rows = build_rows(surnames, ranks, qids, descs, evidence)

    write_csv_no_trailing_newline(CSV_PATH, COLS, rows)

    n_rank = sum(1 for r in rows if r["rank"])
    n_desc = sum(1 for r in rows if r["description"])
    n_wd = sum(1 for r in rows if r["wikidata"])
    n_ver = sum(1 for r in rows if r["verified"] == "yes")
    n = len(rows)
    print(f"\nmyoji.csv: {n}行 / 表記 {len({r['original'] for r in rows})}種 / "
          f"複数読みの表記 {sum(1 for v in surnames.values() if len(v) > 1)}種",
          flush=True)
    print(f"  verified=yes {n_ver}行 ({n_ver / n:.1%}) / "
          f"rank付与 {n_rank}行 ({n_rank / n:.1%}) / "
          f"description付与 {n_desc}行 ({n_desc / n:.1%}) / "
          f"wikidata付与 {n_wd}行 ({n_wd / n:.1%})", flush=True)
    print("  注意: rank は著名人ベースの参考順位であって世帯数・人口順位ではない",
          flush=True)
    print("  注意: verified=no は誤りとは限らず、実在人名で裏が取れなかっただけ",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
