# ADR 00059: plant の分類補完と科別生成イメージ

- Status: accepted
- Date: 2026-08-16
- Related: 00008-plant-wordlist.md / 00014-no-degrading-existing-rows.md / 00017-plant-family-genus-columns.md

## Context

`plant.csv` 6,542行のうち、Commons実写がない743行は大分類SVGを共有していた。
旧処理はP18がある候補だけQIDを保存したため、この743行では取得可能な科・属まで
欠落していた。大分類より具体的なfallbackを使うには、画像の有無とtaxon同定を
分離する必要がある。

## Decision

- `enrich_plant_entities.py` は、種ランクの日本語ラベル完全一致候補を取得し、CSVの
  `class` に対応する植物クレードへ到達する候補だけに絞る。一意な候補だけQIDを
  保存し、複数候補・候補なしは未確定のままにする
- 明示対応が必要なtaxonは、学名と上位分類を確認したうえで `plant_overrides.py` に
  永続保存する。P18は保存済みQIDから別工程で取得し、QID・分類の保存条件にしない
- 画像の優先順位は、確認済み実写、目視QC済み科別生成イメージ、大分類SVGとする。
  科別画像は `family_wikidata` を安定キーに `images/plant/` へ960×600 WebPで保存し、
  右上に「生成イメージ」と表示する。後から実写が得られた場合は実写で置き換える
- 科別画像のplan/materialize/apply/validateを分離する。manifestには科名・科QID、
  最大3件の和名・学名例、prompt、accepted、全数目視QC記録、入力・出力SHA256を残す。
  未確認・不採用の画像はCSVへ割り当てない
- 月次更新はQID→分類→P18→大分類→科別画像の順で実行する。CSVの既存列を保持し、
  曖昧行は大分類SVGへ残す

## Consequences

- 初回補完では743行中699行が180科へ安全に割り当てられ、44行は未解決として
  大分類SVGのまま残る
- 既存の5,799件の実写は変更しない。科別生成イメージは699行に共有され、実写追加時
  には自動的に優先順位が上がる
- 科名変更や同名分類群があっても、科QIDを持つ画像名と割当で識別できる
