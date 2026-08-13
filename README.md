# soramimic-wordlists

[Soramimic](https://github.com/jiroshimaya/soramimic)(空耳作詞支援システム)などで使う単語リスト集。
利用側リポジトリからは git submodule で参照する想定。

## 形式

全リストはCSV形式で、次の列を共通して持つ。

| 列 | 意味 |
|---|---|
| id | 単語のグループID(同じ元単語の行は同じid) |
| original | 元の単語(表示用) |
| surface | 変換結果として表示する表層 |
| pronunciation | 読み(カタカナ)。空の場合は `surface` から推定する |

リスト固有の列と補足は[リスト別の列説明](docs/wordlists.md)を参照。

## リスト一覧

| ファイル | 内容 | 出典・クレジット |
|---|---|---|
| baseball.csv | プロ野球選手 | Moto(選手表ニキ)様と協力者の皆様、[Wikipedia](https://ja.wikipedia.org/)、[Wikimedia Commons](https://commons.wikimedia.org/) |
| football.csv | Jリーグ経験者、世界的著名選手、海外のみで活動する日本人サッカー選手 | [Wikipedia](https://ja.wikipedia.org/)、[Jリーグデータサイト](https://data.j-league.or.jp/)、[Wikidata](https://www.wikidata.org/)、Wikimedia Commons |
| stations.csv | 現役駅・廃駅・旧駅名 | Wikidata、Wikipedia、すきやきすきや様提供の旧リスト(廃駅の照合)、Wikimedia Commons |
| nations.csv | 現存国・消滅国・旧称 | [mledoze/countries](https://github.com/mledoze/countries)、Wikidata、Wikipedia、Wikimedia Commons |
| scientist.csv | 科学者 | Wikidata、Wikipedia、Wikimedia Commons |
| sekitsui.csv | 脊椎動物 | Wikidata、[GBIF](https://www.gbif.org/)、Wikimedia Commons |
| plant.csv | 植物 | Wikidata、Wikimedia Commons |
| insect.csv | 昆虫 | Wikidata、Wikimedia Commons |
| marine_life.csv | 海の生き物 | [WoRMS](https://www.marinespecies.org/)、[JODC海洋生物分類コード](https://www.jodc.go.jp/jodcweb/JDOSS/infoTaxonomicCode_j.html)、Wikidata、日本語Wikipedia、Wikimedia Commons、本リポジトリでのキュレーション |
| pokemon.csv | ポケモン | [PokéAPI](https://github.com/PokeAPI/pokeapi)、[PhyloPic](https://www.phylopic.org/) |
| youtuber.csv | YouTuber・VTuber | Wikidata、Wikipedia、[YouTube Data API v3](https://developers.google.com/youtube/v3)、Wikimedia Commons |
| fictional_scientist.csv | AI生成の架空科学者 | jiroshimaya/fictional-scientists |
| fictional_anime_character.csv | AI生成の架空アニメ登場人物 | jiroshimaya/fictional-scientists |
| fictional_daily_anime_character.csv | AI生成の架空日常アニメ登場人物 | jiroshimaya/fictional-scientists |
| ryuko.csv | 平安〜令和の流行 | Wikipedia等を参照したキュレーション |
| myoji.csv | 名字と読み | [SudachiDict](https://github.com/WorksApplications/SudachiDict)、[Web NDL Authorities](https://id.ndl.go.jp/auth/ndla/Web)、[JMnedict](https://www.edrdg.org/enamdict/enamdict_doc.html)、Wikidata、Wikipedia |
| gimukyoiku.csv | 小中高の学習語 | 本リポジトリでのキュレーション、[教科書LOD](https://jp-textbook.github.io/)、Wikimedia Commons |
| municipality.csv | 現存・廃止自治体 | 総務省、[e-Stat](https://www.e-stat.go.jp/)、Wikidata、Wikipedia、Wikimedia Commons |
| school.csv | 幼稚園〜大学等の学校名 | 文部科学省、総務省、Wikidata、Wikipedia、Wikimedia Commons |

## 利用上の注意

- 本リポジトリは非公式のファンメイド・データ集であり、各作品・団体・人物とは無関係です
- テキストや画像は、再利用可能な条件で提供された素材または本リポジトリで作成した素材から構成するよう努めていますが、利用にあたっては各リストの出典欄と `image_page` に記載されたライセンスを確認し、利用者自身の責任で判断してください
- 実在人物を扱うデータの利用にあたっては、肖像権やパブリシティ権等に配慮してください
- `myoji.csv` の `evidence_sources=jmnedict` に該当する情報は、Electronic Dictionary
  Research and Development Group のJMnedict/ENAMDICTに基づき、
  [CC BY-SA 4.0](https://www.edrdg.org/edrdg/licence.html)の条件で利用しています。
  Web NDL Authorities由来の情報は国立国会図書館の同サービスから取得しており、
  [Web NDL Authoritiesの利用条件](https://id.ndl.go.jp/information/use/)に従います
- 掲載内容に関する権利上のご指摘は、Issueでご連絡ください

## 自動更新

公開データから更新できるリストは、GitHub Actionsで月1回更新し、差分があればPRを作成します。
更新方法、必要な設定、リストごとの処理は[更新・メンテナンス](docs/maintenance.md)を参照してください。

## メンテナンス

- `tools/` に整備用スクリプト(uv管理)
- 提供データの一括取り込みなど手動での更新手順は [docs/](docs/) 参照
- 更新したら利用側リポジトリで submodule を更新する:
  ```sh
  git submodule update --remote wordlists
  ```
