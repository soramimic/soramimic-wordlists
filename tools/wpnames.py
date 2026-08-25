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


def _name_parts(s: str) -> list[str]:
    """欧文由来の人名を、ミドルネームを無視して比較できる単位に分ける。"""
    return [
        _norm_name(part)
        for part in re.split(r"[・＝゠=\s]+", s)
        if len(_norm_name(part)) >= 2
    ]


def _is_name_head(head: str, name: str) -> bool:
    """「〜は」の「〜」が name の呼称かどうか。ミドルネーム付き・敬称付き
    (サー・〜)・爵位付き(〜男爵)・姓のみ、といった表記ゆれを許容する。"""
    raw_name = name
    head = _norm_name(head)
    name = _norm_name(name)
    compact_head = re.sub(r"[・＝゠=]", "", head)
    compact_name = re.sub(r"[・＝゠=]", "", name)
    if compact_head == compact_name or compact_head.endswith(compact_name):
        return True
    if len(compact_head) >= 3 and compact_name.endswith(compact_head):  # 姓のみ等
        return True
    i = compact_head.find(compact_name)
    if i >= 0 and bool(NAME_SUFFIX.match(compact_head[i + len(compact_name):])):
        return True
    # 「レイチェル・カーソン」に対する
    # 「レイチェル・ルイーズ・カーソン」のようなミドルネーム入り表記。
    parts = _name_parts(raw_name)
    if len(parts) < 2:
        return False
    first = head.find(parts[0])
    last = head.rfind(parts[-1])
    return first >= 0 and last >= first + len(parts[0])


def strip_name_prefix(desc: str, name: str) -> str:
    """description 冒頭の「{人名}は、」を除去する。動画キャプションでは人名が
    別に表示されるため冗長なので落とす。

    カードでは人名が直前に大きく表示されるため、述語文でも主語を省略して
    意味が通る。「または」の「は」は助詞ではないので対象外。"""
    if not desc or not name or name == "NA":
        return desc
    end = desc.find("。")
    end = len(desc) if end == -1 else end
    for m in re.finditer("は", desc[:end]):
        if desc[max(0, m.start() - 2):m.end()] == "または":
            continue
        head = desc[:m.start()]
        if not head or len(head) > 60 or "、" in head:
            return desc
        if re.match(
            r"^(?:実?父|実?母|父親|母親|兄|弟|姉|妹|息子|娘|夫|妻)の",
            head,
        ):
            return desc
        if not _is_name_head(head, name):
            # 文中の人名の後ろに現れる助詞を、冒頭主語と誤認しない。
            return desc
        rest = desc[m.end():].lstrip("、 ").strip()
        return rest
    return desc


def _cut_at_comma(s: str, target: int = DESC_TARGET, hard: int = DESC_HARD) -> str:
    """長すぎる1文を「、」境界で切って「。」を付す(中途半端な断片回避)。"""
    pos = s[:hard].rfind("、")
    return (s[:pos] if pos >= 30 else s[:target]).rstrip("、 ") + "。"


def has_achievement(text: str) -> bool:
    """説明文に具体的な業績を示す語が含まれるか。"""
    text = text or ""
    # 肩書きに含まれる語を業績と誤認しない。
    searchable = re.sub(
        r"(?:発明家|実験物理学者|実験科学者|計算機科学者|"
        r"計算機科学|現象学者|分析化学者|研究開発局|"
        r"開発員|開発マネージャー)",
        "",
        text,
    )
    if any(word in searchable for word in ACHIEVEMENT_WORDS):
        return True
    # 「研究者」「研究所」「理論物理学者」のような肩書き・所属だけでは
    # 業績とみなさず、具体的な研究・理論への言及だけを拾う。
    return bool(
        re.search(r"研究(?!者|所|院|科|部|室|機関|職|分野)", text)
        or re.search(
            r"理論(?!物理学(?:者|研究)|化学者|数学者|生物学者)", text
        )
    )


ACHIEVEMENT_WEIGHTS = {
    "発見": 8, "発明": 8, "提唱": 8, "証明": 8, "確立": 8, "創始": 8,
    "考案": 8, "ノーベル": 8, "受賞": 7, "法則": 7, "定理": 7,
    "方程式": 7, "公式": 7, "開発": 6, "解明": 6, "定式化": 6,
    "体系化": 6, "予言": 6, "原理": 6, "仮説": 6, "学説": 6,
    "教科書": 6, "名著": 6, "構築": 5, "模型": 5, "モデル": 5,
    "設計": 5, "製作": 5, "同定": 5, "合成": 5, "著書": 4,
    "測定": 4, "観測": 4, "実験": 4, "計算": 4, "分類": 4,
    "業績": 3, "貢献": 3, "先駆者": 3, "基礎を築": 5, "道を開": 5,
}


def achievement_score(sentence: str) -> int:
    """肩書き・経歴より具体的な科学業績文を上位にする重み付きスコア。"""
    searchable = re.sub(
        r"(?:発明家|実験物理学者|実験科学者|計算機科学者|"
        r"計算機科学|現象学者|分析化学者|研究開発局|"
        r"開発員|開発マネージャー)",
        "",
        sentence,
    )
    score = sum(
        weight for word, weight in ACHIEVEMENT_WEIGHTS.items()
        if word in searchable
    )
    score -= 2 * len(re.findall(r"大学|教授|所長|卒業|出身|生まれ|任命", sentence))
    if re.search(r"主な(?:研究)?業績|代表的な?業績", sentence):
        score += 10
    if re.match(r"(?:このほか|また|一方)", sentence):
        score -= 10
    if re.search(r"行わず|おらず|されず|ではない|なかった|未発見|未解決", sentence):
        score -= 15
    if re.match(r"(?:先人|同時代人|師|弟子)", sentence):
        score -= 8
    # 親族の受賞・業績を本人のものとして拾わない。
    if re.search(r"(?:父|母|息子|娘|夫|妻|兄|弟|姉|妹).{0,16}(?:受賞|業績|発見)", sentence):
        score -= 10
    return score


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
            ranked = sorted(
                ((achievement_score(s), -i, s) for i, s in enumerate(complete)),
                reverse=True,
            )
            if ranked and ranked[0][0] > 0:
                complete = [ranked[0][2]]
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
PLAYER_DESC_TARGET = 50
PLAYER_DESC_MAX = 65
PLAYER_DESCRIPTION_OVERRIDES = {
    "浅尾拓也": (
        "2010年・2011年にセ・リーグ最優秀中継ぎ投手。"
        "2011年はリーグMVP。"
    ),
    "飯塚誠": "1950年に51本塁打・161打点で二冠王とセ・リーグMVPを獲得。",
    "小鶴誠": "1950年に51本塁打・161打点で二冠王とセ・リーグMVPを獲得。",
    "石井一久": "NPBで最多奪三振2回、最高勝率1回、最優秀防御率1回を獲得。",
    "石川雅規": "2002年のセ・リーグ新人王。大卒投手初の新人年から24年連続安打を記録。",
    "上原浩治": "NPB新人年に投手三冠。アジア人初の100勝・100セーブ・100ホールド達成。",
    "小野和義": "近鉄時代に2桁勝利を5度記録。NPB通算82勝。",
    "斉藤和巳": "2003年に投手三冠・リーグMVP。2006年に投手四冠・沢村賞。",
    "九里亜蓮": "2021年に13勝を挙げ、セ・リーグ最多勝利を獲得。",
    "灰山元章": "1931年に4番・エースとして広島商業の夏の甲子園連覇に貢献。",
    "池山隆寛": "ヤクルト一筋で通算304本塁打。5年連続30本塁打を記録。",
    "島野育夫": "中日・阪神で星野仙一監督を支え、コーチとして両球団のリーグ優勝を経験。",
    "中山裕章": "中日の救援投手として1999年のセ・リーグ優勝に貢献。",
    "西本聖": "投手最多タイとなるゴールデングラブ賞8回を受賞。",
    "ウラディミール・バレンティン": (
        "2013年にNPB記録のシーズン60本塁打と長打率.779を記録。"
    ),
    "ウィリー・アップショー": (
        "1989年に福岡ダイエーで33本塁打・80打点を記録。"
    ),
    "藤本英雄": "1943年に防御率0.73と19完封のNPB記録。1950年にNPB初の完全試合。",
    "ジョン・ボウカー": "2012年の日本シリーズで2本塁打を放ち、巨人の日本一に貢献。",
    "星野仙一": "1974年に15勝10セーブで沢村賞とセ・リーグ初の最多セーブ投手。",
    "村田勝喜": "1991年から3年連続で2桁勝利・2桁完投を記録。",
    "前田健太": "2010年に投手三冠。沢村賞2回、最優秀防御率3回。",
    "宮西尚生": "NPB史上初の通算400ホールド。最優秀中継ぎ投手3回。",
    "フォルラン": "2010年W杯で5得点を挙げ、大会MVPのゴールデンボールを受賞。",
    "ディエゴ・フォルラン": (
        "2010年W杯で5得点を挙げ、大会MVPのゴールデンボールを受賞。"
    ),
    "洪明甫": "韓国代表でW杯に4大会連続出場。2002年W杯でブロンズボールを受賞。",
    "釜本邦茂": "日本代表歴代最多の75得点。1968年メキシコ五輪得点王・銅メダル。",
    "三浦知良": "1993年の初代JリーグMVP・アジア年間最優秀選手。",
    "中田英寿": "アジア年間最優秀選手賞を2度受賞。2000-01年のローマのセリエA優勝に貢献。",
    "本田圭佑": "W杯3大会連続で得点し、日本人最多のW杯通算4得点を記録。",
    "香川真司": "ドルトムントのブンデスリーガ2連覇とマンチェスター・ユナイテッドのリーグ優勝に貢献。",
    "遠藤保仁": "日本代表歴代最多の国際Aマッチ152試合出場。2009年アジア年間最優秀選手。",
    "長友佑都": "2010〜2022年にW杯4大会連続出場。インテルでコッパ・イタリア優勝。",
    "吉田麻也": "W杯3大会出場。2019年から日本代表主将を務め、国際Aマッチ126試合出場。",
    "小野伸二": "2002年にフェイエノールトでUEFAカップ優勝。アジア年間最優秀選手賞受賞。",
    "岡崎慎司": "レスターの2015-16年プレミアリーグ初優勝に貢献。日本代表通算50得点。",
    "中村俊輔": "2006-07年スコットランドリーグMVP。J1最多の直接FK24得点。",
    "中山雅史": "1998年W杯で日本代表の本大会初得点。JリーグMVPと2度の得点王。",
    "ラモス瑠偉": "1992年アジアカップ初優勝に貢献。日本代表最年長得点記録保持者。",
    "奥寺康彦": "日本人初のブンデスリーガ選手。ケルンでリーグ優勝・ドイツ杯制覇。",
    "大久保嘉人": "J1歴代最多の通算191得点。史上初の3年連続J1得点王。",
    "稲本潤一": "2002年W杯で2得点を挙げ、日本代表初のベスト16進出に貢献。",
    "高原直泰": "2002年にJリーグMVP・得点王。ブンデスリーガ通算25得点。",
    "名波浩": "ジュビロ磐田のJリーグ3度の優勝に貢献。2000年アジアカップMVP。",
    "ジーコ": "フラメンゴ史上最多の509得点。ブラジル代表でW杯3大会出場。",
    "ストイチコフ": "1994年W杯でブルガリアをベスト4へ導き、得点王・バロンドール。",
    "フリスト・ストイチコフ": (
        "1994年W杯でブルガリアをベスト4へ導き、得点王・バロンドール。"
    ),
    "ロナウド": "2002年W杯で8得点を挙げ、得点王としてブラジルの優勝に貢献。",
    "ディエゴ・マラドーナ": "1986年W杯で大会MVPとなり、アルゼンチンを優勝に導いた。",
    "マラドーナ": "1986年W杯で大会MVPとなり、アルゼンチンを優勝に導いた。",
    "アンドレス・イニエスタ": "2010年W杯決勝で優勝を決める得点。バルセロナでリーグ優勝9回。",
    "ダビド・ビジャ": "スペイン代表歴代最多の59得点。2010年W杯優勝に貢献。",
    "フェルナンド・トーレス": "2008年欧州選手権決勝で決勝点。2010年W杯でも優勝。",
    "ゲーリー・リネカー": "1986年W杯で6得点を挙げ、イングランド代表として得点王。",
    "リネカー": "1986年W杯で6得点を挙げ、イングランド代表として得点王。",
    "ドゥンガ": "主将として1994年W杯でブラジル代表を優勝に導いた。",
    "ベベット": "1994年W杯優勝に貢献。1989年南米年間最優秀選手。",
    "ギド・ブッフバルト": "1990年W杯決勝でマラドーナを封じ、西ドイツの優勝に貢献。",
    "ブッフバルト": "1990年W杯決勝でマラドーナを封じ、西ドイツの優勝に貢献。",
    "ピエール・リトバルスキー": "1990年W杯で西ドイツ代表として優勝。",
    "リトバルスキー": "1990年W杯で西ドイツ代表として優勝。",
    "ミカエル・ラウドルップ": "バルセロナでリーグ4連覇・欧州チャンピオンズカップ優勝。",
    "ラウドルップ": "バルセロナでリーグ4連覇・欧州チャンピオンズカップ優勝。",
    "朴智星": "マンチェスター・ユナイテッドでリーグ優勝4回・欧州CL優勝。",
    "アーセン・ベンゲル": "アーセナルでプレミアリーグ優勝3回。2003-04年は無敗優勝。",
    "ベンゲル": "アーセナルでプレミアリーグ優勝3回。2003-04年は無敗優勝。",
    "岡田武史": "日本代表監督として1998年W杯初出場、2010年W杯ベスト16。",
    "加茂周": "日本代表監督を1994〜1997年に務め、1995年ダイナスティカップ優勝。",
    "白井博幸": "U-23日本代表に選出されたディフェンダー。",
    "池谷友良": "ロッソ熊本初代監督。ロアッソ熊本運営会社の社長を歴任。",
    "フアン・エスナイデル": (
        "1995年欧州カップウィナーズカップ決勝で得点し、サラゴサの優勝に貢献。"
    ),
    "大谷翔平": (
        "MLB史上初の50本塁打・50盗塁を達成し、"
        "両リーグでMVPを受賞した投打の二刀流選手。"
    ),
    "王貞治": "NPB最多の通算868本塁打を記録した、国民栄誉賞受賞者第1号。",
    "野茂英雄": "新人年に投手三冠を達成した、NPB新人王・パ・リーグMVP受賞者。",
    "エディ・ギャラード": (
        "2000年・2002年の最優秀救援投手。NPB通算120セーブ。"
    ),
}
PLAYER_CONTEXTUAL_DESCRIPTION = re.compile(
    r"(?:^|。)(?:また[、]?|さらに[、]?|なお[、]?|同年|同大会|その後|"
    r"この|翌年|翌\d|チーム|ほかに|その他)"
    r"|(?:など|しており|ており|であり)。$"
)
PLAYER_DISAMBIGUATION_DESCRIPTION = re.compile(
    r"とは、以下の|以下の人物を指す|一覧参照|"
    r"(?:男性名|女性名|姓名|人名)である。$|(?:男性名|女性名|人名)。$"
)
PLAYER_ROLE_DESCRIPTION = re.compile(
    r"(?:プロ)?野球選手|サッカー選手|フットボール選手"
)
PLAYER_NON_NAME_SUBJECT = re.compile(
    r"出身|出生|現役|当時|時代|通算|シーズン|試合|記録|受賞|"
    r"優勝|代表|監督として|選手として|NPB|MLB|Jリーグ"
)


def has_redundant_player_subject(description: str) -> bool:
    """選手の肩書き文が、冒頭で本人名を主語に繰り返す形かを返す。

    略称と本名が一致しない場合も、後半が選手の肩書きなら検出する。
    出生地の括弧内や「現役時代は」のような非人名主語は除外する。
    """
    text = clean_ws(description)
    particle = next(
        (
            match
            for match in re.finditer("は", text[:61])
            if text[max(0, match.start() - 2):match.end()] != "または"
        ),
        None,
    )
    if not particle:
        return False
    head = text[:particle.start()]
    rest = text[particle.end():].lstrip("、､ ")
    if not PLAYER_ROLE_DESCRIPTION.search(rest):
        return False
    if "、" in head or PLAYER_NON_NAME_SUBJECT.search(head):
        return False
    if head.count("（") != head.count("）") or head.count("(") != head.count(")"):
        return False
    relative = r"(?:実?父|実?母|父親|母親|兄|弟|姉|妹|息子|娘|夫|妻)"
    if re.search(rf"(?:^{relative}の|{relative}$)", head):
        return False
    return True


def is_likely_disambiguation_text(text: str) -> bool:
    """Wikipediaの曖昧さ回避ページ由来と考えられる本文かを返す。"""
    text = clean_ws(text)
    depth = 0
    dash_outside_parentheses = False
    for offset, char in enumerate(text):
        if char in "（(":
            depth += 1
        elif char in "）)":
            depth = max(0, depth - 1)
        elif depth == 0 and text.startswith(" - ", offset):
            # 曖昧さ回避の「項目名 - 説明」は拾うが、人物記事の生没年
            # 「（1989年10月2日 - ）」等は括弧内なので拾わない。
            dash_outside_parentheses = True
            break
    return bool(
        PLAYER_DISAMBIGUATION_DESCRIPTION.search(text)
        or dash_outside_parentheses
        or re.search(r"\{\{\s*(?:aimai|曖昧さ回避)", text, re.IGNORECASE)
    )


def is_standalone_player_description(description: str) -> bool:
    """カード単体で意味が通り、完結している選手説明かを返す。"""
    return bool(
        description
        and description != "NA"
        and description.endswith(("。", "…"))
        and not PLAYER_CONTEXTUAL_DESCRIPTION.search(description)
    )


def _shorten_player_description(description: str) -> str:
    """約2行の50文字を目安に整え、完結文は65文字まで許容する。"""
    if len(description) <= PLAYER_DESC_TARGET:
        return description
    compact = re.sub(r"（[^（）]*）", "", description)
    compact = re.sub(r"\([^()]*\)", "", compact)
    compact = re.sub(r"[\s　]+", " ", compact).strip()
    if len(compact) <= PLAYER_DESC_MAX:
        return compact
    return compact[:PLAYER_DESC_MAX - 1].rstrip("、。 ") + "…"


def _best_player_achievement_clause(sentence: str) -> str:
    """長い実績列挙から、受賞・優勝・記録を最もよく表す1節を選ぶ。"""
    if len(sentence) <= PLAYER_DESC_MAX:
        return sentence
    titles = re.search(
        r"(\d+度の[^、。]{1,20}優勝と\d+度の[^、。]{1,30}優勝)",
        sentence,
    )
    if titles and len(titles.group(1)) <= PLAYER_DESC_MAX:
        return titles.group(1)
    clauses = [clause.strip() for clause in sentence.split("、") if clause.strip()]
    ranked = []
    for index, clause in enumerate(clauses):
        score = sum(
            weight * clause.count(term)
            for term, weight in PLAYER_ACHIEVEMENT_TERMS.items()
        )
        if score:
            ranked.append((score, -index, clause))
    if not ranked:
        return sentence
    clause = max(ranked)[2]
    index = clauses.index(clause)
    clause = re.sub(r"^(?:また|さらに|なお)", "", clause).strip()
    if index and re.match(r"^(?:チーム|大会|同年|同大会|その)", clause):
        contextual = clauses[index - 1] + "、" + clause
        if len(contextual) <= PLAYER_DESC_MAX:
            clause = contextual
    if clause.endswith("し"):
        clause += "た"
    elif clause.endswith("であり"):
        clause = clause[:-3] + "である"
    return clause


def make_player_description(
    intro: str,
    name: str = "",
    *,
    allow_override: bool = True,
) -> str:
    """選手記事の冒頭から主要実績を優先した説明文を作る。

    受賞・優勝・記録などを含む完結文があれば、重み付きで最も情報量の多い1文を
    採る。記事冒頭が所属・ポジションだけなら通常の人物説明にフォールバックする。
    """
    normalized_name = DISAMBIG.sub("", name).replace(" ", "").replace("　", "")
    override = (
        PLAYER_DESCRIPTION_OVERRIDES.get(normalized_name) if allow_override else None
    )
    if override:
        return override
    if is_likely_disambiguation_text(intro):
        return "NA"
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
    for _, _, sentence in sorted(ranked, reverse=True):
        sentence = _best_player_achievement_clause(sentence) + "。"
        description = _shorten_player_description(
            make_description(sentence, "", name)
        )
        if is_standalone_player_description(description):
            return description
    first = (sentences[0] + "。") if sentences else intro
    description = _shorten_player_description(make_description(first, "", name))
    return description if is_standalone_player_description(description) else "NA"


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
