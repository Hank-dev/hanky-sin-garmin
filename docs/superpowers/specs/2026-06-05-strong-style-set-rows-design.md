# Strong-Style Set Rows — Design

**Date:** 2026-06-05
**Status:** Approved design, ready for implementation plan
**Builds on:** Phase 1 strength logger (`pages/01_Strength.py`, merged to `master`).

## Goal

Replace the live "Log workout" set-entry UI with a Strong-style layout: each
logged set is its own editable row — **Set badge · Previous · kg · Reps ·
remove** — with a **+ Add Set** button, per-exercise column headers, and a
greyed **Previous** column populated from the last session. RPE and warmup are
preserved but tucked into the cleaner row. Only the live logger changes; History,
Insights, Bodyweight, routines, and persistence are untouched.

### In scope

- Per-set editable rows (edit any set in place; remove any row), replacing the
  current "static table + single append row" block.
- A **Set badge** that toggles warmup (shows the set number, or **W**).
- A greyed **Previous** column showing last session's `kg × reps` per set.
- **+ Add Set** that appends a set pre-filled from the last one.
- A per-exercise **RPE** toggle that reveals an RPE cell per row (default off).
- A per-row **L/R** selector for unilateral exercises (side already persists).
- A new pure `analysis.last_session_sets(...)` helper for the Previous column.

### Non-goals

- No template/routine editor screen (live logger only).
- No DB schema changes; reads/writes the existing Phase 1 tables.
- No change to the Finish/persistence path, the History/Insights/Bodyweight tabs,
  the "Add exercise"/custom-exercise controls, or routines.
- No `st.data_editor` grid (rejected: generic look, awkward remove + Previous).

## Current state

`pages/01_Strength.py` renders, per exercise in `st.session_state["active"]
["exercises"][ei]`, a static `st.table` of existing sets plus one row of
`number_input`s (reps/kg/RPE/warmup) and **Add set / Remove last set** buttons
([pages/01_Strength.py:313-345](pages/01_Strength.py)). Each set dict already
has: `set_id`, `set_index`, `side`, `reps`, `weight_kg`, `rpe`, `is_warmup`,
`completed`. The active-state shape, `active_to_frames`, live metrics, and the
Finish persistence loop are reused as-is.

## Architecture

```
db.load_strength_sessions_df / load_strength_sets_df ─┐
                                                      ▼
pages/01_Strength.py (Log tab) ── analysis.last_session_sets(ex_id, sessions, sets) [pure]
   per exercise → header row + one editable row per set + "+ Add Set"
   each rerun: sync per-set widget values back into st.session_state["active"]
   (Finish persistence + metrics unchanged — they read active[...]["sets"])
```

`analysis.py` stays I/O-free; the page owns the Streamlit widgets and the DB
reads.

## Section 1 — `analysis.last_session_sets` (pure)

`last_session_sets(exercise_id, sessions_df, sets_df) -> list[dict]`

- Find the most recent **saved** session (by `date`, then `started_at`) whose
  sets include `exercise_id`. Return its **working** sets (exclude
  `is_warmup == 1`; treat missing `completed` as completed) in `set_index`
  order, each as `{"weight_kg": float, "reps": int}`.
- Returns `[]` when the exercise has never been logged, or on empty/missing
  inputs. Pure, deterministic, unit-tested.
- The page maps active row *i* (1-based) to `previous[i-1]`; rows beyond the
  previous session's set count show `—`.

(The active workout is not yet saved, so "previous" is simply the most recent
session in the DB containing the exercise.)

## Section 2 — Set rows UI (rewrite the per-exercise block)

For each exercise in `active["exercises"]`:

- **Title** — the exercise name (existing styling).
- **Header row** — small labels `Set · Previous · kg · Reps` (oxblood/dim),
  via `st.columns` matching the row widths.
- **One row per set** (`st.columns([...])`), keyed by the set's stable `set_id`:
  - **Set badge** — `st.button` labelled the 1-based set number, or `W` when
    `is_warmup`; on click, toggle `is_warmup` and `st.rerun()`. (Key
    `setbadge_{set_id}`.)
  - **Previous** — greyed `f"{w:g} kg × {r}"` from `last_session_sets` for this
    row index, else `—`. Read-only caption/markdown.
  - **kg** — `st.number_input` (min 0.0, step 1.0), `value=set["weight_kg"]`,
    key `kg_{set_id}`.
  - **Reps** — `st.number_input` (min 0, step 1), `value=set["reps"]`, key
    `reps_{set_id}`.
  - **RPE** (only when the exercise's RPE toggle is on) — `st.number_input`
    (0.0–10.0, step 0.5), `value=set.get("rpe") or 0.0`, key `rpe_{set_id}`.
  - **L/R** (only when `ex["is_unilateral"]`) — a small `st.selectbox`/
    segmented control of `["left","right"]`, `value=set["side"]`, key
    `side_{set_id}`.
  - **— remove** — `st.button("—")` (key `del_{set_id}`); on click, drop that
    set from `ex["sets"]`, then renumber `set_index`, and `st.rerun()`.
- **+ Add Set** — `st.button` (key `add_{ei}`); appends a new set with a fresh
  `set_id`, `set_index = len+1`, `side` = last set's side or `"both"`,
  `is_warmup = 0`, `completed = 1`, and **kg/reps copied from the last set**
  (Strong behaviour; defaults 20 kg × 5 if none), then `st.rerun()`.
- **RPE toggle** — a per-exercise `st.toggle("RPE", key=f"showrpe_{ei}")`
  (default off) that controls whether the RPE cell is shown. Stored RPE values
  are preserved regardless.

**Edit-in-place sync:** each kg/reps/rpe/side widget assigns its **return value**
straight back into the set dict on render (e.g. `set["weight_kg"] =
st.number_input(..., value=float(set["weight_kg"]), key=f"kg_{set_id}")`). The
return is the current (edited) value, so `st.session_state["active"]` stays
authoritative and the Finish persistence reflects live edits without a separate
"Add set" commit step. No separate post-render sync loop is needed.

Because the **Volume / Working sets / Top est-1RM** metrics render above the
rows but must reflect the just-edited values, reserve a top `st.empty()` (or
`st.container()`) placeholder before the rows and fill it with the metrics
*after* the rows have run (so it reads the updated active state, not last
rerun's). Keeps the summary at the top while staying live.

**Widget-key stability:** keys are derived from the immutable `set_id`, so
adding/removing rows never reuses another row's key. `set_index` is display-only
and renumbered after add/remove.

## Section 3 — What stays the same

`active_to_frames`, `summarize_sessions` live metrics, the "Add exercise"
selectbox, the custom-exercise expander, **Save as routine**, **Finish & save**
(persists `active[...]["sets"]` + readiness snapshot), **Discard**, and the
History/Insights/Bodyweight tabs are unchanged. The Finish loop already writes
every field the rows edit.

## Section 4 — Testing

- **`tests/test_strength_analysis.py`** (extend) — `last_session_sets`: picks
  the most recent of multiple sessions; orders by `set_index`; excludes warmups;
  returns `[]` for an unlogged exercise and for empty frames.
- **AppTest smoke** — with an active workout (containing one exercise + a couple
  of sets) injected into `session_state`, the Log tab renders the new rows
  without exception (empty + data-backed). Full browser click-through (toggle
  warmup, edit a cell, add/remove a set, finish) remains the user's manual check.

## Risks / open questions (non-blocking)

- **Streamlit reruns & many widgets:** a long workout creates many widgets;
  acceptable for a single-user app. Keys are `set_id`-scoped to avoid collisions.
- **Edit-sync ordering:** each widget assigns its return value into the set dict
  inline at render, so no ordering concern; the metrics computed below the rows
  read the already-updated active state.
- **Previous matching:** matched by set position, not by load; if the previous
  session had a different set count, trailing rows show `—`. Acceptable.

## Definition of done

1. `analysis.last_session_sets` implemented + unit-tested (pure).
2. The per-exercise set block in `pages/01_Strength.py` renders Strong-style rows
   (Set badge/warmup toggle · Previous · kg · Reps · remove), + Add Set, RPE
   toggle, and L/R for unilateral lifts, with live edit-in-place sync.
3. Finish/persistence, metrics, and the other tabs unchanged.
4. `pytest` green; Insights/Log AppTest smokes green.
