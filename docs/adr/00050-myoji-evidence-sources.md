# ADR 00050: 名字の読みの裏付けをNDL人物典拠とJMnedictへ広げる

- Status: accepted
- Date: 2026-08-13
- Supersedes: none
- Superseded by: 00051 (verifiedの人物裏付けソースを追加)
- Related: 00001 / 00014 / 00038

## Context

`myoji.csv` の母集団と読みは SudachiDict から得ているが、従来の `verified` は
本リポジトリ内の4つの実在人名リストだけとの一致で判定していた。107,063組の
表記・読みのうち確認済みは4,316組に限られ、珍しい姓や人物リストの対象外分野を
十分に裏付けられなかった。

調査の結果、次の再利用可能なソースが利用できる。

- Web NDL Authorities: 国立国会図書館の個人名典拠。姓名とカタカナ読みを保持し、
  SPARQLで機械取得できる。取得データであることの明示を条件に申請なしで利用可能
- JMnedict: EDRDGの日本語固有名詞辞書。姓コード付きの表記と読みを約14万組持つ。
  CC BY-SA 4.0で、相当量の利用時は出典とライセンスの明示が必要

NDLは実在人物を記述する典拠だが、JMnedictは辞書である。両者を同じ意味の
`verified=yes` にまとめると、人物による確認と辞書収録の区別が失われる。

## Decision

`myoji.csv` の末尾に `evidence_sources` 列を追加し、次の固定トークンを `|` 区切りで
保持する。

- `person_lists`: 本リポジトリの実在人名リストとの一致
- `ndl`: Web NDL Authoritiesの個人名典拠との一致
- `jmnedict`: JMnedictのsurnameコード付きエントリとの一致

`verified=yes` は `person_lists` または `ndl` のいずれかがある行に付ける。
`jmnedict` 単独の行は辞書上の裏付けはあるが、実在人物による確認ではないため
`verified=no` のままとする。

Web NDL Authoritiesでは、公式のSPARQL例と同じく個人名典拠の優先ラベルと読みの
コンマ前を姓・姓読みとして取得する。JMnedictでは `name_type` が
`family or surname` のエントリだけを採り、読みの適用先を示す `re_restr` も尊重する。

導入時の実測では、NDLから条件を満たす61,554組、JMnedictから142,156組を取得した。
現行CSVとの一致はNDLが35,070組、JMnedictが79,175組で、人物確認済みは
4,316組から35,490組へ増えた。JMnedictだけに一致する46,584組は
`verified=no,evidence_sources=jmnedict` として区別できる。

既存の方針と同様、裏付けは一方向に追加する。外部データの一時的な欠落やAPI障害で
既存の `verified=yes` や `evidence_sources` を削除しない。列追加前の
`verified=yes` は、その生成経路から `person_lists` として移行する。

## Licensing and attribution

Web NDL Authorities由来データを利用していることをREADMEに明示する。
JMnedict由来部分は Electronic Dictionary Research and Development Group の
JMnedict/ENAMDICTに基づき、CC BY-SA 4.0の条件で利用する。JMnedict由来の
`evidence_sources` 情報を再配布・改変する場合も同ライセンス条件に従う。

## Consequences

- 利用側は実在人名で確認済みの行を従来どおり `verified=yes` で絞れる
- 辞書収録まで含めたい場合は `evidence_sources` の `jmnedict` を利用できる
- CSV列が1つ増えるため、列数を固定している利用側には更新が必要。ただし既存列の
  位置を保つため新列は末尾に追加する
- 月次更新でNDL SPARQLとJMnedictの取得時間が増えるため、`MYOJI_CACHE` 指定時は
  NDLの抽出結果とJMnedict配布ファイルをキャッシュする
