#!/usr/bin/env python3
"""sekitsui.csv(脊椎動物の和名)に未収録の種を追記する(既存行は書き換えない)。

出典: Wikidata(taxon, rank=種 Q7432, 日本語ラベル)。ライセンスは CC0。

- 和名(surface)がそのまま読み(pronunciation)になるので、人名リストのような
  読み抽出は不要。日本語ラベルがカタカナのものだけを対象にする
- `class` 列に大分類(魚類/両生類/爬虫類/鳥類/哺乳類)を持たせる。魚類は分割
  クエリの3綱(条鰭類・軟骨魚類・無顎類)をまとめて「魚類」とする。既存行にも
  Wikidataから分類を引いて付与し、引けなかった行は NA とする
- 化石種・絶滅種(rank=種で登録されているもの)も対象に含め、`extinct` 列
  (yes/no)で区別する。判定は IUCNステータス(P141)が絶滅/野生絶滅、または
  instance of(P31)が化石タクソン(Q23038290)のいずれか。既存行にも付与する
- **既存行の埋まっている値は劣化させない**: 分割クエリのタイムアウトや Wikidata
  側のラベル改名で当回の取得から名前が落ちることがあるため、既存行の class は
  「今回実データが取れたとき」だけ更新し、取れなければ既存値(NA含む)を保つ。
  extinct は no→yes の一方向のみ更新する(絶滅シグナルは取りこぼしやすく、
  取りこぼしで yes→no に落とすと情報が失われるため)
- 種ランクの取得から漏れた既存行でも、目・科が既分類行と矛盾なく対応する場合は
  class を補う。総称として収録している一部の語は手動分類で補う
- 脊椎動物 Q25241 を一括クエリすると WDQS がタイムアウトするため、綱ごとに
  分割してクエリする。綱の系統樹は重複しうるが、original 照合で重複排除する

usage: python3 tools/update_sekitsui.py
"""

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sekitsui_overrides import (
    MANUAL_TAXONOMY,
    build_rank_class_maps,
    class_from_ranks,
)
from wpnames import sparql, write_csv_no_trailing_newline

CSV_PATH = Path(__file__).resolve().parent.parent / "sekitsui.csv"

# 綱QID -> class列の大分類。硬骨魚類 Q27207 は系統樹(P171)上で四足動物まで
# 含みうるため使わず、魚類は条鰭類・軟骨魚類・無顎類に分けて「魚類」に束ねる
CLASSES = {
    "Q7377": "哺乳類",
    "Q5113": "鳥類",
    "Q10811": "爬虫類",
    "Q10908": "両生類",
    "Q127282": "魚類",  # 条鰭類
    "Q25371": "魚類",   # 軟骨魚類
    "Q161095": "魚類",  # 無顎類
}
SPECIES = "wd:Q7432"  # taxon rank = 種
KATAKANA = re.compile(r"^[ァ-ヶー・]+$")
# 分類が引けなかった既存行の class
UNKNOWN = "NA"
# 収集総数がこれを下回ったら取得失敗とみなして中断(既存7280に対する下限)
MIN_TOTAL = 5000


def category_for(name: str, fetched: dict[str, str]) -> str | None:
    """取得結果を基本とし、種ランクで拾えない総称は手動分類で補う。"""
    manual = MANUAL_TAXONOMY.get(name, {})
    return manual.get("class") or fetched.get(name)


def fetch_taxa(qid: str) -> dict:
    """綱QID配下の種 -> 絶滅フラグ(bool)。絶滅は IUCN(P141)が絶滅種/野生絶滅、
    または instance of(P31)が化石タクソンのいずれか。"""
    query = f"""
SELECT DISTINCT ?l (BOUND(?ext) AS ?extinct) WHERE {{
  ?t wdt:P171* wd:{qid} ; wdt:P105 {SPECIES} ; rdfs:label ?l .
  FILTER(LANG(?l) = "ja")
  OPTIONAL {{ ?t wdt:P141 ?i . FILTER(?i IN (wd:Q237350, wd:Q239509)) }}
  OPTIONAL {{ ?t wdt:P31 ?f . FILTER(?f = wd:Q23038290) }}
  BIND(COALESCE(?i, ?f) AS ?ext)
}}"""
    data = sparql(query)
    result = {}
    for b in data["results"]["bindings"]:
        name = b["l"]["value"]
        ext = b["extinct"]["value"] == "true"
        # 同名で絶滅/現生が混在したら絶滅を優先(化石種を取りこぼさない)
        result[name] = result.get(name, False) or ext
    return result


def main() -> int:
    name_cat = {}   # カタカナ和名 -> 大分類(先勝ち)
    name_ext = {}   # カタカナ和名 -> 絶滅フラグ(いずれかの綱で絶滅なら絶滅)
    for qid, cat in CLASSES.items():
        taxa = fetch_taxa(qid)
        kata = {n: e for n, e in taxa.items() if KATAKANA.match(n)}
        for n, e in kata.items():
            name_cat.setdefault(n, cat)
            name_ext[n] = name_ext.get(n, False) or e
        print(f"{cat}({qid}): {len(taxa)}種, カタカナ和名 {len(kata)}, "
              f"うち絶滅 {sum(kata.values())}")

    if len(name_cat) < MIN_TOTAL:
        print(f"error: implausible taxa count: {len(name_cat)}", file=sys.stderr)
        return 1

    def ext_str(name: str) -> str:
        return "yes" if name_ext.get(name) else "no"

    reader = csv.DictReader(CSV_PATH.open(encoding="utf-8"))
    old_rows = list(reader)
    rank_classes = build_rank_class_maps(old_rows)
    na = kept = 0
    for r in old_rows:
        # 既存行は「今回実データが取れたときだけ」更新する。取れなかった名前
        # (クエリのタイムアウト分割・Wikidata側のラベル改名で落ちうる)は既存値を
        # 保持し、既に埋まっている分類を NA に劣化させない
        cat = (category_for(r["original"], name_cat)
               or class_from_ranks(r, rank_classes))
        cur = (r.get("class") or "").strip()
        if cat:
            r["class"] = cat
        elif not cur:
            r["class"] = UNKNOWN
        elif cur != UNKNOWN:
            kept += 1
        # 絶滅列は no→yes の一方向のみ。取りこぼしで yes→no に落とさない
        cur_ext = (r.get("extinct") or "").strip()
        if ext_str(r["original"]) == "yes":
            r["extinct"] = "yes"
        elif cur_ext not in ("yes", "no"):
            r["extinct"] = "no"
        if r["class"] == UNKNOWN:
            na += 1
    existing = {r["original"] for r in old_rows}
    next_id = max(int(r["id"]) for r in old_rows) + 1

    added = []
    for name in sorted(name_cat.keys() - existing):
        added.append({"id": str(next_id), "original": name, "surface": name,
                      "pronunciation": name, "class": name_cat[name],
                      "extinct": ext_str(name)})
        next_id += 1

    # 列は実ファイルのヘッダーに追随する(image列等の追加でここが壊れないように。
    # 新規追加行に無い列は空文字で埋められる)
    cols = list(reader.fieldnames)
    write_csv_no_trailing_newline(CSV_PATH, cols, old_rows + added)
    print(f"sekitsui.csv: +{len(added)}種 (計 {len(old_rows) + len(added)}行), "
          f"既存の分類不明(NA) {na}行, 今回未取得だが既存分類を保持 {kept}行, "
          f"絶滅 {sum(1 for n in name_cat if name_ext.get(n))}種")
    return 0


if __name__ == "__main__":
    sys.exit(main())
