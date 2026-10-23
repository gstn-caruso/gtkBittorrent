"""Exercise the Qt-free client against loopback HTTP and the real engine."""

import argparse
import json
import secrets
import subprocess  # nosec B404 # Exercise the locally built test probe without a shell.
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import testsession

probe: Path
engine: Path | None = None


def callProbe(data: dict[str, Any]) -> tuple[int, Any]:
    result = subprocess.run([str(probe)], input=json.dumps(data), text=True, capture_output=True, timeout=5, check=False)  # nosec B603 # Explicit locally built test probe.
    return result.returncode, json.loads(result.stdout)


class ApiServer(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), ApiHandler)
        self.responses: list[tuple[int, bytes, dict[str, str]]] = []
        self.requests: list[tuple[str, str, dict[str, str], bytes]] = []
        self.delay = 0.0
        self.release: threading.Event | None = None


class ApiHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.respond()

    def do_POST(self) -> None:
        self.respond()

    def respond(self) -> None:
        server = cast(ApiServer, self.server)
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        server.requests.append((self.command, self.path, dict(self.headers.items()), body))
        status, response, headers = server.responses.pop(0) if server.responses else (500, b"Unexpected request", {})
        if server.release is not None:
            server.release.wait(timeout=5)
        time.sleep(server.delay)
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        try:
            self.wfile.write(response)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format: str, *args: Any) -> None:
        pass


class TestEngineClient(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ApiServer()
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()
        self.addCleanup(self.closeServer)
        self.url = f"http://127.0.0.1:{self.server.server_port}/"
        self.password = secrets.token_urlsafe(24) + "+&= 日本語"

    def closeServer(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def invoke(self, **changes: Any) -> tuple[int, Any]:
        data = {"url": self.url, "username": "pruebas 日本語", "password": self.password, **changes}
        return callProbe(data)

    def testAuthenticateAndReadUnicodeSnapshotWithoutLosingIntegerPrecision(self) -> None:
        torrent = {"hash": "a" * 40, "name": "archivo 日本語.bin", "size": 9007199254740993, "progress": 0.5, "state": "stoppedDL"}
        self.server.responses = [(200, b"", {"Set-Cookie": "SID=private-session; HttpOnly; Path=/"}),
                                 (200, json.dumps([torrent]).encode(), {})]
        code, result = self.invoke()
        self.assertEqual(code, 0, result)
        self.assertEqual(result["torrents"], [torrent])
        login, snapshot = self.server.requests
        self.assertEqual(login[:2], ("POST", "/api/v2/auth/login"))
        self.assertEqual(urllib.parse.parse_qs(login[3].decode()), {"username": ["pruebas 日本語"], "password": [self.password]})
        self.assertEqual(login[2]["Referer"], self.url)
        self.assertEqual(snapshot[:2], ("GET", "/api/v2/torrents/info"))
        self.assertEqual(snapshot[2]["Cookie"], "SID=private-session")

    def testControlOnlyTheSelectedTorrentAndPreserveFilesByDefault(self) -> None:
        self.server.responses = [(200, b"", {}), (200, b"", {}), (200, b"", {}), (200, b"", {}), (200, b"[]", {})]
        identifier = "a" * 40
        code, result = self.invoke(stop=identifier, start=identifier, remove=identifier)
        self.assertEqual(code, 0, result)
        self.assertEqual([(method, path) for method, path, _, _ in self.server.requests[1:]],
                         [("POST", "/api/v2/torrents/stop"), ("POST", "/api/v2/torrents/start"),
                          ("POST", "/api/v2/torrents/delete"), ("GET", "/api/v2/torrents/info")])
        self.assertEqual(urllib.parse.parse_qs(self.server.requests[1][3].decode()), {"hashes": [identifier]})
        self.assertEqual(urllib.parse.parse_qs(self.server.requests[3][3].decode()), {"hashes": [identifier], "deleteFiles": ["false"]})

    def testRejectInvalidIdentifiersBeforeSendingAControlRequest(self) -> None:
        for identifier in ("all", "a" * 39, "a" * 41, "a" * 40 + "|" + "b" * 40):
            with self.subTest(identifier=identifier):
                self.server.requests.clear()
                self.server.responses = [(200, b"", {})]
                code, result = self.invoke(stop=identifier)
                self.assertEqual((code, result), (1, {"error": 0, "status": 0}))
                self.assertEqual(len(self.server.requests), 1)

    def testReportAuthenticationFailuresAndExpiredSessions(self) -> None:
        for status, body in ((401, b""), (403, b""), (200, b"Fails.")):
            with self.subTest(status=status):
                self.server.responses = [(status, body, {})]
                self.assertEqual(self.invoke(), (1, {"error": 1, "status": status}))
        self.server.responses = [(200, b"Ok.", {}), (403, b"", {})]
        self.assertEqual(self.invoke(), (1, {"error": 1, "status": 403}))

    def testRejectMalformedSnapshotsWithoutPartialResults(self) -> None:
        valid = {"hash": "a" * 40, "name": "torrent", "size": 123, "progress": 0.5, "state": "futureState"}
        invalid: list[Any] = [{}, "not-an-array", [valid, {}], [dict(valid, hash="invalid")],
                              [dict(valid, size=-1)], [dict(valid, size=1.5)], [dict(valid, progress=1.01)],
                              [dict(valid, progress="0.5")], [dict(valid, name=None)]]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.server.responses = [(200, b"", {}), (200, json.dumps(payload).encode(), {})]
                self.assertEqual(self.invoke(), (1, {"error": 3, "status": 0}))
        self.server.responses = [(200, b"", {}), (200, b"not json", {})]
        self.assertEqual(self.invoke(), (1, {"error": 3, "status": 0}))

    def testPreserveUnknownStatesAndReverseProxyPrefixes(self) -> None:
        torrent = {"hash": "b" * 64, "name": "torrent", "size": 0, "progress": 0, "state": "futureState"}
        self.server.responses = [(200, b"Ok.", {}), (200, json.dumps([torrent]).encode(), {})]
        self.assertEqual(self.invoke(url=self.url + "proxy"), (0, {"torrents": [torrent]}))
        self.assertEqual(self.server.requests[1][1], "/proxy/api/v2/torrents/info")
        self.assertEqual(self.server.requests[0][2]["Referer"], self.url + "proxy/")

    def testReportServerFailuresAndRejectCredentialRedirects(self) -> None:
        self.server.responses = [(500, b"sensitive server details", {})]
        self.assertEqual(self.invoke(), (1, {"error": 4, "status": 500}))
        self.server.requests.clear()
        self.server.responses = [(302, b"", {"Location": self.url + "another-origin"})]
        self.assertEqual(self.invoke(), (1, {"error": 3, "status": 302}))
        self.assertEqual(len(self.server.requests), 1)

    def testRejectInvalidEndpointsBeforeNetworkActivity(self) -> None:
        for url in ("file:///tmp/session", "https://user:secret@example.invalid/", self.url + "?extra=value", self.url + "#fragment", self.url + "\x00suffix"):
            with self.subTest(url=url):
                self.assertEqual(self.invoke(url=url), (1, {"error": 0, "status": 0}))
        self.assertFalse(self.server.requests)

    def testBoundRequestTimeAndReportTransportFailure(self) -> None:
        self.server.delay = 0.2
        self.server.responses = [(200, b"", {})]
        self.assertEqual(self.invoke(timeout=25), (1, {"error": 2, "status": 0}))

    def testAddMagnetWithUnicodeDestinationAndExplicitStoppedState(self) -> None:
        self.server.responses = [(200, b"", {}), (200, b"Ok.", {}), (200, b"[]", {})]
        magnet = "magnet:?xt=urn:btih:" + "a" * 40 + "&dn=日本語"
        code, result = self.invoke(magnet=magnet, save_path="/downloads/descargas 日本語")
        self.assertEqual(code, 0, result)
        addition = self.server.requests[1]
        self.assertEqual(addition[:2], ("POST", "/api/v2/torrents/add"))
        self.assertEqual(urllib.parse.parse_qs(addition[3].decode()), {"urls": [magnet], "savepath": ["/downloads/descargas 日本語"], "stopped": ["true"]})

    def testUploadTorrentBytesWithoutTextConversion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gtkbt-upload-") as directory:
            torrent = Path(directory) / "fixture.torrent"
            torrent.write_bytes(b"torrent\x00\xff\r\nbytes")
            self.server.responses = [(200, b"", {}), (200, b"", {}), (200, b"[]", {})]
            code, result = self.invoke(torrent=str(torrent), save_path="/downloads/descargas 日本語")
            self.assertEqual(code, 0, result)
            upload = self.server.requests[1]
            self.assertEqual(upload[:2], ("POST", "/api/v2/torrents/add"))
            self.assertTrue(upload[2]["Content-Type"].startswith("multipart/form-data; boundary="))
            self.assertIn(torrent.read_bytes(), upload[3])
            self.assertIn('name="savepath"\r\n\r\n/downloads/descargas 日本語'.encode(), upload[3])

    def testRejectUnsuccessfulAdditionEvenWithHttp200(self) -> None:
        self.server.responses = [(200, b"", {}), (200, b"Fails.", {})]
        self.assertEqual(self.invoke(magnet="magnet:?xt=urn:btih:" + "a" * 40, save_path="/downloads"), (1, {"error": 4, "status": 200}))

    def testReadCurrentAdditionSummaryIncludingPendingRequests(self) -> None:
        for status, success, pending in ((200, 1, 0), (202, 0, 1)):
            with self.subTest(status=status):
                summary: dict[str, Any] = {"success_count": success, "failure_count": 0, "pending_count": pending, "added_torrent_ids": []}
                self.server.responses = [(200, b"", {}), (status, json.dumps(summary).encode(), {}), (200, b"[]", {})]
                code, result = self.invoke(magnet="magnet:?xt=urn:btih:" + "a" * 40, save_path="/downloads")
                self.assertEqual(code, 0, result)


class TestRealEngineClient(unittest.TestCase):
    def testControlAndRestartPartialDownloadWithoutQtClientDependencies(self) -> None:
        if engine is None:
            self.skipTest("Run with --engine to exercise a real disposable session")
        testsession.binary = engine
        with tempfile.TemporaryDirectory(prefix="gtkbt-client-session-") as directory:
            session = testsession.Session(Path(directory))
            try:
                torrent, identifier, firstPiece = testsession.torrentFixture()
                torrentPath = session.root / "fixture.torrent"
                torrentPath.write_bytes(torrent)
                payload = session.destination / "archivo 日本語.bin"
                payload.write_bytes(firstPiece + b"\x00" * 16384)
                session.start()
                session.login()

                def invoke(**changes: Any) -> Any:
                    code, result = callProbe({"url": session.url, "username": "baseline", "password": session.password,
                                              "save_path": str(session.destination), **changes})
                    self.assertEqual(code, 0, result)
                    return result

                invoke(torrent=str(torrentPath))
                testsession.waitFor(session.torrents, lambda items: len(items) == 1)
                invoke(start=identifier)
                testsession.waitFor(session.torrents, lambda items: items[0]["state"] == "stalledDL" and items[0]["progress"] == 0.5)
                invoke(stop=identifier)
                testsession.waitFor(session.torrents, lambda items: items[0]["state"] == "stoppedDL")
                session.stop()
                session.start()
                session.login()
                testsession.waitFor(session.torrents, lambda items: bool(items) and items[0]["progress"] == 0.5)
                restored = invoke()["torrents"][0]
                self.assertEqual(restored["hash"], identifier)
                self.assertEqual(restored["progress"], 0.5)
                self.assertEqual(restored["state"], "stoppedDL")
                self.assertEqual(restored["name"], "archivo 日本語.bin")
                invoke(remove=identifier)
                testsession.waitFor(session.torrents, lambda items: not items)
                self.assertEqual(payload.read_bytes()[:16384], firstPiece)
                magnetId = "b" * 40
                invoke(magnet="magnet:?xt=urn:btih:" + magnetId + "&dn=日本語")
                testsession.waitFor(session.torrents, lambda items: len(items) == 1)
                self.assertEqual(invoke()["torrents"][0]["hash"], magnetId)
                invoke(remove=magnetId)
                testsession.waitFor(session.torrents, lambda items: not items)
                invoke(torrent=str(torrentPath))
                testsession.waitFor(session.torrents, lambda items: len(items) == 1)
                invoke(remove=identifier, delete_files=True)
                testsession.waitFor(session.torrents, lambda items: not items)
                testsession.waitFor(payload.exists, lambda exists: not exists)
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
