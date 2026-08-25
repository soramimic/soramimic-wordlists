#!/usr/bin/env python3
"""確定済みWikipedia本文から選手descriptionの候補文をLLMで選ぶ。

LLMは本文に完全一致する連続した抜粋だけを返せる。選ばれた抜粋は既存の
``make_player_description`` で整形し、決定的な検証を通った場合だけ同じIDの全行へ
適用する。取得と適用を分離し、月次更新では成功済みcacheだけをCSVへ反映する。

Examples:
  # 月次更新で追加・変更された選手をcacheへ取得（CSVは変更しない）
  python tools/enrich_player_descriptions_openai.py baseball \
      --fetch --changed-from HEAD --limit 100

  # 同じ入力のcacheだけを使って適用（OpenAI networkは使用しない）
  python tools/enrich_player_descriptions_openai.py baseball \
      --apply --cache-only --changed-from HEAD --limit 100

  # 欠損backlogを小分けに取得
  python tools/enrich_player_descriptions_openai.py football \
      --fetch --include-missing --limit 100
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_player_descriptions import (  # noqa: E402
    CONFIG,
    article_candidates,
    fetch_intros,
    is_missing_description,
    load_cache,
)
from openai_source_selector import (  # noqa: E402
    CacheMissError,
    DEFAULT_MODEL,
    PROMPT_VERSION,
    Selection,
    SourceRecord,
    SourceSelector,
)
from wpnames import (  # noqa: E402
    HIRA2KATA,
    has_redundant_player_subject,
    is_likely_disambiguation_text,
    is_standalone_player_description,
    make_player_description,
    vnorm,
)

ROOT = Path(__file__).resolve().parent.parent
VERIFIED_FOOTBALL_SOURCES = (
    Path(__file__).resolve().parent / "football_jleague_verified_sources.jsonl"
)
VERIFIED_BASEBALL_SOURCES = (
    Path(__file__).resolve().parent / "baseball_verified_sources.jsonl"
)
SELECTOR_DB_PATH = (
    Path(__file__).resolve().parent / ".cache" / "openai-source-selector.sqlite3"
)
PROVENANCE_PATH = (
    Path(__file__).resolve().parent / "openai_player_description_sources.jsonl"
)
PENDING_PATH = (
    Path(__file__).resolve().parent / "openai_player_description_pending.jsonl"
)
MAX_DAILY_TOKEN_BUDGET = 2_000_000
MAX_SOURCE_CHARS = 6_000
# 4096 output tokens include hidden reasoning tokens.  Ten records leave room
# for complete Japanese source sentences plus the structured JSON envelope.
BATCH_SIZE = 10
SPORT_SUFFIXES = {
    "baseball": (" (野球)", " (野球選手)"),
    "football": (" (サッカー選手)",),
}
PROVENANCE_FIELDS = frozenset({
    "kind", "id", "qid", "title", "page_url", "revision_id",
    "source_excerpt", "description", "model", "prompt_version",
    "license", "license_url", "modified",
})
PENDING_FIELDS = frozenset({"kind", "id", "attempts", "reason"})
PENDING_REASONS = frozenset({
    "awaiting_source_selection", "source_unverified", "no_supported_excerpt",
    "ambiguous_source",
})


@dataclass(frozen=True)
class PlayerCandidate:
    kind: str
    group_id: str
    title: str
    record: SourceRecord
    qid: str = ""


def refresh_intros(
    titles: list[str], cache: dict[str, dict[str, str]]
) -> None:
    """Refresh every candidate title during fetch; apply remains offline."""
    fetch_intros(titles, cache, refresh=True)


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        columns = list(reader.fieldnames or ())
    if not columns:
        raise ValueError(f"empty CSV: {path}")
    return columns, rows


def _id_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def read_jsonl(path: Path) -> list[dict]:
    """Read deterministic JSONL, accepting a not-yet-created empty ledger."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return []
    if not raw:
        return []
    if b"\r" in raw or raw.endswith(b"\n"):
        raise ValueError(f"{path.name} must use LF without a trailing newline")
    records: list[dict] = []
    for lineno, line in enumerate(raw.decode("utf-8").split("\n"), 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL: {path}:{lineno}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"JSONL record must be an object: {path}:{lineno}")
        records.append(record)
    return records


def load_provenance(path: Path | None = None) -> dict[tuple[str, str], dict]:
    path = path or PROVENANCE_PATH
    records: dict[tuple[str, str], dict] = {}
    for lineno, record in enumerate(read_jsonl(path), 1):
        if set(record) != PROVENANCE_FIELDS:
            raise ValueError(f"invalid provenance fields: {path}:{lineno}")
        kind = record.get("kind")
        group_id = record.get("id")
        key = (kind, group_id)
        if (
            not isinstance(kind, str)
            or not isinstance(group_id, str)
            or key in records
            or kind not in CONFIG
            or not group_id
        ):
            raise ValueError(f"invalid or duplicate provenance key: {path}:{lineno}")
        records[(kind, group_id)] = record
    return records


def load_pending(path: Path | None = None) -> dict[tuple[str, str], dict]:
    path = path or PENDING_PATH
    records: dict[tuple[str, str], dict] = {}
    for lineno, record in enumerate(read_jsonl(path), 1):
        if set(record) != PENDING_FIELDS:
            raise ValueError(f"invalid pending fields: {path}:{lineno}")
        kind = record.get("kind")
        group_id = record.get("id")
        key = (kind, group_id)
        attempts = record.get("attempts")
        if (
            not isinstance(kind, str)
            or not isinstance(group_id, str)
            or key in records
            or kind not in CONFIG
            or not group_id
            or isinstance(attempts, bool)
            or not isinstance(attempts, int)
            or attempts < 1
            or record.get("reason") not in PENDING_REASONS
        ):
            raise ValueError(f"invalid or duplicate pending record: {path}:{lineno}")
        records[(kind, group_id)] = record
    return records


def jsonl_bytes(records: Iterable[dict]) -> bytes:
    ordered = sorted(
        records,
        key=lambda item: (str(item["kind"]), _id_sort_key(str(item["id"]))),
    )
    return "\n".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for item in ordered
    ).encode("utf-8")


def csv_bytes(columns: list[str], rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    text = buffer.getvalue().rstrip("\n")
    if '"' in text:
        bad = [line for line in text.splitlines() if '"' in line][:3]
        raise ValueError(f"quoted field would break the naive parser: {bad}")
    return text.encode("utf-8")


def _stage_bytes(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        os.chmod(temporary, path.stat().st_mode if path.exists() else 0o644)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def atomic_write_bundle(contents: dict[Path, bytes]) -> None:
    """Stage every output, then publish it as one rollback-capable bundle."""
    originals = {
        path: (path.read_bytes(), path.stat().st_mode) if path.exists() else None
        for path in contents
    }
    staged: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        staged = {path: _stage_bytes(path, content) for path, content in contents.items()}
        try:
            for path, temporary in staged.items():
                os.replace(temporary, path)
                replaced.append(path)
        except Exception:
            for path in reversed(replaced):
                original = originals[path]
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    restore = _stage_bytes(path, original[0])
                    os.chmod(restore, original[1])
                    os.replace(restore, path)
            raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def restore_snapshots(snapshots: dict[Path, bytes | None]) -> None:
    """Restore the exact pre-apply state after a multi-list failure."""
    existing = {path: content for path, content in snapshots.items() if content is not None}
    if existing:
        atomic_write_bundle(existing)  # type: ignore[arg-type]
    for path, content in snapshots.items():
        if content is None:
            path.unlink(missing_ok=True)


def rows_from_git(ref: str, path: Path) -> list[dict[str, str]]:
    """ref上のCSVを読む。shellを介さず、refはgit自身に解釈させる。"""
    relative = path.relative_to(ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return list(csv.DictReader(result.stdout.splitlines()))


def group_rows(rows: Iterable[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(row["id"], []).append(row)
    return groups


def description_state(rows: Iterable[dict[str, str]]) -> tuple[str, ...]:
    return tuple(sorted({row.get("description", "") for row in rows}))


def is_degraded_description(value: str) -> bool:
    """規則で欠損・構造不良と確定でき、出典からの再選択が必要な値か。"""
    return bool(
        is_missing_description(value)
        or not is_standalone_player_description(value)
        or has_redundant_player_subject(value)
        or is_likely_disambiguation_text(value)
        or value.count("（") != value.count("）")
        or value.count("(") != value.count(")")
    )


def changed_description_ids(
    current: dict[str, list[dict[str, str]]],
    previous_rows: Iterable[dict[str, str]],
) -> set[str]:
    previous = group_rows(previous_rows)
    return {
        group_id
        for group_id, rows in current.items()
        if group_id not in previous
        or description_state(rows) != description_state(previous[group_id])
    }


def target_group_ids(
    groups: dict[str, list[dict[str, str]]],
    *,
    previous_rows: Iterable[dict[str, str]] | None,
    include_missing: bool,
    include_degraded: bool,
    limit: int,
    start_after: str | None = None,
    pending_attempts: dict[str, int] | None = None,
) -> list[str]:
    selected: set[str] = set()
    changed: set[str] = set()
    if previous_rows is not None:
        changed = changed_description_ids(groups, previous_rows)
        selected.update(changed)
    if include_missing:
        selected.update(
            group_id
            for group_id, rows in groups.items()
            if any(is_missing_description(row.get("description", "")) for row in rows)
        )
    if include_degraded:
        selected.update(
            group_id
            for group_id, rows in groups.items()
            if any(
                is_degraded_description(row.get("description", "")) for row in rows
            )
        )
    pending_attempts = pending_attempts or {}
    pending = {group_id for group_id in pending_attempts if group_id in groups}
    # changed-fromは月次更新で一度しか現れない集合なので、黙って切り捨てると
    # 次月以降二度と対象にならない。新規集合だけで上限超過なら処理前に停止する。
    if previous_rows is not None and len(changed) > limit:
        raise ValueError(
            f"{len(changed)} changed groups exceed --limit {limit}; "
            "increase --limit after checking the daily token budget"
        )
    if previous_rows is not None:
        ordered_changed = sorted(changed, key=_id_sort_key)
        remaining = limit - len(ordered_changed)
        # 未解決候補は試行回数の少ないものから回し、同じabstainが後続を
        # 永久に塞がないようにする。
        ordered_pending = sorted(
            (pending | selected) - changed,
            key=lambda value: (pending_attempts.get(value, 0), _id_sort_key(value)),
        )
        return ordered_changed + ordered_pending[:remaining]

    ordered = sorted(selected, key=_id_sort_key)
    if start_after is not None:
        cursor_key = _id_sort_key(start_after)
        ordered = [value for value in ordered if _id_sort_key(value) > cursor_key]
    return ordered[:limit]


def load_verified_football_sources(
    path: Path = VERIFIED_FOOTBALL_SOURCES,
) -> dict[str, dict[str, str]]:
    sources: dict[str, dict[str, str]] = {}
    if not path.exists():
        return sources
    with path.open(encoding="utf-8") as stream:
        for lineno, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL: {path}:{lineno}") from exc
            verified_id = str(item.get("verified_id", ""))
            article = str(item.get("article", ""))
            if verified_id and article:
                sources[verified_id] = item
    return sources


def load_verified_sources(kind: str) -> dict[str, dict[str, str]]:
    path = VERIFIED_FOOTBALL_SOURCES if kind == "football" else VERIFIED_BASEBALL_SOURCES
    return load_verified_football_sources(path)


def source_titles(
    kind: str,
    group_id: str,
    rows: list[dict[str, str]],
    verified: dict[str, dict[str, str]],
) -> list[str]:
    titles: list[str] = []
    if group_id in verified:
        titles.append(str(verified[group_id]["article"]))
    base = article_candidates(kind, rows)
    titles.extend(base)
    for title in base:
        plain = re.sub(r"\s+\([^)]*\)$", "", title).strip()
        titles.extend(plain + suffix for suffix in SPORT_SUFFIXES[kind])
    return list(dict.fromkeys(title for title in titles if title))


def _normalized_reading(value: str) -> str:
    return re.sub(r"[\s　・=＝]", "", value.translate(HIRA2KATA))


def intro_reading(intro: str) -> str:
    match = re.match(
        r"^[^（(]{1,80}[（(]\s*([ぁ-ゖァ-ヶー・=＝\s　]+?)(?:[、,]|[）)])",
        intro,
    )
    return _normalized_reading(match.group(1)) if match else ""


def full_readings(rows: Iterable[dict[str, str]]) -> set[str]:
    return {
        _normalized_reading(row.get("pronunciation", ""))
        for row in rows
        if row.get("type") == "full" and row.get("pronunciation")
    }


def full_identity_keys(rows: Iterable[dict[str, str]]) -> set[tuple[str, str]]:
    """baseballの同名同読み衝突を検出するための既存行だけから成るkey。"""
    return {
        (
            re.sub(r"[\s　]", "", vnorm(row.get("surface", ""))),
            _normalized_reading(row.get("pronunciation", "")),
        )
        for row in rows
        if row.get("type") == "full"
        and row.get("surface")
        and row.get("pronunciation")
    }


def source_matches_identity(
    kind: str,
    group_id: str,
    rows: list[dict[str, str]],
    article: dict[str, str],
    verified: dict[str, dict[str, str]],
    requested_title: str = "",
) -> bool:
    """既存の同定情報だけで本文が対象人物に対応すると確認する。"""
    intro = str(article.get("intro", ""))
    source_qid = str(article.get("qid", ""))
    if (
        not intro
        or not str(article.get("revision", "")).strip()
        or not re.fullmatch(r"Q[1-9][0-9]*", source_qid)
        or article.get("disambiguation")
        or is_likely_disambiguation_text(intro)
    ):
        return False
    if not any(keyword in intro for keyword in CONFIG[kind]["keywords"]):
        return False

    # legacy baseballの同じ語IDに複数の元選手が束ねられた行は自動同定しない。
    if kind == "baseball":
        org_ids = {row.get("org_id", "") for row in rows if row.get("org_id")}
        if len(org_ids) > 1:
            return False

    identity_verified = False
    qids = {row.get("wikidata", "") for row in rows if row.get("wikidata")}
    verified_qid = str(verified.get(group_id, {}).get("qid", ""))
    if verified_qid:
        qids.add(verified_qid)
    # CSVと確認済み台帳が衝突している場合は、どちらかをモデルで選ばない。
    if len(qids) > 1:
        return False
    if qids and source_qid not in qids:
        return False
    if len(qids) == 1:
        identity_verified = True

    verified_article = str(verified.get(group_id, {}).get("article", ""))
    if requested_title and requested_title == verified_article:
        identity_verified = True

    # 冒頭に読みが明記されている場合はCSVのfull読みとも一致させる。同名の
    # 同競技選手を名前だけで取り違えるのを防ぐ。
    source_reading = intro_reading(intro)
    expected_readings = full_readings(rows)
    if source_reading and expected_readings and source_reading not in expected_readings:
        return False
    # 競技語と同名だけでは、同名の別選手を排除できない。既存QID、確認済み
    # 記事台帳のどちらかを必須にする。読み一致は拒否条件には使えるが、CSV外の
    # 同名同読み人物を排除できないため、それだけを本人同定の根拠にはしない。
    return identity_verified


def build_candidates(
    kind: str,
    groups: dict[str, list[dict[str, str]]],
    target_ids: Iterable[str],
    source_cache: dict[str, dict[str, str]],
    verified: dict[str, dict[str, str]],
) -> list[PlayerCandidate]:
    candidates: list[PlayerCandidate] = []
    colliding_baseball_ids: set[str] = set()
    if kind == "baseball":
        ids_by_identity: dict[tuple[str, str], set[str]] = {}
        for existing_id, existing_rows in groups.items():
            for identity in full_identity_keys(existing_rows):
                ids_by_identity.setdefault(identity, set()).add(existing_id)
        colliding_baseball_ids = {
            existing_id
            for ids in ids_by_identity.values()
            if len(ids) > 1
            for existing_id in ids
        }
    for group_id in target_ids:
        rows = groups[group_id]
        # baseballにはQID列がなく、同名同読みの別選手は記事名と読みだけでは
        # 一意にできない。候補集合全体で衝突するIDはモデルへ送らない。
        if group_id in colliding_baseball_ids:
            continue
        descriptions = description_state(rows)
        if len(descriptions) != 1:
            raise ValueError(f"{kind}:{group_id}: descriptions disagree within id")
        for requested_title in source_titles(kind, group_id, rows, verified):
            article = source_cache.get(requested_title, {})
            if not source_matches_identity(
                kind,
                group_id,
                rows,
                article,
                verified,
                requested_title,
            ):
                continue
            source = str(article["intro"])[:MAX_SOURCE_CHARS]
            title = str(article.get("title", requested_title))
            record = SourceRecord(
                key=f"{kind}:{group_id}",
                title=title,
                source=source,
                revision=str(article.get("revision", "")),
                draft=descriptions[0],
            )
            candidates.append(PlayerCandidate(
                kind, group_id, title, record, str(article.get("qid", ""))
            ))
            break
    return candidates


def require_cached_sources(
    titles: Iterable[str], source_cache: dict[str, dict[str, str]]
) -> None:
    """Require the exact raw-source cache needed by an offline apply."""
    required = {"title", "intro", "disambiguation", "qid", "revision"}
    missing = [
        title
        for title in titles
        if title not in source_cache
        or not isinstance(source_cache[title], dict)
        or not required.issubset(source_cache[title])
    ]
    if missing:
        preview = ", ".join(missing[:5])
        raise ValueError(f"raw source cache is incomplete: {preview}")


def select_in_batches(
    selector: SourceSelector,
    candidates: list[PlayerCandidate],
    *,
    cache_only: bool,
) -> dict[str, Selection]:
    selections: dict[str, Selection] = {}
    for offset in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[offset:offset + BATCH_SIZE]
        result = selector.select(
            [candidate.record for candidate in batch],
            cache_only=cache_only,
        )
        for candidate in batch:
            selection = result[candidate.record.key]
            if selection.action != "select":
                continue
            try:
                render_selected_description(candidate, selection)
            except ValueError as exc:
                # SourceSelectorの汎用的な完全一致検査を通っていても、リスト固有の
                # 完結性・長さ規則に合わない選択は安全なabstainへ落とす。同じcacheを
                # apply時にも決定的に扱えるため、無限に失敗するcacheを作らない。
                print(f"warning: {exc}; abstaining", file=sys.stderr)
                result[candidate.record.key] = Selection(
                    "abstain", "", "no_supported_excerpt"
                )
        overlap = selections.keys() & result.keys()
        if overlap:
            raise ValueError(f"duplicate selector keys: {sorted(overlap)}")
        selections.update(result)
    return selections


def is_complete_source_excerpt(source: str, excerpt: str) -> bool:
    """excerptがsource中の1つ以上の完全な日本語文かを返す。"""
    terminators = "。！？"
    start_boundaries = "。！？\r\n"
    if (
        not excerpt
        or excerpt != excerpt.strip()
        or excerpt[0] in start_boundaries
        or excerpt[-1] not in terminators
    ):
        return False
    offset = 0
    while True:
        position = source.find(excerpt, offset)
        if position < 0:
            return False
        end = position + len(excerpt)
        starts_at_boundary = (
            position == 0 or source[position - 1] in start_boundaries
        )
        ends_at_boundary = end == len(source) or source[end] not in terminators
        if starts_at_boundary and ends_at_boundary:
            return True
        offset = position + 1


def render_selected_description(candidate: PlayerCandidate, selection: Selection) -> str:
    if selection.action != "select":
        return ""
    if selection.excerpt not in candidate.record.source:
        raise ValueError(f"{candidate.record.key}: excerpt is not in source")
    if not is_complete_source_excerpt(candidate.record.source, selection.excerpt):
        raise ValueError(f"{candidate.record.key}: excerpt is not a complete source sentence")
    # 固定overrideは選択された出典抜粋にない事実を足しうるため、この経路では
    # 明示的に無効化し、抜粋の決定論的な整形だけを許す。
    # Wikipediaの記事名末尾にある曖昧さ回避用の括弧は本文中の人物名ではない。
    # 出典台帳にはcanonical titleを残し、主語除去に使う名前からだけ外す。
    subject_name = re.sub(
        r"\s*[（(][^()（）]+[）)]$",
        "",
        candidate.title,
    ).strip()
    description = make_player_description(
        selection.excerpt,
        subject_name,
        allow_override=False,
    )
    if (
        is_missing_description(description)
        or not is_standalone_player_description(description)
        or has_redundant_player_subject(description)
        or is_likely_disambiguation_text(description)
        or any(char in description for char in ('"', ",", "\r", "\n"))
    ):
        raise ValueError(f"{candidate.record.key}: selected excerpt is not a valid description")
    return description


def provenance_record(
    candidate: PlayerCandidate,
    selection: Selection,
    description: str,
) -> dict:
    revision = str(candidate.record.revision)
    encoded_title = quote(candidate.title.replace(" ", "_"), safe="")
    return {
        "kind": candidate.kind,
        "id": candidate.group_id,
        "qid": candidate.qid,
        "title": candidate.title,
        "page_url": (
            "https://ja.wikipedia.org/w/index.php?title="
            f"{encoded_title}&oldid={revision}"
        ),
        "revision_id": int(revision),
        "source_excerpt": selection.excerpt,
        "description": description,
        "model": DEFAULT_MODEL,
        "prompt_version": PROMPT_VERSION,
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "modified": description != selection.excerpt,
    }


def process_kind(
    kind: str,
    *,
    mode: str,
    selector: SourceSelector | None,
    changed_from: str | None,
    include_missing: bool,
    include_degraded: bool,
    limit: int,
    start_after: str | None,
    cache_only: bool,
    source_cache: dict[str, dict[str, str]] | None = None,
    fetcher: Callable[[list[str], dict[str, dict[str, str]]], None] = refresh_intros,
    verified: dict[str, dict[str, str]] | None = None,
    provenance_path: Path = PROVENANCE_PATH,
    pending_path: Path = PENDING_PATH,
) -> tuple[int, int]:
    path = Path(CONFIG[kind]["path"])
    columns, rows = read_rows(path)
    groups = group_rows(rows)
    previous_rows = rows_from_git(changed_from, path) if changed_from else None
    pending_records = load_pending(pending_path)
    pending_attempts = {
        group_id: int(record["attempts"])
        for (pending_kind, group_id), record in pending_records.items()
        if pending_kind == kind and group_id in groups
    }
    target_ids = target_group_ids(
        groups,
        previous_rows=previous_rows,
        include_missing=include_missing,
        include_degraded=include_degraded,
        limit=limit,
        start_after=start_after,
        pending_attempts=pending_attempts if changed_from else None,
    )
    if mode == "plan":
        print(f"{path.name}: LLM確認対象 {len(target_ids)}選手（未取得）")
        if len(target_ids) == limit and (include_missing or include_degraded):
            print(f"backlog cursor: --start-after {target_ids[-1]}")
        return len(target_ids), 0

    if selector is None:
        raise ValueError("selector is required for fetch/apply mode")

    source_cache = source_cache if source_cache is not None else load_cache()
    verified = verified if verified is not None else load_verified_sources(kind)
    titles = list(dict.fromkeys(
        title
        for group_id in target_ids
        for title in source_titles(kind, group_id, groups[group_id], verified)
    ))
    if mode == "fetch":
        # Fetch mode deliberately refreshes Wikipedia revisions.  It never
        # changes CSV/provenance/pending files.
        fetcher(titles, source_cache)
    else:
        # --cache-only means the complete source snapshot is offline too, not
        # merely that the OpenAI endpoint is disabled.
        require_cached_sources(titles, source_cache)
    candidates = build_candidates(kind, groups, target_ids, source_cache, verified)
    selections = select_in_batches(selector, candidates, cache_only=cache_only)

    if mode == "fetch":
        print(
            f"{path.name}: 対象 {len(target_ids)}、本人確認済み出典 "
            f"{len(candidates)}、OpenAI結果をcacheへ保存（CSV変更なし）"
        )
        if len(target_ids) == limit and (include_missing or include_degraded):
            print(f"backlog cursor: --start-after {target_ids[-1]}")
        return len(candidates), 0

    updated = 0
    original_provenance = load_provenance(provenance_path)
    provenance = dict(original_provenance)
    original_pending = dict(pending_records)
    pending = dict(pending_records)
    # Drop queue entries whose source rows no longer exist.
    for pending_key in list(pending):
        if pending_key[0] == kind and pending_key[1] not in groups:
            pending.pop(pending_key)

    by_group = {candidate.group_id: candidate for candidate in candidates}
    for group_id in target_ids:
        ledger_key = (kind, group_id)
        candidate = by_group.get(group_id)
        existing_source = provenance.get(ledger_key)
        source_is_current = bool(
            existing_source
            and description_state(groups[group_id])
            == (str(existing_source["description"]),)
        )
        # updater等が説明を別経路で変更したときだけ古い根拠を外す。現在値と一致する
        # 恒久版の根拠は、再確認時に候補が得られなくても失わない。
        if not source_is_current:
            provenance.pop(ledger_key, None)
        if candidate is None:
            if source_is_current:
                pending.pop(ledger_key, None)
                continue
            previous_attempts = int(pending.get(ledger_key, {}).get("attempts", 0))
            pending[ledger_key] = {
                "kind": kind,
                "id": group_id,
                "attempts": previous_attempts + 1,
                "reason": "source_unverified",
            }
            continue

        selection = selections[candidate.record.key]
        if selection.action != "select":
            if source_is_current or (
                selection.action == "keep"
                and not any(
                    is_degraded_description(row.get("description", ""))
                    for row in groups[group_id]
                )
            ):
                pending.pop(ledger_key, None)
                continue
            previous_attempts = int(pending.get(ledger_key, {}).get("attempts", 0))
            pending[ledger_key] = {
                "kind": kind,
                "id": group_id,
                "attempts": previous_attempts + 1,
                "reason": (
                    selection.reason_code
                    if selection.action == "abstain"
                    else "no_supported_excerpt"
                ),
            }
            continue

        description = render_selected_description(candidate, selection)
        changed = False
        for row in groups[group_id]:
            if row.get("description", "") != description:
                row["description"] = description
                changed = True
        updated += bool(changed)
        provenance[ledger_key] = provenance_record(candidate, selection, description)
        pending.pop(ledger_key, None)

    contents: dict[Path, bytes] = {}
    if updated:
        contents[path] = csv_bytes(columns, rows)
    if provenance != original_provenance:
        contents[provenance_path] = jsonl_bytes(provenance.values())
    if pending != original_pending:
        contents[pending_path] = jsonl_bytes(pending.values())
    if contents:
        atomic_write_bundle(contents)
    print(
        f"{path.name}: cache済み {len(candidates)}選手中 {updated}選手のdescriptionを更新"
    )
    if len(target_ids) == limit and (include_missing or include_degraded):
        print(f"backlog cursor: --start-after {target_ids[-1]}")
    return len(candidates), updated


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=(*CONFIG, "all"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fetch", action="store_true", help="OpenAI結果をcacheへ保存する")
    mode.add_argument("--apply", action="store_true", help="cache済み結果をCSVへ適用する")
    parser.add_argument("--cache-only", action="store_true", help="OpenAI networkを禁止する")
    parser.add_argument("--changed-from", metavar="GIT_REF")
    parser.add_argument("--include-missing", action="store_true")
    parser.add_argument(
        "--include-degraded",
        action="store_true",
        help="欠損に加えて構造不良と確定できる既存説明も対象にする",
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--start-after",
        metavar="ID",
        help="backlogを直前に表示されたIDの次から再開する",
    )
    parser.add_argument(
        "--daily-token-budget",
        type=int,
        default=MAX_DAILY_TOKEN_BUDGET,
        help=f"日次内部上限（最大{MAX_DAILY_TOKEN_BUDGET}）",
    )
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be positive")
    if not args.changed_from and not args.include_missing and not args.include_degraded:
        parser.error(
            "one of --changed-from, --include-missing or --include-degraded is required"
        )
    if args.fetch and args.cache_only:
        parser.error("--fetch cannot be combined with --cache-only")
    if args.apply and not args.cache_only:
        parser.error("--apply requires --cache-only")
    if args.start_after and args.changed_from:
        parser.error("--start-after cannot be combined with --changed-from")
    if not 1 <= args.daily_token_budget <= MAX_DAILY_TOKEN_BUDGET:
        parser.error(
            f"--daily-token-budget must be between 1 and {MAX_DAILY_TOKEN_BUDGET}"
        )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    mode = "fetch" if args.fetch else "apply" if args.apply else "plan"
    selector = None
    if mode != "plan":
        selector = SourceSelector(
            api_key=os.environ.get("OPENAI_API_KEY"),
            db_path=SELECTOR_DB_PATH,
            daily_token_budget=args.daily_token_budget,
            attestation=os.environ.get(
                "OPENAI_DATA_SHARING_INCENTIVE_CONFIRMED_UNTIL"
            ),
        )
    kinds = tuple(CONFIG) if args.kind == "all" else (args.kind,)
    snapshots: dict[Path, bytes | None] = {}
    if mode == "apply":
        snapshot_paths = {
            *(Path(CONFIG[kind]["path"]) for kind in kinds),
            PROVENANCE_PATH,
            PENDING_PATH,
        }
        snapshots = {
            path: path.read_bytes() if path.exists() else None
            for path in snapshot_paths
        }
    try:
        for kind in kinds:
            process_kind(
                kind,
                mode=mode,
                selector=selector,
                changed_from=args.changed_from,
                include_missing=args.include_missing,
                include_degraded=args.include_degraded,
                limit=args.limit,
                start_after=args.start_after,
                cache_only=args.cache_only,
            )
    except CacheMissError as exc:
        if snapshots:
            restore_snapshots(snapshots)
        print(
            "error: OpenAI cacheが不足しています: " + ", ".join(exc.keys),
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        if snapshots:
            restore_snapshots(snapshots)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
