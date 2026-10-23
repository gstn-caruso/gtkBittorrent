"""Protect immutable release assets and retries without contacting GitHub."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from dist.release.publish import Asset, Release, publishRelease

COMMIT = "a" * 40


class FakeGitHub:
    def __init__(self) -> None:
        self.release: Release | None = None
        self.tag: str | None = None
        self.creates = 0
        self.uploads: list[str] = []
        self.publishes = 0
        self.failUpload = False
        self.corruptUpload = False

    def ensureTag(self, tag: str, commit: str) -> None:
        if self.tag is not None and self.tag != commit:
            raise RuntimeError("Tag points to another commit")
        self.tag = commit

    def findRelease(self, tag: str) -> Release | None:
        return self.release

    def createDraft(self, tag: str, commit: str, body: str) -> Release:
        self.creates += 1
        self.release = Release(1, tag, True, True, {})
        return self.release

    def upload(self, releaseId: int, path: Path) -> None:
        if self.failUpload and self.uploads:
            raise RuntimeError("Interrupted upload")
        self.uploads.append(path.name)
        if self.release is None:
            raise AssertionError("No draft")
        self.release.assets[path.name] = Asset(path.stat().st_size, "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())
        if self.corruptUpload:
            self.release.assets[path.name] = Asset(path.stat().st_size, "sha256:" + "0" * 64)

    def getRelease(self, releaseId: int) -> Release:
        if self.release is None:
            raise AssertionError("No draft")
        return self.release

    def publish(self, releaseId: int) -> None:
        if self.release is None:
            raise AssertionError("No draft")
        self.publishes += 1
        self.release.draft = False


class TestRelease(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="gtkbt-release-")
        self.addCleanup(self.directory.cleanup)
        self.artifacts = Path(self.directory.name)
        (self.artifacts / "gtkbittorrent.deb").write_bytes(b"synthetic package")
        self.manifest = self.artifacts / "build-info.json"
        self.manifest.write_text(json.dumps({"schema": 1, "source_commit": COMMIT, "dirty": False,
                                            "platform": "ubuntu-26.04", "architecture": "amd64", "requires_qt": True}), encoding="utf-8")
        self.writeChecksums()
        self.api = FakeGitHub()

    def writeChecksums(self) -> None:
        lines = [hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
                 for path in sorted(self.artifacts.iterdir()) if path.name != "SHA256SUMS"]
        (self.artifacts / "SHA256SUMS").write_text("".join(lines), encoding="utf-8")

    def testPublishVerifiedArtifactsAsPrerelease(self) -> None:
        self.assertTrue(publishRelease(self.api, self.artifacts, COMMIT))
        self.assertEqual(self.api.tag, COMMIT)
        self.assertEqual(self.api.creates, 1)
        self.assertEqual(set(self.api.uploads), {"gtkbittorrent.deb", "build-info.json", "SHA256SUMS"})
        self.assertEqual(self.api.publishes, 1)
        self.assertIsNotNone(self.api.release)
        if self.api.release is not None:
            self.assertFalse(self.api.release.draft)
            self.assertTrue(self.api.release.prerelease)

    def testRetryPublishedReleaseWithoutChangingAssets(self) -> None:
        publishRelease(self.api, self.artifacts, COMMIT)
        self.assertFalse(publishRelease(self.api, self.artifacts, COMMIT))
        self.assertEqual(self.api.creates, 1)
        self.assertEqual(len(self.api.uploads), 3)
        self.assertEqual(self.api.publishes, 1)

    def testResumeInterruptedDraftWithoutDuplicateAssets(self) -> None:
        self.api.failUpload = True
        with self.assertRaisesRegex(RuntimeError, "Interrupted upload"):
            publishRelease(self.api, self.artifacts, COMMIT)
        self.assertEqual(self.api.publishes, 0)
        self.api.failUpload = False
        self.assertTrue(publishRelease(self.api, self.artifacts, COMMIT))
        self.assertEqual(self.api.creates, 1)
        self.assertEqual(len(self.api.uploads), 3)

    def testRejectTamperedLocalPackageBeforeCreatingTag(self) -> None:
        (self.artifacts / "gtkbittorrent.deb").write_bytes(b"changed package")
        with self.assertRaisesRegex(ValueError, "checksum"):
            publishRelease(self.api, self.artifacts, COMMIT)
        self.assertIsNone(self.api.tag)
        self.assertEqual(self.api.creates, 0)

    def testRejectWrongSourceCommit(self) -> None:
        with self.assertRaisesRegex(ValueError, "commit"):
            publishRelease(self.api, self.artifacts, "b" * 40)
        self.assertIsNone(self.api.tag)

    def testRefuseTagCollision(self) -> None:
        self.api.tag = "b" * 40
        with self.assertRaisesRegex(RuntimeError, "another commit"):
            publishRelease(self.api, self.artifacts, COMMIT)
        self.assertEqual(self.api.creates, 0)

    def testRefuseReplacingPublishedAsset(self) -> None:
        publishRelease(self.api, self.artifacts, COMMIT)
        if self.api.release is None:
            self.fail("No release")
        self.api.release.assets["gtkbittorrent.deb"] = Asset(123, "sha256:" + "0" * 64)
        with self.assertRaisesRegex(ValueError, "different"):
            publishRelease(self.api, self.artifacts, COMMIT)
        self.assertEqual(len(self.api.uploads), 3)
        self.assertEqual(self.api.publishes, 1)

    def testRejectDirtySourceManifest(self) -> None:
        metadata = json.loads(self.manifest.read_text(encoding="utf-8"))
        metadata["dirty"] = True
        self.manifest.write_text(json.dumps(metadata), encoding="utf-8")
        self.writeChecksums()
        with self.assertRaisesRegex(ValueError, "dirty"):
            publishRelease(self.api, self.artifacts, COMMIT)
        self.assertIsNone(self.api.tag)

    def testDoNotPublishUntilRemoteDigestsMatch(self) -> None:
        self.api.corruptUpload = True
        with self.assertRaisesRegex(ValueError, "different"):
            publishRelease(self.api, self.artifacts, COMMIT)
        self.assertEqual(self.api.publishes, 0)
        self.assertIsNotNone(self.api.release)
        if self.api.release is not None:
            self.assertTrue(self.api.release.draft)


if __name__ == "__main__":
    unittest.main()
