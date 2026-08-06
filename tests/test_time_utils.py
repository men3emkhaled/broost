# -*- coding: utf-8 -*-
import unittest
from datetime import datetime

from core.time_utils import elapsed_minutes, to_local_db_timestamp


class TimeUtilsTests(unittest.TestCase):
    def test_utc_timestamp_is_converted_to_system_local_time(self):
        source = "2026-08-05T19:14:43Z"
        expected = (
            datetime.fromisoformat("2026-08-05T19:14:43+00:00")
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S")
        )
        self.assertEqual(to_local_db_timestamp(source), expected)

    def test_naive_local_timestamp_is_not_shifted(self):
        self.assertEqual(
            to_local_db_timestamp("2026-08-05 22:14:43"),
            "2026-08-05 22:14:43",
        )

    def test_elapsed_minutes_never_goes_negative(self):
        now = datetime(2026, 8, 5, 22, 15, 0)
        self.assertEqual(elapsed_minutes("2026-08-05 22:14:00", now), 1)
        self.assertEqual(elapsed_minutes("2026-08-05 22:30:00", now), 0)
        self.assertEqual(elapsed_minutes("not-a-date", now), 0)


if __name__ == "__main__":
    unittest.main()
