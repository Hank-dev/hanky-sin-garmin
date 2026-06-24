# Strength + Recovery Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tie Garmin-derived recovery to strength: a day-type recommendation (Intensity/Volume/Maintenance) in the logger, performance-vs-recovery correlation, and per-lift recovery-sensitivity flags — all keyed on the Health Lab recovery score (inverted).

**Architecture:** Factor the recovery score/zone math out of the Health Lab panel into a shared `_recovery_risk` + a pure `recovery_readiness()`. A `strength_day_type()` maps its zone to a day-type rendered as a banner. Each session stamps `recovery_score`/`recovery_zone` at Finish; the existing correlation function is re-pointed off the dead Garmin score onto the stamped recovery score, and a new per-lift sensitivity function flags lifts that drop on poor-recovery days.

**Tech Stack:** Python, pandas, SQLite (`db.py`), Streamlit (`pages/01_Strength.py`), Plotly-free HTML cards (`cockpit.py`), pytest/unittest.

**Spec:** `docs/superpowers/specs/2026-06-13-strength-recovery-integration-design.md`

---

## File Structure

- **Create** `tests/test_strength_recovery.py` — all unit tests for this feature.
- **Modify** `analysis.py` — `_recovery_risk` (extracted), refactor `_research_recovery_panel` to use it, `recovery_readiness`, `strength_day_type`, upgrade `compute_readiness_performance`, add `compute_lift_recovery_sensitivity`.
- **Modify** `cockpit.py` — `strength_day_type_banner`, `strength_lift_sensitivity_panel`.
- **Modify** `db.py` — two `strength_sessions` columns + `SESSION_COLS` + migration in `init_db`.
- **Modify** `pages/01_Strength.py` — stamp recovery in `todays_readiness_snapshot`, render the day-type banner (Log tab) and sensitivity panel (Insights tab).

Patterns followed: `analysis.py` pure/no-I/O; `db.py` `SCHEMA` + `*_COLS` + `_upsert` + `init_db` ALTER migration; `cockpit.py` cards reuse `_md_sections`/`_collapse_html`/`_fmt`/`html.escape` and `.research-stat`/`.empty-note` classes.

---

## Task 1: Shared `_recovery_risk` + `recovery_readiness()`

**Files:**
- Modify: `analysis.py` (refactor `_research_recovery_panel`, add two functions)
- Test: `tests/test_strength_recovery.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_strength_recovery.py`:

```python
import unittest

import pandas as pd

import analysis


def _daily(zone="green"):
    """Build an enriched-shape daily frame whose latest day is green/yellow/red."""
    n = 16
    dates = pd.date_range("2026-05-26", periods=n, freq="D")
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "date": d,
            "hrv_overnight_avg": 45, "resting_hr": 55, "sleep_hours": 7.5,
            "sleep_debt_h": 0.0, "stress_avg": 30, "body_battery_current": 70,
            "hrv_flag": "balanced", "rhr_elevated": False,
            "hrv_z": 0.0, "rhr_z": 0.0, "sleep_z": 0.0, "stress_z": 0.0,
            "body_battery_z": 0.0,
        })
    df = pd.DataFrame(rows)
    if zone == "red":
        # latest 3 days: HRV suppressed + RHR elevated + sleep debt -> >=3 flags
        for j in (n - 3, n - 2, n - 1):
            df.loc[j, ["hrv_flag", "rhr_elevated", "sleep_debt_h", "stress_avg"]] = \
                ["suppressed", True, 2.0, 70]
    elif zone == "yellow":
        df.loc[n - 1, ["hrv_flag", "sleep_debt_h"]] = ["suppressed", 1.5]
    return df


class RecoveryReadinessTest(unittest.TestCase):
    def test_green_is_high_score(self):
        out = analysis.recovery_readiness(_daily("green"))
        self.assertEqual(out["status"], "ready")
        self.assertEqual(out["zone"], "green")
        self.assertEqual(out["score"], 100)  # risk 0 -> score 100

    def test_red_is_low_score_and_red_zone(self):
        out = analysis.recovery_readiness(_daily("red"))
        self.assertEqual(out["zone"], "red")
        self.assertLess(out["score"], 100)

    def test_as_of_slices_to_date(self):
        df = _daily("red")
        # as_of before the red days -> green
        as_of = df["date"].iloc[-4]
        out = analysis.recovery_readiness(df, as_of=as_of)
        self.assertEqual(out["zone"], "green")

    def test_no_data(self):
        out = analysis.recovery_readiness(pd.DataFrame())
        self.assertEqual(out["status"], "no_data")
        self.assertIsNone(out["score"])

    def test_recovery_panel_unchanged_after_refactor(self):
        # Regression: the Health Lab recovery panel still scores green at 0 risk.
        panel = analysis._research_recovery_panel(_daily("green"))
        self.assertEqual(panel["zone"], "green")
        self.assertEqual(panel["risk_score"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_strength_recovery.py::RecoveryReadinessTest -v`
Expected: FAIL — `AttributeError: module 'analysis' has no attribute 'recovery_readiness'`.

- [ ] **Step 3: Extract `_recovery_risk` and refactor the panel**

In `analysis.py`, add `_recovery_risk` immediately above `def _research_recovery_panel`:

```python
def _recovery_risk(df: pd.DataFrame) -> dict:
    """Recovery score/zone math shared by the Health Lab panel and
    `recovery_readiness`. Expects an enriched daily frame; reads the latest row
    plus the trailing 14 days. Pure."""
    latest = df.iloc[-1]
    recent = df.tail(14)
    flags = _research_recovery_flags(latest)
    flag_counts = recent.apply(_research_recovery_flag_count, axis=1)
    streak = _trailing_true_streak(flag_counts >= 2)
    suppressed_days = int((recent.get("hrv_flag", pd.Series(index=recent.index, dtype=object)) == "suppressed").sum())
    elevated_rhr_days = int(
        recent.get("rhr_elevated", pd.Series(False, index=recent.index)).fillna(False).astype(bool).sum()
    )
    short_sleep_days = int((pd.to_numeric(recent.get("sleep_debt_h"), errors="coerce") >= 1.0).sum()) if "sleep_debt_h" in recent else 0
    risk_score = min(100, len(flags) * 22 + streak * 8 + max(0, suppressed_days - 2) * 3)
    if len(flags) >= 3 or streak >= 2:
        zone = "red"
    elif flags or suppressed_days >= 3 or elevated_rhr_days >= 3 or short_sleep_days >= 3:
        zone = "yellow"
    else:
        zone = "green"
    return {
        "risk_score": int(round(risk_score)), "zone": zone, "flags": flags,
        "streak": streak, "suppressed_days": suppressed_days,
        "elevated_rhr_days": elevated_rhr_days, "short_sleep_days": short_sleep_days,
    }
```

Then replace the body of `_research_recovery_panel` from `latest = df.iloc[-1]` through the `risk_score`/`zone` assignment (the lines computing `flags`, `flag_counts`, `recovery_debt`, `streak`, `suppressed_days`, `elevated_rhr_days`, `short_sleep_days`, `risk_score`, and the `if/elif/else` zone block) with:

```python
    risk = _recovery_risk(df)
    flags = risk["flags"]
    streak = risk["streak"]
    suppressed_days = risk["suppressed_days"]
    elevated_rhr_days = risk["elevated_rhr_days"]
    short_sleep_days = risk["short_sleep_days"]
    risk_score = risk["risk_score"]
    zone = risk["zone"]
```

(Leave the rest of `_research_recovery_panel` — `status`, `message`, the `return` with `stats` — unchanged.)

- [ ] **Step 4: Add `recovery_readiness`**

In `analysis.py`, add after `_research_recovery_panel`:

```python
def recovery_readiness(daily, as_of=None) -> dict:
    """Recovery 'readiness' for strength: the Health Lab recovery score inverted
    (higher = readier). `as_of` slices to rows on/before that date. Pure."""
    if daily is None or getattr(daily, "empty", True):
        return {"status": "no_data", "score": None, "zone": None, "flags": []}
    df = daily.copy()
    if "date" in df:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date")
        if as_of is not None:
            df = df[df["date"] <= pd.to_datetime(as_of)]
    if df.empty or not _has_any(df, ("hrv_overnight_avg", "resting_hr", "sleep_hours")):
        return {"status": "no_data", "score": None, "zone": None, "flags": []}
    risk = _recovery_risk(df)
    return {"status": "ready", "score": 100 - risk["risk_score"],
            "zone": risk["zone"], "flags": risk["flags"]}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_strength_recovery.py::RecoveryReadinessTest -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Run the Health Lab tests (refactor regression)**

Run: `python -m pytest tests/test_health_research.py -q`
Expected: PASS (no behavior change from the refactor).

- [ ] **Step 7: Commit**

```bash
git add analysis.py tests/test_strength_recovery.py
git commit -m "feat(strength-recovery): shared _recovery_risk + recovery_readiness()"
```

---

## Task 2: `strength_day_type()`

**Files:**
- Modify: `analysis.py`
- Test: `tests/test_strength_recovery.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_strength_recovery.py`:

```python
class StrengthDayTypeTest(unittest.TestCase):
    def test_green_to_intensity(self):
        out = analysis.strength_day_type(_daily("green"))
        self.assertEqual(out["day_type"], "Intensity")
        self.assertIn("heavy", out["guidance"].lower())

    def test_yellow_to_volume(self):
        out = analysis.strength_day_type(_daily("yellow"))
        self.assertEqual(out["day_type"], "Volume")

    def test_red_to_maintenance(self):
        out = analysis.strength_day_type(_daily("red"))
        self.assertEqual(out["day_type"], "Maintenance")

    def test_no_data_has_no_day_type(self):
        out = analysis.strength_day_type(pd.DataFrame())
        self.assertEqual(out["status"], "no_data")
        self.assertIsNone(out["day_type"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_strength_recovery.py::StrengthDayTypeTest -v`
Expected: FAIL — `AttributeError: ... 'strength_day_type'`.

- [ ] **Step 3: Write minimal implementation**

In `analysis.py`, add after `recovery_readiness`:

```python
_DAY_TYPE_BY_ZONE = {"green": "Intensity", "yellow": "Volume", "red": "Maintenance"}
_DAY_TYPE_GUIDANCE = {
    "Intensity": "Work up to a heavy 3–5RM; 3–5 hard sets.",
    "Volume": "3–4 sets of 8–12 at a moderate load; leave 1–2 reps in reserve.",
    "Maintenance": "Light technique work ~60–70%; stop well short of failure.",
}


def strength_day_type(daily) -> dict:
    """Map today's recovery zone to a strength day-type + guidance. Pure."""
    r = recovery_readiness(daily)
    if r["status"] != "ready" or r["zone"] not in _DAY_TYPE_BY_ZONE:
        return {"status": "no_data", "day_type": None, "zone": None,
                "score": None, "rationale": "No recovery signals yet — train to feel.",
                "guidance": ""}
    day_type = _DAY_TYPE_BY_ZONE[r["zone"]]
    if r["flags"]:
        rationale = f"Recovery {r['score']}/100 — " + "; ".join(r["flags"][:2]) + "."
    else:
        rationale = f"Recovery {r['score']}/100 — primitives inside baseline."
    return {"status": "ready", "day_type": day_type, "zone": r["zone"],
            "score": r["score"], "rationale": rationale,
            "guidance": _DAY_TYPE_GUIDANCE[day_type]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_strength_recovery.py::StrengthDayTypeTest -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_strength_recovery.py
git commit -m "feat(strength-recovery): strength_day_type() zone->day-type mapping"
```

---

## Task 3: `cockpit.strength_day_type_banner()`

**Files:**
- Modify: `cockpit.py` (add after `strength_correlation_panel`)
- Test: `tests/test_strength_recovery.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_strength_recovery.py`:

```python
import cockpit


class DayTypeBannerTest(unittest.TestCase):
    def test_renders_day_type_and_guidance_one_block(self):
        out = cockpit.strength_day_type_banner({
            "status": "ready", "day_type": "Intensity", "zone": "green",
            "score": 88, "rationale": "Recovery 88/100 — primitives inside baseline.",
            "guidance": "Work up to a heavy 3–5RM; 3–5 hard sets.",
        })
        self.assertIn("Intensity", out)
        self.assertIn("heavy", out)
        self.assertFalse([ln for ln in out.splitlines() if ln.strip() == ""])

    def test_no_data_state(self):
        out = cockpit.strength_day_type_banner({"status": "no_data", "day_type": None})
        self.assertIn("train to feel", out.lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_strength_recovery.py::DayTypeBannerTest -v`
Expected: FAIL — `AttributeError: ... 'strength_day_type_banner'`.

- [ ] **Step 3: Write minimal implementation**

In `cockpit.py`, add after `strength_correlation_panel`:

```python
_DAY_TYPE_ZONE_CLASS = {"green": "good", "yellow": "warn", "red": "bad"}


def strength_day_type_banner(day_type: dict) -> str:
    day_type = day_type or {}
    if day_type.get("status") != "ready" or not day_type.get("day_type"):
        body = ('<div class="empty-note" style="margin:0"><span class="ico">⚡</span> '
                'No recovery call today — train to feel.</div>')
        return _collapse_html(f'<div class="card">{body}</div>')
    zcls = _DAY_TYPE_ZONE_CLASS.get(day_type.get("zone"), "warn")
    return _collapse_html(
        f'<div class="card day-card {zcls}">'
        f'<div class="day-flag">Today · {html.escape(str(day_type["day_type"]))} day</div>'
        f'<div class="day-stat"><b>{html.escape(str(day_type.get("rationale") or ""))}</b></div>'
        f'<div class="sub">{html.escape(str(day_type.get("guidance") or ""))}</div>'
        f'</div>')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_strength_recovery.py::DayTypeBannerTest -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add cockpit.py tests/test_strength_recovery.py
git commit -m "feat(strength-recovery): strength_day_type_banner renderer"
```

---

## Task 4: Stamp `recovery_score`/`recovery_zone` on sessions

**Files:**
- Modify: `db.py` (SCHEMA, SESSION_COLS, init_db migration)
- Modify: `pages/01_Strength.py` (`todays_readiness_snapshot`)
- Test: `tests/test_strength_recovery.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_strength_recovery.py`:

```python
import os
import tempfile

import config
import db


class SessionRecoveryColumnsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self._orig = config.DB_PATH
        config.DB_PATH = self.tmp.name
        db.init_db()

    def tearDown(self):
        config.DB_PATH = self._orig
        os.unlink(self.tmp.name)

    def test_session_round_trip_with_recovery(self):
        self.assertIn("recovery_score", db.SESSION_COLS)
        self.assertIn("recovery_zone", db.SESSION_COLS)
        db.upsert_strength_session({
            "session_id": "s1", "date": "2026-06-10",
            "recovery_score": 88, "recovery_zone": "green",
        })
        df = db.load_strength_sessions_df()
        row = df[df["session_id"] == "s1"].iloc[0]
        self.assertEqual(int(row["recovery_score"]), 88)
        self.assertEqual(row["recovery_zone"], "green")

    def test_migration_adds_columns_to_existing_db(self):
        # Simulate a pre-feature DB: a strength_sessions table missing the new
        # columns. init_db()'s ALTER block must add them.
        path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        orig = config.DB_PATH
        config.DB_PATH = path
        try:
            with db.connect() as conn:
                conn.execute("CREATE TABLE strength_sessions "
                             "(session_id TEXT PRIMARY KEY, date TEXT)")
            db.init_db()
            with db.connect() as conn:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(strength_sessions)")}
            self.assertIn("recovery_score", cols)
            self.assertIn("recovery_zone", cols)
        finally:
            config.DB_PATH = orig
            os.unlink(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_strength_recovery.py::SessionRecoveryColumnsTest -v`
Expected: FAIL — `recovery_score` not in `SESSION_COLS`.

- [ ] **Step 3: Add the columns, COLS entry, and migration**

3a. In `db.py` `SCHEMA`, in the `strength_sessions` table add two columns before the closing `);` (after `acwr REAL`):

```sql
    recovery_score REAL,
    recovery_zone TEXT,
```

3b. In `db.py`, extend `SESSION_COLS` to end with the two new names:

```python
SESSION_COLS = [
    "session_id", "date", "started_at", "ended_at", "routine_id", "name",
    "bodyweight_kg", "notes", "readiness_score", "readiness_level",
    "hrv_status", "hrv_overnight_avg", "body_battery_start", "sleep_score",
    "resting_hr", "acwr", "recovery_score", "recovery_zone",
]
```

3c. In `db.py` `init_db()`, after the `daily_metrics` ALTER loop and still inside the `with connect() as conn:` block, add:

```python
        existing_ss = {r[1] for r in conn.execute("PRAGMA table_info(strength_sessions)")}
        for col, kind in (("recovery_score", "REAL"), ("recovery_zone", "TEXT")):
            if col not in existing_ss:
                conn.execute(f"ALTER TABLE strength_sessions ADD COLUMN {col} {kind}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_strength_recovery.py::SessionRecoveryColumnsTest -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Stamp recovery into the Finish snapshot**

In `pages/01_Strength.py`, replace `todays_readiness_snapshot` with:

```python
def todays_readiness_snapshot(day: str) -> dict:
    daily = analysis.enrich_daily(db.load_daily_df())
    if not daily.empty:
        daily = analysis.compute_acwr(db.load_activities_df(), daily)
    if daily.empty:
        return analysis.readiness_snapshot_from_daily(None)
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    match = daily[daily["date"].dt.strftime("%Y-%m-%d") == day]
    row = match.iloc[-1] if not match.empty else None
    snap = analysis.readiness_snapshot_from_daily(row)
    rec = analysis.recovery_readiness(daily, as_of=day)
    snap["recovery_score"] = rec["score"]
    snap["recovery_zone"] = rec["zone"]
    return snap
```

- [ ] **Step 6: Verify import + full suite**

Run: `python -c "import ast; ast.parse(open('pages/01_Strength.py').read()); print('ok')"`
Expected: `ok`
Run: `python -m pytest tests/test_strength_recovery.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add db.py pages/01_Strength.py tests/test_strength_recovery.py
git commit -m "feat(strength-recovery): stamp recovery_score/zone on sessions at Finish"
```

---

## Task 5: Re-point `compute_readiness_performance` onto recovery + per-signal

**Files:**
- Modify: `analysis.py` (`compute_readiness_performance`)
- Test: `tests/test_strength_recovery.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_strength_recovery.py`:

```python
def _sessions_and_sets(n=10):
    srows, krows = [], []
    for i in range(n):
        sid = f"s{i}"
        rec = 90 if i % 2 == 0 else 40
        srows.append({"session_id": sid, "date": f"2026-06-{i+1:02d}",
                      "bodyweight_kg": 80, "recovery_score": rec,
                      "recovery_zone": "green" if rec >= 70 else "red",
                      "hrv_overnight_avg": 50 if rec >= 70 else 38,
                      "sleep_score": 85 if rec >= 70 else 60, "resting_hr": 52 if rec >= 70 else 60})
        load = 100 if rec >= 70 else 90  # better lifts on good-recovery days
        krows.append({"set_id": f"{sid}a", "session_id": sid, "exercise_id": "squat",
                      "position": 0, "set_index": 1, "side": "both",
                      "reps": 5, "weight_kg": load, "rpe": 8, "is_warmup": 0, "completed": 1})
    return pd.DataFrame(srows), pd.DataFrame(krows)


def _exercises():
    return pd.DataFrame([{"exercise_id": "squat", "name": "Squat",
                          "is_bodyweight": 0, "is_unilateral": 0}])


class ReadinessPerformanceTest(unittest.TestCase):
    def test_keys_on_recovery_score_with_signals(self):
        sess, sets = _sessions_and_sets(10)
        out = analysis.compute_readiness_performance(sess, sets, _exercises(), min_sessions=8)
        self.assertEqual(out["status"], "ok")
        self.assertIn("signals", out)
        self.assertIn("recovery_score", out["signals"])
        # better lifts on good-recovery days -> positive recovery correlation
        self.assertGreater(out["signals"]["recovery_score"]["correlation"], 0)

    def test_gated_when_too_few(self):
        sess, sets = _sessions_and_sets(3)
        out = analysis.compute_readiness_performance(sess, sets, _exercises(), min_sessions=8)
        self.assertEqual(out["status"], "insufficient")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_strength_recovery.py::ReadinessPerformanceTest -v`
Expected: FAIL — `KeyError: 'signals'` (and/or correlation is `None` because it keyed on the absent `readiness_score`).

- [ ] **Step 3: Update the implementation**

In `analysis.py` `compute_readiness_performance`, replace the block from `ton = summarize_sessions(...)` down to the `return {...}` at the end of the function with:

```python
    ton = summarize_sessions(sessions_df, sets_df, exercises_df, formula)[
        ["session_id", "total_volume_kg"]]
    signal_cols = [c for c in ("recovery_score", "hrv_overnight_avg", "sleep_score", "resting_hr")
                   if c in sessions_df.columns]
    keep = ["session_id"] + signal_cols
    ssig = sessions_df[keep].copy()
    for c in signal_cols:
        ssig[c] = pd.to_numeric(ssig[c], errors="coerce")
    merged = (sess.merge(ssig, on="session_id", how="left")
                  .merge(ton, on="session_id", how="left"))
    primary = merged.dropna(subset=["recovery_score", "rel_perf"]) if "recovery_score" in merged else merged.iloc[0:0]
    have = int(len(primary))
    if have < min_sessions:
        return {"status": "insufficient", "have": have, "need": min_sessions}

    def bucket(x):
        return "Low" if x < 50 else ("Med" if x <= 75 else "High")
    primary = primary.copy()
    primary["bucket"] = primary["recovery_score"].apply(bucket)
    buckets = {}
    for b in ("Low", "Med", "High"):
        bb = primary[primary["bucket"] == b]
        if bb.empty:
            continue
        buckets[b] = {
            "n": int(len(bb)),
            "avg_rel_perf": round(float(bb["rel_perf"].mean()), 3),
            "pr_rate": round(float(bb["pr"].mean()), 2),
            "avg_tonnage": round(float(bb["total_volume_kg"].fillna(0).mean()), 0),
        }

    signals = {}
    for c in signal_cols:
        sub = merged.dropna(subset=[c, "rel_perf"])
        if len(sub) < 3:
            continue
        r = sub[c].corr(sub["rel_perf"])
        signals[c] = {"n": int(len(sub)),
                      "correlation": None if pd.isna(r) else round(float(r), 2)}

    corr = signals.get("recovery_score", {}).get("correlation")
    if corr is not None and corr >= 0.3:
        insight = "You tend to hit better lifts on higher-recovery days."
    elif corr is not None and corr <= -0.3:
        insight = "Your best lifts cluster on lower-recovery days — recovery isn't limiting your lifting."
    else:
        insight = "No strong link between recovery and lifting performance so far."
    return {"status": "ok", "n": have, "buckets": buckets,
            "correlation": corr, "signals": signals, "insight": insight}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_strength_recovery.py::ReadinessPerformanceTest -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the existing strength tests (regression)**

Run: `python -m pytest tests/test_strength_analysis.py -q`
Expected: PASS (the function's `status`/`buckets`/`correlation` keys are preserved; `strength_correlation_panel` still reads them).

- [ ] **Step 6: Commit**

```bash
git add analysis.py tests/test_strength_recovery.py
git commit -m "feat(strength-recovery): correlate lifting vs recovery + per-signal"
```

---

## Task 6: `compute_lift_recovery_sensitivity()` + panel

**Files:**
- Modify: `analysis.py` (add function)
- Modify: `cockpit.py` (add `strength_lift_sensitivity_panel`)
- Test: `tests/test_strength_recovery.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_strength_recovery.py`:

```python
class LiftSensitivityTest(unittest.TestCase):
    def test_flags_lift_that_drops_on_poor_recovery(self):
        sess, sets = _sessions_and_sets(10)  # squat: 100kg green days, 90kg red days
        out = analysis.compute_lift_recovery_sensitivity(sess, sets, _exercises())
        self.assertEqual(out["status"], "ok")
        squat = next(l for l in out["lifts"] if l["exercise_id"] == "squat")
        self.assertGreater(squat["drop_pct"], 0)
        self.assertTrue(squat["flag"])  # ~10% drop >= 7% threshold

    def test_needs_both_zones(self):
        sess, sets = _sessions_and_sets(10)
        sess["recovery_zone"] = "green"  # no poor days
        out = analysis.compute_lift_recovery_sensitivity(sess, sets, _exercises())
        self.assertIn(out["status"], ("need_varied_recovery", "insufficient"))

    def test_panel_renders_one_block(self):
        out = cockpit.strength_lift_sensitivity_panel({
            "status": "ok",
            "lifts": [{"exercise_id": "squat", "name": "Squat", "good_rel": 1.0,
                       "poor_rel": 0.9, "drop_pct": 10.0, "n_good": 5, "n_poor": 5,
                       "flag": True}],
        })
        self.assertIn("Squat", out)
        self.assertFalse([ln for ln in out.splitlines() if ln.strip() == ""])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_strength_recovery.py::LiftSensitivityTest -v`
Expected: FAIL — `AttributeError: ... 'compute_lift_recovery_sensitivity'`.

- [ ] **Step 3: Add the analysis function**

In `analysis.py`, add after `compute_readiness_performance`:

```python
def compute_lift_recovery_sensitivity(sessions_df, sets_df, exercises_df,
                                      formula="epley", min_pairs=4, drop_flag_pct=7.0):
    """Per-exercise normalized performance on green vs red recovery days; flags
    lifts that drop >= drop_flag_pct on poor-recovery days. Pure."""
    base = {"status": "insufficient", "lifts": []}
    if (sessions_df is None or sessions_df.empty or sets_df is None or sets_df.empty
            or "recovery_zone" not in sessions_df.columns):
        return base
    enr = enrich_strength_sets(sets_df, sessions_df, exercises_df, formula)
    if enr.empty or "est_1rm_kg" not in enr.columns:
        return base
    work = enr
    if "is_warmup" in work.columns:
        work = work[pd.to_numeric(work["is_warmup"], errors="coerce").fillna(0).astype(int) == 0]
    if "completed" in work.columns:
        work = work[pd.to_numeric(work["completed"], errors="coerce").fillna(1).astype(int) == 1]
    work = work.dropna(subset=["est_1rm_kg"])
    if work.empty:
        return base

    all_best = work.groupby("exercise_id")["est_1rm_kg"].max().to_dict()
    day = (work.groupby(["session_id", "exercise_id"])["est_1rm_kg"].max().reset_index())
    day["rel"] = day.apply(
        lambda r: (r["est_1rm_kg"] / all_best[r["exercise_id"]]) if all_best.get(r["exercise_id"]) else None,
        axis=1)
    zones = sessions_df[["session_id", "recovery_zone"]]
    day = day.merge(zones, on="session_id", how="left").dropna(subset=["rel", "recovery_zone"])

    names = (dict(zip(exercises_df["exercise_id"], exercises_df["name"]))
             if exercises_df is not None and not exercises_df.empty else {})
    lifts = []
    for ex_id, g in day.groupby("exercise_id"):
        good = g[g["recovery_zone"] == "green"]["rel"]
        poor = g[g["recovery_zone"] == "red"]["rel"]
        if good.empty or poor.empty or (len(good) + len(poor)) < min_pairs:
            continue
        gm, pm = float(good.mean()), float(poor.mean())
        drop_pct = round((1 - pm / gm) * 100, 1) if gm else None
        lifts.append({
            "exercise_id": ex_id, "name": names.get(ex_id, ex_id),
            "good_rel": round(gm, 3), "poor_rel": round(pm, 3),
            "drop_pct": drop_pct, "n_good": int(len(good)), "n_poor": int(len(poor)),
            "flag": bool(drop_pct is not None and drop_pct >= drop_flag_pct),
        })
    if not lifts:
        return {"status": "need_varied_recovery", "lifts": []}
    lifts.sort(key=lambda x: (x["drop_pct"] is None, -(x["drop_pct"] or 0)))
    return {"status": "ok", "lifts": lifts}
```

- [ ] **Step 4: Add the panel renderer**

In `cockpit.py`, add after `strength_day_type_banner`:

```python
def strength_lift_sensitivity_panel(model: dict) -> str:
    model = model or {}
    status = model.get("status")
    if status != "ok":
        msg = ("Need lifts performed on both green and red recovery days to compare."
               if status == "need_varied_recovery"
               else "Log more workouts across good and poor recovery days to see "
                    "which lifts are recovery-sensitive.")
        return _collapse_html(
            f'<div class="card"><div class="empty-note" style="margin:0">'
            f'<span class="ico">⚡</span> {msg}</div></div>')
    rows = []
    for lift in model.get("lifts", [])[:8]:
        tag = '<span class="leak-flag">suffers on low recovery</span>' if lift.get("flag") else ""
        rows.append(
            f'<div class="research-stat"><div class="lab">{html.escape(str(lift.get("name")))}</div>'
            f'<div class="val tnum">−{_fmt(lift.get("drop_pct"))}%</div>'
            f'<div class="sub">green {_fmt(lift.get("good_rel"))} vs red {_fmt(lift.get("poor_rel"))} {tag}</div>'
            f'</div>')
    return _collapse_html(f'<div class="card"><div class="research-stats">{"".join(rows)}</div></div>')
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_strength_recovery.py::LiftSensitivityTest -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add analysis.py cockpit.py tests/test_strength_recovery.py
git commit -m "feat(strength-recovery): per-lift recovery-sensitivity + panel"
```

---

## Task 7: Wire into the Strength page (Log banner + Insights panel)

**Files:**
- Modify: `pages/01_Strength.py` (Log tab banner; Insights sensitivity panel)

UI wiring; verified by import + run, not pytest.

- [ ] **Step 1: Add the day-type banner to the Log tab**

In `pages/01_Strength.py`, find the `with tab_log:` block. Immediately after the `with tab_log:` line (before the existing logger content), add:

```python
    _daily_now = analysis.enrich_daily(db.load_daily_df())
    if not _daily_now.empty:
        _daily_now = analysis.compute_acwr(db.load_activities_df(), _daily_now)
    st.markdown(cockpit.strength_day_type_banner(analysis.strength_day_type(_daily_now)),
                unsafe_allow_html=True)
```

- [ ] **Step 2: Add the sensitivity panel to the Insights tab**

In `pages/01_Strength.py`, in the `with tab_insights:` block, after the existing "Readiness vs performance" panel (the block ending with the `corr["insight"]` caption around line 215), add:

```python
        st.divider()
        st.markdown("##### Recovery-sensitive lifts")
        sens = analysis.compute_lift_recovery_sensitivity(sessions, sets, catalog,
                                                          formula=config.ONE_RM_FORMULA)
        st.markdown(cockpit.strength_lift_sensitivity_panel(sens), unsafe_allow_html=True)
```

- [ ] **Step 3: Verify import + full suite**

Run: `python -c "import ast; ast.parse(open('pages/01_Strength.py').read()); print('ok')"`
Expected: `ok`
Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 4: Manual smoke (optional)**

Run: `streamlit run app.py`, open the Strength page. Confirm: the Log tab shows a "Today · <type> day" banner (or the no-recovery note); the Insights tab shows the "Recovery-sensitive lifts" panel ("need more data" until ~enough sessions). Log a workout and confirm Finish saves without error.

- [ ] **Step 5: Commit**

```bash
git add pages/01_Strength.py
git commit -m "feat(strength-recovery): day-type banner + sensitivity panel in the logger"
```

---

## Self-Review

**Spec coverage:**
- Shared `_recovery_risk` + `recovery_readiness` (inverted, `as_of`) → Task 1. ✓
- `strength_day_type` zone mapping (green→Intensity/yellow→Volume/red→Maintenance) → Task 2. ✓
- Day-type banner (label + guidance, top of Log tab) → Tasks 3, 7. ✓
- Stamp `recovery_score`/`recovery_zone` at Finish (+ migration) → Task 4. ✓
- `compute_readiness_performance` re-pointed onto recovery + per-signal HRV/sleep/RHR → Task 5. ✓
- `compute_lift_recovery_sensitivity` + panel + Insights wiring → Tasks 6, 7. ✓
- Gating (≥8 sessions; need-varied-recovery) → Tasks 5, 6. ✓
- Health Lab panel unchanged (regression) → Task 1 Step 6. ✓
- AI context: the spec lists feeding `summarize_strength`; `summarize_strength` already calls `compute_readiness_performance`, so its upgraded output (recovery-based) flows to the AI automatically — no extra task needed. Day-type is not added to the AI payload (YAGNI; the banner is the surface).

**Placeholder scan:** none — every code step shows complete code.

**Type/name consistency:** `recovery_readiness` returns `{status, score, zone, flags}` (Tasks 1, 2, 4). `strength_day_type` returns `{status, day_type, zone, score, rationale, guidance}` (Tasks 2, 3, 7). `compute_readiness_performance` adds `signals` keyed by metric (Task 5), consumed only in tests. `compute_lift_recovery_sensitivity` returns `{status, lifts:[{exercise_id,name,good_rel,poor_rel,drop_pct,n_good,n_poor,flag}]}` (Tasks 6, 7). `SESSION_COLS` gains `recovery_score`,`recovery_zone` (Task 4) used by the snapshot stamp. Consistent across tasks.

**Note:** Tasks 1–6 are pure/db/render with unit tests; Task 7 is Streamlit wiring (import/run verification). `_collapse_html`, `_fmt`, `_has_any`, `_research_recovery_flags`, `_research_recovery_flag_count`, `_trailing_true_streak`, `enrich_strength_sets`, `summarize_sessions` all already exist.
```
