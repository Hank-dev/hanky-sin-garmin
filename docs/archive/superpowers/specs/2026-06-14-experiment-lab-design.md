# N-of-1 Experiment Lab — Design

**Date:** 2026-06-14
**Status:** Approved design, ready for implementation plan
**Builds on:** the SQLite layer (`db.py`), the pure analytics layer (`analysis.py`),
the AI boundary (`ai.py`), the cockpit renderers (`cockpit.py`), and the multipage
pattern (`pages/01_Strength.py`, `pages/02_Coach.py`).
**Part of:** the "a coach that knows me" vision. This is **sub-project 2 of 2**.
Sub-project 1 (persistent coach memory) is implemented. This lab is loosely
coupled to it: active experiments are surfaced to the coach, but findings are
NOT auto-written to memory (the user can hand-add a `pattern` on the Coach page).

## Goal

Turn the app into a personal **N-of-1 science lab**. The user declares a
before/after experiment ("magnesium before bed", "no caffeine after 3pm"),
chooses which recovery metrics to watch, and the lab compares a baseline window
to the intervention window and reports, per metric, a plain-language verdict with
a 95% confidence interval. The coach is aware of active experiments, and a
completed result can be interpreted by the AI in one click.

### In scope

- An `experiments` table in `db.py` with CRUD helpers (add / update / set-status /
  delete / load), following the `coach_memory` CRUD style.
- A pure `analysis.compute_experiment_result(experiment, daily, checkins)` that
  slices baseline vs intervention windows and returns per-metric stats + a
  polarity-aware verdict (no raw time-series leaves the function as output —
  only aggregates).
- A pure `analysis.summarize_active_experiments(experiments_df, daily)` producing
  a compact list for AI context.
- A small `analysis` metric catalog (key → label, source, polarity) shared by the
  page and the analyzer.
- AI integration: inject active experiments into `analyze`/`weekly_summary`/
  `answer_question` (reusing the coach-memory `_memory_block` injection pattern),
  plus a new `ai.interpret_experiment(result)` call.
- A new **`pages/03_Experiments.py`**: create experiments, view active experiments
  with live partial results, mark complete, interpret with the coach, edit/delete,
  and a completed-experiments section.
- A pure `cockpit.experiment_result_card(result)` renderer.
- Tests for the analyzer, the active-experiment summarizer, the `db` CRUD, the
  result-card renderer, and the `interpret_experiment` no-key path.

### Non-goals (v1)

- **No A/B on-off design.** Before/after only.
- **No explicit baseline date range.** Baseline is always the `baseline_days`
  immediately before `start_date`.
- **No result caching.** Results are always recomputed from `daily` so late
  Garmin backfill is reflected automatically.
- **No p-values or Cohen's d.** Plain verdict + 95% CI only (deliberate choice).
- **No auto-save of findings to coach memory** and **no dashboard peek card**.
- **No new third-party dependency.** numpy is available; scipy is NOT — the CI
  uses Welch's standard error with a built-in Student-t critical-value table.
- `ai.interpret_experiment`'s network path is **not** unit-tested (only the
  no-key path), consistent with `analyze`/`answer_question`/`suggest_memories`.

## Current state

- `db.py` has idempotent-upsert tables plus the id-keyed `coach_memory` CRUD
  (the precedent this table follows). Loaders return pandas DataFrames.
- `analysis.py` is pure (no I/O). `enrich_daily()` adds derived columns including
  `sleep_hours`; `build_coach_memory_digest()` is the compaction precedent.
  `import numpy as np` and `import pandas as pd` are at module top.
- `ai.py` has `_memory_block()` (a labeled-JSON injection helper used by
  `analyze`/`weekly_summary`) and threads `coach_memory` through
  `_question_payload`/`answer_question`. Prompts live here; model defaults to
  `config.ANTHROPIC_MODEL`; each call no-ops without `ANTHROPIC_API_KEY`.
- `cockpit.py` renders cards as pure HTML functions (`_collapse_html`, `_SPARK`,
  `html.escape`, `coach_memory_peek`, etc.).
- `pages/02_Coach.py` is the most recent multipage precedent (importlib.reload
  header, `cockpit.CSS`, `db.init_db()`, forms, `st.rerun()` after writes).
- `app.py` enriches `daily` via `analysis` and builds AI context in the main
  script body (outside the cached `load()`).

## Architecture

```
            user (create / edit / complete)                 ai.interpret_experiment(result)
                        │                                              ▲
                        ▼                                              │ (one-click, button)
   db.add_experiment / update_experiment / set_experiment_status / delete_experiment
                        │
                        ▼
                 experiments table ──load_experiments_df()──┐
                                                            ▼
   daily (enriched) + checkins ─► analysis.compute_experiment_result(exp, daily, checkins) [pure]
                                                            │ per-metric {means, delta, CI, n, verdict}
                                                            ▼
                              cockpit.experiment_result_card(result)  →  pages/03_Experiments.py

   active experiments ─► analysis.summarize_active_experiments(df, daily) [pure] ─► compact list
                                                            │
                                                            ▼
                  injected into ai.analyze / weekly_summary / answer_question (coach awareness)
```

### Components

1. **`experiments` table** *(db.py)*
   - Columns:
     ```
     id            INTEGER PRIMARY KEY AUTOINCREMENT
     name          TEXT NOT NULL
     hypothesis    TEXT
     metrics       TEXT NOT NULL          -- JSON list of metric keys
     baseline_days INTEGER NOT NULL DEFAULT 14
     start_date    TEXT NOT NULL          -- 'YYYY-MM-DD'
     end_date      TEXT                   -- nullable; null = ongoing
     status        TEXT NOT NULL DEFAULT 'active'  -- 'active'|'complete'|'archived'
     created_at    TEXT NOT NULL
     updated_at    TEXT NOT NULL
     ```
   - Helpers: `add_experiment(record) -> int` (json-encodes `metrics`, stamps
     timestamps), `update_experiment(id, fields)` (allowlist of editable fields,
     bumps `updated_at`, re-encodes `metrics` if present), `set_experiment_status(id, status)`,
     `delete_experiment(id)`, `load_experiments_df(status="active")` (status=None
     loads all; decodes `metrics` JSON back to a list per row).

2. **Metric catalog** *(analysis.py)*
   - `EXPERIMENT_METRICS`: an ordered list of dicts
     `{"key", "label", "source": "daily"|"checkin", "polarity": "higher"|"lower"}`.
   - Daily (`higher` better unless noted): `hrv_overnight_avg` (higher),
     `resting_hr` (lower), `sleep_hours` (higher), `sleep_score` (higher),
     `body_battery_high` (higher), `stress_avg` (lower).
   - Check-in: `energy` (higher), `pain` (lower), `fatigue` (lower).
   - A helper maps key → catalog entry; unknown keys are skipped defensively.

3. **`analysis.compute_experiment_result(experiment, daily, checkins=None) -> dict`** *(pure)*
   - Resolves windows from `start_date`, `baseline_days`, `end_date`:
     baseline = `[start - baseline_days, start - 1 day]`; intervention =
     `[start, end_date or latest daily date]`. Dates compared as `YYYY-MM-DD`.
   - For each metric key in `experiment["metrics"]`: pulls the non-null series for
     each window from `daily` (or from `checkins` for check-in metrics, joined by
     date), then computes `n_before/n_after`, `mean_before/mean_after`,
     `delta = mean_after - mean_before`, and a 95% CI on the difference of means:
     - Welch SE `= sqrt(var_before/n_before + var_after/n_after)` (sample var, ddof=1).
     - `df` via Welch–Satterthwaite; `t_crit = _t_critical_975(df)` from a built-in
       table (df 1–30 explicit; 40/60/120/∞ → 2.021/2.000/1.980/1.960; pick the
       nearest df not exceeding, clamp to 1.960 for large df).
     - `ci_low/ci_high = delta ∓ t_crit * SE`.
   - **Verdict** (polarity-aware): `insufficient_data` if either period has
     `< MIN_DAYS` (5) usable points or `< 2` (variance undefined); else if the CI
     excludes 0 → `likely helped`/`likely hurt` depending on whether the delta
     moves the metric in the better direction for its polarity; else
     `no clear effect`.
   - Returns:
     ```
     {
       "experiment_id", "name", "status",
       "baseline_window": [start, end], "intervention_window": [start, end],
       "metrics": {
         "<key>": {"label", "polarity", "n_before", "n_after",
                   "mean_before", "mean_after", "delta",
                   "ci_low", "ci_high", "verdict"}, ...
       },
       "notes": ["short caveat strings, e.g. low-data flags"]
     }
     ```
   - Pure: shapes passed-in DataFrames; rounds/`None`-guards; no I/O.

4. **`analysis.summarize_active_experiments(experiments_df, daily) -> list[dict]`** *(pure)*
   - For `status == "active"` rows: `[{"name", "hypothesis", "metrics": [labels],
     "start_date", "days_running"}]` where `days_running = max(0, latest_daily_date
     - start_date)` in days. Caps the list length to bound token budget. Returns
     `[]` when none.

5. **AI integration** *(ai.py)*
   - `_experiment_block(active_experiments)`: same shape as `_memory_block` —
     returns `""` when empty, else a labeled JSON block. `analyze` and
     `weekly_summary` gain an `active_experiments: list | None = None` argument and
     append `_experiment_block(...)`. `_question_payload`/`answer_question` gain an
     `active_experiments` key/arg (defaulting to `[]`). One sentence added to the
     three system prompts: *the athlete may be running experiments; factor them in
     and avoid attributing changes to an intervention beyond what the data shows.*
   - `ai.interpret_experiment(result, model=None) -> str`: no key → italic note;
     else a new `INTERPRET_SYSTEM` prompt produces a short plain-language read of
     the **computed result dict** with explicit N-of-1 caveats (confounding,
     baseline drift). `max_tokens ≈ 600`. Network path untested.

6. **`cockpit.experiment_result_card(result) -> str`** *(pure HTML)*
   - Header (name + windows), then a row per metric: `mean_before → mean_after`,
     the delta with its `[ci_low, ci_high]`, and a verdict pill colored by
     outcome (`likely helped` positive, `likely hurt` negative, `no clear effect`/
     `insufficient_data` neutral). All text via `html.escape`; wrapped in
     `_collapse_html`. Empty/`insufficient_data` states render a note.

7. **`pages/03_Experiments.py`** *(new page, mirrors `pages/02_Coach.py`)*
   - Header idiom (importlib.reload, `cockpit.CSS`, `db.init_db()`). Loads
     `daily = analysis.enrich_daily(db.load_daily_df())` and
     `checkins = db.load_checkins_df()` (enriched `daily` is required for
     `sleep_hours`).
   - **New experiment** form: name, hypothesis, metric multiselect (from
     `analysis.EXPERIMENT_METRICS` labels), `baseline_days` (default 14),
     `start_date` (default today), optional `end_date` → `db.add_experiment(...)`.
   - **Active experiments**: for each, render `cockpit.experiment_result_card(
     analysis.compute_experiment_result(exp, daily, checkins))`; buttons
     **Mark complete** (`set_experiment_status(id, "complete")`), **Interpret with
     coach** (`ai.interpret_experiment(result)`, shown inline), edit, delete.
   - **Completed experiments**: collapsed section with final result cards.

### Data flow

`db.load_experiments_df() → [per active exp] analysis.compute_experiment_result(
exp, enriched_daily, checkins) → cockpit.experiment_result_card → page`. AI:
`summarize_active_experiments(df, daily) → injected into ai.analyze/weekly_summary/
answer_question`. Interpretation: `result → ai.interpret_experiment`.

### Edge cases

- **No experiments:** page shows an empty prompt; `summarize_active_experiments`
  returns `[]`; AI context unchanged.
- **Sparse window** (either period `< 5` usable points): per-metric
  `insufficient_data` verdict; a note explains; no crash.
- **Zero variance / `n < 2`:** `insufficient_data` (CI undefined).
- **`end_date` null or in the future:** intervention end = latest daily date.
- **`baseline_days` exceeds available history:** baseline simply has fewer points
  (possibly insufficient) — handled by the verdict, not an error.
- **Unknown metric key in `metrics`:** skipped defensively.
- **No `ANTHROPIC_API_KEY`:** interpretation returns a note; injection is a no-op.
- **Streamlit cache:** experiments are loaded outside `@st.cache_data`; writes
  call `st.rerun()`.

### Testing

`tests/test_experiment_lab.py`:
- `compute_experiment_result()` over a synthetic enriched `daily` frame:
  correct window selection; means/delta; CI excludes/!excludes 0 mapping to the
  right verdict; polarity (e.g. a drop in `resting_hr` → `likely helped`, a drop
  in `hrv_overnight_avg` → `likely hurt`); `insufficient_data` for short windows;
  a check-in metric (e.g. `energy`) sourced from `checkins`.
- `_t_critical_975()` returns sane values (e.g. df 1 ≈ 12.71, df 10 ≈ 2.23,
  large df → 1.96).
- `summarize_active_experiments()` — active-only, `days_running`, label mapping,
  cap, `[]` on empty.
- `db` experiments CRUD round-trip incl. `metrics` JSON encode/decode and
  `set_experiment_status`.
- `cockpit.experiment_result_card()` — renders each verdict, escapes text.
- `ai.interpret_experiment()` no-key path returns the note.

The `ai.interpret_experiment` network path is left untested, matching the other
AI calls.
