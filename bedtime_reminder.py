import sys
import os
from datetime import datetime, timedelta

# Make sure we can find project modules
sys.path.insert(0, "/home/johannes/apps/hanky-sin-garmin")

import db
import analysis

def main():
    try:
        db.init_db()
        
        # Load data
        daily = analysis.enrich_daily(db.load_daily_df())
        checkins = db.load_checkins_df()
        sleep_timing = db.load_sleep_timing_df()
        
        # Calculate sleep need and bedtime
        personal_sleep_need = analysis.compute_personal_sleep_need(daily, checkins)
        sleep_need_h = personal_sleep_need.get("sleep_need_h", 8.0)
        
        rec = analysis.compute_recommended_bedtime(
            daily,
            sleep_timing,
            sleep_need_h=sleep_need_h,
        )
        
        if rec.get("status") != "ready":
            print("⚠️ Kunne ikke kalkulere leggetid: Mangler nok data.")
            sys.exit(0)
            
        bedtime_center = rec["bedtime_center"] # string like "22:45"
        
        # Parse the bedtime_center time to calculate "30 minutes before"
        h, m = map(int, bedtime_center.split(":"))
        # We need to subtract 30 minutes
        dt = datetime.combine(datetime.today(), datetime.min.time().replace(hour=h, minute=m))
        reminder_dt = dt - timedelta(minutes=30)
        reminder_time = reminder_dt.strftime("%H:%M")
        
        # Output message
        print(f"🛌 **Leggetid-påminnelse for i kveld!**\n")
        print(f"Appen anbefaler at du legger deg mellom **{rec['window_start']}** og **{rec['window_end']}** (optimalt senter: **{bedtime_center}**).")
        print(f"Siden du vil legge deg en halvtime før, bør du gå til sengs senest **{reminder_time}**.")
        if rec.get("reasons"):
            print("\n**Kontekst fra Garmin:**")
            for r in rec["reasons"]:
                print(f"- {r}")
    except Exception as e:
        print(f"❌ Feil ved kjøring av påminnelse: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
