#!/usr/bin/env python3

"""Exercise the installed release package in a clean runtime container."""

import argparse
import json
import os
import subprocess  # nosec B404 # Run installed programs and integration tests without a shell.
import sys
from pathlib import Path

from dist.release.publish import verifyArtifacts


def smoke(source: Path, artifacts: Path, commit: str) -> None:
    verifyArtifacts(artifacts, commit)
    installed = json.loads(Path("/usr/share/gtkbittorrent/build-info.json").read_text(encoding="utf-8"))
    if installed != json.loads((artifacts / "build-info.json").read_text(encoding="utf-8")):
        raise ValueError("Installed package has a different build manifest")
    linked = subprocess.check_output(["/usr/bin/ldd", "/usr/bin/gtkbittorrent-import"], text=True)  # nosec B603 # System ldd and fixed installed binary.
    if "libQt" in linked or "not found" in linked:
        raise ValueError("Importer must run without Qt or missing libraries")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    commands = [[sys.executable, "-B", str(source / "test/testprofileimport.py"), "--importer", "/usr/bin/gtkbittorrent-import", "-v"]]
    for binary in ("/usr/bin/gtkbittorrent-engine", "/usr/bin/gtkbittorrent"):
        commands.append([sys.executable, "-B", str(source / "test/testidentity.py"), "--binary", binary, "-v"])
        commands.append([sys.executable, "-B", str(source / "test/testsession.py"), "--binary", binary,
                         "--importer", "/usr/bin/gtkbittorrent-import", "-v"])
    for command in commands:
        subprocess.run(command, cwd=source, env=environment, check=True, timeout=240)  # nosec B603 # Fixed test paths and installed binaries.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    arguments = parser.parse_args()
    smoke(arguments.source.resolve(), arguments.artifacts.resolve(), arguments.commit)
