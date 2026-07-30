#!/usr/bin/env python3
"""physicist.csv を広義の「科学者」リスト scientist.csv に置き換え・拡張する。

出典: Wikidata(職業P106が物理/化学/数学/天文/生物/計算機科学/地学のいずれか,
sitelinks>=20 ≒ 多言語版20版以上に記事がある著名層)と、Wikipedia日本語版記事
の冒頭文(CC BY-SA 4.0)。

- 旧 physicist.csv の全行(id/original/surface/pronunciation/type/image/image_page)
  はそのまま引き継ぎ、新列 field/era/birth_year/nobel/gender/country/status を付与
- 未収録の著名科学者を追記(読み・姓名分割は update_physicist.py と同じ方式)
- 既存行の読み・id・表記は絶対に書き換えない
- 既存行の付加列は**空欄/NAの補完のみ**行い、既に埋まっている値は書き換えない
  (例外は status の 存命→物故 のみ。死没は不可逆なので反映する)。Wikidata の
  ラベル揺れ・記事冒頭の改稿を毎回取り込むと、月次PRが既存行の書き換えだらけに
  なり、レビューで本当の追記が埋もれるため(ADR 00014)

新列(詳細は docs/adr/00009):
- field:   分野(物理/化学/数学/天文学/生物学/計算機科学/地学)を優先順で並べた
  単一列のスラッシュ区切り多値(例 物理/数学)。切り詰めなし、無ければNA。
  ソラミミック側の部分一致演算子 field~=物理 で1列のまま絞れる前提
- era:     時代区分(古代/中世/近世/近代/現代/NA)。生年basis
- birth_year: 西暦生年(紀元前は「前287」形式、不明はNA)
- nobel:   科学系ノーベル賞受賞者か(yes/no、既存で照合不能はNA)
- gender:  男性/女性/その他/NA
- country: 市民権のある国の日本語ラベル(複数は"/"、不明はNA)
- status:  物故/存命/NA
- description: 主な業績の短い完結文(記事冒頭の先頭生没年カッコと冒頭の
  「{人名}は、」を除去し、「。」区切りで完結文を目安90字まで連結。なければ
  Wikidataのja description、どちらも無ければNA。ASCIIカンマ・二重引用符は除去、
  常に「。」で終わる)

環境変数 SCIENTIST_CACHE を指定すると、Wikidata/Wikipedia の取得結果(属性
attrs と記事冒頭 extracts)をそのパスに pickle キャッシュし、2回目以降は再取得
せず読み込む(開発用。CI では未設定=常に再取得)。

usage: python3 tools/update_scientist.py
"""

import csv
import datetime
import os
import pickle
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import (DISAMBIG, KATA2HIRA, KATAKANA, fetch_extracts,
                     make_description, parse_person, sparql,
                     write_csv_no_trailing_newline)

OLD_CSV = Path(__file__).resolve().parent.parent / "physicist.csv"
NEW_CSV = Path(__file__).resolve().parent.parent / "scientist.csv"
MIN_SITELINKS = 20
CURRENT_YEAR = datetime.date.today().year
CACHE = os.environ.get("SCIENTIST_CACHE")  # 開発用: 取得結果の pickle キャッシュ先
# description の生成(make_description)は wpnames に置いて youtuber と共用する

# 対象職業(P106)→ 日本語フィールドラベル。並び順が field の安定した出力順。
OCCUPATIONS = [
    ("Q169470", "物理"),
    ("Q593644", "化学"),
    ("Q170790", "数学"),
    ("Q11063", "天文学"),
    ("Q864503", "生物学"),
    ("Q82594", "計算機科学"),
    ("Q520549", "地学"),
]
FIELD_ORDER = {label: i for i, (_, label) in enumerate(OCCUPATIONS)}

# 対象外にする人物(norm() 済みの記事名 = CSV の original と同じキー)。
# P106 に上表の職業が付いているが、実際には研究職・研究業績がなく著名性が
# 完全に他分野にある人物。放置すると毎回の自動更新で再追加されるためここで
# 恒久的に除外する。増やすときは「科学の業績・経歴で著名か」を基準に、
# 兼業でも科学者としての実績が実在するなら**残す**こと
# (例: サハロフ=物理学者+反体制活動家、スティーブン・チュー=物理学者+長官)。
EXCLUDED = {
    # 架空の人物(実在しない。架空側は fictional_scientist.csv が担当)
    "エメット・ブラウン",  # 『バック・トゥ・ザ・フューチャー』の架空の人物(ドク・ブラウン)
    "ゴードン・フリーマン",  # ゲーム『ハーフライフ』の主人公である架空の理論物理学者
    "ヤーラ・チムルマン",  # チェコの劇作家ズデニェク・スヴェラークが考案した架空の人物
    "ベイン",  # DCコミックス『バットマン』の架空のスーパーヴィラン
    "ヘンリー・ピム",  # マーベル・コミックの架空のキャラクター(アントマン)
    "ジョーカー",  # DCコミックス『バットマン』の架空のスーパーヴィラン
    "スケアクロウ",  # DCコミックス『バットマン』の架空のスーパーヴィラン
    "ジェームズ・モリアーティ",  # 『シャーロック・ホームズ』の架空の人物
    "シルバーサーファー",  # マーベル・コミックの架空のスーパーヒーロー
    "リザード",  # 『スパイダーマン』の架空のスーパーヴィラン
    "レックス・ルーサー",  # 『スーパーマン』の架空のスーパーヴィラン
    # 政治家・軍人(科学は学位/専攻どまりで研究職・研究業績がない)
    "アンドリュス・クビリュス",  # 物理学は学位のみ。1988年以降は一貫してリトアニアの政治家
    "オスカー・ラフォンテーヌ",  # 学位論文のみで研究職に就かず。ドイツの政治家として著名
    "カジミェシュ・マルチンキェヴィチ",  # 研究業績の記載なし。ポーランド首相を務めた政治家
    "ゲンナジー・ジュガーノフ",  # 研究業績なし。ロシア連邦共産党党首としての政治活動で著名
    "ジョサイア・バートレット",  # 18世紀の医師・政治家。自然科学の研究業績なし
    "ズラブ・ノガイデリ",  # 研究業績なし。ジョージア首相としての政治活動で著名
    "ダヴィト・バクラゼ",  # 軍人・外交官・政治家。物理学者としての実績は確認できず
    "フリードリヒ・アドラー",  # 32歳で研究を放棄。社会主義運動家・政治家として著名
    "ボリス・ネムツォフ",  # 論文等の業績なし。ロシアの政治家・活動家として著名
    "ライナー・ハーゼロフ",  # 研究業績の記載なし。ザクセン＝アンハルト州首相
    "ラージナート・シン",  # 研究業績なし。インド人民党の政治家として著名
    "ヴァルディス・ドンブロウスキス",  # 具体的な研究業績なし。ラトビア首相として著名
    "ジョン・マグフリ",  # 論文等の業績なし。タンザニア大統領として著名
    "エリオ・ディルポ",  # 化学に関する記述なし。ベルギー首相を務めた政治家
    "ロベルト・ライ",  # 研究業績なし。ナチ党ドイツ労働戦線総裁として著名
    "イオナ・ヤキール",  # 化学との関連なし。ソ連の軍人・政治家
    "アンドルス・アンシプ",  # 研究業績なし。エストニア首相として著名
    "フリッツ・クーン",  # 研究業績なし。ドイツ系アメリカ人のナチ系政治活動家
    "マックス・エルヴィン・フォン・ショイブナー＝リヒター",  # 化学は学生時代のみ。外交官・ナチ党幹部として著名
    "エレナ・チャウシェスク",  # 化学博士号に論文代筆疑惑。独裁者夫人としての政治的地位で著名
    "マーガレット・ベケット",  # 研究実績の記載なし。イギリス労働党の政治家
    "テレーズ・コフィー",  # 化学PhDのみで研究職歴なし。イギリス保守党の政治家
    "グエン・ミン・チエット",  # 数学は専攻のみ。ベトナム国家主席として著名
    "マヌエル・プラド・イ・ウガルテチェ",  # 数学に関する記述なし。中央銀行総裁・ペルー大統領
    "トゴン・テムル",  # 天文学に関する記述なし。元朝最後の皇帝
    "ライモンツ・ヴェーヨニス",  # 生物学部卒業後は高校教師を経て政治家。ラトビア大統領
    "ズラブ・ジワニア",  # 具体的研究実績なし。ジョージア首相として著名
    "ヌツ・モヘレ",  # 科学研究の実績の記載なし。レソト首相を歴任した政治家
    "サスキア・エスケン",  # ソフトウェア開発職歴のみ。ドイツ社会民主党党首として著名
    "チェルシー・マニング",  # 科学者としての実績記載なし。元陸軍軍人・内部告発者
    "温家宝",  # 地質学の論文等の研究実績なし。中国首相として著名
    # 実業家・起業家・投資家(同上)
    "デイビッド・コーク",  # 研究実績の記録なし。実業家・政治活動家・慈善家として著名
    "ヴィクトル・ヴェクセリベルク",  # 早期に実業へ転身。ロシアの石油ガス実業家として著名
    "マリッサ・メイヤー",  # 学術論文等の記載なし。Yahoo!元CEOの実業家
    "ビル・ゲイツ",  # 計算機科学の学術研究・論文の記載なし。マイクロソフト創業者
    "スティーブ・ジョブズ",  # 技術研究ではなく製品ビジョンで評価。Apple共同創業者
    "スンダー・ピチャイ",  # 計算機科学の研究実績の記載なし。Google/Alphabet CEO
    "ニクラス・ゼンストローム",  # 学術研究実績の記載なし。Kazaa・Skype創業の起業家
    "キム・ドットコム",  # 学術的な研究実績の記載なし。MEGAUPLOAD等を興した実業家
    "馬化騰",  # 学術論文等の研究実績の記載なし。テンセント創業者
    "サティア・ナデラ",  # 計算機科学の学術研究実績の記載なし。マイクロソフトCEO
    "マット・マレンウェッグ",  # 計算機科学の学位・研究実績なし。WordPress開発の実業家
    "パーヴェル・ドゥーロフ",  # 哲学科卒で計算機科学の研究実績なし。VK・Telegram創業者
    "ポール・アレン",  # 学術的研究実績の記載なし。マイクロソフト共同創業者
    "カルロス・スリム",  # 著名性は実業家・富豪として。メキシコのコングロマリット所有者
    "エヴァン・シュピーゲル",  # 技術開発は共同創業者が担当し研究実績なし。Snap Inc. CEO
    "スティーブ・バルマー",  # 研究実績ではなく経営手腕で著名。マイクロソフト元CEO
    "スティーブ・シャーリー",  # 著名性はソフトウェア企業創業者・慈善家として
    "マイケル・デル",  # 計算機科学の学術研究実績の記載なし。デル創業者
    "マーク・シャトルワース",  # 査読論文・研究職の実績なし。Thawte創業などの実業家
    "シェリル・サンドバーグ",  # 研究実績なし。Facebook COO等の経営者・著作家
    "ティム・クック",  # 学術研究実績なし。Apple CEOの経営者
    "ジェンスン・フアン",  # 個人の研究論文の記録なし。NVIDIA創業者・CEO
    "ジェフ・ベゾス",  # 科学研究実績なし。Amazon創業者の実業家
    "エドゥアルド・サベリン",  # 研究実績の記載なし。Facebook共同創業者の起業家・投資家
    "デビッド・ファイロ",  # 博士課程中退・研究論文なし。Yahoo!共同創業者
    "アダム・オズボーン",  # 化学工学の博士号はあるが研究職歴なし。実業家・著述家
    "マイク・マークラ",  # 研究実績なし。Apple第2代社長を務めた投資家・経営者
    "クリス・ヒューズ",  # 研究実績なし。Facebook共同創業者の起業家
    "スティーブ・チェン",  # 研究実績の記載なし。YouTube共同創業者・元CTO
    "クリストファー・プール",  # 学位・学術研究の記載なし。4chan創設者の起業家
    "ショーン・パーカー",  # 研究実績の記載なし。Napster共同設立・Facebook初代CEO
    "ジャック・ドーシー",  # 大学中退で学術研究実績なし。Twitter/Square創業の起業家
    "アラン・シュガー",  # 科学研究実績の記載なし。アムストラッド創業の実業家
    "ピーター・ティール",  # 専門は哲学・法律で科学研究実績なし。PayPal/Palantir創業者
    "郭台銘",  # 科学研究実績なし。フォックスコン創業の実業家
    "ビズ・ストーン",  # 大学中退で研究実績の記載なし。Twitter共同創業者
    "エヴァン・ウィリアムズ",  # 大学中退で研究実績なし。Blogger/Twitter/Medium創業者
    # 俳優・歌手・スポーツ選手・作曲家・ゲームクリエイター(同上)
    "ドルフ・ラングレン",  # 化学工学修士のみ(MITは3週間で中退)。俳優・格闘家として著名
    "ティム・ラス",  # 科学分野の学位・研究実績は確認できず。俳優・プロデューサー
    "スヴャトスラフ・ヴァカルチュク",  # 物理学PhDのみ。ウクライナの歌手・バンドリーダーとして著名
    "リーア・ルイス",  # 計算機科学との関わりの記載なし。アメリカの女優・声優
    "ヨジー・バーテル",  # 化学の実績記述なし。五輪陸上金メダリスト・運輸相
    "マルタ・トレホン",  # 研究実績の記載なし。スペインの女子サッカー選手
    "ミルトン・バビット",  # 学生時代に数学専攻。作曲家・音楽理論家として著名
    "ティンクトーリス",  # 数学的著作の記述なし。ルネサンス音楽の理論家・作曲家
    "エディソン・デニソフ",  # 転向前に数学専攻のみ。ソ連の作曲家として著名
    "ヨハン・クーナウ",  # 数学の著作・研究の記述なし。バロック音楽の作曲家
    "ステファン・ヒーレンバーグ",  # 海洋生物学の指導歴3年のみ。『スポンジ・ボブ』のアニメーター
    "アーノルド・ファンク",  # 地質学博士号取得後は研究職に就かず。山岳映画の監督
    "宮本茂",  # 工業デザイン専攻。任天堂のゲームプロデューサー
    "桜井政博",  # 科学研究実績なし。『星のカービィ』等のゲームクリエイター
    "坂口博信",  # 科学研究実績なし。『ファイナルファンタジー』のゲームクリエイター
    "小島秀夫",  # 科学者としての実績記載なし。『メタルギア』のゲームクリエイター
    "トッド・ハワード",  # 研究実績の記載なし。『Elder Scrolls』のゲームデザイナー
    "稲船敬二",  # 研究実績の記載なし。『ロックマン』のゲームクリエイター
    # 作家・詩人・ジャーナリスト・科学ライター(同上)
    "ウィリー・レイ",  # 研究職歴・論文なし。ロケット工学の科学ライターとして著名
    "パオロ・ジョルダーノ",  # 素粒子物理学PhDのみ。ストレーガ賞受賞の小説家として著名
    "ラフィク・シャミ",  # 化学PhD取得後すぐ作家に専念。ドイツ語作家として著名
    "マルク・アルダーノフ",  # 化学研究の記述なし。歴史小説の亡命作家として著名
    "ラリー・ニーヴン",  # 研究職に就かず。SF作家『リングワールド』で著名
    "レーモン・クノー",  # 研究実績なし。『地下鉄のザジ』等の小説家・詩人
    "ソル・フアナ＝イネス・デ・ラ・クルス",  # 数学の実績記述なし。スペイン黄金世紀の詩人・修道女
    "エルヴェ・ル・テリエ",  # 学位・研究の記述なし。ゴンクール賞受賞の小説家
    "リュドミラ・ウリツカヤ",  # 遺伝学研究所勤務2年で解雇。以後はロシアの小説家として著名
    "ニコロ・アンマニーティ",  # 生物学との関わりの記載なし。イタリアの小説家
    "ザラ・キルシュ",  # 生物学の学士のみで研究職に就かず。ドイツの詩人
    "ファーレイ・モウワット",  # 動物学は専攻のみで学位未取得。カナダの作家
    "スチュアート・ブランド",  # 生物学研究の実績の記載なし。雑誌編集者・思想家
    "アンディ・ウィアー",  # CS課程を中退。小説『火星の人』の作者として著名
    "セス・ゴーディン",  # 計算機科学の研究実績なし。マーケティング分野の著作家
    "テッド・チャン",  # 論文・発見の実績なし。テクニカルライター・SF作家
    "リディア・マリア・チャイルド",  # 科学者としての実績記載なし。奴隷解放運動家・小説家
    "ミホ・モスリシュヴィリ",  # 具体的研究実績なし。ジョージアの小説家・脚本家
    "トーマス・カーライル",  # 数学者としての活動記録なし。歴史家・評論家として著名
    # 聖職者(同上)
    "トーマス・チャーマーズ",  # 数学の著作なし。スコットランド自由教会の創設者
    # その他(活動家・ハッカーなど。同上)
    "リチャード・バンドラー",  # 数学・計算機科学の研究実績なし。NLP開発者
    "カレン・シルクウッド",  # 化学技術者だったが研究実績なし。労働組合活動家として著名
    "セヴァン・カリス＝スズキ",  # 研究職に就かず。12歳からの環境問題活動家として著名
    "エイドリアン・ラモ",  # 学術的な研究実績なし。元ハッカー・ジャーナリスト
    "ケビン・ポールセン",  # 研究実績の記載なし。元ハッカーで現ジャーナリスト
}


# era 境界(生年basis。明快な丸め値。変更容易にするためここに集約。ADR 00009 参照)
#   古代: 生年 <= 500 / 中世: 501-1500 / 近世: 1501-1700 /
#   近代: 1701-1900 / 現代: 1901-
def era_of(year: int) -> str:
    if year is None:
        return "NA"
    if year <= 500:
        return "古代"
    if year <= 1500:
        return "中世"
    if year <= 1700:
        return "近世"
    if year <= 1900:
        return "近代"
    return "現代"


def is_blank(v) -> bool:
    """既存セルが「未記入」か。空文字・空白のみ・NA を未記入とみなす。"""
    return v is None or v.strip() in ("", "NA")


def norm(title: str) -> str:
    """既存 original との照合キー(曖昧回避サフィックス除去+全半角空白除去)。"""
    return DISAMBIG.sub("", title).replace("　", "").replace(" ", "")


def image_pair(url: str):
    # カンマ等を含むファイル名はCSVを壊すので必ずURLエンコード
    fname = urllib.parse.quote(
        urllib.parse.unquote(url.rsplit("/", 1)[1]).replace(" ", "_"))
    return ("http://commons.wikimedia.org/wiki/Special:FilePath/" + fname,
            "https://commons.wikimedia.org/wiki/File:" + fname)


def parse_birth(iso: str):
    """P569のISO日時 -> (表示用文字列, 数値年)。紀元前は「前287」/ 負の数値年。"""
    if not iso:
        return None, None
    try:
        if iso.startswith("-"):
            y = int(iso[1:].split("-")[0])
            return f"前{y}", -y
        y = int(iso.split("-")[0])
        return str(y), y
    except ValueError:
        return None, None


def field_value(labels) -> str:
    """分野ラベル集合 -> 単一 field 値(優先順のスラッシュ区切り多値)。該当が
    無ければ "物理"(呼び出し側で出自デフォルトに使う)。切り詰めはしない。
    ソラミミック側の部分一致演算子 field~=物理 で1列のまま絞り込める前提。"""
    ordered = sorted(set(labels), key=lambda x: FIELD_ORDER[x])
    return "/".join(ordered) if ordered else "物理"


def fetch_person_set() -> dict:
    """QID -> {"title", "fields"(優先順ラベルのリスト)} を返す(sitelinks>=20)。"""
    qid_fields = {}  # qid -> set(label)
    qid_title = {}   # qid -> ja title
    for occ, label in OCCUPATIONS:
        q = f"""
SELECT ?p ?title WHERE {{
  ?p wdt:P106 wd:{occ} ; wikibase:sitelinks ?n .
  ?a schema:about ?p ; schema:isPartOf <https://ja.wikipedia.org/> ;
     schema:name ?title .
  FILTER(?n >= {MIN_SITELINKS})
}}"""
        data = sparql(q)
        n = 0
        for b in data["results"]["bindings"]:
            qid = b["p"]["value"].rsplit("/", 1)[1]
            qid_title[qid] = b["title"]["value"]
            qid_fields.setdefault(qid, set()).add(label)
            n += 1
        print(f"  {label}(wd:{occ}): {n}人", flush=True)
    persons = {}
    for qid, labels in qid_fields.items():
        ordered = sorted(labels, key=lambda x: FIELD_ORDER[x])
        persons[qid] = {"title": qid_title[qid], "fields": ordered}
    print(f"科学者集合: {len(persons)}人(distinct QID)", flush=True)
    return persons


def fetch_attrs(qids: list) -> dict:
    """QID -> 属性dict。P569/P570/P21/P27/P166(nobel)/P18 をバッチ取得。"""
    attrs = {}
    for i in range(0, len(qids), 200):
        batch = qids[i:i + 200]
        values = " ".join(f"wd:{q}" for q in batch)
        q = f"""
SELECT ?p (MIN(?birth) AS ?b) (MAX(?death) AS ?d) (MIN(?genderL) AS ?g)
  (GROUP_CONCAT(DISTINCT ?countryL; SEPARATOR="||") AS ?countries)
  (MAX(?nobelV) AS ?nobel) (MIN(?img) AS ?image)
  (SAMPLE(?wdesc) AS ?desc) WHERE {{
  VALUES ?p {{ {values} }}
  OPTIONAL {{ ?p wdt:P569 ?birth . FILTER(isLiteral(?birth)) }}
  OPTIONAL {{ ?p wdt:P570 ?death . FILTER(isLiteral(?death)) }}
  OPTIONAL {{ ?p wdt:P21 ?gender . ?gender rdfs:label ?genderL .
             FILTER(LANG(?genderL)="ja") }}
  OPTIONAL {{ ?p wdt:P27 ?country . ?country rdfs:label ?countryL .
             FILTER(LANG(?countryL)="ja") }}
  OPTIONAL {{ ?p wdt:P166 ?a . ?a wdt:P31 wd:Q7191 . BIND("yes" AS ?nobelV) }}
  OPTIONAL {{ ?p wdt:P18 ?img }}
  OPTIONAL {{ ?p schema:description ?wdesc . FILTER(LANG(?wdesc)="ja") }}
}} GROUP BY ?p"""
        data = sparql(q)
        for bnd in data["results"]["bindings"]:
            qid = bnd["p"]["value"].rsplit("/", 1)[1]
            attrs[qid] = build_attr(bnd)
        print(f"  属性取得 {min(i + 200, len(qids))}/{len(qids)}", flush=True)
    return attrs


def build_attr(bnd: dict) -> dict:
    birth_iso = bnd.get("b", {}).get("value")
    death_iso = bnd.get("d", {}).get("value")
    birth_disp, birth_num = parse_birth(birth_iso)
    gender_raw = bnd.get("g", {}).get("value")
    gender = {"男性": "男性", "女性": "女性"}.get(gender_raw, "その他" if gender_raw else "NA")
    countries_raw = bnd.get("countries", {}).get("value", "")
    cs = set()
    for c in countries_raw.split("||"):
        c = c.strip().replace(",", " ")  # ラベル内カンマはパーサを壊すので除去
        if c:
            cs.add(c)
    # 出力順を安定化(WDQSのGROUP_CONCAT順は非決定的で年次PRのノイズになる)
    country = "/".join(sorted(cs)) if cs else "NA"
    nobel = "yes" if bnd.get("nobel", {}).get("value") == "yes" else "no"
    # status: 没年あり=物故 / 生年既知で(現在-生年)>120=物故 / 生年既知=存命 / 不明=NA
    if death_iso:
        status = "物故"
    elif birth_num is not None:
        status = "物故" if (CURRENT_YEAR - birth_num) > 120 else "存命"
    else:
        status = "NA"
    img = bnd.get("image", {}).get("value")
    return {
        "birth_year": birth_disp or "NA",
        "era": era_of(birth_num),
        "gender": gender,
        "country": country,
        "nobel": nobel,
        "status": status,
        "image": image_pair(img) if img else None,
        "wd_desc": bnd.get("desc", {}).get("value", ""),
    }


COLS = ["id", "original", "surface", "pronunciation", "type",
        "field", "era", "birth_year", "nobel", "gender", "country", "status",
        "description", "image", "image_page"]
# 既存行に付与/保持する新列
NEW_FIELDS = ["field", "era", "birth_year", "nobel", "gender", "country",
              "status", "description"]


def fetch_all(persons: dict):
    """attrs と 全人物の記事冒頭 extracts を取得(キャッシュ対応)。"""
    if CACHE and Path(CACHE).exists():
        with open(CACHE, "rb") as fh:
            attrs, extracts = pickle.load(fh)
        print(f"キャッシュから読み込み: {CACHE}", flush=True)
        return attrs, extracts
    attrs = fetch_attrs(sorted(persons))
    titles = sorted({p["title"] for p in persons.values()})
    print(f"記事冒頭を取得中... {len(titles)}件", flush=True)
    extracts = fetch_extracts(titles)
    if CACHE:
        with open(CACHE, "wb") as fh:
            pickle.dump((attrs, extracts), fh)
        print(f"キャッシュ保存: {CACHE}", flush=True)
    return attrs, extracts


def main() -> int:
    persons = fetch_person_set()
    if not 2000 <= len(persons) <= 12000:
        print(f"error: implausible scientist count: {len(persons)}", file=sys.stderr)
        return 1
    attrs, extracts = fetch_all(persons)

    # 照合キー(正規化タイトル)-> {qid, field, attr, desc}
    # norm() は曖昧さ回避サフィックスを落とすので、同名別人が同じキーに衝突する
    # (例: 「カール・フォン・リンネ」と「カール・フォン・リンネ (子)」)。dict の
    # 挿入順まかせだと実行のたびに別人の属性が既存行に書かれてしまうため、
    # (1) サフィックスの無い記事名を優先 (2) 同順は QID 昇順、で決定的に選ぶ
    by_key, collisions = {}, 0
    for qid in sorted(persons, key=lambda q: int(q[1:])):
        p = persons[qid]
        key = norm(p["title"])
        rank = 0 if DISAMBIG.sub("", p["title"]) == p["title"] else 1
        if key in by_key:
            collisions += 1
            if by_key[key]["rank"] <= rank:
                continue
        by_key[key] = {
            "qid": qid, "rank": rank, "field": field_value(p["fields"]),
            "attr": attrs.get(qid, {}),
            "desc": make_description(extracts.get(p["title"], ""),
                                     attrs.get(qid, {}).get("wd_desc", ""),
                                     DISAMBIG.sub("", p["title"])),
        }
    if collisions:
        print(f"照合キー衝突(同名別人) {collisions}件: サフィックス無しを優先", flush=True)

    # 2回目以降は生成済みの scientist.csv を正とし、初回のみ physicist.csv から移行
    source = NEW_CSV if NEW_CSV.exists() else OLD_CSV
    print(f"既存データ読み込み元: {source.name}", flush=True)
    old_rows = list(csv.DictReader(source.open(encoding="utf-8")))
    for r in old_rows:
        r.setdefault("image", "")
        r.setdefault("image_page", "")
    existing = {r["original"] for r in old_rows}

    # 既存行への新列付与 + 空欄のバックフィル。既に埋まっている値は書き換えない
    # (ADR 00014)。上流のラベル揺れ・記事改稿・同名別人の取り違えで、良いデータが
    # 毎回上書きされるのを防ぐ
    matched = filled = deceased = 0
    for r in old_rows:
        info = by_key.get(r["original"])
        if info:
            matched += 1
            a = info["attr"]
            fresh = {
                "field": info["field"],
                "era": a.get("era", "NA"),
                "birth_year": a.get("birth_year", "NA"),
                "nobel": a.get("nobel", "no"),
                "gender": a.get("gender", "NA"),
                "country": a.get("country", "NA"),
                "status": a.get("status", "NA"),
                "description": info["desc"],
            }
            for c, v in fresh.items():
                if is_blank(r.get(c)):
                    r[c] = v if not is_blank(v) else "NA"
                    filled += 1
            # 唯一の例外: 死没は不可逆なので 存命→物故 だけは反映する
            if r["status"] == "存命" and fresh["status"] == "物故":
                r["status"] = "物故"
                deceased += 1
            if not r["image"] and a.get("image"):
                r["image"], r["image_page"] = a["image"]
        elif r.get("field"):
            # scientist.csv 再実行時: Wikidata非一致行は既存の付加情報を保持する
            for c in NEW_FIELDS:
                r.setdefault(c, "NA")
        else:
            # physicist.csv からの初回移行: 出自が物理学者なので field=物理、他はNA
            r["field"] = "物理"
            r["era"] = r["birth_year"] = r["nobel"] = "NA"
            r["gender"] = r["country"] = r["status"] = r["description"] = "NA"
    print(f"既存 {len(old_rows)}行, Wikidata一致 {matched}行, "
          f"空欄補完 {filled}セル, 存命→物故 {deceased}行", flush=True)

    candidates = [p["title"] for p in persons.values()
                  if norm(p["title"]) not in existing
                  and norm(p["title"]) not in EXCLUDED]
    hit = {norm(p["title"]) for p in persons.values()} & EXCLUDED
    print(f"新規候補 {len(candidates)}件 (EXCLUDED で除外 {len(hit)}件)", flush=True)
    # 記事名が変わると除外が効かなくなり、静かに再追加されてしまうので気付けるようにする
    stale = sorted(EXCLUDED - hit)
    if stale:
        print(f"注意: EXCLUDED に未ヒットの項目 {len(stale)}件"
              "(記事改名/sitelinks減で対象外になった可能性): "
              + ", ".join(stale[:20]), flush=True)

    next_id = max(int(r["id"]) for r in old_rows) + 1
    added, flagged = [], []
    for title in candidates:
        parsed = parse_person(DISAMBIG.sub("", title), extracts.get(title, ""))
        if parsed is None:
            flagged.append(title)
            continue
        f_s, f_y, g_s, g_y, full_s, full_y, _reg = parsed
        original = full_s.replace(" ", "")
        if original in existing:
            continue
        existing.add(original)
        # 既存規約: 日本人漢字名の読みはひらがな、カタカナ名はそのまま
        if not KATAKANA.match(original):
            f_y = f_y.translate(KATA2HIRA)
            full_y = (f_y + g_y.translate(KATA2HIRA))
            full_s = original
        info = by_key.get(norm(title), {})
        a = info.get("attr", {})
        base = {
            "field": info.get("field", "物理"),
            "era": a.get("era", "NA"),
            "birth_year": a.get("birth_year", "NA"),
            "nobel": a.get("nobel", "no"),
            "gender": a.get("gender", "NA"),
            "country": a.get("country", "NA"),
            "status": a.get("status", "NA"),
            "description": info.get("desc", "NA"),
        }
        img, img_page = a.get("image") or ("", "")
        rows = []
        if f_s and f_s != full_s:
            rows.append((f_s, f_y, "family"))
        rows.append((full_s, full_y, "full"))
        for surface, pron, typ in rows:
            row = {"id": str(next_id), "original": original, "surface": surface,
                   "pronunciation": pron, "type": typ, **base,
                   "image": img, "image_page": img_page}
            added.append(row)
        next_id += 1

    write_csv_no_trailing_newline(NEW_CSV, COLS, old_rows + added)

    n_people = len({r["id"] for r in added})
    max_fields = max((len(r["field"].split("/")) for r in old_rows + added
                      if r["field"] not in ("NA", "")), default=0)
    print(f"\nscientist.csv: 既存{len(old_rows)}行 + 新規{n_people}人({len(added)}行) "
          f"= {len(old_rows) + len(added)}行", flush=True)
    print(f"単一field列(スラッシュ区切り)・切り詰めなし。最大分野数: {max_fields}", flush=True)
    print(f"要確認(読み機械決定不能) {len(flagged)}件", flush=True)
    for t in flagged[:50]:
        print(f"  要確認: {t}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
