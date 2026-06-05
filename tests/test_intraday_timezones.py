import unittest

import config
import db


class IntradayTimezoneTest(unittest.TestCase):
    def test_numeric_garmin_timestamp_displays_as_local_time(self):
        old_tz = config.LOCAL_TIMEZONE
        config.LOCAL_TIMEZONE = "Europe/Oslo"
        try:
            ts = db._parse_bb_timestamp(1780524000000)
        finally:
            config.LOCAL_TIMEZONE = old_tz

        self.assertEqual(str(ts), "2026-06-04 00:00:00")


if __name__ == "__main__":
    unittest.main()
