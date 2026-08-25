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
- 架空科学者achievementが短い完結文で、同じ人物の各表層で一致する
- 一意であるべき列の妥当性(stationsのwikidata重複など)

usage: python3 tools/validate_csvs.py
"""

import re
import sys
from collections import Counter
from pathlib import Path

from update_school import has_school_suffix
from apply_youtuber_permitted_images import (
    IMAGE_PREFIX as YOUTUBER_FAN_IMAGE_PREFIX,
    load_manifest as load_youtuber_fan_manifest,
)
from apply_youtuber_hololive_images import (
    IMAGE_USAGE as HOLOLIVE_IMAGE_USAGE,
    load_manifest as load_hololive_image_manifest,
)
from apply_youtuber_nijisanji_images import (
    IMAGE_USAGE as NIJISANJI_IMAGE_USAGE,
    load_manifest as load_nijisanji_image_manifest,
)
from wpnames import (
    has_redundant_player_subject,
    is_likely_disambiguation_text,
    is_standalone_player_description,
    strip_name_prefix,
)

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
YOUTUBER_CARD_IMAGE_PREFIX = (
    "https://raw.githubusercontent.com/soramimic/soramimic-wordlists/"
    "main/images/youtuber/"
)
YOUTUBER_CARD_PAGE_PREFIX = (
    "https://github.com/soramimic/soramimic-wordlists/blob/"
    "main/images/youtuber/"
)
YOUTUBER_FAN_IMAGES = {
    YOUTUBER_FAN_IMAGE_PREFIX + record["file"]: record
    for record in load_youtuber_fan_manifest().values()
}
YOUTUBER_FAN_SOURCE_PAGES = {
    record["source_page"] for record in YOUTUBER_FAN_IMAGES.values()
}
YOUTUBER_HOLOLIVE_IMAGES = {
    record["image_url"]: record
    for record in load_hololive_image_manifest().values()
}
YOUTUBER_HOLOLIVE_SOURCE_PAGES = {
    record["source_page"] for record in YOUTUBER_HOLOLIVE_IMAGES.values()
}
YOUTUBER_NIJISANJI_IMAGES = {
    record["image_url"]: record
    for record in load_nijisanji_image_manifest().values()
}
YOUTUBER_NIJISANJI_SOURCE_PAGES = {
    record["source_page"] for record in YOUTUBER_NIJISANJI_IMAGES.values()
}
# 読みにASCII英字が2文字以上続くのは、英名を読みに入れてしまった取り違え
# (例: sekitsui の "Azara's night monkey")。利用側の読み解析がこの手の行で
# 暴走するため、混入を止める。読みはカタカナのみが前提
PRON_ASCII_RE = re.compile(r"[A-Za-z]{2,}")
YEAR_RE = re.compile(r"^(?:NA|前?[0-9]+)$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HAN_RE = re.compile(r"[\u3400-\u9fff]")
MYOJI_EVIDENCE = (
    "person_lists",
    "ndl",
    "wikidata_person",
    "official_web",
    "web_person",
    "jmnedict",
)
MYOJI_HUMAN_EVIDENCE = {
    "person_lists",
    "ndl",
    "wikidata_person",
    "official_web",
    "web_person",
}

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
    if path.name == "youtuber.csv":
        missing = [
            col for col in (
                "image", "image_page", "image_credit", "image_usage",
                "image_terms_page", "scope", "channel_shared",
            )
            if col not in idx
        ]
        if missing:
            err(f"{path.name}: 必須列 {missing[0]} がない")
            return
    if path.name == "myoji.csv":
        missing = [
            col for col in (
                "verified", "rank", "listing_units", "strict_rows",
                "regions", "prefectures", "evidence_sources",
            )
            if col not in idx
        ]
        if missing:
            err(f"{path.name}: 必須列 {missing[0]} がない")
            return
    img_cols = [c for c in ("image", "image_page") if c in idx]
    scientist_years = {}
    fictional_scientist_achievements = {}
    player_groups = {}
    youtuber_snapshots = {}
    youtuber_scopes = {}
    youtuber_channel_shared = {}
    youtuber_images = {}
    youtuber_fan_seen = set()
    youtuber_hololive_seen = set()
    youtuber_nijisanji_seen = set()
    myoji_ranks = {}
    myoji_counts = {}
    myoji_order = []
    myoji_seen_surfaces = set()
    previous_myoji_rank = 0
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
                is_reviewed_youtuber_url = path.name == "youtuber.csv" and (
                    (
                        col == "image"
                        and v in (
                            YOUTUBER_HOLOLIVE_IMAGES
                            | YOUTUBER_NIJISANJI_IMAGES
                        )
                    )
                    or (
                        col == "image_page"
                        and v in (
                            YOUTUBER_FAN_SOURCE_PAGES
                            | YOUTUBER_HOLOLIVE_SOURCE_PAGES
                            | YOUTUBER_NIJISANJI_SOURCE_PAGES
                        )
                    )
                )
                if not is_reviewed_youtuber_url:
                    err(f"{path.name}:{lineno}: {col} が不正なURL: {v[:60]}")
        if "pronunciation" in idx:
            v = f[idx["pronunciation"]]
            if PRON_ASCII_RE.search(v):
                err(
                    f"{path.name}:{lineno}: pronunciation にASCII英字が連続"
                    f"(英名の混入?): {v[:40]}"
                )
        if path.name == "municipality.csv":
            municipality_type = f[idx["municipality_type"]]
            expected_type = f[idx["original"]][-1]
            if municipality_type not in ("市", "区", "町", "村"):
                err(
                    f"{path.name}:{lineno}: municipality_type が不正: "
                    f"{municipality_type}"
                )
            elif municipality_type != expected_type:
                err(
                    f"{path.name}:{lineno}: original/municipality_typeが不整合: "
                    f"{f[idx['original']]} / {municipality_type}"
                )
        if path.name == "school.csv":
            actual = f[idx["has_school_suffix"]]
            expected = has_school_suffix(
                f[idx["surface"]], f[idx["type"]], f[idx["school_type"]]
            )
            if actual != expected:
                err(
                    f"{path.name}:{lineno}: surface/has_school_suffixが不整合: "
                    f"{f[idx['surface']]} / {actual}"
                )
        if path.name == "youtuber.csv":
            person_id = f[idx["id"]]
            creator_scope = f[idx["scope"]]
            if creator_scope not in ("japan", "global", "unknown"):
                err(f"{path.name}:{lineno}: scope が不正: {creator_scope}")
            if (person_id in youtuber_scopes
                    and youtuber_scopes[person_id] != creator_scope):
                err(f"{path.name}:{lineno}: 同じidでscopeが一致しない")
            youtuber_scopes[person_id] = creator_scope
            channel_shared = f[idx["channel_shared"]]
            if channel_shared not in ("yes", "no", "NA"):
                err(f"{path.name}:{lineno}: channel_shared が不正: "
                    f"{channel_shared}")
            if (person_id in youtuber_channel_shared
                    and youtuber_channel_shared[person_id] != channel_shared):
                err(f"{path.name}:{lineno}: 同じidでchannel_sharedが一致しない")
            youtuber_channel_shared[person_id] = channel_shared
            for col in ("image", "image_page"):
                if not f[idx[col]]:
                    err(f"{path.name}:{lineno}: {col} が空")
            image = f[idx["image"]]
            image_page = f[idx["image_page"]]
            image_credit = f[idx["image_credit"]]
            image_usage = f[idx["image_usage"]]
            image_terms_page = f[idx["image_terms_page"]]
            if image.startswith(YOUTUBER_CARD_IMAGE_PREFIX):
                filename = image[len(YOUTUBER_CARD_IMAGE_PREFIX):]
                expected_page = YOUTUBER_CARD_PAGE_PREFIX + filename
                if image_page != expected_page:
                    err(
                        f"{path.name}:{lineno}: カードのimage/image_pageが不整合")
                if not (ROOT / "images" / "youtuber" / filename).is_file():
                    err(
                        f"{path.name}:{lineno}: カードファイルが存在しない: "
                        f"{filename}")
                if image_credit:
                    err(f"{path.name}:{lineno}: 象徴カードにimage_creditがある")
                if image_usage or image_terms_page:
                    err(f"{path.name}:{lineno}: 象徴カードに利用条件がある")
            elif image.startswith(YOUTUBER_FAN_IMAGE_PREFIX):
                record = YOUTUBER_FAN_IMAGES.get(image)
                if not record:
                    err(f"{path.name}:{lineno}: 台帳にないファンメイド画像")
                else:
                    if image_page != record["source_page"]:
                        err(
                            f"{path.name}:{lineno}: ファンメイド画像の"
                            "image_pageが台帳と不一致")
                    if image_credit != record["credit"]:
                        err(
                            f"{path.name}:{lineno}: ファンメイド画像の"
                            "image_creditが台帳と不一致")
                    if image_usage != "noncommercial_fanwork":
                        err(
                            f"{path.name}:{lineno}: ファンメイド画像の"
                            "image_usageが不正")
                    if image_terms_page != record["guideline_url"]:
                        err(
                            f"{path.name}:{lineno}: ファンメイド画像の"
                            "image_terms_pageが台帳と不一致")
                    if f[idx["original"]] != record["original"]:
                        err(
                            f"{path.name}:{lineno}: ファンメイド画像の"
                            "人物が台帳と不一致")
                    youtuber_fan_seen.add(record["original"])
            elif image in YOUTUBER_HOLOLIVE_IMAGES:
                record = YOUTUBER_HOLOLIVE_IMAGES[image]
                expected_status = (
                    "current" if record["talent_status"] == "current" else "former"
                )
                checks = (
                    (image_page, record["source_page"], "image_page"),
                    (image_credit, record["credit"], "image_credit"),
                    (image_usage, HOLOLIVE_IMAGE_USAGE, "image_usage"),
                    (image_terms_page, record["terms_page"], "image_terms_page"),
                    (f[idx["original"]], record["original"], "人物"),
                    (f[idx["status"]], expected_status, "status"),
                )
                for actual, expected, label in checks:
                    if actual != expected:
                        err(
                            f"{path.name}:{lineno}: ホロライブ公式画像の"
                            f"{label}が台帳と不一致"
                        )
                youtuber_hololive_seen.add(record["original"])
            elif image in YOUTUBER_NIJISANJI_IMAGES:
                record = YOUTUBER_NIJISANJI_IMAGES[image]
                checks = (
                    (image_page, record["source_page"], "image_page"),
                    (image_credit, record["credit"], "image_credit"),
                    (image_usage, NIJISANJI_IMAGE_USAGE, "image_usage"),
                    (image_terms_page, record["terms_page"], "image_terms_page"),
                    (f[idx["original"]], record["original"], "人物"),
                    (f[idx["status"]], "current", "status"),
                )
                for actual, expected, label in checks:
                    if actual != expected:
                        err(
                            f"{path.name}:{lineno}: にじさんじ公式画像の"
                            f"{label}が台帳と不一致"
                        )
                youtuber_nijisanji_seen.add(record["original"])
            elif not image_page.startswith("https://commons.wikimedia.org/wiki/File:"):
                err(
                    f"{path.name}:{lineno}: 実写のimage_pageがCommonsでない: "
                    f"{image_page[:60]}")
            elif image_credit:
                err(f"{path.name}:{lineno}: Commons画像にimage_creditがある")
            elif image_usage or image_terms_page:
                err(f"{path.name}:{lineno}: Commons画像に利用条件がある")
            image_pair = (
                image, image_page, image_credit, image_usage, image_terms_page,
            )
            if (person_id in youtuber_images
                    and youtuber_images[person_id] != image_pair):
                err(f"{path.name}:{lineno}: 同じidで画像が一致しない")
            youtuber_images[person_id] = image_pair

            snapshot_cols = ("channel", "subscribers", "subscribers_as_of")
            missing = [col for col in snapshot_cols if col not in idx]
            if missing:
                err(f"{path.name}: 必須列 {missing[0]} がない")
                return
            snapshot = tuple(f[idx[col]] for col in snapshot_cols)
            channel_present = snapshot[0] not in ("", "NA")
            subscriber_snapshot = (
                snapshot[1].isdigit() and ISO_DATE_RE.fullmatch(snapshot[2]))
            subscriber_unavailable = snapshot[1:] == ("NA", "NA")
            if snapshot != ("NA", "NA", "NA") and not (
                    channel_present
                    and (subscriber_snapshot or subscriber_unavailable)):
                err(
                    f"{path.name}:{lineno}: channel/subscribers/取得日が不整合: "
                    f"{' / '.join(snapshot)}"
                )
            if (person_id in youtuber_snapshots
                    and youtuber_snapshots[person_id] != snapshot):
                err(f"{path.name}:{lineno}: 同じidでチャンネル情報が一致しない")
            youtuber_snapshots[person_id] = snapshot
            if channel_shared == "yes" and not (
                    channel_present and subscriber_unavailable):
                err(f"{path.name}:{lineno}: 共有チャンネルに個人登録者数がある")
        if path.name == "myoji.csv":
            surface = f[idx["surface"]]
            count_names = ("listing_units", "strict_rows", "regions", "prefectures")
            count_values = {}
            for name in count_names:
                value = f[idx[name]]
                if not value.isdigit() or int(value) < 1:
                    err(f"{path.name}:{lineno}: {name} が正の整数でない: {value}")
                else:
                    count_values[name] = int(value)
            if len(count_values) == len(count_names):
                if count_values["listing_units"] > count_values["strict_rows"]:
                    err(f"{path.name}:{lineno}: listing_units が strict_rows より多い")
                if count_values["prefectures"] > count_values["regions"]:
                    err(f"{path.name}:{lineno}: prefectures が regions より多い")
                counts = tuple(f[idx[name]] for name in count_names)
                if surface in myoji_counts and myoji_counts[surface] != counts:
                    err(f"{path.name}:{lineno}: 同じ名字で件数が一致しない: {surface}")
                myoji_counts[surface] = counts
            rank = f[idx["rank"]]
            if not rank.isdigit() or int(rank) < 1:
                err(f"{path.name}:{lineno}: rank が正の整数でない: {rank}")
            else:
                numeric_rank = int(rank)
                if numeric_rank < previous_myoji_rank:
                    err(f"{path.name}:{lineno}: rank が昇順でない: {rank}")
                previous_myoji_rank = numeric_rank
                original = f[idx["original"]]
                if original in myoji_ranks and myoji_ranks[original] != rank:
                    err(f"{path.name}:{lineno}: 同じ名字でrankが一致しない: {original}")
                myoji_ranks[original] = rank
                if surface not in myoji_seen_surfaces and "listing_units" in count_values:
                    myoji_order.append(
                        (lineno, surface, numeric_rank, count_values["listing_units"])
                    )
                    myoji_seen_surfaces.add(surface)
            sources = [s for s in f[idx["evidence_sources"]].split("|") if s]
            if any(s not in MYOJI_EVIDENCE for s in sources):
                err(
                    f"{path.name}:{lineno}: evidence_sources が不正: "
                    f"{f[idx['evidence_sources']]}"
                )
            canonical = [s for s in MYOJI_EVIDENCE if s in sources]
            if sources != canonical:
                err(
                    f"{path.name}:{lineno}: evidence_sources の順序・重複が不正: "
                    f"{f[idx['evidence_sources']]}"
                )
            if f[idx["verified"]] == "yes" and not (
                MYOJI_HUMAN_EVIDENCE & set(sources)
            ):
                err(f"{path.name}:{lineno}: verified=yes に人物の裏付けがない")
        if path.name in ("baseball.csv", "football.csv") and "description" in idx:
            v = f[idx["description"]]
            player_groups.setdefault(f[idx["id"]], []).append((lineno, f))
            if v.strip().rstrip("。").strip() == "NA":
                err(
                    f"{path.name}:{lineno}: descriptionにNA sentinelが残っている"
                )
            if v and not is_standalone_player_description(v):
                err(
                    f"{path.name}:{lineno}: descriptionが単独で完結していない: {v[:65]}"
                )
            if v and has_redundant_player_subject(v):
                err(f"{path.name}:{lineno}: descriptionの人名主語が冗長: {v[:65]}")
            if (
                path.name == "football.csv"
                and v
                and is_likely_disambiguation_text(v)
            ):
                err(
                    f"{path.name}:{lineno}: descriptionが曖昧さ回避ページ由来: {v[:65]}"
                )
        if path.name == "scientist.csv":
            # 漢字名の family 行は姓の表記を保つ。読みを surface に誤記すると、
            # 動画字幕でも「小田」ではなく「おだ」のように表示されてしまう。
            if (
                f[idx["type"]] == "family"
                and HAN_RE.search(f[idx["original"]])
                and not HAN_RE.search(f[idx["surface"]])
            ):
                err(
                    f"{path.name}:{lineno}: 漢字名のfamily surfaceが漢字でない: "
                    f"{f[idx['surface']]}"
                )
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
        if path.name == "fictional_scientist.csv":
            achievement = f[idx["achievement"]]
            if not 8 <= len(achievement) <= 90 or not achievement.endswith("。"):
                err(
                    f"{path.name}:{lineno}: achievementが短い完結文でない: "
                    f"{achievement[:65]}"
                )
            person_id = f[idx["id"]]
            if (
                person_id in fictional_scientist_achievements
                and fictional_scientist_achievements[person_id] != achievement
            ):
                err(f"{path.name}:{lineno}: 同じidでachievementが一致しない")
            fictional_scientist_achievements[person_id] = achievement
    if path.name == "youtuber.csv":
        expected = {record["original"] for record in YOUTUBER_FAN_IMAGES.values()}
        if youtuber_fan_seen != expected:
            missing = sorted(expected - youtuber_fan_seen)
            extra = sorted(youtuber_fan_seen - expected)
            detail = f"未適用={missing} 余分={extra}"
            err(f"{path.name}: ファンメイド画像台帳の適用が不完全: {detail}")
        hololive_expected = {
            record["original"] for record in YOUTUBER_HOLOLIVE_IMAGES.values()
        }
        if youtuber_hololive_seen != hololive_expected:
            missing = sorted(hololive_expected - youtuber_hololive_seen)
            extra = sorted(youtuber_hololive_seen - hololive_expected)
            detail = f"未適用={missing} 余分={extra}"
            err(f"{path.name}: ホロライブ公式画像台帳の適用が不完全: {detail}")
        nijisanji_expected = {
            record["original"] for record in YOUTUBER_NIJISANJI_IMAGES.values()
        }
        if youtuber_nijisanji_seen != nijisanji_expected:
            missing = sorted(nijisanji_expected - youtuber_nijisanji_seen)
            extra = sorted(youtuber_nijisanji_seen - nijisanji_expected)
            detail = f"未適用={missing} 余分={extra}"
            err(f"{path.name}: にじさんじ公式画像台帳の適用が不完全: {detail}")
    if path.name == "myoji.csv":
        previous_count = None
        expected_rank = 0
        for position, (lineno, surface, rank, count) in enumerate(myoji_order, 1):
            if previous_count is not None and count > previous_count:
                err(f"{path.name}:{lineno}: listing_units が降順でない: {surface}")
            if count != previous_count:
                expected_rank = position
                previous_count = count
            if rank != expected_rank:
                err(
                    f"{path.name}:{lineno}: rank が件数の競争順位でない: "
                    f"{surface} ({rank}, 期待 {expected_rank})"
                )
    if player_groups:
        for group_rows in player_groups.values():
            descriptions = {fields[idx["description"]] for _, fields in group_rows}
            if len(descriptions) != 1:
                err(f"{path.name}:{group_rows[0][0]}: 同じidでdescriptionが一致しない")
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
        if not fields[idx["order"]].endswith("目") or not fields[
            idx["family"]
        ].endswith("科"):
            err(f"{path.name}:{item_id + 2}: order/familyが不正: {name}")
        description = fields[idx["description"]]
        if description and (
            not 8 <= len(description) <= 90 or not description.endswith("。")
        ):
            err(f"{path.name}:{item_id + 2}: descriptionが不正: {name}")
        if description and re.match(
            rf"^(?:{re.escape(name)}|本種)(?:は|が)[、 ]*", description
        ):
            err(f"{path.name}:{item_id + 2}: descriptionの主語が冗長: {name}")
        if description and ("WoRMS" in description or "学名は" in description):
            err(
                f"{path.name}:{item_id + 2}: descriptionが出典メタデータを重複表示: {name}"
            )
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
                    filename
                    for group, filename in IMAGE_FILE_BY_GROUP.items()
                    if group not in {"哺乳類", "爬虫類", "魚類"}
                )
            if not any(
                image.endswith(f"/images/marine_life/{filename}")
                for filename in valid_fallbacks
            ):
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
