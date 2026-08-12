#!/usr/bin/env python3
"""キュレーション台帳から marine_life.csv を再生成する。

海洋性は単一の分類群ではなく、Wikidata の分類木だけでは安全に判定できない。
そのため初版はレビュー済み台帳を正本とし、このスクリプトで利用用CSVを決定的に
生成する。ネットワークアクセスは行わない。

usage: python3 tools/update_marine_life.py [--check]
"""

import argparse
import csv
import io
import json
import os
import re
import hashlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(__file__).with_name("marine_life_source.csv")
IMAGE_SOURCES = Path(__file__).with_name("marine_life_image_sources.jsonl")
DESCRIPTION_SOURCES = Path(__file__).with_name("marine_life_description_sources.jsonl")
GENERATED_IMAGE_SOURCES = Path(__file__).with_name("marine_life_generated_images.json")
OUTPUT = ROOT / "marine_life.csv"

CLASSES = ("哺乳類", "爬虫類", "魚類", "無脊椎動物")
MIN_CLASS_COUNTS = {
    "哺乳類": 30,
    "爬虫類": 12,
    "魚類": 2976,
    "無脊椎動物": 1236,
}
MIN_TOTAL_COUNT = 4254
MIN_QID_COUNT = 4010
MIN_APHIA_COUNT = 4148
MIN_JODC_COUNT = 4148
MIN_PHOTO_COUNT = 1384
AUTO_DESCRIPTION_START_ID = 179
MIN_AUTO_DESCRIPTION_COUNT = 4075
MIN_WIKIPEDIA_DESCRIPTION_COUNT = 300
VERTEBRATE_BY_CLASS = {
    "哺乳類": "脊椎動物",
    "爬虫類": "脊椎動物",
    "魚類": "脊椎動物",
    "無脊椎動物": "無脊椎動物",
}
IMAGE_FILE_BY_GROUP = {
    "哺乳類": "marine_mammal_generated.webp",
    "爬虫類": "marine_reptile_generated.webp",
    "魚類": "marine_fish_generated.webp",
    "無脊椎動物": "marine_other_invertebrate_generated.webp",
    "刺胞動物": "marine_cnidarian_generated.webp",
    "甲殻類": "marine_crustacean_generated.webp",
    "軟体動物": "marine_mollusk_generated.webp",
    "棘皮動物": "marine_echinoderm_generated.webp",
    "蠕虫型": "marine_worm_generated.webp",
    "その他無脊椎": "marine_other_invertebrate_generated.webp",
}
RAW_BASE = (
    "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/"
    "main/images/marine_life"
)
PAGE_BASE = (
    "https://github.com/soramimic/soramimic-wordlists/blob/"
    "main/images/marine_life"
)
KATAKANA = re.compile(r"^[ァ-ヶー・]+$")
QID = re.compile(r"^Q[1-9][0-9]*$")
APHIA_ID = re.compile(r"^[1-9][0-9]*$")
JODC_CODE = re.compile(r"^[0-9]{14}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SCIENTIFIC_NAME = re.compile(r"^[A-Z][A-Za-z().-]+(?: [A-Za-z().-]+)+$")
SOURCE_COLUMNS = (
    "id", "name", "class", "vertebrate", "order", "family", "description",
    "wikidata", "scientific_name", "aphia_id", "jodc_code", "image", "image_page",
    "image_group",
)
OUTPUT_COLUMNS = (
    "id", "original", "surface", "pronunciation", "class", "vertebrate",
    "order", "family", "description", "image", "image_page", "wikidata",
    "scientific_name", "aphia_id",
)

IUCN_JA = {
    "Least Concern": "低懸念",
    "Near Threatened": "準絶滅危惧",
    "Vulnerable": "危急",
    "Endangered": "危機",
    "Critically Endangered": "深刻な危機",
    "Data Deficient": "情報不足",
    "Not Evaluated": "未評価",
    "Extinct in the Wild": "野生絶滅",
    "Extinct": "絶滅",
}
UNIT_JA = {"mm": "ミリ", "cm": "センチ", "m": "メートル", "µm": "マイクロメートル"}
UNCERTAIN_STATUS_JA = {
    "taxon inquirendum": "要検討分類群",
    "nomen dubium": "疑問名",
    "nomen novum": "新置換名",
    "unreplaced junior homonym": "未置換の新参同名",
}


def _normalized_wikipedia_title(value: str) -> str:
    value = re.sub(r"[（(][^）)]*[）)]$", "", value)
    return value.replace("・", "").replace(" ", "")


def _display_number(raw: str) -> str:
    number = float(raw)
    if number >= 10:
        return str(round(number))
    digits = 1 if number >= 1 else 2
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def description_from_evidence(row: dict[str, str], evidence: dict) -> str:
    """固定済みの百科事典・構造化根拠からカード用説明を再生成する。

    名前・学名・分類・出典名はカードの別欄や根拠台帳にあるため本文へ重ねない。
    生態や形態の根拠がない場合は、分類文で水増しせず空欄を返す。
    """
    wikipedia = evidence.get("wikipedia") or {}
    if wikipedia.get("description"):
        return str(wikipedia["description"])
    traits = {item["type"]: item for item in evidence.get("traits", [])}
    length = traits.get("maximum_length")
    iucn = traits.get("iucn_status")
    candidates: list[str] = []
    status = evidence.get("status")
    if status in UNCERTAIN_STATUS_JA:
        label = UNCERTAIN_STATUS_JA[status]
        return f"分類上の位置づけが未確定で、{label}として扱われる海洋生物名。"
    if length and length.get("unit") in UNIT_JA:
        size = _display_number(str(length["value"])) + UNIT_JA[length["unit"]]
        if iucn and iucn.get("category") in IUCN_JA:
            iucn_label = IUCN_JA[iucn["category"]]
            if str(iucn.get("year") or "").isdigit():
                candidates.append(
                    f"最大体長約{size}。IUCN評価は{iucn_label}（{iucn['year']}年）。"
                )
            candidates.append(f"最大体長約{size}で、IUCN評価は{iucn_label}。")
        candidates.append(f"最大体長約{size}。")
    if iucn and iucn.get("category") in IUCN_JA:
        candidates.append(f"IUCN評価は{IUCN_JA[iucn['category']]}。")
    for description in candidates:
        if 8 <= len(description) <= 90 and "," not in description:
            return description
    return ""


def load_source(path: Path = SOURCE) -> list[dict[str, str]]:
    raw = path.read_bytes()
    if b"\r" in raw or raw.endswith(b"\n") or b'"' in raw:
        raise ValueError("source CSV must use LF without a trailing newline or quotes")
    lines = raw.decode("utf-8").split("\n")
    if tuple(lines[0].split(",")) != SOURCE_COLUMNS:
        raise ValueError(f"unexpected source columns: {lines[0].split(',')}")
    for lineno, line in enumerate(lines[1:], 2):
        if len(line.split(",")) != len(SOURCE_COLUMNS):
            raise ValueError(f"line {lineno}: unexpected number of columns")
    with io.StringIO(raw.decode("utf-8"), newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]

    seen: set[str] = set()
    for lineno, row in enumerate(rows, 2):
        if row["id"] != str(lineno - 2):
            raise ValueError(f"line {lineno}: id must be append-only sequence: {row['id']}")
        name = row["name"]
        if len(name) < 2 or not KATAKANA.fullmatch(name) or name[0] == "・" or name[-1] == "・":
            raise ValueError(f"line {lineno}: name is not katakana: {name}")
        if name in seen:
            raise ValueError(f"line {lineno}: duplicate name: {name}")
        seen.add(name)
        cls = row["class"]
        if cls not in CLASSES:
            raise ValueError(f"line {lineno}: invalid class: {cls}")
        if row["vertebrate"] != VERTEBRATE_BY_CLASS[cls]:
            raise ValueError(f"line {lineno}: class/vertebrate mismatch: {name}")
        if not row["order"].endswith("目") or not row["family"].endswith("科"):
            raise ValueError(f"line {lineno}: order/family must end in 目/科: {name}")
        description = row["description"]
        if description and (not (8 <= len(description) <= 90) or not description.endswith("。")):
            raise ValueError(f"line {lineno}: invalid description: {name}")
        if description and re.match(rf"^(?:{re.escape(name)}|本種)(?:は|が)[、 ]*", description):
            raise ValueError(f"line {lineno}: redundant description subject: {name}")
        if description and ("WoRMS" in description or "学名は" in description):
            raise ValueError(f"line {lineno}: description repeats source metadata: {name}")
        if row["scientific_name"] and row["scientific_name"] in description:
            raise ValueError(f"line {lineno}: description repeats scientific name: {name}")
        if any("," in row[col] for col in SOURCE_COLUMNS):
            raise ValueError(f"line {lineno}: comma is not supported: {name}")
        if row["wikidata"] and not QID.fullmatch(row["wikidata"]):
            raise ValueError(f"line {lineno}: invalid Wikidata QID: {name}")
        if row["scientific_name"] and not SCIENTIFIC_NAME.fullmatch(row["scientific_name"]):
            raise ValueError(f"line {lineno}: invalid scientific name: {name}")
        if row["aphia_id"] and not APHIA_ID.fullmatch(row["aphia_id"]):
            raise ValueError(f"line {lineno}: invalid AphiaID: {name}")
        if row["jodc_code"] and not JODC_CODE.fullmatch(row["jodc_code"]):
            raise ValueError(f"line {lineno}: invalid JODC code: {name}")
        if bool(row["image"]) != bool(row["image_page"]):
            raise ValueError(f"line {lineno}: image/image_page mismatch: {name}")
        if row["image"] and not row["image"].startswith(
                "https://upload.wikimedia.org/wikipedia/commons/"):
            raise ValueError(f"line {lineno}: non-Commons photo: {name}")
        if row["image_page"] and "commons.wikimedia.org/wiki/File:" not in row["image_page"]:
            raise ValueError(f"line {lineno}: invalid Commons source page: {name}")
        if row["image_group"] not in IMAGE_FILE_BY_GROUP:
            raise ValueError(f"line {lineno}: invalid image group: {name}")
    counts = Counter(row["class"] for row in rows)
    for cls, minimum in MIN_CLASS_COUNTS.items():
        if counts[cls] < minimum:
            raise ValueError(f"too few {cls} rows: {counts[cls]} (minimum {minimum})")
    qid_count = sum(bool(row["wikidata"]) for row in rows)
    if qid_count < MIN_QID_COUNT:
        raise ValueError(f"too few Wikidata QIDs: {qid_count} (minimum {MIN_QID_COUNT})")
    aphia_count = sum(bool(row["aphia_id"]) for row in rows)
    if aphia_count < MIN_APHIA_COUNT:
        raise ValueError(f"too few AphiaIDs: {aphia_count} (minimum {MIN_APHIA_COUNT})")
    jodc_count = sum(bool(row["jodc_code"]) for row in rows)
    if jodc_count < MIN_JODC_COUNT:
        raise ValueError(f"too few JODC codes: {jodc_count} (minimum {MIN_JODC_COUNT})")
    if len(rows) < MIN_TOTAL_COUNT:
        raise ValueError(f"too few rows: {len(rows)} (minimum {MIN_TOTAL_COUNT})")
    return rows


def validate_images() -> None:
    image_dir = ROOT / "images" / "marine_life"
    manifest = json.loads(GENERATED_IMAGE_SOURCES.read_text(encoding="utf-8"))
    by_filename = {record["filename"]: record for record in manifest}
    expected = set(IMAGE_FILE_BY_GROUP.values())
    if set(by_filename) != expected:
        raise ValueError("generated image manifest does not match fallback images")
    for filename in expected:
        path = image_dir / filename
        if not path.is_file():
            raise ValueError(f"missing generated image: {path}")
        raw = path.read_bytes()
        marker = raw.find(b"\x9d\x01\x2a")
        if raw[:4] != b"RIFF" or raw[8:12] != b"WEBP" or marker < 0:
            raise ValueError(f"invalid generated WebP: {path}")
        width = int.from_bytes(raw[marker + 3:marker + 5], "little") & 0x3FFF
        height = int.from_bytes(raw[marker + 5:marker + 7], "little") & 0x3FFF
        if (width, height) != (960, 600):
            raise ValueError(f"unexpected generated image size: {path}")
        record = by_filename[filename]
        if record.get("label") != "生成イメージ" or record.get("scope") != "morphology_group":
            raise ValueError(f"generated image lacks disclosure metadata: {path}")
        if hashlib.sha256(raw).hexdigest() != record.get("sha256"):
            raise ValueError(f"generated image hash mismatch: {path}")


def validate_image_sources(rows: list[dict[str, str]], path: Path = IMAGE_SOURCES) -> None:
    """実写のライセンス・同定根拠snapshotが台帳と一対一に対応するか検査する。"""
    raw = path.read_bytes()
    if b"\r" in raw or raw.endswith(b"\n"):
        raise ValueError("image source JSONL must use LF without a trailing newline")
    records = [json.loads(line) for line in raw.decode("utf-8").split("\n")]
    by_name: dict[str, dict] = {}
    for lineno, record in enumerate(records, 1):
        name = record.get("name", "")
        if not name or name in by_name:
            raise ValueError(f"image source line {lineno}: missing or duplicate name: {name}")
        license_name = record.get("license", "")
        if not re.match(r"^(CC BY(?:-SA)?(?: |$)|CC0$|Public domain$)",
                        license_name, re.IGNORECASE):
            raise ValueError(f"image source line {lineno}: unsupported license: {name}")
        if license_name.upper().startswith("CC BY"):
            if not record.get("artist"):
                raise ValueError(f"image source line {lineno}: missing artist: {name}")
            if "creativecommons.org/licenses/" not in record.get("license_url", ""):
                raise ValueError(f"image source line {lineno}: missing license URL: {name}")
        if license_name.upper() == "CC0" and \
                "creativecommons.org/publicdomain/zero/" not in record.get("license_url", ""):
            raise ValueError(f"image source line {lineno}: missing CC0 URL: {name}")
        if not SHA1.fullmatch(record.get("sha1", "")):
            raise ValueError(f"image source line {lineno}: invalid SHA1: {name}")
        if int(record.get("width", 0)) < 320 or int(record.get("height", 0)) < 200:
            raise ValueError(f"image source line {lineno}: image too small: {name}")
        if not record.get("identification_basis"):
            raise ValueError(f"image source line {lineno}: missing identification basis: {name}")
        by_name[name] = record
    expected = {row["name"]: row for row in rows if row["image"]}
    if set(by_name) != set(expected):
        missing = sorted(set(expected) - set(by_name))[:10]
        extra = sorted(set(by_name) - set(expected))[:10]
        raise ValueError(f"image source names mismatch: missing={missing}, extra={extra}")
    for name, row in expected.items():
        record = by_name[name]
        for field in ("image", "image_page", "wikidata", "scientific_name", "aphia_id"):
            if record.get(field, "") != row[field]:
                raise ValueError(f"image source mismatch for {name}: {field}")
    if len(records) < MIN_PHOTO_COUNT:
        raise ValueError(f"too few reviewed photos: {len(records)} (minimum {MIN_PHOTO_COUNT})")


def validate_description_sources(
    rows: list[dict[str, str]], path: Path = DESCRIPTION_SOURCES
) -> None:
    """DB生成説明が固定済みWoRMS根拠と一対一で再生成できるか検査する。"""
    raw = path.read_bytes()
    if b"\r" in raw or raw.endswith(b"\n"):
        raise ValueError("description source JSONL must use LF without a trailing newline")
    records = [json.loads(line) for line in raw.decode("utf-8").split("\n")]
    by_name: dict[str, dict] = {}
    for lineno, record in enumerate(records, 1):
        name = record.get("name", "")
        if not name or name in by_name:
            raise ValueError(
                f"description source line {lineno}: missing or duplicate name: {name}"
            )
        if record.get("status") not in {"accepted", *UNCERTAIN_STATUS_JA}:
            raise ValueError(f"description source has unsupported status: {name}")
        if record.get("rank") not in {"Species", "Subspecies"}:
            raise ValueError(f"description source has unsupported rank: {name}")
        if record.get("is_marine") != 1:
            raise ValueError(f"description source is not marine: {name}")
        if record.get("valid_aphia_id") != int(record.get("aphia_id", 0)):
            raise ValueError(f"description source AphiaID mismatch: {name}")
        if not record.get("record_url", "").startswith(
            "https://www.marinespecies.org/aphia.php?"
        ):
            raise ValueError(f"description source record URL is missing: {name}")
        if not record.get("attributes_url", "").startswith(
            "https://www.marinespecies.org/rest/AphiaAttributesByAphiaID/"
        ):
            raise ValueError(f"description source attributes URL is missing: {name}")
        aphia_id = str(record.get("aphia_id", ""))
        if not APHIA_ID.fullmatch(aphia_id):
            raise ValueError(f"description source AphiaID is invalid: {name}")
        if not record["record_url"].endswith(f"id={aphia_id}") or not record[
            "attributes_url"
        ].endswith(f"/{aphia_id}"):
            raise ValueError(f"description source URL/AphiaID mismatch: {name}")
        if not re.fullmatch(
            r"20[0-9]{2}-[01][0-9]-[0-3][0-9]", record.get("fetched_at", "")
        ):
            raise ValueError(f"description source fetched_at is invalid: {name}")
        seen_traits: set[str] = set()
        for trait in record.get("traits", []):
            if trait.get("type") not in {"maximum_length", "iucn_status"}:
                raise ValueError(f"description source has unknown trait: {name}")
            if trait["type"] in seen_traits:
                raise ValueError(f"description source has duplicate trait: {name}")
            seen_traits.add(trait["type"])
            if not trait.get("reference") or not trait.get("source_id"):
                raise ValueError(f"description source trait lacks a reference: {name}")
            if trait.get("quality_status") not in {"checked", "unreviewed", "trusted"}:
                raise ValueError(f"description source trait quality is invalid: {name}")
            if trait["type"] == "maximum_length":
                try:
                    positive = float(trait.get("value", 0)) > 0
                except (TypeError, ValueError):
                    positive = False
                if not positive or trait.get("unit") not in UNIT_JA:
                    raise ValueError(f"description source length is invalid: {name}")
            if trait["type"] == "iucn_status":
                if trait.get("category") not in IUCN_JA:
                    raise ValueError(f"description source IUCN status is invalid: {name}")
                if trait.get("year") and not str(trait["year"]).isdigit():
                    raise ValueError(f"description source IUCN year is invalid: {name}")
        wikipedia = record.get("wikipedia") or {}
        if wikipedia:
            if wikipedia.get("language") != "ja":
                raise ValueError(f"description source Wikipedia language is invalid: {name}")
            if not QID.fullmatch(str(wikipedia.get("wikidata") or "")):
                raise ValueError(f"description source Wikipedia QID is invalid: {name}")
            if wikipedia.get("wikidata") != record.get("wikidata"):
                raise ValueError(f"description source Wikipedia QID mismatch: {name}")
            title = str(wikipedia.get("title") or "")
            if _normalized_wikipedia_title(title) != _normalized_wikipedia_title(name):
                raise ValueError(f"description source Wikipedia title mismatch: {name}")
            if not str(wikipedia.get("page_url") or "").startswith("https://ja.wikipedia.org/wiki/"):
                raise ValueError(f"description source Wikipedia URL is invalid: {name}")
            if not isinstance(wikipedia.get("revision_id"), int) or wikipedia["revision_id"] <= 0:
                raise ValueError(f"description source Wikipedia revision is invalid: {name}")
            if not re.fullmatch(
                r"20[0-9]{2}-[01][0-9]-[0-3][0-9]", wikipedia.get("fetched_at", "")
            ):
                raise ValueError(f"description source Wikipedia fetched_at is invalid: {name}")
            if wikipedia.get("license") != "CC BY-SA 4.0" or wikipedia.get(
                "license_url"
            ) != "https://creativecommons.org/licenses/by-sa/4.0/":
                raise ValueError(f"description source Wikipedia license is invalid: {name}")
            if not isinstance(wikipedia.get("modified"), bool):
                raise ValueError(f"description source Wikipedia modified flag is invalid: {name}")
            source_sentence = str(wikipedia.get("source_sentence") or "")
            description = str(wikipedia.get("description") or "")
            if not source_sentence.endswith("。") or not description.endswith("。"):
                raise ValueError(f"description source Wikipedia sentence is invalid: {name}")
            if not (8 <= len(description) <= 90) or "," in description:
                raise ValueError(f"description source Wikipedia description is invalid: {name}")
            if re.match(rf"^(?:{re.escape(name)}|本種)(?:は|が)[、 ]*", description):
                raise ValueError(f"description source has redundant subject: {name}")
            if record.get("scientific_name") and record["scientific_name"] in description:
                raise ValueError(f"description source repeats scientific name: {name}")
        by_name[name] = record

    expected = {
        row["name"]: row for row in rows if int(row["id"]) >= AUTO_DESCRIPTION_START_ID
    }
    if set(by_name) != set(expected):
        missing = sorted(set(expected) - set(by_name))[:10]
        extra = sorted(set(by_name) - set(expected))[:10]
        raise ValueError(
            f"description source names mismatch: missing={missing}, extra={extra}"
        )
    if [record["name"] for record in records] != list(expected):
        raise ValueError("description source rows must follow source CSV order")
    for name, row in expected.items():
        record = by_name[name]
        for field in ("aphia_id", "scientific_name", "wikidata"):
            if str(record.get(field, "")) != row[field]:
                raise ValueError(f"description source mismatch for {name}: {field}")
        if record.get("valid_name") != row["scientific_name"]:
            raise ValueError(f"description source valid name mismatch: {name}")
        expected_description = description_from_evidence(row, record)
        if row["description"] != expected_description:
            raise ValueError(f"description is not generated from evidence: {name}")
    if len(records) < MIN_AUTO_DESCRIPTION_COUNT:
        raise ValueError(
            f"too few sourced descriptions: {len(records)} "
            f"(minimum {MIN_AUTO_DESCRIPTION_COUNT})"
        )
    wikipedia_count = sum(bool(record.get("wikipedia")) for record in records)
    if wikipedia_count < MIN_WIKIPEDIA_DESCRIPTION_COUNT:
        raise ValueError(
            f"too few Wikipedia descriptions: {wikipedia_count} "
            f"(minimum {MIN_WIKIPEDIA_DESCRIPTION_COUNT})"
        )


def generate(rows: list[dict[str, str]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        filename = IMAGE_FILE_BY_GROUP[row["image_group"]]
        image = row["image"] or f"{RAW_BASE}/{filename}"
        image_page = row["image_page"] or f"{PAGE_BASE}/{filename}"
        writer.writerow({
            "id": row["id"],
            "original": row["name"],
            "surface": row["name"],
            "pronunciation": row["name"],
            "class": row["class"],
            "vertebrate": row["vertebrate"],
            "order": row["order"],
            "family": row["family"],
            "description": row["description"],
            "image": image,
            "image_page": image_page,
            "wikidata": row["wikidata"],
            "scientific_name": row["scientific_name"],
            "aphia_id": row["aphia_id"],
        })
    return out.getvalue().rstrip("\n").encode("utf-8")


def removed_names(generated: bytes, output: Path = OUTPUT) -> set[str]:
    if not output.exists():
        return set()
    old = {row["original"] for row in csv.DictReader(io.StringIO(output.read_text(encoding="utf-8")))}
    new = {row["original"] for row in csv.DictReader(io.StringIO(generated.decode("utf-8")))}
    return old - new


def write_atomic(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="再生成結果と既存CSVが一致するかだけ確認する")
    parser.add_argument("--allow-removals", action="store_true",
                        help="既存CSVからの項目削除を明示的に許可する")
    args = parser.parse_args(argv)
    rows = load_source()
    validate_images()
    validate_image_sources(rows)
    validate_description_sources(rows)
    generated = generate(rows)
    counts = Counter(row["class"] for row in rows)
    summary = ", ".join(f"{key} {counts[key]}" for key in CLASSES)
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_bytes() != generated:
            print("marine_life.csv は台帳からの再生成結果と一致しません")
            return 1
        print(f"marine_life.csv: 再生成差分なし ({len(rows)}行; {summary})")
        return 0
    removed = removed_names(generated, OUTPUT)
    if removed and not args.allow_removals:
        print(f"既存CSVから{len(removed)}件が消えるため中断しました: "
              + ", ".join(sorted(removed)[:10]))
        print("意図した削除なら --allow-removals を付けて再実行してください")
        return 1
    write_atomic(OUTPUT, generated)
    print(f"marine_life.csv: {len(rows)}行を再生成 ({summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
