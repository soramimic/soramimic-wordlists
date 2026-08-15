# ADR 00051: 実在人名による名字読みの裏付け

- Status: accepted
- Date: 2026-08-13
- Related: 00038 / 00050 / 00052 / 00053

## Decision

`evidence_sources` に次の由来を追加する。

- `wikidata_person`: Wikidataの人物姓と姓アイテムの読みとの一致
- `official_web`: 公式人物ページの公開用根拠台帳との一致

どちらも実在人名の裏付けとして `verified=yes` にする。Wikidata由来情報は
CC0として扱う。公開用根拠台帳は判定に必要な最小項目だけを保持し、
取得元ページ本文、名簿、連絡先、検索記録は再配布しない。
