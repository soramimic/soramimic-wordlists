# 更新・メンテナンス

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
python3 tools/update_marine_life.py --check  # 海の生き物の台帳と配布CSVの同期を検査
python3 tools/update_municipality.py  # 総務省コード表+Wikidataで市区町村を再生成
python3 tools/update_youtuber.py   # WikidataのYouTuber/VTuber(ja記事あり)を追記
python3 tools/update_school.py     # 文科省の学校コード一覧+Wikidata/Wikipediaで全件再生成
python3 tools/update_myoji.py      # SudachiDictの姓エントリ+Wikidata/Wikipediaで生成
python3 tools/update_youtuber_subscribers.py  # 登録者数を全行上書き(要 YOUTUBE_API_KEY)
python3 tools/enrich_images.py     # 画像が空の人物行にCommons画像を遡及付与
python3 tools/enrich_school_municipality_images.py  # 学校・市町村のCommons画像を補完
python3 tools/apply_school_type_images.py  # 実写が無い学校へ校種別イメージを付与
python3 tools/audit_taxa.py sekitsui  # 既存行が想定した界・門・綱の配下か検査(読み取り専用)
```

`marine_life.csv` はネットワークから無人更新せず、レビュー済み台帳
`tools/marine_life_source.csv` から全件再生成する。項目を追加するときは台帳末尾へ
次の連番 `id` で追記し、分類・海洋性・説明・QIDを確認してから次を実行する。
QIDを既存リストから転記する場合は和名と `class` の両方が一致し、候補が一意な場合に
限る。同名の魚と鳥などがあるため、和名だけでの結合は禁止する。
追加行はJODCの和名・学名を候補にし、WoRMSの有効AphiaID側で `rank=Species` と
`isMarine=1` を確認している。旧学名のレコードだけを根拠にしない。QIDは学名P225が
完全一致し、P171の祖先がAnimaliaへ到達する分類群に限る。
JODCに日本語の目・科がない行は、WoRMSの有効レコードの学名に `目` / `科` を付ける。

```sh
python3 tools/update_marine_life.py
python3 tools/update_marine_life.py --check
python3 -m unittest tools/test_update_marine_life.py
```

既存項目の削除は通常実行では拒否される。誤収録を台帳から削除する場合だけ、差分を
レビューしたうえで `--allow-removals` を付ける。実写を追加・変更するときはCommons APIで
ライセンス、作者、寸法、SHA-1を取得し、`tools/marine_life_image_sources.jsonl` の同名行と
台帳の `image` / `image_page` を同時に更新する。`update_marine_life.py --check` は両者の
一対一対応も検査する。分類別概念SVGには必ず「イメージ」表記を残す。

- pokemon: 全件再生成。フォームは「ライチュウ（アローラのすがた）」形式で
  表記ゆれ3行を同一idで収録。種とフォームは別ポケモンとして別id
  (詳細は ADR 00002)。`image`/`image_page` は `original`(名前)から機械的に
  組み立てるので全件再生成でも消えない。**カードのファイル名も名前由来
  (`pkm_<sha1(名前)先頭10桁>.svg`)なので、新種追加で id がずれても既存のURLが
  別のポケモンのカードを指すことはない。**
  **新ポケモンが追加された回はカードを追加して Release を更新すること**
  (アセットが無い名前は画像が404。増えた分だけ送ればよく、既存カードの
  作り直しは不要)。**あわせて新種のモチーフラベルを `tools/pokemon_motifs.json`
  に足す**(無くてもカードは生成できるが、シルエットが `?` になる。新しいラベルが
  実在の生物なら `tools/motif_taxa.json` に学名を足して
  `python3 tools/fetch_motif_silhouettes.py` で素材を取り、架空・非生物なら
  `images/pokemon_motifs/` に自作シルエットを描いて台帳に `"source": "self"` で
  登録する。詳細は ADR 00033):
  ```sh
  # 生成してアップロード。既定でReleaseとサイズが違うもの・無いものだけを送るので、
  # 増分追加にも意匠変更の全枚数差し替えにも同じコマンドでよく、
  # レート制限で途中終了しても再実行すれば続きから進む
  python3 tools/gen_pokemon_typecards.py --out build/pokemon_typecards \
      --upload
  # Releaseのアセットがいま生成されるカードと一致するか(サイズで)検査
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
- baseball: 既存の歴代名鑑を保持し、未収録の現役選手だけ追記する。
  姓名分割済みの読みは記事冒頭「姓 名(せい めい、」から取得する
  (詳細は ADR 00005)。
- football: WikipediaのJリーグクラブ選手カテゴリから候補を作り、Jリーグ公式の
  登録名・生年月日・英字名と本人照合できた選手だけで再生成する
  (詳細は ADR 00047)。読みはWikipedia記事冒頭から取得し、公式の英字名からは
  逆算しない。再生成と監査は次の順で行う:
  ```sh
  python3 tools/rebuild_football_jleague.py
  python3 tools/audit_football_jleague_readings.py \
      --candidates tools/football_jleague_candidates.csv \
      --manifest tools/football_jleague_candidates.jsonl
  python3 tools/audit_football_jleague_eligibility.py \
      --candidates tools/football_jleague_candidates.csv \
      --manifest tools/football_jleague_candidates.jsonl \
      --verified-candidates tools/football_jleague_verified.csv \
      --verified-manifest tools/football_jleague_verified_sources.jsonl
  python3 tools/extend_football_scopes.py \
      --input tools/football_jleague_verified.csv \
      --jleague-manifest tools/football_jleague_verified_sources.jsonl \
      --resume
  # J照合、追加区分の件数・要確認一覧・根拠manifestをレビューしてから切り替える
  cp tools/football_scoped_candidates.csv football.csv
  python3 tools/gen_player_cards.py --list football
  ```
  取得結果を `tools/.cache/`(Git管理外)に逐次保存するので、中断しても
  再実行で続きから再開する(全件引き直したいときはキャッシュを消す)。
  `scope=jleague` は既定で有効にし、`world` と `overseas_japanese` は利用側の
  フィルターで任意追加する。追加基準は ADR 00048 を参照する。
  選手の経歴・主要な実績を紹介する `description` とポジションは生成時に付与する。
  baseballの既存空欄を補完するときは次を使う:
  ```sh
  python3 tools/enrich_player_descriptions.py
  python3 tools/enrich_player_positions.py
  ```
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
  人物を対象に、分野(field。スラッシュ区切り多値)・時代(era)・生没年・ノーベル賞・性別・国・
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
  # Wikidataで引けない旧和名をGBIFの日本語別名完全一致で補完(まずdry-runで確認)
  python3 tools/enrich_sekitsui_gbif.py --dry-run --workers 6
  python3 tools/enrich_sekitsui_gbif.py --workers 6
  # GBIF由来のラテン学名表記をWikidataの日本語ラベル・別名で表示用に直す
  python3 tools/enrich_sekitsui_taxonomy_labels.py
  # 画像が空の行にCommons画像(P18)を遡及付与(概念イメージの行は実写で上書き)
  python3 tools/enrich_sekitsui_images.py
  # 総称・別名用に検証済みの代表画像だけを、WDQS問い合わせなしで再適用
  python3 tools/enrich_sekitsui_images.py --manual-only
  # MANUAL_IMAGESの画像選定を変更した場合は既存の専用画像も更新
  python3 tools/enrich_sekitsui_images.py --manual-only --refresh-manual
  ```
  enrich_sekitsui_taxonomy は取得結果を `tools/.cache/`(Git管理外)に逐次
  保存するので、中断しても再実行で続きから再開する(全件引き直したいときは
  キャッシュを消す)。
  GBIF補完も検索結果を `tools/.cache/sekitsui_gbif.json` に保存する。日本語別名が
  完全一致し、Animalia/Chordata 配下で、複数候補の綱・目・科が矛盾しない場合だけ
  空欄へ適用する。既存値は上書きせず、曖昧な名前は未適用のまま残す。
  種ランク検索から漏れる家畜名・総称・別名の代表画像は
  `tools/sekitsui_overrides.py` の `MANUAL_IMAGES` で管理する。Wikidata QIDと
  Commonsファイルを個別確認したものだけを登録し、同名だけを根拠に自動転用しない。
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
- municipality: 現存の市区町村は**総務省「全国地方公共団体コード」の現行コード表**
  (xlsx)が母集団で、団体コード・都道府県・カナをそのまま採る。政令指定都市の
  行政区は同じコード表の政令市シートから拾い、`original` は区名だけ(`中央区`)、
  `parent` に親の市名(`札幌市`)を入れる。廃止自治体はWikidataの
  「廃止された日本の市町村」(Q18663566)のサブクラス閉包で、ラベルの括弧注記を
  落として末尾が 市/区/町/村 の日本語名だけを採る。人口は2020年国勢調査
  (e-Stat)を優先し、取れない行(北方領土の6村・2020年以降にできた区など)だけ
  WikidataのP1082で補う。descriptionはscientistと同じ生成方式で記事冒頭から
  目安90字の完結文。**openpyxlは使わず、xlsx(zip+XML)を標準ライブラリで読む**
  (updaterは依存パッケージ無しで動かす方針)。id は既存CSVのキー(現存は団体
  コード、廃止はQID。**改称した自治体は旧名と新名で団体コードが同じ**なので
  名前空間を分ける)から引き継ぎ、既存の値は今回取得できた列だけ上書きする
  (ADR 00014)。母集団から消えた現存行は status=former に落として残す。
  取得結果は `tools/.cache/municipality/`(Git管理外)に貯め、再実行では
  Wikipediaの記事冒頭を引き直さない(全件引き直しは `--refresh`)
  画像はWikidata P18を優先し、無い自治体はP242の位置図で補完する。
  なお空欄の旧自治体は `python3 tools/collect_municipality_image_candidates.py`
  でP373のCommonsカテゴリから実写候補台帳を作れるが、旗・章・地図・
  人物などを取り違えないよう、候補は自動適用せず目視確認する。
  `tools/set_image_candidate_review.py municipality ...` で採用を記録し、
  `python3 tools/apply_reviewed_municipality_images.py --dry-run` で確認後に反映する
  (詳細は ADR 00036)
- youtuber: Wikidataの職業(P106)がYouTuber/バーチャルYouTuberで
  ja.wikipediaに記事がある人物のみ。1ファイルに収録し category 列
  (youtuber/vtuber)で区別する。記事名(活動名)のみ収録し本名は取得しない。
  読みは記事冒頭「名前（よみ、」から抽出(かな名は自身から変換)。既存行は
  書き換えず、未収録者の追記と status(current→former)の一方向更新、
  org/debut_year/channel/description の空欄補完のみ。org(所属)・
  debut_year(活動開始年)・channel(メインチャンネル名)・description(短い説明文)付き
  (debut_year は P2031(活動開始)を優先し、無ければ P2397 の修飾子 P580 =
  チャンネル開設年を使う。channel は P2397 の修飾子 P1810 で、複数チャンネルは
  登録者数 P3744 が最大の1本。description は ADR 00045 の専用生成方式で、
  活動内容・実績を中心に目安50字、通常65字以内の完結文にする。
  **記事冒頭には本名がよく書かれているので、
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
  説明文の基準を変更して既存行を再生成するときは、通常更新とは分けて明示的に行う:
  ```sh
  python3 tools/enrich_youtuber_descriptions.py --refresh
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
- school: 文部科学省「学校コード」一覧(全校種・廃校込みで約6万校)を名簿にして
  全件再生成する。`id` は学校コード(`code`列)に対して固定するので、再生成しても
  既存行の id は動かない(ADR 00014)。読み・別名・QIDは Wikidata の
  **P11127(文部科学省学校コード)で直接JOIN**するため名寄せの取り違えが起きない。
  表層は `common`(札幌南高校)・`name`(札幌南)・`nick`(札南)の3種類だけを作り、
  長い正式名称は `original` 列にだけ持つ。**`nick`(通称・略称)は機械生成せず**、
  ja.wikipedia 冒頭の「通称は『札南(さつなん)』」パターンと Wikidata の altLabel
  から取れたものだけを入れる(詳細は ADR 00037)。
  所在地の市区町村は、住所を正規表現で切らず**総務省「全国地方公共団体コード」の
  市区町村名に前方一致(最長一致)させて**決める(正規表現だと「洋野町種市」
  「大阪市城東区古市」のように大字まで飲み込む)。政令市は区を落として市に丸まり、
  東京23区は区のまま残る。`prefecture`/`city` はCJK互換漢字だけをNFKCで統合して
  表記の割れを防ぐ(`original`/`surface` は正式名称なので原文のまま)。
  **保育所は学校教育法の学校ではなく学校コードが無いので収録しない**
  (幼保連携型認定こども園は収録するので「〜保育園」を名乗る園は入る)。
  取得結果は `tools/.cache/`(Git管理外)に保存するので、ローカルでの再実行は
  差分だけ引く(全部引き直したいときは `--refresh`)。
  画像はWikidata P18のCommons実写を優先する。P373のCommonsカテゴリから
  追加候補を作る場合は `python3 tools/collect_school_image_candidates.py` を実行し、
  出力された `tools/school_image_candidates.jsonl` を目視確認する。採用する
  レコードに `review.status=accepted` と候補内の `selected_image_page` を記録する
  (`tools/set_image_candidate_review.py school ...` で安全に更新できる)。
  `python3 tools/apply_reviewed_school_images.py --dry-run` でQID・URL・既存実写の
  保護を検査してから、`--dry-run` 無しで反映する。再収集しても
  `review` は保持される。実写が無い学校は
  `python3 tools/gen_school_type_images.py --prune` で生成した13校種の共有SVGを
  `python3 tools/apply_school_type_images.py` で割り当てる。校章・ロゴは使わず、
  すべてのSVGに「イメージ」と明記する。後から実写が取れた場合は自動で置換される。
  Wikipediaの冒頭文取得(約2.9万記事)が支配的で、初回は35分前後かかる(3並列)
- 自動更新の対象外は fictional_scientist(外部プロジェクトで生成したCSVを
  取り込む方式。詳細は ADR 00006)と gimukyoiku(AI生成による手動キュレーション。
  追加・修正は通常のPRで行う。詳細は ADR 00022)

設計判断の記録は [ADR](adr/) を参照。
