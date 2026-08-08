# ADR 00042: nations の基礎情報・description 列

- Status: accepted
- Date: 2026-08-08
- Related: 00003(nations の表記・status) / 00014(既存行を劣化させない)

## Context

`nations.csv` は国名・読み・現存状態・国旗だけを持ち、人口や面積、国の特徴を
表示する情報がなかった。同じ国には正式名称・通称・旧称など複数行があり、
付加情報は表記ではなく国そのものに対応させる必要がある。

## Decision

- `capital`, `continent`, `population`, `area_km2`, `established_year`,
  `description` を追加する
- 基礎情報は各行の `wikidata` をキーに Wikidata から取得する。同じ item を指す
  別表記行には同じ値が入り、別 item を指す旧国名にはその旧国家の値が入る
- 人口は P1082 の時点(P585)が最新の整数値、面積は P2046 の平方キロメートル値、
  首都は P36、大陸は P30 とする。複数値は `/` 区切りにする
- `established_year` は P571 の非 deprecated 値のうち最古の西暦年とする。
  紀元前は `前660` の形式にする。これは現在の政体の発足年とは限らず、
  国の成立年には複数の解釈があることに注意する
- `description` は日本語版 Wikipedia の記事冒頭から既存の
  `make_description` で作る短い完結文とする。記事本文の転載ではなく、
  目安90字までの導入説明を収録する
- 人口は時変値なので月次更新で最新値に置き換える。他の列と description は
  空欄だけを補完し、取得失敗や上流の一時的欠落で既存値を消さない

## Consequences

- 利用側は人口・面積での比較や、首都・大陸・成立年・特徴の表示ができる
- Wikipedia 由来の description は CC BY-SA 4.0 として出典表示が必要
- 成立年を厳密な「建国年」と断定せず、利用側でも歴史的な目安として扱う
