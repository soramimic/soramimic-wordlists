#!/usr/bin/env python3
"""gimukyoiku.csv に Wikipedia/Commons の画像を付与する。

方針(ADR 00027):
- ja.wikipedia の「語と完全一致する記事」(リダイレクト追従あり)のリード画像
  (pageimages、自由ライセンスのみ)を採用する
- リード画像が無い記事は、Wikidata の画像プロパティ(P18)をフォールバックとして
  引く(記事の代表画像が未設定でも P18 が付いていることが多い。火成岩など)
- 生成イメージ(Release配布)の行は、実写・図版が取れたら上書きする
  (実写の方が良い改善方向。ADR 00021 の概念イメージと同じ扱い)
- 曖昧さ回避ページ・記事なし・画像なしの行は空のまま(同名異義の取り違えを
  避けるため、検索や部分一致では引かない)
- 画像は Wikimedia Commons にあるファイルだけ使う(jawiki ローカルの
  非自由ファイルを除外)。image は Special:FilePath、image_page は
  Commons の File: ページ(ライセンス確認先)
- wikidata 列には画像の取得元になった記事の QID を入れる(画像とセットで
  埋まる。sekitsui/plant と同じ扱い)
- 完全一致でも語義が違う誤マッチ(教科の文脈と別の意味の記事)は EXCLUDED に
  恒久除外として追記する(理由コメント付き。insect の EXCLUDED と同じ流儀)

使い方:
  python3 tools/enrich_gimukyoiku_images.py            # 空欄のみ付与
  python3 tools/enrich_gimukyoiku_images.py --refresh  # キャッシュを引き直す

取得結果は tools/.cache/gimukyoiku_images.json に保存し、中断しても再実行で
続きから再開する。レビュー用の一覧を tools/.cache/gimukyoiku_image_report.tsv
に出力する。
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "gimukyoiku.csv"
CACHE = ROOT / "tools" / ".cache" / "gimukyoiku_images.json"
REPORT = ROOT / "tools" / ".cache" / "gimukyoiku_image_report.tsv"

JA_API = "https://ja.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
UA = "soramimic-wordlists/enrich_gimukyoiku_images (https://github.com/soramimic/soramimic-wordlists)"
BATCH = 40

# 画像として扱える拡張子(PDF・動画・TIFFなどのリード"画像"を弾く)
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".svg", ".gif", ".webp")

# 完全一致でも語義が違う誤マッチ等の恒久除外(語: 理由)。2026-07-29 全件AIレビューによる
EXCLUDED = {
    # 記事が教科の文脈と別の意味
    "シャープ": "記事はシャープ株式会社(音楽記号ではない)",
    "スメタナ": "記事は発酵乳(作曲家ではない)",
    "魔王": "記事は悪魔の王(シューベルトの歌曲ではない)",
    "赤とんぼ": "記事は昆虫(童謡ではない)",
    "かたつむり": "記事は巻貝(唱歌ではない)",
    "明暗": "記事は漱石の小説(陰影表現ではない)",
    "バレン": "記事はアイルランドの地形(版画のばれんではない)",
    "凸版": "TOPPANホールディングスへのリダイレクト(版式ではない)",
    "ゲルニカ": "記事はバスクの自治体(ピカソの絵ではない)",
    "握手": "記事は挨拶(井上ひさしの小説ではない)",
    "トロッコ": "記事は鉱山の貨車(芥川の短編ではない)",
    "高瀬舟": "記事は川舟(鴎外の小説ではない。画像は川面)",
    "ツバメ": "記事は鳥(鉄棒の技ではない)",
    "ゆりかご": "記事は揺り籠(マット運動の技ではない)",
    "台風の目": "記事は気象現象(運動会種目ではない)",
    "反射": "記事は波の反射(生物の反射ではない)",
    "基数": "記事は集合論の濃度(基数詞ではない)",
    # 記事は正しいが画像が語を表していない
    "元素記号": "リード画像が家紋",
    "風神雷神図屏風": "画像が敦煌の阿修羅(宗達の屏風ではない)",
    "数直線": "直線へのリダイレクトで画像が空白プレースホルダ",
    "半直線": "直線へのリダイレクトで画像が空白プレースホルダ",
    "最後の晩餐": "画像がレオナルド作品ではなく別のイコン",
    "木彫": "彫刻へのリダイレクトで画像が大理石像",
    "凹版": "画像が凸版印刷の工房",
    "ヨウ素液": "ヨウ化カリウムへのリダイレクトで画像がKI結晶",
    "質量保存の法則": "画像がベルヌーイの定理の図",
    "振動数": "画像が汎用の物理アイコン",
    "電気抵抗": "画像が汎用の物理アイコン",
    "かさ歯車": "歯車へのリダイレクトで画像が平歯車",
    "いちょう切り": "画像が切り方一覧共通のタイの飾り切り",
    "半月切り": "画像が切り方一覧共通のタイの飾り切り",
    "乱切り": "画像が切り方一覧共通のタイの飾り切り",
    "輪切り": "画像が切り方一覧共通のタイの飾り切り",
    "小口切り": "画像が切り方一覧共通のタイの飾り切り",
    "ささがき": "画像が切り方一覧共通のタイの飾り切り",
    "五大栄養素": "画像が授乳中の乳児",
    "保健": "画像がOECD社会支出グラフ",
    "近郊農業": "画像が古代エジプト墓室壁画",
    "長唄": "画像が山東京伝の盃",
    "画板": "画像が三岸節子の書影",
    "和歌": "画像が原稿用紙の文學の文字",
    "自由民権運動": "画像が汎用の黄色い旗",
    "市場経済": "画像が汎用の黄色い旗",
    # 2026-07-30 P18フォールバック分のAIレビューによる追加
    "体言止め": "P18が海神の絵画(修辞技法と無関係)",
    "類義語": "P18が同音異義語のベン図(別概念)",
    "休符": "P18が全音符の和音譜(休符が写っていない)",
    "四分の四拍子": "P18の譜例が2/2拍子",
    "運命": "P18が運命の三女神の絵画(交響曲の通称と同名異義)",
    "星座早見": "P18が1502年の世界海図(planisphereの同名異義)",
    "発音": "P18がブラジル上院本会議場(pronunciamentoとの誤結合)",
    "暗記": "P18がボードゲーム大会の写真(同名異義)",
    "共同制作": "P18がカタルーニャの人間の塔(美術の共同制作ではない)",
    "ブロック": "P18がソ連の組立玩具(バレーボールのブロックではない)",
    "防具": "P18が産業用保護具の棚(剣道の防具ではない)",
    "ファスナー": "P18がネジの集合写真(fastenerとの誤結合)",
    "悪質商法": "P18が列車のビジネス個室(無関係)",
    "消費電力": "P18が世界の発電量グラフ(別概念)",
    "全数調査": "P18が系統抽出の図(標本調査と同一で逆の内容)",
    "過密": "P18が兵員輸送船内の米兵(都市の過密ではない)",
    "まつり縫い": "P18がミシン前のモデル写真(手縫いを表さない)",
    "木ねじ": "P18がメートル機械ねじ(木ねじではない)",
    "奇数": "P18がメイテイ数字の奇数表(判読不能)",
    "石膏": "P18が透明な鉱物結晶標本(美術の石膏の印象と乖離)",
    "縮尺": "P18が装飾的な古地図(概念が伝わらない)",
    "献立": "P18が居酒屋のメニュー黒板(栄養バランスの献立ではない)",
    "等速直線運動": "P18がプリンキピアのラテン語原文(語を表さない)",
    "アルファベット": "P18が世界の文字体系分布図(英語の26文字ではない)",
    "開脚前転": "リード画像が体操マットの商品写真(技を表さない)",
}

# 完全一致では引けないが、AIレビューで語義一致を確認して手動で対応づけた記事(2026-08-02)。
# 曖昧さ回避ページ止まりだった語(モネ→クロード・モネ)や、日本語版に画像が無く英語版から
# 引く語(雅楽→Gagaku)が対象。ここに無い語を検索で拾いにいくことはしない(取り違え防止)。
MANUAL_TITLES = {
    "おくのほそ道": ("en", "Oku no Hosomichi"),
    "はさみ跳び": ("en", "Scissors jump"),
    "オフサイド": ("en", "Offside (sport)"),
    "カム": ("ja", "カム (機械要素)"),
    "クランプ": ("ja", "クランプ (工具)"),
    "サバナ": ("ja", "サバナ (植生)"),
    "サマー": ("ja", "夏"),
    "シュート": ("ja", "シュート (サッカー)"),
    "スキット": ("ja", "スケッチ・コメディー"),
    "スクール": ("ja", "学校"),
    "スチューデント": ("ja", "生徒"),
    "スプリング": ("ja", "春"),
    "セザンヌ": ("ja", "ポール・セザンヌ"),
    "チャート": ("ja", "チャート (岩石)"),
    "トン": ("en", "Tonne"),
    "ニス": ("en", "Varnish"),
    "ニッパ": ("ja", "ニッパー (工具)"),
    "パス": ("ja", "オイルパステル"),
    "パスワード": ("en", "Password"),
    "パリ協定": ("ja", "パリ協定 (気候変動)"),
    "フロッタージュ": ("en", "Frottage (art)"),
    "ブック": ("ja", "本"),
    "ブラックボード": ("ja", "黒板"),
    "ヘ音記号": ("en", "Clef"),
    "ペンシル": ("ja", "鉛筆"),
    "ホルスト": ("ja", "グスターヴ・ホルスト"),
    "マイムマイム": ("en", "Mayim Mayim"),
    "マスキング": ("ja", "マスキングテープ"),
    "ムンク": ("ja", "エドヴァルド・ムンク"),
    "モネ": ("ja", "クロード・モネ"),
    "ライティング": ("ja", "筆記"),
    "ロダン": ("ja", "オーギュスト・ロダン"),
    "ヴィヴァルディ": ("ja", "アントニオ・ヴィヴァルディ"),
    "ヴェルディ": ("ja", "ジュゼッペ・ヴェルディ"),
    "三平方の定理": ("ja", "ピタゴラスの定理"),
    "傾き": ("ja", "傾き (数学)"),
    "円柱": ("ja", "円柱 (数学)"),
    "分別": ("ja", "分別収集"),
    "原点": ("ja", "原点 (数学)"),
    "叫び": ("ja", "叫び (エドヴァルド・ムンク)"),
    "塗装": ("en", "Coating"),
    "大太鼓": ("ja", "バスドラム"),
    "御伽草子": ("en", "Otogi-zōshi"),
    "持久走": ("en", "Long-distance running"),
    "政府開発援助": ("en", "Official development assistance"),
    "比": ("en", "Ratio"),
    "民謡": ("en", "Min'yō"),
    "気団": ("en", "Air mass"),
    "相似": ("ja", "図形の相似"),
    "第三角法": ("en", "Multiview orthographic projection"),
    "筋かい": ("ja", "筋交い"),
    "考える人": ("ja", "考える人 (ロダン)"),
    "見当": ("ja", "トンボ (印刷)"),
    "通風": ("ja", "換気"),
    "酸化": ("en", "Oxidation"),
    "酸化銅": ("ja", "酸化銅(II)"),
    "長距離走": ("en", "Long-distance running"),
    "雅楽": ("en", "Gagaku"),
    "需要と供給": ("en", "Supply and demand"),
    "pH": ("en", "PH"),
    "きらきら星変奏曲": ("en", 'Twelve Variations on "Ah vous dirai-je, Maman"'),
    "くらしと絵文字": ("ja", "ピクトグラム"),
    "こころ": ("ja", "こゝろ"),
    "さくら変奏曲": ("ja", "宮城道雄"),
    "さけが大きくなるまで": ("ja", "サケ"),
    "すずめのくらし": ("ja", "スズメ"),
    "たけくらべ": ("ja", "樋口一葉"),
    "ちょっと立ち止まって": ("ja", "ルビンの壺"),
    "どうぶつ園のじゅうい": ("ja", "獣医師"),
    "どきん": ("ja", "谷川俊太郎"),
    "ないた赤おに": ("ja", "浜田広介"),
    "ほたるの一生": ("ja", "ホタル"),
    "ほたるの光": ("en", "Auld Lang Syne"),
    "みぶりでつたえる": ("ja", "ジェスチャー"),
    "やしの実": ("ja", "島崎藤村"),
    "わたしが一番きれいだったとき": ("ja", "茨木のり子"),
    "わたしと小鳥とすずと": ("ja", "金子みすゞ"),
    "アタッチメント": ("en", "Attachment theory"),
    "アンデルセン": ("ja", "ハンス・クリスチャン・アンデルセン"),
    "ウナギのなぞを追って": ("ja", "ウナギ"),
    "エシカル消費": ("en", "Fair trade"),
    "エーデルワイス": ("en", "Edelweiss (song)"),
    "オアシス農業": ("en", "Oasis"),
    "オオカミを見る目": ("ja", "オオカミ"),
    "オーラ・リー": ("en", "Aura Lea"),
    "カノン": ("en", "Canon (music)"),
    "クマゼミ増加の原因を探る": ("ja", "クマゼミ"),
    "クロムウェル": ("ja", "オリバー・クロムウェル"),
    "コロンブス": ("ja", "クリストファー・コロンブス"),
    "サイン計画": ("en", "Wayfinding"),
    "サハラ砂漠の茶会": ("ja", "サハラ砂漠"),
    "サン＝テグジュペリ": ("ja", "アントワーヌ・ド・サン＝テグジュペリ"),
    "シェエラザード": ("en", "Scheherazade (Rimsky-Korsakov)"),
    "ストレス": ("en", "Psychological stress"),
    "ダイコンは大きな根": ("ja", "ダイコン"),
    "ダリ": ("ja", "サルバドール・ダリ"),
    "チャイニーズ・ダンス": ("ja", "くるみ割り人形"),
    "トルストイ": ("ja", "レフ・トルストイ"),
    "ドレミの歌": ("en", "The Sound of Music (film)"),
    "ニュータウン": ("en", "New town"),
    "ハトはなぜ首を振って歩くのか": ("ja", "ハト"),
    "バロック美術": ("en", "Baroque painting"),
    "バロック音楽": ("en", "Baroque music"),
    "ヒスパニック": ("en", "Hispanic and Latino Americans"),
    "ビスマルク": ("ja", "オットー・フォン・ビスマルク"),
    "ファラデーの法則": ("en", "Faraday's laws of electrolysis"),
    "フェアプレイ": ("en", "Sportsmanship"),
    "フレーズ": ("en", "Phrase (music)"),
    "ブルーカーボン": ("en", "Blue carbon"),
    "ベンサム": ("ja", "ジェレミ・ベンサム"),
    "ポリス": ("en", "Polis"),
    "マゼラン": ("ja", "フェルディナンド・マゼラン"),
    "メディアリテラシー": ("en", "Media literacy"),
    "モアイは語る": ("ja", "モアイ"),
    "モデル化": ("en", "Scientific modelling"),
    "ライディーン": ("ja", "イエロー・マジック・オーケストラ"),
    "ライフステージ": ("en", "Life course approach"),
    "リカード": ("ja", "デヴィッド・リカード"),
    "リノベーション": ("en", "Renovation"),
    "リピテーション": ("en", "Pattern"),
    "リンカン": ("ja", "エイブラハム・リンカーン"),
    "リート": ("en", "Lied"),
    "ルター": ("ja", "マルティン・ルター"),
    "レモン哀歌": ("ja", "高村光太郎"),
    "ロマン派": ("en", "Romantic music"),
    "一次救命処置": ("en", "Cardiopulmonary resuscitation"),
    "三国同盟": ("ja", "三国同盟 (1882年)"),
    "上を向いて歩こう": ("ja", "坂本九"),
    "不整合": ("en", "Unconformity"),
    "中和滴定": ("en", "Titration"),
    "二月革命": ("ja", "フランス二月革命"),
    "交響組曲": ("en", "Suite (music)"),
    "交響詩": ("ja", "フランツ・リスト"),
    "人権宣言": ("ja", "人間と市民の権利の宣言"),
    "人間失格": ("ja", "太宰治"),
    "介護": ("en", "Elderly care"),
    "企業的穀物農業": ("en", "Combine harvester"),
    "伝統工芸": ("en", "Handicraft"),
    "住生活": ("en", "Housing"),
    "体細胞分裂": ("en", "Mitosis"),
    "余白": ("en", "Negative space"),
    "価電子": ("en", "Valence electron"),
    "保健医療制度": ("en", "Health care"),
    "修復": ("en", "Conservation and restoration of cultural heritage"),
    "俳句の可能性": ("ja", "俳句"),
    "健康寿命": ("en", "Health-adjusted life expectancy"),
    "八幡製鉄所": ("ja", "官営八幡製鐵所"),
    "凝固点降下": ("en", "Freezing-point depression"),
    "分子間力": ("en", "Intermolecular force"),
    "初恋": ("ja", "島崎藤村"),
    "力学的エネルギー保存則": ("en", "Mechanical energy"),
    "包帯法": ("ja", "包帯"),
    "北方領土": ("ja", "北方領土問題"),
    "医療機関": ("en", "Hospital"),
    "十六夜日記": ("ja", "阿仏尼"),
    "千の風になって": ("en", "Do Not Stand at My Grave and Weep"),
    "半保存的複製": ("en", "DNA replication"),
    "南総里見八犬伝": ("ja", "曲亭馬琴"),
    "印象主義音楽": ("ja", "クロード・ドビュッシー"),
    "古典派": ("en", "Classical period (music)"),
    "合成高分子": ("en", "Polymer"),
    "名人伝": ("ja", "中島敦"),
    "君をのせて": ("ja", "久石譲"),
    "和泉式部日記": ("ja", "和泉式部"),
    "問屋制家内工業": ("en", "Putting-out system"),
    "啓蒙思想": ("en", "Age of Enlightenment"),
    "喜びの歌": ("en", "Ode to Joy"),
    "固定法": ("en", "Splint (medicine)"),
    "国司": ("en", "Kokushi (official)"),
    "国民楽派": ("ja", "ベドルジハ・スメタナ"),
    "土の歌": ("ja", "大木惇夫"),
    "土一揆": ("ja", "正長の土一揆"),
    "城の崎にて": ("ja", "志賀直哉"),
    "基質特異性": ("en", "Enzyme"),
    "夏は来ぬ": ("ja", "小山作之助"),
    "多重債務": ("en", "Debt"),
    "夢を跳ぶ": ("ja", "谷真海"),
    "夢十夜": ("ja", "夏目漱石"),
    "大気の大循環": ("en", "Atmospheric circulation"),
    "大阿蘇": ("ja", "三好達治"),
    "天地の文": ("ja", "福沢諭吉"),
    "学ぶ力": ("ja", "内田樹"),
    "宇宙の膨張": ("en", "Expansion of the universe"),
    "守護": ("en", "Shugo"),
    "富嶽百景": ("ja", "太宰治"),
    "対立形質": ("en", "Dominance (genetics)"),
    "封建制度": ("en", "Feudalism"),
    "小フーガ": ("ja", "ヨハン・ゼバスティアン・バッハ"),
    "小僧の神様": ("ja", "志賀直哉"),
    "小景異情": ("ja", "室生犀星"),
    "小林秀雄": ("ja", "小林秀雄 (批評家)"),
    "小筆": ("ja", "筆"),
    "山月記": ("ja", "中島敦"),
    "山椒大夫": ("ja", "森鷗外"),
    "山羊の歌": ("ja", "中原中也"),
    "帰去来辞": ("ja", "陶淵明"),
    "平調子": ("ja", "箏"),
    "待ち行列": ("en", "Queueing theory"),
    "循環型社会": ("en", "Circular economy"),
    "性の多様性": ("en", "LGBTQ"),
    "情報の伝達": ("en", "Telecommunications"),
    "情報デザイン": ("en", "Information design"),
    "情意機能": ("en", "Emotion"),
    "感覚神経": ("en", "Sensory neuron"),
    "抵抗": ("ja", "抵抗器"),
    "持続可能な消費": ("en", "Sustainable Development Goal 12"),
    "敦盛": ("ja", "敦盛 (能)"),
    "文字コード": ("en", "Character encoding"),
    "新期造山帯": ("en", "Alpide belt"),
    "日常食": ("en", "Meal"),
    "旧国名": ("ja", "令制国"),
    "春のうた": ("ja", "草野心平"),
    "春暁": ("ja", "孟浩然"),
    "春琴抄": ("ja", "谷崎潤一郎"),
    "時差": ("en", "Time zone"),
    "時計台の鐘": ("ja", "高階哲夫"),
    "智恵子抄": ("ja", "高村光太郎"),
    "暗夜行路": ("ja", "志賀直哉"),
    "曽根崎心中": ("ja", "近松門左衛門"),
    "最後の一句": ("ja", "森鷗外"),
    "月夜の浜辺": ("ja", "中原中也"),
    "朝のリレー": ("ja", "谷川俊太郎"),
    "木竜うるし": ("ja", "木下順二"),
    "末梢神経": ("en", "Peripheral nervous system"),
    "本州四国連絡橋": ("en", "Honshu–Shikoku Bridge Project"),
    "杜子春": ("ja", "芥川龍之介"),
    "東京スカイツリーのひみつ": ("ja", "東京スカイツリー"),
    "柿山伏": ("ja", "狂言"),
    "根圧": ("en", "Root pressure"),
    "桃花源記": ("ja", "陶淵明"),
    "梁塵秘抄": ("ja", "後白河天皇"),
    "極相": ("en", "Climax community"),
    "構成美の要素": ("en", "Composition (visual arts)"),
    "構造異性体": ("en", "Isomer"),
    "標本化周波数": ("en", "Sampling rate"),
    "檸檬": ("ja", "梶井基次郎"),
    "母子保健": ("en", "Prenatal care"),
    "水の東西": ("ja", "山崎正和"),
    "水害": ("en", "Flood"),
    "沈黙": ("ja", "遠藤周作"),
    "河童と蛙": ("ja", "草野心平"),
    "沸点上昇": ("en", "Colligative properties"),
    "波の干渉": ("en", "Wave interference"),
    "浮動小数点数": ("en", "Floating-point arithmetic"),
    "浮雲": ("ja", "二葉亭四迷"),
    "海の命": ("ja", "立松和平"),
    "海の見える街": ("ja", "久石譲"),
    "海嶺": ("en", "Mid-ocean ridge"),
    "消費生活": ("en", "Consumption (economics)"),
    "涙そうそう": ("ja", "夏川りみ"),
    "深層循環": ("en", "Thermohaline circulation"),
    "混合農業": ("en", "Mixed farming"),
    "混声三部合唱": ("en", "Choir"),
    "清兵衛と瓢箪": ("ja", "志賀直哉"),
    "漆芸": ("ja", "漆器"),
    "漢詩の風景": ("ja", "漢詩"),
    "瀬戸内": ("ja", "瀬戸内海"),
    "瀬戸内工業地域": ("ja", "水島コンビナート"),
    "無名抄": ("ja", "鴨長明"),
    "無常ということ": ("ja", "小林秀雄 (批評家)"),
    "焼き物": ("ja", "陶芸"),
    "物質量": ("en", "Amount of substance"),
    "特許権": ("en", "Patent"),
    "玉勝間": ("ja", "本居宣長"),
    "環境衛生": ("en", "Sanitation"),
    "生命は": ("ja", "吉野弘"),
    "生涯スポーツ": ("en", "Sport"),
    "男女共同参画": ("en", "Gender equality"),
    "発心集": ("ja", "鴨長明"),
    "相似器官": ("en", "Convergent evolution"),
    "相対速度": ("en", "Relative velocity"),
    "相関係数": ("en", "Correlation"),
    "知床": ("ja", "知床半島"),
    "知的機能": ("en", "Cognition"),
    "知的財産権": ("en", "Intellectual property"),
    "砂の女": ("ja", "安部公房"),
    "破戒": ("ja", "島崎藤村"),
    "社会性": ("en", "Social skills"),
    "私のタンポポ研究": ("ja", "タンポポ"),
    "窒素の循環": ("ja", "窒素循環"),
    "笈の小文": ("ja", "松尾芭蕉"),
    "等加速度直線運動": ("en", "Equations of motion"),
    "紙の建築": ("ja", "坂茂"),
    "素朴な琴": ("ja", "八木重吉"),
    "組織液": ("en", "Extracellular fluid"),
    "絶対王政": ("ja", "絶対君主制"),
    "線遠近法": ("en", "Perspective (graphical)"),
    "羅生門": ("ja", "羅生門 (小説)"),
    "義太夫節": ("ja", "文楽"),
    "羽衣": ("ja", "羽衣 (能)"),
    "肖像権": ("en", "Personality rights"),
    "育児休業": ("en", "Parental leave"),
    "舞姫": ("ja", "森鷗外"),
    "色彩調和": ("en", "Color theory"),
    "花は咲く": ("ja", "菅野よう子"),
    "花を見つける手がかり": ("ja", "モンシロチョウ"),
    "華人": ("en", "Overseas Chinese"),
    "落葉松": ("ja", "北原白秋"),
    "藪の中": ("ja", "芥川龍之介"),
    "虹の足": ("ja", "吉野弘"),
    "血糖濃度": ("en", "Blood sugar level"),
    "衣生活": ("en", "Clothing"),
    "装飾": ("en", "Ornament (art)"),
    "補数": ("en", "Method of complements"),
    "触媒": ("en", "Catalysis"),
    "言葉の力": ("ja", "大岡信"),
    "誰かの代わりに": ("ja", "鷲田清一"),
    "誰も知らない私の悩み": ("en", "Nobody Knows the Trouble I've Seen"),
    "論理演算": ("en", "Logical connective"),
    "転写": ("ja", "転写 (生物学)"),
    "進化論": ("en", "Evolution"),
    "運筆": ("ja", "筆"),
    "遠近感": ("en", "Depth perception"),
    "遣隋使": ("ja", "小野妹子"),
    "都道府県": ("en", "Prefectures of Japan"),
    "重心": ("en", "Center of mass"),
    "野原はうたう": ("ja", "工藤直子"),
    "量子化": ("en", "Quantization (signal processing)"),
    "金属結合": ("en", "Metallic bonding"),
    "金槐和歌集": ("ja", "源実朝"),
    "銀閣": ("ja", "慈照寺"),
    "関係データベース": ("en", "Database"),
    "階調": ("en", "Posterization"),
    "集約的稲作農業": ("en", "Paddy field"),
    "雪の降る街を": ("ja", "中田喜直"),
    "雪わたり": ("ja", "宮沢賢治"),
    "雪国": ("ja", "川端康成"),
    "非可逆圧縮": ("en", "Lossy compression"),
    "風のとおり道": ("ja", "久石譲"),
    "風神雷神": ("ja", "風神"),
    "風立ちぬ": ("ja", "堀辰雄"),
    "飛鳥文化": ("ja", "法隆寺"),
    "食品衛生": ("en", "Food safety"),
    "食文化": ("en", "Cuisine"),
    "高野聖": ("ja", "泉鏡花"),
}


# 手動キュレーション(語 → Commonsファイル名)。完全一致記事にもP18にも無いが、
# Commonsを検索すれば教科書的な画像が実在する語。AIレビューでライセンス・被写体を
# 確認済み(2026-07-30)。EXCLUDED より優先する
MANUAL_FILES = {
    "木ねじ": "Wood screws.jpg",
    "防具": "Bogu.jpg",
    "ファスナー": "Zipper - metal - blue 01.jpg",
    "石膏": "Adriano joven - RABASF.jpg",
    "献立": "SchoolLunchJapanese.jpg",
    "星座早見": "星座 早見 渡辺教具製作所 (42414938381).jpg",
    "ブロック": "Volleyball block.jpg",
    "過密": "A crowded platform - rush hour - yurakucho - July 2014.jpg",
}


def api_get(url, params):
    params = dict(params, format="json", maxlag=5)
    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as f:
                return json.load(f)
        except Exception as e:  # noqa: BLE001 - リトライして最後に伝播
            if attempt == 2:
                raise
            wait = 15 if "429" in str(e) else 5
            print(f"  retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(wait)


def lookup_manual(words):
    """MANUAL_TITLES の語を、対応づけた記事から引く(完全一致では届かない語)。"""
    out = {}
    by_host = {}
    for w in words:
        host, title = MANUAL_TITLES[w]
        by_host.setdefault(host, []).append((w, title))
    for host, pairs in by_host.items():
        api = JA_API if host == "ja" else JA_API.replace("ja.wikipedia", "en.wikipedia")
        for i in range(0, len(pairs), BATCH):
            chunk = pairs[i : i + BATCH]
            data = api_get(
                api,
                {
                    "action": "query",
                    "redirects": 1,
                    "titles": "|".join(t for _, t in chunk),
                    "prop": "pageprops|pageimages",
                    "ppprop": "wikibase_item",
                    "piprop": "name",
                    "pilicense": "free",
                },
            )
            q = data["query"]
            norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
            redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
            pages = {p["title"]: p for p in q.get("pages", {}).values()}
            for w, title in chunk:
                resolved = redir.get(norm.get(title, title), norm.get(title, title))
                pg = pages.get(resolved)
                if not pg or "missing" in pg or not pg.get("pageimage"):
                    out[w] = {"status": "noimage", "qid": ""}
                else:
                    out[w] = {
                        "status": "ok",
                        "file": pg["pageimage"],
                        "qid": pg.get("pageprops", {}).get("wikibase_item", ""),
                        "article": resolved,
                    }
            time.sleep(1)
    return out


def lookup_batch(titles):
    """語 -> {status, file, qid} を返す。statusは ok/missing/disambig/noimage。"""
    manual = [t for t in titles if t in MANUAL_TITLES]
    titles = [t for t in titles if t not in MANUAL_TITLES]
    out_manual = lookup_manual(manual) if manual else {}
    if not titles:
        return out_manual
    data = api_get(
        JA_API,
        {
            "action": "query",
            "redirects": 1,
            "titles": "|".join(titles),
            "prop": "pageprops|pageimages",
            "ppprop": "wikibase_item|disambiguation",
            "piprop": "name",
            "pilicense": "free",
        },
    )
    q = data["query"]
    norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
    redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
    pages = {p["title"]: p for p in q.get("pages", {}).values()}
    out = {}
    for t in titles:
        resolved = norm.get(t, t)
        resolved = redir.get(resolved, resolved)
        p = pages.get(resolved)
        if not p or "missing" in p:
            out[t] = {"status": "missing"}
        elif "disambiguation" in p.get("pageprops", {}):
            out[t] = {"status": "disambig"}
        elif not p.get("pageimage"):
            out[t] = {"status": "noimage", "qid": p.get("pageprops", {}).get("wikibase_item", "")}
        else:
            out[t] = {
                "status": "ok",
                "file": p["pageimage"],
                "qid": p.get("pageprops", {}).get("wikibase_item", ""),
                "article": resolved,
            }
    out.update(out_manual)
    return out


WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def fetch_p18(qids):
    """QID -> P18ファイル名。無いQIDは含めない。50件ずつ引く。"""
    out = {}
    qids = sorted(set(qids))
    for i in range(0, len(qids), 50):
        batch = qids[i : i + 50]
        data = api_get(
            WIKIDATA_API,
            {"action": "wbgetentities", "props": "claims", "ids": "|".join(batch)},
        )
        for q in batch:
            p18 = data.get("entities", {}).get(q, {}).get("claims", {}).get("P18")
            if p18:
                f = p18[0].get("mainsnak", {}).get("datavalue", {}).get("value")
                if f:
                    out[q] = f
        time.sleep(2)
    return out


def on_commons(files):
    """Commons に実在するファイル名の集合を返す(jawikiローカル画像を除外)。"""
    ok = set()
    files = sorted(set(files))
    for i in range(0, len(files), 50):
        batch = files[i : i + 50]
        data = api_get(
            COMMONS_API,
            {"action": "query", "titles": "|".join("File:" + f for f in batch)},
        )
        q = data["query"]
        norm = {n["to"]: n["from"] for n in q.get("normalized", [])}
        for p in q.get("pages", {}).values():
            if "missing" not in p:
                title = norm.get(p["title"], p["title"])
                ok.add(title[len("File:"):])
        time.sleep(0.5)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="キャッシュを無視して引き直す")
    args = ap.parse_args()

    lines = CSV.read_text(encoding="utf-8").split("\n")
    header = lines[0].split(",")
    rows = [l.split(",") for l in lines[1:]]
    for col in ("image", "image_page", "wikidata"):
        if col not in header:
            header.append(col)
            for r in rows:
                r.append("")
    idx = {c: header.index(c) for c in header}

    cache = {}
    if CACHE.exists() and not args.refresh:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    # 空欄と Commons 由来の行は毎回引き直す(EXCLUDED 追加を反映できるように)。
    # 生成イメージ(gimukyoiku-image-*)の行も対象にし、実写が取れたら上書きする。
    # それ以外のソースの URL は触らない
    GEN_PREFIX = "https://github.com/soramimic/soramimic-wordlists/releases/download/gimukyoiku-image-"
    targets = [
        r
        for r in rows
        if not r[idx["image"]]
        or "commons.wikimedia.org" in r[idx["image"]]
        or r[idx["image"]].startswith(GEN_PREFIX)
    ]
    kept_generated = {}
    for r in targets:
        if r[idx["image"]].startswith(GEN_PREFIX):
            kept_generated[r[idx["original"]]] = (r[idx["image"]], r[idx["image_page"]])
        r[idx["image"]] = r[idx["image_page"]] = r[idx["wikidata"]] = ""
    pending = sorted({r[idx["original"]] for r in targets if r[idx["original"]] not in cache})
    print(f"対象 {len(targets)} 行 / 問い合わせ {len(pending)} 語(キャッシュ済み {len(targets) - len(pending)})")

    for i in range(0, len(pending), BATCH):
        batch = pending[i : i + BATCH]
        cache.update(lookup_batch(batch))
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  jawiki {min(i + BATCH, len(pending))}/{len(pending)}")
        time.sleep(1)

    # リード画像が無い記事は P18 をフォールバックで引く(結果はキャッシュに保存)
    need_p18 = {
        w: c["qid"]
        for w, c in cache.items()
        if c.get("status") == "noimage" and c.get("qid") and "p18" not in c
    }
    if need_p18:
        print(f"P18フォールバック問い合わせ: {len(need_p18)} 語")
        p18 = fetch_p18(list(need_p18.values()))
        for w, q in need_p18.items():
            cache[w]["p18"] = p18.get(q, "")
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    candidates = {}
    for w, c in cache.items():
        if w in EXCLUDED:
            continue
        if c.get("status") == "ok" and c["file"].lower().endswith(IMAGE_EXT):
            candidates[w] = c
        elif c.get("status") == "noimage" and c.get("p18", "").lower().endswith(IMAGE_EXT):
            candidates[w] = dict(c, status="ok", file=c["p18"])
            cache[w] = candidates[w]
    for w, f in MANUAL_FILES.items():
        candidates[w] = {"status": "ok", "file": f, "qid": ""}
    commons_ok = on_commons([c["file"] for c in candidates.values()])

    stats = {}
    report = ["original\tsubject\tfile\tdescription"]
    for r in targets:
        word = r[idx["original"]]
        subj = r[idx["subject"]]
        c = cache.get(word, {})
        st = stats.setdefault(subj.split("/")[0], dict(n=0, ok=0))
        st["n"] += 1
        if word in MANUAL_FILES:
            c = candidates[word]
        elif word in EXCLUDED or c.get("status") != "ok" or c["file"] not in commons_ok:
            continue
        fname = c["file"].replace(" ", "_")
        quoted = urllib.parse.quote(fname, safe="")
        r[idx["image"]] = f"http://commons.wikimedia.org/wiki/Special:FilePath/{quoted}"
        r[idx["image_page"]] = f"https://commons.wikimedia.org/wiki/File:{quoted}"
        r[idx["wikidata"]] = c.get("qid", "")
        st["ok"] += 1
        report.append(f"{word}\t{subj}\t{c['file']}\t{r[idx['description']]}")

    for r in targets:
        if not r[idx["image"]] and r[idx["original"]] in kept_generated:
            r[idx["image"]], r[idx["image_page"]] = kept_generated[r[idx["original"]]]

    CSV.write_text("\n".join([",".join(header)] + [",".join(r) for r in rows]), encoding="utf-8")
    REPORT.write_text("\n".join(report), encoding="utf-8")

    total_ok = sum(s["ok"] for s in stats.values())
    print(f"\n付与: {total_ok} 行(除外 {len(EXCLUDED)} 語)")
    for subj, s in sorted(stats.items()):
        print(f"  {subj}: {s['ok']}/{s['n']}")
    print(f"レビュー用一覧: {REPORT}")


if __name__ == "__main__":
    main()
