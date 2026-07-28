#!/usr/bin/env python3
"""生物リスト(sekitsui/plant/insect)の全行が想定した界・門・綱の配下かを検査する
(読み取り専用)。

Wikidata の系統樹(P171)には稀に界をまたぐ誤リンクがあり、`update_*.py` の
取得クエリ経由で異界のタクソンが混入しうる(実例: 昆虫「ヘビトンボ」が
被子植物の目の配下として引けた。ADR 00014 参照)。このスクリプトは既存の
CSV 全行について逆向きの確認をする。CSV は変更せず、レポートを出すだけ。

判定手順:

1. `wikidata` 列があればその QID を使う。無ければ日本語ラベル(rdfs:label)で
   検索し、それでも引けなければ ja.wikipedia の記事名(リダイレクト追跡)から
   QID を得る。同名タクソンが複数ある場合は候補すべてを見る
2. 候補 QID の上位タクソンを `?t wdt:P171* ?a` で列挙し、想定ルート QID が
   その集合に入るかを Python 側で判定する。`?t wdt:P171* wd:<root>` と書くと
   Blazegraph がルート側から降りる走査になりタイムアウトするため、この向きで
   引いてから判定する(update_plant.py の animal_taxa と同じ理由)
3. 到達しなかった名前を「候補QIDあり(=何か別物の可能性)」と「QIDなし
   (=Wikidataに日本語ラベルが無いだけかもしれない)」に分けて出力する

到達しなかった = 混入、ではない。「ネコ」「クジラ」のような総称は taxon では
なく common name のアイテムなので到達しないし、P171 が繋がっていないだけの
上流不整合もある。出力は削除候補ではなく**目視確認の対象リスト**として扱う。

WDQS への問い合わせは1バッチ100件・バッチ間1秒。sekitsui.csv 全量で15分程度。

usage:
  python3 tools/audit_taxa.py sekitsui        # 脊椎動物 Q25241 配下か
  python3 tools/audit_taxa.py plant           # 植物界 Q756 配下か
  python3 tools/audit_taxa.py insect          # 昆虫綱 Q1390 配下か
  python3 tools/audit_taxa.py sekitsui --root Q729   # ルートを明示指定
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import sparql_post, titles_to_qids  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# リスト名 -> (CSVファイル名, 想定ルートQID, 説明)
TARGETS = {
    "sekitsui": ("sekitsui.csv", "Q25241", "脊椎動物"),
    "plant": ("plant.csv", "Q756", "植物界"),
    "insect": ("insect.csv", "Q1390", "昆虫綱"),
}
BATCH = 100


def resolve_by_label(names: list) -> dict:
    """日本語ラベル -> 候補QIDのリスト(同名タクソンは複数返る)。"""
    out = {}
    for i in range(0, len(names), BATCH):
        chunk = names[i:i + BATCH]
        vals = " ".join('"%s"@ja' % n for n in chunk)
        data = sparql_post(
            "SELECT ?l ?t WHERE { VALUES ?l { %s } ?t rdfs:label ?l . }" % vals)
        for b in data["results"]["bindings"]:
            out.setdefault(b["l"]["value"], []).append(
                b["t"]["value"].rsplit("/", 1)[-1])
        for n in chunk:
            out.setdefault(n, [])
        print(f"  ラベル解決 {i + len(chunk)}/{len(names)}", flush=True)
        time.sleep(1)
    return out


def fetch_ancestors(qids: list) -> dict:
    """QID -> 上位タクソン(P171*)のQID集合。"""
    out = {}
    for i in range(0, len(qids), BATCH):
        chunk = qids[i:i + BATCH]
        vals = " ".join("wd:" + q for q in chunk)
        data = sparql_post(
            "SELECT ?t ?a WHERE { VALUES ?t { %s } ?t wdt:P171* ?a . }" % vals)
        for b in data["results"]["bindings"]:
            out.setdefault(b["t"]["value"].rsplit("/", 1)[-1], set()).add(
                b["a"]["value"].rsplit("/", 1)[-1])
        for q in chunk:
            out.setdefault(q, set())
        print(f"  上位タクソン {i + len(chunk)}/{len(qids)}", flush=True)
        time.sleep(1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", choices=sorted(TARGETS))
    ap.add_argument("--root", help="想定ルートのQID(省略時はリストの既定値)")
    ap.add_argument("--json", type=Path, help="結果を書き出すJSONファイル")
    args = ap.parse_args()
    fname, default_root, desc = TARGETS[args.target]
    root = args.root or default_root

    with (ROOT / fname).open(encoding="utf-8") as f:
        rows = [dict(r) for r in csv.DictReader(f)]
    print(f"{fname}: {len(rows)}行 / ルート {root}({desc})", flush=True)

    # 1. QIDの解決
    cand = {r["original"]: [r["wikidata"]] for r in rows if r.get("wikidata")}
    todo = sorted({r["original"] for r in rows} - set(cand))
    cand.update(resolve_by_label(todo))
    unresolved = sorted(n for n in todo if not cand[n])
    if unresolved:
        print(f"  ja.wikipedia経由で再解決: {len(unresolved)}件", flush=True)
        for n, q in titles_to_qids(unresolved).items():
            cand[n] = [q]

    # 2. 上位タクソンの取得と判定
    anc = fetch_ancestors(sorted({q for v in cand.values() for q in v}))
    reached, missed, noqid = [], [], []
    for r in rows:
        qs = cand.get(r["original"], [])
        if not qs:
            noqid.append(r["original"])
        elif any(root in anc.get(q, ()) for q in qs):
            reached.append(r["original"])
        else:
            missed.append(r["original"])

    print(f"\n=== {fname}: {desc}に到達 {len(reached)} / 未到達 {len(missed)} / "
          f"QID解決不能 {len(noqid)} ===")
    print("[未到達(要目視確認)]")
    for n in missed:
        print(f"  {n}\t{','.join(cand[n])}")
    if args.json:
        args.json.write_text(json.dumps(
            {"reached": len(reached), "missed": {n: cand[n] for n in missed},
             "noqid": noqid}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n{args.json} に書き出した")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
