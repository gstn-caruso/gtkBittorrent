"""Verify release provenance and real Debian package metadata locally."""

import hashlib
import json
import shutil
import subprocess  # nosec B404 # Invoke local build tools without a shell.
import tempfile
import unittest
from pathlib import Path

from dist.release.package import buildPackage, sourceInfo
from dist.release.publish import verifyArtifacts


def command(*arguments: str, cwd: Path) -> str:
    return subprocess.check_output(arguments, cwd=cwd, text=True).strip()  # nosec B603 # Fixed build tools and temporary test paths.


@unittest.skipUnless(shutil.which("git"), "Git is required for source provenance tests")
class TestPackageSource(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="gtkbt-package-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "src/base").mkdir(parents=True)
        (self.source / "src/base/version.h.in").write_text(
            '#define QBT_VERSION_MAJOR 5\n#define QBT_VERSION_MINOR 4\n'
            '#define QBT_VERSION_BUGFIX 0\n#define QBT_VERSION_BUILD 0\n#define QBT_VERSION_STATUS "alpha1"\n', encoding="utf-8")
        (self.source / "COPYING").write_text("Fixture license\n", encoding="utf-8")
        command("git", "init", "--quiet", cwd=self.source)
        command("git", "add", ".", cwd=self.source)
        command("git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
                "commit", "--quiet", "-m", "Fixture", cwd=self.source)
        self.commit = command("git", "rev-parse", "HEAD", cwd=self.source)

    def testRecordExactSourceCommitAndPrereleaseVersion(self) -> None:
        info = sourceInfo(self.source, self.commit)
        self.assertEqual(info.commit, self.commit)
        self.assertEqual(info.version, "5.4.0~alpha1+git." + self.commit)
        self.assertEqual(info.epoch, int(command("git", "show", "-s", "--format=%ct", "HEAD", cwd=self.source)))

    def testRefuseWrongCommit(self) -> None:
        with self.assertRaisesRegex(ValueError, "commit"):
            sourceInfo(self.source, "0" * 40)

    def testRefuseTrackedAndUntrackedChanges(self) -> None:
        for filename in ("COPYING", "untracked.txt"):
            with self.subTest(filename=filename):
                path = self.source / filename
                original = path.read_bytes() if path.exists() else None
                path.write_text("Changed\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "clean"):
                    sourceInfo(self.source, self.commit)
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)

    def testRequireDesktopEngineAndImporter(self) -> None:
        stage = self.root / "stage"
        stage.mkdir()
        with self.assertRaisesRegex(ValueError, "gtkbittorrent"):
            buildPackage(self.source, stage, self.root / "output", self.commit)
        self.assertFalse((self.root / "output").exists())

    @unittest.skipUnless(Path("/etc/os-release").exists() and 'VERSION_ID="26.04"' in Path("/etc/os-release").read_text(encoding="utf-8")
                         and shutil.which("dpkg-deb") and shutil.which("dpkg-shlibdeps"), "Ubuntu 26.04 packaging tools are required")
    def testBuildInstallablePackageWithVerifiedManifest(self) -> None:
        stage = self.root / "stage"
        binaries = stage / "usr/bin"
        binaries.mkdir(parents=True)
        for name in ("gtkbittorrent", "gtkbittorrent-engine", "gtkbittorrent-import"):
            shutil.copy2("/usr/bin/true", binaries / name)
        output = self.root / "output"
        package = buildPackage(self.source, stage, output, self.commit)
        self.assertNotIn("~", package.name)
        self.assertIn("5.4.0-alpha1+git.", package.name)
        fields = command("dpkg-deb", "--field", str(package), cwd=self.root)
        self.assertIn("Package: gtkbittorrent\n", fields)
        self.assertIn("Version: 5.4.0~alpha1+git." + self.commit, fields)
        self.assertIn("libc6", fields)
        self.assertIn("libqt6sql6-sqlite", fields)
        self.assertIn("qt6-qpa-plugins", fields)
        self.assertIn("libqt6core6t64 (= ", fields)
        metadata = json.loads((output / "build-info.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["source_commit"], self.commit)
        self.assertFalse(metadata["dirty"])
        self.assertTrue(metadata["requires_qt"])
        assets = verifyArtifacts(output, self.commit)
        self.assertEqual(assets[package.name].digest, "sha256:" + hashlib.sha256(package.read_bytes()).hexdigest())
        extracted = self.root / "extracted"
        command("dpkg-deb", "--extract", str(package), str(extracted), cwd=self.root)
        self.assertEqual((extracted / "usr/share/doc/gtkbittorrent/SOURCE_COMMIT").read_text(encoding="utf-8"), self.commit + "\n")
        self.assertEqual(json.loads((extracted / "usr/share/gtkbittorrent/build-info.json").read_text(encoding="utf-8")), metadata)
        self.assertEqual((extracted / "usr/bin/gtkbittorrent-import").read_bytes(), Path("/usr/bin/true").read_bytes())
        rebuilt = buildPackage(self.source, stage, self.root / "rebuilt", self.commit)
        self.assertEqual(package.read_bytes(), rebuilt.read_bytes())
        with self.assertRaisesRegex(ValueError, "exists"):
            buildPackage(self.source, stage, output, self.commit)


if __name__ == "__main__":
    unittest.main()
