#!/usr/bin/env python3
"""にじさんじ公式タレント一覧から現所属ライバーを youtuber.csv に補完する。

Wikidata/日本語Wikipediaを基準にする update_youtuber.py だけでは、個別記事の
ないライバーを収録できない。この補完は公式タレント一覧を名簿の一次ソースとし、
「にじさんじ」「NIJISANJI EN」の掲載者を追加する。VirtuaRealは別ブランドかつ
YouTubeを主活動先としないため対象外。

公式プロフィールにある読み、デビュー日、YouTubeチャンネル、プロフィール色を
使う。立ち絵そのものは再配布せず、色は自作の象徴カードにだけ反映する。

usage: python3 tools/update_nijisanji.py
"""

import csv
import html
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import HIRA2KATA, UA, write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "youtuber.csv"
COLORS_PATH = ROOT / "tools" / "youtuber_colors.json"
CHANNEL_SOURCES_PATH = ROOT / "tools" / "youtuber_channel_sources.jsonl"
LIST_URL = "https://www.nijisanji.jp/talents"
PROFILE_URL = "https://www.nijisanji.jp/talents/l/{slug}"
AFFILIATIONS = {"にじさんじ", "NIJISANJI EN"}
COUNT_GUARD = (180, 220)
CHANNEL_ID_RE = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.S)


def clean(value: str) -> str:
    """素朴なCSV利用者を壊すカンマ・引用符・改行を除く。"""
    return re.sub(r"[\s　]+", " ",
                  (value or "").replace(",", " ").replace('"', "")).strip()


def norm_name(value: str) -> str:
    return clean(value).replace(" ", "")


def next_data(page: str) -> dict:
    match = NEXT_DATA_RE.search(page)
    if not match:
        raise ValueError("__NEXT_DATA__ が見つからない")
    return json.loads(html.unescape(match.group(1)))


def parse_roster(page: str) -> list[dict]:
    payload = next_data(page)
    livers = payload["props"]["pageProps"]["allLivers"]
    selected = []
    for liver in livers:
        affiliation = set(liver.get("profile", {}).get("affiliation") or [])
        if not affiliation & AFFILIATIONS:
            continue
        selected.append({
            "name": norm_name(liver.get("name", "")),
            "slug": liver.get("slug", ""),
            "affiliation": sorted(affiliation & AFFILIATIONS)[0],
        })
    if not COUNT_GUARD[0] <= len(selected) <= COUNT_GUARD[1]:
        raise ValueError(f"公式名簿の対象人数が想定外: {len(selected)}")
    if any(not item["name"] or not item["slug"] for item in selected):
        raise ValueError("公式名簿に名前またはslugの欠損がある")
    if len({item["name"] for item in selected}) != len(selected):
        raise ValueError("公式名簿に重複した名前がある")
    return selected


def parse_detail(page: str, expected: dict) -> dict:
    payload = next_data(page)
    liver = payload["props"]["pageProps"]["liverDetail"]
    name = norm_name(liver.get("name", ""))
    if name != expected["name"] or liver.get("slug") != expected["slug"]:
        raise ValueError(f"プロフィール対応不一致: {expected['name']} / {name}")
    affiliations = set(liver.get("profile", {}).get("affiliation") or [])
    if expected["affiliation"] not in affiliations:
        raise ValueError(f"所属不一致: {name}")
    ruby = norm_name(liver.get("ruby", "")).translate(HIRA2KATA)
    if not ruby or re.search(r"[A-Za-z]", ruby):
        raise ValueError(f"読みが不正: {name}: {ruby}")
    channel_id = liver.get("channelId") or ""
    if not CHANNEL_ID_RE.fullmatch(channel_id):
        raise ValueError(f"YouTubeチャンネルIDが不正: {name}: {channel_id}")
    debut = (liver.get("profile", {}).get("debutAt") or "")[:4]
    if not re.fullmatch(r"20\d{2}", debut):
        raise ValueError(f"デビュー年が不正: {name}: {debut}")
    color = (liver.get("profile", {}).get("color") or "").lower()
    if not HEX_RE.fullmatch(color):
        raise ValueError(f"プロフィール色が不正: {name}: {color}")
    return {
        **expected,
        "ruby": ruby,
        "debut_year": debut,
        "channel_id": channel_id,
        "channel": clean(liver.get("channelName", "")),
        "color": color,
        "profile_url": PROFILE_URL.format(slug=expected["slug"]),
    }


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def fetch_details(roster: list[dict]) -> list[dict]:
    details = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {pool.submit(fetch, PROFILE_URL.format(slug=item["slug"])): item
                for item in roster}
        for future in as_completed(jobs):
            item = jobs[future]
            details[item["name"]] = parse_detail(future.result(), item)
    return [details[item["name"]] for item in roster]


def apply_roster(rows: list[dict], cols: list[str], details: list[dict]) -> tuple:
    """公式名簿を反映し、(追加人数, 追加行数, name->person_id)を返す。"""
    by_name = {}
    for row in rows:
        by_name.setdefault(row["original"], []).append(row)
    next_id = max((int(row["id"]) for row in rows), default=-1) + 1
    added_people = added_rows = 0
    ids = {}
    for item in details:
        name = item["name"]
        description = f"{item['affiliation']}所属のバーチャルライバー。"
        if name not in by_name:
            row = {col: "" for col in cols}
            row.update({
                "id": str(next_id), "original": name, "surface": name,
                "pronunciation": item["ruby"], "type": "full",
                "category": "vtuber", "org": item["affiliation"],
                "debut_year": item["debut_year"], "status": "current",
                "channel": item["channel"] or "NA",
                "description": description,
                "subscribers": "NA", "subscribers_as_of": "NA",
            })
            rows.append(row)
            by_name[name] = [row]
            next_id += 1
            added_people += 1
            added_rows += 1
        for row in by_name[name]:
            # 既存の手修正は尊重し、欠損だけ公式値で埋める。
            for key, value in {
                "org": item["affiliation"],
                "debut_year": item["debut_year"],
                "channel": item["channel"],
                "description": description,
            }.items():
                if row.get(key) in (None, "", "NA") and value:
                    row[key] = value
            row.setdefault("subscribers", "NA")
            row.setdefault("subscribers_as_of", "NA")
        ids[name] = by_name[name][0]["id"]
    return added_people, added_rows, ids


def update_colors(details: list[dict]) -> int:
    data = json.loads(COLORS_PATH.read_text(encoding="utf-8"))
    colors = data.setdefault("colors", {})
    for item in details:
        colors[item["name"]] = {
            "primary": item["color"],
            "source": "official",
            "source_name": "にじさんじ公式タレントプロフィール",
            "source_url": item["profile_url"],
        }
    data["colors"] = dict(sorted(colors.items()))
    COLORS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return len(details)


def update_channel_sources(details: list[dict], ids: dict, rows: list[dict]) -> int:
    qid_by_id = {}
    for row in rows:
        qid_by_id.setdefault(row["id"], row.get("wikidata") or "NA")
    records = []
    if CHANNEL_SOURCES_PATH.exists():
        records = [json.loads(line) for line in
                   CHANNEL_SOURCES_PATH.read_text(encoding="utf-8").splitlines()
                   if line.strip()]
    existing = {(r.get("person_id"), r.get("channel_id")): r for r in records}
    today = date.today().isoformat()
    for item in details:
        pid = ids[item["name"]]
        key = (pid, item["channel_id"])
        if key in existing:
            continue
        record = {
            "channel_id": item["channel_id"],
            "channel_title": item["channel"],
            "decision": "verified",
            "evidence_url": item["profile_url"],
            "identity_basis": "official_page_explicit_channel_link",
            "observed_on": today,
            "original": item["name"],
            "person_id": pid,
            "qid": qid_by_id.get(pid, "NA"),
            "source_type": "official_talent_profile",
            "source_url": item["profile_url"],
        }
        records.append(record)
        existing[key] = record
    records.sort(key=lambda r: (int(r["person_id"]), r["channel_id"]))
    CHANNEL_SOURCES_PATH.write_text("".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records), encoding="utf-8")
    return len(details)


def main() -> int:
    roster = parse_roster(fetch(LIST_URL))
    print(f"公式名簿: {len(roster)}人。プロフィールを取得中...", flush=True)
    details = fetch_details(roster)
    with CSV_PATH.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        cols = list(reader.fieldnames or [])
    added_people, added_rows, ids = apply_roster(rows, cols, details)
    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    color_count = update_colors(details)
    channel_count = update_channel_sources(details, ids, rows)
    print(f"youtuber.csv: にじさんじ公式名簿 {len(details)}人、"
          f"新規 {added_people}人/{added_rows}行")
    print(f"公式プロフィール色 {color_count}人、チャンネル根拠 {channel_count}人")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
