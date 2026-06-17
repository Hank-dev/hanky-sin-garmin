# Smart Session — Strength + Recovery Advisory — Design

**Date:** 2026-06-17
**Status:** Approved design, ready for implementation plan
**Builds on:** the Strong-style strength logger (`views/strength.py`), the strength
analytics (`analysis.py` 1RM/PR/standards/balance functions), the per-session
readiness snapshot (`analysis.readiness_snapshot_from_daily`), the Health Lab
recovery panel (`analysis._research_recovery_panel`), the AI boundary (`ai.py`),
the SQLite layer (`db.py`), the seed catalog (`strength_catalog.py`), and the
cockpit renderers (`cockpit.py`).

**Part of:** the "polished, production-quality alternative to Strong, but with AI
and fitness-data integration" vision. This is **Sub-project A of three**:

- **A — Smart Session (this spec):** recovery-aware, advisory linear-progression
  layer over the logger. Absorbs the full (approved-but-unbuilt)
  `2026-06-13-strength-recovery-integration` spec, which this document supersedes.
- **B — In-workout logging polish** (plate calc, warmup ramp, supersets,
  reorder): later, its own spec.
- **C — Progress & history surfaces** (calendar/streak, per-exercise history,
  volume-per-muscle, measurements, PR celebration, export): later, its own spec.

## Goal

Make the strength module *know how recovered you are* and *what you did last
time*, and turn that into clear, **advisory** guidance you log against by hand.
Nothing is auto-changed: the engine computes a suggested next target per main
lift and a recovery verdict for the day; you decide and log.

Concretely, three layers:

1. **Recovery signal (foundation).** One reusable recovery readiness signal
   (green/yellow/red zone + reasons), factored out of the Health Lab recovery
   panel so there is a single source of truth. Stamped onto each finished
   session.
2. **Linear-progression advisory.** Per main lift, a deterministic next-target
   suggestion (StrongLifts-style: hit all target reps → +increment; miss → hold;
   3 stalls → ~10% deload), shown inline in the logger with an **Apply** button.
3. **AI coach note.** One cached, natural-language sentence per workout that
   synthesizes the recovery verdict + the day's plan + recent strength trends.

### In scope

- **Data model:** add `increment_kg REAL` and `target_reps INTEGER` to the
  `exercises` table; add `recovery_score REAL` and `recovery_zone TEXT` to the
  `strength_sessions` table. Idempotent `ALTER TABLE … ADD COLUMN` migrations in
  `db.init_db()`. Seed per-main-lift increments/target-reps in
  `strength_catalog.py`.
- **`analysis.recovery_readiness(daily, as_of=None)`** — pure, factored out of
  `_research_recovery_panel` via a shared `_recovery_risk` helper (one source of
  truth). Returns zone (green/yellow/red), a 0–100 readiness value (inverted risk,
  higher = readier), and human-readable reason strings. No raw time-series.
- **`analysis.readiness_verdict(readiness)`** — maps the recovery signal to a
  day-type + chip: `green → "Push"`, `yellow → "Hold/Volume"`, `red → "Back off"`,
  with the top reasons. Thin wrapper so the UI/AI share one verdict shape.
- **`analysis.compute_progression_suggestion(exercise_id, sessions_df, sets_df,
  exercises_df, formula)`** — pure linear-progression state machine. Returns
  `{state, suggested_weight_kg, target_reps, last_weight_kg, stalls, reason}` or
  `None` (non-main-lift / no history).
- **Session stamping at Finish:** compute `recovery_readiness` for the session
  date and store `recovery_score` + `recovery_zone` alongside the existing
  snapshot.
- **Re-point `compute_readiness_performance`** from the dead `readiness_score`
  (Garmin `training_readiness_score`, which is null in 100% of rows) to the
  stamped `recovery_score`; add per-signal correlations vs the already-stored
  `hrv_overnight_avg`, `sleep_score`, `resting_hr`.
- **`analysis.compute_lift_recovery_sensitivity(sessions_df, sets_df,
  exercises_df, formula)`** — flag lifts whose normalized performance drops on
  low-recovery days; surfaced in the Insights tab.
- **AI:** `ai.coach_session_note(strength_summary, verdict, plan, model=None)` —
  one cached call per session start, degrades silently without an API key. Feed
  the recovery verdict + day-type into `analysis.summarize_strength` so the
  existing coach Q&A also sees it.
- **UI (`views/strength.py` + `cockpit.py`):** a recovery **verdict chip** in the
  active-workout header; a collapsible **coach-note** line; a per-main-lift
  **suggestion hint** with an **Apply** button; suggestion used as the default
  weight when a fresh main lift is added. A new **recovery-sensitivity** panel in
  Insights.
- **Tests:** unit tests for `recovery_readiness`, `readiness_verdict`,
  `compute_progression_suggestion` (all state transitions), and
  `compute_lift_recovery_sensitivity`.

### Non-goals

- **No auto-regulation of numbers.** Recovery never silently rewrites a weight.
  The verdict and suggestions are advisory; every input stays editable (this is
  the user's explicit choice — "advisory only").
- **No Garmin `training_readiness_score` dependency** — it is not syncing
  (0/22 rows populated). The derived `recovery_readiness` is the sole readiness
  source.
- **No standalone day-type banner.** The old 2026-06-13 spec proposed a banner at
  the top of the Log tab; this design instead carries the day-type inside the
  compact header **verdict chip** + coach note, to avoid a redundant surface.
- **No RPE/percentage/freestyle progression models** — linear only (the user's
  program). Accessories (non-main-lifts) get no suggestion, just the existing
  "previous" column.
- **No raw time-series to AI** — `summarize_strength` + the verdict dict remain
  the privacy boundary.
- **No historical backfill of `recovery_score` onto past sessions** — stamp at
  Finish only (consistent with the old spec; few/zero sessions exist today).
- Sub-projects **B** and **C** are out of scope here.

## Current state (what exists today)

- **Logger** (`views/strength.py`): live Strong-style logging with warmup toggle,
  per-set kg/reps, completed-check + auto rest timer, RPE, unilateral sides,
  exercise notes, a **Previous** column (`analysis.last_session_sets`), routines,
  custom exercises, History + Insights + Bodyweight tabs.
- **Analytics** (`analysis.py`): `estimate_1rm`, `enrich_strength_sets`,
  `summarize_sessions`, `compute_pr_timeline`, `compute_strength_standards`,
  `compute_balance`, `compute_readiness_performance`, `summarize_strength`,
  `readiness_snapshot_from_daily`.
- **Recovery scoring already exists** but only inside the Health Lab:
  `_research_recovery_panel` (`analysis.py:1435`) computes a green/yellow/red
  zone, a `risk_score`, and flags from HRV/RHR/sleep deviations. It is **not**
  reusable yet (not factored out, returns a UI-shaped dict).
- **Two latent issues this spec fixes:**
  - `compute_readiness_performance` and the per-session snapshot key off
    `readiness_score` ← Garmin `training_readiness_score`, which is **null in all
    22 daily rows**. The Insights "Readiness vs performance" panel is therefore
    effectively dead. Re-pointing to `recovery_score` revives it.
  - The `2026-06-13-strength-recovery-integration` spec is approved but **never
    implemented** (no `recovery_readiness`, `strength_day_type`, `recovery_score`
    column exist). This spec absorbs and supersedes it.

## Architecture & data flow

```
exercises (+increment_kg, +target_reps)  ─┐
strength_sessions + strength_sets ────────┼─▶ compute_progression_suggestion()  ─▶ per-lift {state, weight, reps, reason}
                                          │            (pure, analysis.py)
daily_metrics ─▶ enrich_daily ─▶ recovery_readiness() ─▶ readiness_verdict()  ─▶ {zone, day_type, value, reasons}
                                          │                       │
                                          │     ai.coach_session_note(summary, verdict, plan) ─▶ one cached sentence
                                          │                       │
                                  views/strength.py ◀── cockpit.py renderers (verdict chip, hint line, sensitivity panel)
                                          │
                  Finish ─▶ stamp recovery_score + recovery_zone on the session
```

Division of labor (matches the codebase's stated boundaries):

- **`analysis.py` (pure, testable, no I/O):** all numeric work — recovery signal,
  verdict mapping, progression state machine, recovery↔performance correlation,
  lift sensitivity.
- **`ai.py` (boundary):** only the one natural-language coach note; receives the
  already-summarized dicts, never raw sets.
- **`db.py`:** schema migration + the two new stamped columns.
- **`views/strength.py` + `cockpit.py`:** rendering and the Apply interaction.

Why deterministic core + thin AI note: the advice is *inline per exercise*, so it
re-renders on every Streamlit interaction — an LLM call per render is impossible.
Linear progression and zone banding are exactly the auditable math `analysis.py`
exists for. AI adds a single synthesized sentence where judgment helps, cached so
it costs one call per workout.

## Component 1 — Recovery signal (foundation)

**`analysis.recovery_readiness(daily, as_of=None) -> dict`** (pure)

- `daily` is the enriched daily-metrics frame (output of `enrich_daily`, the same
  frame the Health Lab uses). `as_of` selects the row (default: latest ≤ today);
  for session stamping, pass the session date.
- Reuse the existing zone logic by extracting a shared **`_recovery_risk(df,
  as_of)`** helper from `_research_recovery_panel`, returning
  `{risk_score, zone, flags, streak, suppressed_days, elevated_rhr_days,
  short_sleep_days}`. `_research_recovery_panel` is refactored to call it (no
  behavior change to the Health Lab — verified by leaving its output dict intact).
- `recovery_readiness` returns:
  ```python
  {
    "status": "ready" | "no_data",
    "zone": "green" | "yellow" | "red",
    "value": int,           # 0–100, inverted risk (100 - risk_score), higher = readier
    "reasons": [str, ...],  # e.g. "HRV suppressed 3 of last 14 nights"
  }
  ```
- `no_data` when none of HRV / RHR / sleep-duration is available (same gate as the
  panel's `status`).

**`analysis.readiness_verdict(readiness) -> dict`** (pure)

- Maps the recovery signal to the strength-facing verdict:
  ```python
  {
    "zone": "green"|"yellow"|"red",
    "day_type": "Push" | "Hold / volume" | "Back off",
    "value": int,
    "headline": str,        # short chip label, e.g. "Back off — recovery red"
    "reasons": [str, ...],  # top 1–3 reasons from recovery_readiness
  }
  ```
- `no_data` → a neutral `"Log normally"` verdict (chip shows "Recovery: learning").

## Component 2 — Linear-progression advisory

**`analysis.compute_progression_suggestion(exercise_id, sessions_df, sets_df,
exercises_df, formula="epley") -> dict | None`** (pure)

- Returns `None` if the exercise is not a main lift (`is_main_lift != 1`), has no
  `increment_kg`/`target_reps`, or has no prior working sets → the logger falls
  back to today's "Previous" behavior.
- Otherwise walk that lift's sessions newest-first (warmups excluded, only
  `completed == 1` working sets), grouped by session, and run the state machine on
  the **top working weight** of each session:

  | Condition on most-recent session at top weight `W` | State | Suggested |
  |---|---|---|
  | All working sets at `W` reached `target_reps` | `progress` | `W + increment_kg` |
  | Any working set short of `target_reps` | `hold` | `W` |
  | `hold` recorded for **3 consecutive** sessions at the same `W` | `deload` | `round_to_increment(W × 0.9)` |

- "All working sets reached target reps" = every non-warmup, completed set at the
  session's top weight has `reps >= target_reps`. (Sets below top weight are
  back-off/were lighter — ignored for the progression decision.)
- **Stall counting:** count consecutive prior sessions whose top weight equals the
  current `W` and which did not progress. At `stalls >= 3`, emit `deload` and the
  stall counter resets after a deload session (next session at the new weight
  starts fresh).
- `round_to_increment(x)` rounds to the nearest `increment_kg` (e.g. 90.0 for a
  2.5 increment).
- Returns:
  ```python
  {
    "state": "progress" | "hold" | "deload",
    "suggested_weight_kg": float,
    "target_reps": int,
    "last_weight_kg": float,
    "stalls": int,
    "reason": str,   # "all sets hit 5 reps at 100kg" / "missed reps last time" / "stalled 3× at 100kg"
  }
  ```

**Apply / pre-fill behavior**

- Inline hint per main lift renders the suggestion. An **Apply** button writes the
  suggested weight + `target_reps` into that exercise's working sets in the active
  state (creating default sets if none exist), exactly as if the user typed them.
  Advisory: every field stays editable afterward.
- When a **fresh main lift** is added to a workout, its first working set's default
  weight uses `suggested_weight_kg` (when a suggestion exists), instead of the
  current `20.0` / last-set copy.

## Component 3 — AI coach note

**`ai.coach_session_note(strength_summary, verdict, plan, model=None) -> str`**

- Inputs are already-summarized dicts: `strength_summary` from
  `analysis.summarize_strength`, the `readiness_verdict` dict, and `plan` (the
  list of per-main-lift suggestions for the day). No raw sets.
- Returns 1–2 sentences, e.g. *"Squat's stalled 3 sessions and HRV is low — hold
  100 kg and chase clean reps; everything else can progress."*
- Called **once** when a workout becomes active; cached in `st.session_state`
  keyed by `session_id`, with a manual "↻" refresh. Missing API key or any error
  → return `""` and the UI shows only the deterministic chip + hints.
- Also: extend `analysis.summarize_strength` to include the recovery verdict +
  day-type so the existing `ai.answer_question` coach Q&A can reason about recovery
  and progression without a second code path.

## Component 4 — Recovery ↔ performance analytics (Insights)

- **Re-point `compute_readiness_performance`:** replace the `readiness_score`
  source with the stamped `recovery_score`; keep the bucketed (Low/Med/High) view
  and correlation. Add per-signal correlations of normalized performance vs the
  stored `hrv_overnight_avg`, `sleep_score`, `resting_hr` (already on each
  session row).
- **`analysis.compute_lift_recovery_sensitivity(sessions_df, sets_df,
  exercises_df, formula) -> list[dict]`** (pure): for each main lift with enough
  paired sessions, compare normalized day-best e1RM on low-recovery
  (`recovery_zone in {red, yellow}`) vs green days; flag lifts with a meaningful
  drop. Returns `[{exercise, n, delta_pct, flagged, note}, ...]`, gated by a
  minimum sample size.
- Surface both in the existing Insights tab via `cockpit` renderers.

## Data model changes (`db.py` + `strength_catalog.py`)

- `exercises`: `+ increment_kg REAL`, `+ target_reps INTEGER` (NULL for
  accessories).
- `strength_sessions`: `+ recovery_score REAL`, `+ recovery_zone TEXT`.
- `db.init_db()`: idempotent migration — attempt each `ALTER TABLE … ADD COLUMN`
  inside a try/except that ignores "duplicate column name" (SQLite has no
  `ADD COLUMN IF NOT EXISTS`).
- `EXERCISE_COLS` / `SESSION_COLS` extended so the existing upserts carry the new
  fields.
- `strength_catalog.EXERCISE_SEED`: add `increment_kg` + `target_reps` to the five
  main lifts (default `increment_kg = 2.5`, `target_reps = 5`; deadlift may seed a
  larger increment — final defaults set during implementation). `seed_exercises`
  is insert-if-absent, so re-seeding will not clobber user edits; new columns on
  already-seeded rows are populated by a one-time backfill `UPDATE` for rows where
  the value is NULL and the exercise is a main lift.

## UI integration (`views/strength.py` + `cockpit.py`)

- **Verdict chip** in the active-workout header (near the Volume/Sets/Top-1RM
  stat row): colored by zone, shows `day_type` + top reason. New
  `cockpit.strength_recovery_chip(verdict)` renderer (reuse the existing badge
  styling vocabulary).
- **Coach note** line directly under the header: collapsible, populated from the
  cached `coach_session_note`; hidden entirely when empty.
- **Per-main-lift suggestion hint** under each main-lift title (between the title
  and the column header), e.g.
  `Suggested 102.5 × 5  ·  last 100×5×5 ✓  (+2.5)` /
  `Hold 100 × 5 — short last time` / `Deload 90 × 5 — stalled 3×`, plus a small
  **Apply** button. New `cockpit.strength_suggestion_hint(suggestion)` renderer;
  non-main-lifts render nothing (unchanged).
- **Insights tab:** add a "Recovery-sensitive lifts" panel and the revived
  recovery-vs-performance view.
- Existing **Finish** path additionally computes `recovery_readiness` for the
  session date and stores `recovery_score` + `recovery_zone`.

## Testing

Target `analysis.py` (pure) per the repo's stated test strategy; tests live in
`tests/`:

- `recovery_readiness`: green/yellow/red banding at threshold edges; `no_data`
  gate; inversion (value = 100 − risk); reason strings present. Confirm
  `_research_recovery_panel` output is unchanged after the `_recovery_risk`
  refactor (regression guard).
- `readiness_verdict`: zone → day_type mapping; no_data → neutral.
- `compute_progression_suggestion`: progress (all sets hit), hold (a set short),
  deload at exactly 3 stalls and not at 2, stall reset after deload, deload
  rounding to increment, `None` for non-main-lift / no history, warmups &
  incomplete sets ignored, top-weight selection.
- `compute_lift_recovery_sensitivity`: drop detection, min-sample gating, no
  paired data.
- AI `coach_session_note` is a boundary (not unit-tested) but must be guarded for
  missing key (returns `""`).

## Risks / edge cases

- **Stall semantics with deload:** after a deload the next session starts a fresh
  progression at the reduced weight; tests pin this so a deload doesn't immediately
  re-trigger.
- **Mixed top-weight sessions:** if a session's working sets are at different
  weights, "top weight" is the heaviest completed working set; only sets at that
  weight count toward the rep check.
- **Refactor safety:** factoring `_recovery_risk` out of `_research_recovery_panel`
  must not change the Health Lab panel — covered by a regression test.
- **Sparse data:** with 0–few sessions, suggestions return `None` and the logger
  behaves exactly as today; the chip shows "learning" until recovery inputs exist.
- **Increment defaults vs user edits:** the NULL-only backfill must never overwrite
  an increment the user changed.

## Open questions (resolved during planning, not blockers)

- Exact seed increments per lift (e.g. deadlift +2.5 vs +5) — pick sensible
  defaults, all user-editable later (an exercise-edit UI is a B/C concern, not
  here).
- Minimum paired-session count for `compute_lift_recovery_sensitivity` and the
  recovery-vs-performance correlation — choose during implementation.
