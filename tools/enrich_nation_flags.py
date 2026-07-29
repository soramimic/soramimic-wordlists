#!/usr/bin/env python3
"""nations.csv に国旗画像(Wikimedia Commons)を付与する。

nations_map.csv(cca3 -> id)で管理された ISO 3166-1 alpha-3 コードから
Wikidata(P298=cca3, P41=国旗)を引き、各国の image / image_page / wikidata を埋める。
コンゴ(COG/COD)・ギニア(GIN/GNQ=赤道ギニア)など同名別国も cca3 で確実に区別できる。

**消滅した国(ソ連・ユーゴスラビア等)には cca3 が無い**ので、この経路では
1件も引けず、画像が空のまま残っていた。これらは `FORMER_STATES` で
行の表記から直接 Wikidata の item を指し、同じ P41 から旗を引く
(詳細は ADR 00026)。

- 既存の image が空の行だけ埋める(冪等)。original/surface/status は変更しない。
- 画像は現行旗(Wikidata P41 のtruthy値)。アフガニスタン等は現政府の旗になる点に注意。
- 消滅国は**その国が最後に使っていた旗**を選ぶ(P41 の優先ランク、次に
  適用終了時期(P582)が最も新しいもの)。ソ連なら1955-1991年の旗になる。
- URLフォーマットと末尾改行なしは wpnames のヘルパに合わせる。

usage: python3 tools/enrich_nation_flags.py
"""

import csv
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import (commons_urls, sparql,  # noqa: E402
                     write_csv_no_trailing_newline)

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "nations.csv"
MAP_PATH = ROOT / "tools" / "nations_map.csv"
# このスクリプトが必ず必要とする列。**実際の列はCSVのヘッダーに追随する**
# (`pronunciation` のように後から増えた列を、このリストで削り落とさないため)
COLS = ["id", "original", "surface", "status", "image", "image_page", "wikidata"]
MIN_EXPECTED = 180  # 主権国家の国旗はこれ以上取れるはず。下回ったらWDQS部分応答とみなす

# 消滅した国・旧称の行 -> Wikidata item。cca3(ISO 3166-1)が無いので
# `nations_map.csv` には載せられず、ここで表記ごとに指す。
#
# **同じ id でも表記ごとに指す item が違うことがある。** ユーゴスラビアは
# 王国(1918-1941)と社会主義連邦共和国(1943-1992)で旗が別物なので、
# 「ユーゴスラビア王国」の行に社会主義連邦共和国の赤星の旗を出すのは誤り。
# 総称の「ユーゴスラビア」だけは通史の item(Q36704)を指し、後述の規則で
# 最後の旗(1946-1992)になる。
FORMER_STATES = {
    # id 78 スリランカの旧称
    "セイロン": "Q2670092",                        # セイロン(1948-1972)
    # id 118 コンゴ民主共和国の旧称
    "ザイール": "Q6500954",                        # ザイール(1971-1997)
    "ザイール共和国": "Q6500954",
    # id 148 ミャンマーの旧称
    "ビルマ": "Q7233551",                          # ビルマ連邦(1948-1962)
    "ビルマ連邦": "Q7233551",
    # id 193 ソビエト連邦
    "ソ連": "Q15180",
    "ソビエト連邦": "Q15180",
    "ソビエト社会主義共和国連邦": "Q15180",
    # id 194 ユーゴスラビア
    "ユーゴスラビア": "Q36704",                     # 通史(1918-1992)
    "ユーゴスラビア社会主義連邦共和国": "Q83286",
    "ユーゴスラビア王国": "Q191077",
    # id 195 チェコスロバキア
    "チェコスロバキア": "Q33946",
    "チェコスロバキア社会主義共和国": "Q853348",
    # id 196 東ドイツ
    "東ドイツ": "Q16957",
    "ドイツ民主共和国": "Q16957",
    # id 197 西ドイツ(旗は現在のドイツと同じ黒赤金)
    "西ドイツ": "Q713750",
}

# Wikidata が指すファイル名では出所が誤解される場合の差し替え。
# チェコスロバキアの P41 は `Flag of the Czech Republic.svg`(現チェコが
# 同じ旗を引き継いだため)を指すが、クレジット先のページ名が
# 「チェコ共和国の旗」になってしまう。**同じ意匠・同じ作者・同じPD**の
# `Flag of Czechoslovakia.svg` が Commons にあるので、そちらを見せる。
FILE_OVERRIDE = {
    "Flag of the Czech Republic.svg": "Flag of Czechoslovakia.svg",
}


def cca3_to_flag() -> dict[str, tuple[str, str, str]]:
    """ISO 3166-1 alpha-3(P298) -> (qid, image_url, image_page)。

    国旗(P41)とcca3(P298)を持ち、主権国家(Q3624078)または国(Q6256)である
    itemに限定して、cca3・国旗・QIDを1本のSPARQLで取る(2段階呼び出しはWDQSの
    部分応答で国が抜けるため一発にする。デンマークのようにP31がQ6256のみの国も
    拾うため両方許可)。ファイル名の空白は _ に、その他(カンマ等)は %エンコードの
    ままにして image/image_page を組む(素朴なCSVパーサを壊さない)。
    """
    data = sparql(
        "SELECT ?c ?cca3 ?flag WHERE { "
        "VALUES ?type { wd:Q3624078 wd:Q6256 } "
        "?c wdt:P31 ?type; wdt:P298 ?cca3; wdt:P41 ?flag }"
    )
    bindings = data["results"]["bindings"]
    if len(bindings) < MIN_EXPECTED:
        raise RuntimeError(
            f"WDQSの応答が少なすぎます({len(bindings)}件)。部分応答の可能性。再実行してください"
        )
    out: dict[str, tuple[str, str, str]] = {}
    for b in bindings:
        cca3 = b["cca3"]["value"]
        if cca3 in out:
            continue  # 同一cca3に複数(旧旗item等)が来たら先勝ち
        qid = b["c"]["value"].rsplit("/", 1)[-1]
        fname = b["flag"]["value"].rsplit("/", 1)[-1].replace("%20", "_")
        out[cca3] = (
            qid,
            "http://commons.wikimedia.org/wiki/Special:FilePath/" + fname,
            "https://commons.wikimedia.org/wiki/File:" + fname,
        )
    return out


def former_flags() -> dict[str, tuple[str, str, str]]:
    """`FORMER_STATES` の item -> (qid, image_url, image_page)。

    消滅国の P41 は「1922-1923年の旗」「1936-1955年の旗」…と複数並ぶので、
    truthy値(`wdt:P41`)ではなく文(`p:P41`)を順位・適用期間ごと取り、
    **その国が最後に使っていた旗**を選ぶ:

    1. 廃止ランクは捨てる
    2. 優先ランクがあればそれだけに絞る(東ドイツは1959年以降の
       国章入りの旗が優先ランク)
    3. 残りから適用終了(P582)が最も新しいものを採る。終了が書かれて
       いない文は「今も有効」とみなして最後に置く
    4. それでも並ぶときはファイル名順(再実行で結果が変わらないように)
    """
    qids = sorted(set(FORMER_STATES.values()))
    data = sparql(
        "SELECT ?c ?flag ?rank ?start ?end WHERE { VALUES ?c { "
        + " ".join("wd:" + q for q in qids)
        + " } ?c p:P41 ?st . ?st ps:P41 ?flag ; wikibase:rank ?rank . "
        "OPTIONAL { ?st pq:P580 ?start } OPTIONAL { ?st pq:P582 ?end } }"
    )
    per_item: dict[str, list[tuple[str, str, str, str]]] = {}
    for b in data["results"]["bindings"]:
        qid = b["c"]["value"].rsplit("/", 1)[-1]
        rank = b["rank"]["value"].rsplit("#", 1)[-1]
        per_item.setdefault(qid, []).append((
            b["flag"]["value"], rank,
            b.get("start", {}).get("value", ""),
            b.get("end", {}).get("value", ""),
        ))
    missing = [q for q in qids if q not in per_item]
    if missing:
        raise RuntimeError(f"旗が引けない消滅国の item があります: {missing}")

    out: dict[str, tuple[str, str, str]] = {}
    for qid, stmts in per_item.items():
        live = [s for s in stmts if s[1] != "DeprecatedRank"]
        preferred = [s for s in live if s[1] == "PreferredRank"]
        pick = max(preferred or live,
                   key=lambda s: (s[3] or "9999", s[2], s[0]))
        fname = urllib.parse.unquote(pick[0].rsplit("/", 1)[-1])
        fname = FILE_OVERRIDE.get(fname.replace("_", " "), fname)
        out[qid] = (qid, *commons_urls(fname))
    return out


def main() -> int:
    id_to_cca3 = {}
    with open(MAP_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            id_to_cca3[row["id"]] = row["cca3"]

    cca3_flag = cca3_to_flag()
    former = former_flags()

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        cols = list(reader.fieldnames)
    for c in COLS:
        if c not in cols:
            cols.append(c)

    filled = 0
    missing = []
    for r in rows:
        for c in cols:
            r.setdefault(c, "")
        if r.get("image"):
            continue  # 既に画像がある行は触らない(冪等)
        # **消滅国・旧称の行を先に見る。** セイロン・ザイール・ビルマの行は
        # 現在の国(スリランカ・コンゴ民主共和国・ミャンマー)と同じ id に
        # ぶら下がっているので、cca3 から引くと現在の旗が付いてしまう
        hit = former.get(FORMER_STATES.get(r["original"], ""))
        if not hit:
            hit = cca3_flag.get(id_to_cca3.get(r["id"], ""))
        if hit:
            r["wikidata"], r["image"], r["image_page"] = hit
            filled += 1
        else:
            missing.append(f"{r['id']}:{r['original']}")

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    print(f"国旗を付与: {filled}/{len(rows)}")
    if missing:
        print("画像なし:", missing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
