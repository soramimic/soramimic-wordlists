# soramimic-wordlists

[Soramimic](https://github.com/jiroshimaya/soramimic)(空耳作詞支援システム)などで使う単語リスト集。
利用側リポジトリからは git submodule で参照する想定。

## 形式(tidy CSV)

全リストはCSV形式。必須列は `id, original, surface`。
**フィールドにカンマ・引用符を含めないこと**(利用側のパーサはクオート非対応の素朴なsplit。URL中のカンマ等は%エンコードする)。
**ファイル末尾に改行を入れないこと**(soramimic側のパーサが最終空行で落ちる)。

| 列 | 意味 |
|---|---|
| id | 単語のグループID(同じ元単語の行は同じid) |
| original | 元の単語(表示用) |
| surface | 変換結果として表示する表層 |
| pronunciation | 読み(カタカナ)。無い場合はsurfaceから推定される。nationsは漢字を含む表記(大韓民国・米国等)で読みが自明でない行に付与し、カタカナだけの行は空 |
| team, type, org_id | リスト固有の付加情報(野球・サッカー等)。`team` は所属チーム名で、baseball/football 共通。**baseballは球団の変遷を連ねた文字列**(`-` が移籍、`・` が改称。例 `巨人-日本ハム`, `大洋・横浜`)、**footballは代表的な1クラブ**(`横浜F・マリノス` のように `・` を含む名前があるので区切り文字として扱わないこと。取得できない行は空。補完は `tools/enrich_football_team.py`) |
| class | sekitsui/plant/insect: 大分類。sekitsuiは魚類/両生類/爬虫類/鳥類/哺乳類、plantは双子葉/単子葉/裸子植物/シダ植物/コケ植物/藻類、insectは主要な目をまとめた粗い区分(甲虫/チョウ/ハチ/ハエ/カメムシ/バッタ/トンボ/その他。カマキリ・ゴキブリ等は「その他」。詳細は ADR 00021)。分類不明はNA |
| extinct | sekitsui/plant/insect: 絶滅種か(yes/no)。IUCN絶滅・野生絶滅、または化石タクソンをyesとする |
| order, family, genus | sekitsui/plant/insect: 分類階級。sekitsui/insectは目・科(`ネコ目`/`ネコ科`、`トンボ目`/`ヤンマ科`)、plantは科・属(`バラ科`/`サクラ属`。植物は目より科・属が一般的な言及単位なので目は持たない)。Wikidataの日本語ラベル(階級付きの別名があればそちら)、無ければ学名。Wikidataに情報が無い行は空。plantは`wikidata`列が空の行も空にする(和名から逆引きすると動物と同名の行で誤った科を拾うため)。補完は `tools/enrich_sekitsui_taxonomy.py` / `tools/enrich_plant_taxonomy.py`(insectは`tools/update_insect.py`が取得時に付与するので専用スクリプトは無い) |
| type1, type2 | pokemon固有: ポケモンのタイプ(でんき等)。単タイプは type2=NA |
| generation | pokemon固有: 登場世代(1〜9)。フォームはそのフォームが導入された世代 |
| status | nations/stations: `current`(現存)/`former`(廃止・脱退・旧称)。stationsは改名前の旧駅名を `renamed` で区別する。youtuberは `current`(活動中)/`former`(卒業・引退・活動終了) |
| category, org, debut_year, channel, subscribers | youtuber固有: 区分(`youtuber`=実在のYouTuber/`vtuber`=VTuber)、所属事務所・グループ(スラッシュ区切り多値、`org~=ホロライブ` で絞り込む前提。無ければNA)、活動開始年(西暦、無ければNA。Wikidataの活動開始(P2031)が無い人はチャンネル開設年で代用しているので、両者が混在する)、メインYouTubeチャンネル名(活動名と違う場合があるので表示・照合用の情報列。読みは付かない。複数チャンネルを持つ人は登録者数が最大の1本を採るので、本人の主戦場と一致しないことがある。無ければNA。詳細は ADR 00029)、**メインチャンネルの登録者数**(出典は YouTube Data API v3。**YouTubeが公開している概数(有効数字3桁)なので正確な人数ではなく、桁の比較・並べ替えに使う**。時変値なので月次バッチで**毎回全行を上書きする**(既存値を書き換えないという方針の明示的な例外)。WikidataにチャンネルID(P2397)が無い人・登録者数を非公開にしている人はNA。詳細は ADR 00030) |
| prefecture, city | stations固有: 駅の所在都道府県・市区町村(同名駅の区別用。1行=1駅) |
| lines | stations固有: 乗り入れ路線(「JR東日本 東北本線」形式、複数は「／」区切り)。Wikidata/Wikipediaに情報が無い駅は空。補完は `tools/enrich_lines.py` |
| image, image_page | 画像のURL(Wikimedia Commons直リンクまたは本リポジトリのGitHub Releaseアセット)と、ライセンス・作者の確認先ページ(stations/baseball/football/scientist/sekitsui/plant/insect/pokemon/fictional_scientist/fictional_anime_character)。画像が無い行は空。利用時はimage_pageのクレジット条件に従うこと。**sekitsui/plant/insectは実写が取れない行に限り、`class`ごとの概念イメージSVG(`class-image-v1` リリース。画像内に「イメージ」と明記)を分類単位で共有して割り当てている**(実写ではないので、実写だけが欲しい利用側は `.../releases/download/class-image-` で始まるURLを除外すること)。**pokemonは写真ではなく全行が「型色カード」SVG**(タイプの配色と文字だけで描いたもの。キャラクター造形は使わない。詳細は ADR 00002)。**youtuberは自由ライセンスの実写(Commons)が取れた人だけ写真で、残りは配色と頭文字と職業アイコンで描いた「象徴カード」SVG**(`images/youtuber/` をrawで参照。画像内に「イメージ」と明記。チャンネルアイコン・サムネイル・キャラクターイラストは一切使わない。カードの配色は本人のイメージカラー(公式が公表しているもの、または公式ポートレートの情報解析で求めた代表色)があればそれを使う。詳細は ADR 00018, 00019) |。**baseball/football も同じく、実写が無い人には所属チームのチームカラーで描いた「選手カード」SVG**を割り当てている(`images/baseball/` `images/football/` をrawで参照。画像内に「イメージ」と明記。ロゴ・エンブレム・マスコット・ユニフォームの意匠は一切使わない。詳細は ADR 00020)。**scientist は肖像が取れない人に分野の配色で描いた「象徴カード」SVG**(`images/scientist/` をrawで参照。肖像画・肖像写真は使わない。分野の色に出典は無い。詳細は ADR 00025)、**stations は写真が取れない駅に汎用の「駅名標」SVG**(`images/station/` をrawで参照。鉄道会社のロゴ・社章・駅ナンバリング・ラインカラーは使わない。詳細は ADR 00026)を割り当てている。**nations は全行がCommonsの国旗**で、消滅国はその国が最後に使っていた旗(詳細は ADR 00026)。実写だけが欲しい利用側は `https://raw.githubusercontent.com/soramimic/soramimic-wordlists/` で始まるURL(本リポジトリの生成カード)を除外すること |
| field | scientist固有: 分野を優先順(物理→化学→数学→天文学→生物学→計算機科学→地学)で並べた単一列のスラッシュ区切り多値(例 `物理/数学`)。切り詰めなし、無ければ`NA`。ソラミミックに部分一致演算子`~=`を追加したので、多値を1列で持ち`field~=物理`で絞り込める(app側 setting.json の対応は別リポジトリ soramimic 側で実施) |
| era, birth_year, nobel, gender, country, status, description | scientist固有: 時代区分(古代/中世/近世/近代/現代/NA。生年basis)・西暦生年(紀元前は「前287」、不明はNA)・科学系ノーベル賞受賞者か(yes/no、照合不能はNA)・性別(男性/女性/その他/NA)・市民権のある国(情報列。複数は"/"、不明はNA)・生死(物故/存命/NA)・主な業績の短い完結文(記事冒頭の先頭生没年カッコを除去し、「。」区切りで完結文を目安90字まで連結。常に「。」で終わる。ASCIIカンマ・引用符除去、無ければNA)。**youtuberの `description` も同じ生成方式**(どんな人かの短い完結文。記事冒頭が無い人はWikidataのja description。詳細は ADR 00029) |
| wikidata | stations: 駅のWikidata QID(差分更新の永続キー)。sekitsui/plant: 画像の取得元になったtaxonのQID(実写画像とセットで埋まるので、実写画像が無い行は空。sekitsui/plantの分類イメージ画像はWikidata由来ではないので空のまま)。youtuber: 本人のQID(画像の有無とは独立に埋まる。同名で複数QIDに当たった人は曖昧として空) |
| birth_year, death_year, nationality, field, achievement | fictional_scientist固有: 生年・没年・国籍・分野・主な業績(AI生成の架空人物情報) |
| title, org_name, role_in_org, first_year, species, cv_name, description | fictional_anime_character固有: 作品名・所属・役割・初登場年・種族・声優名・紹介文(AI生成の架空キャラ情報) |
| subject | gimukyoiku固有: 教科(国語/社会/数学/理科/英語/音楽/美術/保健体育/技術・家庭の9区分。小学校の算数・図工等は対応する中学教科に吸収)。複数教科にまたがる語はスラッシュ区切り多値で `subject~=美術` で絞り込む。descriptionは授業でどう登場する語かの短い説明(「。」終わり)。imageは全行にあり、実写・図版(語と完全一致するja.wikipedia記事のリード画像。777行、wikidataはその記事のQID)と、実写が無い語の**生成イメージ**(`gimukyoiku-image-v1`/`-v1b` リリース。SD生成の「AIイメージ」またはタイポグラフィカードの「イメージ」を画像内に明記。歴史上の人物は想像画、近現代の実在人物の肖像は含まない。詳細は ADR 00027/00028)。補完は `tools/enrich_gimukyoiku_images.py` と `tools/apply_gimukyoiku_ai_images.py` |
| category, decade, era, year | ryuko固有: 流行の種類(`word`=流行語・言い回し/`item`=モノ・商品/`fashion`=服装・髪型・化粧/`play`=遊び・娯楽・芸能/`food`=飲食/`other`)、流行のピークの10年区切り(「1980年代」形式。前近代はピークが幅でしか分からないので代表的な10年。`decade=1980年代` の完全一致で絞り込む)、時代区分(平安/鎌倉/室町/安土桃山/江戸/明治/大正/昭和/平成/令和)、代表的な流行年(西暦4桁、特定できない語はNA)。descriptionは何がどう流行ったかの短い説明(「。」終わり)。収録・除外基準は ADR 00031 |

## リスト一覧

| ファイル | 内容 | 出典・クレジット |
|---|---|---|
| baseball.csv | プロ野球選手・歴代(type: family/given/full/registered。所属球団・画像URL付き) | Moto(選手表ニキ)様と協力者の皆様。現役の新規追加は[Wikipedia](https://ja.wikipedia.org/) (CC BY-SA 4.0)で自動更新。写真は[Wikimedia Commons](https://commons.wikimedia.org/)(ライセンスは画像ごと。image_page参照)、実写が無い人の選手カード画像は本リポジトリの `images/baseball/`(Apache License 2.0 の職業アイコンを含む。実写ではない。下の「利用上の注意」参照) |
| football.csv | サッカー選手(J1〜J3・歴代。所属クラブ・画像URL付き) | ヨロスー様。現役の新規追加はWikipediaで自動更新。所属クラブはWikipedia/[Wikidata](https://www.wikidata.org/)。写真は[Wikimedia Commons](https://commons.wikimedia.org/)(ライセンスは画像ごと。image_page参照)、実写が無い人の選手カード画像は本リポジトリの `images/football/`(Apache License 2.0 の職業アイコンを含む。実写ではない。下の「利用上の注意」参照) |
| stations.csv | 駅名(現役駅+路面電車・索道。所在地・写真URL付き) | [Wikidata](https://www.wikidata.org/)/[Wikipedia](https://ja.wikipedia.org/) (CC BY-SA 4.0) で自動更新。旧リストはすきやきすきや様。写真は[Wikimedia Commons](https://commons.wikimedia.org/)(ライセンスは画像ごと。image_page参照)、写真が無い駅の駅名標画像は本リポジトリの `images/station/`(実写ではない。鉄道会社の意匠は含まない。詳細は ADR 00026) |
| nations.csv | 国名(国連加盟国+消滅国・旧称。正式名称・通称・漢字略称・別読み・別カナ表記を同一idで併記。国旗URL付き) | [mledoze/countries](https://github.com/mledoze/countries) で自動更新。別表記は[Wikipedia](https://ja.wikipedia.org/) (CC BY-SA 4.0)等を参照して手動追加。国旗は[Wikidata](https://www.wikidata.org/)(P41)経由で[Wikimedia Commons](https://commons.wikimedia.org/)(ライセンスは画像ごと。image_page参照。国旗はほぼすべてPD) |
| scientist.csv | 科学者(物理/化学/数学/天文/生物/計算機/地学。分野・時代区分・生没・国・性別・ノーベル賞・業績説明・画像URL付き。手選び+著名層) | Wikidata/Wikipediaで自動更新。肖像は[Wikimedia Commons](https://commons.wikimedia.org/)(ライセンスは画像ごと。image_page参照)、肖像が無い人の象徴カード画像は本リポジトリの `images/scientist/`(Apache License 2.0 の分野アイコンを含む。実写ではない。下の「利用上の注意」参照) |
| sekitsui.csv | 動物(脊椎動物。分類・絶滅フラグ・目/科・画像URL付き) | [Wikidata](https://www.wikidata.org/) (CC0) で自動更新。写真は[Wikimedia Commons](https://commons.wikimedia.org/)(ライセンスは画像ごと。image_page参照)、実写が無い行の分類イメージ画像は本リポジトリのReleaseで配布(CC0・実写ではない) |
| plant.csv | 植物(被子/裸子/シダ/コケ/藻類の和名。分類・絶滅フラグ・科/属・写真URL付き) | [Wikidata](https://www.wikidata.org/) (CC0) で自動更新。写真は[Wikimedia Commons](https://commons.wikimedia.org/)(ライセンスは画像ごと。image_page参照)、実写が無い行の分類イメージ画像は本リポジトリのReleaseで配布(CC0・実写ではない) |
| insect.csv | 昆虫(昆虫綱の和名。粗い区分・絶滅フラグ・目/科・写真URL付き。クモ・ムカデ等の非昆虫は含まない) | [Wikidata](https://www.wikidata.org/) (CC0) で自動更新。写真は[Wikimedia Commons](https://commons.wikimedia.org/)(ライセンスは画像ごと。image_page参照)、実写が無い行の分類イメージ画像は本リポジトリのReleaseで配布(CC0・実写ではない) |
| pokemon.csv | ポケモン(地方のすがた・メガ・キョダイマックス含む。タイプ配色のみで描いた「型色カード」画像付き) | [PokéAPI](https://github.com/PokeAPI/pokeapi) で自動更新。画像は本リポジトリのReleaseで配布(公式アセット・キャラクター造形は使わず配色と文字のみ)。本リポジトリは非公式のファンメイドであり株式会社ポケモン・任天堂等とは無関係 |
| youtuber.csv | YouTuber・VTuber(ja.wikipediaに記事がある著名層。海外勢含む。活動名のみ、type: family/given/full。category列で区分、所属・活動開始年・status・チャンネル名・登録者数・説明文・画像URL付き) | Wikidata/Wikipedia (CC BY-SA 4.0) で自動更新。登録者数(`subscribers`)のみ [YouTube Data API v3](https://developers.google.com/youtube/v3) から取得(YouTubeが公開している概数)。写真は[Wikimedia Commons](https://commons.wikimedia.org/)の自由ライセンスの実写のみ(ライセンスは画像ごと。image_page参照)、実写が無い人の象徴カード画像は本リポジトリの `images/youtuber/`(Apache License 2.0 の職業アイコンを含む。実写ではない。下の「利用上の注意」参照) |
| fictional_scientist.csv | AI生成による架空の科学者1000人(名前・読み・生没年・国籍・分野・主な業績・肖像画像。type: family/given/full) | jiroshimaya/fictional-scientists プロジェクトによる自動生成(実在人物とは無関係)、画像は本リポジトリのReleaseで配布 |
| fictional_anime_character.csv | AI生成による架空アニメ『蒼穹の螺旋航路』の登場キャラ1000人(名前・読み・所属・初登場年・種族・声優名・紹介文・肖像画像。type: family/given/full/call/nick。callは作中で使われる呼び名(敬称込み)、nickはあだ名) | jiroshimaya/fictional-scientists プロジェクトによる自動生成(実在の作品・人物とは無関係)、画像は本リポジトリのReleaseで配布 |
| fictional_daily_anime_character.csv | AI生成による架空日常アニメ『まちまる！』の住人1025人(名前・読み・所属・初登場年・種族・声優名・紹介文・肖像画像。type: family/given/full/call/nick。callは作中で使われる呼び名(敬称込み)、nickはあだ名) | jiroshimaya/fictional-scientists プロジェクトによる自動生成(実在の作品・人物とは無関係)、画像は本リポジトリのReleaseで配布 |
| ryuko.csv | 年代別の流行(平安〜令和。流行語・モノ・遊び・ファッション・食べ物。10年区切りのdecade・時代区分era・流行年・説明文付き。災害・事件由来や成人向けの語は収録しない。詳細は ADR 00031) | 新語・流行語大賞受賞語(1984〜)は[Wikipedia](https://ja.wikipedia.org/wiki/%E6%96%B0%E8%AA%9E%E3%83%BB%E6%B5%81%E8%A1%8C%E8%AA%9E%E5%A4%A7%E8%B3%9E) (CC BY-SA 4.0)から機械抽出。それ以外はWikipedia等で裏取りしたAIキュレーション(自動更新なし) |
| gimukyoiku.csv | 義務教育(小中学校)の教科書・授業に登場する単語(教科フィルタ・説明文・画像URL付き。学習用語に加え授業で扱う人名・作品名・事件名を含む) | AI生成による手動キュレーション(本リポジトリ内で作成、自動更新なし。詳細は ADR 00022)。写真・図版は[Wikimedia Commons](https://commons.wikimedia.org/)(ライセンスは画像ごと。image_page参照)、実写が無い語は本リポジトリのReleaseで配布する生成イメージ(CC0・実写ではない。画像内に「AIイメージ」等と明記。詳細は ADR 00027/00028) |

## 利用上の注意

- 本リポジトリは非公式のファンメイド・データ集であり、各作品・団体・人物とは無関係です
- 空耳変換の研究・個人利用を想定しています。各リストの元データの帰属・ライセンスは上表の出典欄を参照してください(Wikidata由来はCC0、Wikipedia由来はCC BY-SA 4.0、nationsは[mledoze/countries](https://github.com/mledoze/countries)(ODbL)由来)
- 実在人物名のリスト(baseball/football/scientist/youtuberのcategory=youtuber)は公表済みの事実情報(名簿)のみで構成しています。氏名の営利的な顧客誘引を目的とする利用(パブリシティ権に触れうる利用)は行わないでください。youtuberは記事名(活動名)のみを収録し、本名は収録しません(`description` も本名の記述を落としてから収録しています。詳細は ADR 00029)
- youtuber.csvのcategory=vtuberの行は各社(カバー・ANYCOLOR等)の知的財産であるキャラクター名です。名称と読みのみを非商用のファンメイド用途で収録しています(キャラクターデザイン・アバターのイラストやスクリーンショットは画像として一切収録していません。詳細は ADR 00018)
- baseball/football の生成カードは、公表された事実であるチームカラー(色の値)と、職業を表す汎用アイコンだけで描いたものです。球団・クラブのロゴ・エンブレム・マスコット・ユニフォームの意匠は一切含みません(詳細は ADR 00020, 00024)
- scientist の生成カードは、分野の配色と姓の頭文字と分野を表す汎用アイコンだけで描いたものです。肖像画・肖像写真は一切含みません。**分野の配色はこのリポジトリが見分けやすさのために決めたもので、学問分野の標準的な色ではありません**(詳細は ADR 00025)
- stations の生成画像は、白地の板に駅名とかな読みを置いただけの汎用の駅名標です。**実在の鉄道会社のロゴ・社章・駅ナンバリング・専用書体・ラインカラーは一切含みません**。帯の色は路線名から機械的に決めたもので、路線の実際のラインカラーではありません(詳細は ADR 00026)
- **生成カード画像(職業アイコン・分野アイコン)の帰属**: `images/baseball/` `images/football/` `images/youtuber/` `images/scientist/` の生成カードSVGは、職業・分野を表すアイコンとして [Material Symbols](https://github.com/google/material-design-icons)(Google, **Apache License 2.0**)を含みます(カード生成器 `tools/material_icons.py` も同様)。ライセンス全文は `LICENSE-APACHE-2.0-material-symbols` です。パスデータは改変しておらず、カードの座標系へ収める `transform` を外側に巻いているだけです。**これらのカード画像は CC0 ではありません**。再配布・二次利用の際は Apache License 2.0 の帰属表示に従ってください(各SVGの `<desc>` にも1行の帰属を埋めてあります)。**CSVのテキストデータそのものは従来どおり**で、この帰属義務は生成カード画像にのみ及びます(詳細は ADR 00024, 00025)。`images/station/` の駅名標SVGは Material Symbols を含まないので、この帰属義務は生じません
- 掲載内容について権利者からの申し出があれば速やかに対応します(Issueにてご連絡ください)

## 自動更新

ネット上の公開データから自動更新できるリストは、GitHub Actions
(`.github/workflows/update-wordlists.yml`)で月1回(毎月6日)バッチ実行し、
差分があればPRが作られる(要リポジトリ設定: Settings > Actions > General >
「Allow GitHub Actions to create and approve pull requests」)。
作られたPRはAIレビュー(`review-auto-update.yml`。Gemini API無料枠を使用、
要 `GEMINI_API_KEY` シークレット)が追加行の品質を確認し、問題なければCI通過後に
automergeで自動マージされる。不安があればPRコメントで報告され、マージは
人間の確認待ちになる。
youtuber.csv の登録者数(`subscribers`)の更新には `YOUTUBE_API_KEY` シークレット
(YouTube Data API v3 のAPIキー)が要る。未設定でもバッチは壊れず、そのステップだけ
がスキップされる。
手動実行は Actions タブの workflow_dispatch から。ローカルでは:

```sh
python3 tools/update_pokemon.py    # PokéAPIの公式CSVから全件再生成(id=全国図鑑No-1)
python3 tools/update_nations.py    # 国連加盟国の増減を検出し新規のみ追記
python3 tools/update_stations.py   # Wikidata/Wikipediaと突き合わせ、新駅追記+status更新
python3 tools/update_baseball.py   # NPB現役ロースターから未収録選手を追記
python3 tools/update_football.py   # J1〜J3ロースターから未収録選手を追記
python3 tools/update_scientist.py  # Wikidataの著名科学者(7分野・sitelinks>=20)で生成
python3 tools/update_sekitsui.py   # Wikidataの脊椎動物(rank=種・カタカナ和名)を追記
python3 tools/update_plant.py      # Wikidataの植物(rank=種・カタカナ和名)を追記
python3 tools/update_insect.py    # Wikidataの昆虫(rank=種・カタカナ和名)を追記
python3 tools/update_youtuber.py   # WikidataのYouTuber/VTuber(ja記事あり)を追記
python3 tools/update_youtuber_subscribers.py  # 登録者数を全行上書き(要 YOUTUBE_API_KEY)
python3 tools/enrich_images.py     # 画像が空の人物行にCommons画像を遡及付与
python3 tools/audit_taxa.py sekitsui  # 既存行が想定した界・門・綱の配下か検査(読み取り専用)
```

- pokemon: 全件再生成。フォームは「ライチュウ（アローラのすがた）」形式で
  表記ゆれ3行を同一idで収録。種とフォームは別ポケモンとして別id
  (詳細は ADR 00002)。`image`/`image_page` は `original`(名前)から機械的に
  組み立てるので全件再生成でも消えない。**カードのファイル名も名前由来
  (`pkm_<sha1(名前)先頭10桁>.svg`)なので、新種追加で id がずれても既存のURLが
  別のポケモンのカードを指すことはない。**
  **新ポケモンが追加された回は型色カードを追加して Release を更新すること**
  (アセットが無い名前は画像が404。増えた分だけ送ればよく、既存カードの
  作り直しは不要):
  ```sh
  # 増分だけアップロード(レート制限で途中終了したときの再開にも使える)
  python3 tools/gen_pokemon_typecards.py --out build/pokemon_typecards \
      --upload --only-missing
  # CSVの全 original に対応するアセットがReleaseにあるか検査
  python3 tools/gen_pokemon_typecards.py --verify
  ```
  Releaseは1つあたり1000アセットが上限なので、ハッシュで
  `pokemon-typecard-v2` / `pokemon-typecard-v2b` の2つに振り分けている
  (旧 `-v1` / `-v1b` は id 連番のファイル名。参照されていないが残してある)。
  総枚数が2000枚に近づいたら `RELEASE_BUCKETS` を増やし、タグを v3 に上げて
  全枚数を再アップロードすること
- nations: 既存行の表記・idは変更しない。新規加盟の追記と status の更新のみ。
  ISOコードとの対応は `tools/nations_map.csv` で管理。正式名称(大韓民国)・
  通称(北朝鮮)・漢字略称(米国)・別読み(ニッポン)・別カナ表記(テュルキエ)は
  同じ id の行を手動で追加する。正式名称は通称と表記が異なる限り原則すべての
  国に付与する(ブルンジ共和国のような定型の「〜共和国」も、長い名称も足す)。
  追加行は `nations_map.csv` には登録しない
  (登録済みの original と一致しないので自動更新に巻き込まれない)
  (詳細は ADR 00003)。国旗は月次バッチには入れず手動実行で補完する:
  ```sh
  # Wikidata(P41)経由でCommonsの国旗を付与(image列が空の行だけ)
  python3 tools/enrich_nation_flags.py
  ```
  消滅した国(ソ連・ユーゴスラビア・チェコスロバキア・東西ドイツ)と旧称
  (セイロン・ザイール・ビルマ)には cca3 が無いので、`enrich_nation_flags.py` の
  `FORMER_STATES` で表記ごとにWikidataのitemを直接指し、**その国が最後に使っていた旗**
  (P41の優先ランク→適用終了が最も新しいもの)を選ぶ。ユーゴスラビア王国と
  ユーゴスラビア社会主義連邦共和国のように、同じidでも表記ごとに旗が違う
  (詳細は ADR 00026)
- stations: 1行=1駅(Wikidata QIDが永続キー)。既存行は書き換えず、新駅の追記と
  status の更新のみ。新駅の読みはWikipedia冒頭文から抽出(詳細は ADR 00004)。
  自由ライセンスの写真が無い駅(160駅)には、**どの鉄道会社のものでもない汎用の
  駅名標**SVGを割り当てて全行を埋めている。これは月次バッチには入れず手動実行する
  (詳細は ADR 00026):
  ```sh
  # 写真が無い駅に駅名標を生成して割り当てる(写真のある行は触らない)
  python3 tools/gen_station_signs.py         # --prune で不要SVGを削除
  ```
  画像は `images/station/` に置き、CSVからは raw URL で参照する。**ロゴ・社章・
  駅ナンバリングの丸・専用書体・ラインカラーは一切使わず**、白地の板に駅名と
  かな読み、上下の帯、支柱だけで描く。帯の色は路線名のハッシュで、路線の実際の
  ラインカラーではない(このリポジトリは路線カラーの出典を持たないため)。
  実写と誤認されないよう画像内に「イメージ」と明記する
- baseball/football: 既存データ(歴代名鑑・手選び)は保持し、
  未収録の現役選手だけ追記。姓名分割済みの読みは記事冒頭
  「姓 名(せい めい、」から取得(詳細は ADR 00005)。
  football の `team`(所属クラブ)は月次バッチには入れず手動実行で補完する
  (詳細は ADR 00016):
  ```sh
  # 現役はJ1〜J3のロースター、歴代はWikidataの所属クラブ(P54)から
  # 「最新の所属」を1つ選んで付与(空欄のみ。--refreshで全行)
  python3 tools/enrich_football_team.py
  ```
  取得結果を `tools/.cache/`(Git管理外)に逐次保存するので、中断しても
  再実行で続きから再開する(全件引き直したいときはキャッシュを消す)。
  自由ライセンスの実写が取れるのは baseball 37% / football 9% だけなので、
  **実写が無い人には所属チームのチームカラーで描いた「選手カード」SVG**を
  割り当てて全行を埋めている。これも月次バッチには入れず手動実行する
  (詳細は ADR 00020, 00024):
  ```sh
  # チームカラーを集める(tools/team_colors.json。--report で取れなかったチーム)
  python3 tools/fetch_team_colors.py
  # 実写が無い人にカードを生成して割り当てる(実写のある行は触らない)
  python3 tools/gen_player_cards.py          # --prune で不要SVGを削除
  ```
  カードは `images/baseball/` `images/football/` に置き、CSVからは raw URL で
  参照する。**球団・クラブのロゴ・エンブレム・マスコット・ユニフォームの意匠は
  一切使わず**、公表されたチームカラーの配色と名前の頭文字、職業を表す汎用アイコン
  (Material Symbols)、自作の競技のボールだけで描く。名前・区分・所属の文字は
  カードに入れない(動画側のレイアウトが描くため。詳細は ADR 00024)。
  実写と誤認されないよう画像内に「イメージ」と明記する。
  色の出典は Wikipedia のインフォボックスに**テキストで**書かれた色だけで、
  消滅球団(南海・阪急・大洋など)は当時の色が引けないため推測せず、チーム名の
  ハッシュ由来のフォールバック配色にしている
- scientist: 旧 physicist.csv を広義の科学者リストに拡張・リネーム。Wikidataの
  職業(P106)が物理/化学/数学/天文/生物/計算機科学/地学のいずれかで sitelinks>=20 の
  人物を対象に、分野(field。スラッシュ区切り多値)・時代(era)・生年・ノーベル賞・性別・国・
  生死・業績説明(description)を付与。既存の手選び行は保持し、未収録者を追記。読みは
  記事冒頭から取得(詳細は ADR 00009)。
  自由ライセンスの肖像が取れない289人には、**分野の配色で描いた「象徴カード」SVG**を
  割り当てて全行を埋めている。これも月次バッチには入れず手動実行する
  (詳細は ADR 00025, 00024):
  ```sh
  # 肖像が無い人にカードを生成して割り当てる(肖像のある行は触らない)
  python3 tools/gen_scientist_cards.py       # --prune で不要SVGを削除
  ```
  カードは `images/scientist/` に置き、CSVからは raw URL で参照する。**肖像画・肖像写真は
  一切使わず**、分野の配色と姓の頭文字、分野を表す汎用アイコン(Material Symbols)
  だけで描く。名前・分野・国の文字はカードに入れない(動画側のレイアウトが描くため。
  詳細は ADR 00024)。ノーベル賞受賞者だけ右下に自作の星を置く。
  分野の色に出典は無く、7分野を見分けるためにこのリポジトリが決めたものである
- sekitsui: Wikidataの脊椎動物(rank=種・日本語ラベルがカタカナ)を綱ごとに
  取得し、未収録の和名だけ追記。和名がそのまま読みになるので読み抽出は不要。
  `class` 列に大分類(魚類/両生類/爬虫類/鳥類/哺乳類)、`extinct` 列に絶滅種か
  (yes/no)を付与し、化石種も含める(詳細は ADR 00007)。
  目・科(`order`/`family`)は月次バッチには入れず手動実行で補完する
  (詳細は ADR 00015):
  ```sh
  # Wikidataの親タクソン(P171)を辿って目・科を付与(空欄のみ。--refreshで全行)
  python3 tools/enrich_sekitsui_taxonomy.py
  # 画像が空の行にCommons画像(P18)を遡及付与(概念イメージの行は実写で上書き)
  python3 tools/enrich_sekitsui_images.py
  ```
  enrich_sekitsui_taxonomy は取得結果を `tools/.cache/`(Git管理外)に逐次
  保存するので、中断しても再実行で続きから再開する(全件引き直したいときは
  キャッシュを消す)。
  実写画像が取れない行(約2,700行)には、`class` ごとの**概念イメージ**SVGを
  分類単位で共有して割り当てる。画像は `tools/gen_class_images.py` で生成して
  GitHub Release(`class-image-v1`)で配布し、`tools/apply_class_images.py` が
  image列が空の行だけに割り当てる(月次バッチにも入っているので、新規追加行にも
  自動で付く)。実写と誤認されないよう画像内に「イメージ」と明記してある
  (詳細は ADR 00007):
  ```sh
  python3 tools/gen_class_images.py --group sekitsui --out /tmp/class_images
  python3 tools/apply_class_images.py sekitsui   # 実写のある行は触らない
  ```
- plant: sekitsuiと同じ方式の植物版。被子植物は巨大で一括取得がタイムアウト
  するため目(order)ごとに分割し、単子葉/双子葉に振り分ける。非被子植物は門
  ごとに取得。`class` 列に大分類(双子葉/単子葉/裸子植物/シダ植物/コケ植物/
  藻類)、`extinct` 列に絶滅種か(yes/no)を付与(詳細は ADR 00008)。
  画像(`image`/`image_page`/`wikidata`)と科・属(`family`/`genus`)は
  sekitsuiと同じく月次バッチには入れず手動実行で補完する(科・属の詳細は
  ADR 00017):
  ```sh
  # 画像が空の行にCommons画像(P18)を遡及付与(--refreshで全目・全門を引き直す)
  python3 tools/enrich_plant_images.py
  # Wikidataの親タクソン(P171)を辿って科・属を付与(空欄のみ。--refreshで全行)
  python3 tools/enrich_plant_taxonomy.py
  ```
  取得は目・門ごと(画像)/ノードごと(科・属)に `tools/.cache/`(Git管理外)へ
  逐次保存するので、中断しても再実行で続きから再開する。
  科・属は `wikidata` 列に QID がある行だけを対象にする(和名から逆引きすると
  スギ・ハス等で動物側のタクソンを拾うため)。木を辿る処理は
  `tools/taxonomy.py` にあり、sekitsui の目・科と共通。
  実写画像が取れない行(743行)には、sekitsuiと同じ仕組みで `class` ごとの
  **概念イメージ**SVGを分類単位で共有して割り当てる(画像は `class-image-v1`
  リリースで配布。画像内に「イメージ」と明記。詳細は ADR 00008):
  ```sh
  python3 tools/gen_class_images.py --group plant --out /tmp/class_images
  python3 tools/apply_class_images.py plant   # 実写のある行は触らない
  ```
- insect: Wikidataの昆虫綱 Insecta(Q1390)配下の種(rank=種・日本語ラベルが
  カタカナ)。クモ・ダニ・ムカデ等の非昆虫節足動物は含まない(将来 arthropod
  として別リストにする)。昆虫はWikidataのtaxonが100万件規模で、綱の一括はもちろん
  **目単位でもコウチュウ目はWDQSがタイムアウトする**ため、昆虫綱から下向きに
  辿って集めた目ごとに引き、失敗した対象は子タクソンへ再帰的に分割する。
  `class` 列は目そのものではなく**主要7目をまとめた粗い区分**(甲虫/チョウ/ハチ/
  ハエ/カメムシ/バッタ/トンボ/その他)。目・科(`order`/`family`)は取得時の
  taxon QIDから上位を辿って同時に付ける(和名からの逆引きはしない)。
  和名が脊椎動物・植物と衝突するもの(カマキリ・トンボ・セミ等)は
  **クエリの起点を昆虫綱側に閉じる**ことで取り違えを防ぎ、書き込み前に
  昆虫綱Q1390への到達と脊椎動物Q25241/植物界Q756への非到達を確認する
  (詳細は ADR 00021)。
  画像(`image`/`image_page`/`wikidata`)はsekitsui/plantと同じく月次バッチには
  入れず手動実行で補完する:
  ```sh
  # 画像が空の行にCommons画像(P18)を遡及付与(--refreshで全対象を引き直す)
  python3 tools/enrich_insect_images.py
  # 実写が無い行に class ごとの概念イメージを割り当てる
  python3 tools/gen_class_images.py --group insect --out /tmp/class_images
  python3 tools/apply_class_images.py insect   # 実写のある行は触らない
  ```
  取得は対象ごとに `tools/.cache/`(Git管理外)へ逐次保存するので、中断しても
  再実行で続きから再開する
- youtuber: Wikidataの職業(P106)がYouTuber/バーチャルYouTuberで
  ja.wikipediaに記事がある人物のみ。1ファイルに収録し category 列
  (youtuber/vtuber)で区別する。記事名(活動名)のみ収録し本名は取得しない。
  読みは記事冒頭「名前（よみ、」から抽出(かな名は自身から変換)。既存行は
  書き換えず、未収録者の追記と status(current→former)の一方向更新、
  org/debut_year/channel/description の空欄補完のみ。org(所属)・
  debut_year(活動開始年)・channel(メインチャンネル名)・description(短い説明文)付き
  (debut_year は P2031(活動開始)を優先し、無ければ P2397 の修飾子 P580 =
  チャンネル開設年を使う。channel は P2397 の修飾子 P1810 で、複数チャンネルは
  登録者数 P3744 が最大の1本。description は scientist と同じ生成方式で
  記事冒頭から目安90字の完結文。**記事冒頭には本名がよく書かれているので、
  「本名は〜」の文と「{本名}は、活動名として知られる〜」の主語は description に
  入れる前に機械的に落としている**。詳細は ADR 00011, 00012, 00023, 00029)。
  **`subscribers`(メインチャンネルの登録者数)だけは別スクリプトで、毎回全行を
  上書きする**(登録者数は時変値なので、古い値を残すと「いつの値か分からない列」に
  なる。空欄補完のみという方針の明示的な例外。詳細は ADR 00030):
  ```sh
  # 要 YouTube Data API v3 のキー。環境変数 YOUTUBE_API_KEY か
  # ~/.config/soramimic/youtube_api_key に置く(キーが無ければスキップして正常終了)
  python3 tools/update_youtuber_subscribers.py
  ```
  チャンネルIDはWikidataのP2397から引き、1人が複数チャンネルを持つ場合は
  **最大の登録者数**を採る(`channel` のメイン判定と同じ基準)。値はYouTubeが
  公開している**概数(有効数字3桁)**で、取得できない人はNA。全チャンネルの取得が
  成功してから1回だけ書くので、途中で失敗しても書きかけは残らない。
  **成人向け(アダルト)業界の職業(AV女優・ポルノ俳優・アダルトモデル・
  セックスワーカー等)がP106に付いている人物は、YouTube/VTuber活動があっても
  収録しない**(一般向けアプリのサンプル単語リストとして使うため。P106は現職と
  元職を区別しないので元AV女優も対象。除外職業のQIDは
  `tools/update_youtuber.py` の `EXCLUDED_OCCUPATIONS`。グラビアアイドル・
  グラビアモデルは成人向け業界とは別カテゴリなので除外しない)。
  画像(`image`/`image_page`/`wikidata`)は月次バッチには入れず手動実行で補完する
  (詳細は ADR 00018, 00019):
  ```sh
  # 自由ライセンスの実写(Commons)とQIDを付与。イラスト・アバター・コスプレは採らない
  python3 tools/enrich_youtuber_images.py            # --report で不採用の内訳
  # 公式が公表しているイメージカラーを集める(要 Pillow。tools/youtuber_colors.json)
  python3 tools/fetch_youtuber_colors.py             # --audit で読み取り結果を全件表示
  # 公式色が無いVTuberは、公式ポートレートを情報解析して代表色を最大2色求める
  python3 tools/derive_youtuber_colors.py            # --validate で手法の検算(ΔE00)
  # 実写が無い人に「象徴カード」SVGを生成して割り当てる(実写のある行は触らない)
  python3 tools/gen_youtuber_cards.py               # --prune で不要SVGを削除
  ```
  Wikidata/Commons/公式サイト への問い合わせ結果は `tools/.cache/`(Git管理外)へ
  逐次保存するので、中断しても再実行で続きから再開する(引き直したいときは
  `--refresh`)。
  **チャンネルアイコン・動画サムネイル・キャラクターイラストは使わない**方針で、
  VTuberはほぼ全員が象徴カードになる。カードは `images/youtuber/` に置き、
  CSVからは raw URL で参照する。
  カードの配色は**本人のイメージカラー**(`tools/youtuber_colors.json`)を優先し、
  分からない人は category と org から決める。色の出典は次の3つで、`source` 列で
  区別できる。
  1. 色を**テキストで公表している公式サイト**(`official`)
  2. 公式ライブの**ペンライトカラー一覧画像**(`official-penlight`)
  3. 公式サイトの**ポートレート画像を情報解析**(著作権法30条の4)して求めた
     代表色(`derived-portrait`。VTuberのみ。詳細は ADR 00019)

  3. で解析に使った画像も 2. の一覧画像も `tools/.cache/`(Git管理外)止まりで
  **リポジトリに置かない・再配布しない**。コミットするのは色の値だけで、
  カードは配色と頭文字と汎用アイコンだけのSVGのまま(イラストの貼り込み・
  トレースはしない)
- 自動更新の対象外は fictional_scientist(外部プロジェクトで生成したCSVを
  取り込む方式。詳細は ADR 00006)と gimukyoiku(AI生成による手動キュレーション。
  追加・修正は通常のPRで行う。詳細は ADR 00022)

設計判断の記録は [docs/adr/](docs/adr/) を参照。

## メンテナンス

- `tools/` に整備用スクリプト(uv管理)
- 提供データの一括取り込みなど手動での更新手順は [docs/](docs/) 参照
- 更新したら利用側リポジトリで submodule を更新する:
  ```sh
  git submodule update --remote wordlists
  ```
