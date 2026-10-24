#!/usr/bin/env python3
"""Build the pinned runtime in a private prefix; never install into /usr."""
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
DEPS = ROOT / ".deps"
PREFIX = DEPS / "prefix"
JOBS = os.environ.get("BUILD_JOBS", "4")


def run(args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def environment():
    env = os.environ.copy()
    for key, value in {
        "PATH": str(PREFIX / "bin"),
        "PKG_CONFIG_PATH": f"{PREFIX}/lib/pkgconfig:{PREFIX}/share/pkgconfig",
        "LD_LIBRARY_PATH": str(PREFIX / "lib"),
        "GI_TYPELIB_PATH": str(PREFIX / "lib/girepository-1.0"),
        "XDG_DATA_DIRS": f"{PREFIX}/share:/usr/local/share:/usr/share",
    }.items():
        env[key] = value + (":" + env[key] if env.get(key) else "")
    return env


def main():
    sources = json.loads((ROOT / "scripts/runtime-sources.json").read_text())
    (DEPS / "sources").mkdir(parents=True, exist_ok=True)
    PREFIX.mkdir(exist_ok=True)
    for item in sources:
        name = f"{item['name']}-{item['version']}"
        marker = PREFIX / f".{name}-built"
        source = DEPS / "sources" / name
        if marker.exists():
            licenses = PREFIX / "share/licenses" / name
            licenses.mkdir(parents=True, exist_ok=True)
            if source.exists():
                for path in source.iterdir():
                    if path.is_file() and path.name.startswith(("COPYING", "LICENSE", "LEGAL", "BSDL")):
                        shutil.copy2(path, licenses)
            continue
        archive = DEPS / "sources" / item["url"].split("/")[-1]
        if not archive.exists():
            urllib.request.urlretrieve(item["url"], archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError(f"Checksum incorrecto: {archive}")
        if not source.exists():
            with tarfile.open(archive) as tar:
                tar.extractall(DEPS / "sources", filter="data")
        env = environment()
        if item["name"] == "ruby":
            build = DEPS / "build-ruby"
            build.mkdir(exist_ok=True)
            if not (build / "Makefile").exists():
                run([source / "configure", f"--prefix={PREFIX}", "--enable-shared", "--enable-load-relative", "--disable-install-doc"], cwd=build, env=env)
            run(["make", "-j", JOBS], cwd=build, env=env)
            run(["make", "install"], cwd=build, env=env)
        else:
            build = DEPS / f"build-{name}"
            run(["meson", "setup", *( ["--reconfigure"] if (build / "build.ninja").exists() else []), build, source,
                 f"--prefix={PREFIX}", "--libdir=lib", "--buildtype=release", "--wrap-mode=nodownload", *item["options"]], env=env)
            run(["meson", "compile", "-C", build, "-j", JOBS], env=env)
            run(["meson", "install", "-C", build], env=env)
        marker.touch()
        licenses = PREFIX / "share/licenses" / name
        licenses.mkdir(parents=True, exist_ok=True)
        for path in source.iterdir():
            if path.is_file() and path.name.startswith(("COPYING", "LICENSE", "LEGAL", "BSDL")):
                shutil.copy2(path, licenses)
    (DEPS / "env").write_text("\n".join(f"export {key}='{value}'" for key, value in environment().items()
        if key in {"PATH", "PKG_CONFIG_PATH", "LD_LIBRARY_PATH", "GI_TYPELIB_PATH", "XDG_DATA_DIRS"}) + "\n")


if __name__ == "__main__":
    main()
