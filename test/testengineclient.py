"""Exercise the Qt-free client against loopback HTTP and the real engine."""

import argparse
import json
import secrets
import subprocess  # nosec B404 # Exercise the locally built test probe without a shell.
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

probe: Path


class ApiServer(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), ApiHandler)
        self.responses: list[tuple[int, bytes, dict[str, str]]] = []
        self.requests: list[tuple[str, str, dict[str, str], bytes]] = []


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
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

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
        result = subprocess.run([str(probe)], input=json.dumps(data), text=True, capture_output=True, timeout=5, check=False)  # nosec B603 # Explicit locally built test probe.
        return result.returncode, json.loads(result.stdout)

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    arguments, remaining = parser.parse_known_args()
    probe = arguments.probe.resolve()
    unittest.main(argv=[__file__, *remaining])
