# Persistent Coach Memory — Design

**Date:** 2026-06-14
**Status:** Approved design, ready for implementation plan
**Builds on:** the AI boundary (`ai.py`), the pure analytics layer (`analysis.py`),
the SQLite layer (`db.py`), the cockpit renderers (`cockpit.py` / `app.py`), and
the multipage pattern (`pages/01_Strength.py`).
**Part of:** the "a coach that knows me" vision. This is **sub-project 1 of 2**.
The **N-of-1 experiment lab** is sub-project 2 and will plug into this memory
store (its results become `pattern` memories); it gets its own spec.

## Goal

Turn the AI from a stateless metrics-narrator into a coach that **remembers the
athlete over time**. Add a durable, user-curated memory store that the AI reads
before every answer and that grows through two write paths: **manual entry** (the
user tells the coach things) and **AI-suggested entries the user approves**.
Advice should compound — injuries are honored, goals orient recommendations, and
prior coaching is built upon — so the coach feels like it knows you.

### In scope

- A `coach_memory` table in `db.py` with CRUD helpers (add / update / archive /
  delete / load), following the existing upsert style.
- A pure `analysis.build_coach_memory_digest(memory_df) -> dict` that shapes
  **active** memories into a compact, grouped dict for the AI (no raw
  time-series — same privacy boundary as `summarize()`).
- Injection of that digest into all three AI calls — `analyze()`,
  `weekly_summary()`, and `answer_question()` — with a short prompt instruction
  so the coach uses the memories.
- A new `ai.suggest_memories(summary, strength, existing_memories, model=None)`
  call returning **structured candidate memories** (0–5), plus a pure parser for
  its JSON output.
- A new **`pages/02_Coach.py`** page: view/curate memories, manual quick-add,
  a button-triggered "Find things to remember" suggestion flow with
  Approve / Edit / Reject, and a coaching-log view.
- A small **cockpit peek**: a "Coach knows" card near the existing coach card
  (a couple of active goals/injuries + counts + one-line quick-add + a link to
  the Coach page).
- Tests for `build_coach_memory_digest()`, the `db` memory CRUD round-trip, and
  the `suggest_memories` JSON parser.

### Non-goals (v1)

- **No auto-consolidation/pruning.** The user archives stale memories manually.
- **No automatic/background suggestions.** Suggestions are always explicitly
  button-triggered, so API calls stay under user control.
- **No memory-linking graph** (e.g. coaching→pattern references). The `coaching`
  log is chronological; relationships are implied by text, not modeled.
- **No editing of past AI calls / no retroactive memory.** Memory affects future
  AI calls only.
- **Experiment-lab integration is sub-project 2.** The `pattern` category is
  designed to be forward-compatible to hold experiment results, but nothing in
  this spec depends on the lab.
- `ai.suggest_memories` **network path is not unit-tested** (only its parser is),
  consistent with `analyze` / `answer_question` / `weekly_summary`.

## Current state

- `ai.py` exposes `analyze(summary, strength)`, `weekly_summary(week_payload)`,
  and `answer_question(...)`, all sending `summarize()`-style compact dicts to the
  Anthropic API ([ai.py](../../ai.py)). Prompts live in `ai.py`; model defaults
  to `config.ANTHROPIC_MODEL`. `answer_question` already composes a
  `_question_payload(...)` dict from multiple derived models.
- `analysis.py` is pure (no I/O). It already has compaction precedent
  (`summarize`, `summarize_week`, the capacity/stress-leak/grappling models).
- `db.py` has idempotent-upsert tables (`daily_metrics`, `activities`,
  `daily_checkins`, `raw_json`, `weekly_summaries`, strength tables, single-row
  `profile`) and `load_*_df()` loaders. `weekly_summaries` is the precedent for
  persisting AI-generated text; `profile` is the precedent for a small
  app-managed table with upsert.
- `app.py` renders top-down (topbar → hero → signals → grappling → coach →
  trends/tabs); `load()` is `@st.cache_data(ttl=300)`.
- `cockpit.py` renders cards as pure HTML-returning functions (`*_card`,
  `_md_sections`, `_collapse_html`).
- `pages/01_Strength.py` is the multipage precedent for a dedicated feature page.

## Architecture

```
            ┌──────────────── writes ────────────────┐
 user (manual add / approve)        ai.suggest_memories(summary, strength, existing)
            │                                  │ (button-triggered, you approve)
            ▼                                  ▼
        db.add_memory / update_memory / archive_memory / delete_memory
            │
            ▼
        coach_memory table  ──load_memory_df()──►  analysis.build_coach_memory_digest(df)  [pure]
                                                          │ compact grouped dict (active only)
                                                          ▼
                       injected into  ai.analyze() · ai.weekly_summary() · ai.answer_question()
                                                          │
                                                          ▼
                                  pages/02_Coach.py  +  cockpit "Coach knows" peek
```

### Components

1. **`coach_memory` table** *(db.py)*
   - Columns:
     ```
     id           INTEGER PRIMARY KEY AUTOINCREMENT
     category     TEXT NOT NULL   -- 'goal'|'injury'|'pattern'|'coaching'|'note'
     text         TEXT NOT NULL   -- the fact, short
     status       TEXT NOT NULL DEFAULT 'active'  -- 'active'|'archived'|'superseded'
     source       TEXT NOT NULL   -- 'user'|'ai'
     confidence   TEXT            -- optional: 'low'|'med'|'high' (AI/pattern)
     target_date  TEXT            -- optional, for goals ('YYYY-MM-DD')
     body_part    TEXT            -- optional, for injuries
     created_at   TEXT NOT NULL   -- ISO timestamp
     updated_at   TEXT NOT NULL   -- ISO timestamp
     ```
   - Helpers: `add_memory(record) -> int`, `update_memory(id, fields)`,
     `archive_memory(id)`, `delete_memory(id)`, `load_memory_df(status='active')`.
     `add_memory` stamps `created_at`/`updated_at`; `update_memory`/`archive_memory`
     bump `updated_at`. Unlike the sync tables these are id-keyed CRUD (not
     date-keyed upserts) because they are user-managed, not re-synced.
   - Only `status='active'` rows are sent to the AI.

2. **`analysis.build_coach_memory_digest(memory_df) -> dict`** *(pure)*
   - Filters to `status='active'`, groups by category, shapes a compact dict:
     ```
     {
       "goals":    [{"text": .., "target_date": ..|None}, ...],
       "injuries": [{"text": .., "body_part": ..|None}, ...],
       "patterns": [{"text": .., "confidence": ..|None}, ...],
       "coaching": [{"text": .., "date": "YYYY-MM-DD"}, ...],  # recent-first
       "notes":    ["...", ...]
     }
     ```
   - Caps per-category counts and total size (e.g. ≤ ~8 per category, `coaching`
     limited to the most recent N) to protect the token budget; empty categories
     omitted. Returns `{}` when there are no active memories.
   - Pure: shapes a passed-in DataFrame, no I/O — fits `analysis.py` and is
     directly unit-testable.

3. **AI injection** *(ai.py)*
   - `analyze()` and `weekly_summary()` gain an optional `coach_memory: dict|None`
     argument; when present and non-empty it is appended to the user-content JSON
     under a `coach_memory` key.
   - `answer_question()` adds `coach_memory` to `_question_payload(...)`.
   - System prompts get one short paragraph: *"You also receive `coach_memory` —
     durable, user-approved facts about this athlete (goals, injuries, observed
     patterns, prior coaching). Honor injuries when advising load, orient advice
     toward goals, build on prior coaching, and reference these naturally so the
     athlete feels known. These are curated facts, not raw data."*
   - Backward compatible: omitting the arg leaves current behavior unchanged.

4. **`ai.suggest_memories(summary, strength, existing_memories, model=None)`**
   *(AI boundary)*
   - No API key → returns `[]` (page shows the same italic note style).
   - New `SUGGEST_SYSTEM` prompt: given the compact metrics summary, the strength
     profile, and the list of **existing** memories, propose **0–5** *new*
     durable facts worth remembering — never duplicating an existing memory, never
     transient day-to-day noise, only things that would help a coach over weeks.
   - Output is a strict JSON array of objects:
     `{category, text, confidence?, target_date?, body_part?, rationale}`.
   - A pure helper `_parse_memory_candidates(text) -> list[dict]` extracts/validates
     the JSON (tolerates fenced code blocks; drops malformed items; clamps
     `category` to the allowed set). `suggest_memories` calls it on the response.
   - `max_tokens ≈ 700`.

5. **`pages/02_Coach.py`** *(new page, mirrors `pages/01_Strength.py`)*
   - **"What the coach knows"** — active memories grouped by category; each row has
     edit (text + optional fields), archive, and delete. Goals show `target_date`;
     injuries show `body_part`.
   - **Quick-add** — category picker + text + the optional fields relevant to the
     category → `db.add_memory(source='user')`.
   - **"Find things to remember"** button → `ai.suggest_memories(...)` → candidate
     cards, each Approve (`db.add_memory(source='ai')`) / Edit-then-approve /
     Reject (discard). Existing memories are passed so candidates won't duplicate.
   - **Coaching log** — chronological list of `coaching` entries.
   - Reuses `db.load_*` loaders + `analysis.summarize()/summarize_strength()` to
     build the suggestion payload, mirroring how `app.py` assembles AI context.

6. **Cockpit peek** *(cockpit.py + app.py)*
   - `cockpit.coach_memory_peek(digest) -> str`: a compact "Coach knows" card —
     counts per category + a couple of active goals/injuries + a link to the Coach
     page. Pure HTML, wrapped in `_collapse_html()`, matching existing `*_card`s.
   - A one-line quick-add `st.text_input` in `app.py` near the coach card that
     writes a `note` (or a chosen category) via `db.add_memory`.
   - `app.py` loads `db.load_memory_df()`, builds the digest once, passes it to
     both the peek and the AI calls.

### Data flow

`db.load_memory_df() → analysis.build_coach_memory_digest() → [ injected into
ai.analyze / weekly_summary / answer_question ] + [ cockpit.coach_memory_peek ]`.
Writes: `manual add` and `approved suggestion` → `db.add_memory` → next render
re-reads and re-injects.

### Edge cases

- **No memories:** digest is `{}`; AI calls behave exactly as today; peek shows an
  empty note.
- **No `ANTHROPIC_API_KEY`:** `suggest_memories` returns `[]`; injection is a
  no-op for the (already key-gated) AI calls.
- **Malformed suggestion JSON:** `_parse_memory_candidates` drops bad items and
  returns whatever validates (possibly `[]`); the page never crashes.
- **Duplicate suggestion:** the prompt is told to avoid duplicates; if one slips
  through, the user simply rejects it. (No automatic dedup in v1.)
- **Large memory set:** digest caps per-category counts so token cost stays
  bounded regardless of how many archived/active rows exist.
- **Streamlit cache:** memory writes happen outside the `@st.cache_data` `load()`;
  the page calls `st.rerun()` after writes so the list reflects changes.

### Testing

`tests/test_coach_memory.py`:
- `build_coach_memory_digest()` over a synthetic memory frame → active-only
  filter, correct grouping, field shaping (goal dates, injury body part, coaching
  recency), per-category caps, and `{}` on empty.
- `db` memory CRUD: `add_memory` → `load_memory_df` round-trip;
  `update_memory` bumps `updated_at`; `archive_memory` removes it from the active
  load; `delete_memory` removes it entirely.
- `_parse_memory_candidates()` against fixture strings: clean JSON array, JSON in
  a fenced block, malformed/partial items (dropped), and an unknown `category`
  (clamped/dropped).

The `ai.suggest_memories` network path itself is left untested, matching
`analyze` / `answer_question` / `weekly_summary`.
