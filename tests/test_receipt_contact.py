# -*- coding: utf-8 -*-
"""Receipt contact details must stay in one configured, tested place."""

from __future__ import annotations

import unittest
from pathlib import Path

from core import config


class ReceiptContactTests(unittest.TestCase):
    def test_receipt_uses_current_landline_and_mobile_only(self):
        dashboard_source = (
            Path(__file__).resolve().parents[1] / "views" / "dashboard.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(config.RESTAURANT_LANDLINE, "0552802874")
        self.assertEqual(config.RESTAURANT_MOBILE, "01092453841")
        self.assertIn("config.RESTAURANT_LANDLINE", dashboard_source)
        self.assertIn("config.RESTAURANT_MOBILE", dashboard_source)
        self.assertNotIn("01006593609", dashboard_source)


if __name__ == "__main__":
    unittest.main()
