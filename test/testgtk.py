"""Exercise native GTK controls against a disposable loopback API."""

import argparse
import json
import os
import secrets
import subprocess  # nosec B404 # Run the local GTK test process on its isolated display.
import tempfile
import threading
import unittest
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import testsession
from testengineclient import ApiServer

probe: Path
engine: Path | None = None


def runGtk(data: Mapping[str, Any]) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="gtkbt-gtk-") as directory:
        environment = dict(os.environ, G_DEBUG="fatal-criticals", GSK_RENDERER="cairo", GDK_BACKEND="x11")
        environment.pop("WAYLAND_DISPLAY", None)
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            environment[name] = str(Path(directory) / name)
        return subprocess.run([str(probe)], input=json.dumps(data), env=environment, text=True, capture_output=True, timeout=25, check=False)  # nosec B603 # Explicit locally built GTK test binary.


class TestGtk(unittest.TestCase):
    def testFilterAndSortWithoutChangingTheCommandTarget(self) -> None:
        identifier = "f" * 40
        torrents = [{"hash": "a" * 40, "name": "zeta 日本語.bin", "size": 9007199254740992, "progress": 0.5, "state": "stoppedDL"},
                    {"hash": "b" * 40, "name": "other torrent", "size": 1024, "progress": 1, "state": "stoppedUP"},
                    {"hash": identifier, "name": "alpha 日本語.bin", "size": 9007199254740993, "progress": 0.25, "state": "stoppedDL"}]
        commands: list[tuple[str, dict[str, list[str]]]] = []
        server = ApiServer()

        def respond(method: str, path: str, body: bytes) -> tuple[int, bytes, dict[str, str]]:
            if path == "/api/v2/auth/login":
                return 200, b"Ok.", {}
            if method == "GET" and path == "/api/v2/torrents/info":
                return 200, json.dumps(torrents).encode(), {}
            if path in ("/api/v2/torrents/start", "/api/v2/torrents/stop"):
                commands.append((path, urllib.parse.parse_qs(body.decode())))
                torrents[2]["state"] = "downloading" if path.endswith("start") else "stoppedDL"
                return 200, b"", {}
            return 404, b"", {}

        server.provider = respond
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            result = runGtk({"url": f"http://127.0.0.1:{server.server_port}/", "username": "baseline",
                             "password": secrets.token_urlsafe(24), "action": "filter-sort", "hash": identifier})
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(commands, [("/api/v2/torrents/start", {"hashes": [identifier]}),
                                        ("/api/v2/torrents/stop", {"hashes": [identifier]})])
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def testConfirmRemovalOfTheCapturedTorrentAndResetDeletionChoice(self) -> None:
        for deleteFiles in (False, True):
            with self.subTest(deleteFiles=deleteFiles):
                self.checkRemoval(deleteFiles)

    def checkRemoval(self, deleteFiles: bool) -> None:
        identifier = "d" * 40
        name = "archivo 日本語.bin"
        torrents = [{"hash": "e" * 40, "name": "keep this torrent", "size": 1024, "progress": 1, "state": "stoppedUP"},
                    {"hash": identifier, "name": name, "size": 32768, "progress": 0.5, "state": "stoppedDL"}]
        removals: list[dict[str, list[str]]] = []
        server = ApiServer()

        def respond(method: str, path: str, body: bytes) -> tuple[int, bytes, dict[str, str]]:
            if path == "/api/v2/auth/login":
                return 200, b"Ok.", {}
            if method == "GET" and path == "/api/v2/torrents/info":
                return 200, json.dumps(torrents).encode(), {}
            if path == "/api/v2/torrents/delete":
                removals.append(urllib.parse.parse_qs(body.decode()))
                torrents.pop()
                return 200, b"", {}
            return 404, b"", {}

        server.provider = respond
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            result = runGtk({"url": f"http://127.0.0.1:{server.server_port}/", "username": "baseline",
                             "password": secrets.token_urlsafe(24), "action": "remove", "hash": identifier,
                             "name": name, "delete_files": deleteFiles})
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(removals, [{"hashes": [identifier], "deleteFiles": [str(deleteFiles).lower()]}])
            self.assertEqual(torrents[0]["name"], "keep this torrent")
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def testAddMagnetWithUnicodeDestinationAfterCancelAndInvalidInput(self) -> None:
        identifier = "c" * 40
        name = "descarga 日本語"
        magnet = f"magnet:?xt=urn:btih:{identifier}&dn={urllib.parse.quote(name)}"
        savePath = "/downloads/descargas 日本語"
        torrents: list[dict[str, Any]] = []
        additions: list[dict[str, list[str]]] = []
        server = ApiServer()

        def respond(method: str, path: str, body: bytes) -> tuple[int, bytes, dict[str, str]]:
            if path == "/api/v2/auth/login":
                return 200, b"Ok.", {}
            if method == "GET" and path == "/api/v2/torrents/info":
                return 200, json.dumps(torrents).encode(), {}
            if path == "/api/v2/torrents/add":
                additions.append(urllib.parse.parse_qs(body.decode()))
                torrents.append({"hash": identifier, "name": name, "size": 0, "progress": 0, "state": "stoppedDL"})
                return 200, b'{"success_count":1,"failure_count":0,"pending_count":0}', {}
            return 404, b"", {}

        server.provider = respond
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            result = runGtk({"url": f"http://127.0.0.1:{server.server_port}/", "username": "baseline",
                             "password": secrets.token_urlsafe(24), "action": "add-magnet", "magnet": magnet,
                             "save_path": savePath, "name": name})
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(additions, [{"urls": [magnet], "savepath": [savePath], "stopped": ["true"]}])
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def testExplainAuthenticationFailureAndDisableTorrentControls(self) -> None:
        server = ApiServer()
        server.responses = [(401, b"", {})]
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            result = runGtk({"url": f"http://127.0.0.1:{server.server_port}/", "username": "baseline",
                             "password": secrets.token_urlsafe(24), "expect_auth_failure": True})
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(len(server.requests), 1)
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def testDisplayUnicodeAndControlOnlyTheSelectedTorrent(self) -> None:
        password = secrets.token_urlsafe(24)
        identifier = "a" * 40
        torrents = [{"hash": "b" * 40, "name": "other torrent", "size": 1024, "progress": 1.0, "state": "stoppedUP"},
                    {"hash": identifier, "name": "archivo 日本語.bin", "size": 32768, "progress": 0.5, "state": "stoppedDL"}]
        server = ApiServer()
        commands: list[str] = []

        def respond(method: str, path: str, body: bytes) -> tuple[int, bytes, dict[str, str]]:
            fields = urllib.parse.parse_qs(body.decode())
            if path == "/api/v2/auth/login":
                if fields == {"username": ["baseline"], "password": [password]}:
                    return 200, b"", {"Set-Cookie": "SID=gtk-test; Path=/"}
                return 401, b"", {}
            if method == "GET" and path == "/api/v2/torrents/info":
                return 200, json.dumps(torrents).encode(), {}
            if fields.get("hashes") != [identifier]:
                return 400, b"", {}
            if path == "/api/v2/torrents/start":
                torrents[1]["state"] = "downloading"
                commands.append("start")
                return 200, b"", {}
            if path == "/api/v2/torrents/stop":
                torrents[1]["state"] = "stoppedDL"
                commands.append("stop")
                return 200, b"", {}
            return 404, b"", {}

        server.provider = respond
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            data: dict[str, Any] = {"url": f"http://127.0.0.1:{server.server_port}/", "username": "baseline",
                                    "password": password, "hash": identifier, "name": torrents[1]["name"]}
            result = runGtk(data)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(json.loads(result.stdout)["passed"])
            self.assertEqual(commands, ["start", "stop"])
            self.assertEqual(torrents[0]["state"], "stoppedUP")
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def testNativeControlsDriveARealPartialDownload(self) -> None:
        if engine is None:
            self.skipTest("Run with --engine to exercise the actual headless engine")
        testsession.binary = engine
        with tempfile.TemporaryDirectory(prefix="gtkbt-gtk-session-") as directory:
            session = testsession.Session(Path(directory))
            try:
                torrent, identifier, firstPiece = testsession.torrentFixture()
                payload = session.destination / "archivo 日本語.bin"
                payload.write_bytes(firstPiece + b"\x00" * 16384)
                session.start()
                session.login()
                session.upload(torrent)
                testsession.waitFor(session.torrents, lambda items: len(items) == 1)
                result = runGtk({"url": session.url, "username": "baseline", "password": session.password,
                                 "hash": identifier, "name": "archivo 日本語.bin", "count": 1, "started_state": "stalledDL"})
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertTrue(json.loads(result.stdout)["passed"])
                restored = testsession.waitFor(session.torrents, lambda items: items[0]["state"] == "stoppedDL")[0]
                self.assertEqual(restored["progress"], 0.5)
                self.assertEqual(payload.read_bytes()[:16384], firstPiece)
                self.assertIsNone(session.process.poll() if session.process is not None else 0)
            finally:
                session.close()

    def testNativeMagnetDialogAddsToARealEngine(self) -> None:
        if engine is None:
            self.skipTest("Run with --engine to exercise the actual headless engine")
        testsession.binary = engine
        with tempfile.TemporaryDirectory(prefix="gtkbt-gtk-magnet-") as directory:
            session = testsession.Session(Path(directory))
            try:
                session.start()
                session.login()
                identifier = "c" * 40
                name = "descarga 日本語"
                destination = session.destination / "descargas 日本語"
                magnet = f"magnet:?xt=urn:btih:{identifier}&dn={urllib.parse.quote(name)}"
                result = runGtk({"url": session.url, "username": "baseline", "password": session.password,
                                 "action": "add-magnet", "magnet": magnet, "save_path": str(destination), "name": name})
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                added = testsession.waitFor(session.torrents, lambda items: len(items) == 1)[0]
                self.assertEqual(added["hash"], identifier)
                self.assertEqual(added["name"], name)
                self.assertEqual(added["state"], "stoppedDL")
                self.assertEqual(Path(added["save_path"]), destination)
            finally:
                session.close()

    def testNativeRemovalKeepsFilesUnlessDeletionIsExplicit(self) -> None:
        if engine is None:
            self.skipTest("Run with --engine to exercise the actual headless engine")
        testsession.binary = engine
        for deleteFiles in (False, True):
            with self.subTest(deleteFiles=deleteFiles), tempfile.TemporaryDirectory(prefix="gtkbt-gtk-removal-") as directory:
                session = testsession.Session(Path(directory))
                try:
                    torrent, identifier, firstPiece = testsession.torrentFixture()
                    payload = session.destination / "archivo 日本語.bin"
                    content = firstPiece + b"\x00" * 16384
                    payload.write_bytes(content)
                    session.start()
                    session.login()
                    session.upload(torrent)
                    testsession.waitFor(session.torrents, lambda items: len(items) == 1)
                    result = runGtk({"url": session.url, "username": "baseline", "password": session.password,
                                     "action": "remove", "hash": identifier, "name": payload.name,
                                     "delete_files": deleteFiles, "remaining_count": 0})
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    self.assertEqual(session.torrents(), [])
                    if deleteFiles:
                        testsession.waitFor(payload.exists, lambda exists: not exists)
                    else:
                        self.assertEqual(payload.read_bytes(), content)
                finally:
                    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--engine", type=Path)
    arguments, remaining = parser.parse_known_args()
    probe = arguments.probe.resolve()
    engine = arguments.engine.resolve() if arguments.engine is not None else None
    unittest.main(argv=[__file__, *remaining])
