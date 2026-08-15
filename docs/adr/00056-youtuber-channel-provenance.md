# ADR 00056: YouTuberチャンネル名を公式URLとYouTube APIから安全に補完する

- Status: accepted
- Date: 2026-08-15
- Supersedes: 00055 のchannel自動上書き規則
- Related: 00029(channel列) / 00030(subscribers列) / 00055(API title初回同期)

## Context

`youtuber.csv` は972人中685人だけがchannelを持つ一方、channelがNAでもWikidataの
P2397とYouTube Data APIの登録者数を取得済みの人が22人いた。従来の登録者数更新は
`channels.list(part=statistics)` の結果を人数だけに縮約するため、最大登録者数の
チャンネルIDと正式なチャンネル名を対応させたまま補完できなかった。

残る欠損には、本人のja.wikipedia記事の外部リンクやWikidataの公式サイト(P856)に
公式YouTube URLがある場合がある。ただし名前検索は同名人物、偽アカウント、切り抜き、
サブチャンネルを誤採用しうる。

## Decision

1. `channels.list` は `part=statistics,snippet` で取得し、channel ID、subscriberCount、
   snippet.titleを一つのレコードとして保持する。複数チャンネルは登録者数最大の
   レコードを選び、同数ならchannel ID昇順とする。
2. channelは空欄/NAだけをsnippet.titleで補完する。既存値は自動上書きしない。
   既存channelが選定titleと異なる、または選定IDを取得できない場合は、channelだけを
   古いままにしてsubscribersを別IDから更新せず、3値の以前のスナップショットを保持して
   候補レポートへ出す。一致する行のsubscribers更新規則はADR 00030のまま維持する。
3. P2397以外の自動採用元は、本人QIDのP856が直接指すYouTubeチャンネルURLと、本人の
   ja.wikipedia記事の外部リンク節で「公式」または本人名が明記されたチャンネルURLに
   限る。`/channel/UC...`、Data APIでcanonical IDへ解決できる`@handle`と`/user/`だけを
   扱う。動画、再生リスト、`/c/`、明示性のないURLは採用しない。
4. YouTubeの名前検索は行わない。曖昧・解決不能・既存値と異なる候補はCSVへ書かない。
5. 採用根拠は`tools/youtuber_channel_sources.jsonl`、保留候補は
   `tools/youtuber_channel_candidates.jsonl`へ人物ID、QID、URL、判定理由付きで保存する。
6. Wikimediaの429/maxlagは再試行し、取得不能はその人物だけ保留する。APIキーは既存の
   秘匿・redaction規則を継続する。

## Consequences

- 2026-08-15の実行でchannelは685/972人から721/972人へ増えた。P2397経路22人に加え、
  本人記事の明示的な公式外部リンク経路14人を補完し、既存値の消失は0人とした。
- 本人記事から18チャンネルを検証し、複数チャンネルの人物は最新登録者数最大の1本を
  CSVへ採用した。明示性不足または安全に解決できない候補26人は保留した。
- channelとsubscribersを独立に最大化しないため、新規補完値は常に同一channel IDを指す。
- ADR 00055の初回同期で既存91人をYouTube公式titleへ合わせた履歴は保持するが、以後は
  改名や最大チャンネル変更を自動反映せず監査へ回す。
