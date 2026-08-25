# 更新・メンテナンス

公開データから更新できるワードリストは月次ワークフローで更新され、変更は
CSV検証とテストを通過した場合だけ反映されます。

`myoji.csv` は月次ワークフローの対象外です。Jponの取得済み地域から名字単位に
再集計したスナップショットをレビューし、[ADR 00062](adr/00062-jpon-myoji-replacement.md)
の条件を満たす場合だけ手動で置き換えます。

## 公開仕様

- CSVの列と意味は [wordlists.md](wordlists.md) に記載します。
- 出典、帰属、ライセンスは [README](../README.md) と各行の
  `image_page`、公開された根拠台帳に記載します。
- 既存の人手補正、固定ID、確認済みの値は、自動更新で不用意に失わないよう保護します。
- 実在人物を扱うリストは公開情報だけを使用し、不要な個人情報や取得元ページ本文を
  再配布しません。

## OpenAI APIによる説明文補助

意味的な選択が必要な `description` は、[ADR 00066](adr/00066-openai-source-grounded-description-enrichment.md)
の範囲でだけOpenAI APIを補助的に利用します。LLMは確定済みの公開出典から完全一致する
抜粋を選ぶだけとし、同定、読み、分類、根拠のない補完には使いません。

実行前に、対象projectのData controls表示を確認した期限付きattestation、専用project・
API key、incentive dayごとの使用量台帳を確認します。台帳の内部上限は200万tokenとし、
`service_tier="default"`、`store=false`、toolsなしで実行します。これらは絶対的な無課金を
保証しないため、費用を一切許容できない場合は実行しません。既存の `NA` / `NA。` を
含むbulk migrationは、対象と検証結果を示す別PRで扱います。

月次workflowで有効にするには、専用projectのkeyをrepository secret
`OPENAI_API_KEY`、確認期限をrepository variable
`OPENAI_DATA_SHARING_INCENTIVE_CONFIRMED_UNTIL`（`YYYY-MM-DD`）に設定し、最後に
`OPENAI_LLM_ENRICHMENT_ENABLED=true` をrepository variableへ設定します。資格表示、
正の残高、projectのhard spend limitを確認できない場合は有効化しません。月次処理は
今回追加・変更された選手と前回未解決の選手を最大100件ずつ確認します。API送信前に
repository全体から確認できるimmutable artifactとして当日claimと翌日guardを保存し、
保存後のAPI照合とUTC日の再確認が成功した場合だけ送信します。失敗・cancel・runner消失
だけでなく成功時も翌日guardを残します。このため同じUTC日とその翌日は再送せず、
claimがないUTC日（最短で2日後）の新しい日次枠で再実行します。Actions cacheの保存は
再利用のためだけで、課金防止の安全根拠にはしません。

既存の欠損候補は、まずCSVを変更しない取得を小分けに実行し、その後同じ入力のcache
だけを適用します。

```bash
python3 tools/enrich_player_descriptions_openai.py football --fetch --include-degraded --limit 100
python3 tools/enrich_player_descriptions_openai.py football --apply --cache-only --include-degraded --limit 100
```

未変更の候補（本人同定不能やabstain）が先頭に残る場合は、実行時に表示された
`backlog cursor` を次回の両コマンドへ `--start-after ID` として渡します。月次の
`--changed-from` 対象は一度きりなので、件数が `--limit` を超えた場合は切り捨てずに
処理前に失敗します。月次で未解決だった候補は
`tools/openai_player_description_pending.jsonl` に残し、試行回数の少ない候補から
再確認します。採用した値は記事、QID、版、元文、最終説明を
`tools/openai_player_description_sources.jsonl` に固定します。

## 検証

ローカルでは次の公開検証を実行できます。

```bash
python3 tools/validate_csvs.py
```

各更新器の回帰テストは `tools/test_*.py` にあります。素材ごとの詳しい条件は
READMEの出典表示と関連ADRを参照してください。
