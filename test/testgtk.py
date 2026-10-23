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
from pathlib import Path
from typing import Any

from testengineclient import ApiServer

probe: Path


class TestGtk(unittest.TestCase):
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
            with tempfile.TemporaryDirectory(prefix="gtkbt-gtk-") as directory:
                environment = dict(os.environ, G_DEBUG="fatal-criticals", GSK_RENDERER="cairo")
                for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
                    environment[name] = str(Path(directory) / name)
                data: dict[str, Any] = {"url": f"http://127.0.0.1:{server.server_port}/", "username": "baseline",
                                        "password": password, "hash": identifier, "name": torrents[1]["name"]}
                result = subprocess.run([str(probe)], input=json.dumps(data), env=environment, text=True, capture_output=True, timeout=25, check=False)  # nosec B603 # Explicit locally built GTK test binary.
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertTrue(json.loads(result.stdout)["passed"])
            self.assertEqual(commands, ["start", "stop"])
            self.assertEqual(torrents[0]["state"], "stoppedUP")
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    arguments, remaining = parser.parse_known_args()
    probe = arguments.probe.resolve()
    unittest.main(argv=[__file__, *remaining])
