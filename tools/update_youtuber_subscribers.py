#!/usr/bin/env python3
"""youtuber.csv の channel と subscribers を YouTube API で更新する。

出典: WikidataのYouTubeチャンネルID(P2397、CC0)と YouTube Data API v3 の
channels.list(part=snippet,statistics)。Wikidataの登録者数(P3744)は記録時点が項目ごとに
バラバラ(2019〜2026年が混在)で横比較できないため使わない(詳細は ADR 00030)。

- 対象は wikidata 列にQIDが入っている人。QIDが無い行は NA
- 1人が複数チャンネルを持つ場合は**その人のチャンネル群で最大の登録者数**を採り、
  subscribers と channel(snippet.title)を必ず同じチャンネルIDから取る
- 登録者数を非公開にしているチャンネル(hiddenSubscriberCount)は候補から除く。
  1本も取れなければ NA
- **subscribers と subscribers_as_of は毎回全行を上書きする**。channel は空欄/NAの
  人だけ補完し、既存値は上書きしない。既存値と現在のsnippet.titleが異なる場合は
  監査レポートへ出す。この3列以外の列・行順・idは一切変更しない
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
SOURCE_PATH = ROOT / "tools" / "youtuber_channel_sources.jsonl"
REPORT_PATH = ROOT / "tools" / "youtuber_channel_candidates.jsonl"
COL = "subscribers"
AS_OF_COL = "subscribers_as_of"
CHANNEL_COL = "channel"
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


def apply_snapshot(rows: list, cols: list, best: dict, as_of: str,
                   preserve: set = None) -> tuple:
    """同一スナップショットの登録者数・取得日を全行へ反映する。

    返り値は (新たに値が入った人, 値が変わった人, 取れなくなった人)。
    subscribersがNAの行では取得日も必ずNAにする。channelには触れない。
    """
    for col in (COL, AS_OF_COL):
        if col not in cols:
            cols.append(col)

    preserve = preserve or set()
    filled, updated, lost = set(), set(), set()
    for row in rows:
        if row["id"] in preserve:
            continue
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


def _clean_channel_title(title: str) -> str:
    """CSVの素朴なsplit利用者を壊さない形に公式タイトルを整える。"""
    return re.sub(r"[\s　]+", " ",
                  (title or "").replace(",", " ").replace('"', "")).strip()


def apply_channel_backfill(rows: list, selected: dict) -> set:
    """channel が空/NAの人物だけ、選定IDの snippet.title で補完する。"""
    filled = set()
    for row in rows:
        pid = row["id"]
        choice = selected.get(pid)
        if choice and row.get("channel") in (None, "", "NA"):
            row["channel"] = choice["title"]
            filled.add(pid)
    return filled


def validate_snapshot_alignment(rows: list, selected: dict, preserve: set) -> None:
    """今回書き換えるchannel/subscribersが同じ選定IDの値か検証する。"""
    for row in rows:
        pid = row["id"]
        if pid in preserve or not row.get(COL, "").isdigit():
            continue
        choice = selected.get(pid)
        if not choice or row.get(CHANNEL_COL) != choice["title"] or \
                int(row[COL]) != choice["subscribers"]:
            raise SystemExit(
                f"error: person id {pid}: channel/subscribersが選定IDと不一致")


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


def write_jsonl_atomic(path: Path, records: list) -> None:
    """監査用JSONLをキー順固定・原子的に書く。"""
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                    dir=path.parent)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False,
                                        sort_keys=True) + "\n")
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def update_audit_files(rows: list, qid_of: dict, p2397: dict, selected: dict,
                       as_of: str) -> tuple:
    """採用根拠を台帳へ追記し、既存channelとの差異を候補レポートへ出す。"""
    person = {}
    for row in rows:
        person.setdefault(row["id"], row)

    existing = {}
    if SOURCE_PATH.exists():
        for line in SOURCE_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                existing[(record["person_id"], record["channel_id"])] = record
    matched = {pid for pid, choice in selected.items()
               if person[pid].get("channel") == choice["title"]
               and choice["channel_id"] in p2397.get(qid_of.get(pid, ""), [])}
    for pid in matched:
        choice = selected[pid]
        key = (pid, choice["channel_id"])
        if key in existing:
            continue
        record = {
            "channel_id": choice["channel_id"],
            "channel_title": choice["title"],
            "decision": "verified",
            "identity_basis": "wikidata_person_statement",
            "observed_on": as_of,
            "original": person[pid]["original"],
            "person_id": pid,
            "qid": qid_of[pid],
            "source_type": "wikidata_p2397",
            "source_url": f"https://www.wikidata.org/wiki/{qid_of[pid]}",
            "subscribers": choice["subscribers"],
        }
        existing[key] = record
    write_jsonl_atomic(SOURCE_PATH, sorted(
        existing.values(), key=lambda r: (int(r["person_id"]), r["channel_id"])))

    report = []
    resolved = {pid for pid, choice in selected.items()
                if person[pid].get("channel") == choice["title"]}
    if REPORT_PATH.exists():
        for line in REPORT_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                if record.get("source_type") != "wikidata_p2397" \
                        and record.get("person_id") not in resolved:
                    report.append(record)
    for pid, choice in selected.items():
        current = person[pid].get("channel")
        if current not in (None, "", "NA") \
                and current != choice["title"]:
            report.append({
                "candidate_channel_id": choice["channel_id"],
                "candidate_title": choice["title"],
                "decision": "deferred_existing_channel_preserved",
                "existing_channel": current,
                "original": person[pid]["original"],
                "person_id": pid,
                "qid": qid_of.get(pid, "NA"),
                "reason": "既存channelは自動上書きせず、名称差異を人手確認へ回す",
                "source_type": "wikidata_p2397",
                "source_url": f"https://www.wikidata.org/wiki/{qid_of.get(pid, 'NA')}",
            })
    for pid, current in ((pid, row.get("channel"))
                         for pid, row in person.items()):
        if current not in (None, "", "NA") and pid not in selected:
            report.append({
                "decision": "deferred_channel_unavailable",
                "existing_channel": current,
                "original": person[pid]["original"],
                "person_id": pid,
                "qid": qid_of.get(pid, "NA"),
                "reason": "YouTube Data APIで同じチャンネルのtitle/登録者数を確認できないため既存値を保持",
                "source_type": "youtube_data_api",
                "source_url": f"https://www.wikidata.org/wiki/{qid_of.get(pid, 'NA')}",
            })
    deduped = {}
    for record in report:
        key = (record["person_id"], record["decision"],
               record.get("candidate_channel_id", ""),
               record.get("evidence_url", ""))
        deduped[key] = record
    report = list(deduped.values())
    write_jsonl_atomic(REPORT_PATH, sorted(
        report, key=lambda r: (int(r["person_id"]),
                               r.get("candidate_channel_id",
                                     r.get("evidence_url", "")))))
    return len(existing), len({record["person_id"] for record in report})


def load_verified_channel_sources(qid_of: dict, name_of: dict) -> dict:
    """調査台帳でverifiedになった追加IDを人物IDごとに読む。"""
    out = {}
    if not SOURCE_PATH.exists():
        return out
    for lineno, line in enumerate(
            SOURCE_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("decision") != "verified":
            continue
        if record.get("source_type") == "wikidata_p2397":
            continue
        if record.get("source_type") not in {
                "jawiki_external_link", "wikidata_official_site",
                "wikidata_official_site_page", "wikidata_youtube_handle",
                "jawiki_infobox", "web_search_primary_link",
                "official_talent_profile"}:
            raise SystemExit(f"error: {SOURCE_PATH}:{lineno}: 不正なsource_type")
        channel_id = record.get("channel_id", "")
        qid = record.get("qid", "")
        qid_optional = record.get("source_type") in {
            "web_search_primary_link", "official_talent_profile"}
        if not CHANNEL_ID_RE.fullmatch(channel_id) or not (
                re.fullmatch(r"Q\d+", qid) or (qid_optional and qid == "NA")):
            raise SystemExit(f"error: {SOURCE_PATH}:{lineno}: 不正なQID/channel_id")
        person_id = record.get("person_id", "")
        if qid_of.get(person_id, "NA") != qid or \
                name_of.get(person_id) != record.get("original"):
            raise SystemExit(f"error: {SOURCE_PATH}:{lineno}: 人物/QID対応がCSVと不一致")
        if not record.get("source_url") or not record.get("evidence_url"):
            raise SystemExit(f"error: {SOURCE_PATH}:{lineno}: 出典URLが不足")
        if record.get("source_type") == "web_search_primary_link":
            if record.get("discovery_method") not in {
                    "gemini_chrome_google_search",
                    "codex_standard_web_search",
                    "gemini_and_codex_web_search"}:
                raise SystemExit(
                    f"error: {SOURCE_PATH}:{lineno}: Web検索の探索方法が不足")
            if record.get("identity_basis") not in {
                    "youtube_about_self_identification",
                    "jawiki_person_article_explicit_link",
                    "wikipedia_person_article_explicit_link",
                    "official_page_explicit_channel_link"}:
                raise SystemExit(
                    f"error: {SOURCE_PATH}:{lineno}: Web検索の本人対応根拠が不正")
            if not record.get("evidence_quote"):
                raise SystemExit(
                    f"error: {SOURCE_PATH}:{lineno}: Web検索の根拠要約が不足")
        out.setdefault(person_id, []).append(channel_id)
    return {person_id: sorted(set(ids)) for person_id, ids in out.items()}


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


def fetch_channels(channel_ids: list, key: str) -> tuple:
    """チャンネルID -> {subscribers, title}。非公開・削除済みは含まない。

    返り値は (登録者数の辞書, 非公開だったチャンネル数)。"""
    channels, hidden = {}, 0
    for i in range(0, len(channel_ids), YT_BATCH):
        batch = channel_ids[i:i + YT_BATCH]
        url = API + "?" + urllib.parse.urlencode(
            {"part": "snippet,statistics", "id": ",".join(batch), "key": key})
        data = _get(url, key)
        for item in data.get("items", []):
            st = item.get("statistics", {})
            if st.get("hiddenSubscriberCount"):
                hidden += 1
                continue
            try:
                title = _clean_channel_title(item["snippet"]["title"])
                if not title:
                    continue
                channels[item["id"]] = {
                    "channel_id": item["id"],
                    "subscribers": int(st["subscriberCount"]),
                    "title": title,
                }
            except (KeyError, TypeError, ValueError):
                continue
        # itemsに返らないID(削除・BANされたチャンネル)は静かにスキップする
        print(f"  登録者数取得 {min(i + YT_BATCH, len(channel_ids))}/"
              f"{len(channel_ids)}", flush=True)
    return channels, hidden


def select_channels(channel_ids_by_person: dict, channels: dict) -> dict:
    """人物ごとに最大登録者数の1本を、ID・人数・titleの組のまま選ぶ。"""
    selected = {}
    for pid, ids in channel_ids_by_person.items():
        choices = [channels[channel_id] for channel_id in ids
                   if channel_id in channels]
        if choices:
            # 同数ならID昇順。API応答順やWikidata順で結果を揺らさない。
            selected[pid] = sorted(
                choices, key=lambda c: (-c["subscribers"], c["channel_id"]))[0]
    return selected


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
    name_of = {}
    for r in rows:
        name_of[r["id"]] = r["original"]
        qid = (r.get("wikidata") or "").strip()
        if qid and qid not in ("NA",):
            qid_of[r["id"]] = qid
    people = len({r["id"] for r in rows})
    print(f"youtuber.csv: {len(rows)}行 / {people}人 "
          f"(QIDあり {len(qid_of)}人)", flush=True)

    qids = sorted(set(qid_of.values()))
    p2397 = fetch_channel_ids(qids)
    extra_chans = load_verified_channel_sources(qid_of, name_of)
    extra_id_pairs = {(pid, channel_id) for pid, channel_ids in extra_chans.items()
                      for channel_id in channel_ids}
    ids_by_person = {}
    for pid in name_of:
        ids_by_person[pid] = sorted(set(
            p2397.get(qid_of.get(pid, ""), []) + extra_chans.get(pid, [])))
    all_ids = sorted({c for v in ids_by_person.values() for c in v})
    channel_people = sum(bool(ids) for ids in ids_by_person.values())
    extra_people = len(extra_chans)
    print(f"採用済みチャンネルID: {len(all_ids)}本 / {channel_people}人 "
          f"(外部リンク/P856台帳 {extra_people}人)", flush=True)

    channels, hidden = fetch_channels(all_ids, key)
    print(f"登録者数と正式名が取れたチャンネル: {len(channels)}/{len(all_ids)}本"
          f"(非公開 {hidden}本、取得不能 "
          f"{len(all_ids) - len(channels) - hidden}本)", flush=True)

    selected = select_channels(ids_by_person, channels)
    best = {pid: choice["subscribers"] for pid, choice in selected.items()}
    if len(best) < MIN_PEOPLE:
        print(f"error: implausible subscribers count: {len(best)}人"
              f"(下限 {MIN_PEOPLE}人)。取得が壊れている可能性があるため"
              "書き込まずに中断します", file=sys.stderr)
        return 1

    # ここから書き込み(全取得が成功した後に、3列を1回の置換で反映)
    as_of = _utc_date()
    current_channel = {}
    for row in rows:
        current_channel.setdefault(row["id"], row.get(CHANNEL_COL, "NA"))
    deferred_existing = {
        pid for pid, title in current_channel.items()
        if title not in ("", "NA")
        and (pid not in selected or title != selected[pid]["title"])
    }
    filled, updated, lost = apply_snapshot(
        rows, cols, best, as_of, preserve=deferred_existing)
    channel_filled = apply_channel_backfill(rows, selected)
    validate_snapshot_alignment(rows, selected, deferred_existing)
    evidence_count, deferred_count = update_audit_files(
        rows, qid_of, p2397, selected, as_of)
    # 監査台帳の生成・検証まで成功してからCSVを原子的に置換する。
    write_snapshot_atomic(CSV_PATH, cols, rows)

    have = [r for r in rows if r[COL] != "NA"]
    name = {r["id"]: r["original"] for r in rows}
    print(f"\nyoutuber.csv: {COL} 充足 {len(best)}/{people}人 "
          f"({len(have)}/{len(rows)}行)", flush=True)
    print(f"{COL} の上書き結果: 値が変わった {len(updated)}人 / "
          f"新たに入った {len(filled)}人 / 取れなくなった {len(lost)}人",
          flush=True)
    print(f"{AS_OF_COL}: {as_of} (UTC、登録者数ありの行)", flush=True)
    print(f"channel の安全な空欄補完: {len(channel_filled)}人", flush=True)
    for pid in sorted(channel_filled, key=lambda value: name[value]):
        choice = selected[pid]
        source = ("公式外部リンク台帳"
                  if (pid, choice["channel_id"]) in extra_id_pairs
                  else "Wikidata P2397")
        print(f"  {name[pid]}: {choice['title']} "
              f"({source} {choice['channel_id']})", flush=True)
    print(f"採用根拠台帳: {evidence_count}件 / "
          f"監査レポートで保留: {deferred_count}人", flush=True)
    top = sorted(best.items(), key=lambda kv: -kv[1])[:10]
    print("登録者数 上位10人:", flush=True)
    for pid, n in top:
        print(f"  {n:>12,}  {name[pid]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
