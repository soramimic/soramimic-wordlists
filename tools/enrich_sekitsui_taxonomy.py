#!/usr/bin/env python3
"""sekitsui.csv(脊椎動物の和名)に分類階級の目(order)・科(family)を付与する。

出典: Wikidata(CC0)。各行の wikidata QID から親タクソン(P171)を上に辿り、
taxon rank(P105)が目(Q36602)/科(Q35409)のノードのラベルを取る。日本語ラベルが
無ければ学名(P225)にフォールバックする。

- 既存の order/family が空の行だけ埋める(冪等)。`--refresh` で全行を引き直す。
  他の列は一切変更しない。列が無ければ extinct の後ろに追加する。
- `wdt:P171*` の推移閉包をWDQSに解かせるとタイムアウトするため、親を1段ずつ
  幅優先で引く。1回のクエリで BATCH 件の VALUES をまとめ、目に達した枝は
  それ以上辿らない。取得結果は CACHE に逐次保存するので、中断しても再実行で
  続きから再開できる(キャッシュを消せば全件引き直し)。
- wikidata 列が空の行(画像が無く QID が未取得の行)は、和名(original)から
  タクソンを逆引きして補う。同名候補が複数あるときは rank=種 を優先する。
  逆引きした QID は CSV には書かない(wikidata 列は画像とセットで埋まる列の
  ため、ここでは触らない)。
- WDQS 部分応答ガード: 目が引けた行が MIN_TOTAL を下回ったら書き込まず中断。

usage:
  python3 tools/enrich_sekitsui_taxonomy.py [--refresh]
"""

import csv
import json
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import sparql, write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "sekitsui.csv"
CACHE = Path(__file__).resolve().parent / ".cache" / "sekitsui_taxonomy.json"

ORDER = "Q36602"   # taxon rank = 目
FAMILY = "Q35409"  # taxon rank = 科
SPECIES = "Q7432"  # taxon rank = 種
RANK_SUFFIX = {ORDER: "目", FAMILY: "科"}
# 1クエリあたりのQID数。WDQSはGETのURLが約8KBを超えると 414 を返すので、
# それに収まる件数にする(QIDは1件あたり約14バイト。400件で約3秒)
BATCH = 400
# 和名は日本語のパーセントエンコードで1件70バイト前後になるため小さめにする
LABEL_BATCH = 60
# クエリ間の待ち(WDQSへの負荷を抑える)
SLEEP = 1.0
# 親を辿る最大段数(タクソン木には無階級のクレードが多く入る)
MAX_DEPTH = 60
# 目が引けた行数がこれを下回ったら部分応答とみなして中断(QIDのある約14000行に対する下限)
MIN_TOTAL = 8000


def load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {"nodes": {}, "labels": {}}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def fetch_nodes(qids: list[str]) -> dict[str, dict]:
    """QID -> {parents, rank, ja, sci}。親(P171)は複数ありうるので配列で持つ。"""
    values = " ".join("wd:" + q for q in qids)
    query = f"""
SELECT ?t ?p ?rank ?ja ?sci WHERE {{
  VALUES ?t {{ {values} }}
  OPTIONAL {{ ?t wdt:P171 ?p }}
  OPTIONAL {{ ?t wdt:P105 ?rank }}
  OPTIONAL {{ ?t rdfs:label ?ja . FILTER(LANG(?ja) = "ja") }}
  OPTIONAL {{ ?t wdt:P225 ?sci }}
}}"""
    data = sparql(query)
    # 存在しないQIDや情報の無いQIDも「取得済み」として記録し、再開時に引き直さない
    out = {q: {"parents": [], "rank": "", "ja": "", "sci": ""} for q in qids}
    for b in data["results"]["bindings"]:
        n = out.setdefault(qid(b["t"]["value"]),
                           {"parents": [], "rank": "", "ja": "", "sci": ""})
        if "p" in b:
            p = qid(b["p"]["value"])
            if p not in n["parents"]:
                n["parents"].append(p)
        if "rank" in b and not n["rank"]:
            n["rank"] = qid(b["rank"]["value"])
        if "ja" in b and not n["ja"]:
            n["ja"] = b["ja"]["value"]
        if "sci" in b and not n["sci"]:
            n["sci"] = b["sci"]["value"]
    return out


def fetch_alt_labels(qids: list[str]) -> dict[str, list[str]]:
    """QID -> 日本語の別名(skos:altLabel)一覧。"""
    values = " ".join("wd:" + q for q in qids)
    query = f"""
SELECT ?t ?alt WHERE {{
  VALUES ?t {{ {values} }}
  ?t skos:altLabel ?alt . FILTER(LANG(?alt) = "ja")
}}"""
    data = sparql(query)
    out: dict[str, list[str]] = {}
    for b in data["results"]["bindings"]:
        out.setdefault(qid(b["t"]["value"]), []).append(b["alt"]["value"])
    return out


def add_rank_aliases(cache: dict) -> None:
    """目/科ノードのうち日本語ラベルが「目」「科」で終わらないものに、階級付きの
    別名を補う(例: Anura はラベルが「カエル」だが別名に「カエル目」がある)。
    ラベルの語尾が階級を表さないと、目・科での絞り込みがちぐはぐになるため。"""
    nodes = cache["nodes"]
    todo = sorted(q for q, n in nodes.items()
                  if n["rank"] in RANK_SUFFIX and "alt" not in n
                  and not n["ja"].endswith(RANK_SUFFIX[n["rank"]]))
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        alts = fetch_alt_labels(chunk)
        for q in chunk:
            suffix = RANK_SUFFIX[nodes[q]["rank"]]
            hit = sorted(a for a in alts.get(q, []) if a.endswith(suffix))
            nodes[q]["alt"] = hit[0] if hit else ""
        save_cache(cache)
        print(f"階級付き別名: {i + len(chunk)}/{len(todo)} ノード", flush=True)
        time.sleep(SLEEP)


def fetch_labels(names: list[str]) -> dict[str, str]:
    """和名 -> タクソンQID。同名候補は rank=種 を優先し、それ以外は先勝ち。"""
    values = " ".join(json.dumps(n, ensure_ascii=False) + "@ja" for n in names)
    query = f"""
SELECT ?t ?l ?rank WHERE {{
  VALUES ?l {{ {values} }}
  ?t rdfs:label ?l ; wdt:P105 ?rank .
}}"""
    data = sparql(query)
    out: dict[str, str] = {}
    ranked: set[str] = set()
    for b in data["results"]["bindings"]:
        name = b["l"]["value"]
        t = qid(b["t"]["value"])
        if qid(b["rank"]["value"]) == SPECIES:
            if name not in ranked:
                out[name] = t
                ranked.add(name)
        elif name not in out:
            out[name] = t
    return out


def crawl(seeds: set[str], cache: dict) -> None:
    """seeds から親を1段ずつ幅優先で辿り、cache["nodes"] を埋める。
    目(rank=order)に達した枝はそれ以上辿らない(科は目より下なので取り逃さない)。"""
    nodes = cache["nodes"]
    expanded: set[str] = set()
    frontier = {q for q in seeds if q}
    for depth in range(MAX_DEPTH):
        todo = sorted(q for q in frontier if q not in nodes)
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            nodes.update(fetch_nodes(chunk))
            save_cache(cache)  # 中断しても再開できるよう逐次保存
            print(f"depth {depth}: {i + len(chunk)}/{len(todo)} ノード取得",
                  flush=True)
            time.sleep(SLEEP)
        nxt: set[str] = set()
        for q in frontier:
            if q in expanded:
                continue
            expanded.add(q)
            n = nodes.get(q)
            if not n or n["rank"] == ORDER:
                continue  # 目より上は不要(科は目より下なので取り逃さない)
            nxt.update(p for p in n["parents"] if p not in expanded)
        frontier = nxt
        if not frontier:
            return
    print(f"warning: 深さ{MAX_DEPTH}で打ち切り(未解決 {len(frontier)}ノード)",
          file=sys.stderr)


def label_of(node: dict) -> str:
    """階級付きの日本語別名 > 日本語ラベル > 学名(P225)。
    素朴なCSVパーサを壊す文字は置換する。"""
    v = (node.get("alt") or node["ja"] or node["sci"] or "").strip()
    return v.replace(",", "、").replace('"', "”")


def resolve(start: str, nodes: dict) -> tuple[str, str]:
    """start から親を幅優先で辿り、最も近い目・科の表示名を返す。"""
    seen: set[str] = set()
    queue = deque([start])
    order = family = ""
    while queue:
        q = queue.popleft()
        if q in seen:
            continue
        seen.add(q)
        n = nodes.get(q)
        if not n:
            continue
        if n["rank"] == ORDER and not order:
            order = label_of(n)
        elif n["rank"] == FAMILY and not family:
            family = label_of(n)
        if order and family:
            break
        queue.extend(n["parents"])
    return order, family


def add_columns(header: list[str]) -> list[str]:
    """order/family 列を extinct の後ろに追加する(既にあればそのまま)。"""
    cols = list(header)
    for name, prev in (("order", "extinct"), ("family", "order")):
        if name not in cols:
            cols.insert(cols.index(prev) + 1 if prev in cols else len(cols), name)
    return cols


def main(argv: list[str]) -> int:
    refresh = "--refresh" in argv[1:]
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        cols = add_columns(reader.fieldnames)

    targets = [r for r in rows
               if refresh or not (r.get("order") or r.get("family"))]
    cache = load_cache()

    # wikidata列が空の行は和名からタクソンを逆引きする
    unknown = sorted({r["original"] for r in targets if not r.get("wikidata")}
                     - set(cache["labels"]))
    for i in range(0, len(unknown), LABEL_BATCH):
        chunk = unknown[i:i + LABEL_BATCH]
        got = fetch_labels(chunk)
        cache["labels"].update({n: got.get(n, "") for n in chunk})
        save_cache(cache)
        print(f"和名の逆引き: {i + len(chunk)}/{len(unknown)} 件", flush=True)
        time.sleep(SLEEP)

    def row_qid(r: dict) -> str:
        return r.get("wikidata") or cache["labels"].get(r["original"], "")

    crawl({row_qid(r) for r in targets}, cache)
    add_rank_aliases(cache)

    nodes = cache["nodes"]
    filled_order = filled_family = 0
    for r in targets:
        q = row_qid(r)
        order, family = resolve(q, nodes) if q else ("", "")
        r["order"], r["family"] = order, family
    for r in rows:
        for c in cols:
            r.setdefault(c, "")
        filled_order += 1 if r["order"] else 0
        filled_family += 1 if r["family"] else 0

    if filled_order < MIN_TOTAL:
        print(f"error: implausible order count: {filled_order}", file=sys.stderr)
        return 1

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    n = len(rows)
    print(f"sekitsui.csv: 目 {filled_order}/{n}行, 科 {filled_family}/{n}行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
