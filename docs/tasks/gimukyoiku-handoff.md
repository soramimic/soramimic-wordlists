# gimukyoiku.csv 引き継ぎメモ (2026-08-02)

義務教育リストの増補・画像付与を別セッションで続けるための資料。
正式な設計判断は ADR 00022 / 00027 / 00028 / 00034 / 00036 / 00037 にある。
**画像生成(gpt-image)のパイプラインは `/home/jiro/development/gimukyoiku-imggen/HANDOFF.md`**
が本体で、この文書はリスト側の状態と残りの作業を書く。

## 1. 現状 (main = 全PRマージ済み)

3665行 / 9教科 / level 3段階。

| level | 行数 |  | 画像の方式 | 行数 |
|---|---|---|---|---|
| 中学校 | 1523 |  | 実写・図版(Commons) | 2395 |
| 高等学校 | 1103 |  | 生成イメージ(SD/gpt-image/タイポカード) | 663 |
| 小学校 | 692 |  | **作図SVG(数学)** | 95 |
| 小学校/中学校 | 345 |  | **なし** | **512** |
| 中学校/高等学校 | 3 |  | | |

マージ済みPR: #91(level列と高校の語) / #92(学校生活の撤回) / #96(数学の作図SVGと
手動マッピング277語) / #97(weak67語の生成画像改善) / #98(象徴画像115語をCommons
図版に置き換え)。利用側は soramimic#45, #46 と soramimic-video#206 で追随済み。

**#97 と #98 は別セッション(codex)が並行で進めたもの**で、既存の生成イメージの
品質改善にあたる(生成778→663、Commons 2280→2395)。画像なし512行はこの2本では
動いていない。作業が重ならないよう、着手前に `git log origin/main` で相手の
進捗を確認すること。

## 2. 残っている作業(優先度順)

### ① 画像なし512行

教科別: 国語218 / 英語88 / 社会64 / 音楽47 / 技術・家庭36 / 理科32 / 保健体育17 / 美術10。
level別では高等学校287が最多。

**中身は「語を表す画像が原理的に存在しない」ものが大半**である。

- 四字熟語(`臨機応変` `五里霧中`)約38語
- 古典文法の助動詞・活用・意味区分(`なり` `めり` `推量` `下二段活用`)約35語
- 英文法用語88語(`分詞構文` `仮定法過去完了`)。**ここは全部そう**
- 国語科のメタ用語(`要約` `連文節` `二項対立` `演繹`)約40語
- 高校化学の計算・平衡系(`モル濃度` `イオン化傾向` `電離平衡`)
- 高校日本史の制度・法令名(`租庸調` `不輸不入の権` `棄捐令`)

**打ち手は2つある。**

1. **作図(推奨)**: ADR 00037 の `tools/gen_gimukyoiku_math_figs.py` を数学以外にも
   広げる。理科の実験装置・化学の平衡・技術の製図・古典文法の活用表は図にできる。
   生成より速く正確で、レート制限もない。枠組み(viewBox 320x200・色・ヘルパ)は
   そのまま使える。**四字熟語と英文法用語は図にならないので対象外**
2. **生成イメージ**: imggen の cdp_driver で ChatGPT Web を叩く。ただし
   **1日90枚前後で制限**がかかるので512語なら6日前後。四字熟語は場面を描かせる
   しかなく、当たり外れが大きい

### ② 語の増補

`gimukyoiku-wordlist` のメモにあるとおり **教科書LOD が本命のネタ元**。
`https://w3id.org/jp-textbook/all-teachingUnit-20260407.ttl.gz` に実際の検定教科書の
単元名58,390件が level/subject/publisher 付きで入っている(単元情報は CC BY 4.0)。
未処理の候補は 5408件を抽出済みだが、**単元名は章・節の見出しなので粒度が粗く、
収録判定そのものには使えない**(保健体育の単元は全国で407件しかなく、`筋かい` の
ような確実に教科書にある語も「単元名に出ない」と出る)。抜けを見つける材料に留める。

英語が194行と他教科より薄い(カタカナ英単語を削ったぶん)。増やすなら英語固有の
語をもう少し掘る余地がある。

### ③ 既存の生成イメージ778枚の品質改善

imggen の HANDOFF.md §5 が分析済み。weak67語と、未スイープの
美術94/音楽100/国語95/英語77/社会78/数学77語が残っている。

## 3. 落とし穴(このセッションで踏んだもの)

- **画像の自動探索を緩めてはいけない。** 全文検索フォールバックを無作為60語で試すと
  ヒット10語、そのうち大半が誤マッチ(`どきん`→佐渡金山、`衣生活`→ひとりぼっちの
  ○○生活、`従属接続詞`→シンハラ語)。ADR 00027 の「完全一致＋リダイレクトのみ、
  曖昧さ回避は捨てる」が正しい。**打ち手は `MANUAL_TITLES` に手で足すこと**
- **「記事に画像がある」と「その画像が語を表している」は別。** API検証は前者しか
  見ない。`関白`→旗のsvg、`領事裁判権`→ローマの聖堂、`恒常性`→DNAアイコンのような
  誤りは、返ってきたファイル名か画像そのものを見ないと落とせない
- **`Replace_this_image_JA.svg` はWikipediaの「画像を提供してください」
  プレースホルダ**。APIは正規の画像として返すので、明示的に弾く必要がある
- **soramimic-video の `gimukyoiku_card` は背景が黒**。透過PNG/SVGで暗い線画のものは
  カード上で消える。採用前に黒背景へ合成して平均輝度を測ること(このセッションでは
  透過63件のうち20件が実質不可視だった)
- **enrich スクリプトはキャッシュが効く。** `MANUAL_TITLES` に足しても
  `tools/.cache/gimukyoiku_images.json` に既に「画像なし」で載っている語は
  引き直されない。該当語をキャッシュから消してから実行する
- **リード画像がPDF/動画(ogv)/TIFの記事がある。** `南総里見八犬伝` `平方完成`
  `向心力` `シェエラザード` など。スクリプトが弾くのは正しい挙動なので、
  バグと勘違いしないこと
- **非教科の subject を作るのは割に合わなかった**(ADR 00035→00036)。区分を増やす
  前に「そこに何語入るか」を数えること。2語のために利用側の設定まで変える羽目になった

## 4. 手順の要点

```sh
# 画像の補完(空欄のみ。MANUAL_TITLES を足したらキャッシュから該当語を消してから)
python3 tools/enrich_gimukyoiku_images.py

# 数学の作図SVGを再生成(Release へは gh release upload --clobber で同名上書き)
python3 tools/gen_gimukyoiku_math_figs.py --out /tmp/mathfigs

# 全CSVの検証(CIと同じ)
python3 tools/validate_csvs.py
```

- Release のファイル名は `gk_<sha1(語)先頭10桁>`。バケットは先頭16進が8未満なら
  `gimukyoiku-image-v1`、以上なら `-v1b`。**同名上書きすればURL不変**なので、
  画像だけ差し替えるならCSVも利用側も変更不要
- レビュー用サーバは `gimukyoiku-imggen/review_server.py`。
  `WORDLISTS_DIR=<チェックアウト先> .venv/bin/python review_server.py --port 8401`
  で参照先を切り替えられる(2026-08-02にこの環境変数を足した)
- PRは wordlists なら main宛てでよい(CI通過でautomergeが即マージする)。
  **soramimic本体に触る場合だけ base=dev 必須**

## 5. 作業ファイルの置き場

セッションの scratchpad は消えるので、次に要るものは
**`/home/jiro/development/gimukyoiku-imggen/handoff_20260802/`** に退避してある。

- `textbook_units.tsv` — 教科書LODの単元名58,390件
- `unit_candidates.tsv` — 未収録の単元名候補5408件
- `manual_titles_final.tsv` — 採用した277件の対応づけ(MANUAL_TITLES に反映済み)
- `miss/miss_*.tsv` — 教科別の画像なしリスト(#96 の作業時点。再取得は下のワンライナー)
- `FIG_SPEC.md` / `framework.py` — 作図タスクをsubagentに渡すときの仕様書と枠組み。
  `framework.py` の中身は `tools/gen_gimukyoiku_math_figs.py` の前半と同じものなので、
  作図を他教科へ広げるときはそちらを import するかコピーして使う
- `verify_titles.py` — 語→記事名の対応づけ案を検証するスクリプト。
  `original / host(ja|en) / title` のTSVを渡すと、記事の有無・曖昧さ回避・画像の
  有無・静止画かどうかを判定して `.verified.tsv` を出す

画像なしリストの再取得:

```sh
python3 -c "
import csv, collections
r = [x for x in csv.DictReader(open('gimukyoiku.csv')) if not x['image']]
print(len(r), collections.Counter(x['subject'].split('/')[0] for x in r).most_common())
for x in r: print(x['original'], x['subject'], x['level'], x['description'], sep='	')
" > /tmp/miss.tsv
```
