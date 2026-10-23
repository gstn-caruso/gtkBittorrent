#!/usr/bin/env python3

"""Build, test, stage, and package the transitional Linux application."""

import argparse
import os
import shutil
import subprocess  # nosec B404 # Local CMake and CTest tools without a shell.
from pathlib import Path

from dist.release.package import buildPackage, sourceInfo


def build(source: Path, directory: Path, commit: str, jobs: int) -> Path:
    info = sourceInfo(source, commit)
    if jobs < 1:
        raise ValueError("At least one build job is required")
    cmake = shutil.which("cmake")
    ctest = shutil.which("ctest")
    if cmake is None or ctest is None:
        raise FileNotFoundError("CMake and CTest are required")
    directory.mkdir(parents=True)
    environment = dict(os.environ, SOURCE_DATE_EPOCH=str(info.epoch), QT_QPA_PLATFORM="offscreen")
    stage = directory / "stage"
    for variant in ("gui", "engine"):
        target = directory / variant
        gui = variant == "gui"
        commands = [
            [cmake, "-S", str(source), "-B", str(target), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
             "-DCMAKE_INSTALL_PREFIX=/usr", "-DTESTING=ON", "-DGUI=" + ("ON" if gui else "OFF"),
             "-DSYSTEMD=" + ("OFF" if gui else "ON"),
             "-DSYSTEMD_SERVICES_INSTALL_DIR=/usr/lib/systemd/system",
             f"-DCMAKE_CXX_FLAGS=-DQT_FORCE_ASSERTS -ffile-prefix-map={source}=/source -ffile-prefix-map={directory}=/build"],
            [cmake, "--build", str(target), "--parallel", str(jobs)],
            [ctest, "--test-dir", str(target), "--output-on-failure", "--parallel", str(jobs)],
        ]
        for command in commands:
            subprocess.run(command, cwd=source, env=environment, check=True)  # nosec B603 # Fixed build tools and explicit paths.
        subprocess.run([cmake, "--install", str(target)], cwd=source, env=dict(environment, DESTDIR=str(stage)), check=True)  # nosec B603 # Fixed CMake install command.
    return buildPackage(source, stage, directory / "artifacts", commit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--directory", type=Path, required=True, help="New build directory, outside tracked source files")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--jobs", type=int, default=2)
    arguments = parser.parse_args()
    print(build(arguments.source.resolve(), arguments.directory.resolve(), arguments.commit, arguments.jobs))
