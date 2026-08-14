import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import tools.release_image_manifest as rim


class FakeGitHub:
    def __init__(self, releases=None, fail_upload_tag=None):
        self.releases = releases or {}
        self.fail_upload_tag = fail_upload_tag
        self.events = []

    def release_assets(self, tag):
        self.events.append(("query", tag))
        return {name: dict(value) for name, value in self.releases.get(tag, {}).items()}

    def upload(self, tag, files):
        self.events.append(("upload", tag, [path.name for path in files]))
        if tag == self.fail_upload_tag:
            raise rim.ManifestError("injected upload failure")
        bucket = self.releases.setdefault(tag, {})
        for path in files:
            content = path.read_bytes()
            bucket[path.name] = {
                "url": rim.canonical_url(tag, path.name),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
                "updated_at": "2026-08-15T00:00:00Z",
            }


def entry(content=b"old", revision=1):
    return {
        "revision": revision,
        "updated_at": "2026-08-14T00:00:00Z",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }


class ReleaseImageManifestTests(unittest.TestCase):
    def write_manifest(self, directory, assets):
        path = Path(directory) / "manifest.json"
        manifest = rim.empty_manifest("2026-08-14T00:00:00Z")
        manifest["assets"] = assets
        path.write_bytes(rim.manifest_bytes(manifest))
        return path

    def test_bootstrap_uses_api_digest_and_canonical_url(self):
        url = rim.canonical_url("images-v1", "one.png")
        remote = {"one.png": {"url": url, "sha256": "a" * 64, "size": 12,
                              "updated_at": "2026-08-15T00:00:00Z"}}
        manifest = rim.bootstrap(FakeGitHub({"images-v1": remote}), {url},
                                 "2026-08-15T00:00:00Z")
        self.assertEqual(manifest["assets"][url]["sha256"], "a" * 64)
        self.assertEqual(manifest["assets"][url]["revision"], 1)

    def test_publish_changes_entry_and_uploads_marker_last(self):
        with tempfile.TemporaryDirectory() as directory:
            url = rim.canonical_url("images-v1", "one.png")
            manifest_path = self.write_manifest(directory, {url: entry()})
            image = Path(directory) / "one.png"
            image.write_bytes(b"new")
            github = FakeGitHub()
            result, uploaded = rim.publish(github, {"images-v1": [image]},
                                           note="replacement", manifest_path=manifest_path)
            self.assertEqual(uploaded, 1)
            self.assertEqual(result["assets"][url]["revision"], 2)
            self.assertEqual(result["assets"][url]["note"], "replacement")
            uploads = [event for event in github.events if event[0] == "upload"]
            self.assertEqual(uploads[-1][1:], (rim.MARKER_TAG, [rim.MARKER_NAME]))

    def test_same_content_is_idempotent_without_upload_or_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            url = rim.canonical_url("images-v1", "one.png")
            manifest_path = self.write_manifest(directory, {url: entry()})
            image = Path(directory) / "one.png"
            image.write_bytes(b"old")
            remote = {"one.png": {"url": url, "sha256": hashlib.sha256(b"old").hexdigest(),
                                  "size": 3, "updated_at": "2026-08-14T00:00:00Z"}}
            github = FakeGitHub({"images-v1": remote})
            before = manifest_path.read_bytes()
            _, uploaded = rim.publish(github, {"images-v1": [image]}, manifest_path=manifest_path)
            self.assertEqual(uploaded, 0)
            self.assertEqual(before, manifest_path.read_bytes())
            self.assertFalse(any(event[0] == "upload" for event in github.events))

    def test_image_failure_never_publishes_marker_and_keeps_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            url = rim.canonical_url("images-v1", "one.png")
            manifest_path = self.write_manifest(directory, {url: entry()})
            image = Path(directory) / "one.png"
            image.write_bytes(b"new")
            before = manifest_path.read_bytes()
            github = FakeGitHub(fail_upload_tag="images-v1")
            with self.assertRaises(rim.ManifestError):
                rim.publish(github, {"images-v1": [image]}, manifest_path=manifest_path)
            self.assertEqual(before, manifest_path.read_bytes())
            self.assertNotIn(("upload", rim.MARKER_TAG, [rim.MARKER_NAME]), github.events)

    def test_marker_failure_keeps_local_old_and_retry_publishes(self):
        with tempfile.TemporaryDirectory() as directory:
            url = rim.canonical_url("images-v1", "one.png")
            manifest_path = self.write_manifest(directory, {url: entry()})
            image = Path(directory) / "one.png"
            image.write_bytes(b"new")
            before = manifest_path.read_bytes()
            github = FakeGitHub(fail_upload_tag=rim.MARKER_TAG)
            with self.assertRaises(rim.ManifestError):
                rim.publish(github, {"images-v1": [image]}, manifest_path=manifest_path)
            self.assertEqual(before, manifest_path.read_bytes())
            github.fail_upload_tag = None
            result, _ = rim.publish(github, {"images-v1": [image]}, manifest_path=manifest_path)
            self.assertEqual(result["assets"][url]["revision"], 2)
            self.assertEqual(json.loads(manifest_path.read_text())["assets"][url]["revision"], 2)

    def test_verify_detects_release_drift_and_missing_reference(self):
        url = rim.canonical_url("images-v1", "one.png")
        other = rim.canonical_url("images-v1", "two.png")
        manifest = rim.empty_manifest("2026-08-14T00:00:00Z")
        manifest["assets"] = {url: entry()}
        remote = {"one.png": {"url": url, "sha256": "f" * 64, "size": 3,
                              "updated_at": "2026-08-15T00:00:00Z"}}
        payload = rim.manifest_bytes(manifest)
        marker = {rim.MARKER_NAME: {
            "url": rim.canonical_url(rim.MARKER_TAG, rim.MARKER_NAME),
            "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload),
            "updated_at": "2026-08-15T00:00:00Z",
        }}
        errors = rim.verify(FakeGitHub({"images-v1": remote, rim.MARKER_TAG: marker}),
                            manifest, {url, other})
        self.assertTrue(any("absent from manifest" in error for error in errors))
        self.assertTrue(any("digest/size mismatch" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
