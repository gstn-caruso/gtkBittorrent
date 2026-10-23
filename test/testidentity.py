#!/usr/bin/env python3

"""Check fork identity without opening a user's profile or starting torrent activity."""

import argparse
import os
import subprocess  # nosec B404 # Exercise the locally built application.
import sys
import tempfile
import unittest
from pathlib import Path

binary: Path


class TestIdentity(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("linux"), "Default XDG paths are a Linux-specific contract")
    def testDefaultAndNamedProfilesAreSeparate(self) -> None:
        for configuration in ("", "work"):
            with self.subTest(configuration=configuration), tempfile.TemporaryDirectory(prefix="gtkbt-xdg-") as directory:
                root = Path(directory)
                legacy = root / "config" / "qBittorrent" / "qBittorrent.conf"
                legacy.parent.mkdir(parents=True)
                original = b"[MigrationBaseline]\nSentinel=do-not-change\n"
                legacy.write_bytes(original)
                environment = {key: value for key, value in os.environ.items() if not key.startswith(("QBT_", "GTKB_"))}
                environment.update({"QT_QPA_PLATFORM": "offscreen", "XDG_CONFIG_HOME": str(root / "config"),
                                    "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache")})
                result = subprocess.run(  # nosec B603 # Explicit locally built binary without a shell.
                    [str(binary), "--version", f"--configuration={configuration}"], env=environment,
                    capture_output=True, timeout=20, check=True,
                )
                self.assertTrue(result.stdout.startswith(b"gtkBittorrent v"), result.stdout)
                profile = "gtkBittorrent" + ("_" + configuration if configuration else "")
                self.assertTrue((root / "config" / profile / "gtkBittorrent.conf").is_file())
                self.assertEqual(legacy.read_bytes(), original)

    def testCustomProfileDoesNotChangeQbittorrent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gtkbt-identity-") as directory:
            root = Path(directory)
            extension = ".ini" if sys.platform in ("win32", "darwin") else ".conf"
            legacy = root / "qBittorrent" / "config" / ("qBittorrent" + extension)
            legacy.parent.mkdir(parents=True)
            original = b"[MigrationBaseline]\nSentinel=do-not-change\n"
            legacy.write_bytes(original)
            environment = {key: value for key, value in os.environ.items() if not key.startswith(("QBT_", "GTKB_"))}
            environment["QT_QPA_PLATFORM"] = "offscreen"
            environment["GTKB_PROFILE"] = str(root)
            environment["QBT_PROFILE"] = str(root / "wrong-profile")
            result = subprocess.run(  # nosec B603 # Explicit locally built binary without a shell.
                [str(binary), "--version"], env=environment, capture_output=True, timeout=20, check=True,
            )
            self.assertTrue(result.stdout.startswith(b"gtkBittorrent v"), result.stdout)
            self.assertEqual(legacy.read_bytes(), original)
            self.assertTrue((root / "gtkBittorrent" / "config" / ("gtkBittorrent" + extension)).is_file())
            self.assertFalse((root / "wrong-profile").exists())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    arguments, remaining = parser.parse_known_args()
    binary = arguments.binary.resolve(strict=True)
    unittest.main(argv=[__file__, *remaining])
