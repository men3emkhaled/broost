import unittest

from core.online_sync import strip_area_prefix as strip_local_area_prefix
from webapp.server import strip_area_prefix as strip_web_area_prefix


class AddressNormalizationTests(unittest.TestCase):
    def test_repeated_village_prefix_is_removed(self):
        address = "البلاشون - البلاشون - البلاشون - الشيخ غنيمي الزعور"
        expected = "الشيخ غنيمي الزعور"
        self.assertEqual(strip_web_area_prefix(address, "البلاشون"), expected)
        self.assertEqual(strip_local_area_prefix(address, "البلاشون"), expected)

    def test_unrelated_address_is_preserved(self):
        address = "الشيخ غنيمي الزعور بجوار الوحدة الصحية"
        self.assertEqual(strip_web_area_prefix(address, "البلاشون"), address)
        self.assertEqual(strip_local_area_prefix(address, "البلاشون"), address)

    def test_only_village_is_not_valid_detail(self):
        self.assertEqual(strip_web_area_prefix("البلاشون", "البلاشون"), "")
        self.assertEqual(strip_local_area_prefix("البلاشون", "البلاشون"), "")


if __name__ == "__main__":
    unittest.main()
