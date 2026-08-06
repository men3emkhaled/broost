# -*- coding: utf-8 -*-
import unittest

from core.display_text import pos_text


class PosDisplayTextTest(unittest.TestCase):
    def test_removes_arabic_brand_as_a_standalone_word(self):
        self.assertEqual(pos_text("1. وجبات بروست"), "1. وجبات")
        self.assertEqual(pos_text("سندوتش بروست"), "سندوتش")

    def test_does_not_damage_longer_words(self):
        self.assertEqual(pos_text("بروستر سيستم"), "بروستر سيستم")

    def test_removes_english_brand_case_insensitively(self):
        self.assertEqual(pos_text("BROOST POS"), "POS")
        self.assertEqual(pos_text("Broost Kitchen"), "Kitchen")


if __name__ == "__main__":
    unittest.main()
