#!/usr/bin/env python3

"""Black-box session compatibility tests using only loopback and disposable profiles."""

import argparse
import base64
import hashlib
import http.cookiejar
import json
import os
import secrets
import shutil
import socket
import subprocess  # nosec B404 # Launch the locally built backend under test.
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar, cast

T = TypeVar("T")
binary: Path
fixtureOutput: Path | None = None


def waitFor(operation: Callable[[], T], ready: Callable[[T], bool]) -> T:
    deadline = time.monotonic() + 20
    while True:
        result = operation()
        if ready(result):
            return result
        if time.monotonic() >= deadline:
            raise AssertionError(f"Timed out waiting for session state: {result!r}")
        time.sleep(0.05)


class Session:
    def __init__(self, root: Path, storage: str = "Legacy") -> None:
        self.root = root
        self.profile = root / "qBittorrent"
        extension = ".ini" if sys.platform in ("win32", "darwin") else ".conf"
        self.config = self.profile / "config" / ("qBittorrent" + extension)
        self.config.parent.mkdir(parents=True)
        self.destination = root / "descargas 日本語"
        self.destination.mkdir()
        self.process: subprocess.Popen[bytes] | None = None
        self.log = (root / "process.log").open("wb")
        self.client = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )
        salt = b"session-baseline"
        self.password = secrets.token_urlsafe(24)
        key = hashlib.pbkdf2_hmac("sha512", self.password.encode(), salt, 100000)
        secret = base64.b64encode(salt).decode() + ":" + base64.b64encode(key).decode()
        with socket.socket() as listener, socket.socket() as peerListener:
            listener.bind(("127.0.0.1", 0))
            peerListener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
            peerPort = peerListener.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}/"
        self.config.write_text(
            "[BitTorrent]\n"
            "Session\\DHTEnabled=false\n"
            "Session\\LSDEnabled=false\n"
            "Session\\PeXEnabled=false\n"
            "Session\\InterfaceAddress=127.0.0.1\n"
            f"Session\\Port={peerPort}\n"
            f"Session\\ResumeDataStorageType={storage}\n"
            "[Network]\n"
            "PortForwardingEnabled=false\n"
            "[MigrationBaseline]\n"
            "UnknownSetting=preserve-this-value\n"
            "[Preferences]\n"
            "General\\Locale=en\n"
            "Connection\\ResolvePeerCountries=false\n"
            "WebUI\\Address=127.0.0.1\n"
            "WebUI\\LocalHostAuth=true\n"
            f"WebUI\\Port={self.port}\n"
            "WebUI\\Username=baseline\n"
            f'WebUI\\Password_PBKDF2="@ByteArray({secret})"\n',
            encoding="utf-8",
        )

    def start(self) -> None:
        environment = os.environ.copy()
        for name in tuple(environment):
            if name.startswith("QBT_"):
                del environment[name]
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            environment[name] = str(self.root / name)
        self.process = subprocess.Popen(  # nosec B603 # Explicit test binary without a shell.
            [str(binary), f"--profile={self.root}", "--relative-fastresume", "--confirm-legal-notice"],
            env=environment, stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log,
        )

        def isListening() -> bool:
            if self.process is None or self.process.poll() is not None:
                raise AssertionError("Backend exited during startup: " + self.diagnostics())
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    return True
            except OSError:
                return False

        waitFor(isListening, bool)

    def request(self, endpoint: str, fields: dict[str, str] | None = None,
                body: bytes | None = None, contentType: str = "application/x-www-form-urlencoded") -> bytes:
        if fields is not None:
            body = urllib.parse.urlencode(fields).encode()
        request = urllib.request.Request(
            self.url + "api/v2/" + endpoint, data=body,
            headers={"Referer": self.url, "Content-Type": contentType},
        )
        with self.client.open(request, timeout=3) as response:
            return cast(bytes, response.read())

    def data(self, endpoint: str) -> Any:
        return json.loads(self.request(endpoint))

    def torrents(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self.data("torrents/info"))

    def login(self) -> bytes:
        return self.request("auth/login", {"username": "baseline", "password": self.password})

    def upload(self, torrent: bytes) -> None:
        boundary = "session-baseline-boundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"savepath\"\r\n\r\n"
            f"{self.destination}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"stopped\"\r\n\r\ntrue\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"torrents\"; filename=\"fixture.torrent\"\r\n"
            "Content-Type: application/x-bittorrent\r\n\r\n"
        ).encode() + torrent + f"\r\n--{boundary}--\r\n".encode()
        self.request("torrents/add", body=body, contentType=f"multipart/form-data; boundary={boundary}")

    def stop(self) -> None:
        if self.process is not None:
            try:
                if self.process.poll() is None:
                    if os.name == "nt":
                        self.request("app/shutdown", {})
                    else:
                        self.process.terminate()
                code = self.process.wait(timeout=20)
                if code != 0:
                    raise AssertionError(f"Backend exited with {code}: {self.diagnostics()}")
            finally:
                if self.process.poll() is None:
                    self.process.kill()
                    self.process.wait(timeout=5)
                self.process = None

    def diagnostics(self) -> str:
        return (self.root / "process.log").read_text(encoding="utf-8", errors="replace")

    def close(self) -> None:
        try:
            self.stop()
        finally:
            self.log.close()


def torrentFixture() -> tuple[bytes, str, bytes]:
    """Return a deterministic v1 torrent and one of its two verified pieces."""
    firstPiece = bytes(range(256)) * 64
    secondPiece = b"b" * 16384
    name = "archivo 日本語.bin".encode()
    pieces = (hashlib.sha1(firstPiece, usedforsecurity=False).digest()
              + hashlib.sha1(secondPiece, usedforsecurity=False).digest())
    info = (b"d6:lengthi32768e4:name" + str(len(name)).encode() + b":" + name
            + b"12:piece lengthi16384e6:pieces40:" + pieces + b"7:privatei1ee")
    return b"d4:info" + info + b"e", hashlib.sha1(info, usedforsecurity=False).hexdigest(), firstPiece


class TestSession(unittest.TestCase):
    def testDownloadFromLocalPeer(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gtkbt-transfer-") as directory:
            root = Path(directory)
            seeder = Session(root / "seed")
            downloader = Session(root / "download")
            torrent, torrentHash, firstPiece = torrentFixture()
            completePayload = firstPiece + b"b" * 16384
            (seeder.destination / "archivo 日本語.bin").write_bytes(completePayload)
            try:
                for session in (seeder, downloader):
                    session.start()
                    session.login()
                    session.upload(torrent)
                    waitFor(session.torrents, lambda items: len(items) == 1)
                    session.request("torrents/start", {"hashes": torrentHash})
                waitFor(seeder.torrents, lambda items: items[0]["progress"] == 1)
                waitFor(downloader.torrents, lambda items: items[0]["state"] == "stalledDL")
                port = seeder.data("app/preferences")["listen_port"]
                downloader.request("torrents/addPeers", {"hashes": torrentHash, "peers": f"127.0.0.1:{port}"})
                waitFor(downloader.torrents, lambda items: items[0]["progress"] == 1)
                downloader.stop()
                self.assertEqual((downloader.destination / "archivo 日本語.bin").read_bytes(), completePayload)
            finally:
                try:
                    downloader.close()
                finally:
                    seeder.close()

    def testLoadInheritedResumeData(self) -> None:
        fixtures = Path(__file__).parent / "testdata" / "session"
        for source in ("legacy", "sqlite"):
            for storage in ("Legacy", "SQLite"):
                with self.subTest(source=source, storage=storage), tempfile.TemporaryDirectory(prefix="gtkbt-import-") as directory:
                    session = Session(Path(directory), storage)
                    try:
                        fixture = fixtures / source
                        shutil.copytree(fixture / "qBittorrent" / "data", session.profile / "data")
                        shutil.copytree(fixture / "descargas 日本語", session.destination, dirs_exist_ok=True)
                        session.start()
                        session.login()
                        torrents = waitFor(session.torrents,
                                           lambda items: len(items) == 1 and items[0]["state"] == "stoppedDL")
                        self.assertRestoredTorrent(session, torrents[0])
                    finally:
                        session.close()

    def testRecoverInterruptedSettingsWrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gtkbt-settings-") as directory:
            session = Session(Path(directory))
            try:
                fallback = session.config.with_stem("qBittorrent_new")
                fallback.write_text(session.config.read_text(encoding="utf-8")
                                    + "\n[BitTorrent]\nSession\\GlobalDLSpeedLimit=73\n", encoding="utf-8")
                session.start()
                self.assertEqual(session.login(), b"")
                self.assertEqual(session.data("app/preferences")["dl_limit"], 73 * 1024)
                session.stop()
                self.assertFalse(fallback.exists())
                self.assertIn("UnknownSetting=preserve-this-value", session.config.read_text(encoding="utf-8"))
            finally:
                session.close()

    def testRestartPreservesPartialDownload(self) -> None:
        for storage in ("Legacy", "SQLite"):
            with self.subTest(storage=storage), tempfile.TemporaryDirectory(prefix="gtkbt-session-") as directory:
                session = Session(Path(directory), storage)
                try:
                    self.checkRestart(session, storage)
                finally:
                    session.close()

    def checkRestart(self, session: Session, storage: str) -> None:
        torrent, torrentHash, firstPiece = torrentFixture()
        payload = session.destination / "archivo 日本語.bin"
        payload.write_bytes(firstPiece)
        session.start()
        with self.assertRaises(urllib.error.HTTPError) as rejected:
            session.request("torrents/info")
        self.assertEqual(rejected.exception.code, 403)
        rejected.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as invalidLogin:
            session.request("auth/login", {"username": "baseline", "password": session.password + "-invalid"})
        self.assertEqual(invalidLogin.exception.code, 401)
        invalidLogin.exception.close()
        self.assertEqual(session.login(), b"")
        session.upload(torrent)
        torrents = waitFor(session.torrents, lambda items: len(items) == 1)
        self.assertEqual(torrents[0]["hash"], torrentHash)
        session.request("torrents/recheck", {"hashes": torrentHash})
        waitFor(session.torrents, lambda items: items[0]["progress"] == 0.5)
        session.request("torrents/stop", {"hashes": torrentHash})
        waitFor(session.torrents, lambda items: items[0]["state"] == "stoppedDL")
        session.request("torrents/createCategory", {"category": "pruebas/日本語", "savePath": ""})
        session.request("torrents/setCategory", {"hashes": torrentHash, "category": "pruebas/日本語"})
        session.request("torrents/addTags", {"hashes": torrentHash, "tags": "linux, 日本語"})
        session.request("torrents/setDownloadLimit", {"hashes": torrentHash, "limit": "32768"})
        session.request("torrents/filePrio", {"hash": torrentHash, "id": "0", "priority": "6"})
        session.request("app/setPreferences", {"json": json.dumps({"dl_limit": 131072, "locale": "en"})})
        session.stop()
        if storage == "Legacy":
            self.assertTrue((session.profile / "data" / "BT_backup" / f"{torrentHash}.fastresume").is_file())
        else:
            self.assertTrue((session.profile / "data" / "torrents.db").is_file())
        self.assertIn("UnknownSetting=preserve-this-value", session.config.read_text(encoding="utf-8"))
        if fixtureOutput is not None:
            target = fixtureOutput / storage.lower()
            shutil.copytree(session.profile / "data", target / "qBittorrent" / "data",
                            ignore=shutil.ignore_patterns("GeoDB", "logs"))
            shutil.copytree(session.destination, target / session.destination.name)
            (target / "fixture.torrent").write_bytes(torrent)
        session.start()
        self.assertEqual(session.login(), b"")
        torrents = waitFor(session.torrents,
                           lambda items: len(items) == 1 and items[0]["state"] == "stoppedDL")
        restored = torrents[0]
        self.assertRestoredTorrent(session, restored)
        self.assertEqual(session.data("app/preferences")["dl_limit"], 131072)
        self.assertEqual(payload.read_bytes()[:16384], firstPiece)
        session.request("torrents/start", {"hashes": torrentHash})
        waitFor(session.torrents, lambda items: items[0]["state"] == "stalledDL")
        session.request("torrents/delete", {"hashes": torrentHash, "deleteFiles": "false"})
        waitFor(session.torrents, lambda items: not items)
        self.assertTrue(payload.is_file())
        session.stop()

    def assertRestoredTorrent(self, session: Session, restored: dict[str, Any]) -> None:
        _, torrentHash, _ = torrentFixture()
        self.assertEqual(restored["hash"], torrentHash)
        self.assertEqual(restored["state"], "stoppedDL")
        self.assertEqual(restored["progress"], 0.5)
        self.assertEqual(Path(restored["save_path"]), session.destination)
        self.assertEqual(restored["category"], "pruebas/日本語")
        self.assertEqual(set(restored["tags"].split(", ")), {"linux", "日本語"})
        self.assertEqual(restored["dl_limit"], 32768)
        self.assertEqual(session.data(f"torrents/files?hash={torrentHash}")[0]["priority"], 6)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--fixture-output", type=Path, help="Export resume fixtures before restarting")
    arguments, remaining = parser.parse_known_args()
    binary = arguments.binary.resolve(strict=True)
    fixtureOutput = arguments.fixture_output
    unittest.main(argv=[__file__, *remaining])
