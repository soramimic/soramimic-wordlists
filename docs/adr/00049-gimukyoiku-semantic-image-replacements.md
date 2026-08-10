# ADR 00049: gimukyoiku の定義箱SVGを意味のある画像へ置き換える

- Status: accepted
- Date: 2026-08-10
- Related: 00028 / 00037 / 00039 / 00040 / 00041
- Supersedes: 00041の「画像生成グリッドは最大2×2」制限

## Context

画像欠損をゼロにする過程で追加した汎用SVGのうち、157語は教材画像としての
視覚的価値が低かった。内訳は、説明文を横並びの箱と矢印にした `flow` 64件と、
語と定義文を等号で結んだ `compare` 93件である。画像を見ても語義の構造や場面が
分からず、CSVの説明文を小さく描き直しただけになっていた。

## Decision

157語を語義に応じて三方式へ置き換える。

- 場面・活動・実物が重要な56語は、ログイン済みChatGPT Webの画像生成を使う。
  単純な構図は7×7、複雑な構図は4×4・2×2・1×1へ段階的に下げ、各セルを目視QCする。
  00041で問題になった等分切りによる境界混入を避けるため、罫線帯を画像ごとに検出して
  その両側をトリムする分割器へ変更した。7×7の49セルと既存2×2を使って隣接セルの
  混入がないことを確認し、不合格セルは小さいグリッドで再生成する条件で上限制限を改める。
- 因果・階層・分岐・比較・循環・表などの関係が重要な98語は、
  `gen_gimukyoiku_semantic_figs.py` で320×200の自己完結SVGを描く。
  仕様は `gimukyoiku_semantic_fig_specs.jsonl` に短いラベル、ノード、エッジ、精度上の注意として記録する。
- 原史料や既存の正確な模式図が適する3語はWikimedia Commonsを使う。
  慶安の御触書・公事方御定書はPublic domain、ニホニウム模式図はCC BY-SA 4.0で、
  Commons上の画像をCSVから直接参照し、出典・作者・ライセンスを置換計画に残す。

ChatGPT Web生成画像には右上へ「AIイメージ」と焼き込む。プログラム作図SVGには
生成AI表示を付けず、manifestのmethodを `svg` とする。Commons画像はReleaseへ再配布せず、
CSVの `image` をWikimediaへ、`image_page` を出典ページへ直接向ける。

置換対象とプロンプト・出典は
`gimukyoiku_semantic_image_replacements.jsonl` に固定し、
`apply_gimukyoiku_semantic_images.py` でCSVとmanifestへ冪等に適用する。

## Validation

- ChatGPT Web候補は全セルを実見し、不正確なセルを小さいグリッドで再生成した。
- SVGは分割レビューを繰り返し、矢印方向、ラベル重なり、科学・歴史上の正確性を確認した。
- 全98 SVGをXML parseし、viewBoxが `0 0 320 200` であることを検証する。
- 適用スクリプトの単体テスト、`--check`、全CSV検証をPR前に実行する。

## Consequences

- 157語は説明文の箱から、場面画像56件・意味関係図98件・Commons画像3件へ変わる。
- 既存98 SVGは同名Release assetを上書きするためURLが変わらない。
- 56件は拡張子がSVGからJPEGへ変わるため、CSVとmanifestも新しいファイル名へ更新する。
- Commons画像3件はRelease asset数とライセンス混在を避けるため直接参照し、出典情報を置換計画と `image_page` に維持する。
- JPEG・Commonsへ切り替えた59件の旧SVGは、Releaseの1,000 asset上限を圧迫しないよう置換確認後に削除する。
