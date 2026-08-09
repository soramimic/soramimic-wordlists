#!/usr/bin/env python3
"""baseball.csv にNPB現役の未収録選手を追記する(既存行は書き換えない)。

出典: Wikipedia日本語版の各球団ロースターテンプレート
「Template:〇〇の選手・スタッフ」(CC BY-SA 4.0)と選手記事の冒頭文。

- 支配下選手・育成選手のセクションのみ対象(監督・コーチは除外)
- 登録名はテンプレートのリンク表示([[本名|登録名]])と「本名:」記載から取得
- 姓名分割と読みは記事冒頭「姓 名(せい めい、」から取得(カタカナに変換)
- 既存との照合は type=full の surface(異体字を正規化)
- 記事が無い新人・冒頭が野球選手の記事でないもの(同姓同名)はスキップして報告

usage: python3 tools/update_baseball.py
"""

import csv
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpnames import (DISAMBIG, KATAKANA, LINK, fetch_extracts, images_for_titles,
                     make_player_description, parse_person, template_wikitext,
                     vnorm, write_csv_no_trailing_newline)

TEAMS = {
    "読売ジャイアンツ": "巨人", "東京ヤクルトスワローズ": "ヤクルト",
    "横浜DeNAベイスターズ": "DeNA", "中日ドラゴンズ": "中日",
    "阪神タイガース": "阪神", "広島東洋カープ": "広島",
    "オリックス・バファローズ": "オリックス", "福岡ソフトバンクホークス": "ソフトバンク",
    "埼玉西武ライオンズ": "西武", "東北楽天ゴールデンイーグルス": "楽天",
    "千葉ロッテマリーンズ": "ロッテ", "北海道日本ハムファイターズ": "日本ハム",
}
CSV_PATH = Path(__file__).resolve().parent.parent / "baseball.csv"


def roster(team: str) -> list:
    wt = template_wikitext(f"Template:{team}の選手・スタッフ")
    if wt is None:
        raise RuntimeError(f"template not found: {team}")
    players, section, position = [], "", ""
    for line in wt.splitlines():
        mt = re.search(r"\|\s*title\s*=\s*(.+)", line)
        if mt and "Navbox" not in mt.group(1):
            section = mt.group(1).strip()
            position = ""
        mg = re.search(r"\|\s*group\d+\s*=\s*(.+)", line)
        if mg:
            group = mg.group(1).strip()
            position = group if group in ("投手", "捕手", "内野手", "外野手") else ""
        if not line.strip().startswith("*") or "選手" not in section:
            continue
        for target, display in LINK.findall(line):
            players.append((DISAMBIG.sub("", target.strip()),
                            (display or target).strip(), position))
            break
    return players


def main() -> int:
    old_rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    for r in old_rows:
        r.setdefault("image", "")
        r.setdefault("image_page", "")
        r.setdefault("description", "")
        r.setdefault("position", "")
    # 選手グループ: type=fullのsurface(異体字正規化) -> そのid
    full_to_id = {vnorm(r["surface"]): r["id"] for r in old_rows if r["type"] == "full"}
    rows_by_id = {}
    for r in old_rows:
        rows_by_id.setdefault(r["id"], []).append(r)
    existing_full = set(full_to_id)

    all_players = {}
    for team, short in TEAMS.items():
        for article, display, position in roster(team):
            all_players.setdefault(article, (display, short, position))
        time.sleep(0.5)
    if not 800 <= len(all_players) <= 1500:
        print(f"error: implausible roster size: {len(all_players)}", file=sys.stderr)
        return 1

    # 現役ロースター全員の画像(リンク先記事=本人なので同姓同名事故なし)
    images = images_for_titles(sorted(all_players))
    print(f"画像あり: {len(images)}/{len(all_players)}")

    # 既存選手: 移籍していればteamに「-球団」を追記、画像が空なら付与
    team_updates = img_updates = position_updates = 0
    for article, (display, club, position) in all_players.items():
        gid = full_to_id.get(vnorm(article))
        if gid is None:
            continue
        for r in rows_by_id.get(gid, []):
            if club not in r["team"]:
                r["team"] = f"{r['team']}-{club}"
                team_updates += 1
            if not r["image"] and article in images:
                r["image"], r["image_page"] = images[article]
                img_updates += 1
            if not r["position"] and position:
                r["position"] = position
                position_updates += 1
    if team_updates:
        print(f"移籍によるteam追記: {team_updates}行")
    print(f"既存行への画像付与: {img_updates}行")
    print(f"既存行へのposition付与: {position_updates}行")

    new_players = {a: v for a, v in all_players.items()
                   if vnorm(a) not in existing_full}
    extracts = fetch_extracts(sorted(new_players))

    added, flagged, no_article = [], [], []
    for article in sorted(new_players):
        display, team, position = new_players[article]
        text = extracts.get(article, "")
        if not text:
            no_article.append(article)
            continue
        if "野球" not in text:
            flagged.append((article, "野球選手の記事でない可能性"))
            continue
        parsed = parse_person(article, text)
        if parsed is None:
            flagged.append((article, text[:60].replace("\n", " ")))
            continue
        f_s, f_y, g_s, g_y, full_s, full_y, reg_from_title = parsed
        if vnorm(full_s) in existing_full:
            continue  # 記事名が登録名で、本名では収録済み
        if reg_from_title and reg_from_title != display:
            display = reg_from_title
        if f_s and not KATAKANA.match(full_s):
            full_y = f"{f_y} {g_y}"
        rid = f"{full_s}_{team}_00000"
        rows = []
        if f_s:
            rows.append((full_s, f_s, f_y, "family"))
        if g_s:
            rows.append((full_s, g_s, g_y, "given"))
        rows.append((full_s, full_s, full_y, "full"))
        if vnorm(display) not in {vnorm(x) for x in (f_s, g_s, full_s) if x}:
            if KATAKANA.match(display):
                rows.append((f"{display}({full_s})", display, display, "registered"))
            elif display == g_s:
                rows.append((f"{display}({full_s})", display, g_y, "registered"))
            else:
                flagged.append((article, f"登録名の読み不明: {display}"))
        img, img_page = images.get(article, ("", ""))
        description = make_player_description(text, article)
        for original, surface, pron, typ in rows:
            added.append({"id": rid, "original": original, "team": team,
                          "surface": surface, "pronunciation": pron,
                          "type": typ, "org_id": rid,
                          "image": img, "image_page": img_page,
                          "description": description, "position": position})
        print(f"added: {full_s} ({team})")

    cols = ["id", "original", "team", "surface", "pronunciation", "type",
            "org_id", "image", "image_page", "position", "description"]
    write_csv_no_trailing_newline(CSV_PATH, cols, old_rows + added)

    n_add = len({r["id"] for r in added})
    print(f"baseball.csv: +{n_add}選手 ({len(added)}行), "
          f"記事未作成スキップ {len(no_article)}, 要確認 {len(flagged)}")
    for a, why in flagged:
        print(f"  要確認: {a} | {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
