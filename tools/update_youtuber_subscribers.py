#!/usr/bin/env python3
"""youtuber.csv の subscribers 列(YouTubeチャンネル登録者数)を更新する。

出典: WikidataのYouTubeチャンネルID(P2397、CC0)と YouTube Data API v3 の
channels.list(part=statistics)。Wikidataの登録者数(P3744)は記録時点が項目ごとに
バラバラ(2019〜2026年が混在)で横比較できないため使わない(詳細は ADR 00030)。

- 対象は wikidata 列にQIDが入っている人。QIDが無い行は NA
- 1人が複数チャンネルを持つ場合は**その人のチャンネル群で最大の登録者数**を採る
  (channel 列の「登録者数が最大の1本をメインとみなす」定義と揃える)
- 登録者数を非公開にしているチャンネル(hiddenSubscriberCount)は候補から除く。
  1本も取れなければ NA
- **subscribers と subscribers_as_of は毎回全行を上書きする**。時変値なので
  「既存値は書き換えない」(ADR 00014)の明示的な例外(ADR 00030)。この2列以外の
  列・行順・id は一切変更しない。登録者数が取れない行は両列とも NA
- 書き込みは全チャンネルの取得が成功してから最後に一時ファイルを置換して行う
  (途中で失敗した回は youtuber.csv を書きかけのまま残さず、登録者数と取得日が
  別々のスナップショットになることもない)
- APIキーは環境変数 YOUTUBE_API_KEY、無ければ ~/.config/soramimic/youtube_api_key。
  どちらも無ければ「スキップ」を出して正常終了する(fork や鍵未設定のCIで
  ワークフローを壊さないため)

APIキーはログに出さない。例外メッセージやレスポンス本文に混ざる可能性を考えて、
出力は必ず _redact() を通す。

クォータ消費は channels.list 1回=1ユニット(1日10000ユニット)。全体で20回未満。

usage:
  python3 tools/update_youtuber_subscribers.py
"""

import csv
import json
import os
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import UA, sparql, write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "youtuber.csv"
KEY_FILE = Path.home() / ".config" / "soramimic" / "youtube_api_key"
API = "https://www.googleapis.com/youtube/v3/channels"
COL = "subscribers"
AS_OF_COL = "subscribers_as_of"
QID_BATCH = 200  # SPARQL の VALUES に並べるQID数(fetch_attrs と同じ)
YT_BATCH = 50    # channels.list の id パラメータは1回50件まで
# YouTubeチャンネルIDの書式(UC + 22文字)。P2397 にURLやユーザー名が
# 誤登録されていることがあるので、API に投げる前に弾く
CHANNEL_ID_RE = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
# 登録者数が取れた人数がこれを下回ったら取得失敗とみなし、書き込まずに終了する
# (毎回上書きする列なので、取得が壊れた回に既存値をNAで潰さないための下限)
MIN_PEOPLE = 300


def _utc_date() -> str:
    """成功したスナップショットの取得日を UTC の ISO 8601 形式で返す。"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date().isoformat()


def apply_snapshot(rows: list, cols: list, best: dict, as_of: str) -> tuple:
    """同一スナップショットの登録者数と取得日を全行へ反映する。

    返り値は (新たに値が入った人, 値が変わった人, 取れなくなった人)。
    subscribers が NA の行では取得日も必ず NA にして、古い日付を残さない。
    """
    for col in (COL, AS_OF_COL):
        if col not in cols:
            cols.append(col)

    filled, updated, lost = set(), set(), set()
    for row in rows:
        old = row.get(COL) or ""
        new = str(best[row["id"]]) if row["id"] in best else "NA"
        if old != new:
            if new == "NA":
                # 前回は値があったのに今回取れなかった(空 -> NA は列の新設なので
                # 「取れなくなった」ではない)
                if old != "":
                    lost.add(row["id"])
            elif old in ("", "NA"):
                filled.add(row["id"])
            else:
                updated.add(row["id"])
        row[COL] = new
        row[AS_OF_COL] = as_of if new != "NA" else "NA"
        for col in cols:
            row.setdefault(col, "")
    return filled, updated, lost


def write_snapshot_atomic(path: Path, cols: list, rows: list) -> None:
    """同じディレクトリの一時ファイルを置換し、CSVを原子的に更新する。"""
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                    dir=path.parent)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        write_csv_no_trailing_newline(tmp_path, cols, rows)
        os.chmod(tmp_path, stat.S_IMODE(path.stat().st_mode))
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _load_key() -> str:
    """APIキーを環境変数またはファイルから読む(無ければ空文字)。"""
    key = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    return key


def _redact(text: str, key: str) -> str:
    """ログに出す文字列からAPIキーを消す。"""
    return text.replace(key, "<redacted>") if key else text


def fetch_channel_ids(qids: list) -> dict:
    """QID -> [チャンネルID, ...] を P2397 からバッチ取得する。

    取り消し済み(DeprecatedRank)の文は除く(yt_common.fetch_attrs と同じ扱い)。"""
    out = {}
    bad = set()
    for i in range(0, len(qids), QID_BATCH):
        batch = qids[i:i + QID_BATCH]
        values = " ".join(f"wd:{q}" for q in batch)
        q = f"""
SELECT ?p ?ch WHERE {{
  VALUES ?p {{ {values} }}
  ?p p:P2397 ?st . ?st ps:P2397 ?ch .
  FILTER NOT EXISTS {{ ?st wikibase:rank wikibase:DeprecatedRank }}
}}"""
        for b in sparql(q)["results"]["bindings"]:
            qid = b["p"]["value"].rsplit("/", 1)[1]
            ch = b["ch"]["value"].strip()
            if not CHANNEL_ID_RE.match(ch):
                bad.add(ch)
                continue
            out.setdefault(qid, []).append(ch)
        print(f"  チャンネルID取得 {min(i + QID_BATCH, len(qids))}/{len(qids)}",
              flush=True)
    if bad:
        print(f"  書式不正のP2397値を無視: {len(bad)}件: "
              + ", ".join(sorted(bad)[:5]), flush=True)
    return {q: sorted(set(v)) for q, v in out.items()}


def _get(url: str, key: str) -> dict:
    """channels.list を叩く。一時的な失敗は再試行し、それ以外は即中断する。"""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as res:
                return json.load(res)
        except urllib.error.HTTPError as ex:
            body = ""
            try:
                body = json.loads(ex.read().decode("utf-8"))
                body = body.get("error", {}).get("message", "")
            except Exception:
                pass
            msg = _redact(f"HTTP {ex.code}: {body}", key)
            # 4xx(403 クォータ超過・APIキー無効、400 パラメータ不正)は
            # 待っても直らないので即中断する
            if ex.code < 500:
                raise SystemExit(
                    f"error: YouTube Data API が {msg} を返しました。"
                    "クォータ超過・APIキーの無効/制限を確認してください")
            print(f"  YouTube API retry {attempt}: {msg}", flush=True)
        except Exception as ex:  # ネットワーク・タイムアウト
            print(f"  YouTube API retry {attempt}: "
                  f"{_redact(str(ex), key)}", flush=True)
        if attempt < 2:
            time.sleep(5 * (attempt + 1))
    raise SystemExit("error: YouTube Data API への問い合わせが3回失敗しました")


def fetch_subscribers(channel_ids: list, key: str) -> tuple:
    """チャンネルID -> 登録者数(int)。非公開・削除済みのチャンネルは含まない。

    返り値は (登録者数の辞書, 非公開だったチャンネル数)。"""
    subs, hidden = {}, 0
    for i in range(0, len(channel_ids), YT_BATCH):
        batch = channel_ids[i:i + YT_BATCH]
        url = API + "?" + urllib.parse.urlencode(
            {"part": "statistics", "id": ",".join(batch), "key": key})
        data = _get(url, key)
        for item in data.get("items", []):
            st = item.get("statistics", {})
            if st.get("hiddenSubscriberCount"):
                hidden += 1
                continue
            try:
                subs[item["id"]] = int(st["subscriberCount"])
            except (KeyError, TypeError, ValueError):
                continue
        # itemsに返らないID(削除・BANされたチャンネル)は静かにスキップする
        print(f"  登録者数取得 {min(i + YT_BATCH, len(channel_ids))}/"
              f"{len(channel_ids)}", flush=True)
    return subs, hidden


def main() -> int:
    key = _load_key()
    if not key:
        print("スキップ(YouTube APIキーが無い): 環境変数 YOUTUBE_API_KEY か "
              f"{KEY_FILE} を設定してください", flush=True)
        return 0

    with CSV_PATH.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        cols = list(reader.fieldnames or [])

    # id が1人の単位(family/given/full で複数行)。QIDは本人のもの
    qid_of = {}
    for r in rows:
        qid = (r.get("wikidata") or "").strip()
        if qid and qid not in ("NA",):
            qid_of[r["id"]] = qid
    people = len({r["id"] for r in rows})
    print(f"youtuber.csv: {len(rows)}行 / {people}人 "
          f"(QIDあり {len(qid_of)}人)", flush=True)

    qids = sorted(set(qid_of.values()))
    chans = fetch_channel_ids(qids)
    all_ids = sorted({c for v in chans.values() for c in v})
    print(f"P2397のチャンネルID: {len(all_ids)}本 / {len(chans)}人", flush=True)

    subs, hidden = fetch_subscribers(all_ids, key)
    print(f"登録者数が取れたチャンネル: {len(subs)}/{len(all_ids)}本"
          f"(非公開 {hidden}本、取得不能 "
          f"{len(all_ids) - len(subs) - hidden}本)", flush=True)

    # 人ごとに、その人のチャンネル群の最大値を採る
    best = {}
    for pid, qid in qid_of.items():
        vals = [subs[c] for c in chans.get(qid, []) if c in subs]
        if vals:
            best[pid] = max(vals)
    if len(best) < MIN_PEOPLE:
        print(f"error: implausible subscribers count: {len(best)}人"
              f"(下限 {MIN_PEOPLE}人)。取得が壊れている可能性があるため"
              "書き込まずに中断します", file=sys.stderr)
        return 1

    # ここから書き込み(全取得が成功した後に、2列を1回の置換で反映)
    as_of = _utc_date()
    filled, updated, lost = apply_snapshot(rows, cols, best, as_of)
    write_snapshot_atomic(CSV_PATH, cols, rows)

    have = [r for r in rows if r[COL] != "NA"]
    print(f"\nyoutuber.csv: {COL} 充足 {len(best)}/{people}人 "
          f"({len(have)}/{len(rows)}行)", flush=True)
    print(f"{COL} の上書き結果: 値が変わった {len(updated)}人 / "
          f"新たに入った {len(filled)}人 / 取れなくなった {len(lost)}人",
          flush=True)
    print(f"{AS_OF_COL}: {as_of} (UTC、登録者数ありの行)", flush=True)
    top = sorted(best.items(), key=lambda kv: -kv[1])[:10]
    name = {r["id"]: r["original"] for r in rows}
    print("登録者数 上位10人:", flush=True)
    for pid, n in top:
        print(f"  {n:>12,}  {name[pid]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
