#!/usr/bin/env python3
"""football.csv にJ1〜J3現役の未収録選手を追記する(既存行は書き換えない)。

出典: Wikipedia日本語版。クラブ一覧は「Template:日本プロサッカーリーグ」を
展開してJ1/J2/J3セクションから取得し、各クラブの「Template:〇〇のメンバー」
の選手セクション(GK/DF/MF/FW)から選手記事を集める(CC BY-SA 4.0)。

- スタッフ・マスコット・関連情報セクションは除外
- 姓名分割と読みは記事冒頭から取得(カタカナ)。既存の規約に合わせ、
  日本人は「姓 名」空白区切り、外国人はfamily/given行もsurface=フルネーム
- 記事が無い選手・冒頭がサッカー選手の記事でないもの(同姓同名)はスキップして報告

usage: python3 tools/update_football.py
"""

import csv
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import (DISAMBIG, KATAKANA, LINK, api, fetch_extracts,
                     images_for_titles, make_player_description, parse_person,
                     template_wikitext, vnorm, write_csv_no_trailing_newline)

CSV_PATH = Path(__file__).resolve().parent.parent / "football.csv"
NOISE = re.compile(r"登録選手|キャプテン|一覧|Category|ユース|アカデミー")


def j_clubs() -> list:
    d = api({"action": "expandtemplates", "text": "{{日本プロサッカーリーグ}}",
             "prop": "wikitext"})
    wt = d["expandtemplates"]["wikitext"]
    clubs, mode = [], None
    for m in LINK.finditer(wt):
        t = m.group(1)
        if re.match(r"^J[123]リーグ$", t):
            mode = t
            continue
        if re.search(r"リーグ|協会|法人|シーズン|クラブライセンス|百年構想|"
                     r"ベスト|カップ|プレーオフ|入れ替え戦", t):
            mode = None
            continue
        if mode:
            clubs.append(t)
    return clubs


def club_players(club: str) -> dict:
    wt = template_wikitext(f"Template:{club}のメンバー")
    if wt is None:
        return {}
    players, mode = {}, None
    for line in wt.splitlines():
        mg = re.search(r"\|\s*group\d+\s*=\s*(.+)", line)
        if mg:
            g = mg.group(1).strip()
            mode = g if g in ("GK", "DF", "MF", "FW") else (
                "player" if g == "選手" else None
            )
        if mode is None or not line.strip().startswith("*"):
            continue
        for t, disp in LINK.findall(line):
            if NOISE.search(t):
                continue
            players.setdefault(
                DISAMBIG.sub("", t.strip()),
                ((disp or t).strip(), mode if mode != "player" else ""),
            )
            break  # 行の最初のリンクのみ(注釈リンクを拾わない)
    return players


def main() -> int:
    old_rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    for r in old_rows:
        r.setdefault("image", "")
        r.setdefault("image_page", "")
        r.setdefault("description", "")
        r.setdefault("position", "")
    full_to_id = {vnorm(r["surface"].replace(" ", "")): r["id"]
                  for r in old_rows if r["type"] == "full"}
    rows_by_id = {}
    for r in old_rows:
        rows_by_id.setdefault(r["id"], []).append(r)
    existing_full = set(full_to_id)

    clubs = j_clubs()
    if not 50 <= len(clubs) <= 80:
        print(f"error: implausible club count: {len(clubs)}", file=sys.stderr)
        return 1
    players = {}
    missing_template = []
    for club in clubs:
        ps = club_players(club)
        if not ps:
            missing_template.append(club)
        players.update({a: v for a, v in ps.items() if a not in players})
        time.sleep(0.3)
    if missing_template:
        print("メンバーテンプレートなし:", missing_template)

    # 現役ロースター全員の画像(リンク先記事=本人なので同姓同名事故なし)
    images = images_for_titles(sorted(players))
    print(f"画像あり: {len(images)}/{len(players)}")
    img_updates = position_updates = 0
    for article, (_display, position) in players.items():
        gid = full_to_id.get(vnorm(article.replace(" ", "")))
        if gid is None:
            continue
        for r in rows_by_id.get(gid, []):
            if not r["image"] and article in images:
                r["image"], r["image_page"] = images[article]
                img_updates += 1
            if not r["position"] and position:
                r["position"] = position
                position_updates += 1
    print(f"既存行への画像付与: {img_updates}行")
    print(f"既存行へのposition付与: {position_updates}行")

    new_players = {a: v for a, v in players.items()
                   if vnorm(a.replace(" ", "")) not in existing_full}
    extracts = fetch_extracts(sorted(new_players))

    next_id = max(int(r["id"]) for r in old_rows if r["id"].isdigit()) + 1
    added, flagged, no_article = [], [], []
    for article in sorted(new_players):
        text = extracts.get(article, "")
        if not text:
            no_article.append(article)
            continue
        if "サッカー" not in text and "フットボール" not in text:
            flagged.append((article, "サッカー選手の記事でない可能性"))
            continue
        parsed = parse_person(article, text)
        if parsed is None:
            flagged.append((article, text[:60].replace("\n", " ")))
            continue
        f_s, f_y, g_s, g_y, full_s, full_y, _reg = parsed
        if vnorm(full_s.replace(" ", "")) in existing_full:
            continue
        if KATAKANA.match(full_s.replace(" ", "")):
            # 既存規約: 外国人はfamily/given行もsurface=フルネーム
            original = full_s
            rows = [(full_s, full_y.replace("・", " "), "full")]
            if f_s:
                rows.append((full_s, f_y, "family"))
                rows.append((full_s, g_y, "given"))
        else:
            original = f"{f_s} {g_s}"
            rows = [(original, f"{f_y} {g_y}", "full"),
                    (f_s, f_y, "family"), (g_s, g_y, "given")]
        img, img_page = images.get(article, ("", ""))
        _display, position = new_players[article]
        description = make_player_description(text, article)
        for surface, pron, typ in rows:
            added.append({"id": str(next_id), "original": original,
                          "surface": surface, "pronunciation": pron,
                          "type": typ, "category": "player",
                          "scope": "jleague", "wikidata": "",
                          "image": img, "image_page": img_page,
                          "description": description, "position": position})
        print(f"added: {original}")
        next_id += 1

    cols = ["id", "original", "team", "surface", "pronunciation", "type",
            "category", "scope", "wikidata", "image", "image_page",
            "position", "description"]
    write_csv_no_trailing_newline(CSV_PATH, cols, old_rows + added)

    n_add = len({r["id"] for r in added})
    print(f"football.csv: +{n_add}選手 ({len(added)}行), "
          f"記事未作成スキップ {len(no_article)}, 要確認 {len(flagged)}")
    for a, why in flagged:
        print(f"  要確認: {a} | {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
