#!/usr/bin/env python3
"""stations.csv を Wikidata + Wikipedia から差分更新する。

出典:
- 駅エンティティ・所在地・運営者・開業年・駅番号・画像: Wikidata (CC0)
- 読み・description: Wikipedia日本語版の記事冒頭文 (CC BY-SA 4.0)

方式(既存行は書き換えない):
- 駅の同定は wikidata 列(QID)。既存行の表記・読み・id は保持する
- Wikidata上の現役駅(鉄道駅/路面電車停留場/索道駅のサブクラス閉包、
  廃止でない)のうち csv に無い QID を新規駅として追記
- csv にあって現役でなくなった駅は status=former に変更(行は消さない)
- 新規駅の読みは Wikipedia 冒頭文「〇〇駅(よみえき)」を正規表現で抽出。
  取れない場合は pronunciation 空で追記(PRレビューで補完する)
- 新規駅の description は記事冒頭から短い完結文を作る。既存行の説明は
  書き換えない(初回補完は tools/enrich_station_descriptions.py)
- 新規駅の路線名(lines列)は tools/enrich_lines.py と同じ方式で取得。
  既存行の lines はここでは触らない(補完・更新は enrich_lines.py で行う)

usage: python3 tools/update_stations.py
"""

import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from wpnames import clean_ws, make_description

UA = {"User-Agent": "soramimic-wordlists-updater/1.0 (https://github.com/soramimic/soramimic-wordlists)"}
WDQS = "https://query.wikidata.org/sparql"
WD_API = "https://www.wikidata.org/w/api.php"
WP_API = "https://ja.wikipedia.org/w/api.php"
# 鉄道駅 / 路面電車停留場 / 索道駅
ROOT_CLASSES = "wd:Q55488 wd:Q2175765 wd:Q44696264"
# P5817(使用状態): 退役/廃止/未運行/中止
CLOSED_STATES = {"Q11639308", "Q63065035", "Q111802839", "Q30108381"}
PREF_CLASS = "Q50337"  # 都道府県
# 新規・消滅がこの件数を超えたらソース異常とみなして中断
MAX_CHANGES = 200

CSV_PATH = Path(__file__).resolve().parent.parent / "stations.csv"

KATA2HIRA = str.maketrans({chr(k): chr(k - 0x60) for k in range(ord("ァ"), ord("ヶ") + 1)})
DISAMBIG = re.compile(r"\s+\([^)]*\)$")
SUFFIX = re.compile(r"(駅|停留場|停留所)$")
KANA_NAME = re.compile(r"^[ぁ-ゖァ-ヶーゝゞ・\s]+$")
EXCLUDE_TITLE = re.compile(r"(信号場|信号所|貨物ターミナル|貨物駅|操車場)( \(|（|$)|一覧")
FEATURE_TERMS = (
    (re.compile(r"(日本|国内|JR|世界).{0,12}(唯一|初|最[東西南北]|最も)"), 6),
    (re.compile(r"(唯一|初めて|最[東西南北]|最も.{0,8}(駅|ホーム))"), 6),
    (re.compile(r"(重要文化財|登録有形文化財|文化財|近代化産業遺産)"), 6),
    (re.compile(r"(受賞|選定|百選|ブルネル賞|グッドデザイン賞)"), 5),
    (re.compile(r"(秘境駅|絶景|眺望|海が見える|夜景|桜の名所)"), 5),
    (re.compile(r"(駅名.{0,16}由来|由来する|命名された|改称された)"), 4),
    (re.compile(r"(舞台|ロケ地|モデル|聖地|作品に登場)"), 4),
    (re.compile(r"(建築家|デザイン|意匠|保存|復元|現存する)"), 3),
    (re.compile(r"(スイッチバック|ループ線|地下.{0,10}ホーム|珍しい|特徴)"), 3),
)
LOW_VALUE_SENTENCE = re.compile(
    r"(駅番号|事務管コード|事務管理コード|貨物事務管コード|電報略号|"
    r"特定都区市内制度|運賃計算|管理駅)"
)
CONTEXT_REFERENCE = re.compile(r"(当駅|同駅|同県|同市|同区|同町|同村|同社|同線)")
STATION_COPULA = re.compile(
    r"((?:駅|停留場|停留所)(?:（廃駅）)?)で(?:ある|あった)。"
)
DESCRIPTION_MAX = 48
ERA_PAREN = re.compile(r"（(?:明治|大正|昭和|平成|令和)\d+年(?:\d+月\d+日)?）")
COMPACT_ENDINGS = (
    ("がデザインした。", "がデザイン。"),
    ("に選定されている。", "に選定。"),
    ("に選定された。", "に選定。"),
    ("に認定されている。", "に認定。"),
    ("を受賞した。", "を受賞。"),
    ("として著名である。", "として知られる。"),
    ("ことでも知られる。", "ことで知られる。"),
    ("となっている。", "。"),
)


def to_hira(s: str) -> str:
    return s.translate(KATA2HIRA)


def http_json(url: str, retries: int = 4, wait: float = 10.0):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={**UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as res:
                return json.load(res)
        except (OSError, ValueError) as ex:
            print(f"retry {attempt}: {ex}", file=sys.stderr)
            time.sleep(wait * (attempt + 1))
    raise RuntimeError(f"failed: {url[:120]}")


def fetch_entities() -> dict:
    """現役駅 QID -> {label, title}"""
    query = f"""
SELECT DISTINCT ?s ?label ?title ?dissolved ?state WHERE {{
  ?s wdt:P17 wd:Q17 ; wdt:P31 ?cls .
  ?cls wdt:P279* ?root .
  VALUES ?root {{ {ROOT_CLASSES} }}
  ?s rdfs:label ?label . FILTER(LANG(?label)='ja')
  OPTIONAL {{ ?article schema:about ?s ; schema:isPartOf <https://ja.wikipedia.org/> ; schema:name ?title . }}
  OPTIONAL {{ ?s wdt:P576 ?dissolved }}
  OPTIONAL {{ ?s wdt:P5817 ?state }}
}}"""
    url = WDQS + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    data = http_json(url, wait=70)
    ents: dict = {}
    for b in data["results"]["bindings"]:
        q = b["s"]["value"].rsplit("/", 1)[1]
        e = ents.setdefault(q, {"label": b["label"]["value"], "title": None,
                                "dissolved": False, "state": set()})
        if "title" in b:
            e["title"] = b["title"]["value"]
        if "dissolved" in b:
            e["dissolved"] = True
        if "state" in b:
            e["state"].add(b["state"]["value"].rsplit("/", 1)[1])
    active = {q: e for q, e in ents.items()
              if e["title"] and not e["dissolved"] and not (e["state"] & CLOSED_STATES)
              and not EXCLUDE_TITLE.search(e["title"])}
    return active


def wbget(ids: list, props: str) -> dict:
    url = WD_API + "?" + urllib.parse.urlencode({
        "action": "wbgetentities", "ids": "|".join(ids), "props": props,
        "languages": "ja", "format": "json"})
    return http_json(url).get("entities", {})


def first_claim(e: dict, prop: str):
    for c in e.get("claims", {}).get(prop, []):
        dv = c.get("mainsnak", {}).get("datavalue")
        if dv:
            return dv["value"]
    return None


def claim_values(e: dict, prop: str) -> list:
    claims = [c for c in e.get("claims", {}).get(prop, [])
              if c.get("rank") != "deprecated"
              and c.get("mainsnak", {}).get("datavalue")]
    preferred = [c for c in claims if c.get("rank") == "preferred"]
    return [c["mainsnak"]["datavalue"]["value"] for c in (preferred or claims)]


def claim_year(e: dict) -> str:
    for prop in ("P1619", "P571"):  # 正式開業日、なければ設立日
        years = []
        for value in claim_values(e, prop):
            match = re.match(r"^\+?(-?\d+)-", value.get("time", ""))
            if match:
                years.append(int(match.group(1)))
        if years:
            year = min(years)
            return f"前{abs(year)}" if year < 0 else str(year)
    return ""


def sanitize_cell(value: str) -> str:
    return value.replace(",", "、").replace('"', "”").strip()


def fetch_details(qids: list) -> dict:
    """QID -> 所在地・運営者QID・開業年・駅番号・画像(WDQS非依存)。"""
    details = {}
    for i in range(0, len(qids), 50):
        for q, e in wbget(qids[i:i + 50], "claims").items():
            muni = first_claim(e, "P131")
            img = first_claim(e, "P18")
            operator_qids = sorted({
                value["id"] for value in claim_values(e, "P137")
                if isinstance(value, dict) and value.get("id")
            })
            station_codes = sorted({
                str(value).strip() for value in claim_values(e, "P296")
                if str(value).strip()
            })
            d = {
                "muni": muni["id"] if muni else None,
                "operator_qids": operator_qids,
                "opened_year": claim_year(e),
                "station_code": sanitize_cell("／".join(station_codes)),
                "image": "",
                "image_page": "",
            }
            if img:
                # カンマ等を含むファイル名はCSVを壊すので必ずURLエンコード
                fname = urllib.parse.quote(img.replace(" ", "_"))
                d["image"] = ("http://commons.wikimedia.org/wiki/Special:FilePath/"
                              + fname)
                d["image_page"] = "https://commons.wikimedia.org/wiki/File:" + fname
            details[q] = d
        time.sleep(0.3)
    return details


def resolve_operator_labels(qids: set) -> dict:
    """運営者QID -> 日本語略称(P1813)、なければ日本語ラベル。"""
    result = {}
    for i in range(0, len(qids), 50):
        for q, e in wbget(sorted(qids)[i:i + 50], "claims|labels").items():
            short = next((
                value["text"] for value in claim_values(e, "P1813")
                if isinstance(value, dict) and value.get("language") == "ja"
            ), "")
            label = e.get("labels", {}).get("ja", {}).get("value", "")
            result[q] = short or label
        time.sleep(0.3)
    return result


def resolve_admin(muni_qids: set) -> dict:
    """自治体QID -> (市区町村ラベル, 都道府県ラベル)。P131を親へ辿る"""
    admin: dict = {}
    frontier = sorted(muni_qids)
    for _hop in range(5):
        todo = [q for q in frontier if q not in admin]
        if not todo:
            break
        nxt = []
        for i in range(0, len(todo), 50):
            for q, e in wbget(todo[i:i + 50], "claims|labels").items():
                p31 = {c["mainsnak"]["datavalue"]["value"]["id"]
                       for c in e.get("claims", {}).get("P31", [])
                       if c.get("mainsnak", {}).get("datavalue")}
                parent = first_claim(e, "P131")
                admin[q] = {"label": e.get("labels", {}).get("ja", {}).get("value", ""),
                            "p31": p31, "parent": parent["id"] if parent else None}
                if admin[q]["parent"]:
                    nxt.append(admin[q]["parent"])
            time.sleep(0.3)
        frontier = sorted(set(nxt))

    result = {}
    for q in muni_qids:
        pref = ""
        cur, seen = q, set()
        while cur and cur not in seen:
            seen.add(cur)
            a = admin.get(cur)
            if not a:
                break
            if PREF_CLASS in a["p31"]:
                pref = a["label"]
                break
            cur = a["parent"]
        result[q] = (admin.get(q, {}).get("label", ""), pref)
    return result


def fetch_extracts(titles: list) -> dict:
    """記事タイトル -> 冒頭文"""
    extracts = {}
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        url = WP_API + "?" + urllib.parse.urlencode({
            "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
            "exlimit": "max", "redirects": 1, "format": "json",
            "titles": "|".join(batch)})
        data = http_json(url)
        redir = {r["to"]: r["from"] for r in data["query"].get("redirects", [])}
        for p in data["query"]["pages"].values():
            orig = redir.get(p["title"], p["title"])
            extracts[orig] = p.get("extract", "")[:1200]
        time.sleep(0.6)
    return extracts


def clean_yomi(cand: str):
    cand = re.split(r"[、,/／]", cand)[0]
    cand = re.sub(r"[\s ]", "", cand).replace("（", "").replace("）", "")
    # 読み括弧の閉じ忘れ(Wikipedia側のtypo)で助詞が混入するケースに対応
    cand = re.sub(r"(えき|ていりゅうじょう|ていりゅうば)(は|とは)?$", "", cand)
    return to_hira(cand) if cand and KANA_NAME.match(cand) else None


def parse_station(title: str, extract: str):
    """記事タイトルと冒頭文から(駅名, 読み or None)を得る"""
    base = DISAMBIG.sub("", title)
    name = SUFFIX.sub("", base)
    text = extract.replace("　", " ")
    yomi = None
    # 1) 「タイトル（読み）」が本文中にある(合同記事対応)。括弧は全半角許容
    m = re.search(re.escape(base) + r"\s*[（(]([^（）()]*(?:[（(][^（）()]*[）)])?[^（）()]*?)[）)、]", text)
    if m:
        yomi = clean_yomi(m.group(1))
    # 2) 冒頭に駅名が現れる記事に限り、読みらしき括弧を探す(「AおよびB（よみ）」等)。
    #    合同記事(JR駅の記事に停留場が同居)の誤マッチ防止のため先頭50字に限定
    if yomi is None and base in text[:50]:
        m = re.search(r"[（(]\s*([ぁ-ゖァ-ヶー・\s]+(?:えき|ていりゅうじょう|ていりゅうば))[）)]", text[:150])
        if m:
            yomi = clean_yomi(m.group(1))
    # 3) かな駅名はそのまま読みにする
    if yomi is None and KANA_NAME.match(name):
        yomi = to_hira(name)
    return name, yomi


def resolve_station_references(
    sentence: str, title: str, prefecture: str = "", city: str = "",
    operator: str = "",
) -> str:
    """単独表示した特徴文の「当駅」「同県」等を具体名に置き換える。"""
    replacements = {"当駅": title, "同駅": title, "同県": prefecture}
    if city and "/" not in city and city[-1:] in "市区町村":
        replacements[f"同{city[-1]}"] = city
    if operator and "／" not in operator:
        replacements["同社"] = operator
    for old, new in replacements.items():
        if new:
            sentence = sentence.replace(old, new)
    return sentence


def nominalize_station_description(description: str) -> str:
    """駅種別を説明する定型的な「駅である。」だけを体言止めにする。"""
    return STATION_COPULA.sub(r"\1。", description)


def compact_station_description(
    description: str,
    opened_year: str = "",
    fallback: str = "",
) -> str:
    """特徴文を優先し、無ければ開業年だけを返す。"""
    description = ERA_PAREN.sub("", description)
    for old, new in COMPACT_ENDINGS:
        description = description.replace(old, new)
    description = re.sub(r"\s+", " ", description).strip()
    has_feature = any(pattern.search(description) for pattern, _ in FEATURE_TERMS)
    if has_feature and len(description) <= DESCRIPTION_MAX:
        return description

    if has_feature and description.startswith("駅のシンボルマーク"):
        designers = re.findall(
            r"([一-龥々]{2,8})が(?:デザイン|完成させた)", description
        )
        if designers:
            return f"駅のシンボルマークは{designers[-1]}がデザイン。"

    if has_feature:
        clauses = [
            re.sub(r"^(?:また|なお)、", "", clause).strip()
            for clause in re.split(r"(?<=。)|、", description)
            if clause.strip()
        ]
        candidates = []
        for index, clause in enumerate(clauses):
            if not clause.endswith("。"):
                continue
            score = sum(weight for pattern, weight in FEATURE_TERMS
                        if pattern.search(clause))
            if score and len(clause) <= DESCRIPTION_MAX:
                candidates.append((score, -index, clause))
        if candidates:
            return max(candidates)[2]
        # 特徴を機械的な字数制限で捨てない。長文は少数なので、カード側の
        # 自動フィットで扱い、所在地だけの定型文への品質低下を避ける。
        return description

    fallback = nominalize_station_description(make_description("", fallback))
    if fallback != "NA" and any(
        pattern.search(fallback) for pattern, _ in FEATURE_TERMS
    ):
        return fallback
    return f"{opened_year}年開業。" if opened_year else "NA"


def make_station_description(
    intro: str,
    wd_desc: str,
    title: str,
    opened_year: str = "",
    prefecture: str = "",
    city: str = "",
    operator: str = "",
) -> str:
    """記事導入部から特徴的な1文を優先し、無ければ開業年だけを返す。"""
    text = clean_ws(intro)
    complete = [s.strip() + "。" for s in text.split("。")[:-1] if s.strip()]
    candidates = []
    for index, sentence in enumerate(complete):
        score = sum(weight for pattern, weight in FEATURE_TERMS
                    if pattern.search(sentence))
        if LOW_VALUE_SENTENCE.search(sentence):
            score -= 5
        if score > 0:
            candidates.append((score, -index, sentence))
    if candidates:
        sentence = resolve_station_references(
            max(candidates)[2], title, prefecture, city, operator
        )
        if not CONTEXT_REFERENCE.search(sentence):
            desc = make_description(sentence, "", title)
            if desc != "NA":
                desc = nominalize_station_description(desc)
                return compact_station_description(desc, opened_year, wd_desc)

    first = complete[0] if complete else intro
    desc = make_description(first, wd_desc, title)
    if desc == "NA":
        return compact_station_description("", opened_year)
    if opened_year and opened_year not in desc and len(desc) <= 105:
        desc += f"{opened_year}年開業。"
    desc = nominalize_station_description(desc)
    return compact_station_description(desc, opened_year, wd_desc)


def main() -> int:
    active = fetch_entities()
    if not 8000 <= len(active) <= 12000:
        print(f"error: implausible station count: {len(active)}", file=sys.stderr)
        return 1

    with CSV_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_qid = {r["wikidata"]: r for r in rows if r.get("wikidata")}

    added_qids = sorted(q for q in active if q not in by_qid)
    # 既にformerの行は数えない(新たにcurrent->formerになるものだけ)
    gone_qids = sorted(q for q in by_qid
                       if q not in active and by_qid[q]["status"] == "current")
    if len(added_qids) + len(gone_qids) > MAX_CHANGES:
        print(f"error: too many changes (+{len(added_qids)}/-{len(gone_qids)})",
              file=sys.stderr)
        return 1

    changed = 0
    for q in gone_qids:
        if by_qid[q]["status"] != "former":
            by_qid[q]["status"] = "former"
            print(f"status: {by_qid[q]['original']} ({q}) -> former")
            changed += 1
    # former -> current の自動復帰はしない: 未成駅・計画駅などWikidata上の
    # 状態プロパティが不十分な駅を手動でformerにしたら、それを尊重する
    for q in by_qid:
        if q in active and by_qid[q]["status"] != "current":
            print(f"note: {by_qid[q]['original']} ({q}) はWikidata上は現役だが "
                  "former のまま維持(復活していたら手動でcurrentに戻すこと)")

    if added_qids:
        # 循環import回避のため遅延import(enrich_lines側が本モジュールを使う)
        from enrich_lines import SEP, fetch_station_lines
        line_map = fetch_station_lines()
        details = fetch_details(added_qids)
        operator_qids = {
            op for detail in details.values() for op in detail["operator_qids"]
        }
        operator_labels = resolve_operator_labels(operator_qids)
        munis = {d["muni"] for d in details.values() if d["muni"]}
        admin = resolve_admin(munis)
        extracts = fetch_extracts([active[q]["title"] for q in added_qids])
        next_id = max((int(r["id"]) for r in rows), default=-1) + 1
        for q in added_qids:
            title = active[q]["title"]
            extract = extracts.get(title, "")
            name, yomi = parse_station(title, extract)
            d = details.get(q, {
                "muni": None, "operator_qids": [], "opened_year": "",
                "station_code": "", "image": "", "image_page": "",
            })
            muni_label, pref = admin.get(d["muni"], ("", "")) if d["muni"] else ("", "")
            operators = sorted({
                operator_labels[op] for op in d["operator_qids"]
                if operator_labels.get(op)
            })
            operator = sanitize_cell("／".join(operators))
            desc = make_station_description(
                extract, "", DISAMBIG.sub("", title), d["opened_year"],
                pref, muni_label, operator,
            )
            rows.append({"id": str(next_id), "original": name, "surface": name,
                         "pronunciation": yomi or "", "prefecture": pref,
                         "city": muni_label,
                         "lines": SEP.join(sorted(line_map.get(q, []))),
                         "operator": operator,
                         "opened_year": d["opened_year"],
                         "station_code": d["station_code"],
                         "status": "current",
                         "image": d["image"], "image_page": d["image_page"],
                         "description": "" if desc == "NA" else desc,
                         "wikidata": q})
            mark = "" if yomi else " [要読み確認]"
            print(f"added: {name} ({pref}, {q}) id={next_id}{mark}")
            next_id += 1

    cols = ["id", "original", "surface", "pronunciation", "prefecture", "city",
            "lines", "operator", "opened_year", "station_code", "status",
            "image", "image_page", "description", "wikidata"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    # 末尾改行なしで書く(soramimic側のパーサが最終空行で落ちるため)
    CSV_PATH.write_text(buf.getvalue().rstrip("\n"), encoding="utf-8")

    print(f"stations.csv: +{len(added_qids)} added, -{len(gone_qids)} gone, "
          f"{changed} status changed, {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
