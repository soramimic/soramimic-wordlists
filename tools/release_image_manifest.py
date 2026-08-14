#!/usr/bin/env python3
"""Publish and verify the GitHub Release image source manifest.

The Release marker is the commit marker: image assets are uploaded and verified first,
and ``source-manifest.json`` is uploaded to the marker release last.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "assets" / "release-image-source-manifest-v1.json"
SCHEMA_PATH = ROOT / "assets" / "release-image-source-manifest-v1.schema.json"
REPOSITORY = "soramimic/soramimic-wordlists"
MARKER_TAG = "release-image-source-manifest-v1"
MARKER_NAME = "source-manifest.json"
SCHEMA_ID = "https://github.com/soramimic/soramimic-wordlists/blob/main/assets/release-image-source-manifest-v1.schema.json"
SCHEMA_NAME = "soramimic.release-image-source-manifest"
URL_PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(RuntimeError):
    pass


def now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_url(tag: str, name: str, repository: str = REPOSITORY) -> str:
    return f"https://github.com/{repository}/releases/download/{tag}/{name}"


def split_release_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    prefix = f"/{REPOSITORY}/releases/download/"
    if parsed.scheme != "https" or parsed.netloc != "github.com" or not parsed.path.startswith(prefix):
        raise ManifestError(f"not a canonical {REPOSITORY} Release URL: {url}")
    tail = parsed.path[len(prefix):].split("/", 1)
    if len(tail) != 2 or not all(tail):
        raise ManifestError(f"invalid Release URL: {url}")
    return unquote(tail[0]), unquote(tail[1])


def referenced_release_urls(root: Path = ROOT) -> set[str]:
    urls: set[str] = set()
    for path in sorted(root.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                for value in row.values():
                    if isinstance(value, str) and value.startswith(URL_PREFIX):
                        url = value.strip()
                        tag, name = split_release_url(url)
                        if (tag, name) != (MARKER_TAG, MARKER_NAME):
                            urls.add(url)
    return urls


class GitHub:
    def __init__(self, repository: str = REPOSITORY):
        self.repository = repository

    def _run(self, args: list[str]) -> str:
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode:
            raise ManifestError(f"command failed: {' '.join(args)}\n{result.stderr.strip()}")
        return result.stdout

    def release_assets(self, tag: str) -> dict[str, dict]:
        release = json.loads(self._run(["gh", "api", f"repos/{self.repository}/releases/tags/{tag}"]))
        pages = json.loads(self._run([
            "gh", "api", "--paginate", "--slurp",
            f"repos/{self.repository}/releases/{release['id']}/assets?per_page=100",
        ]))
        assets: dict[str, dict] = {}
        for page in pages:
            for asset in page:
                digest = asset.get("digest") or ""
                if not digest.startswith("sha256:") or not SHA256_RE.fullmatch(digest[7:]):
                    raise ManifestError(f"GitHub API returned no usable sha256 for {tag}/{asset.get('name')}")
                assets[asset["name"]] = {
                    "url": asset["browser_download_url"],
                    "sha256": digest[7:],
                    "size": asset["size"],
                    "updated_at": asset["updated_at"],
                }
        return assets

    def upload(self, tag: str, files: Iterable[Path]) -> None:
        paths = [str(path) for path in files]
        if paths:
            self._run(["gh", "release", "upload", tag, *paths, "--clobber"])


def empty_manifest(generated_at: str | None = None) -> dict:
    return {
        "$schema": SCHEMA_ID,
        "schema": SCHEMA_NAME,
        "version": 1,
        "revision": 1,
        "generated_at": generated_at or now_rfc3339(),
        "repository": REPOSITORY,
        "assets": {},
    }


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict) -> None:
    if (manifest.get("schema") != SCHEMA_NAME or manifest.get("version") != 1
            or manifest.get("repository") != REPOSITORY):
        raise ManifestError("unsupported manifest version or repository")
    if not isinstance(manifest.get("revision"), int) or manifest["revision"] < 1:
        raise ManifestError("manifest revision must be a positive integer")
    assets = manifest.get("assets")
    if not isinstance(assets, dict):
        raise ManifestError("manifest assets must be an object keyed by URL")
    for url, entry in assets.items():
        split_release_url(url)
        if not isinstance(entry, dict):
            raise ManifestError(f"invalid entry for {url}")
        if not isinstance(entry.get("revision"), int) or entry["revision"] < 1:
            raise ManifestError(f"invalid revision for {url}")
        if not SHA256_RE.fullmatch(entry.get("sha256", "")):
            raise ManifestError(f"invalid sha256 for {url}")
        if not isinstance(entry.get("size"), int) or entry["size"] < 0:
            raise ManifestError(f"invalid size for {url}")
        try:
            datetime.fromisoformat(entry["updated_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestError(f"invalid updated_at for {url}") from exc
        if "note" in entry and not isinstance(entry["note"], str):
            raise ManifestError(f"invalid note for {url}")


def manifest_bytes(manifest: dict) -> bytes:
    validate_manifest(manifest)
    return (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def bootstrap(github: GitHub, urls: set[str], generated_at: str | None = None) -> dict:
    by_tag: dict[str, set[str]] = {}
    for url in urls:
        tag, name = split_release_url(url)
        by_tag.setdefault(tag, set()).add(name)
    manifest = empty_manifest(generated_at)
    for tag in sorted(by_tag):
        remote = github.release_assets(tag)
        for name in sorted(by_tag[tag]):
            asset = remote.get(name)
            if asset is None:
                raise ManifestError(f"referenced Release asset is missing: {tag}/{name}")
            url = canonical_url(tag, name)
            if asset["url"] != url:
                raise ManifestError(f"non-canonical browser_download_url for {tag}/{name}: {asset['url']}")
            manifest["assets"][url] = {
                "revision": 1,
                "updated_at": asset["updated_at"],
                "sha256": asset["sha256"],
                "size": asset["size"],
            }
    return manifest


def verify(github: GitHub, manifest: dict, referenced_urls: set[str], *,
           check_marker: bool = True) -> list[str]:
    errors: list[str] = []
    manifest_urls = set(manifest["assets"])
    for url in sorted(referenced_urls - manifest_urls):
        errors.append(f"referenced URL absent from manifest: {url}")
    # Removal is explicit reference removal. Retained unreferenced entries are allowed so
    # downstream consumers can unreference them separately from eventual blob GC.
    by_tag: dict[str, list[tuple[str, str]]] = {}
    for url in manifest_urls:
        tag, name = split_release_url(url)
        by_tag.setdefault(tag, []).append((name, url))
    for tag in sorted(by_tag):
        remote = github.release_assets(tag)
        for name, url in by_tag[tag]:
            actual = remote.get(name)
            expected = manifest["assets"][url]
            if actual is None:
                errors.append(f"manifest asset missing from Release: {url}")
            elif actual["url"] != url:
                errors.append(f"browser_download_url mismatch: {url} != {actual['url']}")
            elif actual["sha256"] != expected["sha256"] or actual["size"] != expected["size"]:
                errors.append(f"digest/size mismatch: {url}")
    if check_marker:
        payload = manifest_bytes(manifest)
        marker = github.release_assets(MARKER_TAG).get(MARKER_NAME)
        marker_digest = hashlib.sha256(payload).hexdigest()
        if marker is None:
            errors.append("published source manifest marker is missing")
        elif marker["sha256"] != marker_digest or marker["size"] != len(payload):
            errors.append("published source manifest marker differs from tracked manifest")
    return errors


def publish_current_marker(github: GitHub, manifest: dict,
                           referenced_urls: set[str]) -> None:
    """Initial publication/recovery of the tracked marker after full verification."""
    errors = verify(github, manifest, referenced_urls, check_marker=False)
    if errors:
        raise ManifestError("source verification failed; marker not published:\n" +
                            "\n".join(errors))
    payload = manifest_bytes(manifest)
    with tempfile.TemporaryDirectory() as directory:
        marker = Path(directory) / MARKER_NAME
        marker.write_bytes(payload)
        github.upload(MARKER_TAG, [marker])
        published = github.release_assets(MARKER_TAG).get(MARKER_NAME)
        if (published is None
                or published["sha256"] != hashlib.sha256(payload).hexdigest()
                or published["size"] != len(payload)):
            raise ManifestError("published source manifest marker failed verification")


def publish(github: GitHub, groups: Mapping[str, list[Path]], *, note: str | None = None,
            force: bool = False, dry_run: bool = False,
            manifest_path: Path = MANIFEST_PATH) -> tuple[dict, int]:
    """Upload all groups, verify them, then publish one new manifest marker.

    Returns the resulting manifest and number of image files uploaded. No marker is
    uploaded if any upload or verification raises.
    """
    old = load_manifest(manifest_path)
    local: dict[str, tuple[Path, str, int]] = {}
    for tag, paths in groups.items():
        for path in paths:
            if not path.is_file():
                raise ManifestError(f"not a file: {path}")
            url = canonical_url(tag, path.name)
            if url in local:
                raise ManifestError(f"duplicate target URL: {url}")
            local[url] = (path, sha256_file(path), path.stat().st_size)
    changed = {
        url: values for url, values in local.items()
        if force or old["assets"].get(url, {}).get("sha256") != values[1]
    }
    if dry_run:
        return old, len(changed)
    uploads_by_tag: dict[str, list[Path]] = {}
    for url, (path, _, _) in changed.items():
        tag, _ = split_release_url(url)
        uploads_by_tag.setdefault(tag, []).append(path)
    for tag in sorted(uploads_by_tag):
        github.upload(tag, uploads_by_tag[tag])
    remote_by_tag = {tag: github.release_assets(tag) for tag in sorted(groups)}
    result = json.loads(json.dumps(old))
    content_changed = False
    for url, (path, digest, size) in local.items():
        tag, name = split_release_url(url)
        actual = remote_by_tag[tag].get(name)
        if actual is None or actual["url"] != url:
            raise ManifestError(f"uploaded asset missing or has non-canonical URL: {url}")
        if actual["sha256"] != digest or actual["size"] != size:
            raise ManifestError(f"uploaded asset failed digest/size verification: {url}")
        previous = old["assets"].get(url)
        if previous is None or previous["sha256"] != digest:
            entry = {
                "revision": 1 if previous is None else previous["revision"] + 1,
                "updated_at": actual["updated_at"],
                "sha256": digest,
                "size": size,
            }
            if note:
                entry["note"] = note
            result["assets"][url] = entry
            content_changed = True
    if not content_changed:
        return old, len(changed)
    result["revision"] = old["revision"] + 1
    result["generated_at"] = now_rfc3339()
    payload = manifest_bytes(result)
    # The marker is deliberately last. A temporary directory guarantees its asset name.
    with tempfile.TemporaryDirectory() as directory:
        marker = Path(directory) / MARKER_NAME
        marker.write_bytes(payload)
        github.upload(MARKER_TAG, [marker])
        published = github.release_assets(MARKER_TAG).get(MARKER_NAME)
        if published is None or published["sha256"] != hashlib.sha256(payload).hexdigest() or published["size"] != len(payload):
            raise ManifestError("published source manifest marker failed verification")
    # Keep the tracked manifest at last-good if publishing the marker fails. If marker
    # verification itself fails after upload, retrying starts from the old local state and
    # safely republishes the same image metadata and marker.
    atomic_write(manifest_path, payload)
    return result, len(changed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    boot = sub.add_parser("bootstrap", help="build the initial manifest from top-level CSV URLs")
    boot.add_argument("--dry-run", action="store_true")
    check = sub.add_parser("verify", help="compare manifest, CSV references, and Release API metadata")
    sub.add_parser("publish-marker", help="verify all sources, then publish the tracked marker")
    pub = sub.add_parser("publish", aliases=["update"], help="upload TAG files, then publish the marker last")
    pub.add_argument("tag", metavar="TAG")
    pub.add_argument("files", metavar="FILE", nargs="+")
    pub.add_argument("--note")
    pub.add_argument("--force", action="store_true")
    pub.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    github = GitHub()
    try:
        if args.command == "bootstrap":
            manifest = bootstrap(github, referenced_release_urls())
            if args.dry_run:
                print(f"would write {len(manifest['assets'])} assets to {args.manifest}")
            else:
                atomic_write(args.manifest, manifest_bytes(manifest))
                print(f"wrote {len(manifest['assets'])} assets to {args.manifest}")
        elif args.command == "verify":
            errors = verify(github, load_manifest(args.manifest), referenced_release_urls())
            if errors:
                print("\n".join(f"error: {error}" for error in errors), file=sys.stderr)
                return 1
            print("source manifest matches CSV references and GitHub Releases")
        elif args.command == "publish-marker":
            manifest = load_manifest(args.manifest)
            publish_current_marker(github, manifest, referenced_release_urls())
            print("published verified source manifest marker")
        else:
            _, count = publish(github, {args.tag: [Path(p) for p in args.files]},
                               note=args.note, force=args.force, dry_run=args.dry_run,
                               manifest_path=args.manifest)
            print(f"{'would upload' if args.dry_run else 'uploaded'} {count} image asset(s)")
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
