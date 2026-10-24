#!/usr/bin/env python3
"""Produce the same version in source, Ruby, helper, tarball and checksums."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def elf(path):
    return path.is_file() and not path.is_symlink() and path.open("rb").read(4) == b"\x7fELF"


def archive(source, output, name):
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    def normalize(info):
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        info.mtime = epoch
        return info
    # gzip header timestamp also has to be stable across interrupted publication.
    import gzip
    with output.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tar:
            tar.add(source, arcname=name, filter=normalize)


def bundle_libraries(runtime, app, prefix):
    lib = runtime / "lib"
    lib.mkdir(exist_ok=True)
    env = os.environ | {"LD_LIBRARY_PATH": f"{prefix}/lib"}
    queue = [path for root in (runtime, app) for path in root.rglob("*") if elf(path)]
    seen = set()
    system = re.compile(r"^(ld-linux|lib(c|m|pthread|rt|dl|resolv|nss_[^.]+|util)\.so)")
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        output = subprocess.run(["ldd", str(path)], env=env, text=True, capture_output=True).stdout
        if "not found" in output:
            raise RuntimeError(f"Dependencia no resuelta: {path}\n{output}")
        for name, location in re.findall(r"\s*(\S+) => (/\S+)", output):
            if system.match(name):
                continue
            target = lib / name
            if not target.exists():
                shutil.copy2(Path(location).resolve(), target)
                queue.append(target)
    for root in (runtime, app):
        for path in root.rglob("*"):
            if elf(path):
                relative = os.path.relpath(lib, path.parent)
                run(["patchelf", "--set-rpath", f"$ORIGIN/{relative}", path], stdout=subprocess.DEVNULL)


def main():
    version = sys.argv[1]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Se requiere una versión SemVer estable")
    prefix = Path(os.environ.get("GTKB_RUNTIME", ROOT / ".deps/prefix")).resolve()
    gems = Path(os.environ.get("GTKB_GEMS", ROOT / "vendor/bundle/ruby/4.0.0")).resolve()
    for item in json.loads((ROOT / "scripts/runtime-sources.json").read_text()):
        if not (prefix / f".{item['name']}-{item['version']}-built").exists():
            raise RuntimeError(f"Compile primero el runtime fijado: {item['name']} {item['version']}")
    if not gems.exists():
        raise RuntimeError("Faltan las gems de Gemfile.lock")
    for name, pinned in re.findall(r"^    ([\w-]+) \(([^) ]+)\)", (ROOT / "Gemfile.lock").read_text(), re.MULTILINE):
        if not (gems / "specifications" / f"{name}-{pinned}.gemspec").is_file():
            raise RuntimeError(f"Gemfile.lock no coincide con las gems verificadas: {name} {pinned}")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    for old in dist.glob("*.tar.gz"):
        old.unlink()
    with tempfile.TemporaryDirectory(prefix="gtkb-package-") as temp:
        stage = Path(temp) / "gtkbittorrent"
        stage.mkdir()
        app = stage / "app"
        app.mkdir()
        for directory in ("lib", "bin", "data"):
            shutil.copytree(ROOT / directory, app / directory)
        (app / "VERSION").write_text(version + "\n")
        for file in ("README.md", "LICENSE", "Gemfile", "Gemfile.lock"):
            shutil.copy2(ROOT / file, app)
        licenses = stage / "licenses"
        licenses.mkdir()
        # Keep license texts for packaged system libraries and the private sources.
        for directory in Path("/usr/share/doc").iterdir():
            copyright_file = directory / "copyright"
            if copyright_file.is_file():
                shutil.copy2(copyright_file, licenses / (directory.name + ".copyright"))
        for item in json.loads((ROOT / "scripts/runtime-sources.json").read_text()):
            source = prefix.parent / "sources" / f"{item['name']}-{item['version']}"
            if source.exists():
                for path in source.glob("*"):
                    if path.is_file() and re.match(r"(COPYING|LICENSE|LEGAL|BSDL)", path.name):
                        shutil.copy2(path, licenses / f"{item['name']}-{path.name}")
        build = Path(temp) / "engine"
        run(["cmake", "-S", ROOT, "-B", build, "-DCMAKE_BUILD_TYPE=Release", f"-DAPP_VERSION={version}"])
        run(["cmake", "--build", build, "-j", os.environ.get("BUILD_JOBS", "4")])
        shutil.copy2(build / "gtkbittorrent-engine", app / "bin")
        runtime = stage / "runtime"
        shutil.copytree(prefix, runtime, symlinks=True, ignore=shutil.ignore_patterns("include", "pkgconfig", "cmake", "*.a", "*.la", "*.gir"))
        shutil.copytree(gems, runtime / "gems", symlinks=True, ignore=shutil.ignore_patterns("cache", "doc"))
        # All introspected namespaces needed by ruby-gnome, independent of host GTK.
        typelibs = runtime / "lib/girepository-1.0"
        typelibs.mkdir(exist_ok=True)
        for source in Path("/usr/lib/x86_64-linux-gnu/girepository-1.0").glob("*.typelib"):
            if not (typelibs / source.name).exists():
                shutil.copy2(source, typelibs)
        for source in (Path("/usr/share/icons/Adwaita"), Path("/usr/share/icons/hicolor")):
            if source.exists():
                shutil.copytree(source, runtime / "share/icons" / source.name, dirs_exist_ok=True)
        schemas = runtime / "share/glib-2.0/schemas"
        schemas.mkdir(parents=True, exist_ok=True)
        for source in Path("/usr/share/glib-2.0/schemas").glob("*.xml"):
            shutil.copy2(source, schemas)
        run(["glib-compile-schemas", schemas])
        # Optional modules opened at runtime are not part of ldd's ELF closure.
        for source in Path("/usr/lib/x86_64-linux-gnu").glob("gdk-pixbuf-2.0/2.10.0/loaders/*.so"):
            target = runtime / "lib/gdk-pixbuf-loaders" / source.name
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(source, target)
        shutil.copy2("/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders", runtime / "bin")
        bundle_libraries(runtime, app, prefix)
        (stage / "launch").write_text((ROOT / "scripts/launch.sh").read_text())
        (stage / "launch").chmod(0o755)
        shutil.copy2(ROOT / "scripts/install.sh", stage / "install.sh")
        (stage / "install.sh").chmod(0o755)
        manifest = {"version": version, "ruby": "4.0.7", "gtk": "4.24.1", "libadwaita": "1.10.0", "libtorrent": "2.0.12",
            "gems_lock_sha256": hashlib.sha256((ROOT / "Gemfile.lock").read_bytes()).hexdigest(),
            "runtime_sources": json.loads((ROOT / "scripts/runtime-sources.json").read_text())}
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        run([stage / "launch", "--version"])
        actual = subprocess.check_output([app / "bin/gtkbittorrent-engine", "--version"], text=True).strip()
        if actual != version:
            raise RuntimeError("Versión incorrecta del motor")
        binary = dist / f"gtkbittorrent-{version}-ubuntu-26.04-x86_64.tar.gz"
        archive(stage, binary, "gtkbittorrent")
        source = Path(temp) / f"gtkbittorrent-{version}"
        source.mkdir()
        try:
            paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
        except subprocess.CalledProcessError:
            paths = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.is_file() and not any(part.startswith(".") or part in {"build", "dist", "vendor", "node_modules"} for part in path.relative_to(ROOT).parts)]
        for name in filter(None, paths):
            path = ROOT / name
            if path.is_file():
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        (source / "VERSION").write_text(version + "\n")
        archive(source, dist / f"gtkbittorrent-{version}-sources.tar.gz", source.name)
    (dist / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in sorted(dist.glob("*.tar.gz"))))


if __name__ == "__main__":
    main()
