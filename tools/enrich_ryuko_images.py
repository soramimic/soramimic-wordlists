#!/usr/bin/env python3
"""ryuko.csv に再利用可能な Wikimedia Commons 画像を付与する。

語と完全一致する日本語Wikipedia記事の自由ライセンスなリード画像を採用し、
リード画像がない場合はWikidata P18を使う。曖昧さ回避・記事なし・Commonsに
存在しない画像は採用しない。結果はキャッシュし、レビュー用TSVも出力する。

usage: python3 tools/enrich_ryuko_images.py [--refresh]
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "ryuko.csv"
CACHE = ROOT / "tools" / ".cache" / "ryuko_images.json"
REPORT = ROOT / "tools" / ".cache" / "ryuko_image_report.tsv"
MISSING_REPORT = ROOT / "tools" / ".cache" / "ryuko_missing_images.tsv"
OVERRIDES = ROOT / "tools" / "ryuko_image_overrides.json"

JA_API = "https://ja.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
UA = (
    "soramimic-wordlists/enrich_ryuko_images "
    "(https://github.com/soramimic/soramimic-wordlists)"
)
BATCH = 40
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".svg", ".gif", ".webp")

# 完全一致でも別義の記事になる語、画像が語の意味を表さない語。
EXCLUDED = {
    "はしか絵": "鯰絵・地震鯰の版画で麻疹絵ではない",
    "モダンボーイ": "画像はモダンガールを描いた作品",
    "防空頭巾": "画像はもんぺで頭巾ではない",
    "カンロ飴": "画像は企業が入居するビルで飴ではない",
    "安全神話": "画像は神話上の人物画で比喩表現と無関係",
    "シャネラー": "画像はパリのホテル建築でファッションと無関係",
    "冷めたピザ": "画像は小渕恵三の肖像で比喩表現を表さない",
    "日本列島総不況": "画像は堺屋太一の肖像で不況を表さない",
    "マイブーム": "画像はみうらじゅんの肖像で概念を表さない",
    "ヤマンバ": "画像は妖怪の山姥で平成期のファッションではない",
    "IT革命": "画像は民衆を導く自由の女神でITと無関係",
    "Godzilla": "画像は怪獣映画のロゴで野球選手の愛称ではない",
    "クールジャパン": "画像は森タワーで文化輸出を表さない",
    "奈良判定": "画像は日本スポーツ協会の建物で判定問題と無関係",
    "沼": "画像は湿地で趣味に没頭する俗語とは別義",
    "ジェルネイル": "画像はカメラでネイルと無関係",
    "チョーカー": "画像は別種の首飾りで流行したチョーカーではない",
    "界隈": "画像は地理的な周辺でネット上のコミュニティとは別義",
    "ミーム": "画像はヒエログリフでネットミームとは別義",
    "緊急銃猟": "画像は政府紋章だけで緊急の野生動物駆除を表さない",
}


def api_get(url, params):
    params = dict(params, format="json", maxlag=5)
    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA}
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response)
        except Exception as exc:  # noqa: BLE001 - 最終試行ではそのまま失敗させる
            if attempt == 3:
                raise
            wait = 15 if "429" in str(exc) else 5 * (attempt + 1)
            print(f"  retry {attempt + 1}: {exc}", file=sys.stderr)
            time.sleep(wait)


def lookup_batch(titles):
    data = api_get(
        JA_API,
        {
            "action": "query",
            "redirects": 1,
            "titles": "|".join(titles),
            "prop": "pageprops|pageimages",
            "ppprop": "wikibase_item|disambiguation",
            "piprop": "name",
            "pilicense": "free",
        },
    )
    query = data["query"]
    normalized = {item["from"]: item["to"] for item in query.get("normalized", [])}
    redirects = {item["from"]: item["to"] for item in query.get("redirects", [])}
    pages = {page["title"]: page for page in query.get("pages", {}).values()}
    results = {}
    for title in titles:
        resolved = redirects.get(normalized.get(title, title), normalized.get(title, title))
        page = pages.get(resolved)
        if not page or "missing" in page:
            results[title] = {"status": "missing"}
            continue
        props = page.get("pageprops", {})
        if "disambiguation" in props:
            results[title] = {"status": "disambig", "article": resolved}
            continue
        result = {
            "status": "ok" if page.get("pageimage") else "noimage",
            "article": resolved,
            "qid": props.get("wikibase_item", ""),
        }
        if page.get("pageimage"):
            result["file"] = page["pageimage"]
        results[title] = result
    return results


def fetch_p18(qids):
    result = {}
    qids = sorted(set(qids))
    for offset in range(0, len(qids), 50):
        batch = qids[offset : offset + 50]
        data = api_get(
            WIKIDATA_API,
            {"action": "wbgetentities", "props": "claims", "ids": "|".join(batch)},
        )
        for qid in batch:
            claims = data.get("entities", {}).get(qid, {}).get("claims", {})
            p18 = claims.get("P18")
            if not p18:
                continue
            value = p18[0].get("mainsnak", {}).get("datavalue", {}).get("value")
            if value:
                result[qid] = value
        time.sleep(0.5)
    return result


def commons_files(files):
    existing = set()
    files = sorted(set(files))
    for offset in range(0, len(files), 50):
        batch = files[offset : offset + 50]
        data = api_get(
            COMMONS_API,
            {"action": "query", "titles": "|".join("File:" + name for name in batch)},
        )
        for page in data["query"].get("pages", {}).values():
            if "missing" not in page:
                existing.add(page["title"][len("File:") :].replace("_", " "))
        time.sleep(0.2)
    return existing


def image_urls(filename):
    quoted = urllib.parse.quote(filename.replace(" ", "_"), safe="")
    return (
        f"http://commons.wikimedia.org/wiki/Special:FilePath/{quoted}",
        f"https://commons.wikimedia.org/wiki/File:{quoted}",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    lines = CSV.read_text(encoding="utf-8").split("\n")
    header = lines[0].split(",")
    rows = [line.split(",") for line in lines[1:]]
    for column in ("image", "image_page", "wikidata"):
        if column not in header:
            header.append(column)
            for row in rows:
                row.append("")
    index = {column: header.index(column) for column in header}

    # このスクリプトが管理するCommons画像は毎回組み直し、EXCLUDEDの追加や
    # Wikipedia側の変更がCSVへ確実に反映されるようにする。
    for row in rows:
        if "commons.wikimedia.org" in row[index["image"]]:
            row[index["image"]] = ""
            row[index["image_page"]] = ""
            row[index["wikidata"]] = ""

    cache = {}
    if CACHE.exists() and not args.refresh:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    elif args.refresh:
        for row in rows:
            row[index["image"]] = ""
            row[index["image_page"]] = ""
            row[index["wikidata"]] = ""

    words = sorted({row[index["original"]] for row in rows})
    pending = [word for word in words if word not in cache]
    print(f"対象 {len(words)} 語 / 問い合わせ {len(pending)} 語")
    CACHE.parent.mkdir(exist_ok=True)
    for offset in range(0, len(pending), BATCH):
        batch = pending[offset : offset + BATCH]
        cache.update(lookup_batch(batch))
        CACHE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"  jawiki {min(offset + BATCH, len(pending))}/{len(pending)}")
        time.sleep(0.5)

    need_p18 = {
        word: item["qid"]
        for word, item in cache.items()
        if item.get("status") == "noimage"
        and item.get("qid")
        and "p18" not in item
    }
    if need_p18:
        print(f"P18フォールバック {len(need_p18)} 語")
        p18 = fetch_p18(need_p18.values())
        for word, qid in need_p18.items():
            cache[word]["p18"] = p18.get(qid, "")

    candidates = {}
    for word, item in cache.items():
        if word in EXCLUDED:
            continue
        filename = item.get("file", "")
        source = "jawiki"
        if not filename and item.get("p18"):
            filename = item["p18"]
            source = "wikidata-p18"
        if filename.lower().endswith(IMAGE_EXT):
            candidates[word] = (filename, source)
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    for word, filename in overrides.items():
        if filename.lower().endswith(IMAGE_EXT):
            candidates[word] = (filename, "reviewed-override")

    existing = commons_files(filename for filename, _ in candidates.values())
    report = [
        "original\tcategory\tdecade\tarticle\tfile\tsource\tdescription"
    ]
    filled = 0
    by_category = {}
    by_decade = {}
    for row in rows:
        word = row[index["original"]]
        candidate = candidates.get(word)
        if not candidate or candidate[0].replace("_", " ") not in existing:
            continue
        filename, source = candidate
        row[index["image"]], row[index["image_page"]] = image_urls(filename)
        row[index["wikidata"]] = cache.get(word, {}).get("qid", "")
        filled += 1
        category = row[index["category"]]
        decade = row[index["decade"]]
        by_category[category] = by_category.get(category, 0) + 1
        by_decade[decade] = by_decade.get(decade, 0) + 1
        report.append(
            "\t".join(
                (
                    word,
                    category,
                    decade,
                    cache.get(word, {}).get("article", ""),
                    filename,
                    source,
                    row[index["description"]],
                )
            )
        )

    CSV.write_text(
        "\n".join([",".join(header)] + [",".join(row) for row in rows]),
        encoding="utf-8",
    )
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    REPORT.write_text("\n".join(report), encoding="utf-8")
    missing_report = ["original\tcategory\tdecade\tdescription"]
    for row in rows:
        if not row[index["image"]]:
            missing_report.append(
                "\t".join(
                    (
                        row[index["original"]],
                        row[index["category"]],
                        row[index["decade"]],
                        row[index["description"]],
                    )
                )
            )
    MISSING_REPORT.write_text("\n".join(missing_report), encoding="utf-8")

    print(
        f"\n付与 {filled}/{len(rows)} 行、未取得 {len(rows) - filled} 行"
        f"(意味レビュー除外 {len(EXCLUDED)} 語)"
    )
    print("カテゴリ別 " + " ".join(f"{k}:{v}" for k, v in sorted(by_category.items())))
    print(f"レビュー用一覧: {REPORT}")
    print(f"生成候補一覧: {MISSING_REPORT}")


if __name__ == "__main__":
    main()
