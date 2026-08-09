#!/usr/bin/env python3
"""stations.csv に路線名(lines列)を Wikidata + Wikipedia から補完する。

出典:
- Wikidata (CC0): 駅の P81(接続路線)と、路線の P137(運営者)から
  「JR東日本 東北本線」のような「運営者略称 + 路線名」を作る。
  運営者名は P1813(略称)の ja があればそれを、なければ ja ラベルを使う。
  複数路線は「／」区切り。1路線に運営者が複数あるとき(東海道本線の
  JR3社+JR貨物等)は、駅自身の P137(運営者)に含まれる会社 > 貨物系以外
  の順で優先する。路線名自体が運営者名で始まる場合(長良川鉄道越美南線、
  阿武隈急行線等)は重複を避けて路線名だけにする。
- Wikipedia日本語版 (CC BY-SA 4.0): 東京・池袋など主要駅は Wikidata に
  P81 が無いことが多いので、取れなかった駅だけ記事の駅情報テンプレート
  (所属事業者/所属路線)から補完する。

方式:
- 既存の lines が空の行だけ埋める(--refresh で全行を上書き)
- lines 列が無ければ city の後ろに追加する
- 値のカンマ・引用符は CSV を壊すので全角に置換する

usage: python3 tools/enrich_lines.py [--refresh]
"""

import csv
import io
import re
import sys
import time
import urllib.parse
from pathlib import Path

from update_stations import ROOT_CLASSES, WD_API, WDQS, WP_API, http_json

CSV_PATH = Path(__file__).resolve().parent.parent / "stations.csv"
SEP = "／"


def sanitize(s: str) -> str:
    # 素朴なsplit(",")のパーサを壊す文字は全角にする
    return s.replace(",", "、").replace('"', "”").strip()


def fetch_station_lines() -> dict:
    """駅QID -> ["JR東日本 東北本線", ...](日本の鉄道駅・停留場・索道駅全件)"""
    query = f"""
SELECT DISTINCT ?s ?line ?lineLabel ?op ?opLabel ?opShort ?stOp WHERE {{
  ?s wdt:P17 wd:Q17 ; wdt:P31 ?cls .
  ?cls wdt:P279* ?root .
  VALUES ?root {{ {ROOT_CLASSES} }}
  ?s wdt:P81 ?line .
  ?line rdfs:label ?lineLabel . FILTER(LANG(?lineLabel)='ja')
  OPTIONAL {{ ?s wdt:P137 ?stOp . }}
  OPTIONAL {{
    ?line wdt:P137 ?op .
    ?op rdfs:label ?opLabel . FILTER(LANG(?opLabel)='ja')
    OPTIONAL {{ ?op wdt:P1813 ?opShort . FILTER(LANG(?opShort)='ja') }}
  }}
}}"""
    url = WDQS + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    data = http_json(url, wait=70)

    # (駅, 路線) ごとに運営者候補を、駅ごとに駅自身の運営者を集める
    by_pair: dict = {}
    station_ops: dict = {}
    for b in data["results"]["bindings"]:
        st = b["s"]["value"].rsplit("/", 1)[1]
        line_id = b["line"]["value"].rsplit("/", 1)[1]
        e = by_pair.setdefault((st, line_id),
                               {"line": b["lineLabel"]["value"], "ops": {}})
        if "stOp" in b:
            station_ops.setdefault(st, set()).add(
                b["stOp"]["value"].rsplit("/", 1)[1])
        if "opLabel" in b:
            op_id = b["op"]["value"].rsplit("/", 1)[1]
            label = b["opLabel"]["value"]
            short = b.get("opShort", {}).get("value")
            # 略称は最初に見つかったものを採用(複数登録されている場合)
            if op_id not in e["ops"] or (short and not e["ops"][op_id][1]):
                e["ops"][op_id] = (label, short)

    result: dict = {}
    for (st, _line_id), e in sorted(by_pair.items()):
        # 駅自身の運営者と一致する会社 > 貨物系以外 > 名前順 で選ぶ
        # (東海道本線はJR東日本/JR東海/JR西日本/JR貨物が全部運営者に入っている)
        st_ops = station_ops.get(st, set())
        ops = sorted(
            e["ops"].items(),
            key=lambda kv: (kv[0] not in st_ops, "貨物" in kv[1][0], kv[1][0]),
        )
        line_label = e["line"]
        if ops:
            label, short = ops[0][1]
            # 路線名が会社名で始まる場合は付けない(長良川鉄道越美南線等)
            if line_label.startswith(label) or (short and line_label.startswith(short)):
                text = line_label
            else:
                text = f"{short or label} {line_label}"
        else:
            text = line_label
        text = sanitize(text)
        entries = result.setdefault(st, [])
        if text not in entries:
            entries.append(text)
    return result


# 記事中のwikiリンク。File:等と#アンカーは路線名として除外する
WIKILINK = re.compile(r"\[\[([^\[\]|]+)(?:\|([^\[\]]*))?\]\]")
FIELD = re.compile(
    r"^\s*\|\s*(所属事業者|所属路線\d*)\s*=\s*(.*)", re.MULTILINE,
)


def _first_link_text(value: str) -> str:
    for m in WIKILINK.finditer(value):
        target, disp = m.group(1), m.group(2)
        if target.startswith(("#", "File:", "ファイル:", "画像:", "Image:")):
            continue
        return (disp if disp is not None else target).strip()
    return ""


def _parse_operator(value: str) -> str:
    # 「[[東日本旅客鉄道]]（JR東日本）」は括弧内の通称を優先する
    m = re.search(r"（([^（）]+)）", value)
    if m:
        cand = m.group(1).split("・")[0].strip()
        if cand and "[" not in cand and "{" not in cand:
            return cand
    return _first_link_text(value)


def parse_infobox_lines(wikitext: str) -> list:
    """駅情報テンプレートの所属事業者/所属路線から路線名リストを作る"""
    result: list = []
    operator = ""
    for m in FIELD.finditer(wikitext):
        field, value = m.group(1), m.group(2)
        if field == "所属事業者":
            operator = _parse_operator(value)
            continue
        line = _first_link_text(value)
        if not line:
            continue
        text = line if (not operator or line.startswith(operator)) \
            else f"{operator} {line}"
        text = sanitize(text)
        if text not in result:
            result.append(text)
    return result


def fetch_wikipedia_lines(qids: list) -> dict:
    """駅QID -> 路線名リスト。jawiki記事の駅情報テンプレートから取得"""
    # QID -> 記事タイトル
    titles = {}
    for i in range(0, len(qids), 50):
        url = WD_API + "?" + urllib.parse.urlencode({
            "action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
            "props": "sitelinks", "sitefilter": "jawiki", "format": "json"})
        for q, e in http_json(url).get("entities", {}).items():
            t = e.get("sitelinks", {}).get("jawiki", {}).get("title")
            if t:
                titles[q] = t
        time.sleep(0.3)

    # 記事タイトル -> wikitext(本文が大きいので少数ずつ)
    texts = {}
    title_list = sorted(set(titles.values()))
    for i in range(0, len(title_list), 10):
        url = WP_API + "?" + urllib.parse.urlencode({
            "action": "query", "prop": "revisions", "rvprop": "content",
            "rvslots": "main", "redirects": 1, "format": "json",
            "formatversion": "2", "titles": "|".join(title_list[i:i + 10])})
        data = http_json(url)
        # 複数タイトルが同じ記事にリダイレクトされることがあるので1対多で持つ
        redir: dict = {}
        for r in data["query"].get("redirects", []):
            redir.setdefault(r["to"], []).append(r["from"])
        for p in data["query"].get("pages", []):
            revs = p.get("revisions")
            if not revs:
                continue
            content = revs[0]["slots"]["main"]["content"]
            for t in [p["title"]] + redir.get(p["title"], []):
                texts[t] = content
        time.sleep(0.6)

    return {q: parse_infobox_lines(texts[t])
            for q, t in titles.items() if t in texts}


def main() -> int:
    refresh = "--refresh" in sys.argv[1:]

    line_map = fetch_station_lines()
    if len(line_map) < 5000:
        print(f"error: implausible result size: {len(line_map)}", file=sys.stderr)
        return 1

    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = list(reader.fieldnames or [])
        rows = list(reader)
    if "lines" not in cols:
        cols.insert(cols.index("city") + 1, "lines")

    kept = 0
    targets = []
    for r in rows:
        if (r.get("lines") or "") and not refresh:
            kept += 1
            continue
        r["lines"] = SEP.join(line_map.get(r.get("wikidata") or "", []))
        targets.append(r)

    # Wikidataで取れなかった駅はWikipediaの駅情報テンプレートから補完
    missing = [r["wikidata"] for r in targets if not r["lines"] and r.get("wikidata")]
    wp_filled = 0
    if missing:
        wp_map = fetch_wikipedia_lines(missing)
        for r in targets:
            if not r["lines"] and wp_map.get(r.get("wikidata")):
                r["lines"] = SEP.join(wp_map[r["wikidata"]])
                wp_filled += 1

    filled = sum(1 for r in targets if r["lines"])
    empty = len(targets) - filled

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", restval="")
    w.writeheader()
    w.writerows(rows)
    # 末尾改行なしで書く(soramimic側のパーサが最終空行で落ちるため)
    CSV_PATH.write_text(buf.getvalue().rstrip("\n"), encoding="utf-8")

    print(f"stations.csv: lines filled={filled} (wikipedia={wp_filled}), "
          f"empty={empty}, kept={kept}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
