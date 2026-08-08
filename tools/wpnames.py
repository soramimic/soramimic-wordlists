"""人名リスト自動更新の共通処理(Wikipedia/Wikidata)。

- 記事冒頭文「姓 名(せい めい、…」から姓名分割済みの読みを取る
- 「本名:姓 名〈せい めい〉」パターン(登録名が記事名の場合)に対応
- 台湾選手等の「姓 名(カタカナ・カタカナ、」にも対応
- 異体字(髙/高等)は照合時のみ正規化する
- 記事冒頭文/Wikidataのja descriptionから短い完結文(description列)を作る
  (make_description。scientist と youtuber で共用)
"""

import json
import re
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "soramimic-wordlists-updater/1.0 (https://github.com/soramimic/soramimic-wordlists)"}
WP_API = "https://ja.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
WDQS = "https://query.wikidata.org/sparql"

DISAMBIG = re.compile(r"\s+\([^)]*\)$")
KATAKANA = re.compile(r"^[ァ-ヶー・=＝\s]+$")
KANJI = r"一-龠々〆豈-﫿ぁ-ゖァ-ヶーA-Za-z"
KANA = r"ぁ-ゖァ-ヶー"
HIRA2KATA = str.maketrans({chr(k): chr(k + 0x60) for k in range(ord("ぁ"), ord("ゖ") + 1)})
KATA2HIRA = str.maketrans({chr(k): chr(k - 0x60) for k in range(ord("ァ"), ord("ヶ") + 1)})
VARIANT = str.maketrans("髙﨑濵濱邉邊瀨栁眞", "高崎浜浜辺辺瀬柳真")
LINK = re.compile(r"\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]")


def vnorm(s: str) -> str:
    return s.translate(VARIANT)


def api(params: dict) -> dict:
    url = WP_API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as res:
                return json.load(res)
        except Exception as ex:
            print(f"retry {attempt}: {ex}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("wikipedia api failed")


def sparql(query: str, retries: int = 4) -> dict:
    """WDQSにGETで問い合わせる。

    retries は総試行回数。既定の4は「一時的な混雑なら待てば通る」前提だが、
    クエリ自体が重すぎて必ずタイムアウトする場合(例: 昆虫のコウチュウ目)は
    待っても通らないので、呼び出し側が小さい値にして早く諦め、対象を分割する
    (update_insect.py の fetch_taxa)。"""
    url = WDQS + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    last = ""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={**UA, "Accept": "application/sparql-results+json"})
            with urllib.request.urlopen(req, timeout=120) as res:
                return json.load(res)
        except Exception as ex:
            last = str(ex)
            print(f"WDQS retry {attempt}: {ex}")
            if attempt < retries - 1:
                time.sleep(70)
    # 最後のエラーを残す。呼び出し側がレート制限(429)とクエリが重すぎる
    # タイムアウト(504)を区別できるようにするため(update_insect.try_sparql)
    raise RuntimeError(f"wdqs failed: {last}")


def sparql_post(query: str) -> dict:
    """sparql() のPOST版。VALUES句に数百件を並べるとGETのURLが長すぎて
    HTTP 414 になるため、大きなクエリはこちらを使う。"""
    body = urllib.parse.urlencode({"query": query}).encode()
    headers = {**UA, "Accept": "application/sparql-results+json",
               "Content-Type": "application/x-www-form-urlencoded"}
    for attempt in range(4):
        try:
            req = urllib.request.Request(WDQS, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as res:
                return json.load(res)
        except Exception as ex:
            print(f"WDQS retry {attempt}: {ex}")
            time.sleep(20 * (attempt + 1))
    raise RuntimeError("wdqs failed")


def commons_urls(name_or_url: str) -> tuple:
    """Commonsのファイル名、またはP18のFilePath URL -> (image, image_page)。

    WDQSはP18を `.../Special:FilePath/<encoded>` のURLで返し、wbgetentities は
    生のファイル名で返すので両方を受ける(ファイル名に "/" は使えないので、
    "/" を含めばURLとみなして最終セグメントを一旦デコードする)。
    空白は _ に直し、カンマ等が生のまま残らないよう必ずURLエンコードする
    (利用側のCSVパーサはクオート非対応の素朴なsplit(",")のため)。"""
    fname = name_or_url
    if "/" in fname:
        fname = urllib.parse.unquote(fname.rsplit("/", 1)[-1])
    quoted = urllib.parse.quote(fname.replace(" ", "_"))
    return ("http://commons.wikimedia.org/wiki/Special:FilePath/" + quoted,
            "https://commons.wikimedia.org/wiki/File:" + quoted)


def template_wikitext(title: str):
    data = api({"action": "query", "prop": "revisions", "rvprop": "content",
                "rvslots": "main", "titles": title})
    page = next(iter(data["query"]["pages"].values()))
    if "revisions" not in page:
        return None
    return page["revisions"][0]["slots"]["main"]["*"]


def fetch_extracts(titles: list, limit: int = 200) -> dict:
    """記事タイトル -> 冒頭文(先頭limit文字)"""
    extracts = {}
    for i in range(0, len(titles), 20):
        data = api({"action": "query", "prop": "extracts", "exintro": 1,
                    "explaintext": 1, "exlimit": "max", "redirects": 1,
                    "titles": "|".join(titles[i:i + 20])})
        redir = {r["to"]: r["from"] for r in data["query"].get("redirects", [])}
        for p in data["query"]["pages"].values():
            orig = redir.get(p["title"], p["title"])
            extracts[orig] = p.get("extract", "")[:limit]
        time.sleep(0.5)
    return extracts


def parse_person(name: str, text: str):
    """記事名と冒頭文から (family_s, family_y, given_s, given_y, full_s, full_y,
    registered) を返す。読みはカタカナ。registered は記事名が登録名だった場合の
    登録名(通常None)。解析できなければ None。"""
    text = text.replace("　", " ")
    plain = name.replace(" ", "")
    if KATAKANA.match(plain):
        parts = [x for x in re.split(r"[・=＝\s]", name) if x]
        fam = parts[-1] if len(parts) >= 2 else None
        giv = parts[0] if len(parts) >= 2 else None
        full_y = name.replace("＝", "・").replace(" ", "・")
        return (fam, fam, giv, giv, name, full_y, None)
    # 記事名=登録名で本名が別記載(大勢、愛斗など)。コロンは全半角
    m = re.search(r"本名[:：]\s*([" + KANJI + r"]+)[  ]+([" + KANJI + r"]+)"
                  r"\s*[〈（(]\s*([" + KANA + r"]+)[  ]+([" + KANA + r"]+)", text)
    if m:
        f_s, g_s, f_y, g_y = m.groups()
        return (f_s, f_y.translate(HIRA2KATA), g_s, g_y.translate(HIRA2KATA),
                f_s + g_s, (f_y + g_y).translate(HIRA2KATA), name)
    # 通常: 姓 名(せい めい、または 姓 名(カタカナ・カタカナ(台湾人名等)
    m = re.match(r"^([" + KANJI + r"]+)[  ]+([" + KANJI + r"]+)\s*[（(]\s*"
                 r"([" + KANA + r"]+)[  ・]+([" + KANA + r"]+)", text)
    if m and vnorm(plain) == vnorm(m.group(1) + m.group(2)):
        f_s, g_s, f_y, g_y = m.groups()
        return (f_s, f_y.translate(HIRA2KATA), g_s, g_y.translate(HIRA2KATA),
                f_s + g_s, (f_y + g_y).translate(HIRA2KATA), None)
    # ウェード式などが先に来る場合: 括弧内のカタカナ・カタカナを読みとする
    m = re.match(r"^([" + KANJI + r"]+)[  ]+([" + KANJI + r"]+)\s*[（(]", text)
    if m and vnorm(plain) == vnorm(m.group(1) + m.group(2)):
        m2 = re.search(r"([ァ-ヶー]+)・([ァ-ヶー]+)", text[:150])
        if m2:
            return (m.group(1), m2.group(1), m.group(2), m2.group(2),
                    m.group(1) + m.group(2), m2.group(1) + m2.group(2), None)
    return None


# ---- description(記事冒頭文からの短い完結文)----------------------------
# scientist / youtuber で共用する(詳細は docs/adr/00009, 00029)。
DESC_TARGET = 90  # description の目安文字数(完結文をここまで連結)
DESC_HARD = 120   # 1文がこれを超える場合のみ「、」境界で切る
ACHIEVEMENT_WORDS = (
    "発見", "発明", "開発", "提唱", "証明", "解明", "確立", "創始", "考案",
    "導入", "構築", "定式化", "体系化", "測定", "観測", "実験",
    "法則", "定理", "公式", "方程式", "効果", "現象", "模型", "モデル", "予言",
    "分類", "計算", "著書", "教科書", "業績", "貢献", "受賞", "ノーベル", "命名",
    "記述", "製作", "設計", "同定", "合成", "分析", "原理", "仮説", "学説",
    "開拓", "実現", "刷新", "名著", "先駆者", "基礎を築", "道を開",
)

# 冒頭の「{人名}は、」除去まわり
HIRAGANA = re.compile(r"[ぁ-ん]")
# 残りが名詞述語として自然に完結する語尾(体言止め以外に許可するもの)
NOUN_PRED_TAIL = ("である", "であった", "だった", "とされる", "といわれる",
                  "と呼ばれる")
# 人名の後ろに付きうる短い爵位等(「〜男爵」「〜卿」)。ひらがなは接続助詞なので不可
NAME_SUFFIX = re.compile(r"^[一-龥]{0,3}$")


def clean_ws(s: str) -> str:
    """改行・タブ・連続空白を1つの半角空白に潰して1行にする。"""
    return re.sub(r"[\s　]+", " ", (s or "").replace("\n", " ")
                  .replace("\t", " ").replace("\r", " ")).strip()


def _sanitize_desc(s: str) -> str:
    """CSVパーサを壊す文字を除去(ASCIIカンマ・二重引用符を削除)。日本語の
    「、」「。」「（）」「：」は残す。連続空白は1つに。"""
    # 動画用フォントで欠字になりやすいIPA表記は説明文には不要。
    s = re.sub(r"\[[^\]]*[\u0250-\u02ff\u1d00-\u1dbf][^\]]*\]", "", s)
    s = re.sub(r"\(\s*音声ファイル\s*\)", "", s)
    s = s.replace('"', "").replace(",", " ")
    return re.sub(r"[\s　]+", " ", s).strip()


def strip_lead_paren(text: str) -> str:
    """記事名直後の生没年・原語表記カッコ（…）/(…) を1つ除去する。
    典型は「名前（…）は、…」。閉じカッコ直後に「は」が来る位置をアンカーにして
    除去する(元記事のカッコ対応が壊れていても暴走しないため)。"""
    opens, closes = "（(", "）)"
    idx = next((i for i, c in enumerate(text) if c in opens), None)
    if idx is None:
        return text
    # 1) 「）は」を優先アンカーにする(name（…）は、… の閉じカッコ)
    # 別名列挙の「または」がカッコより前にあっても、主語の「は」と誤認しない。
    m = re.search(r"[）)]\s*は", text)
    if m and m.start() >= idx:
        return (text[:idx].rstrip() + text[m.start() + 1:].lstrip()).strip()
    ha, period = text.find("は"), text.find("。")
    limit = min([x for x in (ha, period) if x != -1], default=len(text))
    if idx > limit:  # カッコが「は」「。」より後 = 本文中のカッコなので触らない
        return text
    # 2) フォールバック: 対応の取れたブロック。ただし最初の「。」を越えたら暴走と
    #    みなして除去しない(壊れたカッコ対策)
    end = period if period != -1 else len(text)
    depth, j = 0, idx
    while j < len(text):
        if text[j] in opens:
            depth += 1
        elif text[j] in closes:
            depth -= 1
            if depth == 0:
                return (text[:idx].rstrip() + text[j + 1:].lstrip()).strip()
        if j >= end and depth > 0:
            return text
        j += 1
    return text


def _norm_name(s: str) -> str:
    return s.replace(" ", "").replace("　", "").replace("=", "＝")


def _is_name_head(head: str, name: str) -> bool:
    """「〜は」の「〜」が name の呼称かどうか。ミドルネーム付き・敬称付き
    (サー・〜)・爵位付き(〜男爵)・姓のみ、といった表記ゆれを許容する。"""
    if head == name or head.endswith(name):
        return True
    if len(head) >= 3 and name.endswith(head):  # 姓のみ等の短縮形
        return True
    i = head.find(name)
    return i >= 0 and bool(NAME_SUFFIX.match(head[i + len(name):]))


def strip_name_prefix(desc: str, name: str) -> str:
    """description 冒頭の「{人名}は、」を除去する。動画キャプションでは人名が
    別に表示されるため冗長なので落とす。

    ただし除去すると主語を失って壊れる文(「〜は…で、…した。」のように残りの
    1文目が用言で終わる)や、上流のカッコ対応が壊れている文はそのまま返す。"""
    if not desc or not name or name == "NA":
        return desc
    name = _norm_name(name)
    end = desc.find("。")
    end = len(desc) if end == -1 else end
    for m in re.finditer("は", desc[:end]):
        head = _norm_name(desc[:m.start()])
        if not head or len(head) > 30 or "、" in head:
            continue
        if not _is_name_head(head, name):
            continue
        rest = desc[m.end():].lstrip("、 ").strip()
        first = rest.split("。")[0]
        if len(first) < 4:
            return desc
        if first.count("）") > first.count("（") or first.count(")") > first.count("("):
            return desc
        if HIRAGANA.match(first[-1]) and not first.endswith(NOUN_PRED_TAIL):
            return desc
        return rest
    return desc


def _cut_at_comma(s: str, target: int = DESC_TARGET, hard: int = DESC_HARD) -> str:
    """長すぎる1文を「、」境界で切って「。」を付す(中途半端な断片回避)。"""
    pos = s[:hard].rfind("、")
    return (s[:pos] if pos >= 30 else s[:target]).rstrip("、 ") + "。"


def has_achievement(text: str) -> bool:
    """説明文に具体的な業績を示す語が含まれるか。"""
    text = text or ""
    if any(word in text for word in ACHIEVEMENT_WORDS):
        return True
    # 「研究者」「研究所」「理論物理学者」のような肩書き・所属だけでは
    # 業績とみなさず、具体的な研究・理論への言及だけを拾う。
    return bool(re.search(r"研究(?!者|所|院|科|部|室|機関|職)", text)
                or re.search(r"理論(?!物理学者|化学者|数学者|生物学者)", text))


def _assemble(text: str, prefer_achievement: bool = False) -> str:
    """完結した文(「。」区切り)だけを目安 DESC_TARGET 字まで連結する。常に
    「。」で終わる。1文目が長すぎる場合のみ「、」境界で切る。"""
    text = text.strip("、 ").strip()
    if not text:
        return ""
    ends_complete = text.endswith("。")
    segs = [s.strip() for s in text.split("。")]
    complete = [s for s in (segs if ends_complete else segs[:-1]) if s]
    if complete:
        if prefer_achievement:
            start = next((i for i, s in enumerate(complete)
                          if has_achievement(s)), None)
            if start is not None:
                complete = complete[start:]
        out = ""
        for s in complete:
            cand = out + s + "。"
            if out and len(cand) > DESC_TARGET:
                break
            out = cand
            if len(out) >= DESC_TARGET:
                break
        return out if len(out) <= DESC_HARD else _cut_at_comma(complete[0])
    # 完結文が無い(冒頭抽出が1文目の途中で切れている)場合は「、」で整形
    frag = (segs[0] if segs else text).strip()
    return _cut_at_comma(frag) if frag else ""


def make_description(intro: str, wd_desc: str, name: str = "",
                     prefer_achievement: bool = False) -> str:
    """動画キャプションに使える完結文を作る。Wikipedia 冒頭文を優先し、先頭の
    生没年カッコと冒頭の「{人名}は、」を除去してから「。」区切りで完結文を連結。
    無ければ Wikidata の ja description(完結句)にフォールバック、どちらも
    無ければ NA。"""
    text = strip_name_prefix(strip_lead_paren(clean_ws(intro)), name)
    desc = _sanitize_desc(_assemble(text, prefer_achievement)).strip()
    if desc and not desc.endswith("。"):
        desc += "。"
    if not desc:
        wd = _sanitize_desc(clean_ws(wd_desc)).strip()
        desc = (wd + "。") if wd and not wd.endswith("。") else wd
    return desc or "NA"


PLAYER_ACHIEVEMENT_TERMS = {
    "MVP": 4,
    "最優秀": 4,
    "バロンドール": 4,
    "国民栄誉賞": 4,
    "文化勲章": 4,
    "最多": 3,
    "記録": 3,
    "受賞": 3,
    "殿堂": 3,
    "得点王": 3,
    "本塁打王": 3,
    "首位打者": 3,
    "達成": 2,
    "優勝": 2,
    "タイトル": 2,
    "表彰": 2,
    "選出": 1,
    "貢献": 1,
}


def make_player_description(intro: str, name: str = "") -> str:
    """選手記事の冒頭から主要実績を優先した説明文を作る。

    受賞・優勝・記録などを含む完結文があれば、重み付きで最も情報量の多い1文を
    採る。記事冒頭が所属・ポジションだけなら通常の人物説明にフォールバックする。
    """
    text = clean_ws(intro)
    sentences = [sentence.strip() for sentence in text.split("。") if sentence.strip()]
    ranked = []
    for index, sentence in enumerate(sentences):
        score = sum(
            weight * sentence.count(term)
            for term, weight in PLAYER_ACHIEVEMENT_TERMS.items()
        )
        if score:
            ranked.append((score, -index, sentence))
    if ranked:
        sentence = max(ranked)[2] + "。"
        return make_description(sentence, "", name)
    return make_description(intro, "", name)


def titles_to_qids(titles: list) -> dict:
    """記事タイトル -> Wikidata QID。曖昧さ回避ページは除外"""
    result = {}
    for i in range(0, len(titles), 50):
        data = api({"action": "query", "prop": "pageprops",
                    "ppprop": "wikibase_item|disambiguation", "redirects": 1,
                    "titles": "|".join(titles[i:i + 50])})
        redir = {r["to"]: r["from"] for r in data["query"].get("redirects", [])}
        for p in data["query"]["pages"].values():
            pp = p.get("pageprops", {})
            if "disambiguation" in pp or "wikibase_item" not in pp:
                continue
            result[redir.get(p["title"], p["title"])] = pp["wikibase_item"]
        time.sleep(0.3)
    return result


def qids_to_images(qids: list) -> dict:
    """QID -> (image_url, image_page)。P18(画像)があるものだけ返す"""
    result = {}
    for i in range(0, len(qids), 50):
        url = WD_API + "?" + urllib.parse.urlencode({
            "action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
            "props": "claims", "format": "json"})
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=60) as res:
                    entities = json.load(res).get("entities", {})
                break
            except Exception as ex:
                print(f"retry {attempt}: {ex}")
                time.sleep(5 * (attempt + 1))
        else:
            continue
        for q, e in entities.items():
            for c in e.get("claims", {}).get("P18", []):
                dv = c.get("mainsnak", {}).get("datavalue")
                if dv:
                    # カンマ等を含むファイル名はCSVを壊すので必ずURLエンコード
                    result[q] = commons_urls(dv["value"])
                    break
        time.sleep(0.3)
    return result


def images_for_titles(titles: list) -> dict:
    """記事タイトル -> (image_url, image_page)"""
    t2q = titles_to_qids(titles)
    q2img = qids_to_images(sorted(set(t2q.values())))
    return {t: q2img[q] for t, q in t2q.items() if q in q2img}


def write_csv_no_trailing_newline(path, cols, rows):
    import csv as _csv
    import io as _io
    buf = _io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    text = buf.getvalue().rstrip("\n")
    # soramimic側のパーサは素朴なsplit(\",\")なので、クオートが必要になる
    # フィールド(カンマ・引用符入り)は書き込み前にエラーにする
    if '"' in text:
        bad = [line for line in text.splitlines() if '"' in line][:3]
        raise ValueError(f"quoted field would break the naive parser: {bad}")
    # 末尾改行なしで書く(パーサが最終空行で落ちるため)
    path.write_text(text, encoding="utf-8")
