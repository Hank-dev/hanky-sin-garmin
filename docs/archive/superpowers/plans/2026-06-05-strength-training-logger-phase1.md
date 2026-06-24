# Strength Training Logger — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Strong"-style live strength-training logger to the Garmin Coach app — exercise library, saved routines, live set logging, estimated 1RM tracking, Garmin bodyweight/profile sync, and a per-session readiness snapshot — on a dedicated Streamlit page.

**Architecture:** Follows the existing one-directional module split. `db.py` gains five tables + a `profile` row (idempotent upserts, manual-protection on body metrics). `ingest.py` gains Garmin weigh-in/profile pulls via the existing `dig()`/`safe()` pattern. `analysis.py` gains pure 1RM/enrichment/summary/PR/readiness functions (no I/O). UI is a new `pages/01_Strength.py` plus render helpers in `cockpit.py`. AI integration, strength standards, and asymmetry are deferred to Phase 2.

**Tech Stack:** Python, SQLite (`sqlite3`), pandas, Streamlit, Plotly, `garminconnect`/`garth`, `pytest`/`unittest`.

**Spec:** `docs/superpowers/specs/2026-06-05-strength-training-logger-phase1-design.md`

> **Git note:** This workspace is not currently a git repo. If you want the per-task commits below to work, run `git init && git add -A && git commit -m "baseline before strength logger"` first. Otherwise treat each "Commit" step as an optional checkpoint and skip it.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `config.py` | strength settings + profile `.env` overrides | Modify |
| `strength_catalog.py` | seed exercise library + movement-pattern vocabulary | Create |
| `db.py` | new tables, loaders, upserts, seed, manual-protection | Modify |
| `analysis.py` | pure strength functions (1RM, enrich, summaries, PR, readiness) | Modify |
| `ingest.py` | Garmin weigh-in + profile ingest | Modify |
| `cockpit.py` | strength render helpers (oxblood) | Modify |
| `pages/01_Strength.py` | live logger + history UI | Create |
| `tests/test_strength_catalog.py` | seed integrity | Create |
| `tests/test_strength_db.py` | schema idempotency + manual-protection | Create |
| `tests/test_strength_analysis.py` | pure-function behavior | Create |
| `tests/test_strength_ingest.py` | weigh-in/profile mapping (fixtures) | Create |
| `tests/test_strength_cockpit.py` | render helpers return expected shapes | Create |

---

## Task 1: Config — strength + profile settings

**Files:**
- Modify: `config.py` (append after line 27)

- [ ] **Step 1: Add settings to `config.py`**

Append to the end of `config.py`:

```python

# --- Strength training ---
ONE_RM_FORMULA = os.getenv("ONE_RM_FORMULA", "epley")   # "epley" | "brzycki"
STRENGTH_UNIT = os.getenv("STRENGTH_UNIT", "kg")


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Athlete profile. Garmin fills these during sync; anything set here in .env is
# treated as a manual override and is NOT overwritten by a Garmin sync.
PROFILE_SEX = (os.getenv("PROFILE_SEX") or "").strip().lower() or None  # "male"|"female"
PROFILE_BIRTH_YEAR = _int_or_none(os.getenv("PROFILE_BIRTH_YEAR"))
PROFILE_HEIGHT_CM = _float_or_none(os.getenv("PROFILE_HEIGHT_CM"))
```

- [ ] **Step 2: Verify it imports**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -c "import config; print(config.ONE_RM_FORMULA, config.STRENGTH_UNIT, config.PROFILE_SEX)"`
Expected: `epley kg None`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat(strength): add strength + profile config settings

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Exercise catalog seed

**Files:**
- Create: `strength_catalog.py`
- Test: `tests/test_strength_catalog.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_strength_catalog.py`:

```python
import strength_catalog as sc


REQUIRED = {
    "exercise_id", "name", "category", "movement_pattern",
    "primary_muscle", "is_unilateral", "is_bodyweight", "is_main_lift",
}


def test_exercise_ids_unique():
    ids = [e["exercise_id"] for e in sc.EXERCISE_SEED]
    assert len(ids) == len(set(ids))


def test_every_exercise_has_required_keys_and_valid_pattern():
    for e in sc.EXERCISE_SEED:
        assert REQUIRED <= set(e), e
        assert e["movement_pattern"] in sc.MOVEMENT_PATTERNS, e
        for flag in ("is_unilateral", "is_bodyweight", "is_main_lift"):
            assert e[flag] in (0, 1), e


def test_has_the_main_barbell_lifts():
    ids = {e["exercise_id"] for e in sc.EXERCISE_SEED}
    assert {"back-squat", "bench-press", "deadlift", "overhead-press"} <= ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strength_catalog'`

- [ ] **Step 3: Create `strength_catalog.py`**

```python
"""Seed exercise library + movement-pattern vocabulary for the strength logger.

Pure data, no imports. db.seed_exercises() inserts these on init (insert-if-
absent, so user edits to seeded rows are preserved). movement_pattern is stored
now and consumed by the Phase 2 balance/asymmetry analytics.
"""

MOVEMENT_PATTERNS = (
    "squat", "hinge", "horizontal_push", "vertical_push",
    "horizontal_pull", "vertical_pull", "lunge", "carry", "core", "isolation",
)


def _ex(exercise_id, name, category, pattern, muscle,
        unilateral=0, bodyweight=0, main=0):
    return {
        "exercise_id": exercise_id,
        "name": name,
        "category": category,
        "movement_pattern": pattern,
        "primary_muscle": muscle,
        "is_unilateral": unilateral,
        "is_bodyweight": bodyweight,
        "is_main_lift": main,
    }


EXERCISE_SEED = [
    _ex("back-squat", "Back Squat", "barbell", "squat", "quads", main=1),
    _ex("front-squat", "Front Squat", "barbell", "squat", "quads"),
    _ex("leg-press", "Leg Press", "machine", "squat", "quads"),
    _ex("deadlift", "Deadlift", "barbell", "hinge", "hamstrings", main=1),
    _ex("romanian-deadlift", "Romanian Deadlift", "barbell", "hinge", "hamstrings"),
    _ex("leg-curl", "Leg Curl", "machine", "isolation", "hamstrings"),
    _ex("bench-press", "Bench Press", "barbell", "horizontal_push", "chest", main=1),
    _ex("incline-bench-press", "Incline Bench Press", "barbell", "horizontal_push", "chest"),
    _ex("dumbbell-bench-press", "Dumbbell Bench Press", "dumbbell", "horizontal_push", "chest"),
    _ex("overhead-press", "Overhead Press", "barbell", "vertical_push", "shoulders", main=1),
    _ex("dumbbell-shoulder-press", "Dumbbell Shoulder Press", "dumbbell", "vertical_push", "shoulders"),
    _ex("dip", "Dip", "bodyweight", "vertical_push", "triceps", bodyweight=1),
    _ex("barbell-row", "Barbell Row", "barbell", "horizontal_pull", "back", main=1),
    _ex("seated-cable-row", "Seated Cable Row", "cable", "horizontal_pull", "back"),
    _ex("pull-up", "Pull-up", "bodyweight", "vertical_pull", "back", bodyweight=1),
    _ex("chin-up", "Chin-up", "bodyweight", "vertical_pull", "back", bodyweight=1),
    _ex("lat-pulldown", "Lat Pulldown", "cable", "vertical_pull", "back"),
    _ex("bulgarian-split-squat", "Bulgarian Split Squat", "dumbbell", "lunge", "quads", unilateral=1),
    _ex("walking-lunge", "Walking Lunge", "dumbbell", "lunge", "quads", unilateral=1),
    _ex("barbell-curl", "Barbell Curl", "barbell", "isolation", "biceps"),
    _ex("tricep-pushdown", "Tricep Pushdown", "cable", "isolation", "triceps"),
    _ex("plank", "Plank", "bodyweight", "core", "core", bodyweight=1),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_catalog.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add strength_catalog.py tests/test_strength_catalog.py
git commit -m "feat(strength): seed exercise catalog

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: DB schema, loaders, upserts, seed, manual-protection

**Files:**
- Modify: `db.py` (extend `SCHEMA`; add column lists, upserts, loaders, seed; call from `init_db`)
- Test: `tests/test_strength_db.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_strength_db.py`:

```python
import importlib
import tempfile

import config
import db


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    config.DB_PATH = tmp.name           # db.connect() reads this at call time
    importlib.reload(db)                 # rebind db.config.DB_PATH
    db.config.DB_PATH = tmp.name
    db.init_db()
    return tmp.name


def test_seed_is_idempotent_and_preserves_edits():
    _fresh_db()
    db.seed_exercises()
    df = db.load_exercises_df()
    assert "back-squat" in set(df["exercise_id"])
    n = len(df)
    # user edits a seeded row
    db.upsert_exercise({"exercise_id": "back-squat", "name": "My Squat",
                        "category": "barbell", "movement_pattern": "squat",
                        "primary_muscle": "quads", "is_unilateral": 0,
                        "is_bodyweight": 0, "is_main_lift": 1, "is_custom": 0})
    db.seed_exercises()                  # re-seed must not clobber the edit
    df2 = db.load_exercises_df()
    assert len(df2) == n
    row = df2[df2["exercise_id"] == "back-squat"].iloc[0]
    assert row["name"] == "My Squat"


def test_session_and_set_upserts_idempotent():
    _fresh_db()
    db.upsert_strength_session({"session_id": "s1", "date": "2026-06-05",
                                "name": "Push", "bodyweight_kg": 80.0})
    db.upsert_strength_session({"session_id": "s1", "date": "2026-06-05",
                                "name": "Push Day", "bodyweight_kg": 80.0})
    sessions = db.load_strength_sessions_df()
    assert len(sessions) == 1
    assert sessions.iloc[0]["name"] == "Push Day"

    db.upsert_strength_set({"set_id": "x1", "session_id": "s1",
                            "exercise_id": "bench-press", "position": 0,
                            "set_index": 1, "side": "both", "reps": 5,
                            "weight_kg": 100.0, "is_warmup": 0, "completed": 1})
    db.upsert_strength_set({"set_id": "x1", "session_id": "s1",
                            "exercise_id": "bench-press", "position": 0,
                            "set_index": 1, "side": "both", "reps": 6,
                            "weight_kg": 100.0, "is_warmup": 0, "completed": 1})
    sets = db.load_strength_sets_df()
    assert len(sets) == 1
    assert int(sets.iloc[0]["reps"]) == 6


def test_garmin_body_metric_does_not_overwrite_manual():
    _fresh_db()
    db.upsert_body_metric({"date": "2026-06-05", "weight_kg": 81.0, "source": "manual"})
    db.upsert_body_metric({"date": "2026-06-05", "weight_kg": 79.0, "source": "garmin"})
    bm = db.load_body_metrics_df()
    row = bm[bm["date"].astype(str).str.startswith("2026-06-05")].iloc[0]
    assert row["weight_kg"] == 81.0
    assert row["source"] == "manual"
    # but manual can still overwrite
    db.upsert_body_metric({"date": "2026-06-05", "weight_kg": 80.0, "source": "manual"})
    bm = db.load_body_metrics_df()
    row = bm[bm["date"].astype(str).str.startswith("2026-06-05")].iloc[0]
    assert row["weight_kg"] == 80.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_db.py -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'seed_exercises'`

- [ ] **Step 3: Extend `SCHEMA` in `db.py`**

In `db.py`, inside the `SCHEMA = """ ... """` string, before the closing `"""` (after the `daily_checkins` table, around line 71), append:

```sql

CREATE TABLE IF NOT EXISTS exercises (
    exercise_id TEXT PRIMARY KEY,
    name TEXT,
    category TEXT,
    movement_pattern TEXT,
    primary_muscle TEXT,
    is_unilateral INTEGER DEFAULT 0,
    is_bodyweight INTEGER DEFAULT 0,
    is_main_lift INTEGER DEFAULT 0,
    is_custom INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS routines (
    routine_id TEXT PRIMARY KEY,
    name TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS routine_exercises (
    routine_id TEXT,
    position INTEGER,
    exercise_id TEXT,
    target_sets INTEGER,
    target_reps INTEGER,
    target_weight REAL,
    PRIMARY KEY (routine_id, position)
);

CREATE TABLE IF NOT EXISTS strength_sessions (
    session_id TEXT PRIMARY KEY,
    date TEXT,
    started_at TEXT,
    ended_at TEXT,
    routine_id TEXT,
    name TEXT,
    bodyweight_kg REAL,
    notes TEXT,
    readiness_score REAL,
    readiness_level TEXT,
    hrv_status TEXT,
    hrv_overnight_avg REAL,
    body_battery_start REAL,
    sleep_score REAL,
    resting_hr REAL,
    acwr REAL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS strength_sets (
    set_id TEXT PRIMARY KEY,
    session_id TEXT,
    exercise_id TEXT,
    position INTEGER,
    set_index INTEGER,
    side TEXT DEFAULT 'both',
    reps INTEGER,
    weight_kg REAL,
    rpe REAL,
    is_warmup INTEGER DEFAULT 0,
    completed INTEGER DEFAULT 1,
    logged_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS body_metrics (
    date TEXT PRIMARY KEY,
    weight_kg REAL,
    bmi REAL,
    body_fat_pct REAL,
    muscle_mass_kg REAL,
    body_water_pct REAL,
    bone_mass_kg REAL,
    source TEXT DEFAULT 'garmin',
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY,
    sex TEXT,
    birth_year INTEGER,
    height_cm REAL,
    source TEXT DEFAULT 'garmin',
    updated_at TEXT DEFAULT (datetime('now'))
);
```

- [ ] **Step 4: Add column lists in `db.py`**

After the existing `CHECKIN_COLS = [...]` line (around line 91), add:

```python
EXERCISE_COLS = [
    "exercise_id", "name", "category", "movement_pattern", "primary_muscle",
    "is_unilateral", "is_bodyweight", "is_main_lift", "is_custom",
]
ROUTINE_COLS = ["routine_id", "name", "notes"]
ROUTINE_EX_COLS = [
    "routine_id", "position", "exercise_id", "target_sets",
    "target_reps", "target_weight",
]
SESSION_COLS = [
    "session_id", "date", "started_at", "ended_at", "routine_id", "name",
    "bodyweight_kg", "notes", "readiness_score", "readiness_level",
    "hrv_status", "hrv_overnight_avg", "body_battery_start", "sleep_score",
    "resting_hr", "acwr",
]
SET_COLS = [
    "set_id", "session_id", "exercise_id", "position", "set_index", "side",
    "reps", "weight_kg", "rpe", "is_warmup", "completed", "logged_at",
]
BODY_METRIC_COLS = [
    "date", "weight_kg", "bmi", "body_fat_pct", "muscle_mass_kg",
    "body_water_pct", "bone_mass_kg", "source",
]
PROFILE_COLS = ["id", "sex", "birth_year", "height_cm", "source"]
```

- [ ] **Step 5: Add a generic upsert helper + the upserts in `db.py`**

After `save_raw(...)` (around line 164), add:

```python
def _upsert(table, cols_def, record, pk, touch_updated=True):
    cols = [c for c in cols_def if c in record]
    placeholders = ", ".join("?" for _ in cols)
    collist = ", ".join(cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != pk)
    tail = ", updated_at=datetime('now')" if touch_updated else ""
    sql = (
        f"INSERT INTO {table} ({collist}) VALUES ({placeholders}) "
        f"ON CONFLICT({pk}) DO UPDATE SET {updates}{tail}"
        if updates else
        f"INSERT OR IGNORE INTO {table} ({collist}) VALUES ({placeholders})"
    )
    with connect() as conn:
        conn.execute(sql, [record[c] for c in cols])


def upsert_exercise(record: dict):
    _upsert("exercises", EXERCISE_COLS, record, "exercise_id", touch_updated=False)


def upsert_routine(record: dict):
    _upsert("routines", ROUTINE_COLS, record, "routine_id")


def upsert_routine_exercise(record: dict):
    cols = [c for c in ROUTINE_EX_COLS if c in record]
    placeholders = ", ".join("?" for _ in cols)
    collist = ", ".join(cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols
                        if c not in ("routine_id", "position"))
    sql = (
        f"INSERT INTO routine_exercises ({collist}) VALUES ({placeholders}) "
        f"ON CONFLICT(routine_id, position) DO UPDATE SET {updates}"
    )
    with connect() as conn:
        conn.execute(sql, [record[c] for c in cols])


def upsert_strength_session(record: dict):
    _upsert("strength_sessions", SESSION_COLS, record, "session_id")


def upsert_strength_set(record: dict):
    _upsert("strength_sets", SET_COLS, record, "set_id", touch_updated=False)


def delete_strength_set(set_id: str):
    with connect() as conn:
        conn.execute("DELETE FROM strength_sets WHERE set_id=?", (set_id,))


def upsert_body_metric(record: dict):
    """Garmin writes won't overwrite a row whose existing source is 'manual'."""
    source = (record.get("source") or "garmin")
    if source == "garmin":
        with connect() as conn:
            existing = conn.execute(
                "SELECT source FROM body_metrics WHERE date=?", (record["date"],)
            ).fetchone()
        if existing is not None and existing["source"] == "manual":
            return
    _upsert("body_metrics", BODY_METRIC_COLS, record, "date")


def upsert_profile(record: dict):
    """Single-row profile (id=1). Garmin source won't overwrite a manual row."""
    record = {**record, "id": 1}
    source = (record.get("source") or "garmin")
    if source == "garmin":
        with connect() as conn:
            existing = conn.execute(
                "SELECT source FROM profile WHERE id=1"
            ).fetchone()
        if existing is not None and existing["source"] == "manual":
            return
    _upsert("profile", PROFILE_COLS, record, "id")


def seed_exercises():
    """Insert the starter library if absent. INSERT OR IGNORE preserves any
    user edits to seeded rows and any custom exercises."""
    import strength_catalog
    with connect() as conn:
        for e in strength_catalog.EXERCISE_SEED:
            conn.execute(
                "INSERT OR IGNORE INTO exercises "
                "(exercise_id, name, category, movement_pattern, primary_muscle, "
                " is_unilateral, is_bodyweight, is_main_lift, is_custom) "
                "VALUES (?,?,?,?,?,?,?,?,0)",
                (e["exercise_id"], e["name"], e["category"], e["movement_pattern"],
                 e["primary_muscle"], e["is_unilateral"], e["is_bodyweight"],
                 e["is_main_lift"]),
            )
```

- [ ] **Step 6: Add loaders in `db.py`**

After `load_checkins_df()` (around line 191), add:

```python
def load_exercises_df():
    import pandas as pd
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM exercises ORDER BY name", conn)


def load_routines_df():
    import pandas as pd
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM routines ORDER BY name", conn)


def load_routine_exercises_df():
    import pandas as pd
    with connect() as conn:
        return pd.read_sql_query(
            "SELECT * FROM routine_exercises ORDER BY routine_id, position", conn
        )


def load_strength_sessions_df():
    import pandas as pd
    with connect() as conn:
        return pd.read_sql_query(
            "SELECT * FROM strength_sessions ORDER BY date, started_at", conn
        )


def load_strength_sets_df():
    import pandas as pd
    with connect() as conn:
        return pd.read_sql_query(
            "SELECT * FROM strength_sets ORDER BY session_id, position, set_index", conn
        )


def load_body_metrics_df():
    import pandas as pd
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM body_metrics ORDER BY date", conn)


def load_profile() -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM profile WHERE id=1").fetchone()
    return dict(row) if row is not None else {}
```

- [ ] **Step 7: Seed on init + apply config profile override**

In `db.py`, add to `init_db()` **after** the `with connect() as conn:` block
closes (dedented to the function-body level, i.e. 4 spaces — NOT inside the
`with`). The existing function ends with the `ALTER TABLE` backfill `for` loop
inside the `with` block; add this immediately after that block:

```python
    # Seed the strength library + apply any .env profile override. Done AFTER
    # the schema `with connect()` transaction has committed, so these nested
    # connections don't contend with an open write transaction (which on an
    # older DB mid-ALTER would otherwise risk "database is locked").
    seed_exercises()
    prof = {k: v for k, v in (
        ("sex", config.PROFILE_SEX),
        ("birth_year", config.PROFILE_BIRTH_YEAR),
        ("height_cm", config.PROFILE_HEIGHT_CM),
    ) if v is not None}
    if prof:
        upsert_profile({**prof, "source": "manual"})
```

(`seed_exercises()` and `upsert_profile()` are the module-level functions added
in Steps 5–6; each opens its own connection, so they must run after the schema
transaction commits.)

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_db.py -v`
Expected: PASS (3 passed)

- [ ] **Step 9: Commit**

```bash
git add db.py tests/test_strength_db.py
git commit -m "feat(strength): add strength tables, loaders, upserts, seed

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: analysis.estimate_1rm

**Files:**
- Modify: `analysis.py` (append a new section at end)
- Test: `tests/test_strength_analysis.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_strength_analysis.py`:

```python
import math

import pandas as pd

import analysis


def test_estimate_1rm_single_rep_is_weight():
    assert analysis.estimate_1rm(100, 1) == 100


def test_estimate_1rm_epley():
    # 100 * (1 + 5/30) = 116.666...
    assert math.isclose(analysis.estimate_1rm(100, 5), 100 * (1 + 5 / 30))


def test_estimate_1rm_brzycki():
    # 100 * 36 / (37 - 5) = 112.5
    assert math.isclose(analysis.estimate_1rm(100, 5, "brzycki"), 112.5)


def test_estimate_1rm_invalid_returns_none():
    assert analysis.estimate_1rm(100, 0) is None
    assert analysis.estimate_1rm(0, 5) is None
    assert analysis.estimate_1rm(None, 5) is None
    assert analysis.estimate_1rm(100, None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_analysis.py -v`
Expected: FAIL — `AttributeError: module 'analysis' has no attribute 'estimate_1rm'`

- [ ] **Step 3: Append the strength section to `analysis.py`**

At the very end of `analysis.py`, add:

```python


# ── Strength training (pure analytics; no I/O) ────────────────────────────────
def estimate_1rm(weight, reps, formula="epley"):
    """Estimated one-rep max from a working set. Epley default; Brzycki optional.

    Returns None for non-positive weight/reps or unparseable input.
    """
    try:
        w = float(weight)
        r = int(reps)
    except (TypeError, ValueError):
        return None
    if w <= 0 or r <= 0:
        return None
    if r == 1:
        return w
    if formula == "brzycki":
        if r >= 37:
            return None
        return w * 36.0 / (37.0 - r)
    return w * (1.0 + r / 30.0)  # epley
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_analysis.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_strength_analysis.py
git commit -m "feat(strength): estimate_1rm (Epley/Brzycki)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: analysis.enrich_strength_sets

**Files:**
- Modify: `analysis.py`
- Test: `tests/test_strength_analysis.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_strength_analysis.py`:

```python
def _exercises():
    return pd.DataFrame([
        {"exercise_id": "bench-press", "is_bodyweight": 0},
        {"exercise_id": "pull-up", "is_bodyweight": 1},
    ])


def _sessions(bodyweight=80.0):
    return pd.DataFrame([{"session_id": "s1", "date": "2026-06-05",
                          "bodyweight_kg": bodyweight}])


def test_enrich_adds_effective_load_and_1rm():
    sets = pd.DataFrame([
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"set_id": "b", "session_id": "s1", "exercise_id": "pull-up",
         "reps": 5, "weight_kg": 10.0, "is_warmup": 0, "completed": 1},
    ])
    out = analysis.enrich_strength_sets(sets, _sessions(), _exercises())
    bench = out[out["exercise_id"] == "bench-press"].iloc[0]
    pull = out[out["exercise_id"] == "pull-up"].iloc[0]
    assert bench["effective_load_kg"] == 100.0
    assert pull["effective_load_kg"] == 90.0   # 80 bodyweight + 10 added
    assert bench["est_1rm_kg"] > 100


def test_enrich_warmup_has_no_1rm():
    sets = pd.DataFrame([
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 10, "weight_kg": 40.0, "is_warmup": 1, "completed": 1},
    ])
    out = analysis.enrich_strength_sets(sets, _sessions(), _exercises())
    assert pd.isna(out.iloc[0]["est_1rm_kg"])


def test_enrich_empty_returns_empty_with_columns():
    out = analysis.enrich_strength_sets(pd.DataFrame(), _sessions(), _exercises())
    assert out.empty
    assert "effective_load_kg" in out.columns
    assert "est_1rm_kg" in out.columns
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_analysis.py -k enrich -v`
Expected: FAIL — `AttributeError: ... 'enrich_strength_sets'`

- [ ] **Step 3: Append to the strength section of `analysis.py`**

```python


def enrich_strength_sets(sets_df, sessions_df, exercises_df, formula="epley"):
    """Add effective_load_kg and est_1rm_kg to a sets DataFrame.

    Bodyweight exercises use the session's snapshot bodyweight_kg + added load
    so historical numbers stay stable. Warmup sets get no 1RM. Pure.
    """
    base_cols = list(sets_df.columns)
    out_cols = base_cols + ["effective_load_kg", "est_1rm_kg"]
    if sets_df is None or sets_df.empty:
        return pd.DataFrame(columns=out_cols)

    df = sets_df.copy()
    bw = (sessions_df[["session_id", "bodyweight_kg"]]
          if sessions_df is not None and not sessions_df.empty
          else pd.DataFrame(columns=["session_id", "bodyweight_kg"]))
    df = df.merge(bw, on="session_id", how="left")
    isbw = (exercises_df[["exercise_id", "is_bodyweight"]]
            if exercises_df is not None and not exercises_df.empty
            else pd.DataFrame(columns=["exercise_id", "is_bodyweight"]))
    df = df.merge(isbw, on="exercise_id", how="left", suffixes=("", "_ex"))

    df["is_bodyweight"] = pd.to_numeric(df.get("is_bodyweight"), errors="coerce").fillna(0).astype(int)
    body = pd.to_numeric(df.get("bodyweight_kg"), errors="coerce").fillna(0.0)
    added = pd.to_numeric(df.get("weight_kg"), errors="coerce").fillna(0.0)
    df["effective_load_kg"] = added + df["is_bodyweight"] * body

    warm = pd.to_numeric(df.get("is_warmup"), errors="coerce").fillna(0).astype(int)

    def _row_1rm(i):
        if warm.iloc[i] == 1:
            return None
        return estimate_1rm(df["effective_load_kg"].iloc[i], df["reps"].iloc[i], formula)

    df["est_1rm_kg"] = [_row_1rm(i) for i in range(len(df))]
    return df
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_analysis.py -k enrich -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_strength_analysis.py
git commit -m "feat(strength): enrich_strength_sets

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: analysis.summarize_sessions

**Files:**
- Modify: `analysis.py`
- Test: `tests/test_strength_analysis.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_strength_analysis.py`:

```python
def test_summarize_sessions_tonnage_and_top():
    sets = pd.DataFrame([
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"set_id": "b", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 5, "weight_kg": 60.0, "is_warmup": 1, "completed": 1},  # warmup excluded
    ])
    out = analysis.summarize_sessions(_sessions(), sets, _exercises())
    row = out.iloc[0]
    assert row["working_sets"] == 1
    assert row["total_volume_kg"] == 500.0     # 5 * 100 (warmup excluded)
    assert row["top_est_1rm_kg"] > 100


def test_summarize_sessions_empty():
    out = analysis.summarize_sessions(pd.DataFrame(), pd.DataFrame(), _exercises())
    assert out.empty
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_analysis.py -k summarize -v`
Expected: FAIL — `AttributeError: ... 'summarize_sessions'`

- [ ] **Step 3: Append to the strength section of `analysis.py`**

```python


def summarize_sessions(sessions_df, sets_df, exercises_df, formula="epley"):
    """Per-session tonnage, working-set count, and top est-1RM. Pure."""
    cols = ["session_id", "date", "total_volume_kg", "working_sets", "top_est_1rm_kg"]
    if sessions_df is None or sessions_df.empty:
        return pd.DataFrame(columns=cols)

    enr = enrich_strength_sets(sets_df, sessions_df, exercises_df, formula)
    if not enr.empty:
        warm = pd.to_numeric(enr.get("is_warmup"), errors="coerce").fillna(0).astype(int)
        done = pd.to_numeric(enr.get("completed"), errors="coerce").fillna(1).astype(int)
        work = enr[(warm == 0) & (done == 1)]
    else:
        work = enr

    rows = []
    for _, s in sessions_df.iterrows():
        sid = s["session_id"]
        ss = work[work["session_id"] == sid] if not work.empty else work
        if ss.empty:
            rows.append({"session_id": sid, "date": s.get("date"),
                         "total_volume_kg": 0.0, "working_sets": 0,
                         "top_est_1rm_kg": None})
            continue
        reps = pd.to_numeric(ss["reps"], errors="coerce").fillna(0)
        load = pd.to_numeric(ss["effective_load_kg"], errors="coerce").fillna(0)
        tonnage = float((reps * load).sum())
        top = pd.to_numeric(ss["est_1rm_kg"], errors="coerce").max()
        rows.append({"session_id": sid, "date": s.get("date"),
                     "total_volume_kg": tonnage, "working_sets": int(len(ss)),
                     "top_est_1rm_kg": (None if pd.isna(top) else float(top))})
    return pd.DataFrame(rows, columns=cols)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_analysis.py -k summarize -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_strength_analysis.py
git commit -m "feat(strength): summarize_sessions

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: analysis.compute_pr_timeline

**Files:**
- Modify: `analysis.py`
- Test: `tests/test_strength_analysis.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_strength_analysis.py`:

```python
def test_pr_timeline_flags_new_records():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-06-01", "bodyweight_kg": 80.0},
        {"session_id": "s2", "date": "2026-06-03", "bodyweight_kg": 80.0},
        {"session_id": "s3", "date": "2026-06-05", "bodyweight_kg": 80.0},
    ])
    sets = pd.DataFrame([
        {"set_id": "a", "session_id": "s1", "exercise_id": "bench-press",
         "reps": 1, "weight_kg": 100.0, "is_warmup": 0, "completed": 1},
        {"set_id": "b", "session_id": "s2", "exercise_id": "bench-press",
         "reps": 1, "weight_kg": 95.0, "is_warmup": 0, "completed": 1},   # not a PR
        {"set_id": "c", "session_id": "s3", "exercise_id": "bench-press",
         "reps": 1, "weight_kg": 105.0, "is_warmup": 0, "completed": 1},  # PR
    ])
    out = analysis.compute_pr_timeline(sets, sessions, _exercises()).sort_values("date")
    flags = list(out["is_pr"])
    assert flags == [True, False, True]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_analysis.py -k pr_timeline -v`
Expected: FAIL — `AttributeError: ... 'compute_pr_timeline'`

- [ ] **Step 3: Append to the strength section of `analysis.py`**

```python


def compute_pr_timeline(sets_df, sessions_df, exercises_df, formula="epley"):
    """Best est-1RM per exercise per session over time, with a PR flag. Pure."""
    cols = ["exercise_id", "date", "session_id", "best_est_1rm_kg", "is_pr"]
    if (sessions_df is None or sessions_df.empty
            or sets_df is None or sets_df.empty):
        return pd.DataFrame(columns=cols)

    enr = enrich_strength_sets(sets_df, sessions_df, exercises_df, formula)
    enr = enr.merge(sessions_df[["session_id", "date"]], on="session_id",
                    how="left", suffixes=("", "_sess"))
    enr = enr.dropna(subset=["est_1rm_kg"])
    if enr.empty:
        return pd.DataFrame(columns=cols)

    grp = (enr.groupby(["exercise_id", "session_id", "date"], as_index=False)
              ["est_1rm_kg"].max()
              .rename(columns={"est_1rm_kg": "best_est_1rm_kg"}))
    grp = grp.sort_values(["exercise_id", "date"])
    grp["prev_max"] = grp.groupby("exercise_id")["best_est_1rm_kg"].cummax().shift(1)
    # cummax().shift(1) leaks across exercises at the boundary; re-mask first row
    grp["is_first"] = ~grp.duplicated("exercise_id")
    grp["is_pr"] = grp["is_first"] | (grp["best_est_1rm_kg"] > grp["prev_max"])
    return grp[cols].reset_index(drop=True)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_analysis.py -k pr_timeline -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_strength_analysis.py
git commit -m "feat(strength): compute_pr_timeline

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: analysis.readiness_snapshot_from_daily

**Files:**
- Modify: `analysis.py`
- Test: `tests/test_strength_analysis.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_strength_analysis.py`:

```python
def test_readiness_snapshot_maps_fields():
    row = pd.Series({
        "training_readiness_score": 72,
        "training_readiness_level": "READY",
        "hrv_status": "BALANCED",
        "hrv_overnight_avg": 58,
        "body_battery_start": 84,
        "sleep_score": 80,
        "resting_hr": 48,
        "acwr": 1.1,
    })
    snap = analysis.readiness_snapshot_from_daily(row)
    assert snap["readiness_score"] == 72
    assert snap["readiness_level"] == "READY"
    assert snap["acwr"] == 1.1


def test_readiness_snapshot_handles_none_and_nan():
    snap = analysis.readiness_snapshot_from_daily(None)
    assert snap["readiness_score"] is None
    row = pd.Series({"training_readiness_score": float("nan")})
    assert analysis.readiness_snapshot_from_daily(row)["readiness_score"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_analysis.py -k readiness -v`
Expected: FAIL — `AttributeError: ... 'readiness_snapshot_from_daily'`

- [ ] **Step 3: Append to the strength section of `analysis.py`**

```python


def readiness_snapshot_from_daily(daily_row):
    """Map an enriched daily-metrics row -> session readiness snapshot dict.

    daily_row may be a pandas Series, a dict, or None. Returns the eight
    snapshot keys, None where missing/NaN. Pure — caller does the DB read/write.
    """
    def g(key):
        if daily_row is None:
            return None
        try:
            val = daily_row[key]
        except (KeyError, IndexError, TypeError):
            return None
        if val is None:
            return None
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        return val

    return {
        "readiness_score": g("training_readiness_score"),
        "readiness_level": g("training_readiness_level"),
        "hrv_status": g("hrv_status"),
        "hrv_overnight_avg": g("hrv_overnight_avg"),
        "body_battery_start": g("body_battery_start"),
        "sleep_score": g("sleep_score"),
        "resting_hr": g("resting_hr"),
        "acwr": g("acwr"),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_analysis.py -v`
Expected: PASS (all strength_analysis tests pass)

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_strength_analysis.py
git commit -m "feat(strength): readiness_snapshot_from_daily

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Garmin weigh-in + profile ingest

**Files:**
- Modify: `ingest.py` (add helpers + functions; wire into `backfill`)
- Test: `tests/test_strength_ingest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_strength_ingest.py`:

```python
import importlib
import tempfile

import config
import db
import ingest


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    importlib.reload(db)
    db.config.DB_PATH = tmp.name
    db.init_db()


class FakeClient:
    def get_body_composition(self, start, end):
        return {"dateWeightList": [
            {"calendarDate": "2026-06-05", "weight": 80500.0, "bodyFat": 16.2},
            {"calendarDate": "2026-06-04", "weight": 80700.0},
        ]}

    def get_user_profile(self):
        return {"userData": {"gender": "MALE", "birthDate": "1995-03-10",
                             "height": 182.0}}


def test_ingest_body_metrics_maps_grams_to_kg():
    _fresh_db()
    n = ingest.ingest_body_metrics(FakeClient(), "2026-06-04", "2026-06-05")
    assert n == 2
    bm = db.load_body_metrics_df()
    row = bm[bm["date"].astype(str).str.startswith("2026-06-05")].iloc[0]
    assert abs(row["weight_kg"] - 80.5) < 1e-6
    assert row["source"] == "garmin"


def test_ingest_profile_extracts_sex_and_birth_year():
    _fresh_db()
    ingest.ingest_profile(FakeClient())
    prof = db.load_profile()
    assert prof["sex"] == "male"
    assert prof["birth_year"] == 1995
    assert abs(prof["height_cm"] - 182.0) < 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_ingest.py -v`
Expected: FAIL — `AttributeError: module 'ingest' has no attribute 'ingest_body_metrics'`

- [ ] **Step 3: Add helpers + ingest functions to `ingest.py`**

After the `safe(...)` function (around line 44), add:

```python
def _call_first(client, names, *args):
    """Call the first existing client method from `names` (handles garminconnect
    version drift in method naming). Returns None if none exist or all error."""
    for name in names:
        fn = getattr(client, name, None)
        if callable(fn):
            return safe(fn, *args)
    return None


def _grams_to_kg(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    # Garmin reports body weights in grams. Tolerate already-kg payloads.
    return v / 1000.0 if v > 1000 else v


def _norm_sex(value):
    if not value:
        return None
    low = str(value).strip().lower()
    if low.startswith("m"):
        return "male"
    if low.startswith("f") or low.startswith("w"):
        return "female"
    return None


def _year_from(value):
    if not value:
        return None
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None
```

Then, after `ingest_activities(...)` (around line 237), add:

```python
def ingest_body_metrics(client, start: str, end: str) -> int:
    """Pull Garmin weigh-ins / body composition for a date range into
    body_metrics. Stores the raw payload and dig()s out per-day values."""
    data = _call_first(client, ["get_body_composition", "get_weigh_ins"], start, end)
    if not data:
        return 0
    db.save_raw(end, "body_composition", data)
    entries = dig(data, "dateWeightList", "dailyWeightSummaries") or []
    if not isinstance(entries, list):
        entries = []
    n = 0
    for e in entries:
        cal = dig(e, "calendarDate", "date", "summaryDate")
        grams = dig(e, "weight", "weightInGrams")
        if cal is None or grams is None:
            continue
        db.upsert_body_metric({
            "date": str(cal)[:10],
            "weight_kg": _grams_to_kg(grams),
            "bmi": dig(e, "bmi"),
            "body_fat_pct": dig(e, "bodyFat", "bodyFatPercentage"),
            "muscle_mass_kg": _grams_to_kg(dig(e, "muscleMass")),
            "body_water_pct": dig(e, "bodyWater"),
            "bone_mass_kg": _grams_to_kg(dig(e, "boneMass")),
            "source": "garmin",
        })
        n += 1
    return n


def ingest_profile(client) -> None:
    """Pull the Garmin user profile (sex / birth year / height) into profile.
    Won't overwrite a manual/.env profile (db.upsert_profile enforces this)."""
    data = _call_first(client, ["get_user_profile", "get_userprofile",
                                "get_personal_information"])
    if not data:
        return
    db.save_raw(date.today().isoformat(), "user_profile", data)
    db.upsert_profile({
        "sex": _norm_sex(dig(data, "userData.gender", "gender")),
        "birth_year": _year_from(dig(data, "userData.birthDate", "birthDate")),
        "height_cm": dig(data, "userData.height", "height"),
        "source": "garmin",
    })
```

- [ ] **Step 4: Wire into `backfill`**

In `ingest.py`, in `backfill()` (around line 282), after the
`n = ingest_activities(...)` / `print(f"Stored {n} activities. Done.")` lines,
replace that `print` and add the new calls so it reads:

```python
    n = ingest_activities(client, start.isoformat(), today.isoformat())
    print(f"Stored {n} activities.")
    n_bm = ingest_body_metrics(client, start.isoformat(), today.isoformat())
    print(f"Stored {n_bm} body-metric day(s).")
    ingest_profile(client)
    print("Done.")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_ingest.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add ingest.py tests/test_strength_ingest.py
git commit -m "feat(strength): ingest Garmin weigh-ins + profile

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: cockpit.py render helpers

**Files:**
- Modify: `cockpit.py` (append helpers at end)
- Test: `tests/test_strength_cockpit.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_strength_cockpit.py`:

```python
import pandas as pd
import plotly.graph_objects as go

import cockpit


def test_readiness_badge_renders_value():
    html = cockpit.strength_readiness_badge({
        "readiness_score": 72, "readiness_level": "READY",
        "hrv_status": "BALANCED", "body_battery_start": 84,
    })
    assert isinstance(html, str)
    assert "72" in html
    assert "READY" in html


def test_readiness_badge_handles_empty():
    html = cockpit.strength_readiness_badge({})
    assert isinstance(html, str)
    assert "—" in html or "-" in html


def test_session_card_renders_tonnage():
    html = cockpit.strength_session_card(
        {"name": "Push Day", "date": "2026-06-05"},
        {"total_volume_kg": 5000.0, "working_sets": 12, "top_est_1rm_kg": 120.0},
    )
    assert "Push Day" in html
    assert "5000" in html or "5,000" in html


def test_onerm_trend_returns_figure():
    df = pd.DataFrame([
        {"date": "2026-06-01", "best_est_1rm_kg": 100.0, "is_pr": True},
        {"date": "2026-06-05", "best_est_1rm_kg": 105.0, "is_pr": True},
    ])
    fig = cockpit.strength_onerm_trend(df, "Bench Press")
    assert isinstance(fig, go.Figure)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_cockpit.py -v`
Expected: FAIL — `AttributeError: module 'cockpit' has no attribute 'strength_readiness_badge'`

- [ ] **Step 3: Append helpers to `cockpit.py`**

At the end of `cockpit.py`, add (reusing the existing module-level color tokens
`SURFACE`, `TEXT`, `TEXT_DIM`, `ACCENT`, `SERIES2`, `BG`):

```python


# ── Strength logger render helpers ────────────────────────────────────────────
def _fmt(value, suffix="", dash="—"):
    if value is None:
        return dash
    try:
        if pd.isna(value):
            return dash
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        return f"{value:,.0f}{suffix}"
    return f"{html.escape(str(value))}{suffix}"


def strength_readiness_badge(snapshot: dict) -> str:
    """Compact readiness badge for a session, from its stored snapshot dict."""
    snapshot = snapshot or {}
    score = _fmt(snapshot.get("readiness_score"))
    level = _fmt(snapshot.get("readiness_level"))
    hrv = _fmt(snapshot.get("hrv_status"))
    bb = _fmt(snapshot.get("body_battery_start"))
    return (
        f"<div style='display:flex;gap:14px;align-items:center;"
        f"background:{SURFACE};border-radius:10px;padding:8px 14px;"
        f"font-family:IBM Plex Mono,monospace;color:{TEXT_DIM};font-size:12px'>"
        f"<span style='color:{ACCENT};font-size:18px;font-weight:600'>{score}</span>"
        f"<span>{level}</span><span>HRV {hrv}</span><span>BB {bb}</span></div>"
    )


def strength_session_card(session: dict, summary: dict) -> str:
    """Header card for one logged session."""
    session = session or {}
    summary = summary or {}
    name = html.escape(str(session.get("name") or "Workout"))
    day = html.escape(str(session.get("date") or ""))
    vol = _fmt(summary.get("total_volume_kg"), " kg")
    sets = _fmt(summary.get("working_sets"))
    top = _fmt(summary.get("top_est_1rm_kg"), " kg")
    return (
        f"<div style='background:{SURFACE};border-radius:12px;padding:14px 18px;"
        f"color:{TEXT};font-family:Hanken Grotesk,sans-serif'>"
        f"<div style='font-size:18px;font-weight:600'>{name}"
        f"<span style='color:{TEXT_DIM};font-weight:400;font-size:13px'> · {day}</span></div>"
        f"<div style='color:{TEXT_DIM};font-size:13px;margin-top:6px'>"
        f"Volume <b style='color:{TEXT}'>{vol}</b> · "
        f"Sets <b style='color:{TEXT}'>{sets}</b> · "
        f"Top est-1RM <b style='color:{SERIES2}'>{top}</b></div></div>"
    )


def strength_onerm_trend(df, exercise_name: str):
    """Plotly line of best est-1RM over time, PRs marked. df: date,
    best_est_1rm_kg, is_pr."""
    fig = go.Figure()
    if df is not None and not df.empty:
        d = df.sort_values("date")
        fig.add_trace(go.Scatter(
            x=list(d["date"]), y=list(d["best_est_1rm_kg"]),
            mode="lines+markers", line=dict(color=ACCENT, width=2),
            marker=dict(size=6, color=ACCENT), name="est 1RM",
        ))
        prs = d[d["is_pr"] == True]  # noqa: E712
        if not prs.empty:
            fig.add_trace(go.Scatter(
                x=list(prs["date"]), y=list(prs["best_est_1rm_kg"]),
                mode="markers", marker=dict(size=11, color=SERIES2,
                                            symbol="star"), name="PR",
            ))
    fig.update_layout(
        title=f"{exercise_name} — estimated 1RM",
        paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=TEXT),
        margin=dict(l=40, r=20, t=40, b=30), height=300,
        showlegend=False,
    )
    return fig
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_cockpit.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add cockpit.py tests/test_strength_cockpit.py
git commit -m "feat(strength): cockpit render helpers (badge, card, 1RM trend)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 11: Strength page — logger (start / add / log / finish + bodyweight)

**Files:**
- Create: `pages/01_Strength.py`

> This is Streamlit UI — not unit-tested. Verify by running the app (Step 3). The
> page reuses `db` + `analysis` for live totals and persistence (DRY).

- [ ] **Step 1: Create the page**

Create `pages/01_Strength.py`:

```python
"""Strength logger — Strong-style live workout logging on its own page.

Live state lives in st.session_state["active"] until you press Finish, which
persists the session + sets and stamps the readiness snapshot for the day.
"""
import uuid
import importlib
from datetime import datetime, date

import pandas as pd
import streamlit as st

import config
import db
import analysis
import cockpit
import strength_catalog

config = importlib.reload(config)
db = importlib.reload(db)
analysis = importlib.reload(analysis)
cockpit = importlib.reload(cockpit)
strength_catalog = importlib.reload(strength_catalog)

st.set_page_config(page_title="Strength — Hankø", page_icon="🏋️", layout="wide")
st.markdown(cockpit.CSS, unsafe_allow_html=True)

db.init_db()


@st.cache_data(ttl=60)
def load_catalog():
    return db.load_exercises_df()


def today_str():
    return date.today().isoformat()


def resolve_bodyweight(day: str):
    """Bodyweight for `day` from body_metrics, forward-filled from the most
    recent prior weigh-in."""
    bm = db.load_body_metrics_df()
    if bm.empty:
        return None
    bm = bm.copy()
    bm["date"] = bm["date"].astype(str).str[:10]
    bm = bm[bm["date"] <= day].sort_values("date")
    if bm.empty:
        return None
    val = bm.iloc[-1]["weight_kg"]
    return None if pd.isna(val) else float(val)


def todays_readiness_snapshot(day: str) -> dict:
    daily = analysis.enrich_daily(db.load_daily_df())
    if not daily.empty:
        daily = analysis.compute_acwr(db.load_activities_df(), daily)
    if daily.empty:
        return analysis.readiness_snapshot_from_daily(None)
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    match = daily[daily["date"].dt.strftime("%Y-%m-%d") == day]
    row = match.iloc[-1] if not match.empty else None
    return analysis.readiness_snapshot_from_daily(row)


def active_to_frames(active: dict):
    """Build (sessions_df, sets_df) from in-memory active state for live totals."""
    sessions = pd.DataFrame([{
        "session_id": active["session_id"], "date": active["date"],
        "bodyweight_kg": active.get("bodyweight_kg") or 0.0,
    }])
    rows = []
    for ex in active["exercises"]:
        for s in ex["sets"]:
            rows.append({
                "set_id": s["set_id"], "session_id": active["session_id"],
                "exercise_id": ex["exercise_id"], "position": ex["position"],
                "set_index": s["set_index"], "side": s["side"],
                "reps": s["reps"], "weight_kg": s["weight_kg"],
                "rpe": s.get("rpe"), "is_warmup": s["is_warmup"],
                "completed": s["completed"],
            })
    sets = pd.DataFrame(rows)
    return sessions, sets


# ── page ──────────────────────────────────────────────────────────────────────
st.title("🏋️ Strength")

catalog = load_catalog()

tab_log, tab_body = st.tabs(["Log workout", "Bodyweight"])

with tab_body:
    st.subheader("Bodyweight")
    day = today_str()
    current = resolve_bodyweight(day)
    st.caption("Synced from Garmin weigh-ins; override manually below if needed.")
    st.metric("Current bodyweight", f"{current:.1f} kg" if current else "—")
    with st.form("bw_form"):
        manual = st.number_input("Manual bodyweight (kg)", min_value=0.0,
                                 max_value=400.0, step=0.1,
                                 value=float(current or 0.0))
        if st.form_submit_button("Save manual weight") and manual > 0:
            db.upsert_body_metric({"date": day, "weight_kg": float(manual),
                                   "source": "manual"})
            st.success(f"Saved {manual:.1f} kg for {day}.")
            st.rerun()

with tab_log:
    active = st.session_state.get("active")

    if active is None:
        st.subheader("Start a workout")
        name = st.text_input("Workout name", value="Workout")
        if st.button("▶ Start", type="primary"):
            st.session_state["active"] = {
                "session_id": str(uuid.uuid4()),
                "name": name or "Workout",
                "date": today_str(),
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "bodyweight_kg": resolve_bodyweight(today_str()),
                "exercises": [],
            }
            st.rerun()
        st.stop()

    # ── active workout ──
    st.subheader(f"🟢 {active['name']} — {active['date']}")
    sessions_df, sets_df = active_to_frames(active)
    summary = analysis.summarize_sessions(sessions_df, sets_df, catalog,
                                          config.ONE_RM_FORMULA)
    s = summary.iloc[0] if not summary.empty else {}
    c1, c2, c3 = st.columns(3)
    c1.metric("Volume", f"{(s.get('total_volume_kg') or 0):,.0f} kg")
    c2.metric("Working sets", int(s.get("working_sets") or 0))
    top = s.get("top_est_1rm_kg")
    c3.metric("Top est-1RM", f"{top:,.0f} kg" if top else "—")

    # add exercise
    names = catalog["name"].tolist() if not catalog.empty else []
    pick = st.selectbox("Add exercise", [""] + names)
    if st.button("➕ Add to workout") and pick:
        ex_row = catalog[catalog["name"] == pick].iloc[0]
        active["exercises"].append({
            "position": len(active["exercises"]),
            "exercise_id": ex_row["exercise_id"],
            "name": ex_row["name"],
            "is_unilateral": int(ex_row["is_unilateral"]),
            "is_bodyweight": int(ex_row["is_bodyweight"]),
            "sets": [],
        })
        st.rerun()

    with st.expander("➕ New custom exercise"):
        cx_name = st.text_input("Name", key="cx_name")
        cx_cat = st.selectbox(
            "Category", ["barbell", "dumbbell", "machine", "cable", "bodyweight"],
            key="cx_cat")
        cx_pat = st.selectbox("Movement pattern",
                              list(strength_catalog.MOVEMENT_PATTERNS), key="cx_pat")
        cx_muscle = st.text_input("Primary muscle", key="cx_muscle")
        cx_uni = st.checkbox("Unilateral (log left/right)", key="cx_uni")
        cx_bw = st.checkbox("Bodyweight exercise", key="cx_bw")
        if st.button("Create exercise") and cx_name.strip():
            slug = "custom-" + "".join(
                c if c.isalnum() else "-" for c in cx_name.strip().lower()
            ).strip("-")
            db.upsert_exercise({
                "exercise_id": slug, "name": cx_name.strip(), "category": cx_cat,
                "movement_pattern": cx_pat, "primary_muscle": cx_muscle.strip(),
                "is_unilateral": int(cx_uni), "is_bodyweight": int(cx_bw),
                "is_main_lift": 0, "is_custom": 1,
            })
            load_catalog.clear()
            st.success(f"Added {cx_name.strip()}.")
            st.rerun()

    # per-exercise set logging
    for ei, ex in enumerate(active["exercises"]):
        st.markdown(f"**{ex['name']}**")
        if ex["sets"]:
            st.table(pd.DataFrame([{
                "set": s["set_index"], "side": s["side"], "reps": s["reps"],
                "kg": s["weight_kg"], "rpe": s.get("rpe"),
                "warmup": bool(s["is_warmup"]),
            } for s in ex["sets"]]))
        cols = st.columns([1, 1, 1, 1, 1])
        reps = cols[0].number_input("reps", 0, 100, 5, key=f"r{ei}")
        wt = cols[1].number_input("kg", 0.0, 500.0, 20.0, step=1.0, key=f"w{ei}")
        rpe = cols[2].number_input("RPE", 0.0, 10.0, 0.0, step=0.5, key=f"e{ei}")
        warm = cols[3].checkbox("warmup", key=f"wu{ei}")
        side = "both"
        if ex["is_unilateral"]:
            side = cols[4].selectbox("side", ["left", "right"], key=f"sd{ei}")
        if st.button("Add set", key=f"add{ei}"):
            ex["sets"].append({
                "set_id": str(uuid.uuid4()),
                "set_index": len(ex["sets"]) + 1, "side": side,
                "reps": int(reps), "weight_kg": float(wt),
                "rpe": (float(rpe) or None), "is_warmup": int(warm),
                "completed": 1,
            })
            st.rerun()
        if ex["sets"] and st.button("Remove last set", key=f"rm{ei}"):
            ex["sets"].pop()
            st.rerun()

    st.divider()
    fcol1, fcol2 = st.columns(2)
    if fcol1.button("✅ Finish & save", type="primary"):
        snap = todays_readiness_snapshot(active["date"])
        db.upsert_strength_session({
            "session_id": active["session_id"], "date": active["date"],
            "started_at": active["started_at"],
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            "name": active["name"], "bodyweight_kg": active.get("bodyweight_kg"),
            **snap,
        })
        for ex in active["exercises"]:
            for stt in ex["sets"]:
                db.upsert_strength_set({
                    "set_id": stt["set_id"], "session_id": active["session_id"],
                    "exercise_id": ex["exercise_id"], "position": ex["position"],
                    "set_index": stt["set_index"], "side": stt["side"],
                    "reps": stt["reps"], "weight_kg": stt["weight_kg"],
                    "rpe": stt.get("rpe"), "is_warmup": stt["is_warmup"],
                    "completed": stt["completed"],
                })
        del st.session_state["active"]
        st.success("Workout saved.")
        st.rerun()
    if fcol2.button("🗑 Discard"):
        del st.session_state["active"]
        st.rerun()
```

- [ ] **Step 2: Verify the page imports cleanly (no Streamlit runtime needed)**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -c "import ast; ast.parse(open('pages/01_Strength.py').read()); print('parse ok')"`
Expected: `parse ok`

- [ ] **Step 3: Verify in the running app**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && streamlit run app.py` (then open the browser, click "Strength" in the sidebar)
Expected: A "Strength" page appears. You can: set a manual bodyweight, Start a workout, Add an exercise, Add sets (volume/top-1RM metrics update), Finish & save without error.

- [ ] **Step 4: Commit**

```bash
git add pages/01_Strength.py
git commit -m "feat(strength): live logger page (start/add/log/finish + bodyweight)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 12: Strength page — history + 1RM trend

**Files:**
- Modify: `pages/01_Strength.py` (add a History tab)

- [ ] **Step 1: Add a History tab**

In `pages/01_Strength.py`, change the tabs line:

```python
tab_log, tab_body = st.tabs(["Log workout", "Bodyweight"])
```

to:

```python
tab_log, tab_history, tab_body = st.tabs(["Log workout", "History", "Bodyweight"])
```

Then, immediately **before** the `with tab_body:` block, add:

```python
with tab_history:
    st.subheader("History")
    sessions = db.load_strength_sessions_df()
    sets = db.load_strength_sets_df()
    if sessions.empty:
        st.info("No workouts logged yet.")
    else:
        summaries = analysis.summarize_sessions(sessions, sets, catalog,
                                                config.ONE_RM_FORMULA)
        sm = {r["session_id"]: r for _, r in summaries.iterrows()}
        for _, sess in sessions.sort_values("date", ascending=False).iterrows():
            summ = sm.get(sess["session_id"], {})
            st.markdown(cockpit.strength_session_card(dict(sess), dict(summ)),
                        unsafe_allow_html=True)
            snap = {k: sess.get(k) for k in (
                "readiness_score", "readiness_level", "hrv_status",
                "body_battery_start")}
            st.markdown(cockpit.strength_readiness_badge(snap),
                        unsafe_allow_html=True)
            with st.expander("Sets"):
                ssets = sets[sets["session_id"] == sess["session_id"]]
                if ssets.empty:
                    st.caption("No sets.")
                else:
                    named = ssets.merge(
                        catalog[["exercise_id", "name"]], on="exercise_id",
                        how="left")
                    st.table(named[["name", "set_index", "side", "reps",
                                    "weight_kg", "rpe", "is_warmup"]])
            st.write("")

        st.divider()
        st.subheader("Estimated 1RM progress")
        prs = analysis.compute_pr_timeline(sets, sessions, catalog,
                                           config.ONE_RM_FORMULA)
        if prs.empty:
            st.caption("Log a few working sets to see 1RM trends.")
        else:
            id_to_name = dict(zip(catalog["exercise_id"], catalog["name"])) \
                if not catalog.empty else {}
            ex_ids = list(prs["exercise_id"].unique())
            choices = {id_to_name.get(i, i): i for i in ex_ids}
            label = st.selectbox("Exercise", list(choices.keys()))
            ex_id = choices[label]
            fig = cockpit.strength_onerm_trend(
                prs[prs["exercise_id"] == ex_id], label)
            st.plotly_chart(fig, use_container_width=True)
```

- [ ] **Step 2: Verify it parses**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -c "import ast; ast.parse(open('pages/01_Strength.py').read()); print('parse ok')"`
Expected: `parse ok`

- [ ] **Step 3: Verify in the running app**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && streamlit run app.py`
Expected: After logging at least one workout, the "History" tab shows the session card + readiness badge, an expandable Sets table, and a per-exercise estimated-1RM chart with PRs marked.

- [ ] **Step 4: Commit**

```bash
git add pages/01_Strength.py
git commit -m "feat(strength): history tab + 1RM progress chart

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 13: Routines (templates) — start-from-routine + save-as-routine

**Files:**
- Modify: `pages/01_Strength.py`

> Adds the routines half of the spec: start a workout pre-populated from a saved
> routine, and save the current workout's exercises as a reusable routine.

- [ ] **Step 1: Add routine helpers**

In `pages/01_Strength.py`, immediately **after** the `active_to_frames(...)`
function definition, add:

```python
def routine_to_exercises(routine_id: str):
    """Build active-state exercise entries (empty sets) from a saved routine."""
    rex = db.load_routine_exercises_df()
    rex = rex[rex["routine_id"] == routine_id].sort_values("position")
    cat = db.load_exercises_df()
    out = []
    for pos, (_, r) in enumerate(rex.iterrows()):
        m = cat[cat["exercise_id"] == r["exercise_id"]]
        if m.empty:
            continue
        ex = m.iloc[0]
        out.append({
            "position": pos,
            "exercise_id": ex["exercise_id"],
            "name": ex["name"],
            "is_unilateral": int(ex["is_unilateral"]),
            "is_bodyweight": int(ex["is_bodyweight"]),
            "sets": [],
        })
    return out


def save_active_as_routine(active: dict, routine_name: str) -> str:
    """Persist the active workout's exercises as a reusable routine."""
    rid = str(uuid.uuid4())
    db.upsert_routine({"routine_id": rid, "name": routine_name})
    for pos, ex in enumerate(active["exercises"]):
        work = [s for s in ex["sets"] if not s["is_warmup"]]
        first = work[0] if work else (ex["sets"][0] if ex["sets"] else None)
        db.upsert_routine_exercise({
            "routine_id": rid, "position": pos,
            "exercise_id": ex["exercise_id"],
            "target_sets": (len(work) or len(ex["sets"]) or None),
            "target_reps": (first["reps"] if first else None),
            "target_weight": (first["weight_kg"] if first else None),
        })
    return rid
```

- [ ] **Step 2: Add routine selection to the "Start a workout" block**

Replace the entire `if active is None:` block (the "Start a workout" section,
ending with `st.stop()`) with:

```python
    if active is None:
        st.subheader("Start a workout")
        name = st.text_input("Workout name", value="Workout")
        routines = db.load_routines_df()
        routine_names = routines["name"].tolist() if not routines.empty else []
        chosen = st.selectbox("From routine (optional)",
                              ["— blank —"] + routine_names)
        if st.button("▶ Start", type="primary"):
            exercises, routine_id, start_name = [], None, (name or "Workout")
            if chosen != "— blank —" and not routines.empty:
                rrow = routines[routines["name"] == chosen].iloc[0]
                routine_id = rrow["routine_id"]
                start_name = chosen
                exercises = routine_to_exercises(routine_id)
            st.session_state["active"] = {
                "session_id": str(uuid.uuid4()),
                "name": start_name,
                "date": today_str(),
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "bodyweight_kg": resolve_bodyweight(today_str()),
                "routine_id": routine_id,
                "exercises": exercises,
            }
            st.rerun()
        st.stop()
```

- [ ] **Step 3: Persist `routine_id` on finish + add a "Save as routine" control**

In the Finish/Discard area, replace this block:

```python
    st.divider()
    fcol1, fcol2 = st.columns(2)
    if fcol1.button("✅ Finish & save", type="primary"):
        snap = todays_readiness_snapshot(active["date"])
        db.upsert_strength_session({
            "session_id": active["session_id"], "date": active["date"],
            "started_at": active["started_at"],
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            "name": active["name"], "bodyweight_kg": active.get("bodyweight_kg"),
            **snap,
        })
```

with:

```python
    st.divider()
    with st.expander("💾 Save this workout as a routine"):
        rname = st.text_input("Routine name", value=active["name"], key="save_rt")
        if st.button("Save routine") and active["exercises"] and rname.strip():
            save_active_as_routine(active, rname.strip())
            st.success(f"Saved routine “{rname.strip()}”.")

    fcol1, fcol2 = st.columns(2)
    if fcol1.button("✅ Finish & save", type="primary"):
        snap = todays_readiness_snapshot(active["date"])
        db.upsert_strength_session({
            "session_id": active["session_id"], "date": active["date"],
            "started_at": active["started_at"],
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            "name": active["name"], "bodyweight_kg": active.get("bodyweight_kg"),
            "routine_id": active.get("routine_id"),
            **snap,
        })
```

- [ ] **Step 4: Verify it parses**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -c "import ast; ast.parse(open('pages/01_Strength.py').read()); print('parse ok')"`
Expected: `parse ok`

- [ ] **Step 5: Verify in the running app**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && streamlit run app.py`
Expected: Log a workout, "Save this workout as a routine" → it appears in the
"From routine" dropdown on the next blank start; starting from it pre-loads those
exercises (empty sets) ready to log.

- [ ] **Step 6: Commit**

```bash
git add pages/01_Strength.py
git commit -m "feat(strength): routines — start-from and save-as-routine

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 14: Full regression + manual end-to-end

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest -q`
Expected: All tests pass (existing + new strength tests). If a pre-existing test was already failing before this work, note it but don't block on it.

- [ ] **Step 2: Manual end-to-end smoke**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && streamlit run app.py`
Walk through:
1. Recovery cockpit (home page) still loads unchanged.
2. Strength → Bodyweight: set a manual weight, confirm it persists on rerun.
3. Strength → Log: Start → add Bench Press → add 2 working sets + 1 warmup → metrics update (warmup excluded from volume) → Finish & save.
4. Strength → History: session card shows tonnage; readiness badge shows today's Garmin readiness (or "—" if no data for today); Sets expander lists the sets; 1RM chart renders for Bench Press.

Expected: no exceptions in the terminal; data survives a page refresh.

- [ ] **Step 3: Commit any fixups**

```bash
git add -A
git commit -m "test(strength): phase 1 regression pass

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Done criteria (Phase 1)

- `pytest -q` green, no live network in tests.
- Strength tables + loaders/upserts in `db.py`, manual-protection on `body_metrics`/`profile`, idempotent `seed_exercises()`.
- Garmin weigh-in + profile ingest wired into `sync.py`'s `backfill`, raw stored, `dig()` mapping in place.
- Pure `analysis.py` strength functions implemented + unit-tested.
- `pages/01_Strength.py` live logger + history working, readiness snapshot stamped on save, `cockpit.py` helpers in the oxblood language.

## Phase 2 (separate spec — not in scope here)

Strength standards (vs population norms), muscle-balance asymmetry, readiness-vs-
performance correlation analytics, and AI integration (strength summary into
`analysis.summarize()` → readiness report + `ai.answer_question`).
