#!/usr/bin/env python3

"""Exercise profile import through the Qt-free command line tool."""

import argparse
import os
import subprocess  # nosec B404 # Exercise the locally built importer.
import sys
import tempfile
import unittest
from pathlib import Path

importer: Path


class TestProfileImport(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="gtkbt-profile-import-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "qBittorrent 日本語"
        self.target = self.root / "gtkBittorrent 日本語"
        (self.source / "config").mkdir(parents=True)
        (self.source / "data" / "BT_backup").mkdir(parents=True)
        self.settings = b"[BitTorrent]\nSession\\GlobalDLSpeedLimit=73\n"
        (self.source / "config" / "qBittorrent.conf").write_bytes(self.settings)
        (self.source / "data" / "BT_backup" / "fixture.fastresume").write_bytes(b"\x00resume\xff")

    def runImport(self, target: Path | None = None) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(  # nosec B603 # Explicit locally built binary without a shell.
            [str(importer), str(self.source), str(target or self.target)], capture_output=True, timeout=10, check=False,
        )

    def testCopyClosedProfileWithoutChangingSource(self) -> None:
        (self.source / "downloads" / "日本語").mkdir(parents=True)
        (self.source / "downloads" / "日本語" / "archivo.bin").write_bytes(bytes(range(256)))
        payload = self.source / "downloads" / "日本語" / "archivo.bin"
        os.utime(payload, ns=(1600000000000000000, 1600000000000000000))
        (self.source / "cache").mkdir()
        (self.source / "cache" / "sentinel").write_bytes(b"do not import")
        (self.source / "config" / "qBittorrent_new.conf").write_bytes(b"[Recovery]\nValue=latest\n")
        before = {str(path.relative_to(self.source)): path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        result = self.runImport()
        self.assertEqual(result.returncode, 0, result.stderr)
        extension = ".ini" if sys.platform in ("win32", "darwin") else ".conf"
        self.assertEqual((self.target / "config" / ("gtkBittorrent" + extension)).read_bytes(), self.settings)
        self.assertEqual((self.target / "config" / ("gtkBittorrent_new" + extension)).read_bytes(), b"[Recovery]\nValue=latest\n")
        self.assertFalse((self.target / "config" / "qBittorrent.conf").exists())
        self.assertFalse((self.target / "cache").exists())
        self.assertEqual((self.target / "data" / "BT_backup" / "fixture.fastresume").read_bytes(), b"\x00resume\xff")
        self.assertEqual((self.target / "downloads" / "日本語" / "archivo.bin").read_bytes(), bytes(range(256)))
        self.assertEqual((self.target / "downloads" / "日本語" / "archivo.bin").stat().st_mtime_ns, payload.stat().st_mtime_ns)
        self.assertEqual({str(path.relative_to(self.source)): path.read_bytes() for path in self.source.rglob("*") if path.is_file()}, before)
        if os.name == "posix":
            self.assertEqual(self.target.stat().st_mode & 0o777, 0o700)
        self.assertFalse(list(self.root.glob(".gtkBittorrent-import-*")))

    def testRefuseExistingTarget(self) -> None:
        self.target.mkdir()
        sentinel = self.target / "sentinel"
        sentinel.write_bytes(b"keep existing settings")
        result = self.runImport()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_bytes(), b"keep existing settings")
        self.assertEqual(list(self.target.iterdir()), [sentinel])

    def testRefuseActiveSource(self) -> None:
        (self.source / "config" / "lockfile").write_text("active or stale lock", encoding="utf-8")
        result = self.runImport()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"lockfile", result.stderr)
        self.assertFalse(self.target.exists())

    def testRefuseUnrecognizedSource(self) -> None:
        (self.source / "config" / "qBittorrent.conf").unlink()
        result = self.runImport()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.target.exists())

    def testRefuseTargetInsideSource(self) -> None:
        result = self.runImport(self.source / "nested")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.source / "nested").exists())

    @unittest.skipIf(os.name == "nt", "Symlink creation may require elevation on Windows")
    def testRefuseSymlinksWithoutLeavingPartialImport(self) -> None:
        outside = self.root / "outside"
        outside.write_bytes(b"keep outside data")
        (self.source / "data" / "link").symlink_to(outside)
        result = self.runImport()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob(".gtkBittorrent-import-*")))
        self.assertEqual(outside.read_bytes(), b"keep outside data")

    def testRefuseMixedSettingsFormats(self) -> None:
        (self.source / "config" / "qBittorrent.ini").write_bytes(b"[Other]\nValue=ambiguous\n")
        result = self.runImport()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.target.exists())

    def testConflictingForkSettingsLeaveNoPartialImport(self) -> None:
        extension = ".ini" if sys.platform in ("win32", "darwin") else ".conf"
        conflict = self.source / "config" / ("gtkBittorrent" + extension)
        conflict.write_bytes(b"do not replace these settings")
        result = self.runImport()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob(".gtkBittorrent-import-*")))
        self.assertEqual(conflict.read_bytes(), b"do not replace these settings")

    def testImportSeparateDefaultProfileDirectories(self) -> None:
        data = self.root / "separate data 日本語"
        (self.source / "data").rename(data)
        result = subprocess.run(  # nosec B603 # Explicit locally built importer without a shell.
            [str(importer), "--config", str(self.source / "config"), "--data", str(data), str(self.target)],
            capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / "data" / "BT_backup" / "fixture.fastresume").read_bytes(), b"\x00resume\xff")
        self.assertEqual((data / "BT_backup" / "fixture.fastresume").read_bytes(), b"\x00resume\xff")

    @unittest.skipUnless(os.name == "posix", "POSIX file permissions")
    def testImportReadOnlySourceAsWritableCopy(self) -> None:
        config = self.source / "config"
        settings = config / "qBittorrent.conf"
        settings.chmod(0o400)
        config.chmod(0o500)
        self.addCleanup(config.chmod, 0o700)
        result = self.runImport()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / "config" / "gtkBittorrent.conf").read_bytes(), self.settings)
        self.assertEqual(settings.stat().st_mode & 0o777, 0o400)
        self.assertTrue((self.target / "config" / "gtkBittorrent.conf").stat().st_mode & 0o200)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--importer", type=Path, required=True)
    arguments, remaining = parser.parse_known_args()
    importer = arguments.importer.resolve()
    unittest.main(argv=[__file__, *remaining])
