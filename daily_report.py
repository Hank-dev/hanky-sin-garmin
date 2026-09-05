"""Generate a compact daily fitness report and print it to stdout.

Usage:
    cd /home/johannes/apps/hanky-sin-garmin
    .venv/bin/python daily_report.py

Exits 0 on success, 1 on error. Output is plain markdown ready to send.
"""
import sys
import os
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Make sure we can find project modules
sys.path.insert(0, os.path.dirname(__file__))

import db
import analysis
import ai
import config


def _attach_sync_context(summary: dict) -> None:
    """Attach the Garmin stats payload's actual last-sync time.

    `daily_metrics.updated_at` is the local DB write time, not necessarily the
    watch's last sync. The raw stats payload contains lastSyncTimestampGMT,
    which is the timestamp users need when interpreting point-in-time values.
    """
    as_of = summary.get("as_of")
    if not as_of:
        return
    try:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM raw_json WHERE date=? AND endpoint='stats'",
                (as_of,),
            ).fetchone()
        if not row:
            return
        payload = json.loads(row["payload"])
        raw_ts = payload.get("lastSyncTimestampGMT")
        if not raw_ts:
            return
        sync_dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        if sync_dt.tzinfo is None:
            sync_dt = sync_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        local_tz = ZoneInfo(config.LOCAL_TIMEZONE)
        summary["data_freshness"] = {
            "last_sync_local": sync_dt.astimezone(local_tz).isoformat(),
            "age_minutes": round((now - sync_dt).total_seconds() / 60.0, 1),
        }
    except Exception:
        # Freshness is valuable context, but must never break the daily report.
        return


def main():
    try:
        daily_df = db.load_daily_df()
        activities_df = db.load_activities_df()
    except Exception as e:
        print(f"❌ Failed to load data from DB: {e}", file=sys.stderr)
        sys.exit(1)

    if daily_df.empty:
        print("⚠️ No daily data found in database.", file=sys.stderr)
        sys.exit(1)

    try:
        enriched = analysis.enrich_daily(daily_df)
        summary = analysis.summarize(enriched, activities_df, lookback=14)
        _attach_sync_context(summary)
    except Exception as e:
        print(f"❌ Failed to compute metrics: {e}", file=sys.stderr)
        sys.exit(1)

    # Optional extras
    coach_memory = None
    active_experiments = None
    try:
        mem_df = db.load_memory_df(status="active")
        if not mem_df.empty:
            coach_memory = mem_df.to_dict(orient="records")
    except Exception:
        pass

    try:
        exp_df = db.load_experiments_df(status="active")
        if not exp_df.empty:
            active_experiments = exp_df.to_dict(orient="records")
    except Exception:
        pass

    try:
        result = ai.daily_brief(summary, coach_memory=coach_memory,
                                active_experiments=active_experiments)
    except Exception as e:
        print(f"❌ AI analysis failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()
