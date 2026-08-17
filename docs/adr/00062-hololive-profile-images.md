# ADR 00062: ホロライブ公式プロフィール画像

- Status: Accepted
- Date: 2026-08-17
- Related: [00011](00011-youtuber-vtuber-wordlist.md) / [00061](00061-youtuber-permitted-fan-images.md)

## 決定

ホロライブ公式タレントプロフィールで公開されている全身画像を、
`youtuber.csv` の通常の画像URLとして収録する。画像本体はリポジトリへ複製せず、
`image_page` に公式プロフィール、`image_credit` に権利者表記、
`image_usage=noncommercial_fanwork` と `image_terms_page` に公式利用条件を保持する。
利用側は条件確認を明示した場合だけ画像を使う。

対象と画像URLは `tools/youtuber_hololive_images.json` で固定し、更新処理後に
`tools/apply_youtuber_hololive_images.py` を適用する。現役・卒業・配信活動終了を
台帳で区別し、`youtuber.csv` の既存契約では後二者を `status=former` とする。

初回対象は現役63人、卒業9人、配信活動終了2人の計74人である。
