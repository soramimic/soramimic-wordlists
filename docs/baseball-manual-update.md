# 野球選手表の一括更新手順(手動)

現役選手の新規追加は `tools/update_baseball.py`(自動更新)で行う。
ここに書くのは、提供元の選手表(スプレッドシート)を丸ごと取り込み直す場合の手順。頻度は低い。

1. 提供元から最新の野球選手表をダウンロード
2. Sheet1をcsvにして1−4行目を削除。文字コードはutf8。ここでは `new_baseball_raw.csv` とする
   - 使われる列は「氏名」「球団」「フルネーム ふりがな」「姓 フリガナ」「名 フリガナ」のみ
3. 差分csvを作成:
   ```sh
   cd tools
   uv run make_diff_baseball_tidy.py -n new_baseball_raw.csv -c ../baseball.csv -o output.csv
   ```
4. 出力の `score`(NameDividerのスコア。低いほど怪しい)や `note` が「please check」の行を中心に名字分割を目視確認(偽陽性多め)
5. 確認後、`score`/`note` 列を削除して `baseball.csv` に追記する(Google Sheet等の利用推奨)
