import unittest

from webapp.phone_validation import valid_egyptian_mobile


class EgyptianMobileValidationTests(unittest.TestCase):
    def test_accepts_the_four_egyptian_mobile_prefixes(self):
        for phone in (
            "01012345678",
            "01112345678",
            "01212345678",
            "01512345678",
        ):
            with self.subTest(phone=phone):
                self.assertTrue(valid_egyptian_mobile(phone))

    def test_rejects_wrong_length_prefix_or_format(self):
        for phone in (
            "0101234567",
            "010123456789",
            "01312345678",
            "02012345678",
            "+201012345678",
            "010 1234 5678",
            "abcdefghijk",
            "",
            None,
        ):
            with self.subTest(phone=phone):
                self.assertFalse(valid_egyptian_mobile(phone))


if __name__ == "__main__":
    unittest.main()
