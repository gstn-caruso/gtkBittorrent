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

    def invokeBlocked(self, **changes: Any) -> Any:
        self.server.release = threading.Event()
        with subprocess.Popen([str(probe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:  # nosec B603 # Explicit locally built test probe.
            self.assertIsNotNone(process.stdin)
            self.assertIsNotNone(process.stdout)
            if process.stdin is None or process.stdout is None:
                self.fail("Missing probe streams")
            config = {key: value for key, value in {**self.config, **changes}.items() if value is not None}
            process.stdin.write(json.dumps(config))
            process.stdin.close()
            process.stdin = None
            with ThreadPoolExecutor(max_workers=1) as reader:
                ready = reader.submit(process.stdout.readline)
                try:
                    self.assertTrue(json.loads(ready.result(timeout=2))["ready"])
                finally:
                    self.server.release.set()
            output, errors = process.communicate(timeout=8)
            self.assertEqual(process.returncode, 0, errors)
            return json.loads(output)

    def testConstructAndSubmitWhileTheServerCannotRespond(self) -> None:
        self.server.responses = [(200, b"", {"Set-Cookie": "SID=worker; Path=/"}), (200, b"[]", {}),
                                 (200, b"", {}), (200, b"[]", {})]
        events = self.invokeBlocked()["events"]
        self.assertIn({"type": "connected"}, events)
        self.assertIn({"type": "accepted", "id": 1}, events)
        self.assertTrue(any(event["type"] == "snapshot" for event in events))
        self.assertEqual([(method, path) for method, path, _, _ in self.server.requests],
                         [("POST", "/api/v2/auth/login"), ("GET", "/api/v2/torrents/info"),
                          ("POST", "/api/v2/torrents/stop"), ("GET", "/api/v2/torrents/info")])
        self.assertTrue(all(headers.get("Cookie") == "SID=worker" for _, _, headers, _ in self.server.requests[1:]))

    def testKeepProcessingAfterAnIndividualCommandRejection(self) -> None:
        self.server.responses = [(200, b"", {}), (200, b"[]", {}), (409, b"", {}), (200, b"[]", {}),
                                 (200, b"", {}), (200, b"[]", {})]
        events = self.invokeBlocked(start="b" * 40)["events"]
        self.assertIn({"type": "failure", "id": 1, "kind": 4, "status": 409}, events)
        self.assertIn({"type": "accepted", "id": 2}, events)
        self.assertEqual([path for _, path, _, _ in self.server.requests],
                         ["/api/v2/auth/login", "/api/v2/torrents/info", "/api/v2/torrents/stop",
                          "/api/v2/torrents/info", "/api/v2/torrents/start", "/api/v2/torrents/info"])

    def testCancelQueuedCommandsAfterAuthenticationExpiryWithoutReplayingThem(self) -> None:
        self.server.responses = [(200, b"", {}), (200, b"[]", {}), (403, b"", {})]
        events = self.invokeBlocked(start="b" * 40)["events"]
        self.assertIn({"type": "failure", "id": 1, "kind": 1, "status": 403}, events)
        self.assertIn({"type": "failure", "id": 2, "kind": 1, "status": 403}, events)
        self.assertEqual(len(self.server.requests), 3)

    def testFailQueuedCommandsWhenInitialAuthenticationFails(self) -> None:
        self.server.responses = [(401, b"", {})]
        events = self.invokeBlocked()["events"]
        self.assertIn({"type": "failure", "id": 0, "kind": 1, "status": 401}, events)
        self.assertIn({"type": "failure", "id": 1, "kind": 1, "status": 401}, events)
        self.assertEqual(len(self.server.requests), 1)

    def testStopCancelsQueuedCommandsAndSkipsFurtherNetworkCalls(self) -> None:
        self.server.responses = [(200, b"", {})]
        events = self.invokeBlocked(stop_before_connect=True)["events"]
        self.assertIn({"type": "failure", "id": 1, "kind": 5, "status": 0}, events)
        self.assertFalse(any(path.endswith("torrents/stop") for _, path, _, _ in self.server.requests))

    def testCoalesceSnapshotsForASlowConsumer(self) -> None:
        self.server.responses = [(200, b"", {}), *[(200, b"[]", {}) for _ in range(100)]]
        result = self.invokeBlocked(stop=None, poll_ms=5, consumer_delay_ms=100)
        self.assertEqual(result["max_batch_snapshots"], 1)
        self.assertGreater(len(self.server.requests), 3)

    def testStopWakesAnIdleWorkerWithoutWaitingForItsPollDeadline(self) -> None:
        self.server.responses = [(200, b"", {}), (200, b"[]", {})]
        self.invokeBlocked(stop=None, poll_ms=60000)
        self.assertEqual(len(self.server.requests), 2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    arguments, remaining = parser.parse_known_args()
    probe = arguments.probe.resolve()
    unittest.main(argv=[__file__, *remaining])
