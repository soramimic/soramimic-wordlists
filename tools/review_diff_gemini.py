#!/usr/bin/env python3
"""自動更新PRの差分をGemini APIでレビューし、OK/NG判定をJSONで出力する。

review-auto-update.yml から呼ばれる。標準ライブラリのみ使用。
無料枠のAPIキー(https://aistudio.google.com/apikey)を環境変数
GEMINI_API_KEY で渡す。モデルは GEMINI_MODEL で上書き可能。

使い方:
    python tools/review_diff_gemini.py pr.diff -o verdict.json

verdict.json の形式: {"verdict": "OK" | "NG", "reasons": ["..."]}
終了コード: 0=判定を出力できた(OK/NGどちらでも) / 2=APIエラー等で判定不能
判定不能時は呼び出し側(ワークフロー)がジョブを失敗させ、マージは止まる。
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.5-flash"
# 差分がこれを超えたらAPIを呼ばずNG(人間レビューに回す)
MAX_DIFF_CHARS = 800_000
RETRIES = 3
RETRY_WAIT_SEC = 30

PROMPT = """\
あなたは空耳ワードリスト(日本語の単語CSV)の品質チェック担当です。
以下は月次自動更新バッチが作ったPRのdiffです。追加・変更内容を確認し、
自動マージしてよいか判定してください。

観点:
- 人名リスト(baseball.csv / football.csv / scientist.csv):
  追加行(+行)を全行確認。姓名分割が不自然でないか(姓に名の一部が混入等)、
  読み(カタカナ)が名前と明らかに不整合でないか、記事名の括弧書き・記号・
  明らかなゴミ文字列が混入していないか
- 選手リスト(baseball.csv / football.csv)のdescription:
  カードに単独表示して意味が通る短い完結文か確認。「また」「同年」「その後」
  「この年」「翌年」のように前文を必要とする表現、何を指すか不明な「チーム」、
  「〜するなど。」「〜しており。」のような未完の断片があればNG。また、
  曖昧さ回避ページの人物一覧や、同名の野球選手・俳優・作家など別人の説明を
  選手descriptionとして採用していればNG
- その他のリスト(stations/pokemon/nations/sekitsui/plant/insect/youtuber):
  追加行を確認し、全体として異常(大量のゴミ行、日本語名でない行、
  カテゴリ違いの混入)がないか
- 既存行の変更(-行と+行の対): status更新・画像列(image/image_page)の付与・
  channel/subscribers/subscribers_as_of列のスナップショット更新など
  想定内の変更だけか。original/surface/読みの
  書き換えや行の削除があればNG

このデータの仕様(以下はNGの理由にしないこと):
- カタカナ名(中黒「・」区切り)の人物は、family/given行でも表層(surface)が
  フルネームのままになっている(仕様)。読みの列だけが姓/名に分割されている
- 日本人の珍しい読み(いわゆるキラキラネーム。例: 輝夢=キラム)は実在する。
  「珍しい」だけでは疑わず、漢字と音がまったく対応しない場合のみNGにする
- scientist.csvは物理/化学/数学/天文/生物/計算機/地学の広義の科学者リストで、
  隣接分野の人物や他職と兼業の人物(政治家等)も仕様として含まれる
- sekitsui.csv / plant.csv / insect.csv は和名が同音異義になっている行を
  重複して持つことがある(カマキリ=昆虫と魚アユカケの別名、スギ=植物と
  動物、トンボ・セミ等)。別リストに同じ和名があること自体はNGにしない。
  insect.csv の class は目そのものではなく粗い区分(甲虫/チョウ/ハチ/ハエ/
  カメムシ/バッタ/トンボ/その他)で、カマキリ・ゴキブリ・シロアリ等が
  「その他」になるのは仕様
- scientist.csvのstatus列の「存命→物故」への一方向変更は想定内の更新
  (Wikidataに死没日が登録されたことを意味する)。あなたの知識で存命と
  思える人物でも、あなたの知識より新しい情報である可能性が高いため、
  これだけを理由にNGにしないこと(物故→存命への逆方向はNG)
- youtuber.csvのchannel/subscribers/subscribers_as_of列は同じYouTube API
  スナップショットとして更新され、毎月の実行で subscribers は
  ほぼ全行(700行規模)の数値が一斉に更新される(ADR 00030の仕様)。変更行数の
  多さや変動幅の大きさ、チャンネル改名によるchannel変更はNGの理由にしない。
  この3列以外が同じ行で一緒に書き換わっていないかだけを確認する

判定基準: 上記仕様に該当するものはOK扱い。それ以外で明確な誤り(姓名の逆転、
読みと名前の明白な不整合、ゴミ混入、文脈依存・未完の選手description、
既存行の破壊的変更)があればNG、迷ったらNG。
NGにしてもPRは閉じられず人間が確認するだけなので、不確かな場合は遠慮なく
NGにしてよい。reasonsには疑わしい行の内容と理由を日本語で具体的に書くこと
(OKの場合は確認した範囲の要約を1件書く)。

--- diff ここから ---
{diff}
--- diff ここまで ---
"""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "verdict": {"type": "STRING", "enum": ["OK", "NG"]},
        "reasons": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["verdict", "reasons"],
}


def call_gemini(api_key: str, model: str, prompt: str) -> dict:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    req = urllib.request.Request(
        API_URL.format(model=model),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
    )
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=300) as res:
                data = json.load(res)
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            verdict = json.loads(text)
            if verdict.get("verdict") not in ("OK", "NG"):
                raise ValueError(f"unexpected verdict: {verdict!r}")
            verdict.setdefault("reasons", [])
            return verdict
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}"
            # 429(無料枠のレート制限)や5xxは待って再試行
            if e.code not in (429, 500, 503) or attempt == RETRIES:
                break
        except Exception as e:  # ネットワーク断・想定外レスポンス
            last_err = repr(e)
            if attempt == RETRIES:
                break
        print(f"retry {attempt}/{RETRIES}: {last_err}", file=sys.stderr)
        time.sleep(RETRY_WAIT_SEC * attempt)
    raise RuntimeError(f"Gemini API呼び出しに失敗: {last_err}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diff_file", help="レビュー対象のdiffファイル")
    parser.add_argument("-o", "--output", default="verdict.json")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY が設定されていません", file=sys.stderr)
        return 2

    with open(args.diff_file, encoding="utf-8", errors="replace") as f:
        diff = f.read()

    if not diff.strip():
        verdict = {"verdict": "OK", "reasons": ["差分が空のためレビュー対象なし"]}
    elif len(diff) > MAX_DIFF_CHARS:
        verdict = {
            "verdict": "NG",
            "reasons": [
                f"差分が大きすぎるため自動レビューをスキップしました"
                f"({len(diff)}文字 > {MAX_DIFF_CHARS}文字)。人間が確認してください"
            ],
        }
    else:
        model = os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
        try:
            verdict = call_gemini(api_key, model, PROMPT.format(diff=diff))
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 2

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(verdict, f, ensure_ascii=False, indent=2)
    print(f"verdict={verdict['verdict']} -> {args.output}")
    for r in verdict["reasons"]:
        print(f"- {r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
