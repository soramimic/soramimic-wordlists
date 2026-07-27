#!/usr/bin/env python3
"""pokemon.csv を PokéAPI の公式データから再生成する。

出典: https://github.com/PokeAPI/pokeapi (data/v2/csv/*.csv)
local_language_id=1 が ja-Hrkt(かな表記)。

収録内容:
- 全種(id=全国図鑑No-1)
- 地方のすがた(アローラ/ガラル/ヒスイ/パルデア)とキョダイマックス:
  表記ゆれ3行を同一idで持つ(種名のみ / 〇〇+種名 / 種名（〇〇のすがた）)。
  括弧は公式表記に合わせ全角
- メガシンカ: フォーム名がそれ自体で完結した名前(メガリザードンX等)なので1行

type1/type2 はポケモンのタイプ(でんき等)。単タイプは type2=NA。
generation は登場世代(1〜9)。種は全国図鑑上の登場世代、フォームは
そのフォームが導入されたバージョングループの世代(メガシンカ=6等)。
idはポケモン単位(種・各フォームで1つ。種とフォームは別ポケモン扱い)。
フォームのidは種の後ろから連番で振り直すため、世代追加時に変わりうる
(永続キーには使わないこと)。

image/image_page は「型色カード」(タイプ配色のみで描いたSVG。キャラクター造形は
使わない)のURLで、**original(名前)から機械的に組み立てる**ため全件再生成でも
保持される。id は振り直されうるのでURLのキーには使わない(名前をキーにすることで、
新種追加でidがずれても既存のURLが別のポケモンのカードを指すことがない)。
カードの実体は tools/gen_pokemon_typecards.py が生成し GitHub Release で配布する。
**新ポケモンが増えた回は gen_pokemon_typecards.py を再実行して Release へ
増分をアップロードすること**(アセットが無い名前は画像が404になる。
取りこぼしは `gen_pokemon_typecards.py --verify` で検出できる)。

usage: python3 tools/update_pokemon.py
"""

import csv
import io
import sys
import unicodedata
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_pokemon_typecards import image_page_url, image_url  # noqa: E402

BASE_URL = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv"
JA_HRKT_LANGUAGE_ID = "1"
# 「種名(〇〇のすがた)」として収録するフォーム名(完全一致)
SUGATA_FORM_NAMES = {
    "アローラのすがた",
    "ガラルのすがた",
    "ヒスイのすがた",
    "パルデアのすがた",
    "キョダイマックスのすがた",
}
OUT_PATH = Path(__file__).resolve().parent.parent / "pokemon.csv"


def fetch_csv(name: str) -> list[dict]:
    with urllib.request.urlopen(f"{BASE_URL}/{name}.csv", timeout=60) as res:
        return list(csv.DictReader(io.StringIO(res.read().decode("utf-8"))))


def norm(text: str) -> str:
    # 全角英数記号は既存リストに合わせて半角へ(ポリゴン2、タイプ:ヌル等)
    return unicodedata.normalize("NFKC", text)


def pron(text: str) -> str:
    # ♀♂は読めないので発音では読みに置換(表記はそのまま残す)
    return text.replace("♀", "メス").replace("♂", "オス")


def main() -> int:
    species_names = {
        int(r["pokemon_species_id"]): norm(r["name"])
        for r in fetch_csv("pokemon_species_names")
        if r["local_language_id"] == JA_HRKT_LANGUAGE_ID
    }
    form_names = {
        int(r["pokemon_form_id"]): norm(r["form_name"])
        for r in fetch_csv("pokemon_form_names")
        if r["local_language_id"] == JA_HRKT_LANGUAGE_ID and r["form_name"]
    }
    type_names = {
        r["type_id"]: r["name"]
        for r in fetch_csv("type_names")
        if r["local_language_id"] == JA_HRKT_LANGUAGE_ID
    }
    pokemon = {r["id"]: r for r in fetch_csv("pokemon")}
    forms = fetch_csv("pokemon_forms")
    species_generation = {
        int(r["id"]): r["generation_id"] for r in fetch_csv("pokemon_species")
    }
    vg_generation = {
        r["id"]: r["generation_id"] for r in fetch_csv("version_groups")
    }

    if not species_names or not form_names or not type_names:
        print("error: Japanese names not found in source", file=sys.stderr)
        return 1
    species_ids = sorted(species_names)
    if species_ids != list(range(1, len(species_ids) + 1)):
        print("error: species ids are not contiguous from 1", file=sys.stderr)
        return 1

    types_by_pokemon: dict[str, list[str]] = {}
    for r in fetch_csv("pokemon_types"):
        types_by_pokemon.setdefault(r["pokemon_id"], []).append(
            type_names[r["type_id"]]
        )

    def type_cols(pokemon_id: str) -> tuple[str, str]:
        ts = types_by_pokemon.get(pokemon_id, [])
        if not ts:
            return "NA", "NA"
        return ts[0], ts[1] if len(ts) > 1 else "NA"

    # 種のデフォルト個体(タイプ参照用)
    default_pokemon: dict[int, str] = {}
    for pid, p in pokemon.items():
        if p["is_default"] == "1":
            default_pokemon[int(p["species_id"])] = pid

    # 収録対象フォームを種ごとにまとめる(同名フォームは重複排除:
    # パルデアタウロスの3種等は1グループにする)
    form_groups: dict[int, list[tuple[str, bool, str, str]]] = {}
    seen: set[tuple[int, str]] = set()
    for f in sorted(forms, key=lambda r: int(r["id"])):
        name = form_names.get(int(f["id"]))
        if name is None:
            continue
        is_mega = f["is_mega"] == "1"
        if not is_mega and name not in SUGATA_FORM_NAMES:
            continue
        sid = int(pokemon[f["pokemon_id"]]["species_id"])
        if (sid, name) in seen:
            continue
        seen.add((sid, name))
        gen = vg_generation[f["introduced_in_version_group_id"]]
        form_groups.setdefault(sid, []).append((name, is_mega, f["pokemon_id"], gen))

    rows: list[list[str]] = []
    next_form_id = len(species_ids)  # フォーム行のidは種の後ろから行ごとに連番
    n_forms = 0
    for sid in species_ids:
        s_name = species_names[sid]
        s_gen = species_generation[sid]
        t1, t2 = type_cols(default_pokemon[sid])
        rows.append([str(sid - 1), s_name, s_name, pron(s_name), t1, t2, s_gen])
        for form_name, is_mega, pokemon_id, f_gen in form_groups.get(sid, []):
            gid = str(next_form_id)
            next_form_id += 1
            n_forms += 1
            t1, t2 = type_cols(pokemon_id)
            if is_mega:
                # メガリザードンX 等はフォーム名が完結した名前
                rows.append([gid, form_name, form_name, pron(form_name), t1, t2, f_gen])
                continue
            original = f"{s_name}（{form_name}）"
            prefix = form_name.removesuffix("のすがた")
            for surface, p in [
                (s_name, pron(s_name)),
                (f"{prefix}{s_name}", pron(f"{prefix}{s_name}")),
                (original, pron(f"{s_name}{form_name}")),
            ]:
                rows.append([gid, original, surface, p, t1, t2, f_gen])

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        ["id", "original", "surface", "pronunciation", "type1", "type2",
         "generation", "image", "image_page"]
    )
    # 型色カードのURLは original(名前)から決定的に組み立てる
    # (全件再生成でも消えず、idが振り直されても同じカードを指す)
    writer.writerows(
        [row + [image_url(row[1]), image_page_url(row[1])] for row in rows]
    )
    # 末尾改行なしで書く(soramimic側のパーサが最終空行で落ちるため)
    OUT_PATH.write_text(buf.getvalue().rstrip("\n"), encoding="utf-8")

    print(f"pokemon.csv: {len(species_ids)} species + {n_forms} forms, {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
