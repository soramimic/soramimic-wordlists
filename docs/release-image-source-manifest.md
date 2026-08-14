# GitHub Release画像 source manifest

`assets/release-image-source-manifest-v1.json` は、このリポジトリのCSVから参照する
GitHub Release画像の変更を、URLを変えずに利用側へ伝えるための台帳である。
Wikimedia Commonsなど、このリポジトリが公開を管理しないURLは対象外とする。

公開用の固定URLは次のRelease assetである。

```text
https://github.com/soramimic/soramimic-wordlists/releases/download/release-image-source-manifest-v1/source-manifest.json
```

初回だけ `release-image-source-manifest-v1` Releaseを作成しておく。tracked manifestと
公開markerは同じJSONで、schemaは
`assets/release-image-source-manifest-v1.schema.json` にある。

## 公開契約

- `assets` はcanonical `browser_download_url` をキーにする。
- 各entryの `revision` は内容が変わるたびに増加する。`sha256` を同一性の正とし、
  `updated_at` と `size` はGitHub APIで確認した値を記録する。
- top-level `revision` はmanifestの内容変更ごとに増加する。
- 画像をすべてuploadし、GitHub APIのdigestとsizeを検証した後にだけ、固定markerを
  `--clobber` する。markerが公開完了のコミットマーカーになる。
- 同一内容の再実行はentry revisionを増やさず、markerも更新しない。
- CSVからURLを削除しても、manifest entryは自動削除しない。利用側での参照解除と
  content-addressed blobのGCは別工程にする。

## 画像の公開

任意の画像公開経路から共通CLIを利用できる。

```sh
python3 tools/release_image_manifest.py publish TAG FILE [FILE ...] \
  --note "更新理由"
```

`publish` はmanifestのhashと違うファイルだけをuploadする。`--force` は画像を
同内容でも再uploadするが、hashが変わらなければmanifestは切り替えない。
`--dry-run` はupload件数だけを表示し、Release・tracked manifestとも変更しない。
`update` は `publish` のaliasである。

ポケモンカードは複数Release bucketを一つのtransactionとして扱うため、次を使う。

```sh
python3 tools/gen_pokemon_typecards.py --out build/pokemon_typecards \
  --upload --note "カード意匠更新"
```

class image、gimukyoiku、架空人物画像なども、個別の `gh release upload --clobber`
ではなく共通CLIを呼ぶ。画像upload/検証の途中で一件でも失敗するとmarkerは公開されず、
利用側はlast-good manifestを使い続ける。途中まで画像だけが更新された場合は同じpublishを
再実行すればよい。manifestに記録済みのhashとの差分が再送され、全件検証後にmarkerが進む。

## 初期化と検証

top-level CSVで現在参照中のRelease URLをGitHub APIのdigestから取り込む。

```sh
python3 tools/release_image_manifest.py bootstrap --dry-run
python3 tools/release_image_manifest.py bootstrap
gh release create release-image-source-manifest-v1 --title "Release image source manifest v1"
python3 tools/release_image_manifest.py publish-marker
python3 tools/release_image_manifest.py verify
```

`publish-marker` は初回公開または公開markerの復旧用である。全source assetを検証して
からtracked manifestを公開し、tracked file自体は変更しない。

`verify` は次を失敗として検出する。

- CSVで参照中なのにmanifestにないURL
- manifestのassetがReleaseにない
- canonical `browser_download_url` の不一致
- manifestとGitHub APIのsha256またはsizeの不一致

Release/API障害、upload失敗、hash不一致時は修正後に同じコマンドを再実行する。
公開markerを手で先行更新してはならない。
