# リスト別の列説明

全CSVに共通する `id`, `original`, `surface`, `pronunciation` は
[README](../README.md#形式)を参照。ここでは各リストの固有列と、
利用時に注意が必要な点を説明する。

`image` は画像URL、`image_page` はライセンス・作者の確認先、
`wikidata` はWikidataのQIDを表す。画像がない場合は空欄になる。

## baseball.csv

| 列 | 意味 |
|---|---|
| team | 所属球団の変遷。移籍は `-`、球団名の変更は `・` で区切る |
| type | 表層の種類(`family`/`given`/`full`/`registered`) |
| org_id | 選手を識別する元データ側のID |
| position | `投手`/`捕手`/`内野手`/`外野手`。複数は `/` 区切り |
| description | 経歴や主要実績の短い説明 |
| image, image_page | Commonsの肖像。ない場合はチームカラーによる選手カード |

選手カードはチームカラーと汎用の職業アイコンで構成する。詳細は
[ADR 00020](adr/00020-player-cards.md)。

## football.csv

既定対象は、WikipediaのJリーグクラブ選手カテゴリを母集団とし、Jリーグ公式の
全選手一覧で登録歴を本人照合できた選手とする。加えて、再現可能な著名度条件を
満たす世界の選手と、国内クラブ所属歴のない日本人選手を任意選択用に収録する。
Jリーグ照合根拠は
`tools/football_jleague_verified_sources.jsonl` に記録する（詳細は
[ADR 00047](adr/00047-football-jleague-wikipedia-rebuild.md)）。収録範囲の基準は
[ADR 00048](adr/00048-football-scope-filters.md)を参照。

| 列 | 意味 |
|---|---|
| team | Jリーグ経験者は公式の最終所属クラブ、それ以外はWikidata上の最新または最終所属クラブを1つ表示 |
| type | 表層の種類(`family`/`given`/`full`等) |
| category | 選手の区分 |
| scope | `jleague`/`world`/`overseas_japanese`。利用側の既定は `jleague` のみ |
| wikidata | 人物のQID |
| position | `GK`/`DF`/`MF`/`FW`。複数は `/` 区切り |
| description | 経歴や主要実績の短い説明 |
| image, image_page | Commonsの肖像。ない場合はチームカラーによる選手カード |

## stations.csv

| 列 | 意味 |
|---|---|
| prefecture, city | 所在地。同名駅の区別にも使う |
| lines | 乗り入れ路線。複数は `／` 区切り |
| operator | 運営者。複数は `／` 区切り |
| opened_year | 開業年 |
| station_code | 駅ナンバリングまたは電報略号。複数は `／` 区切り |
| status | `current`(現役)/`former`(廃止)/`renamed`(旧駅名) |
| description | 特徴または開業年を記した最大48字の説明 |
| image, image_page | Commonsの写真。ない場合は汎用の駅名標画像 |
| wikidata | 駅のQID |

駅名標画像は白地の板に駅名とかな読みを置き、帯の色は路線名から機械的に決める。

## nations.csv

| 列 | 意味 |
|---|---|
| status | `current`(現存)/`former`(消滅国・旧称) |
| capital, continent | 首都と大陸。複数は `/` 区切り |
| population, population_year | 人口と、その人口値の基準年 |
| area_km2 | 面積(km²) |
| established_year, ended_year | 成立年と終了年。紀元前は `前660` の形式。現存行の終了年は空欄 |
| description | 国の短い説明 |
| image, image_page | Commonsの国旗と確認先 |
| wikidata | 国のQID |

人口はWikidataの最新の時点付き値。成立年は最古の成立日であり、現在の政体の
発足年とは限らない。終了年は旧国家の解散年または旧称が置き換わった年とする。

## scientist.csv

| 列 | 意味 |
|---|---|
| type | 表層の種類(`family`/`given`/`full`) |
| field | 分野。複数は `/` 区切り |
| era | `古代`/`中世`/`近世`/`近代`/`現代`/`NA` |
| birth_year, death_year | 生年と没年。紀元前は `前287` の形式 |
| nobel | 科学系ノーベル賞の受賞有無(`yes`/`no`/`NA`) |
| gender | `男性`/`女性`/`その他`/`NA` |
| country | 市民権のある国。複数は `/` 区切り |
| status | `物故`/`存命`/`NA` |
| description | 主な業績の短い説明 |
| image, image_page | Commonsの肖像。ない場合は分野別の象徴カード |

象徴カードは分野の色、姓の頭文字、汎用アイコンで構成する。
分野の色は本リポジトリ独自の区分。詳細は
[ADR 00025](adr/00025-scientist-symbol-cards.md)。

## sekitsui.csv

| 列 | 意味 |
|---|---|
| class | `魚類`/`両生類`/`爬虫類`/`鳥類`/`哺乳類` |
| extinct | 絶滅種または野生絶滅種か(`yes`/`no`) |
| order, family | 目と科 |
| image, image_page | Commonsの実写。ない場合は `class` 別の概念画像 |
| wikidata | 実写の取得元となった分類群のQID |

## plant.csv

| 列 | 意味 |
|---|---|
| class | `双子葉`/`単子葉`/`裸子植物`/`シダ植物`/`コケ植物`/`藻類` |
| extinct | 絶滅種または野生絶滅種か(`yes`/`no`) |
| family, genus | 科と属 |
| image, image_page | Commonsの実写。ない場合は `class` 別の概念画像 |
| wikidata | 実写の取得元となった分類群のQID |

## insect.csv

| 列 | 意味 |
|---|---|
| class | `甲虫`/`チョウ`/`ハチ`/`ハエ`/`カメムシ`/`バッタ`/`トンボ`/`その他` |
| extinct | 絶滅種または野生絶滅種か(`yes`/`no`) |
| order, family | 目と科 |
| image, image_page | Commonsの実写。ない場合は `class` 別の概念画像 |
| wikidata | 分類群のQID |

`class` は利用しやすくするための粗い区分。詳細は
[ADR 00021](adr/00021-insect-wordlist.md)。

## marine_life.csv

海水域を生活場所に含む現生の海洋動物4254件を収録する。初版179件と、
JODCの和名・学名をWoRMSの有効AphiaIDで海洋性確認して追加した4075件からなる。
`sekitsui.csv` と同じ動物名が含まれるが、海洋というまとまりで選択できることを
優先している。収録基準と更新方針は [ADR 00050](adr/00050-marine-life-wordlist.md)。

| 列 | 意味 |
|---|---|
| class | `哺乳類`/`爬虫類`/`魚類`/`無脊椎動物`。Videoの分類フィルター値 |
| vertebrate | `脊椎動物`/`無脊椎動物`。前者は哺乳類・爬虫類・魚類を包含する上位フィルター |
| order, family | 目と科。JODCの日本語分類名、未収録時はWoRMSの学名による補完 |
| description | 根拠を確認できた生態・形態・生息域等を表す8〜90字の完結した短文。根拠不足時は空欄 |
| image, image_page | Commons実写または分類別の概念画像と、その出典・確認先 |
| wikidata | 対応を確認できた分類群のQID。未確認の場合は空欄 |
| scientific_name | WoRMSで確認した有効学名。初版の一部は空欄 |
| aphia_id | WoRMSの有効AphiaID。初版の一部は空欄 |

1384件はCommonsの自由ライセンス実写（幅960px以下の配信用サムネイル）、残る2870件は形態群別の写真風生成イメージである。
実写のライセンス・作者・SHA-1・同定根拠は `tools/marine_life_image_sources.jsonl` に固定する。
生成画像には「生成イメージ」と表示し、特定種の姿と誤認しないようにしている。生成日、
生成手段、プロンプト、元画像と配布画像のSHA-256は `tools/marine_life_generated_images.json` に固定する。
DB追加分の説明は、Wikidata QIDで表示名との一致を検証した日本語Wikipedia記事の特徴文を
優先し、使った記事URL・版ID・元文・生成文を固定する。該当文がない場合だけ、WoRMSの
種レベルの最大体長・IUCN評価から決定的に生成する。根拠は
`tools/marine_life_description_sources.jsonl` に固定し、根拠がない行には未確認の特徴を補わない。
Wikipedia由来の加工文はCC BY-SA 4.0で、同台帳から原記事への帰属と変更有無を確認できる。

## pokemon.csv

| 列 | 意味 |
|---|---|
| type1, type2 | タイプ。単タイプは `type2=NA` |
| generation | 登場世代(1〜9) |
| genus | 分類名(例: `ねずみポケモン`) |
| rarity | `伝説`/`幻`/`ウルトラビースト`/`NA` |
| height_m, weight_kg | 高さ(m)と重さ(kg) |
| evolves_from | 進化前の種名。ない場合は `NA` |
| description | 上記の事実から機械生成した説明 |
| image, image_page | 図鑑端末風カードと素材の確認先 |

カードはタイプ配色、文字、モチーフの汎用シルエットで構成する。モチーフは
本リポジトリの解釈であり、公式設定ではない。詳細は
[ADR 00032](adr/00032-pokemon-fact-columns.md)と
[ADR 00033](adr/00033-pokemon-motif-silhouettes.md)。

## youtuber.csv

| 列 | 意味 |
|---|---|
| type | 表層の種類(`family`/`given`/`full`) |
| category | `youtuber`/`vtuber` |
| org | 所属。複数は `/` 区切り |
| debut_year | 活動開始年。情報がない場合は `NA` |
| status | `current`(活動中)/`former`(活動終了) |
| channel | 登録者数が最大のYouTubeチャンネル名 |
| subscribers | YouTubeが公開する有効数字3桁の概数 |
| description | 活動内容の短い説明 |
| image, image_page | Commonsの実写。ない場合は象徴カード |
| wikidata | 本人のQID |

人物名には活動名を採用する。VTuberの象徴カードは配色、頭文字、職業アイコンで
構成する。詳細は
[ADR 00029](adr/00029-youtuber-channel-description-columns.md)。

## fictional_scientist.csv

| 列 | 意味 |
|---|---|
| type | 表層の種類(`family`/`given`/`full`) |
| birth_year, death_year | 生年と没年 |
| nationality, field | 国籍と分野 |
| achievement | 主な業績 |
| image, image_page | AI生成の肖像と配布ページ |

すべて架空の人物で、実在人物とは無関係。

## fictional_anime_character.csv

| 列 | 意味 |
|---|---|
| type | `family`/`given`/`full`/`call`/`nick` |
| title | 登場作品 |
| org_name, role_in_org | 所属と役割 |
| first_year | 初登場年 |
| species | 種族 |
| cv_name | 架空の声優名 |
| description | キャラクター紹介 |
| image, image_page | AI生成の肖像と配布ページ |

作品・人物ともに架空。

## fictional_daily_anime_character.csv

列構成は `fictional_anime_character.csv` と同じ。作品・人物ともに架空。

## ryuko.csv

| 列 | 意味 |
|---|---|
| category | `word`/`item`/`fashion`/`play`/`food`/`other` |
| decade | 流行のピークを表す10年区切り |
| era | 平安から令和までの時代区分 |
| year | 代表的な流行年。不明は `NA` |
| sensitive | 災害、事件、政治、成人向け等に由来する語か(`yes`/`no`) |
| description | 何がどう流行したかの短い説明 |

収録基準は [ADR 00031](adr/00031-ryuko-wordlist.md)。

## myoji.csv

| 列 | 意味 |
|---|---|
| verified | 実在人名リスト、Web NDL Authorities、Wikidataの人物姓、または公式人物ページで同じ表記と読みを確認できたか(`yes`/`no`) |
| rank | Wikidata上の著名人数による参考順位 |
| description | 名字や氏族の短い説明 |
| wikidata | 集計に使った姓アイテムのQID |
| evidence_sources | 読みの裏付け。`person_lists` / `ndl` / `wikidata_person` / `official_web` / `jmnedict`を`|`区切りで格納 |

同じ漢字表記に複数の読みがある場合も同じ `id` を使う。`verified=no` は誤りを
意味せず、実在人物で確認できていないことだけを表す。`jmnedict` は辞書収録の
裏付けなので、それ単独では `verified=yes` にしない。詳細は
[ADR 00038](adr/00038-myoji-wordlist.md)と
[ADR 00050](adr/00050-myoji-evidence-sources.md)、
[ADR 00051](adr/00051-myoji-person-evidence.md)。

## gimukyoiku.csv

| 列 | 意味 |
|---|---|
| subject | 教科。複数は `/` 区切り |
| level | 初めて本格的に扱う学校段階。複数は `/` 区切り |
| description | 授業での扱いを示す短い説明 |
| image, image_page | 実写、図版、生成イメージまたはSVG教材図 |
| wikidata | 実写・図版に対応するQID |

教科は9区分、学校段階は `小学校`/`中学校`/`高等学校`。画像内では生成物である
ことを「AIイメージ」「イメージ」等で示す。高等学校は義務教育の範囲外だが、
関連語を継続して利用できるよう収録対象に含める。詳細は
[ADR 00022](adr/00022-gimukyoiku-wordlist.md)。

## municipality.csv

| 列 | 意味 |
|---|---|
| type | `full`(正式名称)/`short`(市区町村の接尾辞を除いた形) |
| municipality_type | 自治体種別。`市`/`区`/`町`/`村` |
| prefecture | 都道府県 |
| parent | 政令指定都市の行政区における親の市 |
| status | `current`(現存)/`former`(廃止・旧名) |
| population | 現存自治体は2020年国勢調査、旧自治体は取得可能な最新値 |
| code | 全国地方公共団体コード |
| description | 自治体の短い説明 |
| image, image_page | Wikidata P18由来のCommons写真、またはP242の位置図と確認先 |
| wikidata | 自治体のQID |

詳細は [ADR 00036](adr/00036-municipality-wordlist.md)。

## school.csv

| 列 | 意味 |
|---|---|
| type | `common`(通用形)/`name`(固有部分)/`nick`(通称・略称) |
| school_type | 幼稚園から大学・高等専門学校までの校種 |
| has_school_suffix | `surface` が一般的な学校名接尾辞（`幼稚園`/`高校`/`小`など）で終わるか。`yes`/`no`。`name` に残る `学院`/`学園` は固有名として `no` |
| founder | `国立`/`公立`/`私立` |
| prefecture, city | 所在地 |
| status | `current`(現存)/`former`(廃校) |
| code | 文部科学省の13桁の学校コード |
| image, image_page | Commons実写。ない場合は校種別の概念イメージ |
| wikidata | 学校のQID |

正式名称は `original` に収録する。通称・略称は出典で確認できたものだけを使う。
詳細は [ADR 00037](adr/00037-school-wordlist.md)。
