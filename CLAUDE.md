# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A private, self-hosted fitness app ("Garmin Coach") that syncs Garmin Connect data into a local SQLite file, visualises recovery/training in a Streamlit dashboard, and runs Claude-powered readiness analysis. Single-user, runs entirely on the user's machine. No web framework, no server, no auth layer.

## Commands

```bash
# Setup (one time)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                # then edit .env

# First Garmin login — interactive, handles MFA, caches OAuth tokens to .garmin_tokens/
python sync.py --login

# Backfill history / sync
python sync.py --days 90            # pull last 90 days
python sync.py                      # headless, last 7 days (what cron runs)

# Run the dashboard
streamlit run app.py

# If Garmin sync breaks (Garmin changed its internal API)
pip install -U garminconnect garth
rm -rf .garmin_tokens/ && python sync.py --login
```

There is no test suite, linter, or build step configured. `analysis.py` is written to be pure and unit-testable (no network, no AI, deterministic) — if adding tests, target that module.

## Architecture

The pipeline is a one-directional flow; each stage is a separate module with a narrow job:

```
Garmin Connect ──garmin_client.py (garminconnect+garth OAuth)──▶ ingest.py ──▶ SQLite (garmin.db, via db.py)
                                                                                    │
                                            analysis.py (pure analytics) ◀──────────┤
                                                    │                               │
                          app.py (Streamlit UI) ◀───┴──── ai.py (Anthropic API) ◀───┘
```

- **`config.py`** — central config, imported by nearly every module. Reads `.env` via `python-dotenv`. Defines `DB_PATH`, `GARMIN_TOKENSTORE`, `ANTHROPIC_MODEL`, `SLEEP_NEED_HOURS`, etc. Change behaviour here or in `.env`, not by hardcoding elsewhere.
- **`garmin_client.py`** — auth only. Resumes cached tokens for headless runs; `interactive=True` allows password+MFA login (only `sync.py --login` uses this). Cron must use `interactive=False`.
- **`ingest.py`** — fetches each Garmin endpoint per day and maps the JSON into flat records. See "The `dig()` pattern" below — this is where things break and get fixed.
- **`db.py`** — SQLite layer. Four tables: `daily_metrics` (PK `date`), `activities` (PK `activity_id`), `daily_checkins` (PK `date` for pain/fatigue/energy), `raw_json` (PK `date`+`endpoint`). All writes are idempotent upserts, so re-syncing a date is safe. Garmin syncs must not overwrite check-ins. Loaders return pandas DataFrames.
- **`analysis.py`** — all derived metrics. `enrich_daily()` adds rolling baselines (7d/28d RHR & HRV), HRV suppression flags, RHR-elevation flags, sleep debt. `compute_acwr()` computes Acute:Chronic Workload Ratio from per-activity load. `compute_capacity_envelope()` estimates personal green/yellow/red load tolerance from stable-response days plus check-ins. `compute_stress_leak_map()` ranks recurring intraday stress leak windows from all-day stress samples and next-day recovery flags. `compute_grappling_sessions()` analyzes auto-detected BJJ/grappling sessions from activity HR detail and Garmin HR zones. `summarize()` produces the compact dict sent to the AI. No I/O here — keep it that way.
- **`ai.py`** — Anthropic API boundary. `analyze(summary)` creates the structured readiness report; `answer_question(question, summary, capacity, stress_leak_map, grappling_sessions)` answers user health/training questions from compact context. Receives summaries/derived metrics only, never raw time-series. Prompts live here.
- **`app.py`** — Streamlit single-page recovery cockpit. `load()` is `@st.cache_data(ttl=300)`, so the DB is re-read at most every 5 minutes.

Data is keyed on `'YYYY-MM-DD'` date strings throughout. `daily_metrics` is one row per day; `activities` is one row per workout, joined to days by date for ACWR; `daily_checkins` is one subjective row per day, joined by date for the capacity envelope.

Body Battery / stress note: the daily Body Battery graph is parsed from raw `all_day_stress` payloads (`bodyBatteryValuesArray`), and the daily stress-level graph is parsed from `stressValuesArray` in the same payload. The separate `get_body_battery` endpoint is still stored as raw `body_battery`, but Garmin returned only sparse event-like values there in local testing.

Stress leak note: `compute_stress_leak_map()` can use intraday stress samples locally, but the UI and AI context expose only derived windows: time range, recurrence, average stress, high-stress minutes, impact score, and short reasons. Do not send raw stress samples to AI.

Grappling note: BJJ/grappling sessions are auto-detected from Garmin activity name/type terms (`bjj`, `jiu-jitsu`, `grappling`, `wrestling`, etc.). For matched activities, sync stores raw `activity_details:<activity_id>` and `activity_hr_zones:<activity_id>` payloads. The dashboard computes rounds, recovery, high-zone time, mat stress cost, classification, and next-day impact from those compact derived metrics; do not send raw HR traces to AI.

## The `dig()` pattern (most important thing to know)

Garmin's internal API field names are **best-effort and undocumented** — Garmin changes them without notice, and they were not all live-tested in this build. `ingest.py` extracts values with `dig(obj, *paths)`, which tries several dot/index key-paths and returns the first that resolves (e.g. `dig(sleep, "dailySleepDTO.sleepScores.overall.value", "sleepScores.overall.value")`).

Every raw endpoint response is stored verbatim in the `raw_json` table. **When a dashboard column is empty, that's the workflow:** query `raw_json` for the relevant `date`/`endpoint`, find the real key path in the payload, and add it to the `dig()` call in `ingest.py`. All field-mapping logic is centralised there for exactly this reason.

## Config

`config.py` loads `.env` from the project root (`load_dotenv()` + `BASE_DIR` defaults). `.env.example` and `.gitignore` live at the root alongside it. `.env`, `.garmin_tokens/`, and `garmin.db` are gitignored and must never be committed.

## Constraints to respect

- **Unofficial Garmin access** via `garminconnect`/`garth`. Personal-use only; endpoints can break on Garmin's side.
- **AI gets summaries, not raw data.** Don't pipe raw time-series into `ai.py` — `analysis.summarize()` plus the capacity-envelope dict are the deliberate privacy boundary, and the user can inspect exactly what's sent.
- **Default model** is `claude-sonnet-4-6` (overridable via `ANTHROPIC_MODEL`).
