# Strength Logger — Phase 2 Design (Intelligence)

**Date:** 2026-06-05
**Status:** Approved design, ready for implementation plan
**Builds on:** Phase 1 (`docs/superpowers/specs/2026-06-05-strength-training-logger-phase1-design.md`,
merged to `master`). Phase 2 adds analytics + AI on top of the Phase 1 data; it
introduces **no new DB tables**.

## Goal

Turn the logged strength data into insight: grade lifts against population
**standards**, surface muscle-**balance / asymmetry**, **correlate** Garmin
readiness with lifting performance, and feed a compact strength summary to the
**AI coach**. Everything follows the Phase 1 module split — a pure-data
reference module, pure functions in `analysis.py`, render helpers in
`cockpit.py`, a new "Insights" tab on the Strength page, and AI wiring in
`ai.py` + `app.py`.

### In scope (Phase 2)

- Strength standards: per main lift, a level (Untrained → Elite) + interpolated
  percentile, graded by sex + bodyweight against a built-in ratio table. No age
  adjustment.
- Muscle balance: cross-movement strength ratios flagged against target ranges,
  **and** left-vs-right percentage difference for unilateral lifts logged per
  side.
- Readiness-vs-performance correlation: bucket sessions by their stored
  readiness snapshot and compare normalized performance, gated until enough
  sessions exist.
- AI integration: a compact, raw-data-free strength summary threaded into
  `ai.answer_question` (which powers both "Analyse my health" and the chat) and
  `ai.analyze`.
- A new "Insights" tab on the Strength page rendering the three analyses.
- Tests for the pure functions + an AppTest smoke for the tab.

### Non-goals

- No age/Masters adjustment of standards (graded against adult/open standards).
- No new DB tables or schema changes; reads Phase 1 data only.
- No raw set/time-series data sent to the AI (privacy boundary preserved).
- Bodyweight-banded absolute standards (the ratio table is the deliberate
  accuracy-for-effort choice; documented as an approximation).

## Data dependencies (all from Phase 1)

- `profile` — `sex`, `birth_year` (age not used in Phase 2), `height_cm`.
- `body_metrics` — current bodyweight (forward-filled).
- `strength_sessions` — per-session readiness snapshot (`readiness_score`, …),
  `bodyweight_kg`, `date`.
- `strength_sets` — reps / weight / `side` / `is_warmup` / `completed`.
- `exercises` — `movement_pattern`, `is_main_lift`, `is_unilateral`,
  `is_bodyweight`.
- `analysis.compute_pr_timeline` (Phase 1) → best est-1RM per exercise; the
  per-exercise max is the "current 1RM" all Phase 2 analytics consume.

## Architecture

```
strength_standards.py (STANDARDS, BALANCE_TARGETS, ASYMMETRY_FLAG_PCT — pure data)
        │
analysis.py (pure):
  best_1rm_by_exercise (from compute_pr_timeline)
    ├─ compute_strength_standards(...)        ─┐
    ├─ compute_balance(...)                     ├─▶ summarize_strength(...) ─┐
    └─ compute_readiness_performance(...)      ─┘                            │
        │                                                                    ▼
  pages/01_Strength.py "Insights" tab ◀── cockpit.py panels        ai.py answer_question/analyze
                                                                             ▲
                                                  app.py load() builds summary ┘
```

`analysis.py` stays I/O-free. No raw time-series leaves the analytics layer.

## Section 1 — Reference data module (`strength_standards.py`)

Pure data, no imports (mirrors `strength_catalog.py`).

- **`LEVELS`** = `("Untrained", "Novice", "Intermediate", "Advanced", "Elite")`.
- **`LEVEL_PERCENTILE_BANDS`** — maps each level to a `(low, high)` percentile
  band: Untrained `(0, 20)`, Novice `(20, 50)`, Intermediate `(50, 80)`,
  Advanced `(80, 95)`, Elite `(95, 100)`.
- **`STANDARDS`** — `{sex: {exercise_id: (novice, intermediate, advanced, elite)}}`
  where each value is the minimum **lift ÷ bodyweight** ratio to reach that
  level; below `novice` = Untrained. Covers the five main lifts (`back-squat`,
  `bench-press`, `deadlift`, `overhead-press`, `barbell-row`) for `male` and
  `female`. Values are documented as approximate (StrengthLevel/ExRx-style).
- **`BALANCE_TARGETS`** — list of `{numerator, denominator, label, low, ideal,
  high, reason}` cross-movement ratio targets, e.g.:
  - bench:squat — `low 0.5, ideal 0.66, high 0.8` ("upper vs lower push")
  - overhead-press:bench — `low 0.5, ideal 0.6, high 0.7` ("vertical vs horizontal push")
  - barbell-row:bench — `low 0.8, ideal 0.9, high 1.05` ("horizontal pull vs push")
  - deadlift:squat — `low 1.1, ideal 1.2, high 1.35` ("posterior vs anterior chain")
- **`ASYMMETRY_FLAG_PCT`** = `10.0` — flag a unilateral lift when
  `|L−R| / max(L,R) · 100` exceeds this.

(Exact threshold numbers are finalized in the implementation plan; this section
fixes the structure and the level/percentile mapping.)

## Section 2 — Strength standards (`analysis.py`, pure)

**`compute_strength_standards(best_1rm_by_exercise, profile, bodyweight_kg)`**

- `best_1rm_by_exercise`: `{exercise_id: best_est_1rm_kg}` (caller derives this
  from `compute_pr_timeline`).
- If `profile` lacks a usable `sex` (`male`/`female`) or `bodyweight_kg` is
  missing/≤0 → return `{"status": "need_profile", "missing": [...]}`.
- For each main lift present in `STANDARDS[sex]` **and** in
  `best_1rm_by_exercise`: `ratio = est_1rm / bodyweight`; find the level whose
  threshold it meets; interpolate a percentile within that level's
  `LEVEL_PERCENTILE_BANDS` entry using the ratio's position between the level's
  lower and next threshold (Elite extrapolates toward 100, capped). Emit
  `{exercise_id, name, est_1rm_kg, ratio, level, percentile}`.
- **Overall**: mean percentile across available lifts → overall `level` (band the
  mean falls into) + `percentile`.
- Returns `{"status": "ok", "lifts": [...], "overall": {...}, "graded_lifts": n}`.
  Unlogged main lifts are omitted (UI shows "log X").
- Pure; deterministic; unit-tested at the level boundaries.

## Section 3 — Balance / asymmetry (`analysis.py`, pure)

**`compute_balance(best_1rm_by_exercise, sets_df, exercises_df)`** returns
`{"ratios": [...], "left_right": [...]}`:

- **ratios** — for each `BALANCE_TARGET` where both `numerator` and
  `denominator` lifts are in `best_1rm_by_exercise`: `ratio = num_1rm /
  den_1rm`; `status` = `ok` if `low ≤ ratio ≤ high`, else `under`/`over`;
  `weak_side` names the lagging lift; include `{label, ratio, low, ideal, high,
  status, weak_side, reason}`. Targets with a missing lift are skipped (UI lists
  them as "needs both lifts logged").
- **left_right** — from `sets_df` joined to `exercises_df` for `is_unilateral`
  lifts, consider completed non-warmup sets with `side` in (`left`, `right`).
  Per exercise compute the best est-1RM per side (reuse `estimate_1rm`); if both
  sides present, `diff_pct = |L−R| / max(L,R) · 100`, `flagged = diff_pct >
  ASYMMETRY_FLAG_PCT`, `stronger_side`. Emit `{name, left_1rm_kg, right_1rm_kg,
  diff_pct, flagged, stronger_side}`.
- Pure; empty/missing inputs return empty lists, never raise.

## Section 4 — Readiness vs performance (`analysis.py`, pure)

**`compute_readiness_performance(sessions_df, sets_df, exercises_df,
min_sessions=8)`**

- Per session, compute a **normalized performance score**: for each working
  exercise that day, `day_best_est_1rm / all_time_best_est_1rm` for that
  exercise; average across the day's working exercises → `rel_perf` (≈1.0 means
  "at your best", <1 means "below"). Sessions with no working sets are excluded.
- Keep only sessions with a non-null `readiness_score` snapshot. If fewer than
  `min_sessions` remain → `{"status": "insufficient", "have": k, "need":
  min_sessions}`.
- Bucket by readiness: **Low** `<50`, **Med** `50–75`, **High** `>75`. Per
  bucket: `n`, `avg_rel_perf`, `pr_rate` (fraction of sessions with a PR that
  day), `avg_tonnage`.
- Also a Pearson-style correlation coefficient between `readiness_score` and
  `rel_perf` across qualifying sessions, plus a one-line `insight` (e.g. "you
  hit your best work on higher-readiness days").
- Returns `{"status": "ok", "buckets": {...}, "correlation": r, "insight":
  str, "n": k}`.
- Pure; the all-time-best lookup reuses `compute_pr_timeline`/`estimate_1rm`.

## Section 5 — AI integration (`analysis.py` → `ai.py` → `app.py`)

- **`analysis.summarize_strength(sessions_df, sets_df, exercises_df, profile,
  bodyweight_kg, lookback_days=28)`** — compact, raw-data-free dict:
  - `recent`: sessions in last `lookback_days`, total tonnage, sessions/week.
  - `standards`: overall level/percentile + per-main-lift level (from
    `compute_strength_standards`).
  - `balance_flags`: the `under`/`over` ratios + flagged left/right entries only.
  - `readiness_link`: the correlation status + headline (from
    `compute_readiness_performance`).
  - `recent_prs`: list of `{exercise, est_1rm_kg, date}` from the last
    `lookback_days`.
  - Contains **no** raw set rows or time-series.
- **`ai.py`**:
  - `answer_question(..., strength: dict | None = None)` — adds
    `strength_profile` to the JSON payload; `QUESTION_SYSTEM` extended with a
    short clause on reasoning about strength standards, balance, and lifting
    load alongside recovery.
  - `analyze(summary, strength: dict | None = None, model=None)` — appends the
    strength block to its message (for completeness; `app.py` currently routes
    through `answer_question`).
- **`app.py`** `load()` — additionally load `strength_sessions`,
  `strength_sets`, `exercises`, `profile`, `body_metrics`; compute
  `strength_summary = analysis.summarize_strength(...)`; pass `strength=
  strength_summary` into the existing `ai.answer_question(...)` call and add it
  to `question_payload` (so the user can inspect exactly what is sent). The
  `load()` cache key is unchanged (still keyed on timezone; cache TTL applies).

## Section 6 — UI (`cockpit.py` + `pages/01_Strength.py`)

- A 4th tab, **"Insights"**, on the Strength page: `tab_log, tab_history,
  tab_insights, tab_body = st.tabs([...])`.
- New `cockpit.py` render helpers (pure HTML/Plotly, oxblood tokens):
  - `strength_standards_panel(standards)` — overall level/percentile badge +
    per-lift rows showing level and a percentile bar; `need_profile` and "log X"
    empty states.
  - `strength_balance_panel(balance)` — ratio rows with the value, the target
    range, an ok/under/over chip and weak-side note; a left/right section with
    per-exercise diff bars and flags.
  - `strength_correlation_panel(corr)` — when `ok`, a Plotly bar of readiness
    bucket vs `avg_rel_perf` (+ correlation/insight caption); when
    `insufficient`, a "N more sessions to unlock" message.
- The Insights tab loads sessions/sets/exercises/profile/bodyweight (reusing the
  page's existing loaders + `resolve_bodyweight`), derives
  `best_1rm_by_exercise` from `compute_pr_timeline`, runs the three analyses, and
  renders the panels.

## Section 7 — Testing

- **`tests/test_strength_standards.py`** (pure):
  - `compute_strength_standards`: a lift landing exactly on a level boundary;
    percentile interpolation within a band; `need_profile` when sex/bodyweight
    missing; unlogged lift omitted; overall aggregation.
  - `compute_balance`: a ratio inside vs outside its target range (status +
    weak_side); a missing-lift target skipped; left/right diff over/under the
    flag threshold; single-side data not flagged.
  - `compute_readiness_performance`: `insufficient` gate below `min_sessions`;
    correct bucketing and a positive correlation on a synthetic
    higher-readiness-→-better-performance series.
  - `summarize_strength`: shape + assert no raw set rows leak (no `set_id`/`reps`
    keys in the payload).
- **`tests/test_strength_cockpit.py`** (extend): the three new panels return
  strings/figures and handle empty/`need_profile`/`insufficient` inputs.
- **AppTest smoke**: the Insights tab renders on an empty DB (graceful empty
  states) and on a data-backed temp DB (standards + balance render; correlation
  shows the insufficient message with few sessions).

## Risks / open questions (non-blocking)

- **Standards accuracy**: ratio-based thresholds drift at bodyweight extremes;
  surfaced in the UI as an "approximate" caption. Numbers can be tuned in the
  data module without code changes.
- **Sparse data**: until the user logs the main lifts and accumulates sessions,
  standards show "log X", balance shows partial ratios, and correlation shows the
  insufficient gate — all intended graceful states.
- **Performance metric choice**: normalized `rel_perf` (day-best ÷ all-time-best)
  is the chosen comparable-across-lifts metric; tonnage and PR-rate are reported
  alongside as secondary views.

## Definition of done (Phase 2)

1. `strength_standards.py` reference tables in place.
2. `analysis.py`: `compute_strength_standards`, `compute_balance`,
   `compute_readiness_performance`, `summarize_strength` — pure, unit-tested.
3. `ai.py`: `answer_question`/`analyze` accept and use `strength`; prompt updated.
4. `app.py`: builds and passes the strength summary; visible in `question_payload`.
5. `cockpit.py`: three Insights panels; `pages/01_Strength.py`: "Insights" tab.
6. Tests pass (`pytest`); AppTest smoke green; no raw set data sent to AI.
