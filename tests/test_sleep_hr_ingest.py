import unittest

import ingest


class SleepHrIngestTest(unittest.TestCase):
    def test_pre_sleep_hr_prefers_10_minute_median(self):
        sleep_start = 1_000_000
        minute = 60_000
        series = [
            [sleep_start - 9 * minute, 60],
            [sleep_start - 5 * minute, 62],
            [sleep_start - 1 * minute, 90],  # spike should not dominate median
            [sleep_start + 1 * minute, 51],
            [sleep_start + 10 * minute, 49],
        ]

        overnight, pre_sleep = ingest._sleep_hr(
            series,
            sleep_start,
            sleep_start + 8 * 60 * minute,
            day_min=44,
        )

        self.assertEqual(overnight, 49.0)
        self.assertEqual(pre_sleep, 62.0)

    def test_pre_sleep_hr_falls_back_to_30_minute_median(self):
        sleep_start = 1_000_000
        minute = 60_000
        series = [
            [sleep_start - 28 * minute, 56],
            [sleep_start - 20 * minute, 60],
            [sleep_start - 12 * minute, 64],
            [sleep_start + 1 * minute, 52],
        ]

        _, pre_sleep = ingest._sleep_hr(series, sleep_start, sleep_start + 8 * 60 * minute, None)

        self.assertEqual(pre_sleep, 60.0)

    def test_sparse_pre_sleep_hr_keeps_nearest_sample_fallback(self):
        sleep_start = 1_000_000
        minute = 60_000
        series = [[sleep_start - 5 * minute, 75]]

        _, pre_sleep = ingest._sleep_hr(series, sleep_start, None, None)

        self.assertEqual(pre_sleep, 75.0)


if __name__ == "__main__":
    unittest.main()
