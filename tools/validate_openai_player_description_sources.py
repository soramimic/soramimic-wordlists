#!/usr/bin/env python3
"""Validate current OpenAI-assisted player descriptions and their source ledger."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_player_descriptions_openai as target  # noqa: E402
from openai_source_selector import Selection, SourceRecord  # noqa: E402


QID = re.compile(r"Q[1-9][0-9]*")


def validate() -> None:
    provenance = target.load_provenance()
    pending = target.load_pending()

    for path, records in (
        (target.PROVENANCE_PATH, provenance.values()),
        (target.PENDING_PATH, pending.values()),
    ):
        if path.exists() and path.read_bytes() != target.jsonl_bytes(records):
            raise ValueError(f"{path.name} is not in deterministic key order")

    groups_by_kind: dict[str, dict[str, list[dict[str, str]]]] = {}
    verified_by_kind = {
        kind: target.load_verified_sources(kind) for kind in target.CONFIG
    }
    colliding_baseball_ids: set[str] = set()
    for kind, config in target.CONFIG.items():
        _, rows = target.read_rows(Path(config["path"]))
        groups = target.group_rows(rows)
        groups_by_kind[kind] = groups
        if kind == "baseball":
            ids_by_identity: dict[tuple[str, str], set[str]] = {}
            for group_id, group_rows in groups.items():
                for identity in target.full_identity_keys(group_rows):
                    ids_by_identity.setdefault(identity, set()).add(group_id)
            colliding_baseball_ids = {
                group_id
                for ids in ids_by_identity.values()
                if len(ids) > 1
                for group_id in ids
            }

    for group_id, identity in verified_by_kind.get("baseball", {}).items():
        groups = groups_by_kind.get("baseball", {})
        if group_id not in groups:
            raise ValueError(f"baseball identity references a missing group: {group_id}")
        article = str(identity.get("article", ""))
        qid = str(identity.get("qid", ""))
        if not QID.fullmatch(qid) or not identity.get("method"):
            raise ValueError(f"baseball identity is incomplete: {group_id}")
        article_name = re.sub(r"\s+\([^)]*\)$", "", article)
        full_names = {
            target.vnorm(row.get("surface", "").replace(" ", "").replace("　", ""))
            for row in groups[group_id]
            if row.get("type") == "full"
        }
        if target.vnorm(article_name.replace(" ", "").replace("　", "")) not in full_names:
            raise ValueError(f"baseball identity title mismatch: {group_id}")

    for key, record in provenance.items():
        kind, group_id = key
        groups = groups_by_kind[kind]
        if group_id not in groups:
            raise ValueError(f"provenance references a missing group: {kind}:{group_id}")
        if kind == "baseball" and group_id in colliding_baseball_ids:
            raise ValueError(f"provenance identity is ambiguous: {kind}:{group_id}")
        qid = str(record["qid"])
        title = str(record["title"])
        revision = record["revision_id"]
        if not QID.fullmatch(qid):
            raise ValueError(f"invalid provenance QID: {kind}:{group_id}")
        if not title or isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError(f"invalid provenance article: {kind}:{group_id}")
        expected_record = target.provenance_record(
            target.PlayerCandidate(
                kind,
                group_id,
                title,
                SourceRecord(
                    key=f"{kind}:{group_id}",
                    title=title,
                    source=str(record["source_excerpt"]),
                    revision=revision,
                    draft="",
                ),
                qid,
            ),
            Selection(
                "select",
                str(record["source_excerpt"]),
                "source_excerpt_preferred",
            ),
            str(record["description"]),
        )
        if record != expected_record:
            raise ValueError(f"provenance fields do not reproduce: {kind}:{group_id}")

        candidate = target.PlayerCandidate(
            kind,
            group_id,
            title,
            SourceRecord(
                key=f"{kind}:{group_id}",
                title=title,
                source=str(record["source_excerpt"]),
                revision=revision,
                draft="",
            ),
            qid,
        )
        rendered = target.render_selected_description(
            candidate,
            Selection(
                "select",
                str(record["source_excerpt"]),
                "source_excerpt_preferred",
            ),
        )
        descriptions = target.description_state(groups[group_id])
        if rendered != record["description"] or descriptions != (rendered,):
            raise ValueError(f"provenance does not reproduce CSV: {kind}:{group_id}")

        if kind == "football":
            expected_qids = {
                row.get("wikidata", "")
                for row in groups[group_id]
                if row.get("wikidata")
            }
            verified_qid = str(
                verified_by_kind[kind].get(group_id, {}).get("qid", "")
            )
            if verified_qid:
                expected_qids.add(verified_qid)
            if expected_qids and expected_qids != {qid}:
                raise ValueError(f"provenance QID disagrees with identity: {kind}:{group_id}")
        else:
            identity = verified_by_kind[kind].get(group_id, {})
            if identity.get("article") != title or identity.get("qid") != qid:
                raise ValueError(f"provenance lacks verified identity: {kind}:{group_id}")

    overlap = provenance.keys() & pending.keys()
    if overlap:
        raise ValueError(f"resolved and pending ledgers overlap: {sorted(overlap)[:3]}")
    for kind, group_id in pending:
        if group_id not in groups_by_kind[kind]:
            raise ValueError(f"pending ledger references a missing group: {kind}:{group_id}")


def main() -> int:
    try:
        validate()
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("OK: OpenAI player description source and pending ledgers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
