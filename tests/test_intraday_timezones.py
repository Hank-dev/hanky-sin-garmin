import unittest
import tempfile

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

    def test_daily_hr_loader_averages_raw_heart_rate_values(self):
        old_path = config.DB_PATH
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        config.DB_PATH = tmp.name
        db.config.DB_PATH = tmp.name
        try:
            db.init_db()
            db.save_raw("2026-06-04", "heart_rates", {
                "heartRateValues": [
                    [1780524000000, 60],
                    [1780524300000, 70],
                    [1780524600000, None],
                    [1780524900000, 300],
                ]
            })

            out = db.load_daily_hr_df()
        finally:
            config.DB_PATH = old_path
            db.config.DB_PATH = old_path

        self.assertEqual(len(out), 1)
        self.assertEqual(float(out.iloc[0]["avg_hr"]), 65.0)
        self.assertEqual(int(out.iloc[0]["samples"]), 2)

    def test_heart_rate_loader_returns_timestamped_samples(self):
        old_path = config.DB_PATH
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        config.DB_PATH = tmp.name
        db.config.DB_PATH = tmp.name
        try:
            db.init_db()
            db.save_raw("2026-06-04", "heart_rates", {
                "heartRateValues": [
                    [1780524000000, 60],
                    [1780524300000, 70],
                    [1780524600000, None],
                    [1780524900000, 300],
                ]
            })

            out = db.load_heart_rate_df()
        finally:
            config.DB_PATH = old_path
            db.config.DB_PATH = old_path

        self.assertEqual(len(out), 2)
        self.assertEqual(sorted(out["value"].tolist()), [60.0, 70.0])
        self.assertTrue((out["date"] == "2026-06-04").all())
        self.assertIn("timestamp", out.columns)


if __name__ == "__main__":
    unittest.main()
