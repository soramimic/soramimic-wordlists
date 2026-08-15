#!/usr/bin/env python3
"""channel欠損者の公式YouTube URLを、人物に直結する出典だけから収集する。

自動採用する根拠は次に限定する。

- 本人のWikidata項目の公式サイト(P856)が直接指すYouTubeチャンネルURL
- 本人QIDのYouTube handle(P11245)
- 本人の非リダイレクトja.wikipedia記事の先頭YouTube infobox
- 同記事の「外部リンク」節で公式または本人名が明記されたチャンネルURL

YouTubeの名前検索は行わない。動画/再生リスト、/c/カスタムURL、明示性のない
外部リンク、解決不能なhandle、P856公式サイト本文は候補レポートへ出すだけで
CSVへは反映しない。公式サイト本文は一般Web検索で人手確認して台帳へ追加する。
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
THIRD_PARTY_OPERATOR_RE = re.compile(
    r"(?:弟|兄|姉|妹|家族|遺族|スタッフ|事務所).{0,12}(?:運営|管理)")
CHANNEL_TABS = {"about", "community", "featured", "live", "playlists",
                "shorts", "streams", "videos"}
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
    suffix_is_safe = len(parts) <= 2 or all(
        part.casefold() in CHANNEL_TABS for part in parts[2:])
    if len(parts) >= 2 and suffix_is_safe and parts[0] == "channel" \
            and updater.CHANNEL_ID_RE.fullmatch(parts[1]):
        return "id", parts[1]
    if len(parts) >= 2 and suffix_is_safe and parts[0] == "channel" \
            and parts[1].startswith("@") and len(parts[1]) > 1:
        return "forHandle", parts[1]
    if parts and (len(parts) == 1 or all(
            part.casefold() in CHANNEL_TABS for part in parts[1:])) \
            and parts[0].startswith("@") and len(parts[0]) > 1:
        return "forHandle", parts[0]
    if len(parts) >= 2 and suffix_is_safe and parts[0] == "user" and parts[1]:
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


def fetch_youtube_handles(qids: list) -> dict:
    """本人QIDのYouTube handle(P11245)だけを取得する。"""
    out = {}
    for start in range(0, len(qids), updater.QID_BATCH):
        batch = qids[start:start + updater.QID_BATCH]
        values = " ".join(f"wd:{qid}" for qid in batch)
        query = f"""
SELECT ?p ?handle WHERE {{
  VALUES ?p {{ {values} }}
  ?p p:P11245 ?statement . ?statement ps:P11245 ?handle .
  FILTER NOT EXISTS {{ ?statement wikibase:rank wikibase:DeprecatedRank }}
}}"""
        for binding in sparql(query)["results"]["bindings"]:
            qid = binding["p"]["value"].rsplit("/", 1)[1]
            handle = urllib.parse.unquote(binding["handle"]["value"].strip())
            if handle:
                if not handle.startswith("@"):
                    handle = "@" + handle
                out.setdefault(qid, []).append(handle)
    return {qid: sorted(set(handles)) for qid, handles in out.items()}


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
        return title, "", False
    content = page.get("revisions", [{}])[0].get("slots", {}).get(
        "main", {}).get("content", "")
    return (page.get("title", title), content,
            bool(data.get("query", {}).get("redirects")))


def _first_template(text: str, name: str) -> str:
    """先頭部にある指定infoboxテンプレートを波括弧の対応込みで返す。"""
    lead = text.split("\n==", 1)[0]
    match = re.search(r"\{\{\s*" + re.escape(name), lead, re.I)
    if not match:
        return ""
    depth = 0
    index = match.start()
    while index < len(lead) - 1:
        pair = lead[index:index + 2]
        if pair == "{{":
            depth += 1
            index += 2
            continue
        if pair == "}}":
            depth -= 1
            index += 2
            if depth == 0:
                return lead[match.start():index]
            continue
        index += 1
    return ""


def infobox_links(text: str) -> list:
    """本人記事先頭のYouTube infoboxフィールドだけをlocator化する。"""
    clean = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    box = (_first_template(clean, "Infobox YouTube personality")
           or _first_template(clean, "Infobox YouTuber"))
    if not box:
        return []
    locators = []
    field_re = re.compile(
        r"(?im)^\|\s*(channel(?:_url|_direct_url|_name)?\d*|channels|website)"
        r"\s*=\s*(.*?)(?=^\|\s*[\w_]+\s*=|\Z)", re.S)
    for match in field_re.finditer(box):
        field = match.group(1).casefold()
        value = match.group(2)
        urls = URL_RE.findall(value)
        for channel_id in CHANNEL_ID_IN_TEXT_RE.findall(value):
            urls.append(f"https://www.youtube.com/channel/{channel_id}")
        for url in sorted(set(urls)):
            locator = youtube_locator(url)
            if locator:
                locators.append({"evidence_url": url, "youtube_locator": locator})
        if field.startswith("channel_name") and not urls:
            username = re.sub(r"[\s{}\[\]|].*", "", value.strip())
            if username:
                locators.append({
                    "evidence_url": f"https://www.youtube.com/user/{username}",
                    "youtube_locator": ("forUsername", username),
                })
    deduped = {}
    for item in locators:
        deduped[item["youtube_locator"]] = item
    return list(deduped.values())


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
            if THIRD_PARTY_OPERATOR_RE.search(line):
                item["reason"] = "本人以外による運営・管理が明記されている"
                ambiguous.append(item)
            elif explicit and locator:
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


def merge_source_records(old_sources: list, verified: list, target_ids: set,
                         fetch_failed: set) -> list:
    """成功した再監査だけを置換し、一時取得失敗時は旧証跡を保持する。"""
    retained = [record for record in old_sources
                if record.get("source_type") in {
                    "wikidata_p2397", "wikidata_official_site_page"}
                or record.get("person_id") not in target_ids
                or record.get("person_id") in fetch_failed]
    source_map = {(record["person_id"], record["channel_id"]): record
                  for record in retained}
    for record in verified:
        source_map[(record["person_id"], record["channel_id"])] = record
    return list(source_map.values())


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
    youtube_handles = fetch_youtube_handles(sorted(
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
        for handle in youtube_handles.get(qid, []):
            candidates.append({
                "evidence_url": f"https://www.youtube.com/{handle}",
                "identity_basis": "wikidata_person_youtube_handle_statement",
                "source_type": "wikidata_youtube_handle",
                "source_url": f"https://www.wikidata.org/wiki/{qid}",
                "youtube_locator": ("forHandle", handle),
            })
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
                continue
            if "youtube" in url.casefold():
                deferred.append({
                    "decision": "deferred_unsupported_url",
                    "evidence_url": url, "original": row["original"],
                    "person_id": pid, "qid": qid,
                    "reason": "P856だがcanonical channel IDへ安全に解決できないURL形式",
                    "source_type": "wikidata_official_site",
                    "source_url": f"https://www.wikidata.org/wiki/{qid}",
                })
                continue
            deferred.append({
                "decision": "deferred_official_site_manual_review",
                "original": row["original"], "person_id": pid, "qid": qid,
                "reason": "P856公式サイト本文はSSRF回避のため自動取得せずWeb検索で人手確認する",
                "source_type": "wikidata_official_site_page",
                "source_url": url,
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
                article_title, wikitext, redirected = fetch_wikitext(article_title)
            else:
                wikitext = ""
                redirected = False
            if redirected:
                deferred.append({
                    "decision": "deferred_jawiki_redirect",
                    "original": row["original"], "person_id": pid, "qid": qid,
                    "reason": "本人QIDのjawiki sitelinkが別記事へリダイレクトされるため自動採用しない",
                    "source_type": "jawiki_external_link",
                    "source_url": article_url,
                })
                wiki_ok, wiki_ambiguous = [], []
            else:
                wiki_ok, wiki_ambiguous = wikipedia_links(article_title, wikitext)
                for item in infobox_links(wikitext):
                    wiki_ok.append({
                        **item,
                        "identity_basis": "person_article_youtube_infobox",
                        "locator": "本人QIDに直結するjawiki記事先頭のYouTube infobox",
                        "source_type": "jawiki_infobox",
                    })
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
                **item,
                "identity_basis": item.get(
                    "identity_basis", "person_article_explicit_official_link"),
                "source_type": item.get(
                    "source_type", "jawiki_external_link"),
                "source_url": article_url,
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

    merged_sources = merge_source_records(
        _load_jsonl(updater.SOURCE_PATH), verified, set(targets), fetch_failed)
    updater.write_jsonl_atomic(updater.SOURCE_PATH, sorted(
        merged_sources, key=lambda record:
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
