# ADR 00016: football.csv の所属クラブ(team)列

- Status: accepted
- Date: 2026-07-27
- Supersedes: none
- Superseded by: none

## Context

ソラミミ動画のレイアウト(player_card)は「選手名 + 所属チーム」を出す想定で、baseball.csv の `team` 列を参照している。football.csv には `id,original,surface,pronunciation,type,category,image,image_page` しか無く、チーム情報が持てないため同じレイアウトを使い回せない。

football.csv は歴代選手を含む名鑑(7,344人)で、大半は現役ではない。所属クラブの情報源は2つある。

- Wikipedia日本語版の「Template:〇〇のメンバー」: 現役ロースターは正確で更新も速い。`tools/update_football.py` が既に同じ経路でJ1〜J3のクラブと選手を取っている。ただし現役しか載らない
- Wikidata の所属クラブ(P54): 歴代選手も辿れるが、移籍への追従が遅く、1人が複数クラブの文を持つ

選手は生涯に複数のクラブを渡り歩くので、1列に入れる「代表的な1クラブ」の決め方を決めないと値が安定しない。また監督(category=manager)の P54 は現役時代の所属になり、監督としてのチームとは別物になる。

## Decision

- `team` 列を `original` の後ろに追加する(baseball.csv と同じ列名・同じ位置。video側の player_card レイアウトをそのまま使い回せる)。値はクラブの日本語名(`鹿島アントラーズ`)
- 取得は `tools/enrich_football_team.py` の2段構え
  - まず Wikipedia の現役ロースター(update_football.py と同じ「Template:日本プロサッカーリーグ」→「Template:〇〇のメンバー」)。現役はWikidataより実態に近いのでこちらを優先する
  - 残りは Wikidata。選手は P54(所属クラブ)、監督は P6087(監督を務めたチーム)を見る。監督に P54 を使うと現役時代のクラブになってしまうため使わない
- 複数ある P54/P6087 から「最新の所属」を1つ選ぶ。並べ替えの優先順は
  1. 取り消された(deprecated)文は使わない
  2. 在籍終了日(P582)が無い文(=現所属)を最優先
  3. 次に終了日が新しい文、さらに開始日(P580)が新しい文
  4. それも並ぶときは Wikidata 上の記載順で後の文
- 各国代表チーム(P31が代表チーム、またはラベルが「〜代表」)はクラブではないので候補から除き、次の候補に送る
- マスコット(category=mascot)は人物ではなくクラブ側の情報なので対象外。空のままにする
- 既定では team が空の行だけ埋める(冪等)。`--refresh` で全行引き直し。取得結果は `tools/.cache/`(Git管理外)に逐次保存し、中断しても再開できる
- 引けなかった行は空にする(誤ったクラブを入れない)。player_card は team が空なら非表示になる

## Consequences

- 現役選手はロースター由来なので移籍直後でも正確。歴代選手は Wikidata のスナップショットで、引退時点の所属が入る
- 値は「代表的な1クラブ」であって在籍歴ではない。複数クラブを渡り歩いた選手の他クラブ時代は表現できない
- ja.wikipedia に記事が無い選手(旧リスト由来の下部リーグ選手など)は QID が引けず空のままになる
- Wikipedia 由来の値が混ざるため、列全体のライセンスは CC BY-SA 4.0 側に合わせて扱うのが安全(ADR 00013 と同じ整理)
- 月次バッチには入れない。移籍期を過ぎたら手動で `--refresh` する運用にする
