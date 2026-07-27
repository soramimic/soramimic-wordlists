#!/usr/bin/env python3
"""plant.csv(植物の和名)に画像(Wikimedia Commons)を付与する。

`enrich_sekitsui_images.py` の植物版。update_plant.py と同じ取得単位
(被子植物は目ごと、非被子植物は門・綱ごと)で Wikidata を引き、各 taxon の
日本語ラベル(=original)と P18(画像)・QID から image/image_page/wikidata を
埋める。

- **同名異義(homonym)ガードは「クエリの起点」で効かせる**。植物には動物と
  同じ和名を持つものが多い(スギ・ハス・ホトトギス・カマツカ等)。取得を
  `?t wdt:P171* wd:<植物側の目・門>` に限定しているので、和名で名寄せしても
  動物側の taxon の画像を拾うことはない(ADR 00008 の「同音異義なだけの行は
  残す」方針と整合する)
- ただし Wikidata の系統樹には界をまたぐ誤リンクがあり、動物が植物の目の配下
  として引けることがある(実例: ヘビトンボ Q2481303)。update_plant.py と同じ
  動物界ガード(`animal_taxa`)を書き込み直前にもう一段かける
- 既存の image が空の行だけ埋める(冪等)。他の列は変更しない。ただし
  apply_class_images.py が入れた分類の概念イメージは実写で上書きする
  (概念イメージ→実写は改善方向なので劣化にあたらない)
- 書き出し列は実ファイルのヘッダーに追随する(ADR 00014・00015 と同じ方針)
- WDQS 部分応答ガード: 収集画像数が MIN_TOTAL を下回ったら中断する
- ファイル名はカンマ等を含みうるので必ずURLエンコードする(利用側のCSVパーサは
  クオート非対応の素朴な split(",") のため)
- 取得対象が70件超あり全体で30〜60分かかるので、目・門ごとの取得結果は CACHE に
  逐次保存する。中断しても再実行で続きから再開する(引き直したいときは
  `--refresh` かキャッシュ削除)

usage: python3 tools/enrich_plant_images.py [--refresh]
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_class_images import is_class_image  # noqa: E402
from update_plant import (ANGIOSPERM, CLADES, KATAKANA,  # noqa: E402
                          MONOCOTS, SPECIES, animal_taxa, fetch_orders)
from wpnames import (commons_urls, sparql,  # noqa: E402
                     write_csv_no_trailing_newline)

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "plant.csv"
CACHE = Path(__file__).resolve().parent / ".cache" / "plant_images.json"
# 書き出し列は実ファイルのヘッダーに追随する。この3列だけは無ければ末尾に足す
OWN_COLS = ["image", "image_page", "wikidata"]

# 収集した「画像付きカタカナ和名」の総数がこれを下回ったら WDQS の部分応答
# とみなして中断する。実測 5,809件(2026-07-28。うち plant.csv に載っていて
# 画像が付いたのは 5,799行 = 88.6%)
MIN_TOTAL = 2000


def load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def fetch_images(qid: str) -> dict:
    """QID配下の種で P18 を持つもの -> {和名: [[taxon QID, P18のURL], ...]}。

    和名に複数の taxon がぶら下がることがある(異物同名・シノニム)ので候補を
    全部持っておき、動物界ガードを通ったものを後段で採用する。"""
    query = f"""
SELECT DISTINCT ?t ?l ?img WHERE {{
  ?t wdt:P171* wd:{qid} ; wdt:P105 {SPECIES} ; wdt:P18 ?img ; rdfs:label ?l .
  FILTER(LANG(?l) = "ja")
}}"""
    data = sparql(query)
    out = {}
    for b in data["results"]["bindings"]:
        name = b["l"]["value"]
        if not KATAKANA.match(name):
            continue  # カタカナ和名のみ(plant.csv の収録基準と同じ)
        cand = [b["t"]["value"].rsplit("/", 1)[-1], b["img"]["value"]]
        if cand not in out.setdefault(name, []):
            out[name].append(cand)
    return out


def collect(refresh: bool) -> dict:
    """全取得対象を引いて {和名: [[taxon QID, P18のURL], ...]} にまとめる。"""
    monocot_orders = fetch_orders(MONOCOTS)
    all_orders = fetch_orders(ANGIOSPERM)
    print(f"被子植物の目: {len(all_orders)}(うち単子葉 {len(monocot_orders)})")

    targets = [(o, "単子葉" if o in monocot_orders else "双子葉")
               for o in sorted(all_orders)]
    targets += sorted(CLADES.items())

    cache = {} if refresh else load_cache()
    for qid, cat in targets:
        if qid not in cache:
            cache[qid] = fetch_images(qid)
            save_cache(cache)  # 中断しても再開できるよう逐次保存
            time.sleep(1)      # WDQSへの連続アクセスを避ける
        print(f"{cat}({qid}): 画像付きカタカナ和名 {len(cache[qid])}", flush=True)

    name_cands = {}
    for qid, _ in targets:
        for name, cands in cache[qid].items():
            have = name_cands.setdefault(name, [])
            for c in cands:
                if c not in have:
                    have.append(c)
    return name_cands


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="キャッシュを無視して全目・全門を引き直す")
    args = ap.parse_args()

    name_cands = collect(args.refresh)
    if len(name_cands) < MIN_TOTAL:
        print(f"error: implausible image count: {len(name_cands)}",
              file=sys.stderr)
        return 1
    print(f"画像付きカタカナ和名: 計 {len(name_cands)}")

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        cols = list(reader.fieldnames)
    cols += [c for c in OWN_COLS if c not in cols]
    for r in rows:
        for c in cols:
            r.setdefault(c, "")

    # 実際に書き込む候補だけに絞って動物界ガードをかける(全和名を検査すると
    # 無駄な問い合わせが増える)。実写が既に入っている行は触らない(概念
    # イメージの行は空扱いにして実写で差し替える)
    todo = [r for r in rows
            if (not r["image"] or is_class_image(r["image"]))
            and r["original"] in name_cands]
    qids = sorted({c[0] for r in todo for c in name_cands[r["original"]]})
    print(f"動物界ガード: 対象 {len(todo)}行 / taxon QID {len(qids)}件")
    bad = animal_taxa(qids) if qids else set()

    filled = 0
    dropped = []
    for r in todo:
        ok = [c for c in name_cands[r["original"]] if c[0] not in bad]
        if not ok:
            # 全候補が動物界に到達した = 植物の目の配下に誤リンクされた動物
            dropped.append(r["original"])
            continue
        wd_qid, img = ok[0]
        r["wikidata"] = wd_qid
        r["image"], r["image_page"] = commons_urls(img)
        filled += 1
    if dropped:
        print(f"動物混入として画像を付けなかった和名: {len(dropped)}件 "
              f"{'/'.join(dropped[:20])}")

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    have = sum(1 for r in rows if r["image"] and not is_class_image(r["image"]))
    print(f"画像を付与: +{filled} (計 {have}/{len(rows)}行に実写画像 "
          f"= {have / len(rows) * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
