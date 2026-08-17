#!/usr/bin/env python3
"""Apply reviewed, non-commercial VTuber fan-made images to youtuber.csv.

Only repository-hosted images listed in ``youtuber_permitted_images.json`` are
accepted.  They may replace the generic SVG fallback, but never a Commons
portrait or another curated image.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_youtuber_cards import (  # noqa: E402
    URL_PREFIX as CARD_PREFIX,
    image_page_url as card_page_url,
    image_url as card_image_url,
)
from wpnames import write_csv_no_trailing_newline  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "youtuber.csv"
MANIFEST_PATH = Path(__file__).resolve().parent / "youtuber_permitted_images.json"
ASSET_DIR = ROOT / "images" / "youtuber_fan"
IMAGE_PREFIX = (
    "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/"
    "main/images/youtuber_fan/"
)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FILENAME = re.compile(r"^yt_fan_[0-9a-f]{10}\.png$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_ORGS = {"あおぎり高校", "ななしいんく"}
ALLOWED_SOURCE_HOSTS = {"vhs-city.com", "www.774.ai"}
ALLOWED_ASSET_HOSTS = {"vhs-city.com", "static.wixstatic.com"}
ALLOWED_GUIDELINES = {
    "https://vhs-city.com/aogirihighschool/guidelines/fanfic",
    "https://www.774.ai/guideline",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    active = data.get("active", True) is True
    records = data.get("images", [])
    required = {
        "original", "file", "asset_url", "source_page", "guideline_url",
        "credit", "organization", "asset_kind", "permission",
        "guideline_reviewed", "reviewed", "source_sha256", "sha256",
    }
    result = {}
    filenames = set()
    for index, record in enumerate(records, 1):
        context = f"{path.name} images[{index}]"
        missing = sorted(required - set(record))
        if missing:
            raise SystemExit(f"error: {context} に {missing[0]} がない")
        original = record["original"]
        if original in result:
            raise SystemExit(f"error: original が重複: {original}")
        if record["file"] in filenames:
            raise SystemExit(f"error: file が重複: {record['file']}")
        if not FILENAME.fullmatch(record["file"]):
            raise SystemExit(f"error: {context} のfileが不正")
        expected_hash = hashlib.sha1(original.encode("utf-8")).hexdigest()[:10]
        if record["file"] != f"yt_fan_{expected_hash}.png":
            raise SystemExit(f"error: {context} のfileがoriginalと不整合")
        if record["organization"] not in ALLOWED_ORGS:
            raise SystemExit(f"error: {context} のorganizationが許可対象外")
        if "ホロライブ" in record["organization"].lower() or "hololive" in record["organization"].lower():
            raise SystemExit(f"error: {context} にホロライブを含められない")
        if record["asset_kind"] != "official_art_fan_composite":
            raise SystemExit(f"error: {context} のasset_kindが不正")
        if record["permission"] != "allowed_noncommercial":
            raise SystemExit(f"error: {context} のpermissionが不正")
        if not record["credit"].strip():
            raise SystemExit(f"error: {context} のcreditが空")
        for field in ("source_page", "credit"):
            if any(char in record[field] for char in ',"\r\n'):
                raise SystemExit(f"error: {context} の{field}にCSV禁止文字がある")
        if not ISO_DATE.fullmatch(record["reviewed"]):
            raise SystemExit(f"error: {context} のreviewedが不正")
        if not ISO_DATE.fullmatch(record["guideline_reviewed"]):
            raise SystemExit(f"error: {context} のguideline_reviewedが不正")
        source_page = urlparse(record["source_page"])
        asset_url = urlparse(record["asset_url"])
        if (source_page.scheme != "https" or source_page.username
                or source_page.password or source_page.port
                or source_page.hostname not in ALLOWED_SOURCE_HOSTS):
            raise SystemExit(f"error: {context} のsource_pageが公式サイトでない")
        if (asset_url.scheme != "https" or asset_url.username
                or asset_url.password or asset_url.port
                or asset_url.hostname not in ALLOWED_ASSET_HOSTS):
            raise SystemExit(f"error: {context} のasset_urlが公式配信元でない")
        if record["guideline_url"] not in ALLOWED_GUIDELINES:
            raise SystemExit(f"error: {context} のguideline_urlが不正")
        asset = ASSET_DIR / record["file"]
        if not asset.is_file():
            raise SystemExit(f"error: {context} の画像が存在しない")
        if sha256(asset) != record["sha256"]:
            raise SystemExit(f"error: {context} の画像ハッシュが不一致")
        if not SHA256.fullmatch(record["source_sha256"]):
            raise SystemExit(f"error: {context} のsource_sha256が不正")
        result[original] = record
        filenames.add(record["file"])
    if path.resolve() == MANIFEST_PATH.resolve():
        actual = {item.name for item in ASSET_DIR.glob("*.png")}
        if actual != filenames:
            raise SystemExit(
                "error: youtuber_fan画像と台帳が不一致: "
                f"不足={sorted(filenames - actual)} 孤立={sorted(actual - filenames)}")
    return result if active else {}


def apply(csv_path: Path = CSV_PATH, manifest_path: Path = MANIFEST_PATH) -> tuple[int, int]:
    manifest = load_manifest(manifest_path)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    for column in ("image_credit", "image_usage", "image_terms_page"):
        if column not in fieldnames:
            fieldnames.append(column)
    for row in rows:
        for column in ("image_credit", "image_usage", "image_terms_page"):
            row.setdefault(column, "")

    by_original: dict[str, list[dict]] = {}
    for row in rows:
        by_original.setdefault(row["original"], []).append(row)

    changed_names = set()
    changed_rows = 0
    # A guideline change or manifest removal must immediately restore the
    # copyright-independent symbolic fallback instead of leaving stale art.
    for row in rows:
        if (row.get("image", "").startswith(IMAGE_PREFIX)
                and row["original"] not in manifest):
            row["image"] = card_image_url(row["original"])
            row["image_page"] = card_page_url(row["original"])
            row["image_credit"] = ""
            row["image_usage"] = ""
            row["image_terms_page"] = ""
            changed_names.add(row["original"])
            changed_rows += 1
    for original, record in manifest.items():
        targets = by_original.get(original, [])
        if not targets:
            raise SystemExit(f"error: youtuber.csv に対象がいない: {original}")
        expected_image = IMAGE_PREFIX + record["file"]
        changed = False
        for row in targets:
            if row.get("category") != "vtuber":
                raise SystemExit(f"error: {original} がvtuberでない")
            if row.get("status") != "current":
                raise SystemExit(f"error: {original} が現所属として確認できない")
            if record["organization"] not in row.get("org", "").split("/"):
                raise SystemExit(f"error: {original} のorgが台帳と不一致")
            current = row.get("image", "")
            if current != expected_image and not current.startswith(CARD_PREFIX):
                raise SystemExit(f"error: {original} の既存画像を上書きできない")
            desired = (
                expected_image, record["source_page"], record["credit"],
                "noncommercial_fanwork", record["guideline_url"],
            )
            actual = (
                current, row.get("image_page", ""), row.get("image_credit", ""),
                row.get("image_usage", ""), row.get("image_terms_page", ""),
            )
            if actual != desired:
                (row["image"], row["image_page"], row["image_credit"],
                 row["image_usage"], row["image_terms_page"]) = desired
                changed = True
                changed_rows += 1
        if changed:
            changed_names.add(original)

    write_csv_no_trailing_newline(csv_path, fieldnames, rows)
    return len(changed_names), changed_rows


def main() -> None:
    people, rows = apply()
    print(f"youtuber.csv: ファンメイド画像 {people}人 / {rows}行を更新")


if __name__ == "__main__":
    main()
