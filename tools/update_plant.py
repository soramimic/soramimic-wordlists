#!/usr/bin/env python3
"""plant.csv(植物の和名)に未収録の種を追記する(既存行は書き換えない)。

出典: Wikidata(taxon, rank=種 Q7432, 日本語ラベル)。ライセンスは CC0。
sekitsui.csv(脊椎動物)と同じ設計。和名(surface)がそのまま読み
(pronunciation)になるので読み抽出は不要。日本語ラベルがカタカナのものだけを
対象にする。

- `class` 列に大分類(双子葉/単子葉/裸子植物/シダ植物/コケ植物/藻類)を持たせる。
  被子植物は数十万種と巨大で一括クエリすると WDQS がタイムアウトするため、
  **目(order)ごとに分割**して取得する。被子植物の目一覧は実行時に Wikidata から
  取得し、単子葉植物 Q78961 配下の目を「単子葉」、それ以外の被子植物の目を
  「双子葉」に分類する(双子葉は多系統だが、伝統的な2分類として運用)
- 非被子植物(裸子/シダ/コケ/藻類)は正式な門・綱の QID を直接指定して取得する。
  コケ・藻類は非公式グループ(bryophyte Q29993 / algae Q37868)が P171 の親
  タクソンにならないため、門ごと(蘚類/苔類/ツノゴケ類、紅藻/緑藻/褐藻/珪藻/
  車軸藻)に分けて束ねる
- 化石種・絶滅種(rank=種で登録されているもの)も対象に含め、`extinct` 列
  (yes/no)で区別する。判定は sekitsui と同じ(IUCN絶滅/野生絶滅、または化石
  タクソン Q23038290)
- **既存行の埋まっている値は劣化させない**: 目ごとの分割クエリの取りこぼしや
  Wikidata側のラベル改名(例 ユーカリ→ユーカリノキ)で当回の取得から名前が落ちる
  ことがあるため、既存行の class は「今回実データが取れたとき」だけ更新し、
  取れなければ既存値(NA含む)を保つ。extinct は no→yes の一方向のみ更新する
- **動物の混入をガードする**: Wikidata の系統樹(P171)には稀に界をまたぐ誤リンク
  があり、昆虫が被子植物の目の配下として引けてしまう(実例: ヘビトンボ
  Q2481303)。新規追加候補の taxon QID について上位タクソン(P171*)を引き、
  動物界 Q729 に到達するものは追加しない
- **動物界に到達しない混入は EXCLUDED で恒久除外する**: 植物の taxon に動物の
  日本語ラベルが付いている場合や、動物の taxon の親が異物同名の植物・藻類の属に
  なっている場合は上のガードをすり抜ける(実例: セモンジンガサハムシ、
  ミクロディクティオン・シニクム)。CSV から消すだけでは翌回に再追加されるため、
  EXCLUDED に理由付きで並べる

usage: python3 tools/update_plant.py
"""

import csv
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import sparql, write_csv_no_trailing_newline

CSV_PATH = Path(__file__).resolve().parent.parent / "plant.csv"

SPECIES = "wd:Q7432"   # taxon rank = 種
ORDER = "wd:Q36602"    # taxon rank = 目
ANGIOSPERM = "Q25314"  # 被子植物
MONOCOTS = "Q78961"    # 単子葉植物
ANIMALIA = "Q729"      # 動物界(誤リンク混入の判定用)

# 非被子植物: 正式な門・綱QID -> class列の大分類。非公式グループ(コケ植物
# Q29993 / 藻類 Q37868)は P171 の親にならないので門ごとに分ける
CLADES = {
    "Q133712": "裸子植物",   # 裸子植物 Gymnospermae
    "Q178249": "シダ植物",   # シダ植物 Pteridophyta
    # ヒカゲノカズラ植物(小葉植物) Lycopodiophyta。Wikidata では Pteridophyta
    # Q178249 の配下に置かれているので現状は上の行と重複するが、将来の再編で
    # 外れたときの取りこぼしを防ぐために明示しておく
    # (旧 Q157819 は Valeriana officinalis(セイヨウカノコソウ)を指す誤りだった)
    "Q215370": "シダ植物",   # 小葉植物 Lycopodiophyta
    "Q25347": "コケ植物",    # 蘚類 Bryophyta
    "Q189808": "コケ植物",   # 苔類 Marchantiophyta
    "Q191156": "コケ植物",   # ツノゴケ類 Anthocerotophyta
    "Q103169": "藻類",       # 紅藻 Rhodophyta
    "Q264543": "藻類",       # 緑藻 Chlorophyta
    "Q184573": "藻類",       # 褐藻 Phaeophyceae
    "Q9642991": "藻類",      # 珪藻 Bacillariophyta
    "Q133219": "藻類",       # 車軸藻 Charophyta
}

# 対象外にする和名(CSV の original と同じキー)。動物界ガード(animal_taxa)は
# 「P171 を辿って動物界 Q729 に到達する」ものしか落とせないので、次の2種類の
# 上流不整合はすり抜ける。放置すると毎回の自動更新で再追加されるため恒久除外する。
#   1. Wikidata 側で植物の taxon に動物の日本語ラベル/sitelink が付いている
#   2. 動物の taxon の親タクソンが異物同名(homonym)の植物・藻類の属になっていて、
#      系統を辿っても動物界に到達しない
# 増やすときは「その和名が指す実体が植物・藻類か」を基準にし、和名が植物と動物で
# 同音異義になっているだけのもの(スギ/サワラ/ハス等)は**残す**こと。
EXCLUDED = {
    # ハムシ科の昆虫 Aspidomorpha transparipennis。Wikidata では植物
    # Senna versicolor (Q15537572) に ja ラベルと ja Wikipedia の
    # 「セモンジンガサハムシ」が誤って付いており、植物として引けてしまう
    "セモンジンガサハムシ",
    # カンブリア紀の葉足動物 Microdictyon sinicum (Q15104318)。化石属
    # Microdictyon が緑藻の属 Microdictyon と異物同名で、Wikidata では
    # 緑藻側(シオグサ目)の配下に置かれているため藻類として引けてしまう
    "ミクロディクティオン・シニクム",
}

KATAKANA = re.compile(r"^[ァ-ヶー・]+$")
UNKNOWN = "NA"          # 分類が引けなかった既存行の class
# 収集総数がこれを下回ったら取得失敗とみなして中断する(妥当性ガード)。
# 実測は被子植物 6,025 + 裸子/シダ/コケ/藻類 で計 約6,500種
MIN_TOTAL = 4000


def fetch_orders(parent: str) -> set:
    """parent(被子植物/単子葉)配下の rank=目 の QID 集合。"""
    query = f"""
SELECT DISTINCT ?o WHERE {{
  ?o wdt:P171* wd:{parent} ; wdt:P105 {ORDER} .
}}"""
    data = sparql(query)
    return {b["o"]["value"].rsplit("/", 1)[-1]
            for b in data["results"]["bindings"]}


def fetch_taxa(qid: str) -> dict:
    """QID配下の種(カタカナ和名) -> (絶滅フラグ(bool), taxon QID集合)。絶滅は
    IUCN(P141)が絶滅種/野生絶滅、または instance of(P31)が化石タクソンのいずれか
    (sekitsui.update_sekitsui.fetch_taxa と同じ判定)。QID は動物混入ガード
    (animal_taxa)で使う。"""
    query = f"""
SELECT DISTINCT ?t ?l (BOUND(?ext) AS ?extinct) WHERE {{
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
        if not KATAKANA.match(name):
            continue
        ext = b["extinct"]["value"] == "true"
        prev_ext, qids = result.get(name, (False, set()))
        qids.add(b["t"]["value"].rsplit("/", 1)[-1])
        result[name] = (prev_ext or ext, qids)
    return result


def animal_taxa(qids: list) -> set:
    """与えた taxon QID のうち、P171 を辿ると動物界(Q729)に到達するものを返す。

    Wikidata の系統樹には稀に界をまたぐ誤リンクがあり、昆虫が被子植物の目の配下
    として引けてしまう(実例: ヘビトンボ Q2481303 の上位が Ranunculales/被子植物
    まで繋がっている)。新規追加候補だけに絞って確認するので件数は小さい。

    上位タクソンを列挙して Python 側で判定する。`?t wdt:P171* wd:Q729` と直接
    書くと WDQS が動物界側から降りる走査になりタイムアウトする。"""
    bad = set()
    for i in range(0, len(qids), 100):
        values = " ".join(f"wd:{q}" for q in qids[i:i + 100])
        data = sparql(f"""
SELECT DISTINCT ?t ?a WHERE {{
  VALUES ?t {{ {values} }}
  ?t wdt:P171* ?a .
}}""")
        for b in data["results"]["bindings"]:
            if b["a"]["value"].rsplit("/", 1)[-1] == ANIMALIA:
                bad.add(b["t"]["value"].rsplit("/", 1)[-1])
        time.sleep(1)
    return bad


def main() -> int:
    # 被子植物の目を実行時に取得し、単子葉/双子葉に振り分ける
    monocot_orders = fetch_orders(MONOCOTS)
    all_orders = fetch_orders(ANGIOSPERM)
    print(f"被子植物の目: {len(all_orders)}(うち単子葉 {len(monocot_orders)})")

    # (QID, class) の取得対象リスト
    targets = []
    for o in sorted(all_orders):
        targets.append((o, "単子葉" if o in monocot_orders else "双子葉"))
    targets.extend(CLADES.items())

    name_cat = {}   # カタカナ和名 -> 大分類(先勝ち)
    name_ext = {}   # カタカナ和名 -> 絶滅フラグ(いずれかで絶滅なら絶滅)
    name_qids = {}  # カタカナ和名 -> taxon QID集合(動物混入ガード用)
    for qid, cat in targets:
        taxa = fetch_taxa(qid)
        for n, (e, qs) in taxa.items():
            name_cat.setdefault(n, cat)
            name_ext[n] = name_ext.get(n, False) or e
            name_qids.setdefault(n, set()).update(qs)
        print(f"{cat}({qid}): カタカナ和名 {len(taxa)}, "
              f"うち絶滅 {sum(e for e, _ in taxa.values())}")
        time.sleep(1)  # WDQSへの連続アクセスを避ける(取得対象は70件超)

    if len(name_cat) < MIN_TOTAL:
        print(f"error: implausible taxa count: {len(name_cat)}", file=sys.stderr)
        return 1

    def ext_str(name: str) -> str:
        return "yes" if name_ext.get(name) else "no"

    if CSV_PATH.exists():
        with CSV_PATH.open(encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            old_rows = list(reader)
            cols = list(reader.fieldnames or [])
    else:
        old_rows = []
        cols = ["id", "original", "surface", "pronunciation", "class", "extinct"]
    na = kept = 0
    for r in old_rows:
        # 既存行は「今回実データが取れたときだけ」更新する。取れなかった名前
        # (目ごとの分割クエリの取りこぼし・Wikidata側のラベル改名で落ちうる)は
        # 既存値を保持し、既に埋まっている分類を NA に劣化させない
        cat = name_cat.get(r["original"])
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
    next_id = (max(int(r["id"]) for r in old_rows) + 1) if old_rows else 0

    # 新規追加候補から、系統樹の誤リンクで拾ってしまった動物を除外する
    candidates = sorted(name_cat.keys() - existing - EXCLUDED)
    hit = name_cat.keys() & EXCLUDED
    stale = sorted(EXCLUDED - hit)
    if stale:
        # ラベル改名等で除外が効かなくなった可能性がある(再混入に気付けるように)
        print(f"注意: EXCLUDED に未ヒットの項目 {len(stale)}件: {'/'.join(stale)}")
    cand_qids = sorted({q for n in candidates for q in name_qids.get(n, ())})
    bad_qids = animal_taxa(cand_qids) if cand_qids else set()
    # 和名に複数のtaxonがぶら下がる場合は、全てが動物到達のときだけ除外する
    dropped = [n for n in candidates
               if name_qids.get(n) and not (name_qids[n] - bad_qids)]
    candidates = [n for n in candidates if n not in set(dropped)]
    if dropped:
        print(f"動物混入として除外: {len(dropped)}件 {'/'.join(dropped[:20])}")

    added = []
    for name in candidates:
        row = {column: "" for column in cols}
        row.update({"id": str(next_id), "original": name, "surface": name,
                    "pronunciation": name, "class": name_cat[name],
                    "extinct": ext_str(name)})
        added.append(row)
        next_id += 1

    write_csv_no_trailing_newline(CSV_PATH, cols, old_rows + added)
    print(f"plant.csv: +{len(added)}種 (計 {len(old_rows) + len(added)}行), "
          f"既存の分類不明(NA) {na}行, 今回未取得だが既存分類を保持 {kept}行, "
          f"絶滅 {sum(1 for n in name_cat if name_ext.get(n))}種")
    return 0


if __name__ == "__main__":
    sys.exit(main())
