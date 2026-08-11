# -*- coding: utf-8 -*-
"""Cashier-readable formatting for incoming online order items."""

import unittest

from dialogs.online_order import format_online_order_item


class OnlineOrderItemFormatTest(unittest.TestCase):
    def test_quantity_size_and_every_extra_have_separate_lines(self):
        formatted = format_online_order_item({
            "item_name": "نص فرخة 5 قطع",
            "quantity": 2,
            "size_name": "كبير",
            "extras": [
                {"name": "صوص شيدر إضافي"},
                {"name": "علبة كول سلو إضافية"},
                {"name": "حار"},
            ],
        })

        self.assertEqual(
            formatted.splitlines(),
            [
                "2 × نص فرخة 5 قطع",
                "الحجم: كبير",
                "إضافة: صوص شيدر إضافي",
                "إضافة: علبة كول سلو إضافية",
                "إضافة: حار",
            ],
        )

    def test_default_size_is_not_repeated(self):
        self.assertEqual(
            format_online_order_item({
                "item_name": "برجر",
                "quantity": 1,
                "size_name": "عادي",
                "extras": [],
            }),
            "1 × برجر",
        )


if __name__ == "__main__":
    unittest.main()
