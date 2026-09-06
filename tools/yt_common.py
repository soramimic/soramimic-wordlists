"""youtuber.csv 自動更新の共通処理(詳細は docs/adr/00011, 00012)。

出典: Wikidata(職業P106がYouTuber/バーチャルYouTuberで、ja.wikipediaに記事が
ある人物)と、Wikipedia日本語版記事の冒頭文(CC BY-SA 4.0)。

- YouTuberとVTuberを別ファイルに収録し、category列(youtuber/vtuber)を保持する
- 収録は記事名(=活動名)のみ。本名などの個人情報は取得しない
- 姓名分割できる名前(兎田ぺこら等)は family/given/full、ハンドル型
  (HIKAKIN/キズナアイ等)は full のみ
- 読みはカタカナ。かな名は自身から変換、漢字・ラテン文字名は記事冒頭
  「名前（よみ、」から抽出。機械決定できない名前はスキップして「要確認」に報告
- 既存行の表記・読み・idは書き換えない。自動で行うのは未収録者の追記と
  status の current→former 一方向更新(P2032: 活動終了)のみ

付加列(いずれも無ければ NA。既存行は空欄補完のみ行う: ADR 00014)
- org:        所属事務所・グループ(P108/P463/P1416、スラッシュ区切り多値)
- debut_year: 活動開始年(P2031、無ければチャンネル開設年 P2397+P580。ADR 00023)
- status:     current(活動中)/former(活動終了。P2032)
- channel:    メインYouTubeチャンネル名(P2397の修飾子P1810)。複数チャンネルを
              持つ人は登録者数(P3744)が最大の1本を採る(ADR 00029)
- description: 活動内容を優先した短い完結文(無ければWikidataのja description。
              目安50字・上限65字で、登録者数や所属・個人情報は除く。ADR 00045)

subscribers(メインチャンネルの登録者数)列も youtuber.csv にあるが、値の管理は
このモジュールの外(tools/update_youtuber_subscribers.py)で行う。時変値なので
毎回全行を上書きする列で、空欄補完のみの上記の付加列とは規則が違う(ADR 00030)。
このモジュールは既存CSVの列を読んでそのまま書き戻すので、subscribers の値には
触らない(新規追加した人の行は空になり、次に登録者数スクリプトが走ると埋まる)。
"""

import csv
import os
import pickle
import re
from pathlib import Path

from creator_csv import read_creator_csvs, write_creator_csvs
from wpnames import (DISAMBIG, HIRA2KATA, _sanitize_desc, clean_ws,
                     fetch_extracts, parse_person, sparql, strip_lead_paren,
                     strip_name_prefix, write_csv_no_trailing_newline)

COLS = ["id", "original", "surface", "pronunciation", "type",
        "category", "org", "debut_year", "status", "channel", "description"]
# 既存CSVに無ければ末尾に足す付加列(列順は既存ファイルの並びを崩さない)
NEW_COLS = ["channel", "description"]

# かな・カタカナだけのハンドル名(読みが自明)。wpnames.KATAKANA のひらがな込み版
KANA_ONLY = re.compile(r"^[ぁ-ゖァ-ヶー・=＝\s]+$")
# 冒頭カッコ内の読みとして許容する文字
YOMI = r"[ぁ-ゖァ-ヶー・]+"


def assert_occupation(qid: str, must: tuple, must_not: tuple):
    """QIDのja/enラベルに期待キーワードが含まれることを確認するフェイルセーフ。
    QIDの取り違え(別概念の取り込み)をクエリ実行前に検出する。"""
    q = f"""
SELECT ?l WHERE {{ wd:{qid} rdfs:label ?l . FILTER(LANG(?l) IN ("ja", "en")) }}"""
    labels = [b["l"]["value"] for b in sparql(q)["results"]["bindings"]]
    low = [l.lower() for l in labels]
    if not any(any(k.lower() in l for l in low) for k in must) or \
            any(any(k.lower() in l for l in low) for k in must_not):
        raise SystemExit(
            f"error: wd:{qid} のラベル {labels} が期待(must={must}, "
            f"must_not={must_not})と合わない。QIDを確認してください")


def _persons(occ: str, exclude: str = None, extra: str = "") -> dict:
    minus = f"MINUS {{ ?p wdt:P106 wd:{exclude} }}" if exclude else ""
    q = f"""
SELECT ?p ?title WHERE {{
  ?p wdt:P106 wd:{occ} .
  {minus}
  {extra}
  ?a schema:about ?p ; schema:isPartOf <https://ja.wikipedia.org/> ;
     schema:name ?title .
}}"""
    persons = {}
    for b in sparql(q)["results"]["bindings"]:
        qid = b["p"]["value"].rsplit("/", 1)[1]
        persons[qid] = b["title"]["value"]
    return persons


def fetch_persons(occ: str, exclude: str = None,
                  excluded_occs: dict = None) -> dict:
    """QID -> ja記事タイトル(職業P106=occ かつ ja.wikipediaに記事がある人物)。

    excluded_occs(QID -> ラベル)のいずれかを P106 に持つ人物は除外する。
    黙って消えると気付けないので、該当者は名前をログに出す。"""
    persons = _persons(occ, exclude)
    print(f"対象(wd:{occ}): {len(persons)}人(distinct QID)", flush=True)
    if excluded_occs:
        vals = " ".join(f"wd:{q}" for q in sorted(excluded_occs))
        dropped = _persons(occ, exclude,
                           f"VALUES ?bad {{ {vals} }} ?p wdt:P106 ?bad .")
        for qid in dropped:
            persons.pop(qid, None)
        print(f"  除外職業(P106)で除外: {len(dropped)}人: "
              + ", ".join(sorted(dropped.values())), flush=True)
    return persons


def _year(iso: str):
    try:
        return str(int(iso.split("-")[0]))
    except (ValueError, AttributeError, IndexError):
        return None


def _clean_label(s: str) -> str:
    """CSVパーサ(素朴なsplit)を壊す文字を除去し、空白を1つに潰す。"""
    return re.sub(r"[\s　]+", " ",
                  s.replace(",", " ").replace('"', "")).strip()


def _main_channel(pairs: str) -> str:
    """"登録者数@@チャンネル名" の連結から、メインチャンネル名を1本選ぶ。

    サブチャンネル・切り抜き・自動生成の Topic チャンネルまで P2397 に並ぶので、
    登録者数(P3744)が最大のものを本人のメインチャンネルとみなす。登録者数が
    無いチャンネルしか無い場合は名前の昇順で先頭(実行ごとに揺れないため)。"""
    cands = []
    for pair in pairs.split("||"):
        subs, _, name = pair.partition("@@")
        name = _clean_label(name)
        if not name:
            continue
        try:
            n = int(float(subs))
        except ValueError:  # 登録者数の修飾子が無いチャンネル
            n = -1
        cands.append((-n, name))
    return sorted(cands)[0][1] if cands else "NA"


def fetch_attrs(qids: list) -> dict:
    """QID -> {org, debut_year, status, channel, wd_desc}。P108/P463/P1416(所属)、
    P2031/P2032(活動期間)、P2397(YouTubeチャンネルID)の修飾子(開始時点P580・
    チャンネル名P1810・登録者数P3744)、ja description をバッチ取得。

    debut_year は P2031(活動開始)を優先し、無ければチャンネル開設年を使う。
    P2031 が入っている人は2割ほどしかいないのに対し、チャンネルIDの P580 は
    多くの項目にあり、YouTuberの「活動開始年」としては十分に近い。"""
    attrs = {}
    for i in range(0, len(qids), 200):
        batch = qids[i:i + 200]
        values = " ".join(f"wd:{q}" for q in batch)
        # チャンネル名と登録者数は同じ P2397 文の修飾子なので、別々に集約すると
        # 対応が失われる。「登録者数@@名前」に連結して1変数で集約し、どれが
        # メインかは Python 側(_main_channel)で決める
        q = f"""
SELECT ?p (GROUP_CONCAT(DISTINCT ?orgL; SEPARATOR="||") AS ?orgs)
  (MIN(?start) AS ?s) (MAX(?end) AS ?e) (MIN(?chan) AS ?c)
  (GROUP_CONCAT(DISTINCT ?chpair; SEPARATOR="||") AS ?chans)
  (SAMPLE(?wdesc) AS ?desc) WHERE {{
  VALUES ?p {{ {values} }}
  OPTIONAL {{ ?p wdt:P108|wdt:P463|wdt:P1416 ?org .
             ?org rdfs:label ?orgL . FILTER(LANG(?orgL)="ja") }}
  OPTIONAL {{ ?p wdt:P2031 ?start . FILTER(isLiteral(?start)) }}
  OPTIONAL {{ ?p wdt:P2032 ?end . FILTER(isLiteral(?end)) }}
  OPTIONAL {{ ?p p:P2397 ?st . ?st pq:P580 ?chan .
             FILTER NOT EXISTS {{ ?st wikibase:rank wikibase:DeprecatedRank }} }}
  OPTIONAL {{ ?p p:P2397 ?cst . ?cst pq:P1810 ?cname .
             FILTER NOT EXISTS {{ ?cst wikibase:rank wikibase:DeprecatedRank }}
             OPTIONAL {{ ?cst pq:P3744 ?csubs }}
             BIND(CONCAT(COALESCE(STR(?csubs), ""), "@@", STR(?cname))
                  AS ?chpair) }}
  OPTIONAL {{ ?p schema:description ?wdesc . FILTER(LANG(?wdesc)="ja") }}
}} GROUP BY ?p"""
        for b in sparql(q)["results"]["bindings"]:
            qid = b["p"]["value"].rsplit("/", 1)[1]
            orgs = set()
            for o in b.get("orgs", {}).get("value", "").split("||"):
                # ラベル内のカンマ・引用符はCSVパーサを壊すので除去
                o = _clean_label(o)
                if o:
                    orgs.add(o)
            attrs[qid] = {
                # 出力順をソート固定(WDQSのGROUP_CONCAT順は非決定的)
                "org": "/".join(sorted(orgs)) if orgs else "NA",
                "debut_year": (_year(b.get("s", {}).get("value"))
                               or _year(b.get("c", {}).get("value")) or "NA"),
                "status": "former" if b.get("e", {}).get("value") else "current",
                "channel": _main_channel(b.get("chans", {}).get("value", "")),
                "wd_desc": b.get("desc", {}).get("value", ""),
            }
        print(f"  属性取得 {min(i + 200, len(qids))}/{len(qids)}", flush=True)
    return attrs


# description に本名を持ち込まないためのフィルタ(このリストは活動名のみを
# 収録する。ADR 00011, 00029)。記事冒頭には本名がよく書かれている
REALNAME = re.compile(r"本名|実名|戸籍名|出生名|旧姓")
# 文頭の「〜は、」(カッコを外した後の冒頭。「、」「。」を跨がない範囲)
LEAD_SUBJ = re.compile(r"^(.{2,30}?)は[、 ]")
# 人名らしさの判定に使う区切り(姓名の空白、カタカナ名の中黒)
NAME_SEP = re.compile(r"[ 　・＝=]")
# 「{本名}は、{活動名}として知られる〜」の言い換え表現。主語が1語の名前
# (「アレクサンダーは、テクノブレードとして知られる〜」)でも本名なので落とす
KNOWN_AS = re.compile(r"として(も|オンラインで)?(よく)?知られ|の名で知られ"
                      r"|を名乗|の芸名|の活動名|通称")


def _plain(s: str) -> str:
    return NAME_SEP.sub("", s)


def _balanced(s: str) -> bool:
    """カッコの対応が取れているか。読みカッコの中に「〜は、」がある名前
    (「風真 いろは（かざま いろは、英: …）は、」)で主語の切り出しを誤らないため。"""
    return s.count("（") == s.count("）") and s.count("(") == s.count(")")


def deidentify(intro: str, original: str) -> str:
    """記事冒頭文から本名の記述を落とす。

    - 「本名は〜」「本名：〜」を含む文は丸ごと捨てる
    - 冒頭が活動名ではない人名の「{本名}は、〜」形式なら、その主語を落として
      述部だけ残す。人名とみなすのは姓名の空白・中黒を含む語(「水戸 由菜は、」
      「アラン・オラフ・ウォーカーは、」)か、「〜として知られる」等が続く1語の名前
      (「アレクサンダーは、テクノブレードとして知られる〜」)。「コムドットは、〜」
      のようなグループ名・屋号は残す
    """
    text = strip_lead_paren(clean_ws(intro))
    # 文末の「。」を保ったまま分割する(最後が未完の断片かどうかを make_description
    # が見るため、勝手に「。」を足さない)
    segs = [s for s in re.split(r"(?<=。)", text) if s.strip()]
    kept = [s for s in segs if not REALNAME.search(s)]
    if not kept:
        return ""
    m = LEAD_SUBJ.match(kept[0])
    if m:
        head = m.group(1)
        rest = kept[0][m.end():]
        if _plain(head) != _plain(original) and _balanced(head) \
                and _balanced(rest) \
                and (NAME_SEP.search(head) or KNOWN_AS.search(kept[0])):
            kept[0] = rest.lstrip("、 ")
    return "".join(kept).strip()


def safe_wd_desc(s: str) -> str:
    """Wikidataのja descriptionも本名を含むものは使わない(フォールバック用)。"""
    return "" if REALNAME.search(s or "") else (s or "")


# YouTuberカードの説明は、選手カードと同じく「1〜2行」を優先する。90字の
# scientist/youtuber共通方式をそのまま使うと、所属・登録者数・出身地などが続き、
# 何をしている人かが見えにくくなるため、YouTuberだけ活動内容を選ぶ。
YOUTUBER_DESC_TARGET = 50
YOUTUBER_DESC_MAX = 65
YOUTUBER_DYNAMIC = re.compile(
    r"チャンネル登録者数|登録者数|登録者|フォロワー数|フォロワー|"
    r"再生回数|視聴回数|動画再生"
)
YOUTUBER_PERSONAL = re.compile(
    r"血液型|出身|生まれ|在住|妻|夫|結婚|既婚|子供|家族"
)
YOUTUBER_ORG = re.compile(
    r"所属|株式会社|代表取締役|本社|プロダクション|マネージャー|"
    r"拠点を置く"
)
YOUTUBER_CONTEXT = re.compile(
    r"^(?:また|その後|同年|翌年|この年|現在は|現在も|以降|これまで)[、 ]*"
)
YOUTUBER_ACTIVITY = {
    "動画": 3, "動画投稿": 4, "投稿": 2, "配信": 3, "ライブ": 3,
    "ゲーム実況": 5, "実況": 3, "音楽": 3, "楽曲": 3, "歌": 2,
    "アニメ": 3, "アフレコ": 4, "料理": 3, "レシピ": 3, "クイズ": 3,
    "解説": 3, "レビュー": 3, "教育": 3, "学習": 3, "科学": 3,
    "美容": 3, "ファッション": 3, "旅行": 3, "ダンス": 3,
    "Vlog": 3, "ゲーム": 2, "ストリーマー": 3, "フード": 2,
    "コメディ": 3, "お笑い": 3, "企画": 3, "チャレンジ": 3,
    "挑戦": 3, "慈善": 4, "寄付": 4, "基金": 4, "グループ": 2,
    "メディア": 2, "作品": 2, "活動": 2, "パイオニア": 5,
    "創設者": 4, "共同創設者": 5, "受賞": 5, "世界一": 5,
    "殿堂": 4,
}
YOUTUBER_ACHIEVEMENT = re.compile(
    r"受賞|パイオニア|世界一|共同創設者|創設者|優勝|記録|選出|賞"
)
YOUTUBER_ROLE = re.compile(
    r"YouTuber|ユーチューバー|VTuber|バーチャルYouTuber|ゲーム実況者|配信者"
)
YOUTUBER_GENERIC_ROLE_TEXT = (
    r"バーチャルYouTuber|YouTuber|ユーチューバー|VTuber"
)
YOUTUBER_GEO_HEAD = re.compile(
    r"^(?:日本|アメリカ(?:合衆国)?|カナダ|イギリス|イングランド|ウェールズ|"
    r"アイルランド|スウェーデン|スペイン|フランス|ドイツ|イタリア|"
    r"ポルトガル|オランダ|ベルギー|ノルウェー|フィンランド|デンマーク|"
    r"ポーランド|チェコ|ルーマニア|ハンガリー|ウクライナ|ロシア|トルコ|"
    r"イスラエル|キプロス|韓国|大韓民国|中国|台湾|タイ|フィリピン|"
    r"インドネシア|インド|オーストラリア|ニュージーランド|アルゼンチン|"
    r"ブラジル|メキシコ|コロンビア|ベネズエラ|エジプト|ナイジェリア|"
    r"南アフリカ)"
)
YOUTUBER_SIMPLE_GEO_PREFIX = re.compile(
    YOUTUBER_GEO_HEAD.pattern + r"(?:人)?の"
)
YOUTUBER_NOT_OWNED = re.compile(r"師事|師匠|弟子入り")
YOUTUBER_INCOMPLETE_TAIL = re.compile(
    r"(?:となり|しており|であり|しつつ|など|等|および|または)$"
)


def _remove_youtuber_metadata(s: str) -> str:
    """説明文からカードの別列と重複する所属・個人情報を取り除く。"""
    ending = "。" if s.endswith("。") else ""
    core = s[:-1] if ending else s
    # 「東京都出身の〜」「〜生まれ」のような修飾だけを落とし、職業部分は残す。
    core = re.sub(r"[^、。]{0,24}(?:出身|生まれ)(?:の)?[、 ]*", "", core)
    # 所属先・運営会社はorg列にあるので、役割だけ残す。
    core = re.sub(r"^[^、。]{0,120}(?:に)?所属(?:する|の)", "", core)
    core = re.sub(r"^[^、。]{0,120}が運営する", "", core)
    parts = [part.strip() for part in core.split("、")]
    parts = [part for part in parts
             if part and not YOUTUBER_ORG.search(part)
             and not YOUTUBER_PERSONAL.search(part)]
    if not parts:
        return ""
    return "、".join(parts) + ending


def _strip_redundant_youtuber_lead(s: str) -> str:
    """カード種別と重複する「日本のYouTuber、」等の書き出しを落とす。"""
    # 地域・国籍が文頭にあり、そのまま一般的なYouTuber肩書きへ続く場合だけ
    # 地域部分を除く。実績文の末尾にある「日本のYouTuber」は対象外にする。
    first_clause = s.split("。", 1)[0]
    geo = YOUTUBER_SIMPLE_GEO_PREFIX.match(s)
    if geo and YOUTUBER_ROLE.search(first_clause):
        s = s[geo.end():]
    else:
        # 「韓国人男性YouTuber」のように「の」を挟まない単純な国籍表現。
        geo_person = re.match(
            YOUTUBER_GEO_HEAD.pattern
            + rf"人(?=(?:男性|女性)?(?:{YOUTUBER_GENERIC_ROLE_TEXT}))",
            s,
        )
        if geo_person:
            s = s[geo_person.end():]

    role = re.match(
        rf"^(?:男性|女性)?(?:{YOUTUBER_GENERIC_ROLE_TEXT})(?:グループ)?"
        rf"(?:（(?P<detail>[^）]{{1,80}})）)?"
        rf"(?:(?P<join>、|・|および|及び|兼|と)|(?P<end>である。|。)|$)",
        s,
    )
    if not role:
        return s

    detail = (role.group("detail") or "").strip()
    # 「以下、VTuber」は略記の宣言なので説明には使わない。一方、
    # 「ゲーム実況者、ストリーマー」のような活動区分は有用なので残す。
    if detail.startswith("以下") or not re.search(
            r"ゲーム実況者|ストリーマー|ビデオブロガー|動画配信者|配信者", detail):
        detail = ""
    rest = s[role.end():].lstrip("、・ ")
    parts = [part for part in (detail, rest) if part]
    if not parts:
        return ""
    result = "、".join(parts)
    if not result.endswith("。"):
        result += "。"
    return result


def _youtuber_piece(sentence: str, name: str) -> str:
    """記事冒頭の1文を、単独表示できる短い候補に整える。"""
    s = clean_ws(sentence).strip("、 ")
    if not s:
        return ""
    # 肩書きに挟まる「（登録者80万人）」などは括弧ごと除く。
    s = re.sub(
        r"[（(][^）)]{0,80}(?:登録者|フォロワー|再生回数|視聴回数|動画再生)"
        r"[^）)]{0,80}[）)]", "", s,
    )
    # 「合計登録者70万人超えのサラリーマンYouTuber」のように、時変値が
    # 肩書きの前置修飾になっている場合は修飾だけ落とす。
    s = re.sub(
        r"(?:合計)?(?:チャンネル)?登録者(?:数)?[^、。]{0,24}?の"
        r"(?=[^、。]{2,})", "", s,
    )
    # それでも時変情報が残る文は、数値を主題にした実績文である可能性が高い。
    # 一部だけ切ると「10年の活動の中で。」のような断片になるため文ごと使わない。
    if YOUTUBER_DYNAMIC.search(s):
        return ""
    # 記事名が句点で終わる場合、匿名化後に助詞だけが残ることがある。
    s = re.sub(r"^(?:は|が|を)[、 ]+", "", s)
    # 時変値入りの括弧を削ったことで隣接した肩書きを、読みやすい列挙に戻す。
    s = re.sub(
        r"(TikToker|YouTuber|VTuber)"
        r"(?=(?:YouTuber|VTuber|インフルエンサー|アーティスト))",
        r"\1、", s,
    )
    s = strip_name_prefix(s if s.endswith("。") else s + "。", name).strip()
    # 共通のstrip_name_prefixは、動詞で終わる長い文を壊さないため保守的に
    # 何もしない場合がある。カードでは名前が別表示されるため、冒頭の主語は
    # それより広く落として単独文にする。
    lead = re.match(r"^(.{2,40}?)は[、 ]+", s)
    if lead and len(s[lead.end():].strip("。 ")) >= 4:
        s = s[lead.end():].lstrip("、 ")
    if name and s.startswith(name):
        s = s[len(name):].lstrip("、 ")
    # 「ミスタービーストとして知られる〜」のような活動名の導入は、
    # カード上では名前が別に出るので落とす。
    if name and name != "NA":
        name_re = re.escape(name.replace(" ", "").replace("　", ""))
        s = re.sub(name_re + r"として(?:も|オンラインで)?(?:よく)?知られている", "", s)
        s = re.sub(name_re + r"として知られる", "", s)
    # 記事名の表記ゆれ・改名・リダイレクトでも、活動名の説明だけを残す。
    s = re.sub(
        r"^(?:一般的には)?[^、。]{1,80}?として(?:も|オンラインで)?"
        r"(?:よく)?知られている(?:が、|、| )?", "", s)
    s = re.sub(
        r"^(?:一般的には)?[^、。]{1,80}?として(?:も|オンラインで)?"
        r"(?:よく)?知られる(?:が、|、| )?", "", s)
    s = re.sub(r"^[^、。]{2,80}(?:（[^）]{0,100}）)?による", "", s)
    s = YOUTUBER_CONTEXT.sub("", s)
    s = re.sub(r"^(?:彼|彼女|本人|同氏)は(?:また)?[、 ]*", "", s)
    s = re.sub(r"彼女?は|彼女?が", "", s)
    s = s.replace("同事務所の", "").replace("同事務所", "")
    s = re.sub(r"彼女?の", "", s)
    s = re.sub(r"^同(?:市|県|社|グループ|チャンネル)[^、。]{0,20}", "", s)
    s = re.sub(r"同(?:市|県|社|グループ|チャンネル)", "", s)
    if "であり、彼は" in s or "であり、彼女は" in s:
        s = re.split(r"であり、(?:彼|彼女)は", s, maxsplit=1)[-1]
    s = s.replace("知られており", "知られている")
    s = re.sub(r"で知られ。$", "で知られている。", s)
    s = re.sub(r"活動する他。$", "活動している。", s)
    # 「〜しており、」「〜であり、」の後ろは別文脈になりやすいので、
    # 前半を自然な完結文にする。
    for needle, replacement in (("おり", "いる"), ("であり", "である")):
        pos = s.find(needle)
        if pos >= 0:
            tail = s[pos + len(needle):]
            if tail.startswith("、") or "、" in tail:
                s = s[:pos] + replacement + "。"
                break
    s = _remove_youtuber_metadata(s)
    s = _strip_redundant_youtuber_lead(s)
    if not s:
        return ""
    if "スケッチ・コメディのグループ" in s:
        s = "スケッチ・コメディのグループ。"
    elif "YouTubeに動画を投稿" in s and "アーティスト" in s:
        s = "YouTubeに動画を投稿するアーティスト。"
    if s.endswith("など。") and "に関する" in s:
        s = s[:s.find("など。")].rstrip("、 ") + "に関するYouTubeチャンネル。"
    # グループ所属の前置きより、後半にある個人チャンネルの内容を優先する。
    s = re.sub(
        r"^YouTuberとしては[^。]{1,120}?として活動する他、", "", s,
    )
    # 冒頭文に長い列挙があるときは、活動の主節だけを残す。
    compact = re.search(
        r"([^、。]{4,60})(?:を中心に活動している|を投稿している|"
        r"を配信している|で知られている|で知られており)", s)
    if compact and len(compact.group(0)) + 1 <= YOUTUBER_DESC_MAX:
        s = compact.group(0) + "。"
    if len(s) > YOUTUBER_DESC_MAX:
        group = re.search(
            r"(?P<group>[^、。]{0,30}グループ[「『][^」』]+[」』])"
            r"(?:の)?(?P<role>メンバー|リーダー)", s)
        if group:
            s = f"{group.group('group')}の{group.group('role')}。"
    s = _sanitize_desc(s).strip()
    if s and not s.endswith("。"):
        s += "。"
    if s and YOUTUBER_INCOMPLETE_TAIL.search(s[:-1]):
        return ""
    return s


def _cut_youtuber_description(s: str) -> str:
    """長すぎる候補を読点境界で短くする(中途半端な語尾を避ける)。"""
    def finish_tail(value: str) -> str:
        value = re.sub(r"で知られ。$", "で知られている。", value)
        value = re.sub(r"活動する他。$", "活動している。", value)
        return value

    if len(s) <= YOUTUBER_DESC_MAX:
        return finish_tail(s)
    core = s[:-1] if s.endswith("。") else s
    pos = core[:YOUTUBER_DESC_MAX].rfind("、")
    while pos >= 24:
        candidate = core[:pos].rstrip()
        # 「〜で、」「〜に、」のような助詞の直後で切ると完結文にならない。
        if candidate.endswith(("など", "等")):
            return candidate[:-2].rstrip("、 ") + "に関するYouTubeチャンネル。"
        if not candidate.endswith(("で", "に", "を", "の", "が", "は", "と", "も", "へ", "や")) \
                and not YOUTUBER_INCOMPLETE_TAIL.search(candidate):
            return finish_tail(candidate + "。")
        pos = core[:pos].rfind("、")
    # 安全な読点境界が無い場合は、多少長くても完結文を保つ。
    return finish_tail(s)


def make_youtuber_description(intro: str, wd_desc: str = "", name: str = "") -> str:
    """YouTuber/VTuberの活動内容を優先した短い完結説明を作る。

    目安50字、上限65字。先頭の肩書きだけでなく、動画・配信・ゲーム実況・
    音楽・慈善活動などを含む文を優先する。登録者数、所属、出身地、家族関係は
    別列または説明として不要なので採らない。記事冒頭が使えない場合は
    Wikidataのja descriptionへフォールバックする。
    """
    text = deidentify(intro, name)
    sentences = [part.strip() for part in re.split(r"(?<=。)", text) if part.strip()]
    pieces = [_youtuber_piece(part, name) for part in sentences]
    pieces = [part for part in pieces if part]
    if not pieces:
        fallback = safe_wd_desc(wd_desc)
        pieces = [_youtuber_piece(fallback, name)] if fallback else []
        pieces = [part for part in pieces if part]
    if not pieces:
        return "NA"

    def score(item):
        index, sentence = item
        value = sum(weight * sentence.count(term)
                    for term, weight in YOUTUBER_ACTIVITY.items())
        if YOUTUBER_ACHIEVEMENT.search(sentence):
            value += 4
        if YOUTUBER_ROLE.search(sentence):
            value += 1
        if index == 0:
            value += 2
        elif len(sentence) > YOUTUBER_DESC_MAX:
            value -= 2
        if index > 0 and re.search(r"\d{4}年|活動休止|休止状態", sentence) \
                and not YOUTUBER_ACHIEVEMENT.search(sentence):
            value -= 4
        if YOUTUBER_NOT_OWNED.search(sentence):
            value -= 6
        return value, -index

    first = pieces[0]
    best = max(enumerate(pieces), key=score)[1]
    # 「日本のYouTuber。」のような短い肩書きは、活動文と一緒にしても
    # 65字以内なら残す。長いときは活動内容だけを優先する。
    if best != first and YOUTUBER_ROLE.search(first) \
            and len(first) + len(best) <= YOUTUBER_DESC_MAX:
        return first + best
    return _cut_youtuber_description(best)


def parse_entry(title: str, text: str):
    """記事名と冒頭文から (original, [(surface, pronunciation, type), ...]) を
    返す。読みが機械決定できなければ None(要確認)。"""
    name = DISAMBIG.sub("", title)
    text = (text or "").replace("　", " ")
    parsed = parse_person(name, text)
    if parsed:
        f_s, f_y, g_s, g_y, full_s, full_y, _reg = parsed
        original = full_s.replace(" ", "")
        rows = []
        if f_s and f_s != original:
            rows.append((f_s, f_y, "family"))
            rows.append((g_s, g_y, "given"))
        rows.append((original, full_y.replace(" ", ""), "full"))
        return original, rows
    plain = name.replace("　", "").replace(" ", "")
    if KANA_ONLY.match(plain):  # かなハンドル名は自身が読み
        yomi = plain.replace("＝", "・").translate(HIRA2KATA)
        return plain, [(plain, yomi, "full")]
    # 漢字・ラテン文字等のハンドル名: 冒頭「名前（よみ、」「名前（よみ）」から抽出
    lead = text.replace(" ", "")
    m = re.match(re.escape(plain) + r"[（(](" + YOMI + r")[、，,）)]", lead)
    if m:
        yomi = m.group(1).translate(HIRA2KATA)
        return plain, [(plain, yomi, "full")]
    return None


def norm(title: str) -> str:
    """既存 original との照合キー(曖昧回避サフィックス除去+空白除去)。"""
    return DISAMBIG.sub("", title).replace("　", "").replace(" ", "")


def build_list(csv_name: str | tuple[str, ...], specs: list, cache_env: str,
               excluded: set = frozenset(),
               excluded_occs: dict = None) -> int:
    """リストを生成(初回)または追記・status更新(2回目以降)する。

    specs: category ごとの取得仕様
      {category, occ, must, must_not, exclude, guard} の dict のリスト。
    excluded: 収録しないja記事名(norm()済み)の集合。P106の誤登録や、別業種の
      著名人が公式チャンネルを持つだけのケースを恒久的に弾く。
    excluded_occs: 収録しない職業の QID -> ラベル。P106 にこの職業を持つ人物を
      属性ごと弾く。値はラベルの期待キーワード(QID取り違えのフェイルセーフ)。
    """
    root = Path(__file__).resolve().parent.parent
    split_paths = (tuple(root / name for name in csv_name)
                   if isinstance(csv_name, tuple) else None)
    csv_path = root / csv_name if split_paths is None else None
    for s in specs:
        assert_occupation(s["occ"], s["must"], s["must_not"])
        if s.get("exclude"):
            assert_occupation(s["exclude"], ("youtuber", "ユーチューバー"), ())
    for qid, label in (excluded_occs or {}).items():
        assert_occupation(qid, (label,), ())

    cache = os.environ.get(cache_env)  # 開発用: 取得結果の pickle キャッシュ先
    if cache and Path(cache).exists():
        with open(cache, "rb") as fh:
            persons_by_cat, attrs, extracts = pickle.load(fh)
        print(f"キャッシュから読み込み: {cache}", flush=True)
    else:
        persons_by_cat = {}
        for s in specs:
            persons = fetch_persons(s["occ"], s.get("exclude"), excluded_occs)
            lo, hi = s["guard"]
            if not lo <= len(persons) <= hi:
                print(f"error: implausible count for {s['category']}: "
                      f"{len(persons)}")
                return 1
            persons_by_cat[s["category"]] = persons
        qids = sorted(set().union(*persons_by_cat.values()))
        attrs = fetch_attrs(qids)
        titles = sorted({t for p in persons_by_cat.values()
                         for t in p.values()})
        print(f"記事冒頭を取得中... {len(titles)}件", flush=True)
        # 活動内容を含む後続文も選べるよう、通常の人名リストより長く取る。
        extracts = fetch_extracts(titles, limit=600)
        if cache:
            with open(cache, "wb") as fh:
                pickle.dump((persons_by_cat, attrs, extracts), fh)
            print(f"キャッシュ保存: {cache}", flush=True)

    if split_paths is not None:
        cols, old_rows = read_creator_csvs(split_paths)
        cols += [c for c in COLS if c not in cols]
    elif csv_path.exists():
        with csv_path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            old_rows = list(reader)
            # 他のスクリプトが足した付加列(image/image_page/wikidata: ADR 00018)を
            # 落とさない。新規行は空にしておき、enrich 側が後から埋める
            cols = list(reader.fieldnames or COLS)
        # 後から増えた付加列(channel/description: ADR 00029)は既存の列順を崩さず
        # 末尾に足す。利用側は列名で読むので位置は問わない
        cols += [c for c in COLS if c not in cols]
    else:
        old_rows, cols = [], list(COLS)
    existing = {r["original"] for r in old_rows}
    next_id = max((int(r["id"]) for r in old_rows), default=-1) + 1

    # 記事タイトル -> description(活動内容を優先した短い完結文)。
    descs = {t: make_youtuber_description(
                 extracts.get(t, ""), attrs.get(q, {}).get("wd_desc"), norm(t))
             for persons in persons_by_cat.values()
             for q, t in sorted(persons.items())}
    wd_attrs = {norm(t): {**attrs.get(q, {}), "description": descs[t]}
                for persons in persons_by_cat.values()
                for q, t in sorted(persons.items())}

    # 既存行の status 一方向更新(current -> former のみ。手動修正は上書きしない)
    turned = set()
    for r in old_rows:
        if r.get("status") == "current" and \
                wd_attrs.get(r["original"], {}).get("status") == "former":
            r["status"] = "former"
            turned.add(r["original"])
    if turned:
        print(f"status更新(current→former): {len(turned)}人", flush=True)

    # 既存行の付加列は空欄補完のみ(ADR 00014)。入っている値は取得結果が違っても
    # 書き換えない。channel/description は新設列なので実質全行が補完対象になる
    backfill = ("org", "debut_year", "channel", "description")
    filled = {c: set() for c in backfill}
    for r in old_rows:
        got = wd_attrs.get(r["original"], {})
        for col in backfill:
            new = got.get(col, "NA")
            if r.get(col, "NA") in ("", "NA") and new not in ("", "NA"):
                r[col] = new
                filled[col].add(r["original"])
        # 照合できなかった行の新設列は空ではなく NA にする(列の意味を揃える)
        for col in NEW_COLS:
            if not r.get(col):
                r[col] = "NA"
    for col, names in filled.items():
        if names:
            print(f"{col} の空欄補完: {len(names)}人", flush=True)

    added, flagged = [], []
    entries = [(title, cat, qid)
               for cat, persons in persons_by_cat.items()
               for qid, title in persons.items()
               if norm(title) not in excluded]
    hit = {norm(t) for persons in persons_by_cat.values()
           for t in persons.values()} & set(excluded)
    print(f"候補 {len(entries)}件 (EXCLUDED で除外 {len(hit)}件)", flush=True)
    # 記事名が変わると除外が効かなくなり、静かに再追加されてしまうので気付けるようにする
    stale = sorted(set(excluded) - hit)
    if stale:
        print(f"注意: EXCLUDED に未ヒットの項目 {len(stale)}件"
              "(記事改名/P106変更で対象外になった可能性): "
              + ", ".join(stale[:20]), flush=True)

    for title, cat, qid in sorted(entries):
        parsed = parse_entry(title, extracts.get(title, ""))
        if parsed is None:
            flagged.append(title)
            continue
        original, rows = parsed
        if "," in original or '"' in original:  # CSVパーサを壊す名前は収録しない
            flagged.append(title)
            continue
        if original in existing:
            continue
        existing.add(original)
        a = attrs.get(qid, {})
        for surface, pron, typ in rows:
            added.append({**{c: "" for c in cols},
                          "id": str(next_id), "original": original,
                          "surface": surface, "pronunciation": pron,
                          "type": typ, "category": cat,
                          "org": a.get("org", "NA"),
                          "debut_year": a.get("debut_year", "NA"),
                          "status": a.get("status", "current"),
                          "channel": a.get("channel", "NA"),
                          "description": descs.get(title, "NA")})
        next_id += 1

    if split_paths is not None:
        write_creator_csvs(cols, old_rows + added, split_paths)
    else:
        write_csv_no_trailing_newline(csv_path, cols, old_rows + added)

    n_people = len({r["id"] for r in added})
    print(f"\n{csv_name}: 既存{len(old_rows)}行 + 新規{n_people}人({len(added)}行) "
          f"= {len(old_rows) + len(added)}行", flush=True)
    all_rows = old_rows + added
    ids = {r["id"] for r in all_rows}
    for col in NEW_COLS + ["org", "debut_year"]:
        have = [r for r in all_rows if r.get(col) not in ("", "NA", None)]
        print(f"{col} 充足: {len(have)}/{len(all_rows)}行 "
              f"({len({r['id'] for r in have})}/{len(ids)}人)", flush=True)
    print(f"要確認(読み機械決定不能) {len(flagged)}件", flush=True)
    for t in flagged[:50]:
        print(f"  要確認: {t}", flush=True)
    return 0
