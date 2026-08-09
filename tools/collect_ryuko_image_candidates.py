#!/usr/bin/env python3
"""Collect second-pass Commons candidates for ryuko rows without images.

Sources:
- Images embedded in the matching Japanese Wikipedia article
- Exact-term Wikimedia Commons file search

The output is review input only. Nothing is applied to ryuko.csv until a
reviewed word-to-file mapping is added to tools/ryuko_image_overrides.json.
"""

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "ryuko.csv"
LOOKUP_CACHE = ROOT / "tools" / ".cache" / "ryuko_images.json"
CANDIDATE_CACHE = ROOT / "tools" / ".cache" / "ryuko_image_candidates.json"
REPORT = ROOT / "tools" / ".cache" / "ryuko_image_candidates.tsv"

JA_API = "https://ja.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
UA = (
    "soramimic-wordlists/collect_ryuko_image_candidates "
    "(https://github.com/soramimic/soramimic-wordlists)"
)
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".svg", ".gif", ".webp")
SKIP_PARTS = (
    "commons-logo",
    "disambig",
    "confusion",
    "question_book",
    "folder",
    "edit-",
    "symbol",
    "stub",
    "replace_this_image",
    "no_image",
    "flag_of_",
    "map.svg",
    "logo.svg",
    "wordmark",
)


def api_get(url, params):
    params = dict(params, format="json", maxlag=5)
    request = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA}
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except Exception:  # noqa: BLE001 - bounded retry, then propagate
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def usable(filename):
    lowered = filename.lower().replace(" ", "_")
    return lowered.endswith(IMAGE_EXT) and not any(part in lowered for part in SKIP_PARTS)


def article_images(title):
    data = api_get(
        JA_API,
        {
            "action": "query",
            "titles": title,
            "redirects": 1,
            "prop": "images",
            "imlimit": 50,
        },
    )
    pages = data.get("query", {}).get("pages", {}).values()
    result = []
    for page in pages:
        for item in page.get("images", []):
            filename = item["title"].removeprefix("ファイル:").removeprefix("File:")
            if usable(filename):
                result.append(filename)
    return result


def commons_search(word):
    data = api_get(
        COMMONS_API,
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": f'"{word}"',
            "gsrnamespace": 6,
            "gsrlimit": 10,
        },
    )
    pages = sorted(
        data.get("query", {}).get("pages", {}).values(),
        key=lambda page: page.get("index", 999),
    )
    result = []
    for page in pages:
        filename = page["title"].removeprefix("File:")
        if usable(filename):
            result.append(filename)
    return result


def main():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    missing = [row for row in rows if not row["image"]]
    lookup = json.loads(LOOKUP_CACHE.read_text(encoding="utf-8"))
    cache = {}
    if CANDIDATE_CACHE.exists():
        cache = json.loads(CANDIDATE_CACHE.read_text(encoding="utf-8"))

    for number, row in enumerate(missing, start=1):
        word = row["original"]
        if word in cache:
            continue
        item = lookup.get(word, {})
        article = item.get("article", "")
        embedded = []
        if item.get("status") == "noimage" and article:
            embedded = article_images(article)
            time.sleep(0.1)
        searched = commons_search(word)
        cache[word] = {
            "article": article,
            "article_images": embedded,
            "search_images": searched,
        }
        if number % 50 == 0:
            CANDIDATE_CACHE.write_text(
                json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print(f"{number}/{len(missing)}")
        time.sleep(0.1)

    CANDIDATE_CACHE.parent.mkdir(exist_ok=True)
    CANDIDATE_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    lines = [
        "original\tcategory\tdecade\troute\trank\tarticle\tfile\tdescription"
    ]
    candidate_words = 0
    for row in missing:
        word = row["original"]
        item = cache.get(word, {})
        candidates = []
        seen = set()
        for route, files in (
            ("article", item.get("article_images", [])),
            ("search", item.get("search_images", [])),
        ):
            for rank, filename in enumerate(files, start=1):
                normalized = filename.replace("_", " ")
                if normalized in seen:
                    continue
                seen.add(normalized)
                candidates.append((route, rank, filename))
        if candidates:
            candidate_words += 1
        for route, rank, filename in candidates:
            lines.append(
                "\t".join(
                    (
                        word,
                        row["category"],
                        row["decade"],
                        route,
                        str(rank),
                        item.get("article", ""),
                        filename,
                        row["description"],
                    )
                )
            )
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"候補あり {candidate_words}/{len(missing)} 語、"
        f"候補 {len(lines) - 1} 件: {REPORT}"
    )


if __name__ == "__main__":
    main()
