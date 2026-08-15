# ADR 00050: 名字読みの追加根拠

- Status: accepted
- Date: 2026-08-13
- Related: 00038 / 00051

## Decision

`evidence_sources` は次の由来を区別する。

- `person_lists`: 本リポジトリの実在人名リストとの一致
- `ndl`: Web NDL Authoritiesの個人名典拠との一致
- `jmnedict`: JMnedictのsurnameエントリとの一致

`person_lists` または `ndl` がある行は `verified=yes` とする。
`jmnedict` 単独は辞書収録の裏付けであるため `verified=no` のままとする。

## Licensing and attribution

Web NDL Authorities由来情報は同サービスの利用条件に従う。JMnedict由来情報は
Electronic Dictionary Research and Development GroupのJMnedict/ENAMDICTに基づき、
CC BY-SA 4.0の条件で利用する。具体的なリンクは [README](../../README.md) に保持する。
