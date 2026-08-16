#!/usr/bin/env python3
"""youtuber.csv に Wikidata QID と「自由ライセンスの実写」画像を付与する。

YouTuber/VTuberの画像は他リストと権利事情が違う。**チャンネルアイコン・動画
サムネイル・キャラクターイラストは本人/事務所の著作物なので一切使わない**。
使えるのは Wikimedia Commons にある自由ライセンスのファイルだけで、さらに
そこから**実写(生身の人物の写真)だけ**を選び出す(詳細は ADR 00018)。

- 人物の同定は名前の文字列一致ではなく **Wikidata の QID** で行う。youtuber.csv は
  そもそも「P106がYouTuber/VTuberでja.wikipediaに記事がある人物」から生成されて
  いる(ADR 00011)ので、同じクエリを引き直せば `original` = norm(ja記事名) で
  1対1に戻せる。同名の別人・一般名詞を拾う余地がない
- 同じ `original` に複数のQIDがぶら下がったら**曖昧として捨てる**(空のまま)
- P18があっても、以下をすべて満たさなければ採用しない:
  1. その項目が **P31=Q5(人間)** であること。VTuberの多くはキャラクター項目で、
     P18はアバターのイラストや配信のスクリーンショットなので、これで大半が落ちる
  2. MIMEが image/jpeg か image/png (SVG等のベクター図版を除く)
  3. **ファイル名**にイラスト・ロゴ・痛車・コスプレ等の語を含まない
  4. **Commonsのカテゴリ**に除外語を含まない。とくに
     `Screenshots of Virtual YouTubers`(アバターのスクショ)と
     `Free depictions of non-free works`(非自由な原著作物の写り込み)、
     `Cosplay ...`(衣装=第三者の意匠)は確実に落とす
- 表記が必要なライセンスがあるので `image_page` も必ず入れる
  (soramimic-video 側が Commons の extmetadata からクレジットを焼き込む)
- P18に無い画像は、本人QIDのStructured Data(P180)またはWikidata P373の
  本人カテゴリから見つけ、実画像を目視確認したものだけを
  `tools/youtuber_image_sources.json` に保存して補完する
- WDQSはPOST。取得結果は `tools/.cache/` に逐次保存し、中断しても再開できる
- 冪等。既存の image が空か、生成カード(gen_youtuber_cards.py 由来)の行だけ
  埋める。実写が既に入っている行は触らない

usage:
  python3 tools/enrich_youtuber_images.py [--refresh]
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import (DISAMBIG, UA, commons_urls,  # noqa: E402
                     sparql_post, write_csv_no_trailing_newline)

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "youtuber.csv"
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
WD_CACHE = CACHE_DIR / "youtuber_wikidata.json"
COMMONS_CACHE = CACHE_DIR / "youtuber_commons.json"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
CURATED_SOURCES = Path(__file__).resolve().parent / "youtuber_image_sources.json"

# 書き出し列は実ファイルのヘッダーに追随する。この3列だけは無ければ末尾に足す
OWN_COLS = ["image", "image_page", "wikidata"]

# 取得仕様(update_youtuber.py の SPECS と同じ職業QID・同じ除外)
SPECS = [
    ("youtuber", "Q17125263", "MINUS { ?p wdt:P106 wd:Q55155641 }"),
    ("vtuber", "Q55155641", ""),
]
# WDQSの部分応答ガード(update_youtuber.py の guard と同じ考え方)。
# 実測 2026-07-28: youtuber 859人(うちP18あり 384) / vtuber 561人(同 17)
MIN_PERSONS = {"youtuber": 400, "vtuber": 150}

# --- 実写でないものを落とすためのパターン ---------------------------------
# ファイル名(Commonsのファイル名は英語が基本だが日本語のものもある)
DENY_NAME = re.compile(
    r"artwork|illust|itasha|痛車|cosplay|コスプレ|\blogos?\b|ロゴ|\bicons?\b"
    r"|\bavatars?\b|fanart|fan[ _]art|イラスト|drawing|painting|\brender\b"
    r"|3d ?model|emblem|\bmascot\b", re.I)
# Commonsのカテゴリ名。上2つがVTuberのアバター画像を落とす本命
DENY_CAT = re.compile(
    r"screenshots of virtual youtubers|free depictions of non-free works"
    r"|cosplay|itasha|virtual youtubers on vehicles|fan ?art|illustration"
    r"|drawings|paintings|artwork|logos|icons|avatars|anime and manga"
    r"|figurine|statue|action figure|coats of arms", re.I)
# 「カメラで撮られた実写」の積極的な根拠(採用の必須条件ではなく、同じ人物に
# 複数候補があるときの優先順位に使う)
POSITIVE_CAT = re.compile(
    r"photograph|photos by|taken with|flickr|wikiportraits|retouched pictures"
    r"|personality rights", re.I)

ALLOWED_MIME = ("image/jpeg", "image/png")


def norm(title: str) -> str:
    """ja記事名 -> youtuber.csv の original(yt_common.norm と同じ規則)。"""
    return DISAMBIG.sub("", title).replace("　", "").replace(" ", "")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_curated_sources(path: Path = CURATED_SOURCES) -> list[dict]:
    """目視確認済みのP18以外のCommons画像台帳を読む。"""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    sources = data.get("images", [])
    required = {"original", "wikidata", "file", "source_type", "reviewed"}
    allowed_source_types = {
        "commons_structured_depicts",
        "commons_person_category",
    }
    seen_originals = set()
    seen_qids = set()
    for i, source in enumerate(sources, 1):
        missing = sorted(required - set(source))
        if missing:
            raise SystemExit(
                f"error: {path.name} images[{i}] に {missing[0]} がない")
        if source["original"] in seen_originals:
            raise SystemExit(
                f"error: {path.name} で original が重複: {source['original']}")
        if source["wikidata"] in seen_qids:
            raise SystemExit(
                f"error: {path.name} で wikidata が重複: {source['wikidata']}")
        if source["source_type"] not in allowed_source_types:
            raise SystemExit(
                f"error: {path.name} images[{i}] のsource_typeが不正: "
                f"{source['source_type']}")
        seen_originals.add(source["original"])
        seen_qids.add(source["wikidata"])
    return sources


def fetch_persons(occ: str, minus: str) -> list:
    """[{qid, title, img, human}, ...]。P18は無くてもよい(QIDだけ埋める用)。"""
    query = f"""
SELECT ?p ?title ?img ?human WHERE {{
  ?p wdt:P106 wd:{occ} .
  {minus}
  ?a schema:about ?p ; schema:isPartOf <https://ja.wikipedia.org/> ;
     schema:name ?title .
  OPTIONAL {{ ?p wdt:P18 ?img }}
  BIND(EXISTS {{ ?p wdt:P31 wd:Q5 }} AS ?human)
}}"""
    out = []
    for b in sparql_post(query)["results"]["bindings"]:
        out.append({
            "qid": b["p"]["value"].rsplit("/", 1)[-1],
            "title": b["title"]["value"],
            "img": b.get("img", {}).get("value", ""),
            "human": b["human"]["value"] == "true",
        })
    return out


def collect_wikidata(refresh: bool) -> dict:
    """category -> [{qid, title, img, human}, ...]。キャッシュに逐次保存。"""
    cache = {} if refresh else load_json(WD_CACHE)
    for cat, occ, minus in SPECS:
        if cat not in cache:
            cache[cat] = fetch_persons(occ, minus)
            save_json(WD_CACHE, cache)
            time.sleep(1)  # WDQSへの連続アクセスを避ける
        n = len(cache[cat])
        if n < MIN_PERSONS[cat]:
            raise SystemExit(
                f"error: implausible person count for {cat}: {n} "
                "(WDQSの部分応答の可能性。--refresh で引き直すこと)")
        with_img = sum(1 for r in cache[cat] if r["img"])
        print(f"{cat}: {n}人(P18あり {with_img})", flush=True)
    return cache


def commons_meta(files: list, refresh: bool) -> dict:
    """Commonsファイル名 -> {mime, cats, positive}。25件ずつ、逐次キャッシュ。"""
    cache = {} if refresh else load_json(COMMONS_CACHE)
    todo = [f for f in files if f not in cache]
    for i in range(0, len(todo), 25):
        batch = todo[i:i + 25]
        params = {"action": "query",
                  "titles": "|".join("File:" + t for t in batch),
                  "prop": "imageinfo|categories",
                  "iiprop": "mime|metadata", "cllimit": "max",
                  "format": "json", "formatversion": "2"}
        req = urllib.request.Request(
            COMMONS_API + "?" + urllib.parse.urlencode(params), headers=UA)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as res:
                    data = json.load(res)
                break
            except Exception as ex:      # noqa: BLE001 (ネットワーク全般)
                print(f"Commons retry {attempt}: {ex}", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
        else:
            raise SystemExit("error: Commons APIの取得に失敗")
        for page in data["query"]["pages"]:
            info = (page.get("imageinfo") or [{}])[0]
            meta = {m["name"]: m["value"] for m in (info.get("metadata") or [])}
            cats = [c["title"][9:] for c in page.get("categories", [])]
            cache[page["title"][len("File:"):]] = {
                "mime": info.get("mime"),
                "cats": cats,
                # EXIFにカメラ情報があるか、写真系カテゴリに属するか
                "positive": bool(meta.get("Make") or meta.get("Model"))
                or any(POSITIVE_CAT.search(c) for c in cats),
            }
        save_json(COMMONS_CACHE, cache)
        time.sleep(0.5)   # Commons APIへの連続アクセスを避ける
        print(f"  Commons {i + len(batch)}/{len(todo)}", flush=True)
    return cache


def reject_reason(rec: dict, meta: dict) -> str | None:
    """実写として採用できない理由。採用できるなら None。"""
    if not rec["human"]:
        # キャラクター項目・グループ項目。VTuberのアバター画像はここで落ちる
        return "P31がQ5(人間)でない"
    if meta is None:
        return "Commonsのメタ情報を取得できない"
    if meta.get("mime") not in ALLOWED_MIME:
        return f"MIMEが写真でない({meta.get('mime')})"
    if DENY_NAME.search(rec["file"]):
        return "ファイル名がイラスト・ロゴ等"
    hit = [c for c in meta.get("cats", []) if DENY_CAT.search(c)]
    if hit:
        return f"カテゴリ「{hit[0]}」"
    return None


def is_generated_card(url: str) -> bool:
    """gen_youtuber_cards.py が入れた生成カードのURLか(実写で上書きしてよい)。"""
    from gen_youtuber_cards import URL_PREFIX
    return url.startswith(URL_PREFIX)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true",
                    help="キャッシュを無視してWikidata/Commonsを引き直す")
    ap.add_argument("--report", action="store_true",
                    help="採用/不採用の内訳を1件ずつ表示する")
    args = ap.parse_args()

    wd = collect_wikidata(args.refresh)

    with CSV_PATH.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [dict(r) for r in reader]
        cols = list(reader.fieldnames)
    cols += [c for c in OWN_COLS if c not in cols]
    for r in rows:
        for c in cols:
            r.setdefault(c, "")
    originals = {r["original"] for r in rows}

    # original -> [レコード]。CSVに載っている人だけ相手にする
    by_original: dict[str, list] = {}
    for cat, records in wd.items():
        for rec in records:
            o = norm(rec["title"])
            if o in originals:
                rec = {**rec, "cat": cat,
                       "file": urllib.parse.unquote(rec["img"].rsplit("/", 1)[-1])
                       if rec["img"] else ""}
                by_original.setdefault(o, []).append(rec)

    # 同じ original に別QIDがぶら下がったら曖昧として捨てる(同名の別人を避ける)
    ambiguous = sorted(o for o, recs in by_original.items()
                       if len({r["qid"] for r in recs}) > 1)
    for o in ambiguous:
        del by_original[o]
    print(f"CSVと照合: {len(by_original)}人"
          f"(QID重複で除外 {len(ambiguous)}人)", flush=True)

    curated = load_curated_sources()
    for source in curated:
        recs = by_original.get(source["original"])
        if not recs:
            raise SystemExit(
                f"error: curated imageの人物がCSV/Wikidata照合結果にない: "
                f"{source['original']}")
        qids = {r["qid"] for r in recs}
        if qids != {source["wikidata"]}:
            raise SystemExit(
                f"error: curated imageのQIDが現在値と不一致: "
                f"{source['original']} {source['wikidata']} / {sorted(qids)}")

    files = sorted({r["file"] for recs in by_original.values()
                    for r in recs if r["file"]}
                   | {r["file"] for r in curated})
    print(f"Commonsファイル: {len(files)}件を検査", flush=True)
    meta = commons_meta(files, args.refresh) if files else {}

    photos: dict[str, tuple] = {}     # original -> (image, image_page)
    rejected: list[tuple] = []
    for o, recs in sorted(by_original.items()):
        ok = []
        for rec in recs:
            if not rec["file"]:
                continue
            why = reject_reason(rec, meta.get(rec["file"]))
            if why:
                rejected.append((rec["cat"], o, rec["file"], why))
            else:
                ok.append((not meta[rec["file"]]["positive"], rec["file"]))
        if ok:
            # カメラ由来の根拠がある方を優先し、同点はファイル名で決定的に選ぶ
            photos[o] = commons_urls(sorted(ok)[0][1])

    # P18に無いが、本人QIDのStructured Data(P180)または本人のCommons
    # カテゴリから見つかった画像。QID/カテゴリだけではロゴや別人も混ざりうるため、
    # 台帳へは実画像を目視確認したものだけを入れる。現在のP18候補より後に適用し、
    # 明示的に選んだ画像を優先する。
    for source in curated:
        rec = {
            "human": True,
            "file": source["file"],
        }
        why = reject_reason(rec, meta.get(source["file"]))
        if why:
            raise SystemExit(
                f"error: curated imageが現在の安全基準を満たさない: "
                f"{source['original']} ({why})")
        photos[source["original"]] = commons_urls(source["file"])

    n_ok = {c: 0 for c, _, _ in SPECS}
    for o in photos:
        n_ok[by_original[o][0]["cat"]] += 1
    print(f"\n実写として採用: {len(photos)}人 "
          + ", ".join(f"{c} {n}" for c, n in n_ok.items()))
    print(f"P18はあるが不採用: {len(rejected)}件")
    print(f"目視確認済みP18外画像: {len(curated)}人")
    reasons: dict[str, int] = {}
    for _cat, _o, _f, why in rejected:
        reasons[why] = reasons.get(why, 0) + 1
    for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {n:3d} {why}")
    if args.report:
        for cat, o, f, why in sorted(rejected):
            print(f"  不採用 [{cat}] {o}: {f} ({why})")

    curated_originals = {source["original"] for source in curated}
    filled = qid_filled = kept = 0
    for r in rows:
        o = r["original"]
        recs = by_original.get(o)
        if recs and not r["wikidata"]:
            r["wikidata"] = recs[0]["qid"]
            qid_filled += 1
        hit = photos.get(o)
        if not hit:
            continue
        if (r["image"] and not is_generated_card(r["image"])
                and o not in curated_originals):
            kept += 1          # 既に実写がある行は触らない(冪等)
            continue
        if r["image"] == hit[0]:
            continue
        r["image"], r["image_page"] = hit
        filled += 1

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    print(f"\nyoutuber.csv: image を実写で埋めた行 +{filled}, "
          f"既に実写だった行 {kept}, wikidata を埋めた行 +{qid_filled}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
