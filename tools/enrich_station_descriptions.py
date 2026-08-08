#!/usr/bin/env python3
"""stations.csv の空の description を Wikipedia/Wikidata から補完する。

通常は既存の description を上書きしない。日本語版 Wikipedia の記事冒頭を優先し、
記事が無い場合は Wikidata の日本語 description を使う。出典の更新を明示的に
反映するときだけ --refresh で取得可能な説明を再生成する。

usage: python3 tools/enrich_station_descriptions.py
       python3 tools/enrich_station_descriptions.py --refresh
"""

import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from wpnames import fetch_extracts, make_description

UA = {
    "User-Agent": (
        "soramimic-wordlists-updater/1.0 "
        "(https://github.com/soramimic/soramimic-wordlists)"
    )
}
WD_API = "https://www.wikidata.org/w/api.php"
CSV_PATH = Path(__file__).resolve().parent.parent / "stations.csv"
COLS = [
    "id", "original", "surface", "pronunciation", "prefecture", "city",
    "lines", "operator", "opened_year", "station_code", "status",
    "image", "image_page", "description", "wikidata",
]
DISAMBIG = re.compile(r"\s+\([^)]*\)$")


def fetch_entities(qids: list[str]) -> dict[str, dict[str, str]]:
    result = {}
    for i in range(0, len(qids), 50):
        url = WD_API + "?" + urllib.parse.urlencode({
            "action": "wbgetentities",
            "ids": "|".join(qids[i:i + 50]),
            "props": "sitelinks|descriptions",
            "sitefilter": "jawiki",
            "languages": "ja",
            "format": "json",
        })
        last_error = None
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=60) as response:
                    entities = json.load(response).get("entities", {})
                break
            except Exception as ex:
                last_error = ex
                print(f"Wikidata retry {attempt}: {ex}")
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"Wikidata API failed: {last_error}")

        for qid, entity in entities.items():
            result[qid] = {
                "title": entity.get("sitelinks", {}).get("jawiki", {}).get("title", ""),
                "description": (
                    entity.get("descriptions", {}).get("ja", {}).get("value", "")
                ),
            }
        time.sleep(0.3)
    return result


def main() -> int:
    refresh = "--refresh" in sys.argv[1:]
    unknown = [arg for arg in sys.argv[1:] if arg != "--refresh"]
    if unknown:
        print(f"unknown option: {unknown[0]}", file=sys.stderr)
        return 2

    with CSV_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    targets = [
        r for r in rows
        if r.get("wikidata") and (refresh or not r.get("description"))
    ]
    entities = fetch_entities(sorted({r["wikidata"] for r in targets}))
    titles = sorted({
        entities.get(r["wikidata"], {}).get("title", "")
        for r in targets
        if entities.get(r["wikidata"], {}).get("title")
    })
    extracts = fetch_extracts(titles)

    filled = 0
    for row in targets:
        entity = entities.get(row["wikidata"], {})
        title = entity.get("title", "")
        desc = make_description(
            extracts.get(title, ""),
            entity.get("description", ""),
            DISAMBIG.sub("", title),
        )
        if desc != "NA":
            row["description"] = desc
            filled += 1

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=COLS, lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    writer.writerows(rows)
    CSV_PATH.write_text(buf.getvalue().rstrip("\n"), encoding="utf-8")

    total = sum(bool(r.get("description")) for r in rows)
    print(
        f"stations.csv: description {filled}件補完、"
        f"{total}/{len(rows)}件 ({total * 100 / len(rows):.1f}%)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
