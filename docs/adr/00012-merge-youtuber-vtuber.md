# ADR 00012: youtuber.csv と vtuber.csv を統合し category 列で区別する

- Status: superseded
- Date: 2026-07-25
- Supersedes: [00011](00011-youtuber-vtuber-wordlist.md) のうち「2ファイル構成」の判断(取得方式・列の意味・追記専用の運用は変更しない)
- Superseded by: [YouTuber・VTuberの分離仕様](../wordlists.md#youtubercsv--vtubercsv)

現在の公開仕様は [リスト別の列説明](../wordlists.md#youtubercsv--vtubercsv) を参照。
YouTuberとVTuberは別々のCSVで提供する。

## Context

ADR 00011 で youtuber.csv(838人)と vtuber.csv(256人)の 2 ファイル構成を採ったが、以下の理由で統合に倒す:

- **利用形態**: YouTuber と VTuber をまとめて替え歌の題材にしたいケースがある。ソラミミック(mini)のリスト定義は 1 ボタン = 1 ファイル(filepath が単数)のため、跨いだ結合はデータ層でしかできない。
- **UIの命名**: 統合ジャンルのボタン名として「配信者」等の広い語は不正確(動画勢を含み、リスト外のTwitch勢等を連想させる)。VTuber は「バーチャル YouTuber」の略であり、ボタン名「YouTuber」が両者を正確に包含する。
- **分ける理由の消失**: 実装の結果、両ファイルの列構成は完全に同一になった(00011 時点で想定した「付加情報の性質の違い」は生じなかった)。org 軸での分類漏れ(VTuber 事務所所属が youtuber 側に混入等)もゼロだった。

## Decision

**vtuber.csv を youtuber.csv に統合**し、`category` 列(`youtuber` / `vtuber`)で区別する。

- **列**: `id, original, surface, pronunciation, type, category, org, debut_year, status`(type の次に category)。
- **移行**: 既存 youtuber 行は id 据え置きで `category=youtuber`。旧 vtuber 行は id に +838(旧 youtuber の最大 id+1)のオフセットを加えて `category=vtuber` として続ける。original/surface/pronunciation は変更しない。id の再採番はこの 1 回限り(外部参照が付く前の統合のため許容)。
- **スクリプト**: `tools/update_vtuber.py` を廃止し、`tools/update_youtuber.py` が両職業(Q17125263 / Q55155641)を取得して 1 ファイルに追記する。QID フェイルセーフ・妥当性ガード(youtuber 200〜20,000 / vtuber 100〜10,000)は職業ごとに維持。両方の P106 を持つ者は vtuber とする(youtuber 側クエリで除外)。
- **アプリ側(別リポジトリ)**: ボタン名は「YouTuber」1 つとし、既存のフィルタ機構(nations の status フィルタと同じ)で category による絞り込み(YouTuber/VTuber、デフォルト両方ON)を提供する。

## Consequences

- まとめて使う(デフォルト)・どちらかだけ使う(フィルタ)の両方が 1 ボタンで実現できる。
- README の注意書きは従来どおり書き分ける: category=youtuber は実在人物(パブリシティ権の注記)、category=vtuber は企業 IP のキャラクター名。ファイルが 1 本になっても法的性格の区別は column で保たれる。
- 旧 vtuber.csv の id を参照していた利用者には破壊的変更(公開直後の統合のため実害は無い見込み)。
- 将来 VTuber の母数拡張(Wikidata P1814 仮名表記の利用等)を行う場合も、この 1 ファイル構成の上に追記する。
