#!/usr/bin/env python3
"""channel欠損者の公式YouTube URLを、人物に直結する出典だけから収集する。

自動採用する根拠は次の2種類に限定する。

- 本人のWikidata項目の公式サイト(P856)が直接指すYouTubeチャンネルURL
- 本人のja.wikipedia記事の「外部リンク」節で、公式または本人名が明記された
  YouTubeチャンネルURL

YouTubeの名前検索は行わない。動画/再生リスト、/c/カスタムURL、明示性のない
外部リンク、解決不能なhandleは候補レポートへ出すだけでCSVへは反映しない。
採用IDは tools/youtuber_channel_sources.jsonl に根拠付きで保存し、
update_youtuber_subscribers.py が同じIDから subscribers と snippet.title を取得する。
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_youtuber_subscribers as updater  # noqa: E402
from wpnames import UA, sparql  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "youtuber.csv"
WIKI_API = "https://ja.wikipedia.org/w/api.php"
YOUTUBE_HOST_RE = re.compile(r"(?:www\.|m\.)?youtube\.com$", re.I)
URL_RE = re.compile(r"https?://[^\s\]\[|{}<>]+", re.I)
CHANNEL_ID_IN_TEXT_RE = re.compile(
    r"(?<![0-9A-Za-z_-])UC[0-9A-Za-z_-]{22}(?![0-9A-Za-z_-])")
OFFICIAL_RE = re.compile(r"公式|official|本人", re.I)
EXTERNAL_SECTION_RE = re.compile(
    r"(?ms)^==\s*外部リンク\s*==\s*(.*?)(?=^==[^=]|\Z)")


def _request_json(url: str) -> dict:
    """Wikimediaのmaxlag/429を尊重して再試行する。URL本文はログに出さない。"""
    for attempt in range(5):
        try:
            request = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as ex:
            if ex.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise
            retry_after = ex.headers.get("Retry-After", "")
            try:
                delay = min(30, max(1, int(retry_after)))
            except ValueError:
                delay = min(30, 2 ** attempt)
        except (TimeoutError, urllib.error.URLError):
            if attempt == 4:
                raise
            delay = min(30, 2 ** attempt)
        time.sleep(delay)
    raise RuntimeError("unreachable")


def youtube_locator(url: str):
    """チャンネルURLを (APIパラメータ, 値) にする。動画等はNone。"""
    try:
        parsed = urllib.parse.urlsplit(url.rstrip(".,、。）)"))
    except ValueError:
        return None
    if not YOUTUBE_HOST_RE.fullmatch((parsed.hostname or "").lower()):
        return None
    parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) == 2 and parts[0] == "channel" \
            and updater.CHANNEL_ID_RE.fullmatch(parts[1]):
        return "id", parts[1]
    if len(parts) == 1 and parts[0].startswith("@") and len(parts[0]) > 1:
        return "forHandle", parts[0]
    if len(parts) == 2 and parts[0] == "user" and parts[1]:
        return "forUsername", parts[1]
    return None


def resolve_locator(locator, key: str):
    """URL由来のID/handle/usernameをcanonical UC IDへ解決する。検索はしない。"""
    parameter, value = locator
    if parameter == "id":
        return value
    url = updater.API + "?" + urllib.parse.urlencode(
        {"part": "id", parameter: value, "key": key})
    data = updater._get(url, key)
    items = data.get("items", [])
    if len(items) != 1:
        return None
    channel_id = items[0].get("id", "")
    return channel_id if updater.CHANNEL_ID_RE.fullmatch(channel_id) else None


def fetch_official_sites(qids: list) -> dict:
    """本人QIDのP856だけを取得する。"""
    out = {}
    for start in range(0, len(qids), updater.QID_BATCH):
        batch = qids[start:start + updater.QID_BATCH]
        values = " ".join(f"wd:{qid}" for qid in batch)
        query = f"""
SELECT ?p ?url WHERE {{
  VALUES ?p {{ {values} }}
  ?p p:P856 ?statement . ?statement ps:P856 ?url .
  FILTER NOT EXISTS {{ ?statement wikibase:rank wikibase:DeprecatedRank }}
}}"""
        for binding in sparql(query)["results"]["bindings"]:
            qid = binding["p"]["value"].rsplit("/", 1)[1]
            out.setdefault(qid, []).append(binding["url"]["value"])
    return out


def fetch_jawiki_sitelinks(qids: list) -> dict:
    """QIDに直結するja.wikipedia記事名とURLを取得する。名前検索はしない。"""
    out = {}
    for start in range(0, len(qids), updater.QID_BATCH):
        batch = qids[start:start + updater.QID_BATCH]
        values = " ".join(f"wd:{qid}" for qid in batch)
        query = f"""
SELECT ?p ?article ?title WHERE {{
  VALUES ?p {{ {values} }}
  ?article schema:about ?p ;
           schema:isPartOf <https://ja.wikipedia.org/> ;
           schema:name ?title .
}}"""
        for binding in sparql(query)["results"]["bindings"]:
            qid = binding["p"]["value"].rsplit("/", 1)[1]
            out[qid] = {
                "title": binding["title"]["value"],
                "url": binding["article"]["value"],
            }
    return out


def fetch_wikitext(title: str) -> tuple:
    params = {
        "action": "query", "format": "json", "formatversion": 2,
        "prop": "revisions", "rvprop": "content", "rvslots": "main",
        "redirects": 1, "titles": title, "maxlag": 5,
    }
    data = _request_json(WIKI_API + "?" + urllib.parse.urlencode(params))
    page = data.get("query", {}).get("pages", [{}])[0]
    if page.get("missing"):
        return title, ""
    content = page.get("revisions", [{}])[0].get("slots", {}).get(
        "main", {}).get("content", "")
    return page.get("title", title), content


def wikipedia_links(title: str, text: str) -> tuple:
    """外部リンク節から (明示的, 曖昧) のURLとlocatorを返す。"""
    match = EXTERNAL_SECTION_RE.search(text)
    if not match:
        return [], []
    verified, ambiguous = [], []
    compact_title = re.sub(r"[\s　]", "", title).casefold()
    for line in match.group(1).splitlines():
        if "youtube" not in line.casefold():
            continue
        urls = URL_RE.findall(line)
        # {{YouTube|...UC...}} のようなテンプレートもURLへ正規化する。
        for channel_id in CHANNEL_ID_IN_TEXT_RE.findall(line):
            urls.append(f"https://www.youtube.com/channel/{channel_id}")
        for url in sorted(set(urls)):
            locator = youtube_locator(url)
            # 公式表記を同じ行の別リンクから借りない。角括弧リンクなら当該URLの
            # ラベルだけ、YouTubeテンプレートならそのテンプレート行を判定する。
            position = line.find(url)
            context = line[position + len(url):] if position >= 0 else line
            if "]" in context:
                context = context.split("]", 1)[0]
            compact_context = re.sub(r"[\s　]", "", context).casefold()
            explicit = bool(OFFICIAL_RE.search(context)) or \
                compact_title in compact_context
            item = {"evidence_url": url, "locator": line.strip()[:500]}
            if explicit and locator:
                item["youtube_locator"] = locator
                verified.append(item)
            else:
                item["reason"] = (
                    "人物との公式な対応が明記されていない"
                    if locator else "canonical channel IDへ安全に解決できないURL形式")
                ambiguous.append(item)
    return verified, ambiguous


def _load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--person-id", action="append", default=[],
        help="欠損状態にかかわらず指定person idだけを再監査する(複数指定可)")
    args = parser.parse_args(argv)
    key = updater._load_key()
    if not key:
        print("スキップ(YouTube APIキーが無い): URLからIDを安全に解決できません")
        return 0

    with CSV_PATH.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    people = {}
    for row in rows:
        people.setdefault(row["id"], row)
    requested = set(args.person_id)
    missing = {pid: row for pid, row in people.items()
               if (not requested or pid in requested)
               and (requested or row.get("channel") in (None, "", "NA"))
               and re.fullmatch(r"Q\d+", row.get("wikidata", ""))}
    absent = sorted(requested - set(missing))
    if absent:
        raise SystemExit(f"error: 不明またはQIDなしのperson id: {', '.join(absent)}")
    qids = sorted({row["wikidata"] for row in missing.values()})
    p2397 = updater.fetch_channel_ids(qids)
    targets = ({pid: row for pid, row in missing.items()}
               if requested else
               {pid: row for pid, row in missing.items()
                if row["wikidata"] not in p2397})
    print(f"channel欠損 {len(missing)}人 / P2397なし調査対象 {len(targets)}人")

    official_sites = fetch_official_sites(sorted(
        {row["wikidata"] for row in targets.values()}))
    jawiki = fetch_jawiki_sitelinks(sorted(
        {row["wikidata"] for row in targets.values()}))
    accepted = []
    deferred = []
    fetch_failed = set()
    for index, (pid, row) in enumerate(sorted(
            targets.items(), key=lambda item: item[1]["original"]), 1):
        qid = row["wikidata"]
        candidates = []
        for url in official_sites.get(qid, []):
            locator = youtube_locator(url)
            if locator:
                candidates.append({
                    "evidence_url": url,
                    "identity_basis": "wikidata_official_website_statement",
                    "source_type": "wikidata_official_site",
                    "source_url": f"https://www.wikidata.org/wiki/{qid}",
                    "youtube_locator": locator,
                })
            elif "youtube" in url.casefold():
                deferred.append({
                    "decision": "deferred_unsupported_url",
                    "evidence_url": url, "original": row["original"],
                    "person_id": pid, "qid": qid,
                    "reason": "P856だがcanonical channel IDへ安全に解決できないURL形式",
                    "source_type": "wikidata_official_site",
                    "source_url": f"https://www.wikidata.org/wiki/{qid}",
                })
        sitelink = jawiki.get(qid)
        if not sitelink:
            deferred.append({
                "decision": "deferred_no_jawiki_sitelink",
                "original": row["original"], "person_id": pid, "qid": qid,
                "reason": "本人QIDにja.wikipedia sitelinkがない",
                "source_type": "jawiki_external_link",
                "source_url": f"https://www.wikidata.org/wiki/{qid}",
            })
            wiki_ok, wiki_ambiguous = [], []
            article_title = row["original"]
            article_url = f"https://www.wikidata.org/wiki/{qid}"
        else:
            article_title = sitelink["title"]
            article_url = sitelink["url"]
        try:
            if sitelink:
                article_title, wikitext = fetch_wikitext(article_title)
            else:
                wikitext = ""
            wiki_ok, wiki_ambiguous = wikipedia_links(article_title, wikitext)
        except Exception as ex:
            fetch_failed.add(pid)
            deferred.append({
                "decision": "deferred_fetch_error", "original": row["original"],
                "person_id": pid, "qid": qid,
                "reason": f"ja.wikipedia取得失敗: {type(ex).__name__}",
                "source_type": "jawiki_external_link",
                "source_url": article_url,
            })
            wiki_ok, wiki_ambiguous = [], []
            article_title = row["original"]
        if sitelink and article_title != sitelink["title"]:
            article_url = "https://ja.wikipedia.org/wiki/" + urllib.parse.quote(
                article_title.replace(" ", "_"))
        for item in wiki_ok:
            candidates.append({
                **item, "identity_basis": "person_article_explicit_official_link",
                "source_type": "jawiki_external_link", "source_url": article_url,
            })
        for item in wiki_ambiguous:
            deferred.append({
                **item, "decision": "deferred_ambiguous", "original": row["original"],
                "person_id": pid, "qid": qid,
                "source_type": "jawiki_external_link", "source_url": article_url,
            })

        seen_ids = set()
        for candidate in candidates:
            channel_id = resolve_locator(candidate.pop("youtube_locator"), key)
            if not channel_id:
                deferred.append({
                    **candidate, "decision": "deferred_unresolved",
                    "original": row["original"], "person_id": pid, "qid": qid,
                    "reason": "公式URLのhandle/usernameをcanonical IDへ解決できない",
                })
                continue
            if channel_id in seen_ids:
                continue
            seen_ids.add(channel_id)
            accepted.append({
                **candidate, "channel_id": channel_id, "decision": "verified",
                "original": row["original"], "person_id": pid, "qid": qid,
            })
        if index % 25 == 0:
            print(f"  外部リンク調査 {index}/{len(targets)}", flush=True)

    # 削除/BAN済みIDは採用しない。snippet.titleも台帳に残す。
    metadata, _ = updater.fetch_channels(
        sorted({record["channel_id"] for record in accepted}), key)
    verified = []
    for record in accepted:
        channel = metadata.get(record["channel_id"])
        if not channel:
            deferred.append({
                **record, "decision": "deferred_youtube_unavailable",
                "reason": "YouTube Data APIでチャンネルを確認できない",
            })
            continue
        verified.append({
            **record, "channel_title": channel["title"],
            "observed_on": updater._utc_date(),
            "subscribers": channel["subscribers"],
        })

    old_sources = _load_jsonl(updater.SOURCE_PATH)
    source_map = {(record["person_id"], record["channel_id"]): record
                  for record in old_sources}
    for record in verified:
        source_map[(record["person_id"], record["channel_id"])] = record
    updater.write_jsonl_atomic(updater.SOURCE_PATH, sorted(
        source_map.values(), key=lambda record:
        (int(record["person_id"]), record["channel_id"])))

    # P2397名称差異はsubscribers updaterが再生成するので、それ以外だけ置換する。
    old_report = [record for record in _load_jsonl(updater.REPORT_PATH)
                  if record.get("source_type") == "wikidata_p2397"
                  or record.get("person_id") in fetch_failed
                  or (requested and record.get("person_id") not in targets)]
    updater.write_jsonl_atomic(updater.REPORT_PATH, sorted(
        old_report + deferred, key=lambda record:
        (int(record["person_id"]), record.get("evidence_url", ""))))
    by_source = {}
    for record in verified:
        by_source[record["source_type"]] = by_source.get(record["source_type"], 0) + 1
    print(f"安全に採用: {len({r['person_id'] for r in verified})}人 "
          f"({by_source}) / 曖昧・取得不能で保留: "
          f"{len({r['person_id'] for r in deferred})}人")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
