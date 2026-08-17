from __future__ import annotations

import io
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from core.online_sync import OnlineSyncManager
from pos_guard import MAX_RESTARTS, RESTART_WINDOW_SECONDS, should_restart


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class RuntimeRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.manager = OnlineSyncManager()
        self.manager._connection_values = lambda: ("https://example.test", "sync-key")

    def test_transient_network_failure_is_retried_once(self):
        with mock.patch(
            "core.online_sync.open_url",
            side_effect=[urllib.error.URLError(TimeoutError()), _Response(b'{"ok": true}')],
        ) as opener, mock.patch("core.online_sync.time.sleep"):
            result = self.manager._request_json("/health")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(opener.call_count, 2)

    def test_authentication_error_is_not_retried(self):
        error = urllib.error.HTTPError(
            "https://example.test/health", 401, "Unauthorized", {}, io.BytesIO(b"{}")
        )
        with mock.patch("core.online_sync.open_url", side_effect=error) as opener:
            with self.assertRaisesRegex(RuntimeError, "مفتاح المزامنة"):
                self.manager._request_json("/health")
        self.assertEqual(opener.call_count, 1)

    def test_guard_stops_an_infinite_restart_loop(self):
        now = time.monotonic()
        restarts = [now - 10] * MAX_RESTARTS
        self.assertFalse(should_restart(1, restarts, now))
        self.assertFalse(should_restart(0, [], now))

    def test_guard_discards_old_restart_attempts(self):
        now = time.monotonic()
        restarts = [now - RESTART_WINDOW_SECONDS - 1] * MAX_RESTARTS
        self.assertTrue(should_restart(1, restarts, now))
        self.assertEqual(restarts, [])

    def test_release_launchers_use_the_recovery_guard(self):
        root = Path(__file__).resolve().parents[1]
        build_script = (root / "build_windows.bat").read_text(encoding="utf-8")
        installer = (root / "setup.iss").read_text(encoding="utf-8")
        self.assertIn('CashierSystemGuard.exe', build_script)
        self.assertIn('Filename: "{app}\\CashierSystemGuard.exe"', installer)


if __name__ == "__main__":
    unittest.main()
