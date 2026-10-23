#!/usr/bin/env python3

"""Package a clean, staged Ubuntu build with its source and dependency record."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess  # nosec B404 # Build tools run without a shell.
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Source:
    commit: str
    version: str
    epoch: int


def run(command: list[str], directory: Path, environment: dict[str, str] | None = None) -> str:
    return subprocess.check_output(command, cwd=directory, env=environment, text=True).strip()  # nosec B603 # Local build tools with explicit arguments.


def sourceInfo(source: Path, commit: str) -> Source:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None or run(["git", "rev-parse", "HEAD"], source) != commit:
        raise ValueError("The source commit must match the checked-out HEAD")
    if run(["git", "status", "--porcelain", "--untracked-files=all"], source):
        raise ValueError("Release builds require a clean source tree")
    header = (source / "src/base/version.h.in").read_text(encoding="utf-8")
    numbers: list[str] = []
    for component in ("MAJOR", "MINOR", "BUGFIX", "BUILD"):
        match = re.search(r"^#define QBT_VERSION_" + component + r" (\d+)$", header, re.MULTILINE)
        if match is None:
            raise ValueError("Missing application version")
        numbers.append(match[1])
    if numbers[-1] == "0":
        numbers.pop()
    status = re.search(r'^#define QBT_VERSION_STATUS "([A-Za-z0-9]*)"', header, re.MULTILINE)
    if status is None:
        raise ValueError("Missing application version status")
    version = ".".join(numbers) + ("~" + status[1] if status[1] else "") + "+git." + commit
    return Source(commit, version, int(run(["git", "show", "-s", "--format=%ct", "HEAD"], source)))


def buildPackage(source: Path, stage: Path, output: Path, commit: str) -> Path:
    info = sourceInfo(source, commit)
    names = ("gtkbittorrent", "gtkbittorrent-engine", "gtkbittorrent-import")
    for name in names:
        binary = stage / "usr/bin" / name
        if not binary.is_file() or binary.is_symlink() or not os.access(binary, os.X_OK):
            raise ValueError("Missing staged executable: " + name)
    if output.exists():
        raise ValueError("The output directory already exists")
    operatingSystem = Path("/etc/os-release").read_text(encoding="utf-8")
    if re.search(r'^ID=ubuntu$', operatingSystem, re.MULTILINE) is None or 'VERSION_ID="26.04"' not in operatingSystem:
        raise ValueError("Release packages require Ubuntu 26.04")
    architecture = run(["dpkg", "--print-architecture"], source)
    if architecture != "amd64":
        raise ValueError("Release packages currently require amd64")
    environment = dict(os.environ, SOURCE_DATE_EPOCH=str(info.epoch), LC_ALL="C")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gtkbt-package-", dir=output.parent) as temporary:
        work = Path(temporary)
        root = work / "root"
        shutil.copytree(stage, root, symlinks=True)
        control = root / "DEBIAN"
        control.mkdir()
        (work / "debian").mkdir()
        (work / "debian/control").write_text("Source: gtkbittorrent\n\nPackage: gtkbittorrent\nArchitecture: any\n", encoding="utf-8")
        dependencies = run(["dpkg-shlibdeps", "-O", *["-e" + str(root / "usr/bin" / name) for name in names]], work, environment)
        if not dependencies.startswith("shlibs:Depends="):
            raise RuntimeError("Cannot determine package dependencies")
        qtCore = run(["dpkg-query", "-W", "-f=${Version}", "libqt6core6t64"], work)
        depends = dependencies.removeprefix("shlibs:Depends=") + ", libqt6sql6-sqlite, qt6-qpa-plugins, libqt6core6t64 (= " + qtCore + ")"
        installed = run(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n"], work)
        metadata = {"schema": 1, "source_commit": info.commit, "dirty": False, "version": info.version,
                    "platform": "ubuntu-26.04", "architecture": architecture, "requires_qt": True,
                    "source_date_epoch": info.epoch, "build_packages": dict(line.split("\t", 1) for line in installed.splitlines())}
        manifest = json.dumps(metadata, indent=2, sort_keys=True) + "\n"
        documentation = root / "usr/share/doc/gtkbittorrent"
        documentation.mkdir(parents=True, exist_ok=True)
        (documentation / "SOURCE_COMMIT").write_text(info.commit + "\n", encoding="utf-8")
        applicationData = root / "usr/share/gtkbittorrent"
        applicationData.mkdir(parents=True, exist_ok=True)
        (applicationData / "build-info.json").write_text(manifest, encoding="utf-8")
        shutil.copyfile(source / "COPYING", documentation / "copyright")
        (control / "control").write_text(
            f"Package: gtkbittorrent\nVersion: {info.version}\nArchitecture: {architecture}\n"
            "Maintainer: gtkBittorrent contributors <noreply@gstn-caruso.github.io>\n"
            "Section: net\nPriority: optional\nHomepage: https://github.com/gstn-caruso/gtkBittorrent\n"
            f"Depends: {depends}\n"
            "Description: BitTorrent client undergoing migration to GTK\n"
            " Transitional build including the Qt desktop, headless engine, and\n"
            " Qt-free profile importer. Native GTK migration remains in progress.\n", encoding="utf-8")
        for path in [root, *root.rglob("*")]:
            os.utime(path, (info.epoch, info.epoch), follow_symlinks=False)
        artifacts = work / "artifacts"
        artifacts.mkdir()
        package = artifacts / f"gtkbittorrent_{info.version}_{architecture}.deb"
        run(["dpkg-deb", "--build", "--root-owner-group", "--uniform-compression", "-Zxz", "-z6", str(root), str(package)], work, environment)
        (artifacts / "build-info.json").write_text(manifest, encoding="utf-8")
        checksums = [hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n" for path in sorted(artifacts.iterdir())]
        (artifacts / "SHA256SUMS").write_text("".join(checksums), encoding="utf-8")
        artifacts.rename(output)
    return output / package.name


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    arguments = parser.parse_args()
    print(buildPackage(arguments.source.resolve(), arguments.stage.resolve(), arguments.output.resolve(), arguments.commit))
