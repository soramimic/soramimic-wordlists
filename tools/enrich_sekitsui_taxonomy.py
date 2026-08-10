#!/usr/bin/env python3
"""sekitsui.csv(脊椎動物の和名)に分類階級の目(order)・科(family)を付与する。

出典: Wikidata(CC0)。各行の wikidata QID から親タクソン(P171)を上に辿り、
taxon rank(P105)が目(Q36602)/科(Q35409)のノードのラベルを取る。日本語ラベルが
無ければ学名(P225)にフォールバックする。木を辿る処理は `taxonomy.py` にある
(植物の科・属を取る enrich_plant_taxonomy.py と共通)。

- 既存の order/family が空の行だけ埋める(冪等)。`--refresh` で全行を引き直す。
  他の列は一切変更しない。列が無ければ extinct の後ろに追加する。
- 取得結果は CACHE に逐次保存するので、中断しても再実行で続きから再開できる
  (キャッシュを消せば全件引き直し)。
- wikidata 列が空の行(画像が無く QID が未取得の行)は、和名(original)から
  タクソンを逆引きして補う。同名候補が複数あるときは rank=種 を優先する。
  逆引きした QID は CSV には書かない(wikidata 列は画像とセットで埋まる列の
  ため、ここでは触らない)。
- WDQS 部分応答ガード: 目が引けた行が MIN_TOTAL を下回ったら書き込まず中断。
- 目・科から大分類が一意に決まる `class=NA` 行は class も補完する。

usage:
  python3 tools/enrich_sekitsui_taxonomy.py [--refresh]
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import taxonomy as tx  # noqa: E402
from sekitsui_overrides import (  # noqa: E402
    apply_manual_ranks,
    build_rank_class_maps,
    class_from_ranks,
)
from wpnames import write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "sekitsui.csv"
CACHE = Path(__file__).resolve().parent / ".cache" / "sekitsui_taxonomy.json"

# 上位の階級から順に(rank QID, 列名, 階級付き別名の語尾)。
# 先頭(目)が幅優先探索の打ち切り階級になる
RANKS = [(tx.ORDER, "order", "目"), (tx.FAMILY, "family", "科")]
# 目が引けた行数がこれを下回ったら部分応答とみなして中断(QIDのある約14000行に対する下限)
MIN_TOTAL = 8000


def main(argv: list[str]) -> int:
    refresh = "--refresh" in argv[1:]
    own = [c for _, c, _ in RANKS]
    ranks = [q for q, _, _ in RANKS]
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        cols = tx.add_columns(reader.fieldnames, own, "extinct")

    targets = [r for r in rows if refresh or not any(r.get(c) for c in own)]
    cache = tx.load_cache(CACHE)

    # wikidata列が空の行は和名からタクソンを逆引きする
    tx.resolve_names([r["original"] for r in targets if not r.get("wikidata")],
                     cache, CACHE)

    def row_qid(r: dict) -> str:
        return r.get("wikidata") or cache["labels"].get(r["original"], "")

    tx.crawl({row_qid(r) for r in targets}, cache, CACHE, ranks[0])
    tx.add_rank_aliases(cache, CACHE, {q: s for q, _, s in RANKS})

    nodes = cache["nodes"]
    for r in targets:
        q = row_qid(r)
        vals = tx.resolve(q, nodes, ranks) if q else [""] * len(ranks)
        r.update(dict(zip(own, vals)))
        apply_manual_ranks(r["original"], r)
    rank_classes = build_rank_class_maps(rows)
    for r in rows:
        if (r.get("class") or "").strip() in ("", "NA"):
            inferred = class_from_ranks(r, rank_classes)
            if inferred:
                r["class"] = inferred
    for r in rows:
        for c in cols:
            r.setdefault(c, "")
    filled = {c: sum(1 for r in rows if r[c]) for c in own}

    if filled["order"] < MIN_TOTAL:
        print(f"error: implausible order count: {filled['order']}",
              file=sys.stderr)
        return 1

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    n = len(rows)
    print(f"sekitsui.csv: 目 {filled['order']}/{n}行, "
          f"科 {filled['family']}/{n}行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
