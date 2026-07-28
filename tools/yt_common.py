"""youtuber.csv 自動更新の共通処理(詳細は docs/adr/00011, 00012)。

出典: Wikidata(職業P106がYouTuber/バーチャルYouTuberで、ja.wikipediaに記事が
ある人物)と、Wikipedia日本語版記事の冒頭文(CC BY-SA 4.0)。

- YouTuberとVTuberを1ファイルに収録し、category列(youtuber/vtuber)で区別する
- 収録は記事名(=活動名)のみ。本名などの個人情報は取得しない
- 姓名分割できる名前(兎田ぺこら等)は family/given/full、ハンドル型
  (HIKAKIN/キズナアイ等)は full のみ
- 読みはカタカナ。かな名は自身から変換、漢字・ラテン文字名は記事冒頭
  「名前（よみ、」から抽出。機械決定できない名前はスキップして「要確認」に報告
- 既存行の表記・読み・idは書き換えない。自動で行うのは未収録者の追記と
  status の current→former 一方向更新(P2032: 活動終了)のみ
"""

import csv
import os
import pickle
import re
from pathlib import Path

from wpnames import (DISAMBIG, HIRA2KATA, fetch_extracts, parse_person, sparql,
                     write_csv_no_trailing_newline)

COLS = ["id", "original", "surface", "pronunciation", "type",
        "category", "org", "debut_year", "status"]

# かな・カタカナだけのハンドル名(読みが自明)。wpnames.KATAKANA のひらがな込み版
KANA_ONLY = re.compile(r"^[ぁ-ゖァ-ヶー・=＝\s]+$")
# 冒頭カッコ内の読みとして許容する文字
YOMI = r"[ぁ-ゖァ-ヶー・]+"


def assert_occupation(qid: str, must: tuple, must_not: tuple):
    """QIDのja/enラベルに期待キーワードが含まれることを確認するフェイルセーフ。
    QIDの取り違え(別概念の取り込み)をクエリ実行前に検出する。"""
    q = f"""
SELECT ?l WHERE {{ wd:{qid} rdfs:label ?l . FILTER(LANG(?l) IN ("ja", "en")) }}"""
    labels = [b["l"]["value"] for b in sparql(q)["results"]["bindings"]]
    low = [l.lower() for l in labels]
    if not any(any(k.lower() in l for l in low) for k in must) or \
            any(any(k.lower() in l for l in low) for k in must_not):
        raise SystemExit(
            f"error: wd:{qid} のラベル {labels} が期待(must={must}, "
            f"must_not={must_not})と合わない。QIDを確認してください")


def _persons(occ: str, exclude: str = None, extra: str = "") -> dict:
    minus = f"MINUS {{ ?p wdt:P106 wd:{exclude} }}" if exclude else ""
    q = f"""
SELECT ?p ?title WHERE {{
  ?p wdt:P106 wd:{occ} .
  {minus}
  {extra}
  ?a schema:about ?p ; schema:isPartOf <https://ja.wikipedia.org/> ;
     schema:name ?title .
}}"""
    persons = {}
    for b in sparql(q)["results"]["bindings"]:
        qid = b["p"]["value"].rsplit("/", 1)[1]
        persons[qid] = b["title"]["value"]
    return persons


def fetch_persons(occ: str, exclude: str = None,
                  excluded_occs: dict = None) -> dict:
    """QID -> ja記事タイトル(職業P106=occ かつ ja.wikipediaに記事がある人物)。

    excluded_occs(QID -> ラベル)のいずれかを P106 に持つ人物は除外する。
    黙って消えると気付けないので、該当者は名前をログに出す。"""
    persons = _persons(occ, exclude)
    print(f"対象(wd:{occ}): {len(persons)}人(distinct QID)", flush=True)
    if excluded_occs:
        vals = " ".join(f"wd:{q}" for q in sorted(excluded_occs))
        dropped = _persons(occ, exclude,
                           f"VALUES ?bad {{ {vals} }} ?p wdt:P106 ?bad .")
        for qid in dropped:
            persons.pop(qid, None)
        print(f"  除外職業(P106)で除外: {len(dropped)}人: "
              + ", ".join(sorted(dropped.values())), flush=True)
    return persons


def _year(iso: str):
    try:
        return str(int(iso.split("-")[0]))
    except (ValueError, AttributeError, IndexError):
        return None


def fetch_attrs(qids: list) -> dict:
    """QID -> {org, debut_year, status}。P108/P463/P1416(所属)と
    P2031/P2032(活動期間)、P2397(YouTubeチャンネルID)の開始時点(P580)を
    バッチ取得。

    debut_year は P2031(活動開始)を優先し、無ければチャンネル開設年を使う。
    P2031 が入っている人は2割ほどしかいないのに対し、チャンネルIDの P580 は
    多くの項目にあり、YouTuberの「活動開始年」としては十分に近い。"""
    attrs = {}
    for i in range(0, len(qids), 200):
        batch = qids[i:i + 200]
        values = " ".join(f"wd:{q}" for q in batch)
        q = f"""
SELECT ?p (GROUP_CONCAT(DISTINCT ?orgL; SEPARATOR="||") AS ?orgs)
  (MIN(?start) AS ?s) (MAX(?end) AS ?e) (MIN(?chan) AS ?c) WHERE {{
  VALUES ?p {{ {values} }}
  OPTIONAL {{ ?p wdt:P108|wdt:P463|wdt:P1416 ?org .
             ?org rdfs:label ?orgL . FILTER(LANG(?orgL)="ja") }}
  OPTIONAL {{ ?p wdt:P2031 ?start . FILTER(isLiteral(?start)) }}
  OPTIONAL {{ ?p wdt:P2032 ?end . FILTER(isLiteral(?end)) }}
  OPTIONAL {{ ?p p:P2397 ?st . ?st pq:P580 ?chan .
             FILTER NOT EXISTS {{ ?st wikibase:rank wikibase:DeprecatedRank }} }}
}} GROUP BY ?p"""
        for b in sparql(q)["results"]["bindings"]:
            qid = b["p"]["value"].rsplit("/", 1)[1]
            orgs = set()
            for o in b.get("orgs", {}).get("value", "").split("||"):
                # ラベル内のカンマ・引用符はCSVパーサを壊すので除去
                o = o.replace(",", " ").replace('"', "").strip()
                if o:
                    orgs.add(o)
            attrs[qid] = {
                # 出力順をソート固定(WDQSのGROUP_CONCAT順は非決定的)
                "org": "/".join(sorted(orgs)) if orgs else "NA",
                "debut_year": (_year(b.get("s", {}).get("value"))
                               or _year(b.get("c", {}).get("value")) or "NA"),
                "status": "former" if b.get("e", {}).get("value") else "current",
            }
        print(f"  属性取得 {min(i + 200, len(qids))}/{len(qids)}", flush=True)
    return attrs


def parse_entry(title: str, text: str):
    """記事名と冒頭文から (original, [(surface, pronunciation, type), ...]) を
    返す。読みが機械決定できなければ None(要確認)。"""
    name = DISAMBIG.sub("", title)
    text = (text or "").replace("　", " ")
    parsed = parse_person(name, text)
    if parsed:
        f_s, f_y, g_s, g_y, full_s, full_y, _reg = parsed
        original = full_s.replace(" ", "")
        rows = []
        if f_s and f_s != original:
            rows.append((f_s, f_y, "family"))
            rows.append((g_s, g_y, "given"))
        rows.append((original, full_y.replace(" ", ""), "full"))
        return original, rows
    plain = name.replace("　", "").replace(" ", "")
    if KANA_ONLY.match(plain):  # かなハンドル名は自身が読み
        yomi = plain.replace("＝", "・").translate(HIRA2KATA)
        return plain, [(plain, yomi, "full")]
    # 漢字・ラテン文字等のハンドル名: 冒頭「名前（よみ、」「名前（よみ）」から抽出
    lead = text.replace(" ", "")
    m = re.match(re.escape(plain) + r"[（(](" + YOMI + r")[、，,）)]", lead)
    if m:
        yomi = m.group(1).translate(HIRA2KATA)
        return plain, [(plain, yomi, "full")]
    return None


def norm(title: str) -> str:
    """既存 original との照合キー(曖昧回避サフィックス除去+空白除去)。"""
    return DISAMBIG.sub("", title).replace("　", "").replace(" ", "")


def build_list(csv_name: str, specs: list, cache_env: str,
               excluded: set = frozenset(),
               excluded_occs: dict = None) -> int:
    """リストを生成(初回)または追記・status更新(2回目以降)する。

    specs: category ごとの取得仕様
      {category, occ, must, must_not, exclude, guard} の dict のリスト。
    excluded: 収録しないja記事名(norm()済み)の集合。P106の誤登録や、別業種の
      著名人が公式チャンネルを持つだけのケースを恒久的に弾く。
    excluded_occs: 収録しない職業の QID -> ラベル。P106 にこの職業を持つ人物を
      属性ごと弾く。値はラベルの期待キーワード(QID取り違えのフェイルセーフ)。
    """
    csv_path = Path(__file__).resolve().parent.parent / csv_name
    for s in specs:
        assert_occupation(s["occ"], s["must"], s["must_not"])
        if s.get("exclude"):
            assert_occupation(s["exclude"], ("youtuber", "ユーチューバー"), ())
    for qid, label in (excluded_occs or {}).items():
        assert_occupation(qid, (label,), ())

    cache = os.environ.get(cache_env)  # 開発用: 取得結果の pickle キャッシュ先
    if cache and Path(cache).exists():
        with open(cache, "rb") as fh:
            persons_by_cat, attrs, extracts = pickle.load(fh)
        print(f"キャッシュから読み込み: {cache}", flush=True)
    else:
        persons_by_cat = {}
        for s in specs:
            persons = fetch_persons(s["occ"], s.get("exclude"), excluded_occs)
            lo, hi = s["guard"]
            if not lo <= len(persons) <= hi:
                print(f"error: implausible count for {s['category']}: "
                      f"{len(persons)}")
                return 1
            persons_by_cat[s["category"]] = persons
        qids = sorted(set().union(*persons_by_cat.values()))
        attrs = fetch_attrs(qids)
        titles = sorted({t for p in persons_by_cat.values()
                         for t in p.values()})
        print(f"記事冒頭を取得中... {len(titles)}件", flush=True)
        extracts = fetch_extracts(titles)
        if cache:
            with open(cache, "wb") as fh:
                pickle.dump((persons_by_cat, attrs, extracts), fh)
            print(f"キャッシュ保存: {cache}", flush=True)

    if csv_path.exists():
        with csv_path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            old_rows = list(reader)
            # 他のスクリプトが足した付加列(image/image_page/wikidata: ADR 00018)を
            # 落とさない。新規行は空にしておき、enrich 側が後から埋める
            cols = list(reader.fieldnames or COLS)
    else:
        old_rows, cols = [], list(COLS)
    existing = {r["original"] for r in old_rows}
    next_id = max((int(r["id"]) for r in old_rows), default=-1) + 1

    wd_attrs = {norm(t): attrs.get(q, {})
                for persons in persons_by_cat.values()
                for q, t in persons.items()}

    # 既存行の status 一方向更新(current -> former のみ。手動修正は上書きしない)
    turned = set()
    for r in old_rows:
        if r.get("status") == "current" and \
                wd_attrs.get(r["original"], {}).get("status") == "former":
            r["status"] = "former"
            turned.add(r["original"])
    if turned:
        print(f"status更新(current→former): {len(turned)}人", flush=True)

    # 既存行の org/debut_year は空欄補完のみ(ADR 00014)。入っている値は
    # 取得結果が違っても書き換えない
    filled = {"org": set(), "debut_year": set()}
    for r in old_rows:
        got = wd_attrs.get(r["original"], {})
        for col in ("org", "debut_year"):
            new = got.get(col, "NA")
            if r.get(col, "NA") in ("", "NA") and new not in ("", "NA"):
                r[col] = new
                filled[col].add(r["original"])
    for col, names in filled.items():
        if names:
            print(f"{col} の空欄補完: {len(names)}人", flush=True)

    added, flagged = [], []
    entries = [(title, cat, qid)
               for cat, persons in persons_by_cat.items()
               for qid, title in persons.items()
               if norm(title) not in excluded]
    hit = {norm(t) for persons in persons_by_cat.values()
           for t in persons.values()} & set(excluded)
    print(f"候補 {len(entries)}件 (EXCLUDED で除外 {len(hit)}件)", flush=True)
    # 記事名が変わると除外が効かなくなり、静かに再追加されてしまうので気付けるようにする
    stale = sorted(set(excluded) - hit)
    if stale:
        print(f"注意: EXCLUDED に未ヒットの項目 {len(stale)}件"
              "(記事改名/P106変更で対象外になった可能性): "
              + ", ".join(stale[:20]), flush=True)

    for title, cat, qid in sorted(entries):
        parsed = parse_entry(title, extracts.get(title, ""))
        if parsed is None:
            flagged.append(title)
            continue
        original, rows = parsed
        if "," in original or '"' in original:  # CSVパーサを壊す名前は収録しない
            flagged.append(title)
            continue
        if original in existing:
            continue
        existing.add(original)
        a = attrs.get(qid, {})
        for surface, pron, typ in rows:
            added.append({**{c: "" for c in cols},
                          "id": str(next_id), "original": original,
                          "surface": surface, "pronunciation": pron,
                          "type": typ, "category": cat,
                          "org": a.get("org", "NA"),
                          "debut_year": a.get("debut_year", "NA"),
                          "status": a.get("status", "current")})
        next_id += 1

    write_csv_no_trailing_newline(csv_path, cols, old_rows + added)

    n_people = len({r["id"] for r in added})
    print(f"\n{csv_name}: 既存{len(old_rows)}行 + 新規{n_people}人({len(added)}行) "
          f"= {len(old_rows) + len(added)}行", flush=True)
    print(f"要確認(読み機械決定不能) {len(flagged)}件", flush=True)
    for t in flagged[:50]:
        print(f"  要確認: {t}", flush=True)
    return 0
