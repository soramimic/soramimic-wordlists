# ADR 00038: myoji.csv の公開仕様

- Status: accepted
- Date: 2026-01-30
- Related: 00001 / 00014 / 00050 / 00051 / 00052 / 00053 / 00054

## Decision

`myoji.csv` は名字の表記と読みを収録する。母集団と読みには
[SudachiDict](https://github.com/WorksApplications/SudachiDict)を使用し、追加の裏付けには
Web NDL Authorities、JMnedict、Wikidata、Wikipedia、および公開人物ページの
レビュー済み根拠台帳を使用する。

`rank` はWikidata上の著名人数による参考順位であり、人口・戸籍・世帯数の順位ではない。
同じ表記に複数の読みがある場合は同じ `id` を共有する。`verified` と
`evidence_sources` の意味は [wordlists.md](../wordlists.md) に定める。

電話帳、住宅地図、および再配布条件を確認できない民間ランキング由来の値は
`myoji.csv` に含めない。

## Attribution

SudachiDictはApache License 2.0で提供される。辞書にはUniDic（BSD 3-Clause）および
mecab-unidic-NEologd（Apache License 2.0）由来の素材が含まれる。JMnedict由来情報は
CC BY-SA 4.0、Wikidata由来情報はCC0、Wikipedia由来の文章はCC BY-SAの条件に従う。
Web NDL Authoritiesは同サービスの利用条件に従う。公開時の具体的な帰属先とリンクは
[README](../../README.md)に保持する。
