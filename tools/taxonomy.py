#!/usr/bin/env python3
"""Wikidataのタクソン木を親(P171)方向に辿り、指定した階級の表示名を得る共通処理。

`enrich_sekitsui_taxonomy.py`(目・科)と `enrich_plant_taxonomy.py`(科・属)が
共有する。設計の背景は ADR 00015 / 00017。

- `wdt:P171*` の推移閉包をWDQSに解かせるとタイムアウトするため、親を1段ずつ
  幅優先で引く。1回のクエリで BATCH 件の VALUES をまとめ、目的の最上位階級
  (`stop_rank`)に達した枝はそれ以上辿らない
- クエリはPOST(`wpnames.sparql_post`)で投げる。VALUES に数百件を並べると
  GETではURIが長すぎて HTTP 414 になるため
- 取得結果は呼び出し側が指定するキャッシュに逐次保存する。中断しても再実行で
  続きから再開できる(キャッシュを消せば全件引き直し)
"""

import json
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import sparql_post  # noqa: E402

# 分類階級(P105)のQID
ORDER = "Q36602"   # 目
FAMILY = "Q35409"  # 科
GENUS = "Q34740"   # 属
SPECIES = "Q7432"  # 種

# 1クエリあたりのQID数(400件で約3秒)
BATCH = 400
# 和名は日本語のパーセントエンコードで1件70バイト前後になるため小さめにする
LABEL_BATCH = 60
# クエリ間の待ち(WDQSへの負荷を抑える)
SLEEP = 1.0
# 親を辿る最大段数(タクソン木には無階級のクレードが多く入る)
MAX_DEPTH = 60


def fetch_scientific_taxa(
    names_and_ranks: list[tuple[str, str]],
) -> dict[tuple[str, str], list[dict]]:
    """P225（学名）とP105（階級）がともに一致する分類群をまとめて取得する。

    戻り値の候補には日本語ラベルと日本語別名を含める。同じ学名を持つ項目が
    複数あることがあるため、呼び出し側で曖昧性を判定できるよう候補を潰さない。
    """
    pairs = list(dict.fromkeys(names_and_ranks))
    if not pairs:
        return {}
    values = " ".join(
        f"({json.dumps(name, ensure_ascii=False)} wd:{rank})"
        for name, rank in pairs
    )
    query = f"""
SELECT ?t ?sci ?rank ?ja ?alt WHERE {{
  VALUES (?sci ?rank) {{ {values} }}
  ?t wdt:P225 ?sci ; wdt:P105 ?rank .
  OPTIONAL {{ ?t rdfs:label ?ja . FILTER(LANG(?ja) = "ja") }}
  OPTIONAL {{ ?t skos:altLabel ?alt . FILTER(LANG(?alt) = "ja") }}
}}"""
    data = sparql_post(query)
    by_pair: dict[tuple[str, str], dict[str, dict]] = {
        pair: {} for pair in pairs
    }
    for binding in data["results"]["bindings"]:
        pair = (binding["sci"]["value"], qid(binding["rank"]["value"]))
        if pair not in by_pair:
            continue
        taxon_qid = qid(binding["t"]["value"])
        candidate = by_pair[pair].setdefault(
            taxon_qid, {"qid": taxon_qid, "ja": "", "alts": []}
        )
        if "ja" in binding and not candidate["ja"]:
            candidate["ja"] = binding["ja"]["value"]
        if "alt" in binding:
            alt = binding["alt"]["value"]
            if alt not in candidate["alts"]:
                candidate["alts"].append(alt)
    return {pair: list(candidates.values()) for pair, candidates in by_pair.items()}


def load_cache(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"nodes": {}, "labels": {}}


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


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
    data = sparql_post(query)
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
    data = sparql_post(query)
    out: dict[str, list[str]] = {}
    for b in data["results"]["bindings"]:
        out.setdefault(qid(b["t"]["value"]), []).append(b["alt"]["value"])
    return out


def add_rank_aliases(cache: dict, cache_path: Path,
                     rank_suffix: dict[str, str]) -> None:
    """対象階級のノードのうち日本語ラベルが階級の語(「目」「科」「属」)で
    終わらないものに、階級付きの別名を補う(例: Anura はラベルが「カエル」だが
    別名に「カエル目」がある)。ラベルの語尾が階級を表さないと、階級での
    絞り込みがちぐはぐになるため。"""
    nodes = cache["nodes"]
    todo = sorted(q for q, n in nodes.items()
                  if n["rank"] in rank_suffix and "alt" not in n
                  and not n["ja"].endswith(rank_suffix[n["rank"]]))
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        alts = fetch_alt_labels(chunk)
        for q in chunk:
            suffix = rank_suffix[nodes[q]["rank"]]
            hit = sorted(a for a in alts.get(q, []) if a.endswith(suffix))
            nodes[q]["alt"] = hit[0] if hit else ""
        save_cache(cache_path, cache)
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
    data = sparql_post(query)
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


def resolve_names(names: list[str], cache: dict, cache_path: Path) -> None:
    """未取得の和名だけ逆引きして cache["labels"] に入れる(取れなければ空)。"""
    todo = sorted(set(names) - set(cache["labels"]))
    for i in range(0, len(todo), LABEL_BATCH):
        chunk = todo[i:i + LABEL_BATCH]
        got = fetch_labels(chunk)
        cache["labels"].update({n: got.get(n, "") for n in chunk})
        save_cache(cache_path, cache)
        print(f"和名の逆引き: {i + len(chunk)}/{len(todo)} 件", flush=True)
        time.sleep(SLEEP)


def crawl(seeds: set[str], cache: dict, cache_path: Path,
          stop_rank: str) -> None:
    """seeds から親を1段ずつ幅優先で辿り、cache["nodes"] を埋める。
    stop_rank(対象階級のうち最上位)に達した枝はそれ以上辿らない
    (下位の階級は stop_rank より下にあるので取り逃さない)。"""
    nodes = cache["nodes"]
    expanded: set[str] = set()
    frontier = {q for q in seeds if q}
    for depth in range(MAX_DEPTH):
        todo = sorted(q for q in frontier if q not in nodes)
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            nodes.update(fetch_nodes(chunk))
            save_cache(cache_path, cache)  # 中断しても再開できるよう逐次保存
            print(f"depth {depth}: {i + len(chunk)}/{len(todo)} ノード取得",
                  flush=True)
            time.sleep(SLEEP)
        nxt: set[str] = set()
        for q in frontier:
            if q in expanded:
                continue
            expanded.add(q)
            n = nodes.get(q)
            if not n or n["rank"] == stop_rank:
                continue  # stop_rank より上は不要
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


def resolve(start: str, nodes: dict, ranks: list[str]) -> list[str]:
    """start から親を幅優先で辿り、ranks それぞれに最も近いノードの表示名を返す。"""
    seen: set[str] = set()
    queue = deque([start])
    found = {r: "" for r in ranks}
    while queue:
        q = queue.popleft()
        if q in seen:
            continue
        seen.add(q)
        n = nodes.get(q)
        if not n:
            continue
        if n["rank"] in found and not found[n["rank"]]:
            found[n["rank"]] = label_of(n)
        if all(found.values()):
            break
        queue.extend(n["parents"])
    return [found[r] for r in ranks]


def add_columns(header: list[str], names: list[str], after: str) -> list[str]:
    """names の列を after の後ろに順に追加する(既にあればそのまま)。"""
    cols = list(header)
    prev = after
    for name in names:
        if name not in cols:
            cols.insert(cols.index(prev) + 1 if prev in cols else len(cols),
                        name)
        prev = name
    return cols
