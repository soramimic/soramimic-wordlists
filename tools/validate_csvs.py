#!/usr/bin/env python3
"""全CSVがsoramimic側パーサの前提を満たすか検証する(CI用)。

チェック内容:
- 引用符付きフィールドがない(利用側はクオート非対応の素朴なsplit(","))
- 改行コードがLFのみ・末尾改行なし(最終空行でパーサが落ちる)
- 全行がヘッダと同じ列数(素朴なsplitで列ズレしない)
- 必須列(id, original, surface)が存在し、値が空でない
- pronunciation にASCII英字の連続が無い(英名をそのまま読みに入れると、利用側の
  読み解析が異常に遅くなる。実際に3行で辞書構築が193秒かかっていた)
- image/image_page は生カンマを含まないURL
- 選手descriptionが文脈依存の接続語や未完の語尾を含まない
- 選手descriptionがカードに別表示される人名を主語に繰り返さない
- 一意であるべき列の妥当性(stationsのwikidata重複など)

usage: python3 tools/validate_csvs.py
"""

import re
import sys
from collections import Counter
from pathlib import Path

from wpnames import (
    PLAYER_DISAMBIGUATION_DESCRIPTION,
    has_redundant_player_subject,
    is_standalone_player_description,
    strip_name_prefix,
)
from update_school import has_school_suffix

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ("id", "original", "surface")
# image/image_page として許可するURLプレフィックス(明示的な許可リスト。any-httpsにはしない)
IMAGE_URL_RE = re.compile(
    r"^https?://commons\.wikimedia\.org/"
    r"|^https://upload\.wikimedia\.org/"
    r"|^https://github\.com/soramimic/soramimic-wordlists/releases/"
    # youtuber の象徴カードと baseball/football の選手カードは、リポジトリ内
    # (images/)に置いて raw で参照する(1枚3KB前後のSVGで、CSVと同じ
    # コミットに入る利点を採ってReleaseを介さない。詳細は ADR 00018, 00019)
    r"|^https://raw\.githubusercontent\.com/soramimic/soramimic-wordlists/"
    r"|^https://github\.com/soramimic/soramimic-wordlists/blob/"
)
# 読みにASCII英字が2文字以上続くのは、英名を読みに入れてしまった取り違え
# (例: sekitsui の "Azara's night monkey")。利用側の読み解析がこの手の行で
# 暴走するため、混入を止める。読みはカタカナのみが前提
PRON_ASCII_RE = re.compile(r"[A-Za-z]{2,}")
YEAR_RE = re.compile(r"^(?:NA|前?[0-9]+)$")
HAN_RE = re.compile(r"[\u3400-\u9fff]")
MYOJI_EVIDENCE = ("person_lists", "ndl", "wikidata_person", "official_web",
                  "jmnedict")
MYOJI_HUMAN_EVIDENCE = {"person_lists", "ndl", "wikidata_person",
                        "official_web"}

errors = []


def err(msg):
    errors.append(msg)
    print(f"NG: {msg}")


def validate(path: Path):
    raw = path.read_bytes()
    if b"\r" in raw:
        err(f"{path.name}: CR(\\r)を含む")
    if raw.endswith(b"\n"):
        err(f"{path.name}: 末尾に改行がある")
    text = raw.decode("utf-8")
    if '"' in text:
        err(f"{path.name}: 引用符付きフィールドがある(カンマ入りの値?)")
        return
    lines = text.split("\n")
    header = lines[0].split(",")
    ncol = len(header)
    for col in REQUIRED:
        if col not in header:
            err(f"{path.name}: 必須列 {col} がない")
            return
    idx = {c: i for i, c in enumerate(header)}
    if path.name == "scientist.csv" and "death_year" not in idx:
        err(f"{path.name}: 必須列 death_year がない")
        return
    if path.name == "municipality.csv" and "municipality_type" not in idx:
        err(f"{path.name}: 必須列 municipality_type がない")
        return
    if path.name == "school.csv" and "has_school_suffix" not in idx:
        err(f"{path.name}: 必須列 has_school_suffix がない")
        return
    img_cols = [c for c in ("image", "image_page") if c in idx]
    scientist_years = {}
    player_groups = {}
    for lineno, line in enumerate(lines[1:], start=2):
        f = line.split(",")
        if len(f) != ncol:
            err(f"{path.name}:{lineno}: 列数が{len(f)}(期待{ncol}): {line[:60]}")
            continue
        for col in REQUIRED:
            if not f[idx[col]]:
                err(f"{path.name}:{lineno}: {col} が空")
        for col in img_cols:
            v = f[idx[col]]
            if v and not IMAGE_URL_RE.match(v):
                err(f"{path.name}:{lineno}: {col} が不正なURL: {v[:60]}")
        if "pronunciation" in idx:
            v = f[idx["pronunciation"]]
            if PRON_ASCII_RE.search(v):
                err(f"{path.name}:{lineno}: pronunciation にASCII英字が連続"
                    f"(英名の混入?): {v[:40]}")
        if path.name == "municipality.csv":
            municipality_type = f[idx["municipality_type"]]
            expected_type = f[idx["original"]][-1]
            if municipality_type not in ("市", "区", "町", "村"):
                err(f"{path.name}:{lineno}: municipality_type が不正: "
                    f"{municipality_type}")
            elif municipality_type != expected_type:
                err(f"{path.name}:{lineno}: original/municipality_typeが不整合: "
                    f"{f[idx['original']]} / {municipality_type}")
        if path.name == "school.csv":
            actual = f[idx["has_school_suffix"]]
            expected = has_school_suffix(f[idx["surface"]], f[idx["type"]],
                                         f[idx["school_type"]])
            if actual != expected:
                err(f"{path.name}:{lineno}: surface/has_school_suffixが不整合: "
                    f"{f[idx['surface']]} / {actual}")
        if path.name == "myoji.csv":
            if "evidence_sources" not in idx:
                err(f"{path.name}: 必須列 evidence_sources がない")
                return
            sources = [s for s in f[idx["evidence_sources"]].split("|") if s]
            if any(s not in MYOJI_EVIDENCE for s in sources):
                err(f"{path.name}:{lineno}: evidence_sources が不正: "
                    f"{f[idx['evidence_sources']]}")
            canonical = [s for s in MYOJI_EVIDENCE if s in sources]
            if sources != canonical:
                err(f"{path.name}:{lineno}: evidence_sources の順序・重複が不正: "
                    f"{f[idx['evidence_sources']]}")
            if f[idx["verified"]] == "yes" and not (
                    MYOJI_HUMAN_EVIDENCE & set(sources)):
                err(f"{path.name}:{lineno}: verified=yes に人物の裏付けがない")
        if path.name in ("baseball.csv", "football.csv") and "description" in idx:
            v = f[idx["description"]]
            player_groups.setdefault(f[idx["id"]], []).append((lineno, f))
            if v and not is_standalone_player_description(v):
                err(f"{path.name}:{lineno}: descriptionが単独で完結していない: "
                    f"{v[:65]}")
            if v and has_redundant_player_subject(v):
                err(f"{path.name}:{lineno}: descriptionの人名主語が冗長: "
                    f"{v[:65]}")
            if (
                path.name == "football.csv"
                and v
                and PLAYER_DISAMBIGUATION_DESCRIPTION.search(v)
            ):
                err(f"{path.name}:{lineno}: descriptionが曖昧さ回避ページ由来: "
                    f"{v[:65]}")
        if path.name == "scientist.csv":
            # 漢字名の family 行は姓の表記を保つ。読みを surface に誤記すると、
            # 動画字幕でも「小田」ではなく「おだ」のように表示されてしまう。
            if (
                f[idx["type"]] == "family"
                and HAN_RE.search(f[idx["original"]])
                and not HAN_RE.search(f[idx["surface"]])
            ):
                err(f"{path.name}:{lineno}: 漢字名のfamily surfaceが漢字でない: "
                    f"{f[idx['surface']]}")
            death_year = f[idx["death_year"]]
            if not YEAR_RE.fullmatch(death_year):
                err(f"{path.name}:{lineno}: death_year が不正: {death_year}")
            if death_year != "NA" and f[idx["status"]] != "物故":
                err(f"{path.name}:{lineno}: 没年があるのにstatusが物故でない")
            person_id = f[idx["id"]]
            years = (f[idx["birth_year"]], death_year)
            if person_id in scientist_years and scientist_years[person_id] != years:
                err(f"{path.name}:{lineno}: 同じidで生没年が一致しない")
            scientist_years[person_id] = years
    if player_groups:
        for group_rows in player_groups.values():
            descriptions = {fields[idx["description"]] for _, fields in group_rows}
            if len(descriptions) != 1:
                err(
                    f"{path.name}:{group_rows[0][0]}: "
                    "同じidでdescriptionが一致しない"
                )
            aliases = set()
            for _, fields in group_rows:
                aliases.add(fields[idx["original"]])
                if fields[idx["type"]] in ("full", "registered"):
                    aliases.add(fields[idx["surface"]])
            for lineno, fields in group_rows:
                description = fields[idx["description"]]
                if description and any(
                    strip_name_prefix(description, alias) != description
                    for alias in aliases
                ):
                    err(
                        f"{path.name}:{lineno}: descriptionの人名主語が冗長: "
                        f"{description[:65]}"
                    )
    print(f"OK: {path.name} ({len(lines) - 1}行)")


def validate_marine_life(path: Path):
    """公開CSVでも分類facetとキュレーション契約を独立に検証する。"""
    from update_marine_life import (
        APHIA_ID,
        CLASSES,
        IMAGE_FILE_BY_GROUP,
        MIN_APHIA_COUNT,
        MIN_CLASS_COUNTS,
        MIN_QID_COUNT,
        MIN_TOTAL_COUNT,
        OUTPUT_COLUMNS,
        VERTEBRATE_BY_CLASS,
        detailed_generated_filename,
        load_generated_image_manifest,
    )

    lines = path.read_text(encoding="utf-8").split("\n")
    header = lines[0].split(",")
    if tuple(header) != OUTPUT_COLUMNS:
        err(f"{path.name}: 列が規約と一致しない: {header}")
        return
    idx = {name: pos for pos, name in enumerate(header)}
    generated_manifest = load_generated_image_manifest()
    seen = set()
    counts = Counter()
    for item_id, line in enumerate(lines[1:]):
        fields = line.split(",")
        if len(fields) != len(header):
            continue  # 共通検証が列数エラーを報告する
        name = fields[idx["original"]]
        cls = fields[idx["class"]]
        if fields[idx["id"]] != str(item_id):
            err(f"{path.name}:{item_id + 2}: idが0始まりの連番でない")
        if name in seen:
            err(f"{path.name}:{item_id + 2}: originalが重複: {name}")
        seen.add(name)
        if cls not in CLASSES:
            err(f"{path.name}:{item_id + 2}: classが不正: {cls}")
            continue
        counts[cls] += 1
        if fields[idx["vertebrate"]] != VERTEBRATE_BY_CLASS[cls]:
            err(f"{path.name}:{item_id + 2}: class/vertebrateが不整合: {name}")
        if not fields[idx["order"]].endswith("目") or not fields[idx["family"]].endswith("科"):
            err(f"{path.name}:{item_id + 2}: order/familyが不正: {name}")
        description = fields[idx["description"]]
        if description and (not 8 <= len(description) <= 90 or not description.endswith("。")):
            err(f"{path.name}:{item_id + 2}: descriptionが不正: {name}")
        if description and re.match(rf"^(?:{re.escape(name)}|本種)(?:は|が)[、 ]*", description):
            err(f"{path.name}:{item_id + 2}: descriptionの主語が冗長: {name}")
        if description and ("WoRMS" in description or "学名は" in description):
            err(f"{path.name}:{item_id + 2}: descriptionが出典メタデータを重複表示: {name}")
        scientific_name = fields[idx["scientific_name"]]
        if scientific_name and scientific_name in description:
            err(f"{path.name}:{item_id + 2}: descriptionが学名を重複表示: {name}")
        image = fields[idx["image"]]
        if not image.startswith("https://upload.wikimedia.org/wikipedia/commons/"):
            valid_fallbacks = {IMAGE_FILE_BY_GROUP[cls]}
            detailed = detailed_generated_filename(
                fields[idx["family"]], fields[idx["order"]], generated_manifest
            )
            if detailed:
                valid_fallbacks.add(detailed)
            if cls == "無脊椎動物":
                valid_fallbacks.update(
                    filename for group, filename in IMAGE_FILE_BY_GROUP.items()
                    if group not in {"哺乳類", "爬虫類", "魚類"}
                )
            if not any(image.endswith(f"/images/marine_life/{filename}")
                       for filename in valid_fallbacks):
                err(f"{path.name}:{item_id + 2}: classとimageが不整合: {name}")
        aphia_id = fields[idx["aphia_id"]]
        if aphia_id and not APHIA_ID.fullmatch(aphia_id):
            err(f"{path.name}:{item_id + 2}: AphiaIDが不正: {name}")
    for cls, minimum in MIN_CLASS_COUNTS.items():
        if counts[cls] < minimum:
            err(f"{path.name}: {cls}が少なすぎる: {counts[cls]} < {minimum}")
    qid_count = sum(bool(line.split(",")[idx["wikidata"]]) for line in lines[1:])
    if qid_count < MIN_QID_COUNT:
        err(f"{path.name}: Wikidata QIDが少なすぎる: {qid_count} < {MIN_QID_COUNT}")
    aphia_count = sum(bool(line.split(",")[idx["aphia_id"]]) for line in lines[1:])
    if aphia_count < MIN_APHIA_COUNT:
        err(f"{path.name}: AphiaIDが少なすぎる: {aphia_count} < {MIN_APHIA_COUNT}")
    if len(lines) - 1 < MIN_TOTAL_COUNT:
        err(f"{path.name}: 行数が少なすぎる: {len(lines) - 1} < {MIN_TOTAL_COUNT}")


def main() -> int:
    for p in sorted(ROOT.glob("*.csv")):
        validate(p)
        if p.name == "marine_life.csv":
            validate_marine_life(p)
    # tools のPythonが構文エラーでないこと
    import py_compile
    for p in sorted((ROOT / "tools").glob("*.py")):
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as ex:
            err(f"{p.name}: 構文エラー: {ex}")
    if errors:
        print(f"\n{len(errors)}件のエラー")
        return 1
    print("\nすべてOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
