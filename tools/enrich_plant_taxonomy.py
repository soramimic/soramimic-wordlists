#!/usr/bin/env python3
"""plant.csv(植物の和名)に分類階級の科(family)・属(genus)を付与する。

`enrich_sekitsui_taxonomy.py`(動物の目・科)の植物版で、木を辿る処理は
`taxonomy.py` を共有する。植物は目より科・属が一般的な言及単位なので、
取る階級を科(Q35409)・属(Q34740)に変えてある。

出典: Wikidata(CC0)。各行の wikidata QID から親タクソン(P171)を上に辿り、
taxon rank(P105)が科/属のノードの表示名を取る。表示名は「階級付きの日本語
別名 > 日本語ラベル > 学名(P225)」の順(動物と同じ。Wikidataの ja ラベルは
「バラ」のように階級を含まないことがあり、別名に「バラ科」がある)。

- **この工程では和名から逆引きしない**。`wikidata` 列が空の行は空のままにする。植物は
  動物と同じ和名を持つものが多く(スギ・ハス・ホトトギス・カマツカ等)、和名で
  引くと動物側のタクソンを拾ってしまう。CSV の `wikidata` は
  `enrich_plant_entities.py` が種ランク完全一致と植物クレード制約を通して埋めた
  QIDなので、そこから辿るぶんには界をまたがない
- 既存の family/genus が空の行だけ埋める(冪等)。`--refresh` で全行を引き直す。
  他の列は一切変更しない。列が無ければ extinct の後ろに追加する
- 取得結果は CACHE に逐次保存するので、中断しても再実行で続きから再開できる
  (キャッシュを消せば全件引き直し)
- WDQS 部分応答ガード: 科が引けた行が MIN_TOTAL を下回ったら書き込まず中断

usage:
  python3 tools/enrich_plant_taxonomy.py [--refresh]
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import taxonomy as tx  # noqa: E402
from plant_overrides import apply_manual_taxon  # noqa: E402
from wpnames import write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "plant.csv"
CACHE = Path(__file__).resolve().parent / ".cache" / "plant_taxonomy.json"

# 上位の階級から順に(rank QID, 列名, 階級付き別名の語尾)。
# 先頭(科)が幅優先探索の打ち切り階級になる
RANKS = [(tx.FAMILY, "family", "科"), (tx.GENUS, "genus", "属")]
EXTRA_COLS = ["scientific_name", "family_wikidata"]
# 科が引けた行数がこれを下回ったら部分応答とみなして中断
# (QIDのある約5800行に対する下限)
MIN_TOTAL = 3000


def main(argv: list[str]) -> int:
    refresh = "--refresh" in argv[1:]
    own = [c for _, c, _ in RANKS]
    ranks = [q for q, _, _ in RANKS]
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        cols = tx.add_columns(reader.fieldnames, own, "extinct")
        cols = tx.add_columns(cols, ["family_wikidata"], "family")
        cols = tx.add_columns(cols, ["scientific_name"], "genus")

    targets = [r for r in rows if refresh or not any(r.get(c) for c in own)]
    cache = tx.load_cache(CACHE)

    tx.crawl({r.get("wikidata", "") for r in targets}, cache, CACHE, ranks[0])
    tx.add_rank_aliases(cache, CACHE, {q: s for q, _, s in RANKS})

    nodes = cache["nodes"]
    for r in targets:
        q = r.get("wikidata", "")
        vals = tx.resolve(q, nodes, ranks) if q else [""] * len(ranks)
        r.update(dict(zip(own, vals)))
        rank_qids = tx.resolve_qids(q, nodes, ranks) if q else [""] * len(ranks)
        r["family_wikidata"] = rank_qids[0]
        r["scientific_name"] = nodes.get(q, {}).get("sci", "") if q else ""
        apply_manual_taxon(r)
    for r in rows:
        apply_manual_taxon(r)
        for c in cols:
            r.setdefault(c, "")
    filled = {c: sum(1 for r in rows if r[c]) for c in own}

    if filled["family"] < MIN_TOTAL:
        print(f"error: implausible family count: {filled['family']}",
              file=sys.stderr)
        return 1

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    n = len(rows)
    have_qid = sum(1 for r in rows if r.get("wikidata"))
    print(f"plant.csv: 科 {filled['family']}/{n}行, 属 {filled['genus']}/{n}行 "
          f"(QIDのある{have_qid}行に限れば "
          f"科 {sum(1 for r in rows if r['family'] and r.get('wikidata'))}, "
          f"属 {sum(1 for r in rows if r['genus'] and r.get('wikidata'))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
