"""Command-line sync. Run by cron for headless daily updates.

  python sync.py --login        # first time: interactive login + MFA, caches tokens
  python sync.py                # headless: sync last 7 calendar days (for cron)
  python sync.py --days 90      # backfill 90 days
"""
import argparse
import garmin_client
import ingest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--login", action="store_true",
                   help="Interactive first-time login (password + MFA), caches tokens.")
    p.add_argument("--days", type=int, default=7, help="How many trailing days to sync.")
    args = p.parse_args()

    client = garmin_client.get_client(interactive=args.login)
    ingest.backfill(client, days=args.days)


if __name__ == "__main__":
    main()
