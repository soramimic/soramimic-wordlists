# ADR 00018: youtuber.csv の画像(自由ライセンスの実写 + 象徴カード)

- Status: accepted
- Date: 2026-07-28
- Supersedes: none
- Superseded by: none

## Context

youtuber.csv だけが画像列(`image`/`image_page`)を持っていなかった。ソラミミ動画は単語ごとに
1枚絵を出すので、画像が無いリストは他のリストと同じ見せ方ができない。

一方でYouTuber/VTuberの画像は、他のリスト(生物・駅・ポケモン)と権利事情が大きく違う。

- **チャンネルアイコン・動画サムネイル**は本人または事務所の著作物で、引用の要件も満たさない
- **VTuberのキャラクターイラスト**はカバー・ANYCOLOR等の知的財産そのもの。README の利用上の注意でも
  「画像・キャラクターデザインは含みません」と明記している
- 実在人物なのでパブリシティ権・肖像権の配慮も要る(ADR 00011 で本名を収録しないと決めたのと同じ理由)

使えるのは Wikimedia Commons にある自由ライセンスのファイルだけだが、Commons にあるからといって
「実写」とは限らない。実際に Wikidata の P18(画像)を引くと、VTuber項目のP18は大半がアバターの
配信スクリーンショットや公式イラストで、`Screenshots of Virtual YouTubers` /
`Free depictions of non-free works`(非自由な原著作物を写したもの)といった Commons カテゴリが付く。
痛車の写真、コスプレイベントの写真も混ざる。素通しで採用すると、まさに避けたかったものが入る。

## Decision

### 1. 人物の同定は名前ではなく Wikidata の QID で行う

youtuber.csv はそもそも「P106(職業)がYouTuber(Q17125263)/バーチャルYouTuber(Q55155641)で
ja.wikipedia に記事がある人物」から生成されている(ADR 00011)。同じクエリを引き直せば
`original` = norm(ja記事名) で1対1に戻せるので、和名の文字列照合で同名の別人・一般名詞を拾う余地がない。
同じ `original` に別QIDがぶら下がった場合は**曖昧として捨てる**(画像も QID も入れない)。

同定できた人には `wikidata` 列に QID を入れる(画像の有無とは独立。永続キーとして使える)。

### 2. 実写は「Wikidata P18 + 多段の除外」を通ったものだけ採用する

P18 があっても、次をすべて満たさなければ採用しない。

1. その項目が **P31 = Q5(人間)** であること。VTuberの多くはキャラクター項目で、その P18 は
   アバターのイラスト/スクリーンショットなので、この1段でほぼ落ちる
2. MIME が `image/jpeg` か `image/png`(ベクター図版・アニメーションGIFを除く)
3. **ファイル名**に illustration / artwork / logo / icon / avatar / itasha / cosplay / イラスト 等を含まない
4. **Commonsのカテゴリ**に除外語を含まない。とくに
   - `Screenshots of Virtual YouTubers`(アバターのスクショ)
   - `Free depictions of non-free works`(非自由な原著作物の写り込み)
   - `Cosplay ...`(衣装は第三者の意匠。本人が写っていても採らない)
   - `Itasha ...` / `Virtual YouTubers on vehicles`

同じ人物に候補が複数あるときは、EXIFのカメラ情報や `Photographs ...` 系カテゴリという
「カメラで撮られた実写」の積極的根拠がある方を優先し、同点はファイル名で決定的に選ぶ。

表記が必要なライセンスがあるので `image_page`(Commonsのファイルページ)も必ず入れる。
soramimic-video 側が Commons の extmetadata から作者・ライセンスを取ってフレームに焼き込む。

### 3. 実写が取れない行には「象徴カード」SVGを割り当てる

pokemon の型色カード(ADR 00002)と同じ考え方で、**素材を一切借りずに配色と文字だけで**描く。

- 1人1枚。同じ人物の複数行(full/family/given)は同じ `original` なので同じカードを共有する
- ファイル名は `yt_<sha1(original)の先頭10桁>.svg`。id は将来の再採番に耐えないので使わない
- 配色は `category` と `org` で決まる。youtuberは暖色(赤〜橙)、vtuberは寒色(青紫)と帯を分け、
  **同じ事務所は同じ色相**になるよう org から決定的に色相を振る。所属なし(NA)は各カテゴリの基準色
- `org` はスラッシュ区切りの多値で事務所とユニット・期生が混ざる(`ROF-MAO/にじさんじ`,
  `ホロライブ/ホロライブ3期生`)。**最も短い要素**を採ると事務所側が残るので、それを色と表示に使う
- 中央に名前の頭文字、下部にフルネーム、上部に区分と所属を描く。実写と誤認されないよう
  右上に「イメージ」の札を必ず入れる(sekitsui/plant の概念イメージと同じ扱い)

### 4. 生成カードはリポジトリ内に置き、raw URL で参照する

pokemon/sekitsui/plant の生成画像は GitHub Release のアセットとして配布しているが、
youtuber のカードは `images/youtuber/` に置き、`image` は
`https://raw.githubusercontent.com/soramimic/soramimic-wordlists/main/images/youtuber/<file>.svg`、
`image_page` は同じファイルの blob ページを指す。理由は次の2点。

- 1枚1KB程度・1,000枚弱(合計1MB強)と小さく、Release のアセット上限(1リリース1000件)を
  意識した振り分けや、レート制限と戦うアップロード処理が要らない
- CSVと画像が同じコミットに入るので、URLとファイルの対応がPRの差分の中で完結して検証できる

これに伴い `tools/validate_csvs.py` の画像URL許可リストに、本リポジトリの raw / blob を追加する。

### 5. 列の位置と実行順

`image`, `image_page`, `wikidata` を末尾に足す(plant/sekitsui と同じ並び)。
実行順は「実写 → カード」。実写は空欄と生成カードの行を上書きしてよい(改善方向)が、
カード側は**実写がある行に絶対に触らない**。どちらも冪等。

## Consequences

- 実写が付くのは996人中284人(youtuber 281 / vtuber 3)。残り712人はカードになる。
  VTuberはほぼ全員がカードで、これは意図した結果である
- コスプレイヤーのYouTuber(くりえみ・みゃこ・ピョ・ウンジ・かざり)は、本人が写った写真でも
  衣装が第三者の意匠なので採用しない。デュオ・グループ項目(はなおでんがん等)は P31 が Q5 でないため
  実写があっても落ちる。いずれも「取りこぼしてもカードで埋まる」ので、判断を安全側に倒している
- Commons のカテゴリ運用に依存する。カテゴリが付いていないアバター画像が現れたら素通ししうるので、
  除外パターンは実データを見ながら育てる前提とする
- 画像は Wikipedia/Commons 由来(CC BY-SA 等)と本リポジトリ生成(CC0相当)が混在する。
  利用側は `image_page` のクレジット条件に従う。生成カードは Commons ではないので
  soramimic-video 側のクレジット取得は素通りする(表記不要)
- 月次バッチには入れない。新規追加行はカードだけ先に付き、実写は手動実行で後追いする運用にする
  (WDQS + Commons API への問い合わせが数分かかるため)
