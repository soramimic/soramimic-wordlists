#!/usr/bin/env python3
"""日本語Wikipediaの検証可能な特徴文で海の生き物の説明を改善する。

Wikidata QIDから日本語記事へ直接たどり、記事冒頭の版ID・採用元文・生成文を
``marine_life_description_sources.jsonl`` に固定する。名前検索は行わない。
本文に形態・生態・生息域などの有用な完結文がない行は既存の構造化Traitsへ
フォールバックし、分類文や学名だけでは説明を埋めない。

usage: python3 tools/enrich_marine_life_wikipedia_descriptions.py
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import update_marine_life as marine
from enrich_marine_life_descriptions import write_source

WD_API = "https://www.wikidata.org/w/api.php"
WP_API = "https://ja.wikipedia.org/w/api.php"
USER_AGENT = (
    "soramimic-wordlists-marine-wikipedia-description/1.0 "
    "(+https://github.com/soramimic/soramimic-wordlists)"
)
DEFAULT_CACHE = Path(__file__).with_name(".cache") / "marine_life_wikipedia"
FEATURE_TERMS = {
    "生息": 8, "分布": 7, "深海": 7, "沿岸": 5, "外洋": 5, "熱帯": 4,
    "温帯": 4, "サンゴ礁": 6, "体長": 6, "全長": 6, "発光": 8,
    "特徴": 6, "斑点": 5, "縞": 5, "触手": 5, "ひれ": 4, "鰭": 4,
    "甲羅": 5, "殻": 4, "毒": 6, "食べ": 7, "捕食": 7, "主食": 7,
    "群れ": 7, "回遊": 7, "繁殖": 6, "産卵": 6, "泳": 4, "潜": 4,
    "最大": 5, "唯一": 3, "大型": 3, "小型": 3,
}
GENERIC_TERMS = re.compile(
    r"(?:属する|分類される|一種である|1種である|構成する|学名|別名|ともよばれる)"
)
USEFUL_ASSERTION = re.compile(
    r"(?:生息(?:し|する)|分布(?:し|する)|発光|食べ|捕食|主食|群れを|回遊(?:し|する)|"
    r"繁殖|産卵|泳|潜|特徴|有毒|毒を|体長|全長|最大(?:で|体長|全長)|"
    r"斑点を|縞を|触手を|ひれを|鰭を|甲羅を|殻を)"
)
BAD_TERMS = re.compile(
    r"(?:曖昧さ回避|本項では|以下では|詳細は|参照|指定されている|市の魚|県の魚|和名|英名)"
)
CONTEXT_HEAD = re.compile(r"^(?:また|さらに|一方|なお|しかし|このため|そのため)[、 ]*")
PARENS = re.compile(r"（[^（）]*?[）)]|\([^()]*?[）)]")
DISAMBIG = re.compile(r"[（(][^）)]*[）)]$")
LATIN_BINOMIAL = re.compile(r"\b[A-Z][a-z]+\s+[a-z][a-z.-]+(?:\s+[a-z][a-z.-]+)?\b")
OTHER_KATAKANA_SUBJECT = re.compile(r"^[ァ-ヶー・]{2,}[ ]*(?:とは|は|が)[、 ]*")


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except Exception as exc:
            error = exc
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Wikipedia APIの取得に失敗しました: {url} ({error})")


def cached_json(path: Path, url: str, refresh: bool) -> dict:
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch_json(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    marine.write_atomic(
        path, json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    )
    return data


def fetch_sitelinks(rows: list[dict[str, str]], cache: Path, refresh: bool) -> dict[str, str]:
    qids = sorted({row["wikidata"] for row in rows if row["wikidata"]})
    result: dict[str, str] = {}
    for start in range(0, len(qids), 50):
        batch = qids[start:start + 50]
        key = f"{start:05d}-{batch[0]}-{batch[-1]}.json"
        url = WD_API + "?" + urllib.parse.urlencode({
            "action": "wbgetentities", "ids": "|".join(batch),
            "props": "sitelinks", "sitefilter": "jawiki", "format": "json",
        })
        data = cached_json(cache / "sitelinks" / key, url, refresh)
        for qid, entity in data.get("entities", {}).items():
            title = entity.get("sitelinks", {}).get("jawiki", {}).get("title")
            if title:
                result[qid] = title
    return result


def fetch_extract_batch(
    titles: list[str], cache: Path, refresh: bool
) -> dict[str, dict]:
    key = hashlib.sha1("\n".join(titles).encode()).hexdigest() + ".json"
    url = WP_API + "?" + urllib.parse.urlencode({
        "action": "query", "prop": "extracts|revisions", "exintro": 1,
        "explaintext": 1, "redirects": 1, "rvprop": "ids",
        "titles": "|".join(titles), "format": "json", "formatversion": 2,
    })
    data = cached_json(cache / "extracts" / key, url, refresh)
    redirects = {item["from"]: item["to"] for item in data.get("query", {}).get("redirects", [])}
    pages = {page.get("title", ""): page for page in data.get("query", {}).get("pages", [])}
    result = {}
    for requested in titles:
        resolved = redirects.get(requested, requested)
        page = pages.get(resolved, {})
        revisions = page.get("revisions") or []
        if page.get("extract") and revisions:
            result[requested] = {
                "title": resolved,
                "extract": page["extract"],
                "revision_id": int(revisions[0]["revid"]),
            }
    return result


def fetch_extracts(
    titles: list[str], cache: Path, refresh: bool, workers: int
) -> dict[str, dict]:
    batches = [titles[start:start + 20] for start in range(0, len(titles), 20)]
    result: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch_extract_batch, batch, cache, refresh) for batch in batches]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            result.update(future.result())
            if index % 10 == 0 or index == len(futures):
                print(f"Wikipedia冒頭: {index}/{len(futures)} batches")
    return result


def normalize_sentence(sentence: str) -> str:
    value = PARENS.sub("", sentence)
    value = LATIN_BINOMIAL.sub("", value)
    value = re.sub(r"\[[0-9]+\]", "", value)
    value = re.sub(r"[\s　]+", " ", value).strip(" 、")
    value = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", value)
    value = value.replace(",", "、").replace('"', "")
    return value + ("" if value.endswith("。") else "。") if value else ""


def normalized_title(value: str) -> str:
    """曖昧さ回避の括弧と表記用中黒だけを除いて記事名を比較する。"""
    return DISAMBIG.sub("", value).replace("・", "").replace(" ", "")


def title_matches_name(name: str, title: str) -> bool:
    """同じQIDでも別和名の記事を流用せず、表示名と記事名の一致を要求する。"""
    return normalized_title(name) == normalized_title(title)


def strip_subject(sentence: str, name: str, title: str) -> str:
    value = CONTEXT_HEAD.sub("", sentence)
    subjects = {
        name, DISAMBIG.sub("", title), name.replace("・", ""), "本種", "この種",
    }
    for subject in sorted(subjects, key=len, reverse=True):
        if not subject:
            continue
        match = re.match(
            rf"^{re.escape(subject)}[ ]*(?:と呼ばれる[^はが、。]{{0,30}})?(?:とは|は|が)[、 ]*",
            value,
        )
        if match and len(value[match.end():].strip("。 ")) >= 6:
            value = value[match.end():]
            break
    return value.lstrip("、 ")


def compact_sentence(sentence: str) -> str:
    if len(sentence) <= 90:
        return sentence
    core = sentence.removesuffix("。")
    endings = (
        "生息する", "分布する", "食べる", "捕食する", "形成する", "備える",
        "持つ", "特徴である", "知られる", "回遊する", "産卵する",
    )
    for ending in endings:
        match = re.search(rf"^(.{{12,84}}?{ending})[、。]", core + "。")
        if match:
            return match.group(1) + "。"
    return ""


def candidate_score(sentence: str, index: int) -> int:
    if not USEFUL_ASSERTION.search(sentence):
        return -100
    score = sum(weight * sentence.count(term) for term, weight in FEATURE_TERMS.items())
    if BAD_TERMS.search(sentence):
        score -= 20
    if GENERIC_TERMS.search(sentence):
        score -= 4
    if index == 0:
        score += 1
    if len(sentence) > 90:
        score -= 3
    return score


def select_description(extract: str, name: str, title: str) -> tuple[str, str] | None:
    if not title_matches_name(name, title):
        return None
    raw_sentences = [part.strip() + "。" for part in extract.split("。") if part.strip()]
    ranked = []
    for index, raw in enumerate(raw_sentences[:12]):
        normalized = normalize_sentence(raw)
        styled = compact_sentence(strip_subject(normalized, name, title))
        if not styled or not 8 <= len(styled) <= 90:
            continue
        if OTHER_KATAKANA_SUBJECT.match(styled):
            continue
        if normalized_title(styled).startswith(normalized_title(name)):
            continue
        score = candidate_score(styled, index)
        if score > 0:
            ranked.append((score, -index, -len(styled), normalized, styled))
    if not ranked:
        return None
    _score, _index, _length, source, description = max(ranked)
    return source, description


def load_evidence() -> tuple[list[dict], dict[str, dict]]:
    records = [
        json.loads(line)
        for line in marine.DESCRIPTION_SOURCES.read_text(encoding="utf-8").splitlines()
    ]
    return records, {record["name"]: record for record in records}


def write_evidence(records: list[dict]) -> None:
    lines = [json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in records]
    marine.write_atomic(marine.DESCRIPTION_SOURCES, "\n".join(lines).encode())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--fetched-at", default=date.today().isoformat())
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8:
        parser.error("--workers は1〜8で指定してください")
    try:
        date.fromisoformat(args.fetched_at)
    except ValueError:
        parser.error("--fetched-at はYYYY-MM-DDで指定してください")

    rows = marine.load_source()
    records, by_name = load_evidence()
    targets = [row for row in rows if row["name"] in by_name and row["wikidata"]]
    sitelinks = fetch_sitelinks(targets, args.cache, args.refresh)
    titles = sorted(set(sitelinks.values()))
    extracts = fetch_extracts(titles, args.cache, args.refresh, args.workers)

    applied = 0
    unavailable = 0
    for row in rows:
        record = by_name.get(row["name"])
        if record is None:
            continue
        record["wikidata"] = row["wikidata"]
        record.pop("wikipedia", None)
        title = sitelinks.get(row["wikidata"])
        page = extracts.get(title or "")
        selected = select_description(page["extract"], row["name"], page["title"]) if page else None
        if selected:
            source_sentence, description = selected
            record["wikipedia"] = {
                "language": "ja", "wikidata": row["wikidata"], "title": page["title"],
                "page_url": "https://ja.wikipedia.org/wiki/" + urllib.parse.quote(page["title"].replace(" ", "_")),
                "revision_id": page["revision_id"], "fetched_at": args.fetched_at,
                "source_sentence": source_sentence, "description": description,
                "license": "CC BY-SA 4.0",
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                "modified": source_sentence != description,
            }
            applied += 1
        else:
            unavailable += 1
        row["description"] = marine.description_from_evidence(row, record)

    write_evidence(records)
    write_source(rows)
    marine.validate_description_sources(rows)
    marine.write_atomic(marine.OUTPUT, marine.generate(rows))
    print(
        f"Wikipedia特徴文を適用: {applied}件; 日本語記事なしまたは有用文なし: "
        f"{unavailable}件"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
