# Strength Training Logger — Phase 1 Design (Foundation & Logger)

**Date:** 2026-06-05
**Status:** Approved design, ready for implementation plan
**Scope:** Phase 1 of 2. Phase 2 (strength standards, muscle-balance asymmetry,
readiness-vs-performance correlation, AI integration) is a separate spec built
on top of this one.

## Goal

Add a "Strong"-style strength-training logger to the Garmin Coach app: a full
live workout logger with an exercise library and saved routines, estimated 1RM
tracking, and a Garmin readiness snapshot stamped on every session. It lives on
a dedicated Streamlit page alongside the recovery cockpit and follows the
existing module split exactly (`db.py` persistence, `analysis.py` pure
analytics, `ingest.py` Garmin mapping, `app.py`/`cockpit.py` UI).

### In scope (Phase 1)

- Exercise library (seeded + user-added custom exercises).
- Saved routines / templates.
- Live workout logging via `st.session_state`: start workout (blank or from a
  routine), add exercises, log sets (reps × weight × optional RPE), mark sets
  complete, finish.
- Estimated 1RM per working set (Epley default) and per-exercise 1RM trend / PR
  detection.
- Bodyweight + body-composition syncing from Garmin (with manual override).
- Athlete profile (sex, birth year, height) pulled from Garmin (overridable via
  `.env`).
- Readiness snapshot: each session is stamped with that day's Garmin readiness
  metrics at save time.
- Session history view with per-exercise 1RM trend chart.
- Tests targeting the pure `analysis.py` functions plus light `db` idempotency.

### Explicitly deferred to Phase 2

- Strength standards (Untrained → Elite, percentile vs population norms).
- Muscle-balance asymmetry (movement-pattern ratios + left:right).
- Readiness-vs-performance correlation analytics.
- AI integration (strength summary into `summarize()` → readiness report + Q&A).

### Non-goals (this build)

- lb display toggle (kg only for now; you're on Europe/Oslo).
- Push notifications / background rest-timer alerts (timer is visual only).
- Multi-user / auth (app remains single-user, local).

## Units

All weights stored and displayed in **kilograms**. Garmin returns body weight in
grams; ingest divides by 1000.

## Architecture

The feature slots into the existing one-directional pipeline. New surfaces:

```
Garmin Connect ──ingest.py (weigh-ins + profile, dig() pattern)──▶ body_metrics, profile (db.py)
                                                                            │
strength logging (pages/01_Strength.py + st.session_state) ──▶ strength_sessions, strength_sets,
                                                                exercises, routines (db.py)
                                                                            │
                                  analysis.py (1RM, enrich, summaries — pure) ◀┘
                                                                            │
                          pages/01_Strength.py UI ◀──── cockpit.py render helpers (oxblood)
```

No new cross-module dependencies that violate the existing boundaries:
`analysis.py` stays I/O-free; `ai.py` is untouched in Phase 1; Garmin sync never
writes to the strength tables and never overwrites manual body-metric rows.

## Section 1 — Data model (`db.py`)

All tables created in `SCHEMA`, all writes idempotent upserts, all loaders return
pandas DataFrames — same conventions as `daily_metrics` / `daily_checkins`. New
columns added to existing-DB tables via the same `ALTER TABLE` backfill loop
already in `init_db()`.

### `exercises` — the library

| column | type | notes |
|---|---|---|
| `exercise_id` | TEXT PK | slug, e.g. `back-squat` |
| `name` | TEXT | e.g. `Back Squat` |
| `category` | TEXT | barbell / dumbbell / machine / bodyweight / cable |
| `movement_pattern` | TEXT | squat / hinge / horizontal_push / vertical_push / horizontal_pull / vertical_pull / lunge / carry / core / isolation — stored now, consumed by Phase 2 |
| `primary_muscle` | TEXT | e.g. quads, chest |
| `is_unilateral` | INTEGER | 0/1 — enables per-side (left/right) logging |
| `is_bodyweight` | INTEGER | 0/1 — load = bodyweight + added weight |
| `is_main_lift` | INTEGER | 0/1 — flags lifts that will get standards in Phase 2 |
| `is_custom` | INTEGER | 0/1 — user-added vs seeded |
| `created_at` | TEXT | default `datetime('now')` |

Seeded with a starter set of common lifts (squat, bench, deadlift, OHP, barbell
row, front squat, pull-up, dip, RDL, lunge, etc.). Users can add custom
exercises (`is_custom=1`). Re-seeding is idempotent (upsert on `exercise_id`) and
must not overwrite a user's edits to a seeded exercise — seed only inserts rows
that do not already exist.

### `routines` + `routine_exercises` — saved templates

`routines`: `routine_id` PK, `name`, `notes`, `created_at`, `updated_at`.

`routine_exercises`: PK (`routine_id`, `position`); columns `exercise_id`,
`target_sets` INTEGER, `target_reps` INTEGER, `target_weight` REAL (nullable).
`position` gives display order.

### `strength_sessions` — one row per workout

| column | type | notes |
|---|---|---|
| `session_id` | TEXT PK | uuid4 |
| `date` | TEXT | `YYYY-MM-DD` local — joins to `daily_metrics` |
| `started_at` | TEXT | ISO local datetime |
| `ended_at` | TEXT | ISO local datetime |
| `routine_id` | TEXT | nullable, if started from a template |
| `name` | TEXT | e.g. "Push Day" |
| `bodyweight_kg` | REAL | snapshot at save (from `body_metrics`, forward-filled) |
| `notes` | TEXT | |
| `readiness_score` | REAL | denormalized snapshot ↓ |
| `readiness_level` | TEXT | |
| `hrv_status` | TEXT | |
| `hrv_overnight_avg` | REAL | |
| `body_battery_start` | REAL | |
| `sleep_score` | REAL | |
| `resting_hr` | REAL | |
| `acwr` | REAL | |
| `updated_at` | TEXT | default `datetime('now')` |

The readiness block is a **denormalized point-in-time snapshot**, copied in at
save so it stays stable even if daily metrics are later recomputed. Derived
performance values (tonnage, est-1RM, PRs) are NOT stored here — they're computed
in `analysis.py`.

### `strength_sets` — one row per set

| column | type | notes |
|---|---|---|
| `set_id` | TEXT PK | uuid4 |
| `session_id` | TEXT | FK → strength_sessions |
| `exercise_id` | TEXT | FK → exercises |
| `position` | INTEGER | exercise order within session |
| `set_index` | INTEGER | set number within exercise (1,2,3…) |
| `side` | TEXT | `both` (default) / `left` / `right` (unilateral) |
| `reps` | INTEGER | |
| `weight_kg` | REAL | added load (for bodyweight lifts, added on top of BW) |
| `rpe` | REAL | nullable |
| `is_warmup` | INTEGER | 0/1 |
| `completed` | INTEGER | 0/1 — planned vs done in the live flow |
| `logged_at` | TEXT | |

Sets store **raw reps/weight only**. Est-1RM, tonnage, and PRs are derived in
`analysis.py`, honoring the "no derived data in db" rule.

### `body_metrics` — bodyweight / composition from Garmin

`date` PK, `weight_kg`, `bmi` (nullable), `body_fat_pct` (nullable),
`muscle_mass_kg` (nullable), `body_water_pct` (nullable), `bone_mass_kg`
(nullable), `source` (`garmin` | `manual`), `updated_at`.

**Manual-protection rule:** a Garmin sync writes `source='garmin'` rows but must
NOT overwrite a row whose existing `source='manual'`. The upsert checks the
current source before clobbering (same spirit as Garmin syncs never overwriting
check-ins). A manual override always wins until the user clears it.

### `profile` — single-row athlete profile

One row (`id` PK = 1): `sex` (`male`/`female`/null), `birth_year` INTEGER,
`height_cm` REAL, `source` (`garmin` | `manual`), `updated_at`. Populated from
the Garmin user profile during sync; `.env` values (if set) override. Phase 1
only consumes bodyweight; `sex`/`birth_year` are pulled in the same call so
Phase 2 standards have them ready. A `.env`-provided value is treated as
`source='manual'` and is not overwritten by Garmin.

### Loaders

`load_exercises_df()`, `load_routines_df()` / `load_routine_exercises_df()`,
`load_strength_sessions_df()`, `load_strength_sets_df()`, `load_body_metrics_df()`,
`load_profile()` (returns a dict or single-row). Upserts:
`upsert_exercise`, `upsert_routine`, `upsert_routine_exercise`,
`upsert_strength_session`, `upsert_strength_set`, `delete_strength_set`,
`upsert_body_metric`, `upsert_profile`. A `seed_exercises()` helper inserts the
starter library on `init_db()` (insert-if-absent).

## Section 2 — Garmin ingest (`ingest.py` + `sync.py`)

A new sync step following the **`dig()` pattern** exactly — Garmin field names are
best-effort and undocumented, every response is stored verbatim in `raw_json`,
and empty columns are fixed by inspecting `raw_json` and adding the real key path.

- **Weigh-ins / body composition** for the date range. The exact
  `garminconnect` method name varies by version (`get_body_composition`,
  `get_weigh_ins`, `get_daily_weigh_ins`); resolve at call time and store the
  response under `raw_json` endpoint `body_composition` (keyed by date).
  `dig()` out `weight` (grams → /1000 = `weight_kg`), `bodyFat`, `muscleMass`,
  `bodyWater`, `boneMass`, `bmi` into `body_metrics` with `source='garmin'`,
  respecting the manual-protection rule.
- **User profile** once per sync. Store under `raw_json` endpoint
  `user_profile`; `dig()` out gender, birth date (→ `birth_year`), and height
  (→ `height_cm`) into `profile` with `source='garmin'` (not overwriting `.env`
  /manual values).
- Wire both into `sync.py`'s flow. Weigh-ins iterate the sync date range (or a
  single range call if the endpoint supports it); profile is fetched once.

**Bodyweight resolution for a session:** look up `body_metrics` for the session
`date`; if absent, forward-fill from the most recent prior weigh-in. The
resolved value is snapshotted onto `strength_sessions.bodyweight_kg`.

## Section 3 — Analysis layer (`analysis.py`, pure, no I/O)

- **`estimate_1rm(weight, reps, formula="epley")`** — Epley default
  (`1RM = weight · (1 + reps/30)`); Brzycki available
  (`weight · 36/(37 − reps)`); `reps == 1` → `weight`; `reps <= 0` → None.
- **`enrich_strength_sets(sets_df, sessions_df, exercises_df)`** — adds
  `effective_load_kg` (for `is_bodyweight` lifts: the session's snapshot
  `bodyweight_kg` + added `weight_kg`; else `weight_kg`), `est_1rm_kg` per
  non-warmup set, and a clean warmup flag. Uses `sessions_df.bodyweight_kg` (the
  stable per-session snapshot) so historical loads don't shift when weight
  changes — `body_metrics` is only read at save time and for the bodyweight UI.
- **`summarize_sessions(sessions_df, sets_df, exercises_df)`** — per session:
  total tonnage (Σ reps·effective_load over working sets), set count, top
  working set and best est-1RM per exercise.
- **`compute_pr_timeline(sets_df, sessions_df, exercises_df)`** — best est-1RM
  per exercise over time with a running-max PR flag (drives "new PR" in the UI).
- **`readiness_snapshot_from_daily(daily_row)`** — pure dict builder mapping an
  enriched daily-metrics row → the eight snapshot fields. `app.py`/the page does
  the DB read + write; the field-selection logic stays pure and unit-testable.

All functions are I/O-free, matching `compute_acwr` / `compute_grappling_sessions`.

## Section 4 — Live-logger UI (`pages/01_Strength.py` + `cockpit.py`)

- **Multipage move:** `app.py` remains the recovery cockpit (landing page). The
  logger lives in a new `pages/01_Strength.py`. Streamlit auto-lists `pages/`
  entries in the sidebar. New render helpers added to `cockpit.py` in the
  existing oxblood design language (exercise picker, set rows, session summary
  card, readiness badge, history list, 1RM trend chart) — pure HTML/Plotly that
  take plain values; the page wires the Streamlit widgets.
- **Live flow (`st.session_state`):** Start workout (blank or from a routine) →
  add exercises from the catalog or add a custom one → log set rows (reps,
  weight, RPE; mark complete; unilateral lifts show left/right rows) → running
  tonnage / top est-1RM update on each rerun → **Finish** persists the session +
  sets, snapshots readiness (`readiness_snapshot_from_daily` over the enriched
  daily row for today) and bodyweight, then clears the active-session state.
- **Rest timer — honest constraint:** Streamlit's rerun model makes a
  server-side ticking clock awkward, so the timer is a small **client-side JS
  countdown** rendered via `st.components.v1.html`, running in the browser
  independent of reruns. Visual only — no push notifications. Optional auto-start
  when a set is marked complete.
- **History:** list past sessions (date, name, tonnage, top lifts, readiness
  badge); expand to view sets; per-exercise 1RM trend chart (Plotly, dark). The
  readiness badge reads the session's denormalized snapshot, not live metrics.
- **Bodyweight:** shown from `body_metrics`; a manual-override number input
  writes a `source='manual'` row for the chosen date.

## Section 5 — Testing

- **`tests/test_strength_analysis.py`** (pure functions): `estimate_1rm`
  (Epley/Brzycki, `reps==1`, bodyweight loads, invalid reps), `enrich_strength_sets`
  (effective load for bodyweight vs barbell, warmup exclusion),
  `summarize_sessions` (tonnage + top set), `compute_pr_timeline` (PR flag on a
  rising then plateauing series), `readiness_snapshot_from_daily` (field mapping,
  missing/None handling).
- **`db` idempotency test:** upsert a session/set twice → one row; a Garmin
  `body_metrics` write does NOT overwrite a `manual` row; `seed_exercises()` run
  twice leaves seeded rows and any user edits intact.
- **Optional ingest-mapping test:** a captured raw weigh-in payload fixture locks
  the `dig()` paths (grams → kg). No live Garmin network in any test.

## Risks / open questions (non-blocking)

- **Garmin weigh-in availability:** weight data may be sparse or absent; the
  manual-override path and forward-fill make the feature usable regardless. The
  exact `dig()` key paths are confirmed post-implementation by inspecting the
  first real `raw_json` payload.
- **`garminconnect` method names** for weigh-ins/profile vary by version —
  resolved defensively at call time, matching how the rest of the client is
  written.
- **Streamlit live-logging ergonomics:** rapid set entry across reruns needs
  care with `session_state` keys; covered in the implementation plan.

## Definition of done (Phase 1)

1. New tables + loaders/upserts in `db.py`, with manual-protection on
   `body_metrics` and idempotent `seed_exercises()`.
2. Garmin weigh-in + profile ingest wired into `sync.py`, raw stored, `dig()`
   mapping in place.
3. Pure `analysis.py` strength functions implemented and unit-tested.
4. `pages/01_Strength.py` live logger + history working, with `cockpit.py` render
   helpers in the oxblood language, readiness snapshot stamped on save.
5. Tests pass (`pytest`); no live network in tests.
