# Garmin Coach

A private, self-hosted fitness app that **auto-syncs your Garmin data**, **visualises**
recovery and training, and runs **Claude-powered analysis** (readiness coaching,
trend/anomaly detection, plain-English summaries). Weighted toward sleep / HRV /
recovery, with all-round coverage.

Everything runs on your own machine. Your data lives in a local SQLite file.

---

## How it works

```
Garmin Connect ──(garminconnect + garth, OAuth)──▶ sync.py ──▶ SQLite (garmin.db)
                                                                   │
                                              analysis.py (rolling baselines,
                                              HRV deviation, sleep debt, ACWR)
                                                                   │
                                   app.py (Streamlit dashboard) ───┤
                                                                   │
                                   ai.py (Anthropic API) ──────────┘
```

- **`sync.py`** — pulls data from Garmin and writes it to SQLite. Run by cron daily.
- **`app.py`** — the dashboard you open in a browser.
- No data leaves your machine except the compact metrics summary you explicitly
  send to Anthropic when you click "Analyse".

---

## Setup (one time)

```bash
cd garmin-coach
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # then edit .env with your details
```

Fill in `.env`:
- `GARMIN_EMAIL` / `GARMIN_PASSWORD` — only used for the first login.
- `ANTHROPIC_API_KEY` — from console.anthropic.com (for the AI tab).
- `ANTHROPIC_MODEL` — defaults to `claude-sonnet-4-6`; change to whatever you have access to.
- `SLEEP_NEED_HOURS` — your personal target (default 8).

### First login (interactive, handles MFA)

```bash
python sync.py --login
```

You'll be prompted for your MFA code if 2FA is on. On success, OAuth tokens are
cached in `.garmin_tokens/` and **you won't need your password or MFA again**
until they expire (~1 year). After this, you can even delete the password line
from `.env`.

### Backfill history

```bash
python sync.py --days 90      # pull the last 90 days
```

### Open the dashboard

```bash
streamlit run app.py
```

---

## Automate the daily sync (the "automatic" part)

After the one-time `--login`, sync runs headless from the cached tokens.

**macOS / Linux (cron):**
```bash
crontab -e
# every morning at 07:30, sync the last 3 days (catches late-uploading devices):
30 7 * * * cd /full/path/to/garmin-coach && .venv/bin/python sync.py --days 3 >> sync.log 2>&1
```

**Windows:** use Task Scheduler to run
`C:\path\to\.venv\Scripts\python.exe sync.py --days 3` daily, with the working
directory set to the project folder.

Leave the dashboard running (or start it when you want it). It re-reads the DB on
load; the cache refreshes every 5 minutes.

---

## What you get

**Recovery tab**
- Overnight HRV plotted against your Garmin baseline band, with a 7-day line.
- Resting HR with 7- and 28-day baselines; auto-flag when >5% above baseline.
- Sleep hours vs your target, colour-coded for debt.
- Sleep-stage composition (deep/REM/light/awake), Body Battery daily graph, and
  stress-level daily graph.
- A top-of-page alert when overnight HRV is **suppressed** vs baseline.

**Capacity envelope**
- Daily pain / fatigue / energy check-in stored locally.
- Learns a personal green / yellow / red load zone from steps, active minutes,
  activity load, high-stress minutes, sleep, HRV, resting HR, Body Battery, and
  your check-in response.
- After ~2 weeks, gives conservative activity ceilings based on what you are
  currently tolerating, not a generic push for more activity.

**Stress leak map**
- Finds recurring intraday high-stress windows from Garmin all-day stress
  samples, such as work-block or pre-bed leaks.
- Ranks leaks by recurrence, stress intensity, evening timing, and next-day
  recovery flags so the dashboard can point at the highest-impact intervention.

**Grappling**
- Auto-detects BJJ / grappling activities by Garmin activity name or type.
- For matched sessions, syncs activity HR detail and Garmin HR zones to estimate
  rounds, round recovery, peak HR, high-zone minutes, mat stress cost, and
  rolling / drilling / mixed classification.
- Joins next-day recovery metrics to flag when mat stress stacks with poor
  sleep, low Body Battery, suppressed HRV, or elevated resting HR.

**Training tab**
- Acute:Chronic Workload Ratio (ACWR) from per-activity training load, with the
  ~0.8–1.3 "sweet spot" band shaded. *ACWR is a contested metric — treat it as one
  signal, not gospel.*
- VO₂max estimate trend, and a recent-activities table (load, TE, HR, distance).

**AI analysis tab**
- Sends a compact metrics summary (not raw signals) to Claude, which returns:
  readiness verdict for today, flagged trends/anomalies over ~2 weeks, and 2–4
  concrete recommendations. You can inspect exactly what data was sent.
- Includes a question field where you can ask about recovery, fatigue, sleep,
  Body Battery, or training load. Claude answers from the compact metrics
  summary, capacity envelope, stress-leak map, and computed grappling metrics,
  not raw time-series.

---

## Honest limitations (read this)

- **Unofficial Garmin access.** `garminconnect` talks to Garmin Connect's internal
  API. This violates Garmin's ToS in the strict sense (personal-use sync is common
  and rarely actioned, but your account is theoretically exposable). Garmin can and
  does change its endpoints without notice, which may break sync until the library
  is updated (`pip install -U garminconnect`).
- **Field extraction is best-effort.** The exact JSON keys Garmin returns were not
  live-tested in this build. Every endpoint's raw response is stored verbatim in
  the `raw_json` table, so if a chart column is empty, inspect the raw payload and
  fix the `dig()` paths in `ingest.py`. They're all in one place.
- **Credentials live locally.** Your password (until tokens are cached) and the
  token cache sit on your machine. Keep it private; don't commit `.env` or
  `.garmin_tokens/`.
- **The AI is a model, not a doctor or coach.** It reasons over the numbers you
  give it. It can be wrong. Symptoms, pain, or illness override any readout.

## If sync breaks
1. `pip install -U garminconnect garth` (Garmin probably changed something).
2. Delete `.garmin_tokens/` and re-run `python sync.py --login`.
3. If a metric is missing, check the `raw_json` table for that date/endpoint and
   adjust the matching `dig()` path in `ingest.py`.
```
