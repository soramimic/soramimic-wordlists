#!/usr/bin/env python3
"""sekitsui.csv(脊椎動物の和名)に画像(Wikimedia Commons)を付与する。

update_sekitsui.py と同じく綱QIDごとに Wikidata を引き、各 taxon の
日本語ラベル(=original)と P18(画像)・QID を取得して image/image_page/
wikidata を埋める。人名リストと違い taxon は日本語ラベルが一意な学術和名
なので、enrich_images.py のような同名回避キーワードガードは不要。

- 既存の image が空の行だけ埋める(冪等)。他の列は変更しない。ただし
  apply_class_images.py が入れた分類の概念イメージは実写で上書きする
  (概念イメージ→実写は改善方向なので劣化にあたらない)。
- 脊椎動物 Q25241 を一括で引くと WDQS がタイムアウトするため、綱ごとに
  分割してクエリする(update_sekitsui.py と同じ7綱)。
- WDQS 部分応答ガード: 収集画像数が MIN_TOTAL を下回ったら中断。
- ファイル名はカンマ等を含みうるので必ずURLエンコードして素朴なCSVパーサを守る。

usage: python3 tools/enrich_sekitsui_images.py
"""

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_class_images import is_class_image  # noqa: E402
from wpnames import (commons_urls, sparql,  # noqa: E402
                     write_csv_no_trailing_newline)

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "sekitsui.csv"
# 書き出し列は実ファイルのヘッダーに追随する(order/family等の列追加で
# 列が落ちないように)。この3列だけは無ければ末尾に足す
OWN_COLS = ["image", "image_page", "wikidata"]

# update_sekitsui.py と同じ綱(値は使わないがクエリ対象として列挙)
CLASSES = ["Q7377", "Q5113", "Q10811", "Q10908", "Q127282", "Q25371", "Q161095"]
SPECIES = "wd:Q7432"  # taxon rank = 種
KATAKANA = re.compile(r"^[ァ-ヶー・]+$")
# 収集画像総数がこれを下回ったら WDQS 部分応答とみなして中断
MIN_TOTAL = 500


def fetch_images(qid: str) -> dict[str, tuple[str, str, str]]:
    """綱QID配下の種で P18 を持つもの -> {和名: (wikidata_qid, image, image_page)}。"""
    query = f"""
SELECT DISTINCT ?t ?l ?img WHERE {{
  ?t wdt:P171* wd:{qid} ; wdt:P105 {SPECIES} ; wdt:P18 ?img ; rdfs:label ?l .
  FILTER(LANG(?l) = "ja")
}}"""
    data = sparql(query)
    out: dict[str, tuple[str, str, str]] = {}
    for b in data["results"]["bindings"]:
        name = b["l"]["value"]
        if not KATAKANA.match(name) or name in out:
            continue  # カタカナ和名のみ / 同名は先勝ち
        wd_qid = b["t"]["value"].rsplit("/", 1)[-1]
        image, image_page = commons_urls(b["img"]["value"])
        out[name] = (wd_qid, image, image_page)
    return out


def main() -> int:
    name_img: dict[str, tuple[str, str, str]] = {}
    for qid in CLASSES:
        got = fetch_images(qid)
        for n, v in got.items():
            name_img.setdefault(n, v)  # 綱をまたぐ重複は先勝ち
        print(f"{qid}: 画像付き和名 {len(got)}", flush=True)

    if len(name_img) < MIN_TOTAL:
        print(f"error: implausible image count: {len(name_img)}", file=sys.stderr)
        return 1

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        cols = list(reader.fieldnames)
    cols += [c for c in OWN_COLS if c not in cols]

    filled = 0
    for r in rows:
        for c in cols:
            r.setdefault(c, "")
        cur = r.get("image") or ""
        if cur and not is_class_image(cur):
            continue  # 実写がある行は触らない(冪等)
        hit = name_img.get(r["original"])
        if hit:
            r["wikidata"], r["image"], r["image_page"] = hit
            filled += 1  # 概念イメージだった行は実写に差し替わる

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    have = sum(1 for r in rows if r["image"] and not is_class_image(r["image"]))
    print(f"画像を付与: +{filled} (計 {have}/{len(rows)}行に実写画像)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
