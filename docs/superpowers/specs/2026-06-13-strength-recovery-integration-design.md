# Strength + Recovery Integration — Design

**Date:** 2026-06-13
**Status:** Approved design, ready for implementation plan
**Builds on:** the Health Lab recovery panel (`analysis._research_recovery_panel`),
the strength logger + analytics (`pages/01_Strength.py`, `analysis.py` strength
functions), the per-session recovery snapshot (`readiness_snapshot_from_daily`),
and the Insights tab.

## Goal

Tie Garmin-derived recovery to strength training, three ways:

1. **Day-type recommendation** — a banner in the strength logger: "Today is an
   **Intensity / Volume / Maintenance** day", driven by recovery, with a one-line
   rationale and concrete rep/load guidance.
2. **Performance vs recovery** — correlate PR rate and normalized est-1RM against
   recovery (and HRV / sleep / RHR), shown in Insights.
3. **Per-lift sensitivity** — flag lifts whose performance drops on
   poor-recovery days.

**Readiness signal:** reuse the Health Lab recovery score (HRV/RHR/sleep
z-deviations + flags), **inverted** so higher = readier — no second recovery
number in the app. Garmin's `training_readiness_score` is unused (it isn't
syncing).

### In scope

- A pure `analysis.recovery_readiness(daily, as_of=None)` factored out of the
  Health Lab recovery panel (shared `_recovery_risk` helper → one source of truth).
- `analysis.strength_day_type(daily)` mapping recovery zone → day-type +
  rationale + guidance, and a `cockpit.strength_day_type_banner(...)` renderer at
  the top of the **Log** tab.
- Stamp `recovery_score` + `recovery_zone` onto each session at **Finish** (two
  new `strength_sessions` columns + migration).
- Re-point `compute_readiness_performance` from the dead `readiness_score` to the
  stamped `recovery_score`, and add per-signal correlations vs the already-stored
  `hrv_overnight_avg`, `sleep_score`, `resting_hr`.
- `analysis.compute_lift_recovery_sensitivity(...)` + a Insights panel flagging
  recovery-sensitive lifts.
- Feed the recovery-performance + day-type into the AI strength context
  (`summarize_strength`).

### Non-goals

- **No new standalone recovery score** — reuse the Health Lab one (inverted).
- **No Garmin `training_readiness_score` dependency** (it isn't syncing).
- **No change to the Strong-style set-logging inputs** — day-type is advisory
  (label + guidance), it does not pre-fill targets.
- **No historical backfill** of recovery onto sessions — stamp at Finish only
  (there are 0 sessions today, so every future session is tagged).

## Current state

- `analysis._research_recovery_panel(df)` (part of
  `compute_health_research_panels(daily, acts, sleep_timing)["recovery"]`) emits
  `zone` (`green`/`yellow`/`red`), a 0–100 `risk_score`
  (`min(100, len(flags)*22 + streak*8 + max(0, suppressed_days-2)*3)`), and
  `flags`, using `_research_recovery_flags`, `_research_recovery_flag_count`,
  `_trailing_true_streak`.
- `readiness_snapshot_from_daily(daily_row)` returns 8 keys
  (`readiness_score`, `readiness_level`, `hrv_status`, `hrv_overnight_avg`,
  `body_battery_start`, `sleep_score`, `resting_hr`, `acwr`); `pages/01_Strength.py`
  `todays_readiness_snapshot(day)` builds it from the enriched daily frame and the
  Finish flow writes it onto the session row (`SESSION_COLS`).
- `compute_readiness_performance(sessions_df, sets_df, exercises_df,
  min_sessions=8, formula)` correlates day-best-1RM ÷ all-time-best vs
  `readiness_score`, Low/Med/High buckets — **currently inert** because
  `readiness_score` is never populated.
- Insights tab (`pages/01_Strength.py`) renders three panels: standards, muscle
  balance, and "Readiness vs performance" (`cockpit.strength_correlation_panel`).
- 0 strength sessions / 0 sets logged so far.

## Architecture

```
compute_health_research_panels ─┐ (shared math)
                                ▼
analysis._recovery_risk(df)  ── analysis.recovery_readiness(daily, as_of) ──┐
                                                                            │
              ┌──────────────────────────────┬──────────────────────────────┤
              ▼                               ▼                              ▼
  strength_day_type(daily)        Finish: stamp recovery_score/zone   (today's score)
              │                     onto strength_sessions row
              ▼                               │
  cockpit.strength_day_type_banner            ▼
   (top of Log tab)             compute_readiness_performance(... recovery_score,
                                  + hrv_overnight_avg/sleep_score/resting_hr)
                                compute_lift_recovery_sensitivity(...)
                                              │
                                              ▼
                                Insights tab panels (correlation + per-lift flags)
                                              │
                                              ▼
                                  summarize_strength → AI coach context
```

### Components

1. **`analysis.recovery_readiness(daily, as_of=None) -> dict`** *(pure)*
   - Refactor: extract the risk/zone/flags computation from
     `_research_recovery_panel` into a shared `_recovery_risk(df)`; the panel and
     this function both call it (behavior of the Health Lab panel unchanged).
   - `as_of`: slice `daily` to rows `<= as_of` (default latest) before computing,
     so a session's stamp uses recovery known on its day.
   - Returns `{"status": "ready"|"no_data", "score": 100 - risk_score,
     "zone": "green"|"yellow"|"red", "flags": [...]}`.

2. **`analysis.strength_day_type(daily) -> dict`** *(pure)*
   - Calls `recovery_readiness`. Maps zone → `day_type`: **green→"Intensity",
     yellow→"Volume", red→"Maintenance"**; `no_data` → `day_type=None`.
   - Returns `{day_type, zone, score, rationale, guidance, status}`.
     - `guidance`: Intensity → "Work up to a heavy 3–5RM; 3–5 hard sets."
       Volume → "3–4 sets of 8–12 at a moderate load; leave 1–2 in reserve."
       Maintenance → "Light technique work ~60–70%; stop well short of failure."
     - `rationale`: cites the score and top 1–2 flags (or "recovery primitives in
       baseline").

3. **`cockpit.strength_day_type_banner(day_type: dict) -> str`** *(render)*
   - Card with the day-type, zone-colored accent, score, rationale, guidance.
   - `status == "no_data"` or `day_type is None` → a neutral "No recovery call
     today — train to feel" note. Wrapped in `_collapse_html`.
   - Rendered at the **top of the Log tab** in `pages/01_Strength.py`.

4. **Session recovery stamp** *(db + Finish flow)*
   - Add `recovery_score REAL`, `recovery_zone TEXT` to the `strength_sessions`
     schema and `SESSION_COLS`; extend `db.init_db()` to `ALTER TABLE
     strength_sessions ADD COLUMN ...` for existing DBs (mirroring the
     `daily_metrics` migration block).
   - In `todays_readiness_snapshot(day)`, also call `recovery_readiness(daily,
     as_of=day)` and merge `{"recovery_score", "recovery_zone"}` into the snapshot
     dict, so Finish persists them.

5. **`compute_readiness_performance` upgrade** *(pure)*
   - Key the correlation on `recovery_score` (stamped) instead of `readiness_score`.
   - Add a `signals` breakdown: for each of `recovery_score`,
     `hrv_overnight_avg`, `sleep_score`, `resting_hr` present on sessions, compute
     Pearson r vs `rel_perf` and Low/Med/High buckets (rel-1RM, PR rate, tonnage).
   - Keep `status`/`have`/`need` gating (`min_sessions=8`) and the headline
     `insight`. `strength_correlation_panel` updated to show the multi-signal view.

6. **`analysis.compute_lift_recovery_sensitivity(sessions, sets, exercises, formula, min_pairs=4) -> dict`** *(pure)*
   - Per exercise with enough paired data: mean normalized performance
     (day-best-1RM ÷ all-time-best) on **good days** (`recovery_zone == "green"`)
     vs **poor days** (`recovery_zone == "red"`); yellow days are excluded from
     this comparison. Reports the drop % and a `flag` when the drop ≥ ~7%. Returns
     ranked sensitive lifts + a `status` marker when sparse.
   - `cockpit.strength_lift_sensitivity_panel(...)` renders it in Insights.

7. **AI context** *(summarize_strength)*
   - Replace the inert `readiness_link` with the upgraded recovery-performance
     output; add `day_type` and the top recovery-sensitive lifts. Still
     summaries-only (privacy boundary intact).

### Data flow

`daily → recovery_readiness → {day_type banner now} + {recovery_score/zone stamped at Finish}`
`sessions(+recovery_score) × sets → compute_readiness_performance / compute_lift_recovery_sensitivity → Insights panels + AI`

### Edge cases

- **HRV/RHR/sleep missing today** → `recovery_readiness` returns `no_data`;
  banner shows the neutral note; nothing stamped.
- **< 8 recovery-tagged sessions** (the case today, 0) → correlation + sensitivity
  panels show "need more data"; Part 1 banner still works.
- **A session predating recovery stamping** (none today) → excluded from the
  `recovery_score` correlation; still counts for raw HRV/sleep/RHR signals if
  those snapshot fields exist.
- **All sessions one zone** (e.g. all green) → sensitivity needs both good and
  poor days; returns a "need varied recovery" marker rather than a flag.

### Testing

- `recovery_readiness`: inversion (`score == 100 - risk`), `as_of` slicing,
  `no_data`; and that `_research_recovery_panel` output is unchanged after the
  refactor (regression).
- `strength_day_type`: zone→day-type mapping for green/yellow/red and `no_data`.
- `compute_readiness_performance`: keys on `recovery_score`; per-signal `signals`
  block; gating.
- `compute_lift_recovery_sensitivity`: drop-% + flag on a synthetic
  good-vs-poor-day fixture; sparse/one-zone markers.
- `db` round-trip of the two new session columns + migration on a pre-existing DB.
- Renderers (`strength_day_type_banner`, sensitivity panel): section content +
  single-HTML-block (no blank lines) invariant.
- Finish-stamp + Insights wiring verified by import/run (Streamlit), not pytest.
