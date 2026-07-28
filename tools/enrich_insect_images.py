#!/usr/bin/env python3
"""insect.csv(昆虫の和名)に画像(Wikimedia Commons)を付与する。

`enrich_plant_images.py` の昆虫版。update_insect.py と同じ取得単位(昆虫綱から
下向きに辿って集めた目など)で Wikidata を引き、各 taxon の日本語ラベル
(=original)と P18(画像)・QID から image/image_page/wikidata を埋める。

- **同名異義(homonym)ガードは「クエリの起点」で効かせる**。昆虫には脊椎動物・
  植物と同じ和名を持つものが多い(カマキリ=昆虫だが魚アユカケの別名でもある /
  トンボ / セミ / ミノムシ 等)。取得を `?t wdt:P171* wd:<昆虫側の目>` に限定して
  いるので、和名で名寄せしても魚や植物の taxon の画像を拾うことはない
  (ADR 00021 の「同音異義なだけの行は残す」方針と整合する)
- ただし Wikidata の系統樹には界をまたぐ誤リンクがあるので、update_insect.py と
  同じ混入ガード(`screen_taxa`。昆虫綱 Q1390 に到達し、かつ脊椎動物 Q25241 /
  植物界 Q756 に到達しないこと)を書き込み直前にもう一段かける
- 既存の image が空の行だけ埋める(冪等)。他の列は変更しない。ただし
  apply_class_images.py が入れた分類の概念イメージは実写で上書きする
  (概念イメージ→実写は改善方向なので劣化にあたらない)
- 書き出し列は実ファイルのヘッダーに追随する(ADR 00014 と同じ方針)
- WDQS 部分応答ガード: 収集画像数が MIN_TOTAL を下回ったら中断する
- ファイル名はカンマ等を含みうるので必ずURLエンコードする(利用側のCSVパーサは
  クオート非対応の素朴な split(",") のため)
- 取得対象が170件超あり全体で60分前後かかるので、対象ごとの取得結果は CACHE に
  逐次保存する。中断しても再実行で続きから再開する(引き直したいときは
  `--refresh` かキャッシュ削除)

usage: python3 tools/enrich_insect_images.py [--refresh]
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_class_images import is_class_image  # noqa: E402
from update_insect import (CLASS_BY_ORDER, KATAKANA,  # noqa: E402
                           SPECIES, fetch_children, fetch_targets, qid_of,
                           screen_taxa, try_sparql)
from wpnames import (commons_urls,  # noqa: E402
                     write_csv_no_trailing_newline)

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "insect.csv"
CACHE = Path(__file__).resolve().parent / ".cache" / "insect_images.json"
# 書き出し列は実ファイルのヘッダーに追随する。この3列だけは無ければ末尾に足す
OWN_COLS = ["image", "image_page", "wikidata"]

# 収集した「画像付きカタカナ和名」の総数がこれを下回ったら WDQS の部分応答
# とみなして中断する。実測 1,420件(2026-07-28。うち insect.csv に載っていて
# 画像が付いたのは 1,420行 = 71.7%)
MIN_TOTAL = 800
# 分割の最大深さ(update_insect.fetch_taxa と同じくコウチュウ目対策)
MAX_SPLIT_DEPTH = 5


def load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def fetch_images(qid: str, depth: int = 0) -> dict:
    """QID配下の種で P18 を持つもの -> {和名: [[taxon QID, P18のURL], ...]}。

    和名に複数の taxon がぶら下がることがある(異物同名・シノニム)ので候補を
    全部持っておき、混入ガードを通ったものを後段で採用する。
    重すぎてタイムアウトする対象(コウチュウ目)は子タクソンに再帰分割する。"""
    query = f"""
SELECT DISTINCT ?t ?l ?img WHERE {{
  ?t wdt:P171* wd:{qid} ; wdt:P105 {SPECIES} ; wdt:P18 ?img ; rdfs:label ?l .
  FILTER(LANG(?l) = "ja")
}}"""
    data = try_sparql(query)
    if data is None:
        if depth >= MAX_SPLIT_DEPTH:
            print(f"warning: {qid} の取得を諦めた(分割上限)", file=sys.stderr)
            return {}
        kids = sorted(fetch_children([qid]))
        print(f"  {qid} はタイムアウト: 子 {len(kids)}件に分割(深さ {depth + 1})",
              flush=True)
        merged: dict = {}
        for k in kids:
            for name, cands in fetch_images(k, depth + 1).items():
                have = merged.setdefault(name, [])
                for c in cands:
                    if c not in have:
                        have.append(c)
            time.sleep(1)
        return merged

    out: dict = {}
    for b in data["results"]["bindings"]:
        name = b["l"]["value"]
        if not KATAKANA.match(name):
            continue  # カタカナ和名のみ(insect.csv の収録基準と同じ)
        cand = [qid_of(b["t"]["value"]), b["img"]["value"]]
        if cand not in out.setdefault(name, []):
            out[name].append(cand)
    return out


def collect(refresh: bool) -> dict:
    """全取得対象を引いて {和名: [[taxon QID, P18のURL], ...]} にまとめる。"""
    targets = fetch_targets(refresh)
    ordered = sorted(targets, key=lambda q: (q not in CLASS_BY_ORDER, q))
    print(f"取得対象 {len(ordered)}件")

    cache = {} if refresh else load_cache()
    for i, qid in enumerate(ordered, 1):
        if qid not in cache:
            cache[qid] = fetch_images(qid)
            save_cache(cache)  # 中断しても再開できるよう逐次保存
            time.sleep(1)      # WDQSへの連続アクセスを避ける
        print(f"[{i}/{len(ordered)}] {targets[qid].get('sci') or qid}: "
              f"画像付きカタカナ和名 {len(cache[qid])}", flush=True)

    name_cands: dict = {}
    for qid in ordered:
        for name, cands in cache[qid].items():
            have = name_cands.setdefault(name, [])
            for c in cands:
                if c not in have:
                    have.append(c)
    return name_cands


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="キャッシュを無視して全対象を引き直す")
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

    # 実際に書き込む候補だけに絞って混入ガードをかける(全和名を検査すると
    # 無駄な問い合わせが増える)。実写が既に入っている行は触らない(概念
    # イメージの行は空扱いにして実写で差し替える)
    todo = [r for r in rows
            if (not r["image"] or is_class_image(r["image"]))
            and r["original"] in name_cands]
    qids = sorted({c[0] for r in todo for c in name_cands[r["original"]]})
    print(f"混入ガード: 対象 {len(todo)}行 / taxon QID {len(qids)}件")
    good, crossed = screen_taxa(qids) if qids else (set(), set())
    flagged = sorted({r["original"] for r in todo
                      if {c[0] for c in name_cands[r["original"]]} & crossed})
    if flagged:
        print(f"注意: 界をまたぐ誤リンクを持つ和名 {len(flagged)}件(画像は付ける): "
              f"{'/'.join(flagged[:20])}")

    filled = 0
    dropped = []
    for r in todo:
        ok = [c for c in name_cands[r["original"]] if c[0] in good]
        if not ok:
            # 全候補が昆虫綱に到達しない = 昆虫の目の配下に誤リンクされた別物
            dropped.append(r["original"])
            continue
        wd_qid, img = ok[0]
        r["wikidata"] = wd_qid
        r["image"], r["image_page"] = commons_urls(img)
        filled += 1
    if dropped:
        print(f"混入として画像を付けなかった和名: {len(dropped)}件 "
              f"{'/'.join(dropped[:20])}")

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    have = sum(1 for r in rows if r["image"] and not is_class_image(r["image"]))
    print(f"画像を付与: +{filled} (計 {have}/{len(rows)}行に実写画像 "
          f"= {have / len(rows) * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
