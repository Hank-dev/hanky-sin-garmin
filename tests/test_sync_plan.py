import unittest
from datetime import date

import ingest


class SyncPlanTest(unittest.TestCase):
    def test_empty_or_invalid_db_uses_initial_window(self):
        self.assertEqual(ingest.smart_sync_days(None, today=date(2026, 6, 4)), 7)
        self.assertEqual(ingest.smart_sync_days("not-a-date", today=date(2026, 6, 4)), 7)

    def test_current_db_uses_two_day_overlap(self):
        self.assertEqual(
            ingest.smart_sync_days("2026-06-04", today=date(2026, 6, 4)),
            2,
        )

    def test_yesterday_db_uses_two_days(self):
        self.assertEqual(
            ingest.smart_sync_days("2026-06-03", today=date(2026, 6, 4)),
            2,
        )

    def test_behind_db_catches_up_from_latest_day(self):
        self.assertEqual(
            ingest.smart_sync_days("2026-06-01", today=date(2026, 6, 4)),
            4,
        )

    def test_old_db_is_capped_for_dashboard_responsiveness(self):
        self.assertEqual(
            ingest.smart_sync_days("2026-05-01", today=date(2026, 6, 4)),
            14,
        )


if __name__ == "__main__":
    unittest.main()
