"""Command-line sync. Run by cron for headless daily updates.

  python sync.py --login        # first time: interactive login + MFA, caches tokens
  python sync.py                # headless: sync last 7 calendar days (for cron)
  python sync.py --days 90      # backfill 90 days
"""
import argparse
import sys
import garmin_client
import db
import ingest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--login", action="store_true",
                   help="Interactive first-time login (password + MFA), caches tokens.")
    p.add_argument("--days", type=int, default=None,
                   help="How many trailing days to sync. Defaults to smart_sync_days().")
    args = p.parse_args()

    if args.days is None:
        try:
            latest = None
            try:
                daily = db.load_daily_df()
                if daily is not None and not daily.empty:
                    latest = str(daily.iloc[-1]["date"])[:10]
            except Exception:
                latest = None
            days = ingest.smart_sync_days(latest)
            if not days:
                days = 7
            print(f"smart_sync_days() -> {days} (latest={latest})")
        except Exception as e:
            days = 7
            print(f"smart_sync_days() failed ({e}); falling back to 7.")
    else:
        days = args.days
        print(f"--days {days} (explicit)")

    client = garmin_client.get_client(interactive=args.login)
    ok = ingest.backfill(client, days=days)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
