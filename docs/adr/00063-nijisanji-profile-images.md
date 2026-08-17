# ADR 00063: にじさんじ公式プロフィール画像

- Status: Accepted
- Date: 2026-08-17
- Related: [00060](00060-nijisanji-official-roster.md) / [00062](00062-hololive-profile-images.md)

## 決定

にじさんじ公式タレントプロフィールで公開されている全身画像を、
`youtuber.csv` の通常の画像URLとして収録する。画像本体はリポジトリへ複製せず、
`image_page` に公式プロフィール、`image_credit` に権利者表記、
`image_usage=noncommercial_fanwork` と `image_terms_page` に公式利用条件を保持する。
利用側は条件確認を明示した場合だけ画像を使う。

対象と画像URLは `tools/youtuber_nijisanji_images.json` で固定し、公式名簿更新後に
`tools/apply_youtuber_nijisanji_images.py` を適用する。台帳にない画像URLは採用せず、
画像のSHA-256を記録して取得内容の同一性を検証可能にする。

初回対象は、公式名簿に掲載中の「にじさんじ」「NIJISANJI EN」所属198人である。
