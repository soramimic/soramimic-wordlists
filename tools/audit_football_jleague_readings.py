#!/usr/bin/env python3
"""Jリーグ候補CSVとmanifestの読み品質を監査する。

既存の生成器や ``football.csv`` は変更せず、レビュー用候補に対して実行する。
Jリーグ公式fallbackを採用するmanifestは、次の ``reading_evidence`` を持つ想定。

    {
      "method": "registered_katakana" | "katakana_search_match",
      "status": "verified",
      "player_id": "7647",
      "url": "https://data.j-league.or.jp/SFIX04/?player_id=7647",
      "registered_name": "青山　敏弘",
      "official_english_name": "Toshihiro AOYAMA"
    }

``romanization_guess`` は、英字名から長音や外国語名の読みを一意に復元できないため、
採用候補では常にerrorにする。記事をparseできない人物はCSVへ混ぜず、manifest上の
review対象として報告する。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

KATAKANA = re.compile(r"^[ァ-ヶー・=＝\s]+$")
ROMAN_GUESS = re.compile(
    r"roman|romaji|english|latin|transliterat|ローマ字|英字", re.I
)
JLEAGUE_PROVIDER = re.compile(r"j[. _-]?league|jリーグ", re.I)
SAFE_JLEAGUE_METHODS = {"registered_katakana", "katakana_search_match"}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    subject: str
    message: str


def _compact(value: str) -> str:
    return re.sub(r"[・=＝\s]", "", value or "")


def _is_katakana(value: str) -> bool:
    return bool(value and KATAKANA.fullmatch(value))


def load_manifest(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as stream:
        for lineno, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{lineno}: manifest record must be an object")
            records.append(value)
    return records


def load_candidates(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def audit_candidates(rows: list[dict]) -> list[Issue]:
    issues: list[Issue] = []
    by_id: dict[str, list[dict]] = defaultdict(list)
    for index, row in enumerate(rows, 2):
        subject = f"csv:{index}"
        pronunciation = row.get("pronunciation", "")
        if not pronunciation or not _is_katakana(pronunciation):
            issues.append(Issue(
                "error", "invalid_pronunciation_characters", subject,
                "pronunciation must contain only full-width Katakana and name separators",
            ))
        by_id[row.get("id", "")].append(row)

    for candidate_id, group in by_id.items():
        subject = f"candidate:{candidate_id or '<missing-id>'}"
        full_rows = [row for row in group if row.get("type") == "full"]
        if len(full_rows) != 1:
            issues.append(Issue(
                "error", "full_row_count", subject,
                f"expected exactly one full row, found {len(full_rows)}",
            ))
            continue
        full = full_rows[0]
        surface = full.get("surface", "")
        pronunciation = full.get("pronunciation", "")
        if _is_katakana(surface) and _compact(surface) != _compact(pronunciation):
            issues.append(Issue(
                "error", "katakana_registered_name_mismatch", subject,
                "Katakana registered name is a direct reading source; do not replace it "
                "with an English-name guess",
            ))
        if _is_katakana(surface):
            full_reading = _compact(pronunciation)
            for row in group:
                if row.get("type") in {"family", "given"} and (
                    not _compact(row.get("pronunciation", ""))
                    or _compact(row.get("pronunciation", "")) not in full_reading
                ):
                    issues.append(Issue(
                        "error", "katakana_component_not_in_full_name", subject,
                        f"{row.get('type')} reading is not a component of the full reading",
                    ))
    return issues


def _reading_evidence(record: dict) -> dict:
    evidence = record.get("reading_evidence", {})
    return evidence if isinstance(evidence, dict) else {}


def audit_manifest(records: list[dict]) -> list[Issue]:
    issues: list[Issue] = []
    for index, record in enumerate(records, 1):
        subject = str(record.get("article") or record.get("qid") or f"manifest:{index}")
        status = str(record.get("status", ""))
        reason = str(record.get("reason", ""))
        provider = str(record.get("reading_provider", ""))
        evidence = _reading_evidence(record)
        method = str(evidence.get("method") or record.get("reading_method") or "")
        verification = str(evidence.get("status") or record.get("reading_status") or "")

        if reason == "reading_unparsed":
            issues.append(Issue(
                "warning", "wikipedia_parse_person_failed", subject,
                "parse_person failed; keep this person out of the CSV and review an "
                "individual official-page fallback",
            ))
            continue
        if status != "accepted":
            continue
        if not provider:
            issues.append(Issue(
                "error", "missing_reading_provider", subject,
                "accepted reading has no provider provenance",
            ))

        provenance = " ".join((provider, method))
        if ROMAN_GUESS.search(provenance) or method == "romanization_guess":
            issues.append(Issue(
                "error", "romanization_guess_accepted", subject,
                "English/Latin spelling cannot determine Japanese long vowels, name "
                "order, or Korean/Chinese conventional readings",
            ))

        # reading_evidence はWikipediaの版・抽出箇所を記録する用途にも使える。
        # オブジェクトが存在するだけではJリーグ公式fallbackとみなさない。
        reading_sources = " ".join((
            provider,
            str(record.get("reading_source", "")),
            str(evidence.get("provider", "")),
            str(evidence.get("source", "")),
        ))
        is_jleague = bool(JLEAGUE_PROVIDER.search(reading_sources))
        if not is_jleague:
            continue
        if method not in SAFE_JLEAGUE_METHODS:
            issues.append(Issue(
                "error", "unsafe_jleague_fallback_method", subject,
                "official fallback must use registered_katakana or an individually "
                "verified katakana_search_match",
            ))
        if verification != "verified":
            issues.append(Issue(
                "error", "unverified_jleague_fallback", subject,
                "official fallback is accepted without status=verified",
            ))
        player_id = str(evidence.get("player_id", ""))
        url = str(evidence.get("url", ""))
        if not player_id or f"player_id={player_id}" not in url:
            issues.append(Issue(
                "error", "missing_individual_official_source", subject,
                "record player_id and its SFIX04 individual URL; do not cite a bulk list",
            ))
        registered_name = str(evidence.get("registered_name", ""))
        resolved = str(evidence.get("resolved_reading") or record.get("pronunciation") or "")
        if method == "registered_katakana":
            if not _is_katakana(registered_name):
                issues.append(Issue(
                    "error", "registered_katakana_not_katakana", subject,
                    "registered_katakana evidence must contain the displayed Katakana name",
                ))
            elif resolved and _compact(registered_name) != _compact(resolved):
                issues.append(Issue(
                    "error", "registered_katakana_evidence_mismatch", subject,
                    "resolved reading differs from the displayed Katakana registered name",
                ))
        if method == "katakana_search_match" and not evidence.get("identity_match"):
            issues.append(Issue(
                "error", "katakana_search_identity_unverified", subject,
                "a search hit must also match identity evidence such as birth date; a "
                "same-name hit is insufficient",
            ))
    return issues


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="print issues as JSON")
    parser.add_argument(
        "--fail-on", choices=("error", "warning"), default="error",
        help="warning also fails when set to warning",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        issues = audit_candidates(load_candidates(args.candidates))
        issues += audit_manifest(load_manifest(args.manifest))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([asdict(issue) for issue in issues], ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            print(f"{issue.severity}: {issue.code}: {issue.subject}: {issue.message}")
        errors = sum(issue.severity == "error" for issue in issues)
        warnings = sum(issue.severity == "warning" for issue in issues)
        print(f"reading audit: {errors} error(s), {warnings} warning(s)")
    threshold = {"error": 2, "warning": 1}[args.fail_on]
    return int(any({"warning": 1, "error": 2}[issue.severity] >= threshold
                   for issue in issues))


if __name__ == "__main__":
    sys.exit(main())
