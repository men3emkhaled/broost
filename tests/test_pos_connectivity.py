from __future__ import annotations

import socket
import ssl
import unittest
import urllib.error

from core.online_sync import network_error_message, ssl_context


class PosConnectivityTest(unittest.TestCase):
    def test_bundled_ssl_context_requires_verified_certificates(self):
        context = ssl_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_network_errors_are_actionable(self):
        cert_error = urllib.error.URLError(
            ssl.SSLCertVerificationError(1, "certificate verify failed")
        )
        self.assertIn("شهادة HTTPS", network_error_message(cert_error))
        self.assertIn("مهلة", network_error_message(urllib.error.URLError(TimeoutError())))
        self.assertIn(
            "DNS",
            network_error_message(urllib.error.URLError(socket.gaierror(-2, "not found"))),
        )


if __name__ == "__main__":
    unittest.main()
