# ADR 00054: 名字の確認状態と順位

- Status: superseded
- Date: 2026-08-14
- Superseded by: 00062-jpon-myoji-replacement.md
- Related: 00038 / 00050 / 00051 / 00052 / 00053

## Decision

公開スキーマは `verified=yes/no` と `evidence_sources` を使用する。
`verified=no` は誤りを意味せず、採用済みの根拠で実在人名を確認できていないことだけを示す。
`jmnedict` は辞書収録の裏付けであり、単独では `verified=yes` にしない。

`rank` はWikidata上の著名人数による参考順位を維持する。人口、戸籍、電話帳掲載件数、
世帯数の順位として扱わない。再配布条件を確認できない電話帳・民間ランキング由来の値は
収録しない。
