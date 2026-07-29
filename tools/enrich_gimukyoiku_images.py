#!/usr/bin/env python3
"""gimukyoiku.csv に Wikipedia/Commons の画像を付与する。

方針(ADR 00027):
- ja.wikipedia の「語と完全一致する記事」(リダイレクト追従あり)のリード画像
  (pageimages、自由ライセンスのみ)を採用する
- 曖昧さ回避ページ・記事なし・画像なしの行は空のまま(同名異義の取り違えを
  避けるため、検索や部分一致では引かない)
- 画像は Wikimedia Commons にあるファイルだけ使う(jawiki ローカルの
  非自由ファイルを除外)。image は Special:FilePath、image_page は
  Commons の File: ページ(ライセンス確認先)
- wikidata 列には画像の取得元になった記事の QID を入れる(画像とセットで
  埋まる。sekitsui/plant と同じ扱い)
- 完全一致でも語義が違う誤マッチ(教科の文脈と別の意味の記事)は EXCLUDED に
  恒久除外として追記する(理由コメント付き。insect の EXCLUDED と同じ流儀)

使い方:
  python3 tools/enrich_gimukyoiku_images.py            # 空欄のみ付与
  python3 tools/enrich_gimukyoiku_images.py --refresh  # キャッシュを引き直す

取得結果は tools/.cache/gimukyoiku_images.json に保存し、中断しても再実行で
続きから再開する。レビュー用の一覧を tools/.cache/gimukyoiku_image_report.tsv
に出力する。
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "gimukyoiku.csv"
CACHE = ROOT / "tools" / ".cache" / "gimukyoiku_images.json"
REPORT = ROOT / "tools" / ".cache" / "gimukyoiku_image_report.tsv"

JA_API = "https://ja.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
UA = "soramimic-wordlists/enrich_gimukyoiku_images (https://github.com/soramimic/soramimic-wordlists)"
BATCH = 40

# 画像として扱える拡張子(PDF・動画・TIFFなどのリード"画像"を弾く)
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".svg", ".gif", ".webp")

# 完全一致でも語義が違う誤マッチ等の恒久除外(語: 理由)。2026-07-29 全件AIレビューによる
EXCLUDED = {
    # 記事が教科の文脈と別の意味
    "シャープ": "記事はシャープ株式会社(音楽記号ではない)",
    "スメタナ": "記事は発酵乳(作曲家ではない)",
    "魔王": "記事は悪魔の王(シューベルトの歌曲ではない)",
    "赤とんぼ": "記事は昆虫(童謡ではない)",
    "かたつむり": "記事は巻貝(唱歌ではない)",
    "明暗": "記事は漱石の小説(陰影表現ではない)",
    "バレン": "記事はアイルランドの地形(版画のばれんではない)",
    "凸版": "TOPPANホールディングスへのリダイレクト(版式ではない)",
    "ゲルニカ": "記事はバスクの自治体(ピカソの絵ではない)",
    "握手": "記事は挨拶(井上ひさしの小説ではない)",
    "トロッコ": "記事は鉱山の貨車(芥川の短編ではない)",
    "高瀬舟": "記事は川舟(鴎外の小説ではない。画像は川面)",
    "ツバメ": "記事は鳥(鉄棒の技ではない)",
    "ゆりかご": "記事は揺り籠(マット運動の技ではない)",
    "台風の目": "記事は気象現象(運動会種目ではない)",
    "反射": "記事は波の反射(生物の反射ではない)",
    "基数": "記事は集合論の濃度(基数詞ではない)",
    # 記事は正しいが画像が語を表していない
    "元素記号": "リード画像が家紋",
    "風神雷神図屏風": "画像が敦煌の阿修羅(宗達の屏風ではない)",
    "数直線": "直線へのリダイレクトで画像が空白プレースホルダ",
    "半直線": "直線へのリダイレクトで画像が空白プレースホルダ",
    "最後の晩餐": "画像がレオナルド作品ではなく別のイコン",
    "木彫": "彫刻へのリダイレクトで画像が大理石像",
    "凹版": "画像が凸版印刷の工房",
    "ヨウ素液": "ヨウ化カリウムへのリダイレクトで画像がKI結晶",
    "質量保存の法則": "画像がベルヌーイの定理の図",
    "振動数": "画像が汎用の物理アイコン",
    "電気抵抗": "画像が汎用の物理アイコン",
    "かさ歯車": "歯車へのリダイレクトで画像が平歯車",
    "いちょう切り": "画像が切り方一覧共通のタイの飾り切り",
    "半月切り": "画像が切り方一覧共通のタイの飾り切り",
    "乱切り": "画像が切り方一覧共通のタイの飾り切り",
    "輪切り": "画像が切り方一覧共通のタイの飾り切り",
    "小口切り": "画像が切り方一覧共通のタイの飾り切り",
    "ささがき": "画像が切り方一覧共通のタイの飾り切り",
    "五大栄養素": "画像が授乳中の乳児",
    "保健": "画像がOECD社会支出グラフ",
    "近郊農業": "画像が古代エジプト墓室壁画",
    "長唄": "画像が山東京伝の盃",
    "画板": "画像が三岸節子の書影",
    "和歌": "画像が原稿用紙の文學の文字",
    "自由民権運動": "画像が汎用の黄色い旗",
    "市場経済": "画像が汎用の黄色い旗",
}


def api_get(url, params):
    params = dict(params, format="json", maxlag=5)
    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as f:
                return json.load(f)
        except Exception as e:  # noqa: BLE001 - リトライして最後に伝播
            if attempt == 2:
                raise
            print(f"  retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(5)


def lookup_batch(titles):
    """語 -> {status, file, qid} を返す。statusは ok/missing/disambig/noimage。"""
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
    q = data["query"]
    norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
    redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
    pages = {p["title"]: p for p in q.get("pages", {}).values()}
    out = {}
    for t in titles:
        resolved = norm.get(t, t)
        resolved = redir.get(resolved, resolved)
        p = pages.get(resolved)
        if not p or "missing" in p:
            out[t] = {"status": "missing"}
        elif "disambiguation" in p.get("pageprops", {}):
            out[t] = {"status": "disambig"}
        elif not p.get("pageimage"):
            out[t] = {"status": "noimage", "qid": p.get("pageprops", {}).get("wikibase_item", "")}
        else:
            out[t] = {
                "status": "ok",
                "file": p["pageimage"],
                "qid": p.get("pageprops", {}).get("wikibase_item", ""),
                "article": resolved,
            }
    return out


def on_commons(files):
    """Commons に実在するファイル名の集合を返す(jawikiローカル画像を除外)。"""
    ok = set()
    files = sorted(set(files))
    for i in range(0, len(files), 50):
        batch = files[i : i + 50]
        data = api_get(
            COMMONS_API,
            {"action": "query", "titles": "|".join("File:" + f for f in batch)},
        )
        q = data["query"]
        norm = {n["to"]: n["from"] for n in q.get("normalized", [])}
        for p in q.get("pages", {}).values():
            if "missing" not in p:
                title = norm.get(p["title"], p["title"])
                ok.add(title[len("File:"):])
        time.sleep(0.5)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="キャッシュを無視して引き直す")
    args = ap.parse_args()

    lines = CSV.read_text(encoding="utf-8").split("\n")
    header = lines[0].split(",")
    rows = [l.split(",") for l in lines[1:]]
    for col in ("image", "image_page", "wikidata"):
        if col not in header:
            header.append(col)
            for r in rows:
                r.append("")
    idx = {c: header.index(c) for c in header}

    cache = {}
    if CACHE.exists() and not args.refresh:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    # 空欄と Commons 由来の行は毎回引き直す(EXCLUDED 追加を反映できるように)。
    # Release 等の他ソースの URL(将来のAI生成画像)は触らない
    targets = [
        r
        for r in rows
        if not r[idx["image"]] or "commons.wikimedia.org" in r[idx["image"]]
    ]
    for r in targets:
        r[idx["image"]] = r[idx["image_page"]] = r[idx["wikidata"]] = ""
    pending = sorted({r[idx["original"]] for r in targets if r[idx["original"]] not in cache})
    print(f"対象 {len(targets)} 行 / 問い合わせ {len(pending)} 語(キャッシュ済み {len(targets) - len(pending)})")

    for i in range(0, len(pending), BATCH):
        batch = pending[i : i + BATCH]
        cache.update(lookup_batch(batch))
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  jawiki {min(i + BATCH, len(pending))}/{len(pending)}")
        time.sleep(1)

    candidates = {
        w: c
        for w, c in cache.items()
        if c.get("status") == "ok"
        and w not in EXCLUDED
        and c["file"].lower().endswith(IMAGE_EXT)
    }
    commons_ok = on_commons([c["file"] for c in candidates.values()])

    stats = {}
    report = ["original\tsubject\tfile\tdescription"]
    for r in targets:
        word = r[idx["original"]]
        subj = r[idx["subject"]]
        c = cache.get(word, {})
        st = stats.setdefault(subj.split("/")[0], dict(n=0, ok=0))
        st["n"] += 1
        if word in EXCLUDED or c.get("status") != "ok" or c["file"] not in commons_ok:
            continue
        fname = c["file"].replace(" ", "_")
        quoted = urllib.parse.quote(fname, safe="")
        r[idx["image"]] = f"http://commons.wikimedia.org/wiki/Special:FilePath/{quoted}"
        r[idx["image_page"]] = f"https://commons.wikimedia.org/wiki/File:{quoted}"
        r[idx["wikidata"]] = c.get("qid", "")
        st["ok"] += 1
        report.append(f"{word}\t{subj}\t{c['file']}\t{r[idx['description']]}")

    CSV.write_text("\n".join([",".join(header)] + [",".join(r) for r in rows]), encoding="utf-8")
    REPORT.write_text("\n".join(report), encoding="utf-8")

    total_ok = sum(s["ok"] for s in stats.values())
    print(f"\n付与: {total_ok} 行(除外 {len(EXCLUDED)} 語)")
    for subj, s in sorted(stats.items()):
        print(f"  {subj}: {s['ok']}/{s['n']}")
    print(f"レビュー用一覧: {REPORT}")


if __name__ == "__main__":
    main()
