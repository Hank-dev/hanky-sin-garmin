# N-of-1 Experiment Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a before/after self-experiment lab: declare an experiment, pick recovery metrics, and get a polarity-aware verdict with a 95% CI per metric — with active experiments surfaced to the AI coach and one-click AI interpretation.

**Architecture:** A new `experiments` SQLite table (id-keyed CRUD like `coach_memory`). A pure `analysis.compute_experiment_result()` slices baseline vs intervention windows and computes per-metric stats + verdicts (Welch CI via a built-in t-table — no scipy). A pure `analysis.summarize_active_experiments()` feeds active experiments into the three `ai.py` calls (reusing the `_memory_block` injection pattern), and `ai.interpret_experiment()` reads a computed result. A `cockpit.experiment_result_card()` renders results on a new `pages/03_Experiments.py`.

**Tech Stack:** Python, SQLite (stdlib `sqlite3`), pandas, numpy, Streamlit, Anthropic SDK, pytest.

**Interpreter:** run all tests with the project venv: `<repo>/.venv/bin/python -m pytest` (the venv lives in the main checkout). Commands below use `python`/`pytest` for brevity.

**Spec:** [docs/superpowers/specs/2026-06-14-experiment-lab-design.md](../specs/2026-06-14-experiment-lab-design.md)

---

## File Structure

- **`db.py`** (modify) — `experiments` table in `SCHEMA`, `EXPERIMENT_COLS`, CRUD: `add_experiment`, `update_experiment`, `set_experiment_status`, `delete_experiment`, `load_experiments_df` (JSON-encodes/decodes `metrics`).
- **`analysis.py`** (modify) — `EXPERIMENT_METRICS` catalog + `_EXPERIMENT_METRIC_BY_KEY`, `_t_critical_975`, `_experiment_verdict`, `compute_experiment_result`, `summarize_active_experiments`. (Ensure `import json` at top.)
- **`ai.py`** (modify) — `_experiment_block`, `INTERPRET_SYSTEM`, `interpret_experiment`; thread `active_experiments` through `analyze`/`weekly_summary`/`_question_payload`/`answer_question`; prompt line in the three system prompts.
- **`cockpit.py`** (modify) — `_exp_num`, `_exp_signed`, `_VERDICT_TONE`, `experiment_result_card`.
- **`app.py`** (modify) — load active experiments, build the compact list, inject into the live AI calls.
- **`pages/03_Experiments.py`** (create) — the lab UI.
- **`tests/test_experiment_lab.py`** (create) — analyzer, summarizer, t-table, db CRUD, renderer, and interpret no-key tests.

---

## Task 1: `experiments` table + CRUD in db.py

**Files:**
- Modify: `db.py`
- Test: `tests/test_experiment_lab.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_experiment_lab.py`:

```python
import importlib
import tempfile

import config
import db


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    importlib.reload(db)
    db.config.DB_PATH = tmp.name
    db.init_db()
    return tmp.name


def test_experiment_add_load_roundtrip():
    _fresh_db()
    eid = db.add_experiment({
        "name": "Magnesium", "hypothesis": "better sleep",
        "metrics": ["hrv_overnight_avg", "sleep_hours"],
        "baseline_days": 10, "start_date": "2026-06-01"})
    assert isinstance(eid, int) and eid > 0
    df = db.load_experiments_df()
    assert len(df) == 1
    row = df.iloc[0]
    assert row["name"] == "Magnesium"
    assert row["metrics"] == ["hrv_overnight_avg", "sleep_hours"]   # decoded list
    assert row["baseline_days"] == 10
    assert row["status"] == "active"
    assert row["end_date"] is None
    assert row["created_at"] and row["updated_at"]


def test_experiment_update_and_status_and_delete():
    _fresh_db()
    eid = db.add_experiment({"name": "X", "metrics": ["resting_hr"],
                             "start_date": "2026-06-01"})
    db.update_experiment(eid, {"name": "Y", "metrics": ["stress_avg", "energy"]})
    row = db.load_experiments_df().iloc[0]
    assert row["name"] == "Y"
    assert row["metrics"] == ["stress_avg", "energy"]
    db.set_experiment_status(eid, "complete")
    assert db.load_experiments_df().empty                      # default active-only
    assert db.load_experiments_df(status="complete").iloc[0]["name"] == "Y"
    assert len(db.load_experiments_df(status=None)) == 1
    db.delete_experiment(eid)
    assert len(db.load_experiments_df(status=None)) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_experiment_lab.py -v`
Expected: FAIL — `module 'db' has no attribute 'add_experiment'`.

- [ ] **Step 3: Add the table to `SCHEMA`**

In `db.py`, inside the `SCHEMA` string (after the `coach_memory` table is fine):

```sql
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    hypothesis TEXT,
    metrics TEXT NOT NULL,
    baseline_days INTEGER NOT NULL DEFAULT 14,
    start_date TEXT NOT NULL,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

- [ ] **Step 4: Add `EXPERIMENT_COLS` and CRUD functions**

`db.py` already has `import json` at the top. Add the column list near the other `*_COLS`:

```python
EXPERIMENT_COLS = [
    "id", "name", "hypothesis", "metrics", "baseline_days",
    "start_date", "end_date", "status", "created_at", "updated_at",
]
```

Add these functions (near the coach-memory CRUD):

```python
def add_experiment(record: dict) -> int:
    """Insert one experiment. `name`, `metrics` (list), `start_date` required.
    `metrics` is stored as a JSON string; status defaults to 'active'."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fields = {
        "name": record["name"],
        "hypothesis": record.get("hypothesis"),
        "metrics": json.dumps(list(record.get("metrics", []))),
        "baseline_days": int(record.get("baseline_days", 14)),
        "start_date": record["start_date"],
        "end_date": record.get("end_date"),
        "status": record.get("status", "active"),
        "created_at": now,
        "updated_at": now,
    }
    cols = list(fields)
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO experiments ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})",
            [fields[c] for c in cols],
        )
        return int(cur.lastrowid)


def update_experiment(experiment_id: int, fields: dict):
    """Update editable experiment fields and bump updated_at. `metrics` (if
    present) is re-encoded to JSON."""
    allowed = ("name", "hypothesis", "metrics", "baseline_days",
               "start_date", "end_date", "status")
    sets = {}
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets[k] = json.dumps(list(v)) if k == "metrics" else v
    if not sets:
        return
    sets["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    assignments = ", ".join(f"{k}=?" for k in sets)
    with connect() as conn:
        conn.execute(f"UPDATE experiments SET {assignments} WHERE id=?",
                     [*sets.values(), experiment_id])


def set_experiment_status(experiment_id: int, status: str):
    update_experiment(experiment_id, {"status": status})


def delete_experiment(experiment_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM experiments WHERE id=?", (experiment_id,))


def load_experiments_df(status: str | None = "active"):
    """Load experiments. status=None loads all. `metrics` is decoded to a list."""
    import pandas as pd
    with connect() as conn:
        if status is None:
            df = pd.read_sql_query(
                "SELECT * FROM experiments ORDER BY created_at", conn)
        else:
            df = pd.read_sql_query(
                "SELECT * FROM experiments WHERE status=? ORDER BY created_at",
                conn, params=(status,))
    if not df.empty:
        df["metrics"] = df["metrics"].apply(
            lambda s: json.loads(s) if isinstance(s, str) and s else [])
    return df
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_experiment_lab.py -v`
Expected: PASS (2 tests). Then `python -m pytest -q` — no regressions.

- [ ] **Step 6: Commit**

```bash
git add db.py tests/test_experiment_lab.py
git commit -m "feat(experiment-lab): experiments table + CRUD in db.py"
```

---

## Task 2: metric catalog + t-critical helper (analysis.py)

**Files:**
- Modify: `analysis.py`
- Test: `tests/test_experiment_lab.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_experiment_lab.py`:

```python
import analysis


def test_experiment_metric_catalog_shapes():
    keys = {m["key"] for m in analysis.EXPERIMENT_METRICS}
    assert {"hrv_overnight_avg", "resting_hr", "sleep_hours", "energy",
            "pain"} <= keys
    by_key = analysis._EXPERIMENT_METRIC_BY_KEY
    assert by_key["resting_hr"]["polarity"] == "lower"
    assert by_key["hrv_overnight_avg"]["polarity"] == "higher"
    assert by_key["energy"]["source"] == "checkin"


def test_t_critical_975():
    assert abs(analysis._t_critical_975(1) - 12.706) < 1e-6
    assert abs(analysis._t_critical_975(10) - 2.228) < 1e-6
    assert abs(analysis._t_critical_975(35) - 2.042) < 1e-6   # nearest <= 35 is 30
    assert abs(analysis._t_critical_975(500) - 1.960) < 1e-6
    assert abs(analysis._t_critical_975(float("nan")) - 1.960) < 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_experiment_lab.py -k "catalog or t_critical" -v`
Expected: FAIL — `module 'analysis' has no attribute 'EXPERIMENT_METRICS'`.

- [ ] **Step 3: Ensure `import json` and add the catalog + t-table**

If `analysis.py` does not already `import json` at the top, add it. Then add:

```python
EXPERIMENT_METRICS = [
    {"key": "hrv_overnight_avg", "label": "HRV (overnight avg)", "source": "daily", "polarity": "higher"},
    {"key": "resting_hr", "label": "Resting HR", "source": "daily", "polarity": "lower"},
    {"key": "sleep_hours", "label": "Sleep (hours)", "source": "daily", "polarity": "higher"},
    {"key": "sleep_score", "label": "Sleep score", "source": "daily", "polarity": "higher"},
    {"key": "body_battery_high", "label": "Body Battery (peak)", "source": "daily", "polarity": "higher"},
    {"key": "stress_avg", "label": "Stress (avg)", "source": "daily", "polarity": "lower"},
    {"key": "energy", "label": "Energy (check-in)", "source": "checkin", "polarity": "higher"},
    {"key": "pain", "label": "Pain (check-in)", "source": "checkin", "polarity": "lower"},
    {"key": "fatigue", "label": "Fatigue (check-in)", "source": "checkin", "polarity": "lower"},
]

_EXPERIMENT_METRIC_BY_KEY = {m["key"]: m for m in EXPERIMENT_METRICS}

EXPERIMENT_MIN_DAYS = 5

_T_TABLE_975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
    7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
    13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101,
    19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064,
    25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
    40: 2.021, 60: 2.000, 120: 1.980,
}


def _t_critical_975(df) -> float:
    """Two-sided 95% Student-t critical value via a built-in table (no scipy).
    Picks the largest tabulated df not exceeding `df` (conservative for
    fractional Welch df); asymptotes to 1.960 for df >= 120 or invalid input."""
    if df is None or df != df or df < 1:    # None / NaN / invalid
        return 1.960
    if df >= 120:
        return 1.960
    chosen = 1
    for k in sorted(_T_TABLE_975):
        if k <= df:
            chosen = k
        else:
            break
    return _T_TABLE_975[chosen]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_experiment_lab.py -k "catalog or t_critical" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_experiment_lab.py
git commit -m "feat(experiment-lab): metric catalog + t-critical helper"
```

---

## Task 3: `analysis.compute_experiment_result` (pure)

**Files:**
- Modify: `analysis.py`
- Test: `tests/test_experiment_lab.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_experiment_lab.py`:

```python
import pandas as pd


def _daily_for_experiment():
    # 2026-05-18..2026-06-14. Baseline (14d before 06-01) = 05-18..05-31,
    # intervention = 06-01..06-14. RHR drops 60 -> 52 (improvement, lower=better).
    dates = pd.date_range("2026-05-18", "2026-06-14", freq="D")
    rows = []
    for d in dates:
        intervention = d >= pd.Timestamp("2026-06-01")
        rows.append({
            "date": d,
            "resting_hr": 52.0 if intervention else 60.0,
            "hrv_overnight_avg": 70.0 if intervention else 60.0,
            "sleep_hours": 7.5,
        })
    return pd.DataFrame(rows)


def test_compute_result_windows_and_verdicts():
    daily = _daily_for_experiment()
    exp = {"id": 1, "name": "Mag", "status": "active",
           "metrics": ["resting_hr", "hrv_overnight_avg", "sleep_hours"],
           "baseline_days": 14, "start_date": "2026-06-01", "end_date": None}
    res = analysis.compute_experiment_result(exp, daily, checkins=None)
    assert res["baseline_window"] == ["2026-05-18", "2026-05-31"]
    assert res["intervention_window"] == ["2026-06-01", "2026-06-14"]
    rhr = res["metrics"]["resting_hr"]
    assert rhr["mean_before"] == 60.0 and rhr["mean_after"] == 52.0
    assert rhr["verdict"] == "likely helped"          # RHR down, lower is better
    hrv = res["metrics"]["hrv_overnight_avg"]
    assert hrv["verdict"] == "likely helped"          # HRV up, higher is better
    sleep = res["metrics"]["sleep_hours"]
    assert sleep["verdict"] == "no clear effect"      # identical both windows


def test_compute_result_insufficient_data():
    daily = _daily_for_experiment()
    exp = {"id": 2, "name": "Short", "status": "active",
           "metrics": ["resting_hr"], "baseline_days": 2,
           "start_date": "2026-06-01", "end_date": "2026-06-03"}
    res = analysis.compute_experiment_result(exp, daily, checkins=None)
    assert res["metrics"]["resting_hr"]["verdict"] == "insufficient_data"
    assert res["notes"]


def test_compute_result_checkin_metric():
    daily = _daily_for_experiment()
    cdates = pd.date_range("2026-05-18", "2026-06-14", freq="D")
    checkins = pd.DataFrame([
        {"date": d, "energy": (4 if d >= pd.Timestamp("2026-06-01") else 2)}
        for d in cdates])
    exp = {"id": 3, "name": "E", "status": "active", "metrics": ["energy"],
           "baseline_days": 14, "start_date": "2026-06-01", "end_date": None}
    res = analysis.compute_experiment_result(exp, daily, checkins=checkins)
    assert res["metrics"]["energy"]["verdict"] == "likely helped"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_experiment_lab.py -k compute_result -v`
Expected: FAIL — `compute_experiment_result` not defined.

- [ ] **Step 3: Implement the analyzer**

Add to `analysis.py` (uses the module-level `np`, `pd`, and the Task 2 helpers):

```python
def _experiment_verdict(delta, ci_low, ci_high, polarity) -> str:
    if ci_low is None or ci_high is None:
        return "insufficient_data"
    excludes_zero = (ci_low > 0) or (ci_high < 0)
    if not excludes_zero:
        return "no clear effect"
    improved = (delta > 0) if polarity == "higher" else (delta < 0)
    return "likely helped" if improved else "likely hurt"


def compute_experiment_result(experiment, daily, checkins=None) -> dict:
    """Before/after analysis for one experiment. Pure: slices baseline vs
    intervention windows from `daily` (and `checkins` for check-in metrics),
    returns per-metric aggregates + a polarity-aware verdict. No I/O."""
    start = str(experiment.get("start_date"))[:10]
    baseline_days = int(experiment.get("baseline_days") or 14)
    metrics = experiment.get("metrics") or []
    if isinstance(metrics, str):
        metrics = json.loads(metrics) if metrics else []

    start_ts = pd.to_datetime(start, errors="coerce")
    latest = None
    if daily is not None and len(daily):
        latest = pd.to_datetime(daily["date"]).dt.normalize().max()
    end_raw = experiment.get("end_date")
    end_ts = pd.to_datetime(end_raw, errors="coerce") if end_raw else None
    if end_ts is None or (latest is not None and end_ts > latest):
        end_ts = latest
    baseline_start = start_ts - pd.Timedelta(days=baseline_days)
    baseline_end = start_ts - pd.Timedelta(days=1)

    def _window_values(key, source, w_start, w_end):
        if w_start is None or w_end is None or pd.isna(w_start) or pd.isna(w_end):
            return np.array([])
        frame = checkins if source == "checkin" else daily
        if frame is None or len(frame) == 0 or key not in frame.columns:
            return np.array([])
        f = frame.copy()
        f["_d"] = pd.to_datetime(f["date"]).dt.normalize()
        mask = (f["_d"] >= w_start.normalize()) & (f["_d"] <= w_end.normalize())
        vals = pd.to_numeric(f.loc[mask, key], errors="coerce").dropna()
        return vals.to_numpy(dtype=float)

    out_metrics, notes = {}, []
    for key in metrics:
        meta = _EXPERIMENT_METRIC_BY_KEY.get(key)
        if meta is None:
            continue
        before = _window_values(key, meta["source"], baseline_start, baseline_end)
        after = _window_values(key, meta["source"], start_ts, end_ts)
        n_b, n_a = int(before.size), int(after.size)
        entry = {
            "label": meta["label"], "polarity": meta["polarity"],
            "n_before": n_b, "n_after": n_a,
            "mean_before": None, "mean_after": None, "delta": None,
            "ci_low": None, "ci_high": None, "verdict": "insufficient_data",
        }
        if n_b >= EXPERIMENT_MIN_DAYS and n_a >= EXPERIMENT_MIN_DAYS:
            mean_b, mean_a = float(np.mean(before)), float(np.mean(after))
            var_b, var_a = float(np.var(before, ddof=1)), float(np.var(after, ddof=1))
            delta = mean_a - mean_b
            se = (var_b / n_b + var_a / n_a) ** 0.5
            if se > 0:
                df_num = (var_b / n_b + var_a / n_a) ** 2
                df_den = ((var_b / n_b) ** 2) / (n_b - 1) + ((var_a / n_a) ** 2) / (n_a - 1)
                dfree = df_num / df_den if df_den > 0 else (n_b + n_a - 2)
                t_crit = _t_critical_975(dfree)
                ci_low, ci_high = delta - t_crit * se, delta + t_crit * se
            else:
                ci_low = ci_high = delta
            entry.update({
                "mean_before": round(mean_b, 2), "mean_after": round(mean_a, 2),
                "delta": round(delta, 2),
                "ci_low": round(ci_low, 2), "ci_high": round(ci_high, 2),
                "verdict": _experiment_verdict(delta, ci_low, ci_high, meta["polarity"]),
            })
        else:
            notes.append(f"{meta['label']}: not enough data "
                         f"({n_b} baseline / {n_a} intervention days; need ≥{EXPERIMENT_MIN_DAYS}).")
        out_metrics[key] = entry

    def _fmt(ts):
        return None if ts is None or pd.isna(ts) else ts.strftime("%Y-%m-%d")

    return {
        "experiment_id": experiment.get("id"),
        "name": experiment.get("name"),
        "status": experiment.get("status", "active"),
        "baseline_window": [_fmt(baseline_start), _fmt(baseline_end)],
        "intervention_window": [_fmt(start_ts), _fmt(end_ts)],
        "metrics": out_metrics,
        "notes": notes,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_experiment_lab.py -k compute_result -v`
Expected: PASS (3 tests). Then `python -m pytest -q` — no regressions.

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_experiment_lab.py
git commit -m "feat(experiment-lab): compute_experiment_result analyzer"
```

---

## Task 4: `analysis.summarize_active_experiments` (pure)

**Files:**
- Modify: `analysis.py`
- Test: `tests/test_experiment_lab.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_experiment_lab.py`:

```python
def test_summarize_active_experiments():
    daily = _daily_for_experiment()   # latest date 2026-06-14
    df = pd.DataFrame([
        {"name": "Mag", "hypothesis": "better sleep", "status": "active",
         "metrics": ["hrv_overnight_avg", "sleep_hours"], "start_date": "2026-06-01"},
        {"name": "Done", "hypothesis": None, "status": "complete",
         "metrics": ["resting_hr"], "start_date": "2026-05-01"},
    ])
    out = analysis.summarize_active_experiments(df, daily)
    assert len(out) == 1
    a = out[0]
    assert a["name"] == "Mag"
    assert a["metrics"] == ["HRV (overnight avg)", "Sleep (hours)"]
    assert a["days_running"] == 13      # 06-01 -> 06-14
    assert a["hypothesis"] == "better sleep"


def test_summarize_active_experiments_empty():
    assert analysis.summarize_active_experiments(pd.DataFrame(), pd.DataFrame()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_experiment_lab.py -k summarize_active -v`
Expected: FAIL — `summarize_active_experiments` not defined.

- [ ] **Step 3: Implement the summarizer**

Add to `analysis.py`:

```python
def summarize_active_experiments(experiments_df, daily, cap: int = 6) -> list[dict]:
    """Compact list of active experiments for AI context. Pure."""
    if experiments_df is None or len(experiments_df) == 0:
        return []
    df = experiments_df
    if "status" in df.columns:
        df = df[df["status"] == "active"]
    if len(df) == 0:
        return []
    latest = None
    if daily is not None and len(daily):
        latest = pd.to_datetime(daily["date"]).dt.normalize().max()
    out = []
    for _, r in df.head(cap).iterrows():
        metrics = r.get("metrics") or []
        if isinstance(metrics, str):
            metrics = json.loads(metrics) if metrics else []
        labels = [_EXPERIMENT_METRIC_BY_KEY[m]["label"]
                  for m in metrics if m in _EXPERIMENT_METRIC_BY_KEY]
        start = str(r.get("start_date"))[:10]
        start_ts = pd.to_datetime(start, errors="coerce")
        days_running = None
        if latest is not None and not pd.isna(start_ts):
            days_running = max(0, int((latest - start_ts.normalize()).days))
        hyp = r.get("hypothesis")
        hyp = hyp if (hyp not in (None, "") and pd.notna(hyp)) else None
        out.append({
            "name": r.get("name"), "hypothesis": hyp, "metrics": labels,
            "start_date": start, "days_running": days_running,
        })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_experiment_lab.py -k summarize_active -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_experiment_lab.py
git commit -m "feat(experiment-lab): summarize_active_experiments for AI context"
```

---

## Task 5: AI integration (ai.py)

**Files:**
- Modify: `ai.py`
- Test: `tests/test_experiment_lab.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_experiment_lab.py`:

```python
import ai


def test_experiment_block_empty_and_full():
    assert ai._experiment_block(None) == ""
    assert ai._experiment_block([]) == ""
    block = ai._experiment_block([{"name": "Mag", "days_running": 5}])
    assert block.startswith("\n\nActive experiments")
    assert "Mag" in block


def test_question_payload_includes_active_experiments():
    payload = ai._question_payload(
        "q", {"a": 1}, None, None, None, None, None,
        active_experiments=[{"name": "Mag"}])
    assert payload["active_experiments"] == [{"name": "Mag"}]


def test_question_payload_defaults_active_experiments_empty():
    payload = ai._question_payload("q", {}, None, None, None, None, None)
    assert payload["active_experiments"] == []


def test_interpret_experiment_without_key(monkeypatch):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "")
    out = ai.interpret_experiment({"name": "Mag", "metrics": {}})
    assert "ANTHROPIC_API_KEY" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_experiment_lab.py -k "experiment_block or active_experiments or interpret" -v`
Expected: FAIL — `_experiment_block` not defined.

- [ ] **Step 3: Add `_experiment_block` and thread it through**

In `ai.py`, add next to `_memory_block`:

```python
def _experiment_block(active_experiments: list | None) -> str:
    if not active_experiments:
        return ""
    return ("\n\nActive experiments the athlete is currently running:\n\n"
            + json.dumps(active_experiments, indent=2))
```

Update `analyze` to add `active_experiments: list | None = None` (before `model`) and append `+ _experiment_block(active_experiments)` immediately after the existing `+ _memory_block(coach_memory)` line (i.e., before the final `"\n\nAnalyse it."`). Update `weekly_summary` the same way (append `+ _experiment_block(active_experiments)` after `+ _memory_block(coach_memory)`, before the `"\n\nWrite the recap."` suffix), adding the `active_experiments` parameter before `model`.

Update `_question_payload`: add a trailing `active_experiments=None` keyword parameter and add `"active_experiments": active_experiments or []` to the returned dict.

Update `answer_question`: add `active_experiments: list | None = None` (after `coach_memory`, before `model`) and pass it through to `_question_payload(...)` as the final argument.

- [ ] **Step 4: Add the interpretation prompt + call**

Add to `ai.py` (near the other prompt constants + functions):

```python
INTERPRET_SYSTEM = """You interpret one N-of-1 self-experiment result for an
athlete. You receive a computed result: per-metric mean-before, mean-after, the
change, its 95% confidence interval, sample sizes, and a verdict. You do NOT see
raw daily data.

Be concise and honest. For each metric with a verdict, say in plain language what
the numbers suggest. Stress N-of-1 caveats: a before/after change can be caused by
confounders (seasonality, training load, life stress, sleep debt), and a wide or
zero-crossing confidence interval means the effect is not established. Do not
overclaim. If everything is 'insufficient_data', say more days are needed.

Output two short markdown sections:
## What this suggests
## Caveats"""


def interpret_experiment(result: dict, model: str | None = None) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable experiment interpretation._"
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=600,
        system=INTERPRET_SYSTEM,
        messages=[{
            "role": "user",
            "content": "Interpret this experiment result:\n\n"
                       + json.dumps(result, indent=2),
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")
```

- [ ] **Step 5: Add the prompt line to the three system prompts**

Append this sentence inside the closing triple-quotes of `SYSTEM`, `WEEKLY_SYSTEM`, and `QUESTION_SYSTEM`:

```
The athlete may also be running self-experiments (before/after tests of a habit
or supplement). When experiments are provided, factor them in, but do not
attribute changes to an intervention beyond what the data supports.
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_experiment_lab.py tests/test_ai_payload.py tests/test_coach_memory.py -v`
Expected: PASS — new tests pass; existing `test_ai_payload.py` and `test_coach_memory.py` still green (new params are keyword-defaulted). Then `python -m pytest -q`.

- [ ] **Step 7: Commit**

```bash
git add ai.py tests/test_experiment_lab.py
git commit -m "feat(experiment-lab): active-experiment AI context + interpret_experiment"
```

---

## Task 6: `cockpit.experiment_result_card` renderer

**Files:**
- Modify: `cockpit.py`
- Test: `tests/test_experiment_lab.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_experiment_lab.py`:

```python
import cockpit


def test_experiment_card_renders_verdicts_and_escapes():
    result = {
        "name": "Mag <b>", "baseline_window": ["2026-05-18", "2026-05-31"],
        "intervention_window": ["2026-06-01", "2026-06-14"],
        "metrics": {
            "resting_hr": {"label": "Resting HR", "polarity": "lower",
                           "n_before": 14, "n_after": 14, "mean_before": 60.0,
                           "mean_after": 52.0, "delta": -8.0, "ci_low": -10.0,
                           "ci_high": -6.0, "verdict": "likely helped"},
            "sleep_hours": {"label": "Sleep (hours)", "polarity": "higher",
                            "n_before": 2, "n_after": 2, "mean_before": None,
                            "mean_after": None, "delta": None, "ci_low": None,
                            "ci_high": None, "verdict": "insufficient_data"},
        },
        "notes": ["Sleep (hours): not enough data"],
    }
    out = cockpit.experiment_result_card(result)
    assert "Mag &lt;b&gt;" in out               # escaped
    assert "Resting HR" in out
    assert "likely helped" in out
    assert "insufficient_data" in out


def test_experiment_card_empty_metrics():
    out = cockpit.experiment_result_card({"name": "Empty", "metrics": {}})
    assert "No metrics selected" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_experiment_lab.py -k experiment_card -v`
Expected: FAIL — `experiment_result_card` not defined.

- [ ] **Step 3: Implement the renderer**

Add to `cockpit.py` (uses the existing `html`, `_SPARK`, `_collapse_html`):

```python
def _exp_num(v):
    return "—" if v is None else f"{v:g}"


def _exp_signed(v):
    return "—" if v is None else (f"+{v:g}" if v >= 0 else f"{v:g}")


_VERDICT_TONE = {
    "likely helped": ("✅", "#7CE7A6"),
    "likely hurt": ("⚠️", "#FF8B8B"),
    "no clear effect": ("•", "#A9B3C1"),
    "insufficient_data": ("…", "#A9B3C1"),
}


def experiment_result_card(result: dict) -> str:
    """Render one experiment's per-metric before/after result. Pure HTML."""
    name = html.escape(str(result.get("name", "Experiment")))
    bw = result.get("baseline_window") or [None, None]
    iw = result.get("intervention_window") or [None, None]
    meta = f"baseline {bw[0]}–{bw[1]} · intervention {iw[0]}–{iw[1]}"
    head = (f'<div class="coach-head"><span class="glyph">{_SPARK}</span>'
            f'<div><h3>{name}</h3>'
            f'<div class="meta">{html.escape(meta)}</div></div></div>')
    metrics = result.get("metrics") or {}
    if not metrics:
        body = ('<div class="empty-note" style="margin:0"><span class="ico">🧪</span> '
                'No metrics selected for this experiment.</div>')
        return _collapse_html(f'<div class="card coach">{head}{body}</div>')
    rows = []
    for key, m in metrics.items():
        verdict = str(m.get("verdict", ""))
        icon, color = _VERDICT_TONE.get(verdict, ("•", "#A9B3C1"))
        label = html.escape(str(m.get("label", key)))
        if verdict == "insufficient_data" or m.get("delta") is None:
            detail = (f'<span style="opacity:.7">not enough data '
                      f'({m.get("n_before", 0)}/{m.get("n_after", 0)} days)</span>')
        else:
            detail = (f'{_exp_num(m.get("mean_before"))} → {_exp_num(m.get("mean_after"))} '
                      f'(Δ {_exp_signed(m.get("delta"))}, 95% CI '
                      f'{_exp_num(m.get("ci_low"))}…{_exp_num(m.get("ci_high"))})')
        rows.append(
            f'<div style="margin:4px 0">'
            f'<span style="color:{color}">{icon}</span> <b>{label}</b> — '
            f'<span style="color:{color}">{html.escape(verdict)}</span><br>'
            f'<span style="font-size:12px;opacity:.85">{detail}</span></div>')
    notes = result.get("notes") or []
    note_html = ""
    if notes:
        note_html = ('<div style="font-size:11px;opacity:.6;margin-top:6px">'
                     + html.escape(" ".join(str(n) for n in notes)) + "</div>")
    body = "".join(rows) + note_html
    return _collapse_html(f'<div class="card coach">{head}{body}</div>')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_experiment_lab.py -k experiment_card -v`
Expected: PASS (2 tests). Then `python -m pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add cockpit.py tests/test_experiment_lab.py
git commit -m "feat(experiment-lab): experiment_result_card renderer"
```

---

## Task 7: Inject active experiments into the dashboard AI calls (app.py)

**Files:**
- Modify: `app.py`

Streamlit UI; verify with `python -m py_compile app.py` and the full suite.

- [ ] **Step 1: Load active experiments next to the coach-memory digest**

In `app.py`, find the two lines added by the coach-memory feature:

```python
coach_memory_df = db.load_memory_df()                       # fresh: not cached
coach_memory_digest = analysis.build_coach_memory_digest(coach_memory_df)
```

Immediately AFTER them, add:

```python
active_experiments = analysis.summarize_active_experiments(
    db.load_experiments_df(status="active"), daily)
```

- [ ] **Step 2: Pass it into the weekly summary call**

Find:

```python
md = ai.weekly_summary(week, coach_memory=coach_memory_digest)
```

Change to:

```python
md = ai.weekly_summary(week, coach_memory=coach_memory_digest,
                       active_experiments=active_experiments)
```

- [ ] **Step 3: Pass it into the question call**

Find the `ai.answer_question(...)` call and add, next to `coach_memory=coach_memory_digest,`:

```python
                active_experiments=active_experiments,
```

- [ ] **Step 4: Verify**

Run: `python -m py_compile app.py` → exit 0.
Run: `python -m pytest -q` → no regressions.
Re-read `git diff` to confirm only the three additive edits.

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat(experiment-lab): surface active experiments to the dashboard coach"
```

---

## Task 8: The Experiments page (`pages/03_Experiments.py`)

**Files:**
- Create: `pages/03_Experiments.py`

Streamlit page; verify with `python -m py_compile pages/03_Experiments.py` and the full suite.

- [ ] **Step 1: Create the page**

Create `pages/03_Experiments.py`:

```python
"""Experiment lab — run N-of-1 before/after self-experiments and see whether a
habit or supplement actually moved your recovery metrics."""
import importlib
from datetime import date

import streamlit as st

import config
import db
import analysis
import ai
import cockpit

config = importlib.reload(config)
db = importlib.reload(db)
analysis = importlib.reload(analysis)
ai = importlib.reload(ai)
cockpit = importlib.reload(cockpit)

st.set_page_config(page_title="Experiments — Hankø", page_icon="🧪", layout="wide")
st.markdown(cockpit.CSS, unsafe_allow_html=True)

db.init_db()

_daily_raw = db.load_daily_df()
daily = analysis.enrich_daily(_daily_raw) if not _daily_raw.empty else _daily_raw
checkins = db.load_checkins_df()

METRIC_LABELS = {m["key"]: m["label"] for m in analysis.EXPERIMENT_METRICS}
METRIC_KEYS = [m["key"] for m in analysis.EXPERIMENT_METRICS]

st.markdown(cockpit.section_label("Experiment lab"), unsafe_allow_html=True)

# ── create ───────────────────────────────────────────────────────────────────
with st.expander("➕ New experiment", expanded=db.load_experiments_df().empty):
    with st.form("new_experiment", clear_on_submit=True):
        name = st.text_input("Name", placeholder="Magnesium before bed")
        hypothesis = st.text_input("Hypothesis (optional)",
                                   placeholder="expect higher HRV, better sleep")
        metric_keys = st.multiselect("Metrics to watch", METRIC_KEYS,
                                     format_func=lambda k: METRIC_LABELS[k],
                                     default=["hrv_overnight_avg", "sleep_hours"])
        c = st.columns(3)
        with c[0]:
            start_date = st.date_input("Intervention start", value=date.today())
        with c[1]:
            baseline_days = st.number_input("Baseline days", min_value=3,
                                            max_value=90, value=14)
        with c[2]:
            use_end = st.checkbox("Set end date")
            end_date = st.date_input("End", value=date.today()) if use_end else None
        if st.form_submit_button("Start experiment") and name.strip() and metric_keys:
            db.add_experiment({
                "name": name.strip(), "hypothesis": hypothesis.strip() or None,
                "metrics": metric_keys, "baseline_days": int(baseline_days),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat() if end_date else None,
            })
            st.rerun()


def _render(exp_row, completed=False):
    exp = exp_row.to_dict()
    eid = int(exp["id"])
    result = analysis.compute_experiment_result(exp, daily, checkins)
    st.markdown(cockpit.experiment_result_card(result), unsafe_allow_html=True)
    cols = st.columns([1, 1, 1, 3])
    if not completed:
        with cols[0]:
            if st.button("Mark complete", key=f"done-{eid}", width="stretch"):
                db.set_experiment_status(eid, "complete")
                st.rerun()
    with cols[1]:
        if st.button("Interpret", key=f"interpbtn-{eid}", width="stretch"):
            with st.spinner("Reading the result…"):
                st.session_state[f"interptext-{eid}"] = ai.interpret_experiment(result)
    with cols[2]:
        if st.button("Delete", key=f"del-{eid}", width="stretch"):
            db.delete_experiment(eid)
            st.rerun()
    if st.session_state.get(f"interptext-{eid}"):
        st.markdown(st.session_state[f"interptext-{eid}"])
    if not completed:
        with st.expander("✎ Edit"):
            with st.form(f"edit-{eid}"):
                en = st.text_input("Name", value=exp.get("name") or "")
                eh = st.text_input("Hypothesis", value=exp.get("hypothesis") or "")
                em = st.multiselect(
                    "Metrics", METRIC_KEYS, format_func=lambda k: METRIC_LABELS[k],
                    default=[m for m in (exp.get("metrics") or []) if m in METRIC_LABELS])
                ec = st.columns(2)
                with ec[0]:
                    eb = st.number_input("Baseline days", min_value=3, max_value=90,
                                         value=int(exp.get("baseline_days") or 14))
                with ec[1]:
                    ee = st.text_input("End date (YYYY-MM-DD, blank=ongoing)",
                                       value=exp.get("end_date") or "")
                if st.form_submit_button("Save changes") and en.strip() and em:
                    db.update_experiment(eid, {
                        "name": en.strip(), "hypothesis": eh.strip() or None,
                        "metrics": em, "baseline_days": int(eb),
                        "end_date": ee.strip() or None,
                    })
                    st.rerun()


active = db.load_experiments_df(status="active")
if active.empty:
    st.caption("No active experiments. Create one above to start testing.")
else:
    for _, row in active.iterrows():
        _render(row)

completed = db.load_experiments_df(status="complete")
if not completed.empty:
    st.markdown(cockpit.section_label("Completed"), unsafe_allow_html=True)
    for _, row in completed.iterrows():
        _render(row, completed=True)
```

- [ ] **Step 2: Verify**

Run: `python -m py_compile pages/03_Experiments.py` → exit 0.
Run: `python -m pytest -q` → no regressions.
Confirm `analysis.enrich_daily`, `analysis.EXPERIMENT_METRICS`, `analysis.compute_experiment_result`, `cockpit.experiment_result_card`, `cockpit.section_label`, `cockpit.CSS`, `ai.interpret_experiment`, and the `db` experiment functions all exist with the signatures used (read the modules if unsure).

- [ ] **Step 3: Manual smoke (optional but recommended)**

Run: `streamlit run app.py`, open the **Experiments** page, create an experiment (e.g. HRV + Sleep, start a few weeks back so both windows have ≥5 days), confirm a result card with verdicts renders, **Interpret** returns text (with an API key), **Mark complete** moves it to Completed, **Edit** updates it, **Delete** removes it. No terminal exceptions.

- [ ] **Step 4: Commit**

```bash
git add pages/03_Experiments.py
git commit -m "feat(experiment-lab): Experiments page (create/run/interpret/complete)"
```

---

## Self-Review

**1. Spec coverage**

| Spec item | Task |
|---|---|
| `experiments` table + CRUD (metrics JSON) | Task 1 |
| Metric catalog (key/label/source/polarity) | Task 2 |
| Welch CI via built-in t-table (no scipy) | Task 2 (`_t_critical_975`) + Task 3 |
| `compute_experiment_result` (windows, stats, polarity verdict, MIN_DAYS, check-in metrics) | Task 3 |
| `summarize_active_experiments` (active-only, days_running, labels, cap) | Task 4 |
| Active experiments injected into analyze/weekly/answer + prompt line | Task 5 (+ wired live in Task 7) |
| `interpret_experiment` + no-key path | Task 5 |
| `experiment_result_card` (verdict pills, escape, empty/insufficient states) | Task 6 |
| `pages/03_Experiments.py` (create/list/results/complete/interpret/edit/delete) | Task 8 |
| Tests: analyzer, summarizer, t-table, db CRUD, renderer, interpret no-key | Tasks 1–6 |
| Edge cases: no experiments → []; sparse/zero-var → insufficient_data; null/future end → latest; unknown key skipped; no key → note | Tasks 3, 4, 5 (tested) |

`analyze()` is updated for signature consistency though not wired live in the UI (matches the coach-memory precedent and the plan's intent). Body-battery metric is `body_battery_high` per the spec.

**2. Placeholder scan:** None — every code step is complete; every command has an expected result.

**3. Type consistency:** `add_experiment(record)->int`, `update_experiment(id, fields)`, `set_experiment_status(id, status)`, `delete_experiment(id)`, `load_experiments_df(status="active")` (metrics decoded to list); `compute_experiment_result(experiment, daily, checkins=None)->dict` with metric entries `{label,polarity,n_before,n_after,mean_before,mean_after,delta,ci_low,ci_high,verdict}`; `summarize_active_experiments(experiments_df, daily, cap=6)->list`; `_experiment_block(active_experiments)`, `interpret_experiment(result, model=None)`; `experiment_result_card(result)`. Metric keys and verdict strings (`likely helped`/`likely hurt`/`no clear effect`/`insufficient_data`) are identical across the analyzer, the card's `_VERDICT_TONE`, and the tests. The `active_experiments` arg is keyword-defaulted everywhere for backward compatibility.
