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
| team, type, org_id | リスト固有の付加情報(野球・サッカー等)。`team` は所属チーム名で、baseball/football 共通(footballは代表的な1クラブ。取得できない行は空。補完は `tools/enrich_football_team.py`) |
| class | sekitsui/plant: 大分類。sekitsuiは魚類/両生類/爬虫類/鳥類/哺乳類、plantは双子葉/単子葉/裸子植物/シダ植物/コケ植物/藻類。分類不明はNA |
| extinct | sekitsui/plant: 絶滅種か(yes/no)。IUCN絶滅・野生絶滅、または化石タクソンをyesとする |
| order, family, genus | sekitsui/plant: 分類階級。sekitsuiは目・科(`ネコ目`/`ネコ科`)、plantは科・属(`バラ科`/`サクラ属`。植物は目より科・属が一般的な言及単位なので目は持たない)。Wikidataの日本語ラベル(階級付きの別名があればそちら)、無ければ学名。Wikidataに情報が無い行は空。plantは`wikidata`列が空の行も空にする(和名から逆引きすると動物と同名の行で誤った科を拾うため)。補完は `tools/enrich_sekitsui_taxonomy.py` / `tools/enrich_plant_taxonomy.py` |
| type1, type2 | pokemon固有: ポケモンのタイプ(でんき等)。単タイプは type2=NA |
| generation | pokemon固有: 登場世代(1〜9)。フォームはそのフォームが導入された世代 |
| status | nations/stations: `current`(現存)/`former`(廃止・脱退・旧称)。stationsは改名前の旧駅名を `renamed` で区別する。youtuberは `current`(活動中)/`former`(卒業・引退・活動終了) |
| category, org, debut_year | youtuber固有: 区分(`youtuber`=実在のYouTuber/`vtuber`=VTuber)、所属事務所・グループ(スラッシュ区切り多値、`org~=ホロライブ` で絞り込む前提。無ければNA)、活動開始年(西暦、無ければNA) |
| prefecture, city | stations固有: 駅の所在都道府県・市区町村(同名駅の区別用。1行=1駅) |
| lines | stations固有: 乗り入れ路線(「JR東日本 東北本線」形式、複数は「／」区切り)。Wikidata/Wikipediaに情報が無い駅は空。補完は `tools/enrich_lines.py` |
| image, image_page | 画像のURL(Wikimedia Commons直リンクまたは本リポジトリのGitHub Releaseアセット)と、ライセンス・作者の確認先ページ(stations/baseball/football/scientist/sekitsui/plant/pokemon/fictional_scientist/fictional_anime_character)。画像が無い行は空。利用時はimage_pageのクレジット条件に従うこと。**sekitsui/plantは実写が取れない行に限り、`class`ごとの概念イメージSVG(`class-image-v1` リリース。画像内に「イメージ」と明記)を分類単位で共有して割り当てている**(実写ではないので、実写だけが欲しい利用側は `.../releases/download/class-image-` で始まるURLを除外すること)。**pokemonは写真ではなく全行が「型色カード」SVG**(タイプの配色と文字だけで描いたもの。キャラクター造形は使わない。詳細は ADR 00002)。**youtuberは自由ライセンスの実写(Commons)が取れた人だけ写真で、残りは配色と文字だけで描いた「象徴カード」SVG**(`images/youtuber/` をrawで参照。画像内に「イメージ」と明記。チャンネルアイコン・サムネイル・キャラクターイラストは一切使わない。カードの配色は公式が公表している本人のイメージカラーがあればそれを使う。詳細は ADR 00018) |
| field | scientist固有: 分野を優先順(物理→化学→数学→天文学→生物学→計算機科学→地学)で並べた単一列のスラッシュ区切り多値(例 `物理/数学`)。切り詰めなし、無ければ`NA`。ソラミミックに部分一致演算子`~=`を追加したので、多値を1列で持ち`field~=物理`で絞り込める(app側 setting.json の対応は別リポジトリ soramimic 側で実施) |
| era, birth_year, nobel, gender, country, status, description | scientist固有: 時代区分(古代/中世/近世/近代/現代/NA。生年basis)・西暦生年(紀元前は「前287」、不明はNA)・科学系ノーベル賞受賞者か(yes/no、照合不能はNA)・性別(男性/女性/その他/NA)・市民権のある国(情報列。複数は"/"、不明はNA)・生死(物故/存命/NA)・主な業績の短い完結文(記事冒頭の先頭生没年カッコを除去し、「。」区切りで完結文を目安90字まで連結。常に「。」で終わる。ASCIIカンマ・引用符除去、無ければNA) |
| wikidata | stations: 駅のWikidata QID(差分更新の永続キー)。sekitsui/plant: 画像の取得元になったtaxonのQID(実写画像とセットで埋まるので、実写画像が無い行は空。sekitsui/plantの分類イメージ画像はWikidata由来ではないので空のまま)。youtuber: 本人のQID(画像の有無とは独立に埋まる。同名で複数QIDに当たった人は曖昧として空) |
| birth_year, death_year, nationality, field, achievement | fictional_scientist固有: 生年・没年・国籍・分野・主な業績(AI生成の架空人物情報) |
| title, org_name, role_in_org, first_year, species, cv_name, description | fictional_anime_character固有: 作品名・所属・役割・初登場年・種族・声優名・紹介文(AI生成の架空キャラ情報) |

## リスト一覧

| ファイル | 内容 | 出典・クレジット |
|---|---|---|
| baseball.csv | プロ野球選手・歴代(type: family/given/full/registered) | Moto(選手表ニキ)様と協力者の皆様。現役の新規追加は[Wikipedia](https://ja.wikipedia.org/) (CC BY-SA 4.0)で自動更新 |
| football.csv | サッカー選手(J1〜J3・歴代。所属クラブ付き) | ヨロスー様。現役の新規追加はWikipediaで自動更新。所属クラブはWikipedia/[Wikidata](https://www.wikidata.org/) |
| stations.csv | 駅名(現役駅+路面電車・索道。所在地・写真URL付き) | [Wikidata](https://www.wikidata.org/)/[Wikipedia](https://ja.wikipedia.org/) (CC BY-SA 4.0) で自動更新。旧リストはすきやきすきや様 |
| nations.csv | 国名(国連加盟国。正式名称・通称・漢字略称・別読み・別カナ表記を同一idで併記) | [mledoze/countries](https://github.com/mledoze/countries) で自動更新。別表記は[Wikipedia](https://ja.wikipedia.org/) (CC BY-SA 4.0)等を参照して手動追加 |
| scientist.csv | 科学者(物理/化学/数学/天文/生物/計算機/地学。分野・時代区分・生没・国・性別・ノーベル賞・業績説明付き。手選び+著名層) | Wikidata/Wikipediaで自動更新 |
| sekitsui.csv | 動物(脊椎動物。分類・絶滅フラグ・目/科・画像URL付き) | [Wikidata](https://www.wikidata.org/) (CC0) で自動更新。写真は[Wikimedia Commons](https://commons.wikimedia.org/)(ライセンスは画像ごと。image_page参照)、実写が無い行の分類イメージ画像は本リポジトリのReleaseで配布(CC0・実写ではない) |
| plant.csv | 植物(被子/裸子/シダ/コケ/藻類の和名。分類・絶滅フラグ・科/属・写真URL付き) | [Wikidata](https://www.wikidata.org/) (CC0) で自動更新。写真は[Wikimedia Commons](https://commons.wikimedia.org/)(ライセンスは画像ごと。image_page参照)、実写が無い行の分類イメージ画像は本リポジトリのReleaseで配布(CC0・実写ではない) |
| pokemon.csv | ポケモン(地方のすがた・メガ・キョダイマックス含む。タイプ配色のみで描いた「型色カード」画像付き) | [PokéAPI](https://github.com/PokeAPI/pokeapi) で自動更新。画像は本リポジトリのReleaseで配布(公式アセット・キャラクター造形は使わず配色と文字のみ)。本リポジトリは非公式のファンメイドであり株式会社ポケモン・任天堂等とは無関係 |
| youtuber.csv | YouTuber・VTuber(ja.wikipediaに記事がある著名層。海外勢含む。活動名のみ、type: family/given/full。category列で区分、所属・活動開始年・status・画像URL付き) | Wikidata/Wikipedia (CC BY-SA 4.0) で自動更新。写真は[Wikimedia Commons](https://commons.wikimedia.org/)の自由ライセンスの実写のみ(ライセンスは画像ごと。image_page参照)、実写が無い人の象徴カード画像は本リポジトリの `images/youtuber/`(CC0・実写ではない) |
| fictional_scientist.csv | AI生成による架空の科学者1000人(名前・読み・生没年・国籍・分野・主な業績・肖像画像。type: family/given/full) | jiroshimaya/fictional-scientists プロジェクトによる自動生成(実在人物とは無関係)、画像は本リポジトリのReleaseで配布 |
| fictional_anime_character.csv | AI生成による架空アニメ『蒼穹の螺旋航路』の登場キャラ1000人(名前・読み・所属・初登場年・種族・声優名・紹介文・肖像画像。type: family/given/full/call/nick。callは作中で使われる呼び名(敬称込み)、nickはあだ名) | jiroshimaya/fictional-scientists プロジェクトによる自動生成(実在の作品・人物とは無関係)、画像は本リポジトリのReleaseで配布 |
| fictional_daily_anime_character.csv | AI生成による架空日常アニメ『まちまる！』の住人1025人(名前・読み・所属・初登場年・種族・声優名・紹介文・肖像画像。type: family/given/full/call/nick。callは作中で使われる呼び名(敬称込み)、nickはあだ名) | jiroshimaya/fictional-scientists プロジェクトによる自動生成(実在の作品・人物とは無関係)、画像は本リポジトリのReleaseで配布 |

## 利用上の注意

- 本リポジトリは非公式のファンメイド・データ集であり、各作品・団体・人物とは無関係です
- 空耳変換の研究・個人利用を想定しています。各リストの元データの帰属・ライセンスは上表の出典欄を参照してください(Wikidata由来はCC0、Wikipedia由来はCC BY-SA 4.0、nationsは[mledoze/countries](https://github.com/mledoze/countries)(ODbL)由来)
- 実在人物名のリスト(baseball/football/scientist/youtuberのcategory=youtuber)は公表済みの事実情報(名簿)のみで構成しています。氏名の営利的な顧客誘引を目的とする利用(パブリシティ権に触れうる利用)は行わないでください。youtuberは記事名(活動名)のみを収録し、本名は収録しません
- youtuber.csvのcategory=vtuberの行は各社(カバー・ANYCOLOR等)の知的財産であるキャラクター名です。名称と読みのみを非商用のファンメイド用途で収録しています(キャラクターデザイン・アバターのイラストやスクリーンショットは画像として一切収録していません。詳細は ADR 00018)
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
python3 tools/update_youtuber.py   # WikidataのYouTuber/VTuber(ja記事あり)を追記
python3 tools/enrich_images.py     # 画像が空の人物行にCommons画像を遡及付与
python3 tools/audit_taxa.py sekitsui  # 既存行が想定した界・門の配下か検査(読み取り専用)
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
  (詳細は ADR 00003)
- stations: 1行=1駅(Wikidata QIDが永続キー)。既存行は書き換えず、新駅の追記と
  status の更新のみ。新駅の読みはWikipedia冒頭文から抽出(詳細は ADR 00004)
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
  再実行で続きから再開する(全件引き直したいときはキャッシュを消す)
- scientist: 旧 physicist.csv を広義の科学者リストに拡張・リネーム。Wikidataの
  職業(P106)が物理/化学/数学/天文/生物/計算機科学/地学のいずれかで sitelinks>=20 の
  人物を対象に、分野(field。スラッシュ区切り多値)・時代(era)・生年・ノーベル賞・性別・国・
  生死・業績説明(description)を付与。既存の手選び行は保持し、未収録者を追記。読みは
  記事冒頭から取得(詳細は ADR 00009)
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
- youtuber: Wikidataの職業(P106)がYouTuber/バーチャルYouTuberで
  ja.wikipediaに記事がある人物のみ。1ファイルに収録し category 列
  (youtuber/vtuber)で区別する。記事名(活動名)のみ収録し本名は取得しない。
  読みは記事冒頭「名前（よみ、」から抽出(かな名は自身から変換)。既存行は
  書き換えず、未収録者の追記と status(current→former)の一方向更新のみ。
  org(所属)・debut_year(活動開始年)付き(詳細は ADR 00011, 00012)。
  画像(`image`/`image_page`/`wikidata`)は月次バッチには入れず手動実行で補完する
  (詳細は ADR 00018):
  ```sh
  # 自由ライセンスの実写(Commons)とQIDを付与。イラスト・アバター・コスプレは採らない
  python3 tools/enrich_youtuber_images.py            # --report で不採用の内訳
  # 本人のイメージカラーを集める(要 Pillow。tools/youtuber_colors.json)
  python3 tools/fetch_youtuber_colors.py             # --audit で読み取り結果を全件表示
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
  分からない人は category と org から決める。色の出典は「色をテキストで公表して
  いる公式サイト」と「公式ライブのペンライトカラー一覧画像」の2つで、
  **キャラクターイラストからの色抽出はしない**。一覧画像は `tools/.cache/` 止まりで
  リポジトリには置かない
- 自動更新の対象外は fictional_scientist(外部プロジェクトで生成したCSVを
  取り込む方式。詳細は ADR 00006)

設計判断の記録は [docs/adr/](docs/adr/) を参照。

## メンテナンス

- `tools/` に整備用スクリプト(uv管理)
- 提供データの一括取り込みなど手動での更新手順は [docs/](docs/) 参照
- 更新したら利用側リポジトリで submodule を更新する:
  ```sh
  git submodule update --remote wordlists
  ```
