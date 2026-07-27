#!/usr/bin/env python3
"""plant.csv の全行が本当に植物・藻類かを Wikidata で全量検証する(棚卸し用)。

`tools/update_plant.py` の動物界ガードは**新規追加候補にしか効かない**(ADR
00014)。既に混入している行を洗い出すために、CSV の和名を1件ずつ Wikidata に
突き合わせて次の3段階で判定する。

1. 和名(ja ラベル)から taxon QID を引く。同じ和名に複数の taxon がぶら下がる
   ことがある(スギ=Cryptomeria japonica と魚のスギ等)ので全て取る
2. 各 QID の上位タクソン(P171*)を列挙し、植物界 Q756 / 藻類の門(紅藻・緑藻・
   褐藻・珪藻・車軸藻)/ 動物界 Q729 / 菌界 Q764 への到達を見る。**必ず
   `?t wdt:P171* ?a` の向き**で書くこと。`?t wdt:P171* wd:Q729` と終端を固定
   すると WDQS が動物界側から降りる走査になりタイムアウトする
3. 系統だけでは、動物の taxon の親が異物同名の植物属になっている場合(実例:
   カンブリア紀の葉足動物 Microdictyon sinicum が緑藻の Microdictyon 配下)や、
   植物の taxon に動物の日本語ラベルが付いている場合(実例: Senna versicolor に
   「セモンジンガサハムシ」)を検出できない。そこで description(en/ja)でも
   動物語彙・植物語彙を突き合わせて二重チェックする

判定は自動では確定させない。出力された要確認リストを人(またはエージェント)が
Wikidata/Wikipedia で実体確認し、混入と確定したものを CSV から削除して
`update_plant.py` の EXCLUDED に追加する運用。

WDQS には礼儀正しくアクセスする(バッチ分割・sleep・リトライ)。全量で30〜60分
程度かかる。中間結果は --cache のディレクトリに保存し、再実行時は再利用する。

usage: python3 tools/audit_plant_taxa.py [--cache DIR]
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "plant.csv"

UA = {"User-Agent": "soramimic-wordlists-updater/1.0 "
                    "(https://github.com/soramimic/soramimic-wordlists)"}
WDQS = "https://query.wikidata.org/sparql"

PLANTAE = "Q756"    # 植物界
ANIMALIA = "Q729"   # 動物界
FUNGI = "Q764"      # 菌界
# 藻類は植物界の外に出る系統があるので別枠で正常扱いする(update_plant.py の
# CLADES の藻類5門と同じ)
ALGAE = {
    "Q103169",   # 紅藻 Rhodophyta
    "Q264543",   # 緑藻 Chlorophyta
    "Q184573",   # 褐藻 Phaeophyceae
    "Q9642991",  # 珪藻 Bacillariophyta
    "Q133219",   # 車軸藻 Charophyta
}

# description に出たら「動物・菌類の疑い」とみなす語。`\bant\b` のように必ず語境界を
# 付ける(境界なしだと "plant" が "ant" にマッチして全件が引っかかる)
ANIMAL_EN = re.compile(
    r"\b(insect|beetle|moth|butterfl\w*|fish|fishes|bird|mammal|reptile|amphibian"
    r"|spider|mollusc\w*|snail|crustacean|worm|dinosaur|lobopodian|wasp|bees?|ants?"
    r"|flies|dragonfl\w*|damselfl\w*|bugs?|cicada|animal|frog|snake|lizard|turtle"
    r"|shark|crab|shrimp|corals?|sponge|nematode|arachnid|mites?|ticks?|louse|weevil"
    r"|aphid|cricket|grasshopper|termite|cockroach|mayfly|caddisfly|stonefly"
    r"|lacewing|scorpion|fungus|mushroom)\b", re.I)
ANIMAL_JA = re.compile(
    r"昆虫|甲虫|ハムシ科|魚類|魚の|鳥類|鳥の|哺乳類|爬虫類|両生類|クモ類|軟体動物"
    r"|動物|恐竜|甲殻類|貝類|線虫|環形動物|菌類|キノコ")


def sparql(query: str) -> dict:
    """WDQS に POST で問い合わせる。長い VALUES 句は GET だとヘッダ長制限
    (HTTP 431)に当たるので POST を使う。"""
    body = urllib.parse.urlencode({"query": query, "format": "json"}).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                WDQS, data=body,
                headers={**UA, "Accept": "application/sparql-results+json",
                         "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=120) as res:
                return json.load(res)
        except Exception as ex:
            print(f"WDQS retry {attempt}: {ex}", flush=True)
            time.sleep(30 * (attempt + 1))
    raise RuntimeError("wdqs failed")


def batched(seq, size):
    for i in range(0, len(seq), size):
        yield i, seq[i:i + size]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def resolve_qids(names: list, cache: Path) -> dict:
    """和名 -> [taxon QID]。rank(P105)を持つ taxon を優先し、無いものは
    親タクソン(P171)を持つ item で拾い直す。"""
    path = cache / "name_qids.json"
    got = load(path)
    for mode, body in (("rank", "?t rdfs:label ?l ; wdt:P105 ?r ."),
                       ("parent", "?t rdfs:label ?l ; wdt:P171 ?p .")):
        todo = [n for n in names if n not in got]
        print(f"--- QID解決 mode={mode} 残 {len(todo)}", flush=True)
        for i, chunk in batched(todo, 100):
            values = " ".join('"%s"@ja' % n for n in chunk)
            data = sparql(f"SELECT DISTINCT ?t ?l WHERE {{\n"
                          f"  VALUES ?l {{ {values} }}\n  {body}\n}}")
            for b in data["results"]["bindings"]:
                got.setdefault(b["l"]["value"], []).append(
                    b["t"]["value"].rsplit("/", 1)[-1])
            save(path, got)
            print(f"  {i}: 累計 {len(got)}", flush=True)
            time.sleep(2)
    return got


def fetch_ancestors(qids: list, cache: Path) -> dict:
    """taxon QID -> 上位タクソン QID の集合(自身を含む)。"""
    path = cache / "ancestors.json"
    got = load(path)
    todo = [q for q in qids if q not in got]
    print(f"--- 上位タクソン取得 残 {len(todo)}", flush=True)
    for i, chunk in batched(todo, 100):
        values = " ".join(f"wd:{q}" for q in chunk)
        data = sparql(f"SELECT ?t ?a WHERE {{\n  VALUES ?t {{ {values} }}\n"
                      f"  ?t wdt:P171* ?a .\n}}")
        acc = {}
        for b in data["results"]["bindings"]:
            acc.setdefault(b["t"]["value"].rsplit("/", 1)[-1], set()).add(
                b["a"]["value"].rsplit("/", 1)[-1])
        for q in chunk:
            got[q] = sorted(acc.get(q, ()))
        save(path, got)
        print(f"  {i}: 累計 {len(got)}", flush=True)
        time.sleep(2)
    return got


def fetch_desc(qids: list, cache: Path) -> dict:
    """taxon QID -> {tn: 学名, de: 英語description, dj: 日本語description}。"""
    path = cache / "desc.json"
    got = load(path)
    todo = [q for q in qids if q not in got]
    print(f"--- description取得 残 {len(todo)}", flush=True)
    for i, chunk in batched(todo, 200):
        values = " ".join(f"wd:{q}" for q in chunk)
        data = sparql(f"""SELECT ?t ?tn ?de ?dj WHERE {{
  VALUES ?t {{ {values} }}
  OPTIONAL {{ ?t wdt:P225 ?tn }}
  OPTIONAL {{ ?t schema:description ?de . FILTER(LANG(?de) = "en") }}
  OPTIONAL {{ ?t schema:description ?dj . FILTER(LANG(?dj) = "ja") }}
}}""")
        for b in data["results"]["bindings"]:
            rec = got.setdefault(b["t"]["value"].rsplit("/", 1)[-1], {})
            for k in ("tn", "de", "dj"):
                if k in b:
                    rec[k] = b[k]["value"]
        for q in chunk:
            got.setdefault(q, {})
        save(path, got)
        print(f"  {i}: 累計 {len(got)}", flush=True)
        time.sleep(1)
    return got


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="/tmp/audit_plant_taxa",
                    help="中間結果の保存先(再実行時に再利用する)")
    args = ap.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    names = [r["original"] for r in rows]
    print(f"plant.csv: {len(names)}行")

    name_qids = resolve_qids(names, cache)
    qids = sorted({q for v in name_qids.values() for q in v})
    anc = fetch_ancestors(qids, cache)
    desc = fetch_desc(qids, cache)

    unresolved, animal, fungi, no_plant, mismatch = [], [], [], [], []
    for r in rows:
        name = r["original"]
        qs = name_qids.get(name, [])
        if not qs:
            unresolved.append(name)
            continue
        per = {q: set(anc.get(q, ())) for q in qs}
        # 系統上「植物・藻類として妥当」な QID(和名が動植物で同音異義のときは
        # 植物側の QID が1つでもあれば妥当)
        plant_qs = [q for q, a in per.items()
                    if PLANTAE in a or (a & ALGAE)]
        if not plant_qs:
            if all(ANIMALIA in a for a in per.values()):
                animal.append((name, r["class"], qs))
            elif all(FUNGI in a for a in per.values()):
                fungi.append((name, r["class"], qs))
            else:
                no_plant.append((name, r["class"], qs))
            continue
        # 系統は植物でも description が動物・菌類を指しているものを拾う
        # (異物同名・ラベル誤りによる混入)
        # 「植物語彙が無い」ではなく「動物・菌類語彙がある」で拾う。前者だと
        # "species of kumquat" のような普通の植物が大量に引っかかる。en と ja で
        # 食い違う場合(実例: Senna versicolor は en が species of plant、ja が
        # 「ハムシ科の昆虫」)も拾いたいので、片方でも動物語彙があれば疑い扱いにする
        ok = False
        for q in plant_qs:
            de, dj = desc.get(q, {}).get("de", ""), desc.get(q, {}).get("dj", "")
            if ANIMAL_EN.search(de) or ANIMAL_JA.search(dj):
                continue
            ok = True
        if not ok:
            mismatch.append((name, r["class"],
                             [(q, desc.get(q, {}).get("tn"),
                               desc.get(q, {}).get("de"),
                               desc.get(q, {}).get("dj")) for q in qs]))

    def dump(title, items):
        print(f"\n=== {title}: {len(items)}件")
        for it in items:
            print("  ", it)

    print(f"\n検証 {len(rows)}行 / taxon QID {len(qids)}件")
    dump("QIDが引けない(ラベル改名の可能性。実体確認して残す/直す)", unresolved)
    dump("動物界 Q729 のみに到達(混入の強い疑い)", animal)
    dump("菌界 Q764 のみに到達(混入の疑い)", fungi)
    dump("植物界にも藻類の門にも到達しない(要確認)", no_plant)
    dump("系統は植物だが description が非植物(異物同名・ラベル誤りの疑い)",
         mismatch)
    total = len(animal) + len(fungi) + len(no_plant) + len(mismatch)
    print(f"\n要確認 計 {total}件(自動削除はしない。実体確認のうえ CSV から"
          f"削除し update_plant.py の EXCLUDED に追加すること)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
