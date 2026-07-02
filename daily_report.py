"""Generate a compact daily fitness report and print it to stdout.

Usage:
    cd /home/johannes/apps/hanky-sin-garmin
    .venv/bin/python daily_report.py

Exits 0 on success, 1 on error. Output is plain markdown ready to send.
"""
import sys
import os

# Make sure we can find project modules
sys.path.insert(0, os.path.dirname(__file__))

import db
import analysis
import ai


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
