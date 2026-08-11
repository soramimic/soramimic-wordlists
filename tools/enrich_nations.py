#!/usr/bin/env python3
"""nations.csv に国の基礎情報と短い説明を付与する。

出典:
- 人口・面積・首都・大陸・成立年・終了年: Wikidata (CC0)
- description: 日本語版 Wikipedia の記事冒頭 (CC BY-SA 4.0)

同じ id でも旧称が別の Wikidata item を指す場合があるため、id ではなく各行の
wikidata を基準にする。人口は時変値なので最新の時点付き値で更新し、それ以外は
取得できた値で空欄を補完する。取得失敗時に既存値を消さない。

usage: python3 tools/enrich_nations.py
"""

import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import (fetch_extracts, make_description, sparql,  # noqa: E402
                     write_csv_no_trailing_newline)

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "nations.csv"
MAP_PATH = ROOT / "tools" / "nations_map.csv"
WD_API = "https://www.wikidata.org/w/api.php"
UA = {
    "User-Agent": (
        "soramimic-wordlists-updater/1.0 "
        "(https://github.com/soramimic/soramimic-wordlists)"
    )
}
ADDED_COLS = [
    "capital", "continent", "population", "population_year", "area_km2",
    "established_year", "ended_year", "description",
]
MIN_ENTITIES = 180

# 現存国の旧称は国item自体に解散日(P576)がないため、その名称が日本語で
# 置き換わった年を補う。status=current の同一itemには適用しない。
FORMER_NAME_ENDED_YEAR = {
    "Q230": "2015",  # グルジア -> ジョージア
    "Q1050": "2018",  # スワジランド -> エスワティニ
    "Q221": "2019",  # マケドニア -> 北マケドニア
}


def wd_entities(qids: list[str], props: str) -> dict:
    result = {}
    # 国itemはclaim数が多く、50件指定ではAPIが一部itemを黙って省くことがある。
    for i in range(0, len(qids), 20):
        batch = qids[i:i + 20]
        url = WD_API + "?" + urllib.parse.urlencode({
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": props,
            "languages": "ja",
            "sitefilter": "jawiki",
            "format": "json",
        })
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=60) as res:
                    result.update(json.load(res).get("entities", {}))
                break
            except Exception as ex:
                print(f"Wikidata retry {attempt}: {ex}", file=sys.stderr)
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        time.sleep(0.2)
    missing = set(qids) - set(result)
    if missing:
        raise RuntimeError(
            "Wikidata response omitted entities: " + ", ".join(sorted(missing))
        )
    return result


def statements(entity: dict, prop: str) -> list[dict]:
    return [
        s for s in entity.get("claims", {}).get(prop, [])
        if s.get("rank") != "deprecated"
        and s.get("mainsnak", {}).get("snaktype") == "value"
        and s.get("mainsnak", {}).get("datavalue")
    ]


def preferred(items: list[dict]) -> list[dict]:
    best = [s for s in items if s.get("rank") == "preferred"]
    return best or items


def point_in_time(statement: dict) -> tuple[int, int, int] | None:
    """P585のうち最も遅い年月日を返す。年未満の精度は採用しない。"""
    points = []
    for qualifier in statement.get("qualifiers", {}).get("P585", []):
        if qualifier.get("snaktype") != "value":
            continue
        value = qualifier.get("datavalue", {}).get("value", {})
        if not isinstance(value, dict) or value.get("precision", 0) < 9:
            continue
        match = re.fullmatch(
            r"([+-])(\d+)-(\d{2})-(\d{2})T\d{2}:\d{2}:\d{2}Z",
            value.get("time", ""),
        )
        if not match:
            continue
        sign, year, month, day = match.groups()
        signed_year = int(year) * (-1 if sign == "-" else 1)
        points.append((signed_year, int(month), int(day)))
    return max(points) if points else None


def quantity(statement: dict) -> str:
    value = statement["mainsnak"]["datavalue"]["value"]
    try:
        number = Decimal(value["amount"])
    except (InvalidOperation, KeyError):
        return ""
    if number == number.to_integral():
        return str(int(number))
    return format(number.normalize(), "f")


def latest_population_facts(entity: dict) -> tuple[str, str]:
    """最新の人口値と、その同じstatementに付いた時点(P585)の年を返す。"""
    items = statements(entity, "P1082")
    if not items:
        return "", ""
    dated = [s for s in items if point_in_time(s) is not None]
    chosen = max(
        dated,
        key=lambda s: (point_in_time(s), s.get("rank") == "preferred"),
    ) if dated else preferred(items)[0]
    point = point_in_time(chosen)
    year = point[0] if point else None
    year_text = "" if year is None else (
        f"前{abs(year)}" if year < 0 else str(year)
    )
    return quantity(chosen), year_text


def area(entity: dict) -> str:
    items = preferred(statements(entity, "P2046"))
    return quantity(items[0]) if items else ""


def item_ids(entity: dict, prop: str) -> list[str]:
    ids = []
    for statement in preferred(statements(entity, prop)):
        value = statement["mainsnak"]["datavalue"]["value"]
        qid = value.get("id") if isinstance(value, dict) else None
        if qid and qid not in ids:
            ids.append(qid)
    return ids


def established_year(entity: dict) -> str:
    years = []
    for statement in statements(entity, "P571"):
        value = statement["mainsnak"]["datavalue"]["value"]
        try:
            years.append(int(value["time"][:5]))
        except (KeyError, ValueError):
            continue
    if not years:
        return ""
    year = min(years)
    return f"前{abs(year)}" if year < 0 else str(year)


def ended_year(entity: dict) -> str:
    """解散・廃止日(P576)のうち最も遅い西暦年を返す。"""
    years = []
    for statement in statements(entity, "P576"):
        value = statement["mainsnak"]["datavalue"]["value"]
        try:
            years.append(int(value["time"][:5]))
        except (KeyError, ValueError):
            continue
    if not years:
        return ""
    year = max(years)
    return f"前{abs(year)}" if year < 0 else str(year)


def clean(value: str) -> str:
    return (value or "").replace(",", " ").replace('"', "").strip()


def resolve_missing_qids(rows: list[dict]) -> None:
    """新規加盟国の cca3 から QID を引き、同じ id の行へ設定する。"""
    missing_ids = {r["id"] for r in rows if not r.get("wikidata")}
    if not missing_ids:
        return
    with MAP_PATH.open(encoding="utf-8") as fh:
        id_to_code = {
            r["id"]: r["cca3"] for r in csv.DictReader(fh)
            if r["id"] in missing_ids
        }
    codes = sorted(id_to_code.values())
    if codes:
        values = " ".join(f'"{code}"' for code in codes)
        data = sparql(
            "SELECT ?country ?cca3 WHERE { "
            f"VALUES ?cca3 {{ {values} }} "
            "?country wdt:P298 ?cca3 }"
        )
        code_to_qid = {
            b["cca3"]["value"]: b["country"]["value"].rsplit("/", 1)[-1]
            for b in data["results"]["bindings"]
        }
        for row in rows:
            code = id_to_code.get(row["id"], "")
            if not row.get("wikidata") and code in code_to_qid:
                row["wikidata"] = code_to_qid[code]
    unresolved = sorted({r["id"] for r in rows if not r.get("wikidata")})
    if unresolved:
        raise RuntimeError(
            "rows lack Wikidata QIDs after cca3 lookup: " + ", ".join(unresolved)
        )


def main() -> int:
    with CSV_PATH.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        cols = list(reader.fieldnames or [])
    for col in ADDED_COLS:
        if col not in cols:
            cols.append(col)

    resolve_missing_qids(rows)
    qids = sorted({r.get("wikidata", "") for r in rows if r.get("wikidata")})
    entities = wd_entities(qids, "claims|sitelinks|descriptions")
    if len(entities) < MIN_ENTITIES:
        print(
            f"error: Wikidata entities are too few: {len(entities)}",
            file=sys.stderr,
        )
        return 1

    related = set()
    for entity in entities.values():
        related.update(item_ids(entity, "P36"))
        related.update(item_ids(entity, "P30"))
    labels = wd_entities(sorted(related), "labels")

    titles = {
        qid: entity.get("sitelinks", {}).get("jawiki", {}).get("title", "")
        for qid, entity in entities.items()
    }
    extracts = fetch_extracts(sorted({t for t in titles.values() if t}), limit=300)

    info = {}
    for qid, entity in entities.items():
        title = titles.get(qid, "")
        intro = extracts.get(title, "")
        wd_desc = entity.get("descriptions", {}).get("ja", {}).get("value", "")
        desc = make_description(intro, wd_desc, title)
        population, population_year = latest_population_facts(entity)
        info[qid] = {
            "capital": "/".join(
                labels.get(x, {}).get("labels", {}).get("ja", {}).get("value", "")
                for x in item_ids(entity, "P36")
            ).strip("/"),
            "continent": "/".join(
                labels.get(x, {}).get("labels", {}).get("ja", {}).get("value", "")
                for x in item_ids(entity, "P30")
            ).strip("/"),
            "population": population,
            "population_year": population_year,
            "area_km2": area(entity),
            "established_year": established_year(entity),
            "ended_year": ended_year(entity),
            "description": "" if desc == "NA" else desc,
        }

    for row in rows:
        values = info.get(row.get("wikidata", ""), {})
        new_population = clean(values.get("population", ""))
        if new_population:
            # 人口と基準年は同じP1082 statementの組なので必ず同時に更新する。
            row["population"] = new_population
            row["population_year"] = clean(values.get("population_year", ""))
        for col in ADDED_COLS:
            if col in {"population", "population_year"}:
                continue
            new = clean(values.get(col, ""))
            if col == "ended_year":
                if row.get("status") == "former":
                    new = FORMER_NAME_ENDED_YEAR.get(
                        row.get("wikidata", ""), new,
                    )
                    row[col] = row.get(col, "") or new
                else:
                    row[col] = ""
                continue
            row[col] = row.get(col, "") or new

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    print(f"nations.csv: {len(rows)} rows / {len(qids)} Wikidata items")
    for col in ADDED_COLS:
        count = sum(bool(r.get(col)) for r in rows)
        print(f"  {col}: {count}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
