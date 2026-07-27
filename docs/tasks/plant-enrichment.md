# 作業指示書: plant.csv に wikidata ID・画像・科/属を追加する

## ゴール

`plant.csv`(約6,542行)に以下の列を追加し、動画レイアウトで「写真 + 和名 + ヒルガオ科サツマイモ属」のような表示ができるようにする。

| 追加する列 | 内容 | 例 |
| --- | --- | --- |
| `family` | 科の日本語名(なければ学名) | `バラ科` |
| `genus` | 属の日本語名(なければ学名) | `サクラ属` |
| `image` | Wikimedia Commonsの画像URL | `http://commons.wikimedia.org/wiki/Special:FilePath/...` |
| `image_page` | 同・ファイルページURL | `https://commons.wikimedia.org/wiki/File:...` |
| `wikidata` | Wikidata QID | `Q165137` |

列の位置と命名は **sekitsui.csv に合わせる**(`id,original,surface,pronunciation,class,extinct,order,family,image,image_page,wikidata`)。植物は目より科・属が一般的な言及単位なので `order` は作らず `family`/`genus` にする。

## 現状

```
$ head -1 plant.csv
id,original,surface,pronunciation,class,extinct
```

- `class` は `双子葉` `単子葉` などの大分類。既存の棚卸し(PR #46, #49)でQIDベースの検証はされているが、**QID自体はCSVに保存されていない**
- 画像も分類階級もまだ無い

## 進め方

### 1. 既存資産を必ず先に読む

新規に書き始めないこと。以下がそのまま使える/流用できる。

- `tools/audit_taxa.py` — 棚卸しで使った同定ロジック。`resolve_by_label` は**和名ラベルに対する候補QIDを全部返す**ので、「候補が複数なら空にする」という方針にそのまま使える
- `wpnames.sparql_post` — POSTベースのSPARQL。GETだとURI長制限(HTTP 414)に当たるので**必ずこちらを使う**
- `tools/enrich_sekitsui_taxonomy.py` — 親分類群をBFSで辿る実装。`wdt:P171*`(推移的閉包)はWDQSでタイムアウトするため、**400 QID/クエリで1段ずつ親を辿り、目的のランクに到達した枝から打ち切る**方式になっている。ランク指定を科(Q35409)・属(Q34740)に変えればほぼそのまま流用できる
- `tools/enrich_sekitsui_images.py` — `commons_urls` が `image`/`image_page` の**URL形式を正確に生成する**。ここは自作せず流用すること
- ADR `docs/adr/00015-*`, `00016-*` — 直近の同種作業の設計判断

### 2. QIDの同定(ここが品質の要)

和名から `plant.csv` の各行に対応する Wikidata の分類群を特定する。

- 対象を分類群に限定する: `P31 = Q16521`(taxon)、または `P225`(学名)を持つこと
- **曖昧なら空にする**。同名の地名・商品名・作品名を拾うくらいなら空のほうがよい。`resolve_by_label` が複数候補を返したら、taxonフィルタ後も2件以上残るものは空
- 同定率は 100% を目指さない。sekitsui では「QIDのある行に限れば99.8%」という形で、**同定できた行の品質**を担保した

### 3. 分類階級の取得

- `P171`(親分類群)を辿り、`P105`(分類階級)が科(Q35409)・属(Q34740)のものを拾う
- 表示名の優先順位は **ランク付きja別名 > jaラベル > 学名(P225)**。sekitsui でこの順にしたのは、Wikidataの ja ラベルが「バラ」のようにランクを含まない場合があるため(別名に「バラ科」がある)
- 取れなければ空。学名フォールバックは許容(sekitsui でも51目が学名のまま)

### 4. 画像の取得

- `P18` から。URL形式は `enrich_sekitsui_images.py::commons_urls` に合わせる(2列とも)
- 画像が無い行は空

## 守ること

- **既存CSVのスタイルを壊さない**: 行順・引用符の付き方・改行コードを変えない。`git diff` で列追加以外の差分が出ていないか必ず確認する
- **レート制限**: WDQSに連続リクエストしない。バッチ間に十分なsleepを入れ、User-Agentを設定する
- **再開可能に**: `tools/.cache/` にチェックポイントを書き、中断しても続きから再開できるようにする(`.gitignore` 済み)。`--refresh` で再取得できること
- **冪等性**: 2回実行して差分が出ないことを確認する
- スクリプトは `tools/` に置き、実行方法を README に追記。ADR を1本書く
- コミットは「スクリプト追加」「CSV更新」で分ける。**pushとPR作成はしない**

## 検証

著名な植物で目視確認し、報告に含めること。

| 和名 | 期待される科/属 |
| --- | --- |
| ソメイヨシノ | バラ科 / サクラ属 |
| ヒマワリ | キク科 / ヒマワリ属 |
| イネ | イネ科 / イネ属 |
| セイヨウタンポポ | キク科 / タンポポ属 |
| スギ | ヒノキ科 / スギ属 |
| サツマイモ | ヒルガオ科 / サツマイモ属 |

加えて、同定率・取得率(科・属・画像それぞれ)を報告すること。

## 品質が担保できない場合

無理に埋めない。「ここまでしかできなかった」と報告するほうが、誤った分類を配るよりずっとよい。特に園芸品種・和名が通称の行は同定が難しいはずなので、空のまま残す判断を歓迎する。

## 完了後(依頼元での作業)

このリポジトリがマージされたら、soramimic-video 側で以下を行う(こちらは依頼元が対応するので、指示書の範囲外):

- `src/soramimic_video/layouts/plant_card.json` を作成(`animal_card.json` が雛形。`{family}{genus}` を出す)
- `src/soramimic_video/wordlist_layouts.json` に `"plant": "plant_card"` を追加
- submodule を更新
