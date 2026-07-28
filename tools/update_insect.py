#!/usr/bin/env python3
"""insect.csv(昆虫の和名)に未収録の種を追記する(既存行は書き換えない)。

出典: Wikidata(taxon, rank=種 Q7432, 日本語ラベル)。ライセンスは CC0。
sekitsui.csv(脊椎動物)/ plant.csv(植物)と同じ設計で、和名(surface)が
そのまま読み(pronunciation)になるので読み抽出は不要。日本語ラベルが
カタカナのものだけを対象にする。

- 対象は **昆虫綱 Insecta Q1390** の配下だけ。クモ・ダニ・ムカデ・エビ等の
  非昆虫節足動物は対象外(将来別リストにする。詳細は ADR 00021)
- `class` 列には**主要な目をまとめた粗い大分類**(甲虫/チョウ/ハチ/ハエ/
  カメムシ/バッタ/トンボ/その他)を入れる。昆虫は目が30以上あって
  そのままでは分類軸として細かすぎるため。定義は `CLASS_BY_ORDER`
- `order` / `family` は目・科の和名(sekitsui と同じ流儀。階級付きの日本語
  別名があればそれ、無ければ日本語ラベル、無ければ学名)。上位タクソンを
  辿る処理は `tools/taxonomy.py` を sekitsui / plant と共用する
- 化石種・絶滅種(rank=種で登録されているもの)も対象に含め、`extinct` 列
  (yes/no)で区別する。判定は sekitsui / plant と同じ(IUCN絶滅/野生絶滅、
  または化石タクソン Q23038290)

### 取得の分割

昆虫綱 Q1390 を一括クエリすると WDQS がタイムアウトする(Wikidata の昆虫
taxon は100万件規模)。**目(order)ごとに分割**して取得する。

- 目の一覧は `?o wdt:P171* wd:Q1390 ; wdt:P105 wd:Q36602` でも取れない
  (Blazegraph が昆虫綱側から降りる走査になりタイムアウトする)ため、
  昆虫綱から P171 の**子を1段ずつ下向きに幅優先**で辿って集める。目より下の
  階級(上科・科・属…)に達したらそこで打ち切る
- 目に達しない枝(上科・科が昆虫綱直下にぶら下がっている等の上流不整合)は
  取りこぼさないよう、打ち切った地点そのものを取得対象に加える(class は
  その目が分からないので「その他」になる)
- **コウチュウ目 Q22671 は目単位でもタイムアウトする**(Wikidata の甲虫は
  40万件超)。取得に失敗した対象は自動的に子タクソンへ再帰的に分割する。
  待っても通らないクエリなのでリトライは1回で打ち切る(`sparql(retries=1)`)

### 同名異義(homonym)対策

昆虫の和名は脊椎動物・植物と衝突するものが多い(カマキリ=昆虫だが魚
アユカケの別名でもある / トンボ / セミ / ミノムシ 等)。plant と同じく
**クエリの起点を昆虫綱側に閉じる**ことで一次的に防ぐ。和名から QID を
引いてから界を判定する順序にすると、同名の魚や植物を先に拾ってしまう。

そのうえで、書き込み前に新規候補の上位タクソンを引き、**昆虫綱 Q1390 に
到達しない**ものを追加しない。脊椎動物 Q25241 / 植物界 Q756 にも到達する
taxon は**落とさずに報告だけする**(plant の動物界ガードと違い、昆虫では
この検査が逆向きになって本物の昆虫を落とすため。詳細は `screen_taxa`)。

### 既存行の扱い(ADR 00014)

分割クエリの取りこぼしや Wikidata 側のラベル改名で当回の取得から名前が
落ちることがあるため、既存行の class / order / family は「今回実データが
取れたとき」だけ更新し、取れなければ既存値(NA・空を含む)を保つ。
extinct は no→yes の一方向のみ更新する。

usage: python3 tools/update_insect.py [--refresh]
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import taxonomy  # noqa: E402
from wpnames import sparql, sparql_post, write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "insect.csv"
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
ORDERS_CACHE = CACHE_DIR / "insect_orders.json"
TAXONOMY_CACHE = CACHE_DIR / "insect_taxonomy.json"

INSECTA = "Q1390"       # 昆虫綱 Insecta
VERTEBRATA = "Q25241"   # 脊椎動物(誤リンク混入の判定用)
PLANTAE = "Q756"        # 植物界(誤リンク混入の判定用)
SPECIES = "wd:Q7432"    # taxon rank = 種
RANK_ORDER = "Q36602"   # taxon rank = 目
RANK_FAMILY = "Q35409"  # taxon rank = 科

# 目より下の階級(P105 の QID)。下向きBFSはここに達したら打ち切り、その
# ノード自体を取得対象にする(降りると属・種まで展開してクエリ数が爆発する)。
# Wikidata の昆虫は階級付けが一貫しておらず、ゴキブリ目 Blattodea Q25309 が
# 「亜目」、シロアリ Isoptera Q546583 が「上科の上(epifamily)」になっている
# ような例が多いので、目だけでなく目より下の階級すべてを打ち切り点にする。
# 無階級のクレード(rank が空、または Q713623 clade)は打ち切らずに展開する
BELOW_ORDER_RANKS = {
    "Q5867959",    # 亜目 suborder(ゴキブリ目 Blattodea などがここ)
    "Q2889003",    # 下目 infraorder
    "Q10296147",   # epifamily(シロアリ Isoptera がここ)
    "Q2136103",    # 上科 superfamily
    "Q35409",      # 科 family
    "Q164280",     # 亜科 subfamily
    "Q227936",     # 族 tribe
    "Q3965313",    # 亜族 subtribe
    "Q34740",      # 属 genus
    "Q3238261",    # 亜属 subgenus
    "Q112082101",  # 生痕属 ichnogenus
    "Q7432",       # 種 species
    "Q68947",      # 亜種 subspecies
}

# 大分類(class列)。昆虫は目が30以上あり、そのまま class にすると細かすぎる
# ので、種数・知名度ともに大きい現生7目だけを個別の区分に立て、残りは
# 「その他」にまとめる(化石のみの目もすべて「その他」)。区分名は目の和名
# ではなく通称にする(「コウチュウ目」より「甲虫」の方が利用側で扱いやすい)
CLASS_BY_ORDER = {
    "Q22671": "甲虫",     # コウチュウ目 Coleoptera
    "Q28319": "チョウ",   # チョウ目 Lepidoptera(ガを含む)
    "Q22651": "ハチ",     # ハチ目 Hymenoptera(アリを含む)
    "Q25312": "ハエ",     # ハエ目 Diptera(カ・アブを含む)
    "Q26371": "カメムシ",  # カメムシ目 Hemiptera(セミ・アブラムシを含む)
    "Q167810": "バッタ",  # バッタ目 Orthoptera(コオロギ・キリギリスを含む)
    "Q25375": "トンボ",   # トンボ目 Odonata
}
OTHER = "その他"        # 上記以外の目(カマキリ目・ゴキブリ目・化石の目など)
UNKNOWN = "NA"          # 分類が引けなかった既存行の class

# 対象外にする和名(CSV の original と同じキー)。昆虫綱ガードをすり抜ける
# 混入(昆虫の taxon に非昆虫の日本語ラベルが誤って付いている等)を恒久除外
# する。CSV から消すだけでは翌回の自動更新で再追加されるため。
# 増やすときは「その和名が指す実体が昆虫か」を基準にし、和名が昆虫と
# 脊椎動物・植物で同音異義になっているだけのもの(カマキリ・トンボ等)は
# **残す**こと(昆虫側の taxon が実在するなら昆虫の和名として正しい)。
EXCLUDED: set[str] = set()

KATAKANA = re.compile(r"^[ァ-ヶー・]+$")
# 収集総数がこれを下回ったら取得失敗とみなして中断する(妥当性ガード)。
# 実測 1,980種(2026-07-28。チョウ目656 / コウチュウ目593 / カメムシ目210 /
# ハチ目144 / トンボ目97 / バッタ目97 / ハエ目86 / その他97)。大きい目が
# 1つ丸ごと落ちたら気付ける水準に置く(チョウ目かコウチュウ目が落ちると下回る)
MIN_TOTAL = 1500
# 1つの取得対象を子タクソンに分割する最大の深さ(コウチュウ目対策)
MAX_SPLIT_DEPTH = 5
# 分割時のWDQSリトライ回数。重すぎて必ず落ちるクエリを待っても無駄なので短い
SPLIT_RETRIES = 1


def qid_of(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


# --- 取得対象(目)の列挙 --------------------------------------------------

def fetch_children(qids: list[str]) -> dict[str, dict]:
    """P171 の直接の子 -> {rank, ja, sci}。"""
    values = " ".join("wd:" + q for q in qids)
    data = sparql_post(f"""
SELECT ?c ?rank ?ja ?sci WHERE {{
  VALUES ?p {{ {values} }}
  ?c wdt:P171 ?p .
  OPTIONAL {{ ?c wdt:P105 ?rank }}
  OPTIONAL {{ ?c rdfs:label ?ja . FILTER(LANG(?ja) = "ja") }}
  OPTIONAL {{ ?c wdt:P225 ?sci }}
}}""")
    out: dict[str, dict] = {}
    for b in data["results"]["bindings"]:
        n = out.setdefault(qid_of(b["c"]["value"]),
                           {"rank": "", "ja": "", "sci": ""})
        if "rank" in b and not n["rank"]:
            n["rank"] = qid_of(b["rank"]["value"])
        if "ja" in b and not n["ja"]:
            n["ja"] = b["ja"]["value"]
        if "sci" in b and not n["sci"]:
            n["sci"] = b["sci"]["value"]
    return out


def fetch_targets(refresh: bool = False) -> dict[str, dict]:
    """昆虫綱から下向きに幅優先で辿り、取得対象 QID -> {rank, ja, sci} を返す。

    `?o wdt:P171* wd:Q1390 ; wdt:P105 wd:Q36602`(plant の fetch_orders と
    同じ形)は昆虫では必ずタイムアウトするので、子を1段ずつ降りて集める。
    rank=目 に達したらそこが取得対象。目より下の階級に達した枝は上流不整合
    なので、その地点を取得対象に加えて打ち切る(取りこぼさないため)。"""
    if ORDERS_CACHE.exists() and not refresh:
        return json.loads(ORDERS_CACHE.read_text(encoding="utf-8"))

    targets: dict[str, dict] = {}
    seen = {INSECTA}
    frontier = {INSECTA}
    for depth in range(16):
        got = fetch_children(sorted(frontier))
        nxt = set()
        for c, n in got.items():
            if c in seen:
                continue
            seen.add(c)
            if n["rank"] == RANK_ORDER or n["rank"] in BELOW_ORDER_RANKS:
                targets[c] = n   # 目、または目に達しない枝の打ち切り地点
            else:
                nxt.add(c)       # 無階級のクレード・亜綱・下綱・上目など
        print(f"目の探索 depth {depth}: 子 {len(got)}, 取得対象 {len(targets)}, "
              f"次の階層 {len(nxt)}", flush=True)
        if not nxt:
            break
        frontier = nxt
        time.sleep(1)
    else:
        print("warning: 目の探索が深さ上限に達した", file=sys.stderr)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ORDERS_CACHE.write_text(json.dumps(targets, ensure_ascii=False),
                            encoding="utf-8")
    return targets


# --- 種の取得 --------------------------------------------------------------

def _taxa_query(qid: str) -> str:
    return f"""
SELECT DISTINCT ?t ?l (BOUND(?ext) AS ?extinct) WHERE {{
  ?t wdt:P171* wd:{qid} ; wdt:P105 {SPECIES} ; rdfs:label ?l .
  FILTER(LANG(?l) = "ja")
  OPTIONAL {{ ?t wdt:P141 ?i . FILTER(?i IN (wd:Q237350, wd:Q239509)) }}
  OPTIONAL {{ ?t wdt:P31 ?f . FILTER(?f = wd:Q23038290) }}
  BIND(COALESCE(?i, ?f) AS ?ext)
}}"""


def try_sparql(query: str):
    """重いクエリ用。通らなければ None を返す(呼び出し側が対象を分割する)。

    **429(Too Many Requests)のときだけ待って1回だけ再試行する**。レート制限は
    待てば解けるので、これを「重すぎて通らないクエリ」と取り違えて分割すると
    クエリ数が増えて逆効果になる。一方 504(Gateway Timeout)は待っても通らない
    ので、即座に分割へ回して時間を無駄にしない。"""
    try:
        return sparql(query, retries=SPLIT_RETRIES)
    except RuntimeError as ex:
        if "429" not in str(ex):
            return None
    print("  レート制限のため60秒待って再試行する", flush=True)
    time.sleep(60)
    try:
        return sparql(query, retries=SPLIT_RETRIES)
    except RuntimeError:
        return None


def fetch_taxa(qid: str, depth: int = 0) -> dict[str, tuple[bool, set[str]]]:
    """QID配下の種(カタカナ和名) -> (絶滅フラグ, taxon QID集合)。

    重すぎてタイムアウトする対象(コウチュウ目 Q22671 など)は、直接の子
    タクソンに分割して再帰的に取得する。"""
    data = try_sparql(_taxa_query(qid))
    if data is None:
        if depth >= MAX_SPLIT_DEPTH:
            print(f"warning: {qid} の取得を諦めた(分割上限)", file=sys.stderr)
            return {}
        kids = sorted(fetch_children([qid]))
        print(f"  {qid} はタイムアウト: 子 {len(kids)}件に分割(深さ {depth + 1})",
              flush=True)
        merged: dict[str, tuple[bool, set[str]]] = {}
        for i, k in enumerate(kids, 1):
            for n, (e, qs) in fetch_taxa(k, depth + 1).items():
                pe, pq = merged.get(n, (False, set()))
                merged[n] = (pe or e, pq | qs)
            if i % 20 == 0:
                print(f"  {qid}: 分割 {i}/{len(kids)} (和名 {len(merged)})",
                      flush=True)
            time.sleep(1)
        return merged

    result: dict[str, tuple[bool, set[str]]] = {}
    for b in data["results"]["bindings"]:
        name = b["l"]["value"]
        if not KATAKANA.match(name):
            continue
        ext = b["extinct"]["value"] == "true"
        prev_ext, qids = result.get(name, (False, set()))
        qids.add(qid_of(b["t"]["value"]))
        result[name] = (prev_ext or ext, qids)
    return result


# --- 混入ガード ------------------------------------------------------------

def screen_taxa(qids: list[str]) -> tuple[set[str], set[str]]:
    """(昆虫として採用してよい taxon QID, 界をまたぐ誤リンクを持つ QID) を返す。

    上位タクソン(P171*)を列挙して Python 側で判定する。`?t wdt:P171* wd:Q1390`
    と直接書くと WDQS が昆虫綱側から降りる走査になりタイムアウトする
    (update_plant.animal_taxa と同じ理由)。

    採用条件は **昆虫綱 Q1390 に到達すること**。取得の起点を昆虫綱配下に閉じて
    いるので通常は全件が通るが、`fetch_targets` のキャッシュが古い・Wikidata の
    再編で対象が昆虫綱から外れた、といった場合にここで気付ける。

    **脊椎動物 Q25241 / 植物界 Q756 にも到達する taxon は「落とさずに報告する」**。
    plant では同じ形の検査(動物界に到達したら落とす)が正しく効くが、昆虫では
    逆向きになって本物の昆虫を落としてしまうため。実例: ヘビトンボ
    Protohermes grandis (Q2481303) は Corydalidae→Megaloptera→昆虫綱と正しく
    繋がっている本物の昆虫だが、Wikidata に Papaveraceae→Ranunculales→植物界
    という誤った親も付いている(ADR 00014 が plant 側の混入元として挙げた
    まさにその1件)。「昆虫綱にも植物界にも到達する」だけでは、本物の昆虫に
    余計な親が付いた場合と、非昆虫が昆虫の配下に誤リンクされた場合を区別
    できないので、自動では落とさず EXCLUDED での判断に回す。"""
    ok: set[str] = set()
    crossed: set[str] = set()
    for i in range(0, len(qids), 100):
        chunk = qids[i:i + 100]
        values = " ".join(f"wd:{q}" for q in chunk)
        data = sparql_post(f"""
SELECT DISTINCT ?t ?a WHERE {{
  VALUES ?t {{ {values} }}
  ?t wdt:P171* ?a .
}}""")
        anc: dict[str, set[str]] = {q: set() for q in chunk}
        for b in data["results"]["bindings"]:
            anc.setdefault(qid_of(b["t"]["value"]), set()).add(qid_of(b["a"]["value"]))
        for q, a in anc.items():
            if INSECTA in a:
                ok.add(q)
            if a & {VERTEBRATA, PLANTAE}:
                crossed.add(q)
        print(f"  混入ガード {min(i + 100, len(qids))}/{len(qids)}", flush=True)
        time.sleep(1)
    return ok, crossed


# --- 目・科の和名 ----------------------------------------------------------

def resolve_taxonomy(qids: list[str], refresh: bool) -> dict[str, tuple[str, str]]:
    """taxon QID -> (目の和名, 科の和名)。sekitsui / plant と同じ tools/taxonomy.py
    で親(P171)を1段ずつ辿る。候補は数千件なので数分で終わる。"""
    cache = {"nodes": {}, "labels": {}} if refresh \
        else taxonomy.load_cache(TAXONOMY_CACHE)
    taxonomy.crawl(set(qids), cache, TAXONOMY_CACHE, stop_rank=RANK_ORDER)
    taxonomy.add_rank_aliases(cache, TAXONOMY_CACHE,
                              {RANK_ORDER: "目", RANK_FAMILY: "科"})
    nodes = cache["nodes"]
    out = {}
    for q in qids:
        o, f = taxonomy.resolve(q, nodes, [RANK_ORDER, RANK_FAMILY])
        out[q] = (o, f)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="目の一覧・分類木のキャッシュを無視して引き直す")
    args = ap.parse_args()

    targets = fetch_targets(args.refresh)
    print(f"取得対象 {len(targets)}件"
          f"(うち大分類を立てた目 {len(CLASS_BY_ORDER)}件)")

    name_cat: dict[str, str] = {}    # カタカナ和名 -> 大分類(主要目が先勝ち)
    name_ext: dict[str, bool] = {}   # カタカナ和名 -> 絶滅フラグ
    name_qids: dict[str, set[str]] = {}  # カタカナ和名 -> taxon QID集合
    # 主要7目を先に引き、「その他」に落ちる目より優先させる(系統樹の重複で
    # 同じ和名が複数の対象から引けたときの先勝ちを決定的にするため)
    ordered = sorted(targets, key=lambda q: (q not in CLASS_BY_ORDER, q))
    for n_done, qid in enumerate(ordered, 1):
        cat = CLASS_BY_ORDER.get(qid, OTHER)
        taxa = fetch_taxa(qid)
        for n, (e, qs) in taxa.items():
            name_cat.setdefault(n, cat)
            name_ext[n] = name_ext.get(n, False) or e
            name_qids.setdefault(n, set()).update(qs)
        info = targets[qid]
        print(f"[{n_done}/{len(ordered)}] {cat} {info.get('sci') or qid} "
              f"({info.get('ja')}): カタカナ和名 {len(taxa)}, "
              f"うち絶滅 {sum(e for e, _ in taxa.values())} / 累計 {len(name_cat)}",
              flush=True)
        time.sleep(1)  # WDQSへの連続アクセスを避ける

    if len(name_cat) < MIN_TOTAL:
        print(f"error: implausible taxa count: {len(name_cat)}", file=sys.stderr)
        return 1

    def ext_str(name: str) -> str:
        return "yes" if name_ext.get(name) else "no"

    cols = ["id", "original", "surface", "pronunciation", "class", "extinct",
            "order", "family", "image", "image_page", "wikidata"]
    if CSV_PATH.exists():
        with CSV_PATH.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            old_rows = [dict(r) for r in reader]
            cols = list(reader.fieldnames)
    else:
        old_rows = []
    existing = {r["original"] for r in old_rows}

    # 新規追加候補から、系統樹の誤リンクで拾ってしまった非昆虫を除外する
    candidates = sorted(name_cat.keys() - existing - EXCLUDED)
    stale = sorted(EXCLUDED - name_cat.keys())
    if stale:
        # ラベル改名等で除外が効かなくなった可能性がある(再混入に気付けるように)
        print(f"注意: EXCLUDED に未ヒットの項目 {len(stale)}件: {'/'.join(stale)}")
    cand_qids = sorted({q for n in candidates for q in name_qids.get(n, ())})
    print(f"混入ガード: 候補 {len(candidates)}件 / taxon QID {len(cand_qids)}件")
    good_qids, crossed = screen_taxa(cand_qids) if cand_qids else (set(), set())
    flagged = sorted(n for n in candidates if name_qids.get(n, set()) & crossed)
    if flagged:
        # 落とさずに報告する(本物の昆虫に誤った親が付いているだけのことが多い。
        # 実体が昆虫でなければ EXCLUDED に足す)
        print(f"注意: 界をまたぐ誤リンクを持つ和名 {len(flagged)}件(採用はする。"
              f"実体が昆虫でなければ EXCLUDED へ): {'/'.join(flagged[:20])}")
    dropped = [n for n in candidates if not (name_qids.get(n, set()) & good_qids)]
    candidates = [n for n in candidates if n not in set(dropped)]
    if dropped:
        print(f"非昆虫として除外: {len(dropped)}件 {'/'.join(dropped[:20])}")

    # 目・科の和名。既存行の分も含めて、QIDが分かっている名前だけ引く
    # (和名から逆引きすると同名の魚・植物の科を拾うため引かない)
    known = {r["original"] for r in old_rows} | set(candidates)
    pick: dict[str, str] = {}
    for n in sorted(known):
        qs = sorted(name_qids.get(n, set()) & good_qids) \
            or sorted(name_qids.get(n, set()))
        if qs:
            pick[n] = qs[0]
    print(f"目・科の解決: {len(pick)}件のtaxonを対象に上位タクソンを辿る")
    taxa_labels = resolve_taxonomy(sorted(set(pick.values())), args.refresh)
    name_taxo = {n: taxa_labels.get(q, ("", "")) for n, q in pick.items()}

    # 既存行は「今回実データが取れたときだけ」更新する(ADR 00014)
    na = kept = 0
    for r in old_rows:
        cat = name_cat.get(r["original"])
        cur = (r.get("class") or "").strip()
        if cat:
            r["class"] = cat
        elif not cur:
            r["class"] = UNKNOWN
        elif cur != UNKNOWN:
            kept += 1
        o, fam = name_taxo.get(r["original"], ("", ""))
        if o:
            r["order"] = o
        if fam:
            r["family"] = fam
        # 絶滅列は no→yes の一方向のみ。取りこぼしで yes→no に落とさない
        cur_ext = (r.get("extinct") or "").strip()
        if ext_str(r["original"]) == "yes":
            r["extinct"] = "yes"
        elif cur_ext not in ("yes", "no"):
            r["extinct"] = "no"
        if r["class"] == UNKNOWN:
            na += 1

    next_id = (max(int(r["id"]) for r in old_rows) + 1) if old_rows else 0
    added = []
    for name in candidates:
        o, fam = name_taxo.get(name, ("", ""))
        added.append({"id": str(next_id), "original": name, "surface": name,
                      "pronunciation": name, "class": name_cat[name],
                      "extinct": ext_str(name), "order": o, "family": fam})
        next_id += 1

    for r in old_rows + added:
        for c in cols:
            r.setdefault(c, "")
    write_csv_no_trailing_newline(CSV_PATH, cols, old_rows + added)
    breakdown = {}
    for r in old_rows + added:
        breakdown[r["class"]] = breakdown.get(r["class"], 0) + 1
    print(f"insect.csv: +{len(added)}種 (計 {len(old_rows) + len(added)}行), "
          f"既存の分類不明(NA) {na}行, 今回未取得だが既存分類を保持 {kept}行, "
          f"絶滅 {sum(1 for n in name_cat if name_ext.get(n))}種")
    print("大分類: " + ", ".join(f"{k} {v}" for k, v in
                                 sorted(breakdown.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
