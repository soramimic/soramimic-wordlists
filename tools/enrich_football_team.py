#!/usr/bin/env python3
"""football.csv に所属クラブ(team列)を付与する。baseball.csv の team と同じ役割。

出典は既存の football 更新と同じ2つ。
- Wikipedia日本語版 (CC BY-SA 4.0): 「Template:日本プロサッカーリーグ」から
  J1〜J3のクラブを取り、各クラブの「Template:〇〇のメンバー」に載っている
  選手・監督を現役の所属として採る(update_football.py と同じ経路)。
  Wikidataは移籍への追従が遅れるため、現役はこちらを優先する
- Wikidata (CC0): 上で拾えない歴代の選手は所属クラブ(P54)から代表的な1つを
  選ぶ。監督(category=manager)は P54 が現役時代の所属になってしまうので、
  監督を務めたチーム(P6087)だけを見る

代表的な1クラブの決め方(P54/P6087が複数あるとき):
  1. 取り消された(deprecated)文は使わない
  2. 「在籍終了日(P582)が無い = 現所属」を最優先
  3. 次に終了日が新しいもの、さらに開始日(P580)が新しいもの
  4. それでも並ぶときは Wikidata 上の記載順で後のもの
  つまり「最新の所属」を採る。代表チーム(〜代表)はクラブではないので除く

- 既存の team が空の行だけ埋める(冪等)。`--refresh` で全行引き直し。
  他の列は変更しない。team 列が無ければ original の後ろに追加する
  (baseball.csv と同じ位置)
- マスコット(category=mascot)は人物ではなくクラブ側の情報なので対象外。空のまま
- 取得結果は tools/.cache/ に逐次保存するので、中断しても再実行で再開できる

usage:
  python3 tools/enrich_football_team.py [--refresh]
"""

import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_football import NOISE, j_clubs  # noqa: E402
from wpnames import (DISAMBIG, LINK, UA, WD_API, template_wikitext,  # noqa: E402
                     titles_to_qids, vnorm, write_csv_no_trailing_newline)

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "football.csv"
CACHE = Path(__file__).resolve().parent / ".cache" / "football_team.json"

# 選手の所属クラブ / 監督を務めたチーム
CLUB_PROPS = {"player": "P54", "manager": "P6087"}
# クラブとして扱わない instance of(各国代表チーム)
NATIONAL_TEAM = {"Q6979593", "Q21945604", "Q1194951"}
# ラベルに含まれていたら代表チームとみなす語
NATIONAL_RE = re.compile(r"代表$|代表チーム|U-\d+日本")
# wbgetentities の ids は1回50件まで
BATCH = 50
SLEEP = 0.3
# team が埋まった行がこれを下回ったら取得失敗とみなして書き込まない
MIN_TOTAL = 3000


def load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {"roster": {}, "titles": {}, "picks": {}, "clubs": {}}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def wd_entities(qids: list[str], props: str) -> dict:
    url = WD_API + "?" + urllib.parse.urlencode({
        "action": "wbgetentities", "ids": "|".join(qids), "props": props,
        "languages": "ja|en", "format": "json"})
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as res:
                return json.load(res).get("entities", {})
        except Exception as ex:
            print(f"retry {attempt}: {ex}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("wikidata api failed")


def club_members(club: str) -> dict[str, str]:
    """「Template:〇〇のメンバー」から {記事タイトル: player|manager}。
    update_football.club_players と同じ読み方だが、監督も拾う。"""
    wt = template_wikitext(f"Template:{club}のメンバー")
    if wt is None:
        return {}
    members: dict[str, str] = {}
    mode = None
    for line in wt.splitlines():
        mg = re.search(r"\|\s*group\d+\s*=\s*(.+)", line)
        if mg:
            g = mg.group(1).strip()
            mode = ("player" if g in ("選手", "GK", "DF", "MF", "FW")
                    else "manager" if g in ("監督", "監督・コーチ") else None)
        if mode is None or not line.strip().startswith("*"):
            continue
        for t, _disp in LINK.findall(line):
            if NOISE.search(t):
                continue
            members.setdefault(DISAMBIG.sub("", t.strip()), mode)
            break  # 行の最初のリンクのみ(注釈リンクを拾わない)
    return members


def fetch_rosters(cache: dict) -> None:
    """現役ロースターを取り込む。cache["roster"]: 照合キー -> クラブ名。"""
    if cache["roster"]:
        return  # 既に取得済み(引き直したいときはキャッシュを消す)
    clubs = j_clubs()
    if not 50 <= len(clubs) <= 80:
        raise RuntimeError(f"implausible club count: {len(clubs)}")
    roster: dict[str, str] = {}
    for club in clubs:
        members = club_members(club)
        for article in members:
            roster.setdefault(key_of(article), club)
        print(f"{club}: {len(members)}人", flush=True)
        time.sleep(SLEEP)
    cache["roster"] = roster
    save_cache(cache)


def key_of(name: str) -> str:
    """CSVのoriginalと記事タイトルを突き合わせるための正規化キー。"""
    return vnorm(name.replace(" ", "").replace("　", "").replace("・", ""))


def title_candidates(original: str) -> list[str]:
    """originalから記事タイトル候補を作る(日本人は空白なし、外国人は中黒)。"""
    out = [original]
    for c in (original.replace(" ", ""), original.replace(" ", "・")):
        if c not in out:
            out.append(c)
    return out


def resolve_titles(names: list[str], cache: dict) -> None:
    """記事タイトル -> QID をキャッシュに詰める。"""
    todo = [n for n in names if n not in cache["titles"]]
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        cands = []
        for n in chunk:
            for c in title_candidates(n):
                if c not in cands:
                    cands.append(c)
        t2q = titles_to_qids(cands)
        for n in chunk:
            cache["titles"][n] = next(
                (t2q[c] for c in title_candidates(n) if c in t2q), "")
        save_cache(cache)
        print(f"記事→QID: {i + len(chunk)}/{len(todo)}", flush=True)


def sort_key(cand: list) -> tuple:
    """新しい所属ほど大きくなるキー。cand は [開始日, 終了日, 記載順, クラブQID]。

    在籍中(開始日があって終了日が無い)> 終了した所属(終了日が新しい順)>
    日付が全く無い文、の順。日付なしを「終了日が無い=在籍中」と見なすと、
    古い所属が最新扱いになる(イビチャ・オシムのジェリェズニチャル)ため
    別扱いにする。"""
    start, end, idx = cand[0], cand[1], cand[2]
    if end:
        return (1, end, start, idx)
    if start:
        return (2, "", start, idx)  # 在籍中
    return (0, "", "", idx)


def fetch_picks(qid_roles: dict[str, str], cache: dict) -> None:
    """人物QID -> [開始日, 終了日, 記載順, クラブQID] の一覧。並べ替えは
    使うときに sort_key で行う(選び方を変えても引き直さなくて済むように、
    キャッシュには生の日付を持たせる)。"""
    todo = sorted(q for q in qid_roles if q not in cache["picks"])
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        ents = wd_entities(chunk, "claims")
        for q in chunk:
            prop = CLUB_PROPS[qid_roles[q]]
            cands = []
            for idx, c in enumerate(ents.get(q, {}).get("claims", {}).get(prop, [])):
                if c.get("rank") == "deprecated":
                    continue  # 取り消された文は使わない
                dv = c.get("mainsnak", {}).get("datavalue")
                if not dv:
                    continue
                qual = c.get("qualifiers", {})

                def t(prop_id: str) -> str:
                    v = qual.get(prop_id, [{}])[0].get("datavalue", {}).get("value", {})
                    return v.get("time", "") if isinstance(v, dict) else ""

                cands.append([t("P580"), t("P582"), idx, dv["value"]["id"]])
            cache["picks"][q] = cands
        save_cache(cache)
        print(f"所属クラブ(P54/P6087): {i + len(chunk)}/{len(todo)}", flush=True)
        time.sleep(SLEEP)


def fetch_clubs(qids: list[str], cache: dict) -> None:
    """クラブQID -> 表示名。代表チームは空文字にして候補から外す。"""
    todo = sorted(q for q in qids if q not in cache["clubs"])
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        ents = wd_entities(chunk, "labels|claims")
        for q in chunk:
            e = ents.get(q, {})
            labels = e.get("labels", {})
            name = (labels.get("ja") or labels.get("en") or {}).get("value", "")
            insts = {c.get("mainsnak", {}).get("datavalue", {})
                      .get("value", {}).get("id")
                     for c in e.get("claims", {}).get("P31", [])}
            if insts & NATIONAL_TEAM or NATIONAL_RE.search(name):
                name = ""  # 代表チームはクラブではない
            cache["clubs"][q] = sanitize(name)
        save_cache(cache)
        print(f"クラブ名: {i + len(chunk)}/{len(todo)}", flush=True)
        time.sleep(SLEEP)


def sanitize(s: str) -> str:
    # 素朴なsplit(",")のパーサを壊す文字は置換する
    return s.replace(",", "、").replace('"', "”").strip()


def add_column(header: list[str]) -> list[str]:
    """team 列を original の後ろに追加する(baseball.csv と同じ位置)。"""
    cols = list(header)
    if "team" not in cols:
        cols.insert(cols.index("original") + 1 if "original" in cols else len(cols),
                    "team")
    return cols


def main(argv: list[str]) -> int:
    refresh = "--refresh" in argv[1:]
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        cols = add_column(reader.fieldnames)

    cache = load_cache()
    targets = [r for r in rows
               if r["category"] in CLUB_PROPS and (refresh or not r.get("team"))]

    # 1) 現役ロースター(Wikipedia)。移籍への追従が速いのでこちらを優先する
    fetch_rosters(cache)
    roster = cache["roster"]
    rest = {}  # original -> player|manager
    for r in targets:
        if key_of(r["original"]) not in roster:
            rest.setdefault(r["original"], r["category"])

    # 2) 残りは Wikidata
    resolve_titles(sorted(rest), cache)
    qid_roles = {}
    for name, role in rest.items():
        q = cache["titles"].get(name)
        if q:
            qid_roles.setdefault(q, role)
    fetch_picks(qid_roles, cache)
    fetch_clubs(sorted({c[3] for q in qid_roles for c in cache["picks"].get(q, [])}),
                cache)

    def wd_team(name: str) -> str:
        q = cache["titles"].get(name)
        cands = sorted(cache["picks"].get(q, []) if q else [],
                       key=sort_key, reverse=True)
        for c in cands:
            # 代表チームは fetch_clubs で空にしてあるので次の候補に送られる
            if cache["clubs"].get(c[3]):
                return cache["clubs"][c[3]]
        return ""

    from_roster = from_wd = 0
    for r in targets:
        hit = roster.get(key_of(r["original"]))
        if hit:
            r["team"] = sanitize(hit)
            from_roster += 1
        else:
            r["team"] = wd_team(r["original"])
            from_wd += 1 if r["team"] else 0
    for r in rows:
        for c in cols:
            r.setdefault(c, "")

    have = sum(1 for r in rows if r["team"])
    if have < MIN_TOTAL:
        print(f"error: implausible team count: {have}", file=sys.stderr)
        return 1

    write_csv_no_trailing_newline(CSV_PATH, cols, rows)
    people = len({r["original"] for r in rows})
    with_team = len({r["original"] for r in rows if r["team"]})
    print(f"football.csv: team {have}/{len(rows)}行 "
          f"({with_team}/{people}人)、今回 ロースター{from_roster}行 "
          f"+ Wikidata{from_wd}行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
