#!/usr/bin/env python3

"""Publish verified artifacts once for their exact source commit."""

import argparse
import hashlib
import json
import re
import subprocess  # nosec B404 # Use GitHub's authenticated CLI without a shell.
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote


@dataclass(frozen=True)
class Asset:
    size: int
    digest: str


@dataclass
class Release:
    releaseId: int
    tag: str
    draft: bool
    prerelease: bool
    assets: dict[str, Asset]


class ReleaseApi(Protocol):
    def ensureTag(self, tag: str, commit: str) -> None: ...
    def findRelease(self, tag: str) -> Release | None: ...
    def createDraft(self, tag: str, commit: str, body: str) -> Release: ...
    def upload(self, releaseId: int, path: Path) -> None: ...
    def getRelease(self, releaseId: int) -> Release: ...
    def publish(self, releaseId: int) -> None: ...


def fileAsset(path: Path) -> Asset:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return Asset(path.stat().st_size, "sha256:" + digest.hexdigest())


def verifyArtifacts(directory: Path, commit: str) -> dict[str, Asset]:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("A full source commit SHA is required")
    paths = sorted(directory.iterdir())
    if any(not path.is_file() or path.is_symlink() or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*[A-Za-z0-9]", path.name) is None for path in paths):
        raise ValueError("Artifacts must be regular files with plain filenames")
    names = {path.name for path in paths}
    if not {"build-info.json", "SHA256SUMS"}.issubset(names) or not any(name.endswith(".deb") for name in names):
        raise ValueError("Missing package, build manifest, or checksums")
    if any(name not in ("build-info.json", "SHA256SUMS") and not name.endswith(".deb") for name in names):
        raise ValueError("Unexpected artifact")
    metadata = json.loads((directory / "build-info.json").read_text(encoding="utf-8"))
    if metadata.get("schema") != 1 or metadata.get("source_commit") != commit:
        raise ValueError("Build manifest does not match the source commit")
    if metadata.get("dirty") is not False:
        raise ValueError("Cannot publish a dirty source build")
    if metadata.get("requires_qt") is not True or metadata.get("platform") != "ubuntu-26.04":
        raise ValueError("Unsupported migration package metadata")
    expected = {path.name: fileAsset(path) for path in paths}
    checksums: dict[str, str] = {}
    for line in (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._+-]+)", line)
        if match is None or match[2] in checksums:
            raise ValueError("Invalid checksum manifest")
        checksums[match[2]] = "sha256:" + match[1]
    if set(checksums) != names - {"SHA256SUMS"}:
        raise ValueError("Incomplete checksum manifest")
    if any(expected[name].digest != digest for name, digest in checksums.items()):
        raise ValueError("Artifact checksum mismatch")
    return expected


def validateRemote(release: Release, expected: dict[str, Asset], complete: bool) -> None:
    if not release.prerelease:
        raise ValueError("Migration builds must remain prereleases")
    if set(release.assets) - set(expected):
        raise ValueError("Existing release contains different assets")
    if any(expected[name] != asset for name, asset in release.assets.items()):
        raise ValueError("Existing release contains different asset bytes")
    if complete and release.assets != expected:
        raise ValueError("Existing release has missing assets")


def publishRelease(api: ReleaseApi, directory: Path, commit: str) -> bool:
    expected = verifyArtifacts(directory, commit)
    tag = "build-" + commit
    api.ensureTag(tag, commit)
    release = api.findRelease(tag)
    if release is None:
        release = api.createDraft(tag, commit,
                                  "Transitional Qt build: the native GTK migration is in progress.\n\n"
                                  f"Source commit: `{commit}`. Linux packages target Ubuntu 26.04.\n"
                                  "See build-info.json for dependencies and SHA256SUMS for integrity checks.")
    if release.tag != tag:
        raise ValueError("Release tag does not match the source commit")
    validateRemote(release, expected, complete=not release.draft)
    if not release.draft:
        return False
    for name in sorted(expected):
        if name not in release.assets:
            api.upload(release.releaseId, directory / name)
    verified = api.getRelease(release.releaseId)
    validateRemote(verified, expected, complete=True)
    if verified.tag != tag:
        raise ValueError("Release tag changed during upload")
    api.ensureTag(tag, commit)
    if verified.draft:
        api.publish(release.releaseId)
    return True


class GitHub:
    def __init__(self, repository: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", repository) is None:
            raise ValueError("Invalid repository")
        self.repository = repository
        self.base = "repos/" + repository

    def request(self, endpoint: str, method: str = "GET", payload: dict[str, Any] | None = None,
                file: Path | None = None) -> tuple[int, Any]:
        command = ["gh", "api", "--include", "--method", method, endpoint]
        body = None
        if payload is not None:
            command.extend(["--input", "-"])
            body = json.dumps(payload)
        if file is not None:
            command.extend(["-H", "Content-Type: application/octet-stream", "--input", str(file)])
        result = subprocess.run(command, input=body, capture_output=True, text=True, check=False)  # nosec B603 # No shell; endpoints are constructed by this client.
        headers, separator, content = result.stdout.partition("\n\n")
        if not separator or not headers.startswith("HTTP/"):
            raise RuntimeError("GitHub request failed: " + result.stderr.strip())
        status = int(headers.splitlines()[0].split()[1])
        if status == 404:
            return status, None
        if result.returncode != 0:
            raise RuntimeError("GitHub request failed: " + result.stderr.strip())
        return status, json.loads(content) if content.strip() else None

    def ensureTag(self, tag: str, commit: str) -> None:
        endpoint = self.base + "/git/ref/tags/" + tag
        status, ref = self.request(endpoint)
        if status == 404:
            self.request(self.base + "/git/refs", "POST", {"ref": "refs/tags/" + tag, "sha": commit})
            _, ref = self.request(endpoint)
        if ref["object"]["type"] != "commit" or ref["object"]["sha"] != commit:
            raise RuntimeError("Immutable tag points to another commit")

    @staticmethod
    def parseRelease(data: dict[str, Any]) -> Release:
        return Release(int(data["id"]), str(data["tag_name"]), bool(data["draft"]), bool(data["prerelease"]),
                       {str(asset["name"]): Asset(int(asset["size"]), str(asset.get("digest") or "")) for asset in data["assets"]})

    def findRelease(self, tag: str) -> Release | None:
        status, data = self.request(self.base + "/releases/tags/" + tag)
        if status != 404:
            return self.parseRelease(data)
        page = 1
        while True:
            _, releases = self.request(self.base + f"/releases?per_page=100&page={page}")
            for release in releases:
                if release["tag_name"] == tag:
                    return self.parseRelease(release)
            if len(releases) < 100:
                return None
            page += 1

    def createDraft(self, tag: str, commit: str, body: str) -> Release:
        _, release = self.request(self.base + "/releases", "POST", {
            "tag_name": tag, "target_commitish": commit, "name": "gtkBittorrent " + tag,
            "body": body, "draft": True, "prerelease": True,
        })
        return self.parseRelease(release)

    def upload(self, releaseId: int, path: Path) -> None:
        self.request(f"https://uploads.github.com/{self.base}/releases/{releaseId}/assets?name={quote(path.name)}", "POST", file=path)

    def getRelease(self, releaseId: int) -> Release:
        _, release = self.request(self.base + f"/releases/{releaseId}")
        return self.parseRelease(release)

    def publish(self, releaseId: int) -> None:
        self.request(self.base + f"/releases/{releaseId}", "PATCH", {"draft": False, "prerelease": True, "make_latest": "false"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", required=True)
    arguments = parser.parse_args()
    created = publishRelease(GitHub(arguments.repository), arguments.artifacts, arguments.commit)
    print("Published prerelease" if created else "Reused immutable prerelease")
