# ADR 00057: YouTuberチャンネルの本人直結ソースを拡張する

- Status: accepted
- Date: 2026-08-15
- Related: 00056(channel補完と由来台帳)

## Context

ADR 00056の適用後も972人中251人はchannelが欠損していた。一般Web検索は追加候補を
見つける助けになる一方、検索順位や名前一致だけでは同名人物、グループ、切り抜き、
企業共通チャンネルを本人のチャンネルと誤認しうる。

再調査すると、本人QIDのYouTube handle(P11245)、本人QIDに直結するja.wikipedia記事の
先頭infobox、P856公式ページ上のYouTubeリンクに、検索結果より強い対応根拠が残っていた。

## Decision

1. Web検索は発見と調査経路の改善に使えるが、検索結果自体は自動採用根拠にしない。
2. 非deprecatedのP11245を本人直結識別子として扱い、`channels.list(forHandle=...)`で
   canonical UC IDへ解決できたものだけを採用する。
3. 本人QIDのja.wikipedia sitelinkがリダイレクトでない場合に限り、記事先頭の
   `Infobox YouTube personality` / `Infobox YouTuber`のchannel系フィールドを採用する。
   リダイレクト先がグループ記事の場合は自動採用しない。
4. 一般Web検索でP856公式ページ上のYouTubeリンクを見つけても、定期処理からP856 URLへ
   アクセスしない。公開編集可能なURLによるSSRFを避け、人物との対応とリンク先を
   人手確認して由来台帳へ追加する。別ドメインへの転送、複数候補、動画・再生リスト・
   未対応カスタムURLは保留する。
5. `/channel/UC...`、`@handle`、`/user/`に既知のチャンネルタブが付くURLは同じ
   channel locatorへ正規化する。任意の追加パスは許可しない。
6. 全経路の候補を合流してAPI確認してから登録者数最大の一件を選ぶ。channel、
   subscribers、snippet.titleは常に同じUC IDのレコードを使う。

## Consequences

- 2026-08-15の再監査で118人を追加し、channel網羅率は721/972人(74.18%)から
  839/972人(86.32%)へ上がった。
- 新規人物の主な根拠は、本人記事の先頭infoboxが59人、外部リンクが33人、P11245が
  20人、P856公式ページが6人だった。複数経路を持つ人物は人物単位で重複除外した。
- リダイレクト先のグループ記事、複数の公式サイト候補、取得不能なhandleは
  `tools/youtuber_channel_candidates.jsonl`へ残り、CSVへは入らない。
- P856公式ページの6人はWeb検索とページ確認で採用した。定期処理はその証跡をAPIで
  再検証するが、P856本文を自動取得しない。
