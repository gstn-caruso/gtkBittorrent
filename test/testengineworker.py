"""Verify that engine I/O stays on the worker and results cross as values."""

import argparse
import json
import secrets
import subprocess  # nosec B404 # Exercise the locally built worker probe.
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from testengineclient import ApiServer

probe: Path


class TestEngineWorker(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ApiServer()
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()
        self.addCleanup(self.closeServer)
        self.config: dict[str, Any] = {"url": f"http://127.0.0.1:{self.server.server_port}/", "username": "baseline",
                                       "password": secrets.token_urlsafe(24), "timeout": 5000, "stop": "a" * 40}

    def closeServer(self) -> None:
        if self.server.release is not None:
            self.server.release.set()
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def testConstructAndSubmitWhileTheServerCannotRespond(self) -> None:
        self.server.responses = [(200, b"", {"Set-Cookie": "SID=worker; Path=/"}), (200, b"[]", {}),
                                 (200, b"", {}), (200, b"[]", {})]
        self.server.release = threading.Event()
        with subprocess.Popen([str(probe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:  # nosec B603 # Explicit locally built test probe.
            self.assertIsNotNone(process.stdin)
            self.assertIsNotNone(process.stdout)
            if process.stdin is None or process.stdout is None:
                self.fail("Missing probe streams")
            process.stdin.write(json.dumps(self.config))
            process.stdin.close()
            process.stdin = None
            with ThreadPoolExecutor(max_workers=1) as reader:
                ready = reader.submit(process.stdout.readline)
                try:
                    self.assertEqual(json.loads(ready.result(timeout=2)), {"ready": True, "submitted": 1})
                finally:
                    self.server.release.set()
            output, errors = process.communicate(timeout=8)
            self.assertEqual(process.returncode, 0, errors)
            events = json.loads(output)["events"]
        self.assertIn({"type": "connected"}, events)
        self.assertIn({"type": "accepted", "id": 1}, events)
        self.assertTrue(any(event["type"] == "snapshot" for event in events))
        self.assertEqual([(method, path) for method, path, _, _ in self.server.requests],
                         [("POST", "/api/v2/auth/login"), ("GET", "/api/v2/torrents/info"),
                          ("POST", "/api/v2/torrents/stop"), ("GET", "/api/v2/torrents/info")])
        self.assertTrue(all(headers.get("Cookie") == "SID=worker" for _, _, headers, _ in self.server.requests[1:]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    arguments, remaining = parser.parse_known_args()
    probe = arguments.probe.resolve()
    unittest.main(argv=[__file__, *remaining])
