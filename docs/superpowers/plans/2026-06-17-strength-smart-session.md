# Smart Session — Strength + Recovery Advisory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a recovery-aware, advisory linear-progression layer to the strength logger — per-main-lift next-target suggestions, a daily recovery verdict, and one cached AI coach note — without ever auto-changing a logged number.

**Architecture:** All numeric work is pure functions in `analysis.py` (recovery signal, verdict, progression state machine, recovery↔performance analytics), tested in isolation. `ai.py` adds one natural-language coach note at the boundary. `db.py` gains four columns via idempotent migrations. `cockpit.py` renders, and `views/strength.py` wires it into the live logger (inline hints + Apply, header chip, coach note, Finish-time stamping).

**Tech Stack:** Python 3, pandas, SQLite (`db.py`), Streamlit (`views/strength.py`), Anthropic SDK (`ai.py`), pytest (`tests/`).

## Global Constraints

- **Advisory only** — recovery and suggestions never silently rewrite a logged weight/rep; every input stays editable.
- **No Garmin `training_readiness_score` dependency** — it is null in 100% of rows. `recovery_readiness` (derived) is the sole readiness source.
- **AI gets summaries, not raw data** — `ai.coach_session_note` receives already-summarized dicts only; never raw sets/series.
- **`analysis.py` stays pure** — no network, no DB, no AI, deterministic. Tests target it.
- **AI degrades silently** — every `ai.py` entry returns a safe value when `config.ANTHROPIC_API_KEY` is unset.
- **Idempotent migrations** — new columns added via guarded `ALTER TABLE … ADD COLUMN`; re-running `init_db()` is safe.
- **1RM formula** comes from `config.ONE_RM_FORMULA` (`"epley"` default).
- **Frequent commits** — one commit per task, message prefix `feat:`/`refactor:`/`test:`.

---

### Task 1: Data model — columns, seeds, migration

**Files:**
- Modify: `db.py` — `SCHEMA` (exercises + strength_sessions), `EXERCISE_COLS`, `SESSION_COLS`, `init_db()` migration + main-lift backfill.
- Modify: `strength_catalog.py` — `_ex()` signature + main-lift seeds.
- Test: `tests/test_strength_db.py` (append).

**Interfaces:**
- Produces: `exercises.increment_kg REAL`, `exercises.target_reps INTEGER`, `strength_sessions.recovery_score REAL`, `strength_sessions.recovery_zone TEXT`. Seeded main lifts (`back-squat`, `bench-press`, `deadlift`, `overhead-press`, `barbell-row`) carry `increment_kg` + `target_reps`. `db.upsert_exercise`/`upsert_strength_session` accept the new keys.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strength_db.py  (append)
import importlib

def test_init_db_adds_smart_session_columns(tmp_path, monkeypatch):
    import config
    dbfile = tmp_path / "t.db"
    monkeypatch.setattr(config, "DB_PATH", str(dbfile))
    import db
    importlib.reload(db)
    db.init_db()
    import sqlite3
    conn = sqlite3.connect(dbfile)
    ex_cols = {r[1] for r in conn.execute("PRAGMA table_info(exercises)")}
    se_cols = {r[1] for r in conn.execute("PRAGMA table_info(strength_sessions)")}
    assert {"increment_kg", "target_reps"} <= ex_cols
    assert {"recovery_score", "recovery_zone"} <= se_cols
    row = conn.execute(
        "SELECT increment_kg, target_reps FROM exercises WHERE exercise_id='back-squat'"
    ).fetchone()
    conn.close()
    assert row == (2.5, 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_strength_db.py::test_init_db_adds_smart_session_columns -v`
Expected: FAIL (columns absent / values None).

- [ ] **Step 3: Implement**

In `strength_catalog.py`, extend `_ex` and the five main-lift rows:

```python
def _ex(exercise_id, name, category, pattern, muscle,
        unilateral=0, bodyweight=0, main=0, increment_kg=None, target_reps=None):
    return {
        "exercise_id": exercise_id,
        "name": name,
        "category": category,
        "movement_pattern": pattern,
        "primary_muscle": muscle,
        "is_unilateral": unilateral,
        "is_bodyweight": bodyweight,
        "is_main_lift": main,
        "increment_kg": increment_kg,
        "target_reps": target_reps,
    }
```

Set the five main lifts (leave all others as-is, defaults `None`):

```python
_ex("back-squat", "Back Squat", "barbell", "squat", "quads", main=1, increment_kg=2.5, target_reps=5),
_ex("deadlift", "Deadlift", "barbell", "hinge", "hamstrings", main=1, increment_kg=2.5, target_reps=5),
_ex("bench-press", "Bench Press", "barbell", "horizontal_push", "chest", main=1, increment_kg=2.5, target_reps=5),
_ex("overhead-press", "Overhead Press", "barbell", "vertical_push", "shoulders", main=1, increment_kg=2.5, target_reps=5),
_ex("barbell-row", "Barbell Row", "barbell", "horizontal_pull", "back", main=1, increment_kg=2.5, target_reps=5),
```

In `db.py` `SCHEMA`, add the columns to the `CREATE TABLE` bodies (for fresh DBs):

```sql
-- exercises: after is_main_lift INTEGER DEFAULT 0,
    increment_kg REAL,
    target_reps INTEGER,
-- strength_sessions: after acwr REAL,
    recovery_score REAL,
    recovery_zone TEXT,
```

Extend the column lists:

```python
EXERCISE_COLS = [
    "exercise_id", "name", "category", "movement_pattern", "primary_muscle",
    "is_unilateral", "is_bodyweight", "is_main_lift", "is_custom",
    "increment_kg", "target_reps",
]
SESSION_COLS = [
    "session_id", "date", "started_at", "ended_at", "routine_id", "name",
    "bodyweight_kg", "notes", "readiness_score", "readiness_level",
    "hrv_status", "hrv_overnight_avg", "body_battery_start", "sleep_score",
    "resting_hr", "acwr", "recovery_score", "recovery_zone",
]
```

In `init_db()`, after the existing `coach_memory` migration block and before the closing of the `with connect()` block, add:

```python
        existing = {r[1] for r in conn.execute("PRAGMA table_info(exercises)")}
        for col, kind in (("increment_kg", "REAL"), ("target_reps", "INTEGER")):
            if col not in existing:
                conn.execute(f"ALTER TABLE exercises ADD COLUMN {col} {kind}")
        existing = {r[1] for r in conn.execute("PRAGMA table_info(strength_sessions)")}
        for col, kind in (("recovery_score", "REAL"), ("recovery_zone", "TEXT")):
            if col not in existing:
                conn.execute(f"ALTER TABLE strength_sessions ADD COLUMN {col} {kind}")
```

Update `seed_exercises()` so seeded INSERTs carry the two new columns, and add a NULL-only backfill so already-seeded main lifts get defaults without clobbering user edits:

```python
def seed_exercises():
    import strength_catalog
    with connect() as conn:
        for e in strength_catalog.EXERCISE_SEED:
            conn.execute(
                "INSERT OR IGNORE INTO exercises "
                "(exercise_id, name, category, movement_pattern, primary_muscle, "
                "is_unilateral, is_bodyweight, is_main_lift, increment_kg, target_reps) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (e["exercise_id"], e["name"], e["category"], e["movement_pattern"],
                 e["primary_muscle"], e["is_unilateral"], e["is_bodyweight"],
                 e["is_main_lift"], e.get("increment_kg"), e.get("target_reps")),
            )
        # NULL-only backfill: seeded main lifts created before these columns existed.
        for e in strength_catalog.EXERCISE_SEED:
            if e.get("increment_kg") is None:
                continue
            conn.execute(
                "UPDATE exercises SET increment_kg=?, target_reps=? "
                "WHERE exercise_id=? AND increment_kg IS NULL",
                (e["increment_kg"], e["target_reps"], e["exercise_id"]),
            )
```

> NOTE: keep the existing seed column order if it differs; the point is the two new columns are inserted and backfilled. If `seed_exercises` already lists explicit columns, append `increment_kg, target_reps` consistently.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_strength_db.py::test_init_db_adds_smart_session_columns -v`
Expected: PASS.

- [ ] **Step 5: Run the full strength-db + catalog suites (regression)**

Run: `pytest tests/test_strength_db.py tests/test_strength_catalog.py -q`
Expected: PASS (existing tests unaffected; update `test_strength_catalog.py` only if it asserts exact `_ex` dict keys — add the two new keys there if so).

- [ ] **Step 6: Commit**

```bash
git add db.py strength_catalog.py tests/test_strength_db.py tests/test_strength_catalog.py
git commit -m "feat: add increment/target-reps + session recovery columns"
```

---

### Task 2: Factor out `_recovery_risk` (refactor, no behavior change)

**Files:**
- Modify: `analysis.py` — extract `_recovery_risk(df)` from `_research_recovery_panel` (`analysis.py:1435`).
- Test: `tests/test_health_research.py` (append regression guard).

**Interfaces:**
- Produces: `analysis._recovery_risk(df) -> dict` with keys `status, zone, risk_score, flags, streak, suppressed_days, elevated_rhr_days, short_sleep_days`. `_research_recovery_panel` output is byte-for-byte unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_research.py  (append)
import pandas as pd
import analysis

def _recovery_df():
    # green-ish frame: enough signal columns present, no flags
    return pd.DataFrame({
        "date": pd.date_range("2026-05-20", periods=14, freq="D"),
        "hrv_overnight_avg": [60] * 14,
        "resting_hr": [50] * 14,
        "sleep_hours": [8.0] * 14,
        "hrv_flag": ["balanced"] * 14,
        "rhr_elevated": [False] * 14,
        "sleep_debt_h": [0.0] * 14,
        "stress_avg": [30] * 14,
        "body_battery_current": [70] * 14,
    })

def test_recovery_risk_returns_expected_shape():
    r = analysis._recovery_risk(_recovery_df())
    assert set(r) >= {"status", "zone", "risk_score", "flags", "streak",
                      "suppressed_days", "elevated_rhr_days", "short_sleep_days"}
    assert r["zone"] == "green"
    assert r["status"] == "ready"

def test_recovery_panel_unchanged_after_refactor():
    panel = analysis._research_recovery_panel(_recovery_df())
    assert panel["zone"] == "green"
    assert panel["status"] == "ready"
    assert panel["title"] == "Recovery and resilience"
    assert isinstance(panel["risk_score"], int)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_health_research.py -k recovery_risk -v`
Expected: FAIL with `AttributeError: module 'analysis' has no attribute '_recovery_risk'`.

- [ ] **Step 3: Implement the extraction**

Add `_recovery_risk` immediately above `_research_recovery_panel`:

```python
def _recovery_risk(df: pd.DataFrame) -> dict:
    """Primitive-signal recovery risk from an enriched daily frame. Pure.

    Uses the last row as 'today' and the trailing 14 rows as the window.
    Missing columns degrade gracefully (flag helpers guard None)."""
    latest = df.iloc[-1]
    recent = df.tail(14)
    flags = _research_recovery_flags(latest)
    flag_counts = recent.apply(_research_recovery_flag_count, axis=1)
    recovery_debt = flag_counts >= 2
    streak = _trailing_true_streak(recovery_debt)
    suppressed_days = int(
        (recent.get("hrv_flag", pd.Series(index=recent.index, dtype=object)) == "suppressed").sum())
    elevated_rhr_days = int(
        recent.get("rhr_elevated", pd.Series(False, index=recent.index)).fillna(False).astype(bool).sum())
    short_sleep_days = (
        int((pd.to_numeric(recent.get("sleep_debt_h"), errors="coerce") >= 1.0).sum())
        if "sleep_debt_h" in recent else 0)
    risk_score = min(100, len(flags) * 22 + streak * 8 + max(0, suppressed_days - 2) * 3)
    if len(flags) >= 3 or streak >= 2:
        zone = "red"
    elif flags or suppressed_days >= 3 or elevated_rhr_days >= 3 or short_sleep_days >= 3:
        zone = "yellow"
    else:
        zone = "green"
    status = "ready" if _has_any(df, ("hrv_overnight_avg", "resting_hr", "sleep_hours")) else "no_data"
    return {"status": status, "zone": zone, "risk_score": int(round(risk_score)),
            "flags": flags, "streak": streak, "suppressed_days": suppressed_days,
            "elevated_rhr_days": elevated_rhr_days, "short_sleep_days": short_sleep_days}
```

Then replace the top of `_research_recovery_panel` (the lines computing `flags`…`status`) with a single call, keeping the rest of the function (message + return dict) identical:

```python
def _research_recovery_panel(df: pd.DataFrame) -> dict:
    r = _recovery_risk(df)
    zone, status = r["zone"], r["status"]
    flags = r["flags"]
    risk_score = r["risk_score"]
    streak, suppressed_days = r["streak"], r["suppressed_days"]
    elevated_rhr_days, short_sleep_days = r["elevated_rhr_days"], r["short_sleep_days"]
    # ... unchanged: if status == "no_data": message = ...  (existing body) ...
```

(Leave the existing `message` branches and the returned dict exactly as they are.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_health_research.py -q`
Expected: PASS (both new and all pre-existing health-research tests).

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_health_research.py
git commit -m "refactor: extract _recovery_risk from recovery panel"
```

---

### Task 3: `recovery_readiness()` (pure)

**Files:**
- Modify: `analysis.py` — add `recovery_readiness`.
- Test: `tests/test_smart_session.py` (create).

**Interfaces:**
- Consumes: `analysis._recovery_risk` (Task 2).
- Produces: `analysis.recovery_readiness(daily, as_of=None) -> {"status": "ready"|"no_data", "zone": "green"|"yellow"|"red", "value": int, "reasons": list[str]}`. `value` = `100 - risk_score`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smart_session.py  (create)
import pandas as pd
import analysis

def _green_daily():
    return pd.DataFrame({
        "date": pd.date_range("2026-05-20", periods=14, freq="D"),
        "hrv_overnight_avg": [60] * 14, "resting_hr": [50] * 14,
        "sleep_hours": [8.0] * 14, "hrv_flag": ["balanced"] * 14,
        "rhr_elevated": [False] * 14, "sleep_debt_h": [0.0] * 14,
        "stress_avg": [30] * 14, "body_battery_current": [70] * 14,
    })

def _red_daily():
    df = _green_daily()
    df["hrv_flag"] = ["suppressed"] * 14
    df["rhr_elevated"] = [True] * 14
    df["sleep_debt_h"] = [2.0] * 14
    df["stress_avg"] = [70] * 14
    df["body_battery_current"] = [20] * 14
    return df

def test_recovery_readiness_green():
    r = analysis.recovery_readiness(_green_daily())
    assert r["status"] == "ready"
    assert r["zone"] == "green"
    assert r["value"] == 100

def test_recovery_readiness_red_has_reasons():
    r = analysis.recovery_readiness(_red_daily())
    assert r["zone"] == "red"
    assert r["value"] < 100
    assert len(r["reasons"]) >= 1

def test_recovery_readiness_no_data():
    r = analysis.recovery_readiness(pd.DataFrame())
    assert r["status"] == "no_data"
    assert r["zone"] == "green"

def test_recovery_readiness_as_of_slices():
    df = _green_daily()
    df.loc[df.index[-1], "hrv_flag"] = "suppressed"  # only the last day is bad
    early = analysis.recovery_readiness(df, as_of="2026-05-25")
    assert early["zone"] == "green"  # the bad last day is excluded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smart_session.py -k recovery_readiness -v`
Expected: FAIL (`recovery_readiness` undefined).

- [ ] **Step 3: Implement**

```python
def recovery_readiness(daily, as_of=None):
    """Reusable recovery signal from an enriched daily frame. Pure.

    Returns zone (green/yellow/red), an inverted 0-100 readiness value
    (higher = readier), and human-readable reasons. `as_of` (date or
    'YYYY-MM-DD') limits the frame to rows on/before that date."""
    if daily is None or getattr(daily, "empty", True):
        return {"status": "no_data", "zone": "green", "value": 100, "reasons": []}
    df = daily.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date")
        if as_of is not None:
            df = df[df["date"] <= pd.to_datetime(as_of)]
    if df.empty:
        return {"status": "no_data", "zone": "green", "value": 100, "reasons": []}

    r = _recovery_risk(df)
    value = max(0, min(100, 100 - r["risk_score"]))
    reasons = list(r["flags"])
    if not reasons:
        if r["suppressed_days"] >= 3:
            reasons.append(f"HRV suppressed {r['suppressed_days']} of last 14 nights")
        if r["elevated_rhr_days"] >= 3:
            reasons.append(f"resting HR elevated {r['elevated_rhr_days']} of last 14 days")
        if r["short_sleep_days"] >= 3:
            reasons.append(f"short sleep {r['short_sleep_days']} of last 14 nights")
    if not reasons and r["zone"] == "green":
        reasons = ["recovery primitives inside baseline"]
    return {"status": r["status"], "zone": r["zone"], "value": int(value),
            "reasons": reasons[:3]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_smart_session.py -k recovery_readiness -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_smart_session.py
git commit -m "feat: recovery_readiness derived recovery signal"
```

---

### Task 4: `readiness_verdict()` (pure)

**Files:**
- Modify: `analysis.py` — add `readiness_verdict`.
- Test: `tests/test_smart_session.py` (append).

**Interfaces:**
- Consumes: a `recovery_readiness` dict (Task 3).
- Produces: `analysis.readiness_verdict(readiness) -> {"zone": str, "day_type": str, "value": int, "headline": str, "reasons": list[str]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smart_session.py  (append)
def test_verdict_green_is_push():
    v = analysis.readiness_verdict({"status": "ready", "zone": "green", "value": 95, "reasons": []})
    assert v["day_type"] == "Push"
    assert v["zone"] == "green"

def test_verdict_red_is_back_off():
    v = analysis.readiness_verdict({"status": "ready", "zone": "red", "value": 30,
                                    "reasons": ["HRV below personal baseline"]})
    assert v["day_type"] == "Back off"
    assert "HRV below personal baseline" in v["reasons"]

def test_verdict_no_data_is_neutral():
    v = analysis.readiness_verdict({"status": "no_data", "zone": "green", "value": 100, "reasons": []})
    assert v["day_type"] == "Log normally"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smart_session.py -k verdict -v`
Expected: FAIL (`readiness_verdict` undefined).

- [ ] **Step 3: Implement**

```python
def readiness_verdict(readiness):
    """Map a recovery_readiness dict to the strength-facing verdict. Pure."""
    if not readiness or readiness.get("status") == "no_data":
        return {"zone": "green", "day_type": "Log normally", "value": 100,
                "headline": "Recovery: learning", "reasons": []}
    zone = readiness.get("zone", "green")
    day_type = {"green": "Push", "yellow": "Hold / volume", "red": "Back off"}.get(zone, "Push")
    reasons = list(readiness.get("reasons", []))
    headline = f"{day_type} — recovery {zone}"
    return {"zone": zone, "day_type": day_type, "value": int(readiness.get("value", 0)),
            "headline": headline, "reasons": reasons[:3]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_smart_session.py -k verdict -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_smart_session.py
git commit -m "feat: readiness_verdict day-type mapping"
```

---

### Task 5: `compute_progression_suggestion()` (pure)

**Files:**
- Modify: `analysis.py` — add `_round_to_increment` + `compute_progression_suggestion`.
- Test: `tests/test_smart_session.py` (append).

**Interfaces:**
- Produces: `analysis.compute_progression_suggestion(exercise_id, sessions_df, sets_df, exercises_df, formula="epley") -> dict | None` with keys `state ("progress"|"hold"|"deload"), suggested_weight_kg, target_reps, last_weight_kg, stalls, reason`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smart_session.py  (append)
def _ex_df():
    return pd.DataFrame([
        {"exercise_id": "back-squat", "is_main_lift": 1, "increment_kg": 2.5, "target_reps": 5},
        {"exercise_id": "barbell-curl", "is_main_lift": 0, "increment_kg": None, "target_reps": None},
    ])

def _sess(*dates):
    return pd.DataFrame([{"session_id": f"s{i}", "date": d} for i, d in enumerate(dates)])

def _set(session_id, weight, reps, completed=1, warmup=0, exercise_id="back-squat"):
    return {"session_id": session_id, "exercise_id": exercise_id, "weight_kg": weight,
            "reps": reps, "completed": completed, "is_warmup": warmup}

def test_progression_progresses_when_all_sets_hit():
    sets = pd.DataFrame([_set("s0", 100, 5), _set("s0", 100, 5), _set("s0", 100, 5)])
    out = analysis.compute_progression_suggestion("back-squat", _sess("2026-06-01"), sets, _ex_df())
    assert out["state"] == "progress"
    assert out["suggested_weight_kg"] == 102.5

def test_progression_holds_when_a_set_short():
    sets = pd.DataFrame([_set("s0", 100, 5), _set("s0", 100, 3)])
    out = analysis.compute_progression_suggestion("back-squat", _sess("2026-06-01"), sets, _ex_df())
    assert out["state"] == "hold"
    assert out["suggested_weight_kg"] == 100

def test_progression_deloads_after_three_stalls():
    sets = pd.DataFrame([
        _set("s0", 100, 3), _set("s1", 100, 3), _set("s2", 100, 3),
    ])
    sess = _sess("2026-06-01", "2026-06-03", "2026-06-05")
    out = analysis.compute_progression_suggestion("back-squat", sess, sets, _ex_df())
    assert out["state"] == "deload"
    assert out["stalls"] == 3
    assert out["suggested_weight_kg"] == 90.0  # round(100*0.9 / 2.5)*2.5

def test_progression_no_deload_at_two_stalls():
    sets = pd.DataFrame([_set("s0", 100, 3), _set("s1", 100, 3)])
    sess = _sess("2026-06-01", "2026-06-03")
    out = analysis.compute_progression_suggestion("back-squat", sess, sets, _ex_df())
    assert out["state"] == "hold"

def test_progression_none_for_accessory():
    sets = pd.DataFrame([_set("s0", 30, 10, exercise_id="barbell-curl")])
    out = analysis.compute_progression_suggestion("barbell-curl", _sess("2026-06-01"), sets, _ex_df())
    assert out is None

def test_progression_none_with_no_history():
    out = analysis.compute_progression_suggestion(
        "back-squat", pd.DataFrame(columns=["session_id", "date"]),
        pd.DataFrame(columns=["session_id", "exercise_id", "weight_kg", "reps", "completed", "is_warmup"]),
        _ex_df())
    assert out is None

def test_progression_ignores_warmups_and_incomplete():
    sets = pd.DataFrame([
        _set("s0", 60, 5, warmup=1), _set("s0", 100, 5), _set("s0", 100, 5, completed=0),
    ])
    out = analysis.compute_progression_suggestion("back-squat", _sess("2026-06-01"), sets, _ex_df())
    # only the one completed working set at 100×5 counts → all hit → progress
    assert out["state"] == "progress"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smart_session.py -k progression -v`
Expected: FAIL (`compute_progression_suggestion` undefined).

- [ ] **Step 3: Implement**

```python
def _round_to_increment(x, inc):
    if not inc:
        return round(float(x), 4)
    return round(round(float(x) / inc) * inc, 4)


def compute_progression_suggestion(exercise_id, sessions_df, sets_df,
                                   exercises_df, formula="epley"):
    """Linear-progression next-target suggestion for a main lift. Pure.

    progress: last session's working sets at the top weight all reached
    target_reps -> +increment. hold: a set fell short -> repeat weight.
    deload: 3 consecutive miss-sessions at the same top weight -> ~10% down,
    rounded to the increment. Returns None for non-main-lifts / no history."""
    if exercises_df is None or getattr(exercises_df, "empty", True):
        return None
    ex = exercises_df[exercises_df["exercise_id"] == exercise_id]
    if ex.empty:
        return None
    ex = ex.iloc[0]
    if int(ex.get("is_main_lift") or 0) != 1:
        return None
    try:
        inc = float(ex.get("increment_kg"))
        tgt = int(ex.get("target_reps"))
    except (TypeError, ValueError):
        return None
    if not (inc > 0 and tgt > 0):
        return None
    if (sessions_df is None or getattr(sessions_df, "empty", True)
            or sets_df is None or getattr(sets_df, "empty", True)):
        return None

    s = sets_df[sets_df["exercise_id"] == exercise_id].copy()
    if s.empty:
        return None
    warm = pd.to_numeric(s.get("is_warmup", 0), errors="coerce").fillna(0).astype(int)
    done = pd.to_numeric(s.get("completed", 1), errors="coerce").fillna(1).astype(int)
    s = s[(warm == 0) & (done == 1)]
    if s.empty:
        return None
    sess = sessions_df[["session_id", "date"]].copy()
    sess["date"] = pd.to_datetime(sess["date"], errors="coerce")
    s = s.merge(sess, on="session_id", how="left").dropna(subset=["date"])
    s["weight_kg"] = pd.to_numeric(s["weight_kg"], errors="coerce")
    s["reps"] = pd.to_numeric(s["reps"], errors="coerce")
    s = s.dropna(subset=["weight_kg", "reps"])
    if s.empty:
        return None

    rows = []
    for sid, grp in s.groupby("session_id"):
        top = grp["weight_kg"].max()
        at_top = grp[grp["weight_kg"] == top]
        rows.append({"date": grp["date"].iloc[0], "top": float(top),
                     "hit": bool((at_top["reps"] >= tgt).all())})
    hist = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    last = hist.iloc[-1]
    last_w = last["top"]

    # consecutive most-recent miss-sessions at the same top weight
    stalls = 0
    for _, r in hist.iloc[::-1].iterrows():
        if abs(r["top"] - last_w) < 1e-9 and not r["hit"]:
            stalls += 1
        else:
            break

    if last["hit"]:
        return {"state": "progress",
                "suggested_weight_kg": _round_to_increment(last_w + inc, inc),
                "target_reps": tgt, "last_weight_kg": last_w, "stalls": 0,
                "reason": f"all sets hit {tgt} reps at {last_w:g}kg"}
    if stalls >= 3:
        return {"state": "deload",
                "suggested_weight_kg": _round_to_increment(last_w * 0.9, inc),
                "target_reps": tgt, "last_weight_kg": last_w, "stalls": stalls,
                "reason": f"stalled {stalls}× at {last_w:g}kg"}
    return {"state": "hold", "suggested_weight_kg": last_w, "target_reps": tgt,
            "last_weight_kg": last_w, "stalls": stalls, "reason": "missed reps last time"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_smart_session.py -k progression -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_smart_session.py
git commit -m "feat: linear progression suggestion engine"
```

---

### Task 6: `compute_lift_recovery_sensitivity()` (pure)

**Files:**
- Modify: `analysis.py` — add `compute_lift_recovery_sensitivity`.
- Test: `tests/test_smart_session.py` (append).

**Interfaces:**
- Consumes: `analysis.enrich_strength_sets` (existing).
- Produces: `analysis.compute_lift_recovery_sensitivity(sessions_df, sets_df, exercises_df, formula="epley", min_pairs=4) -> list[dict]` with keys `exercise, n, delta_pct, flagged, note`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smart_session.py  (append)
def test_lift_recovery_sensitivity_flags_drop():
    ex = pd.DataFrame([{"exercise_id": "back-squat", "name": "Back Squat",
                        "is_bodyweight": 0, "is_main_lift": 1}])
    # green days lift heavier than low-recovery days
    sess = pd.DataFrame([
        {"session_id": "g1", "date": "2026-06-01", "bodyweight_kg": 80, "recovery_zone": "green"},
        {"session_id": "g2", "date": "2026-06-03", "bodyweight_kg": 80, "recovery_zone": "green"},
        {"session_id": "r1", "date": "2026-06-05", "bodyweight_kg": 80, "recovery_zone": "red"},
        {"session_id": "r2", "date": "2026-06-07", "bodyweight_kg": 80, "recovery_zone": "yellow"},
    ])
    def row(sid, w):
        return {"session_id": sid, "exercise_id": "back-squat", "weight_kg": w,
                "reps": 5, "completed": 1, "is_warmup": 0}
    sets = pd.DataFrame([row("g1", 100), row("g2", 100), row("r1", 90), row("r2", 90)])
    out = analysis.compute_lift_recovery_sensitivity(sess, sets, ex, min_pairs=4)
    squat = [o for o in out if o["exercise"] == "Back Squat"]
    assert squat and squat[0]["flagged"] is True
    assert squat[0]["delta_pct"] < 0

def test_lift_recovery_sensitivity_gated_by_sample():
    ex = pd.DataFrame([{"exercise_id": "back-squat", "name": "Back Squat",
                        "is_bodyweight": 0, "is_main_lift": 1}])
    sess = pd.DataFrame([{"session_id": "g1", "date": "2026-06-01", "bodyweight_kg": 80,
                          "recovery_zone": "green"}])
    sets = pd.DataFrame([{"session_id": "g1", "exercise_id": "back-squat", "weight_kg": 100,
                          "reps": 5, "completed": 1, "is_warmup": 0}])
    assert analysis.compute_lift_recovery_sensitivity(sess, sets, ex, min_pairs=4) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smart_session.py -k sensitivity -v`
Expected: FAIL (undefined).

- [ ] **Step 3: Implement**

```python
def compute_lift_recovery_sensitivity(sessions_df, sets_df, exercises_df,
                                      formula="epley", min_pairs=4):
    """Flag main lifts whose normalized performance drops on low-recovery days.

    Compares day-best est-1RM (relative to the lift's all-time best) on green
    days vs low-recovery (yellow/red) days. Pure. Gated by min_pairs."""
    if (sessions_df is None or getattr(sessions_df, "empty", True)
            or sets_df is None or getattr(sets_df, "empty", True)
            or "recovery_zone" not in sessions_df.columns):
        return []
    enr = enrich_strength_sets(sets_df, sessions_df, exercises_df, formula)
    if enr.empty or "est_1rm_kg" not in enr.columns:
        return []
    work = enr
    if "is_warmup" in work.columns:
        work = work[pd.to_numeric(work["is_warmup"], errors="coerce").fillna(0).astype(int) == 0]
    if "completed" in work.columns:
        work = work[pd.to_numeric(work["completed"], errors="coerce").fillna(1).astype(int) == 1]
    work = work.dropna(subset=["est_1rm_kg"])
    if work.empty:
        return []

    zone = sessions_df[["session_id", "recovery_zone"]]
    day = (work.groupby(["session_id", "exercise_id"])["est_1rm_kg"].max().reset_index())
    all_best = day.groupby("exercise_id")["est_1rm_kg"].max().to_dict()
    day["rel"] = day.apply(
        lambda r: r["est_1rm_kg"] / all_best[r["exercise_id"]] if all_best.get(r["exercise_id"]) else None,
        axis=1)
    day = day.merge(zone, on="session_id", how="left").dropna(subset=["rel", "recovery_zone"])

    main_ids = set(exercises_df[exercises_df.get("is_main_lift", 0) == 1]["exercise_id"]) \
        if "is_main_lift" in exercises_df.columns else set(day["exercise_id"])
    name_map = dict(zip(exercises_df["exercise_id"], exercises_df["name"])) \
        if "name" in exercises_df.columns else {}

    out = []
    for ex_id, grp in day.groupby("exercise_id"):
        if ex_id not in main_ids:
            continue
        green = grp[grp["recovery_zone"] == "green"]["rel"]
        low = grp[grp["recovery_zone"].isin(["yellow", "red"])]["rel"]
        n = int(len(grp))
        if len(green) < 2 or len(low) < 2 or n < min_pairs:
            continue
        delta_pct = round((low.mean() - green.mean()) / green.mean() * 100, 1)
        flagged = delta_pct <= -5.0
        note = (f"{abs(delta_pct):g}% lower on low-recovery days" if flagged
                else "no meaningful recovery sensitivity")
        out.append({"exercise": name_map.get(ex_id, ex_id), "n": n,
                    "delta_pct": delta_pct, "flagged": flagged, "note": note})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_smart_session.py -k sensitivity -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_smart_session.py
git commit -m "feat: per-lift recovery sensitivity"
```

---

### Task 7: Re-point `compute_readiness_performance` to `recovery_score`

**Files:**
- Modify: `analysis.py` — `compute_readiness_performance` (`analysis.py:2860`).
- Test: `tests/test_strength_analysis.py` (append).

**Interfaces:**
- Produces: same return shape as today, but bucketed on `sessions_df["recovery_score"]` instead of the dead `readiness_score`, plus a new `"signals"` dict of correlations vs `hrv_overnight_avg`, `sleep_score`, `resting_hr`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strength_analysis.py  (append)
import pandas as pd
import analysis

def test_readiness_performance_uses_recovery_score():
    ex = pd.DataFrame([{"exercise_id": "back-squat", "name": "Back Squat",
                        "is_bodyweight": 0}])
    rows, sets = [], []
    for i in range(8):
        sid = f"s{i}"
        rec = 90 if i % 2 == 0 else 40
        w = 105 if rec == 90 else 95
        rows.append({"session_id": sid, "date": f"2026-06-0{i+1}", "bodyweight_kg": 80,
                     "recovery_score": rec, "readiness_score": None,
                     "hrv_overnight_avg": rec, "sleep_score": rec, "resting_hr": 50})
        sets.append({"session_id": sid, "exercise_id": "back-squat", "weight_kg": w,
                     "reps": 5, "completed": 1, "is_warmup": 0})
    out = analysis.compute_readiness_performance(pd.DataFrame(rows), pd.DataFrame(sets), ex,
                                                 min_sessions=8)
    assert out["status"] == "ok"
    assert "signals" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_strength_analysis.py::test_readiness_performance_uses_recovery_score -v`
Expected: FAIL (`status` insufficient — function still reads the all-null `readiness_score`; no `signals` key).

- [ ] **Step 3: Implement**

In `compute_readiness_performance`, change the snapshot source line:

```python
    rsc = sessions_df[["session_id", "recovery_score"]].copy()
    rsc["readiness_score"] = pd.to_numeric(rsc["recovery_score"], errors="coerce")
```

(Keep the internal name `readiness_score` for the rest of the function so the bucketing/correlation code is unchanged.) Then, just before the final `return`, add per-signal correlations and include them:

```python
    signals = {}
    for col in ("hrv_overnight_avg", "sleep_score", "resting_hr"):
        if col in sessions_df.columns:
            sig = sessions_df[["session_id", col]].copy()
            sig[col] = pd.to_numeric(sig[col], errors="coerce")
            m = merged.merge(sig, on="session_id", how="left").dropna(subset=[col, "rel_perf"])
            if len(m) >= min_sessions:
                c = m[col].corr(m["rel_perf"])
                signals[col] = None if pd.isna(c) else round(float(c), 2)
    return {"status": "ok", "n": have, "buckets": buckets,
            "correlation": corr, "insight": insight, "signals": signals}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_strength_analysis.py::test_readiness_performance_uses_recovery_score -v`
Expected: PASS.

- [ ] **Step 5: Run the strength-analysis suite (regression)**

Run: `pytest tests/test_strength_analysis.py -q`
Expected: PASS (other tests that build sessions without `recovery_score` should already pass `status == insufficient`; if any assert on the old `readiness_score` path, update them to set `recovery_score`).

- [ ] **Step 6: Commit**

```bash
git add analysis.py tests/test_strength_analysis.py
git commit -m "feat: readiness-vs-performance keyed on recovery_score + per-signal correlations"
```

---

### Task 8: Feed the verdict into `summarize_strength`

**Files:**
- Modify: `analysis.py` — `summarize_strength` (`analysis.py:2932`).
- Test: `tests/test_smart_session.py` (append).

**Interfaces:**
- Produces: `summarize_strength(..., verdict=None)` adds `"recovery_verdict": verdict` to its output dict (or `None`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smart_session.py  (append)
def test_summarize_strength_carries_verdict():
    ex = pd.DataFrame([{"exercise_id": "back-squat", "name": "Back Squat",
                        "is_bodyweight": 0, "is_main_lift": 1}])
    sess = pd.DataFrame([{"session_id": "s0", "date": "2026-06-01", "bodyweight_kg": 80,
                          "recovery_score": 80}])
    sets = pd.DataFrame([{"session_id": "s0", "exercise_id": "back-squat", "weight_kg": 100,
                          "reps": 5, "completed": 1, "is_warmup": 0}])
    verdict = {"zone": "yellow", "day_type": "Hold / volume", "value": 60,
               "headline": "Hold / volume — recovery yellow", "reasons": ["sleep debt >1h"]}
    out = analysis.summarize_strength(sess, sets, ex, profile=None, bodyweight_kg=80, verdict=verdict)
    assert out["recovery_verdict"]["day_type"] == "Hold / volume"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smart_session.py -k carries_verdict -v`
Expected: FAIL (`summarize_strength` has no `verdict` kwarg).

- [ ] **Step 3: Implement**

Change the signature and the return dict of `summarize_strength`:

```python
def summarize_strength(sessions_df, sets_df, exercises_df, profile,
                       bodyweight_kg, lookback_days=28, formula="epley", verdict=None):
    ...
    return {
        "status": "ok",
        "recent": {...},          # unchanged
        "standards": standards_out,
        "balance_flags": {...},
        "readiness_link": readiness_out,
        "recent_prs": recent_prs,
        "recovery_verdict": verdict,
    }
```

(Also return `"recovery_verdict": verdict` in the early `{"status": "no_data"}` path? No — keep that path minimal; callers handle `no_data`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_smart_session.py -k carries_verdict -v`
Expected: PASS.

- [ ] **Step 5: Run AI-payload + smart-session suites (regression)**

Run: `pytest tests/test_smart_session.py tests/test_ai_payload.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add analysis.py tests/test_smart_session.py
git commit -m "feat: carry recovery verdict into strength AI summary"
```

---

### Task 9: `ai.coach_session_note()` (boundary)

**Files:**
- Modify: `ai.py` — add `COACH_NOTE_SYSTEM` + `coach_session_note`.
- Test: `tests/test_ai_payload.py` (append; no-key path only).

**Interfaces:**
- Consumes: a `summarize_strength` dict, a `readiness_verdict` dict, and `plan` (list of per-lift suggestion dicts).
- Produces: `ai.coach_session_note(strength_summary, verdict, plan, model=None) -> str` (`""` when no API key / on error).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ai_payload.py  (append)
def test_coach_session_note_no_key_returns_empty(monkeypatch):
    import config, ai, importlib
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    importlib.reload(ai)
    out = ai.coach_session_note({"status": "ok"}, {"day_type": "Push"}, [])
    assert out == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ai_payload.py::test_coach_session_note_no_key_returns_empty -v`
Expected: FAIL (`coach_session_note` undefined).

- [ ] **Step 3: Implement**

Add near the other system prompts in `ai.py`:

```python
COACH_NOTE_SYSTEM = (
    "You are a concise strength coach. Given today's recovery verdict, the "
    "linear-progression plan, and a compact strength summary, write ONE or TWO "
    "sentences of practical guidance for today's session. Be specific about "
    "which lifts to push, hold, or back off, and why (tie to recovery). No "
    "lists, no preamble, no diagnosis. Plain text."
)


def coach_session_note(strength_summary: dict, verdict: dict,
                       plan: list, model: str | None = None) -> str:
    if not config.ANTHROPIC_API_KEY:
        return ""
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=model or config.ANTHROPIC_MODEL,
            max_tokens=160,
            system=COACH_NOTE_SYSTEM,
            messages=[{
                "role": "user",
                "content": "Recovery verdict:\n\n" + json.dumps(verdict or {}, indent=2)
                           + "\n\nToday's progression plan (per main lift):\n\n"
                           + json.dumps(plan or [], indent=2)
                           + "\n\nStrength summary:\n\n"
                           + json.dumps(strength_summary or {}, indent=2)
                           + "\n\nWrite the session note.",
            }],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()
    except Exception:
        return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ai_payload.py::test_coach_session_note_no_key_returns_empty -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai.py tests/test_ai_payload.py
git commit -m "feat: ai.coach_session_note (cached session guidance)"
```

---

### Task 10: Cockpit renderers

**Files:**
- Modify: `cockpit.py` — add `strength_recovery_chip`, `strength_suggestion_hint`, `strength_recovery_sensitivity_panel`.
- Test: `tests/test_strength_cockpit.py` (append).

**Interfaces:**
- Consumes: `readiness_verdict` dict (Task 4), `compute_progression_suggestion` dict (Task 5), `compute_lift_recovery_sensitivity` list (Task 6).
- Produces: three functions returning HTML `str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strength_cockpit.py  (append)
import cockpit

def test_recovery_chip_renders_day_type():
    html = cockpit.strength_recovery_chip(
        {"zone": "red", "day_type": "Back off", "value": 30,
         "headline": "Back off — recovery red", "reasons": ["HRV below personal baseline"]})
    assert "Back off" in html
    assert "red" in html

def test_suggestion_hint_progress():
    html = cockpit.strength_suggestion_hint(
        {"state": "progress", "suggested_weight_kg": 102.5, "target_reps": 5,
         "last_weight_kg": 100.0, "stalls": 0, "reason": "all sets hit 5 reps at 100kg"})
    assert "102.5" in html
    assert "5" in html

def test_suggestion_hint_none_is_empty():
    assert cockpit.strength_suggestion_hint(None) == ""

def test_sensitivity_panel_lists_flagged():
    html = cockpit.strength_recovery_sensitivity_panel(
        [{"exercise": "Back Squat", "n": 6, "delta_pct": -8.0, "flagged": True,
          "note": "8% lower on low-recovery days"}])
    assert "Back Squat" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_strength_cockpit.py -k "chip or hint or sensitivity" -v`
Expected: FAIL (functions undefined).

- [ ] **Step 3: Implement** (follow the existing `cockpit.py` HTML-string style; `import html as _html` is already used there — reuse the module's escaping helper if present, else `html.escape`)

```python
def strength_recovery_chip(verdict: dict) -> str:
    if not verdict:
        return ""
    zone = verdict.get("zone", "green")
    color = {"green": "#2ecc71", "yellow": "#ffb234", "red": "#ff5a5a"}.get(zone, "#8a8a8a")
    day_type = html.escape(str(verdict.get("day_type", "")))
    reason = html.escape(str((verdict.get("reasons") or [""])[0]))
    return (
        f"<div class='strength-recovery-chip' style='display:inline-flex;align-items:center;"
        f"gap:8px;padding:6px 12px;border-radius:999px;background:#151515;"
        f"border:1px solid {color};color:#fff;font-size:13px;'>"
        f"<span style='width:9px;height:9px;border-radius:50%;background:{color};'></span>"
        f"<b>{day_type}</b><span style='color:#9a9a9a;'>{reason}</span></div>"
    )


def strength_suggestion_hint(suggestion: dict) -> str:
    if not suggestion:
        return ""
    state = suggestion.get("state")
    w = suggestion.get("suggested_weight_kg")
    reps = suggestion.get("target_reps")
    reason = html.escape(str(suggestion.get("reason", "")))
    color = {"progress": "#2ecc71", "hold": "#ffb234", "deload": "#ff5a5a"}.get(state, "#8a8a8a")
    label = {"progress": "Suggested", "hold": "Hold", "deload": "Deload"}.get(state, "Suggested")
    return (
        f"<div class='strength-suggestion-hint' style='margin:4px 0 8px;font-size:14px;"
        f"color:{color};'><b>{label} {w:g} × {reps}</b>"
        f"<span style='color:#8a8a8a;'> — {reason}</span></div>"
    )


def strength_recovery_sensitivity_panel(items: list) -> str:
    if not items:
        return "<div style='color:#8a8a8a;'>Not enough paired sessions yet.</div>"
    rows = []
    for it in items:
        flag = "⚠️ " if it.get("flagged") else ""
        rows.append(
            f"<div style='display:flex;justify-content:space-between;padding:4px 0;'>"
            f"<span>{flag}{html.escape(str(it.get('exercise')))}</span>"
            f"<span style='color:#8a8a8a;'>{html.escape(str(it.get('note')))} "
            f"(n={it.get('n')})</span></div>")
    return "<div class='strength-recovery-sensitivity'>" + "".join(rows) + "</div>"
```

> NOTE: if `cockpit.py` imports `html` under a different alias, match it. Verify with `grep -n "^import html\|import html as" cockpit.py` and adjust the `html.escape` calls.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_strength_cockpit.py -k "chip or hint or sensitivity" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cockpit.py tests/test_strength_cockpit.py
git commit -m "feat: cockpit renderers for chip, hint, sensitivity"
```

---

### Task 11: Wire Smart Session into the logger UI

**Files:**
- Modify: `views/strength.py` — `finish_active_workout` (stamp recovery), active-workout header (chip + coach note), per-exercise loop (hint + Apply), add-exercise default weight, Insights tab (sensitivity panel).
- Manual verification (no unit test — Streamlit view).

**Interfaces:**
- Consumes: `analysis.recovery_readiness`, `analysis.readiness_verdict`, `analysis.compute_progression_suggestion`, `analysis.compute_lift_recovery_sensitivity`, `analysis.summarize_strength`, `ai.coach_session_note`, `cockpit.strength_recovery_chip`, `cockpit.strength_suggestion_hint`, `cockpit.strength_recovery_sensitivity_panel`.

- [ ] **Step 1: Add a recovery-stamp helper + import `ai`**

At the top imports of `views/strength.py`, add `import ai` (and `importlib.reload(ai)` alongside the others). Add a helper next to `todays_readiness_snapshot`:

```python
def todays_recovery_verdict(day: str) -> dict:
    daily = analysis.enrich_daily(db.load_daily_df())
    readiness = analysis.recovery_readiness(daily, as_of=day)
    return analysis.readiness_verdict(readiness), readiness
```

- [ ] **Step 2: Stamp recovery on Finish**

In `finish_active_workout`, compute and store the recovery score/zone alongside the existing snapshot:

```python
    snap = todays_readiness_snapshot(active["date"])
    _verdict, _readiness = todays_recovery_verdict(active["date"])
    db.upsert_strength_session({
        "session_id": active["session_id"], "date": active["date"],
        "started_at": active["started_at"],
        "ended_at": datetime.now().isoformat(timespec="seconds"),
        "name": active["name"], "bodyweight_kg": active.get("bodyweight_kg"),
        "routine_id": active.get("routine_id"),
        "recovery_score": _readiness.get("value"),
        "recovery_zone": _readiness.get("zone"),
        **snap,
    })
```

- [ ] **Step 3: Render verdict chip + cached coach note in the active-workout header**

After the `strong-stats` markdown block (just before `names = catalog["name"].tolist()`), add:

```python
        verdict, _readiness = todays_recovery_verdict(active["date"])
        st.markdown(cockpit.strength_recovery_chip(verdict), unsafe_allow_html=True)

        note_key = f"coach_note_{active['session_id']}"
        cols = st.columns([6, 1])
        if cols[1].button("↻", key="coach_note_refresh", help="Refresh coach note"):
            st.session_state.pop(note_key, None)
        if note_key not in st.session_state:
            plan = []
            for ex in active["exercises"]:
                sug = analysis.compute_progression_suggestion(
                    ex["exercise_id"], hist_sessions_for_note(), hist_sets_for_note(),
                    catalog, config.ONE_RM_FORMULA)
                if sug:
                    plan.append({"exercise": ex["name"], **sug})
            strength_summary = analysis.summarize_strength(
                db.load_strength_sessions_df(), db.load_strength_sets_df(), catalog,
                db.load_profile(), resolve_bodyweight(active["date"]),
                formula=config.ONE_RM_FORMULA, verdict=verdict)
            st.session_state[note_key] = ai.coach_session_note(strength_summary, verdict, plan)
        if st.session_state.get(note_key):
            cols[0].caption("🧠 " + st.session_state[note_key])
```

Add two tiny cached readers near the other helpers (avoids re-reading the DB inside the loop):

```python
@st.cache_data(ttl=30)
def hist_sessions_for_note():
    return db.load_strength_sessions_df()

@st.cache_data(ttl=30)
def hist_sets_for_note():
    return db.load_strength_sets_df()
```

> The coach note is computed once per `session_id` (cached in `st.session_state`); the ↻ button clears the cache key to force a refresh. With no API key it stays empty and nothing renders.

- [ ] **Step 4: Per-main-lift suggestion hint + Apply button**

Inside the `for ei, ex in enumerate(active["exercises"]):` loop, right after the exercise-title markdown and before the note text input, add:

```python
            suggestion = analysis.compute_progression_suggestion(
                ex["exercise_id"], hist_sessions, hist_sets, catalog, config.ONE_RM_FORMULA)
            if suggestion:
                hcols = st.columns([6, 1])
                hcols[0].markdown(cockpit.strength_suggestion_hint(suggestion),
                                  unsafe_allow_html=True)
                if hcols[1].button("Apply", key=f"apply_sug_{ei}"):
                    w = float(suggestion["suggested_weight_kg"])
                    r = int(suggestion["target_reps"])
                    if not ex["sets"]:
                        ex["sets"] = [{
                            "set_id": str(uuid.uuid4()), "set_index": 1,
                            "side": "left" if ex["is_unilateral"] else "both",
                            "reps": r, "weight_kg": w, "rpe": None,
                            "is_warmup": 0, "completed": 0,
                        }]
                    else:
                        for stt in ex["sets"]:
                            if not stt["is_warmup"]:
                                stt["weight_kg"] = w
                                stt["reps"] = r
                    st.rerun()
```

(`hist_sessions`/`hist_sets` are already loaded just above the loop at `views/strength.py:639-640`.)

- [ ] **Step 5: Use the suggestion as the default weight when adding a main lift**

In the `if st.button("➕ Add to workout") and pick:` block, replace the appended `"sets": []` with a suggestion-seeded first set:

```python
            ex_row = catalog[catalog["name"] == pick].iloc[0]
            sug = analysis.compute_progression_suggestion(
                ex_row["exercise_id"], db.load_strength_sessions_df(),
                db.load_strength_sets_df(), catalog, config.ONE_RM_FORMULA)
            seed_sets = []
            if sug:
                seed_sets = [{
                    "set_id": str(uuid.uuid4()), "set_index": 1,
                    "side": "left" if int(ex_row["is_unilateral"]) else "both",
                    "reps": int(sug["target_reps"]), "weight_kg": float(sug["suggested_weight_kg"]),
                    "rpe": None, "is_warmup": 0, "completed": 0,
                }]
            active["exercises"].append({
                "position": len(active["exercises"]),
                "exercise_id": ex_row["exercise_id"],
                "name": ex_row["name"],
                "is_unilateral": int(ex_row["is_unilateral"]),
                "is_bodyweight": int(ex_row["is_bodyweight"]),
                "sets": seed_sets,
            })
            st.rerun()
```

- [ ] **Step 6: Add the recovery-sensitivity panel to Insights**

In the `with tab_insights:` block, after the "Readiness vs performance" section, add:

```python
        st.divider()
        st.markdown("##### Recovery-sensitive lifts")
        sens = analysis.compute_lift_recovery_sensitivity(
            sessions, sets, catalog, formula=config.ONE_RM_FORMULA)
        st.markdown(cockpit.strength_recovery_sensitivity_panel(sens),
                    unsafe_allow_html=True)
```

- [ ] **Step 7: Manual verification**

Run: `streamlit run app.py`
Check, on the Strength page:
1. **Log tab** with no main-lift history → no hint shown; chip shows "Recovery: learning" or a colored verdict if daily data exists. No crash.
2. Add **Back Squat**, log 3×5 at 100, **Finish**. Re-open a new workout, add Back Squat → hint reads **"Suggested 102.5 × 5"**; **Apply** fills the set to 102.5×5.
3. Log a session where a set is short of 5 → next suggestion reads **"Hold 100 × 5"**.
4. **History tab** → the saved session still renders; **Insights tab** shows the "Recovery-sensitive lifts" panel (likely "Not enough paired sessions yet").
5. With `ANTHROPIC_API_KEY` set, the **🧠 coach note** line appears under the chip; the **↻** button refreshes it. With the key unset, no note line appears and nothing errors.

- [ ] **Step 8: Run the full test suite**

Run: `pytest -q`
Expected: PASS (no regressions).

- [ ] **Step 9: Commit**

```bash
git add views/strength.py
git commit -m "feat: wire Smart Session (chip, coach note, hints, recovery stamp) into logger"
```

---

## Self-Review

**Spec coverage:**

- Data model (`increment_kg`, `target_reps`, `recovery_score`, `recovery_zone`, migration, seeds) → Task 1. ✓
- `_recovery_risk` factor-out (one source of truth, panel unchanged) → Task 2. ✓
- `recovery_readiness` → Task 3. ✓
- `readiness_verdict` (day-type) → Task 4. ✓
- `compute_progression_suggestion` (linear, all-sets-hit / hold / 3-stall deload, main-lifts-only, None fallback) → Task 5. ✓
- Session stamping at Finish → Task 11 Step 2. ✓
- Re-point `compute_readiness_performance` + per-signal correlations → Task 7. ✓
- `compute_lift_recovery_sensitivity` + Insights panel → Tasks 6 + 11 Step 6. ✓
- `ai.coach_session_note` (cached, degrades) → Task 9 + 11 Step 3. ✓
- Feed verdict into `summarize_strength` (coach Q&A) → Task 8. ✓
- UI: verdict chip, coach note, inline hint + Apply, default weight → Task 11. ✓
- Tests for the four pure functions → Tasks 3–7. ✓
- Non-goal "no standalone banner" honored (chip only). ✓
- Non-goal "no historical backfill of recovery_score" honored (stamp at Finish only). ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to" — each step has concrete code or exact commands.

**Type consistency:** `compute_progression_suggestion` returns `{state, suggested_weight_kg, target_reps, last_weight_kg, stalls, reason}` and every consumer (cockpit hint, Apply, plan list, default weight) reads those exact keys. `recovery_readiness` → `{status, zone, value, reasons}` feeds `readiness_verdict` → `{zone, day_type, value, headline, reasons}`, consumed by the chip and `summarize_strength(verdict=…)`. `compute_lift_recovery_sensitivity` → list of `{exercise, n, delta_pct, flagged, note}`, consumed by `strength_recovery_sensitivity_panel`. Consistent.

**One note for the implementer:** Task 11 Step 3 references `hist_sessions_for_note()`/`hist_sets_for_note()`; the per-exercise loop (Step 4) reuses the already-present `hist_sessions`/`hist_sets` locals at `views/strength.py:639-640`. Keep both — the header runs before that loop.
