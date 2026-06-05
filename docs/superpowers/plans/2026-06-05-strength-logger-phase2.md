# Strength Logger — Phase 2 Implementation Plan (Intelligence)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add strength standards (vs population), muscle-balance/asymmetry, readiness-vs-performance correlation, and AI integration on top of the Phase 1 strength logger — pure analytics + a new "Insights" tab, no new DB tables.

**Architecture:** A pure-data reference module (`strength_standards.py`) + four pure functions in `analysis.py` consuming Phase 1 data (best est-1RM from `compute_pr_timeline`). A compact `summarize_strength` dict is threaded into `ai.py` (`answer_question`/`analyze`) and built in `app.py`. New `cockpit.py` panels render a 4th "Insights" tab on the Strength page. No raw set/time-series data reaches the AI.

**Tech Stack:** Python, pandas, Streamlit, Plotly, `pytest`/`unittest`, Anthropic SDK (existing).

**Spec:** `docs/superpowers/specs/2026-06-05-strength-logger-phase2-design.md`

> **Git:** This is a normal git repo on branch `master`. Per repo convention, branch first: `git checkout -b feat/strength-logger-phase2`. Commit after each task.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `strength_standards.py` | reference tables: STANDARDS, BALANCE_TARGETS, level/percentile bands, names | Create |
| `analysis.py` | `compute_strength_standards`, `compute_balance` (+`_left_right_asymmetry`), `compute_readiness_performance`, `summarize_strength` | Modify |
| `ai.py` | `_question_payload` helper + `strength` param on `answer_question`/`analyze` + prompt | Modify |
| `app.py` | build strength summary in `load()`, pass to `answer_question` + `question_payload` | Modify |
| `cockpit.py` | `strength_standards_panel`, `strength_balance_panel`, `strength_correlation_panel` | Modify |
| `pages/01_Strength.py` | new "Insights" tab | Modify |
| `tests/test_strength_standards.py` | standards/balance/correlation/summary pure tests | Create |
| `tests/test_strength_cockpit.py` | extend with the 3 new panels | Modify |
| `tests/test_ai_payload.py` | `_question_payload` includes strength | Create |

- [ ] **Task 0: Create the feature branch**

```bash
cd "/home/jhank/vscode/hanky sin garmin" && git checkout master && git checkout -b feat/strength-logger-phase2 && git branch --show-current
```
Expected: `feat/strength-logger-phase2`

---

## Task 1: Reference data module `strength_standards.py`

**Files:**
- Create: `strength_standards.py`
- Test: `tests/test_strength_standards.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_strength_standards.py`:

```python
import strength_standards as ss


def test_levels_and_bands_consistent():
    assert ss.LEVELS == ("Untrained", "Novice", "Intermediate", "Advanced", "Elite")
    assert set(ss.LEVEL_PERCENTILE_BANDS) == set(ss.LEVELS)
    # bands are contiguous 0..100
    lows = [ss.LEVEL_PERCENTILE_BANDS[l][0] for l in ss.LEVELS]
    highs = [ss.LEVEL_PERCENTILE_BANDS[l][1] for l in ss.LEVELS]
    assert lows[0] == 0 and highs[-1] == 100
    assert highs[:-1] == lows[1:]  # each band's high == next band's low


def test_standards_cover_main_lifts_both_sexes():
    for sex in ("male", "female"):
        assert sex in ss.STANDARDS
        for lift in ("back-squat", "bench-press", "deadlift",
                     "overhead-press", "barbell-row"):
            thr = ss.STANDARDS[sex][lift]
            assert len(thr) == 4
            assert list(thr) == sorted(thr)  # strictly increasing thresholds


def test_balance_targets_well_formed():
    for t in ss.BALANCE_TARGETS:
        assert {"numerator", "denominator", "label", "low", "ideal", "high",
                "reason"} <= set(t)
        assert t["low"] <= t["ideal"] <= t["high"]


def test_asymmetry_flag_pct_is_positive_number():
    assert isinstance(ss.ASYMMETRY_FLAG_PCT, (int, float))
    assert ss.ASYMMETRY_FLAG_PCT > 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && source .venv/bin/activate 2>/dev/null; python -m pytest tests/test_strength_standards.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strength_standards'`

- [ ] **Step 3: Create `strength_standards.py`**

```python
"""Strength norms for the Phase 2 intelligence layer. Pure data, no imports.

All values are approximate, population-level references (StrengthLevel / ExRx
style) expressed as lift ÷ bodyweight ratios. They are tuning parameters: adjust
here without touching analysis code. No age adjustment (open/adult standards).
"""

LEVELS = ("Untrained", "Novice", "Intermediate", "Advanced", "Elite")

# Percentile band each level maps to (contiguous, 0..100).
LEVEL_PERCENTILE_BANDS = {
    "Untrained": (0, 20),
    "Novice": (20, 50),
    "Intermediate": (50, 80),
    "Advanced": (80, 95),
    "Elite": (95, 100),
}

MAIN_LIFT_NAMES = {
    "back-squat": "Back Squat",
    "bench-press": "Bench Press",
    "deadlift": "Deadlift",
    "overhead-press": "Overhead Press",
    "barbell-row": "Barbell Row",
}

# {sex: {exercise_id: (novice, intermediate, advanced, elite)}} minimum
# lift÷bodyweight ratio to reach each level; below novice = Untrained.
STANDARDS = {
    "male": {
        "back-squat": (0.75, 1.25, 1.75, 2.25),
        "bench-press": (0.5, 1.0, 1.5, 2.0),
        "deadlift": (1.0, 1.5, 2.25, 2.75),
        "overhead-press": (0.35, 0.6, 0.9, 1.2),
        "barbell-row": (0.5, 0.85, 1.15, 1.5),
    },
    "female": {
        "back-squat": (0.5, 0.9, 1.35, 1.8),
        "bench-press": (0.3, 0.6, 0.95, 1.35),
        "deadlift": (0.6, 1.1, 1.6, 2.1),
        "overhead-press": (0.2, 0.4, 0.6, 0.85),
        "barbell-row": (0.3, 0.55, 0.8, 1.1),
    },
}

# Cross-movement strength-ratio targets (numerator 1RM ÷ denominator 1RM).
BALANCE_TARGETS = [
    {"numerator": "bench-press", "denominator": "back-squat",
     "label": "Bench : Squat", "low": 0.5, "ideal": 0.66, "high": 0.8,
     "reason": "upper vs lower push balance"},
    {"numerator": "overhead-press", "denominator": "bench-press",
     "label": "OHP : Bench", "low": 0.5, "ideal": 0.6, "high": 0.7,
     "reason": "vertical vs horizontal push"},
    {"numerator": "barbell-row", "denominator": "bench-press",
     "label": "Row : Bench", "low": 0.8, "ideal": 0.9, "high": 1.05,
     "reason": "horizontal pull vs push"},
    {"numerator": "deadlift", "denominator": "back-squat",
     "label": "Deadlift : Squat", "low": 1.1, "ideal": 1.2, "high": 1.35,
     "reason": "posterior vs anterior chain"},
]

# Flag a unilateral lift when |L-R| / max(L,R) * 100 exceeds this.
ASYMMETRY_FLAG_PCT = 10.0
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_standards.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add strength_standards.py tests/test_strength_standards.py
git commit -m "feat(strength): phase2 reference norms module

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `analysis.compute_strength_standards`

**Files:**
- Modify: `analysis.py` (append to the strength section at end of file)
- Test: `tests/test_strength_standards.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_strength_standards.py`:

```python
import analysis


def test_standards_levels_and_percentiles_at_boundaries():
    # bodyweight 100 → ratio == 1RM/100
    best = {"back-squat": 125.0, "bench-press": 100.0}
    out = analysis.compute_strength_standards(best, {"sex": "male"}, 100.0)
    assert out["status"] == "ok"
    sq = [l for l in out["lifts"] if l["exercise_id"] == "back-squat"][0]
    # 1.25 == Intermediate lower bound → percentile 50.0
    assert sq["level"] == "Intermediate"
    assert sq["percentile"] == 50.0
    # overall is the mean of the graded lifts
    assert out["overall"]["level"] == "Intermediate"


def test_standards_need_profile_when_sex_or_weight_missing():
    assert analysis.compute_strength_standards({"back-squat": 100.0}, {}, 100.0)["status"] == "need_profile"
    assert analysis.compute_strength_standards({"back-squat": 100.0}, {"sex": "male"}, 0)["status"] == "need_profile"


def test_standards_omits_unlogged_lifts_and_handles_none():
    out = analysis.compute_strength_standards({"back-squat": 150.0}, {"sex": "male"}, 100.0)
    assert out["graded_lifts"] == 1
    # 1.5 < 1.75 → Advanced? thresholds (0.75,1.25,1.75,2.25): 1.5 is Intermediate
    sq = out["lifts"][0]
    assert sq["level"] == "Intermediate"


def test_standards_no_main_lifts_logged():
    out = analysis.compute_strength_standards({"barbell-curl": 40.0}, {"sex": "male"}, 100.0)
    assert out["status"] == "no_main_lifts"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_standards.py -k standards_levels -v`
Expected: FAIL — `AttributeError: module 'analysis' has no attribute 'compute_strength_standards'`

- [ ] **Step 3: Append to the strength section of `analysis.py`**

```python


def compute_strength_standards(best_1rm_by_exercise, profile, bodyweight_kg):
    """Grade main-lift est-1RMs against population norms (ratio table). Pure.

    best_1rm_by_exercise: {exercise_id: best_est_1rm_kg}. Returns
    {status:'ok', lifts:[...], overall:{level,percentile}, graded_lifts:n} or a
    {status:'need_profile'/'no_main_lifts'} marker.
    """
    import strength_standards as ss
    profile = profile or {}
    sex = (profile.get("sex") or "").strip().lower()
    missing = []
    if sex not in ss.STANDARDS:
        missing.append("sex")
    try:
        bw = float(bodyweight_kg)
    except (TypeError, ValueError):
        bw = 0.0
    if bw <= 0:
        missing.append("bodyweight")
    if missing:
        return {"status": "need_profile", "missing": missing}

    best_map = best_1rm_by_exercise or {}
    lifts = []
    for ex_id, thr in ss.STANDARDS[sex].items():
        try:
            best = float(best_map.get(ex_id))
        except (TypeError, ValueError):
            continue
        if best <= 0:
            continue
        ratio = best / bw
        nov, inter, adv, eli = thr
        if ratio < nov:
            level, lo, hi = "Untrained", 0.0, nov
        elif ratio < inter:
            level, lo, hi = "Novice", nov, inter
        elif ratio < adv:
            level, lo, hi = "Intermediate", inter, adv
        elif ratio < eli:
            level, lo, hi = "Advanced", adv, eli
        else:
            level, lo, hi = "Elite", eli, eli * 1.25
        plo, phi = ss.LEVEL_PERCENTILE_BANDS[level]
        frac = 1.0 if hi <= lo else (ratio - lo) / (hi - lo)
        frac = min(max(frac, 0.0), 1.0)
        pct = round(plo + frac * (phi - plo), 1)
        lifts.append({
            "exercise_id": ex_id, "name": ss.MAIN_LIFT_NAMES.get(ex_id, ex_id),
            "est_1rm_kg": round(best, 1), "ratio": round(ratio, 2),
            "level": level, "percentile": pct,
        })

    if not lifts:
        return {"status": "no_main_lifts", "lifts": [], "overall": None,
                "graded_lifts": 0}
    mean_pct = sum(l["percentile"] for l in lifts) / len(lifts)
    overall_level = "Elite"
    for lv in ss.LEVELS:
        if mean_pct < ss.LEVEL_PERCENTILE_BANDS[lv][1]:
            overall_level = lv
            break
    return {"status": "ok", "lifts": lifts,
            "overall": {"level": overall_level, "percentile": round(mean_pct, 1)},
            "graded_lifts": len(lifts)}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_standards.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_strength_standards.py
git commit -m "feat(strength): compute_strength_standards

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `analysis.compute_balance` (+ `_left_right_asymmetry`)

**Files:**
- Modify: `analysis.py`
- Test: `tests/test_strength_standards.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_strength_standards.py`:

```python
import pandas as pd


def test_balance_ratio_ok_and_under():
    # bench:squat = 100/125 = 0.8 → within [0.5,0.8] → ok
    out = analysis.compute_balance({"bench-press": 100.0, "back-squat": 125.0},
                                   pd.DataFrame(), pd.DataFrame())
    bs = [r for r in out["ratios"] if r["label"] == "Bench : Squat"][0]
    assert bs["status"] == "ok"
    # bench weak: 50/200 = 0.25 < 0.5 → under, weak bench
    out2 = analysis.compute_balance({"bench-press": 50.0, "back-squat": 200.0},
                                    pd.DataFrame(), pd.DataFrame())
    bs2 = [r for r in out2["ratios"] if r["label"] == "Bench : Squat"][0]
    assert bs2["status"] == "under"
    assert bs2["weak_side"] == "bench-press"


def test_balance_skips_missing_lift():
    out = analysis.compute_balance({"bench-press": 100.0}, pd.DataFrame(), pd.DataFrame())
    # Bench:Squat needs squat too → skipped
    assert not any(r["label"] == "Bench : Squat" for r in out["ratios"])


def test_left_right_asymmetry_flag():
    exercises = pd.DataFrame([{"exercise_id": "bulgarian-split-squat",
                               "name": "Bulgarian Split Squat", "is_unilateral": 1}])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "bulgarian-split-squat", "side": "left",
         "reps": 5, "weight_kg": 40.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s1", "exercise_id": "bulgarian-split-squat", "side": "right",
         "reps": 5, "weight_kg": 50.0, "is_warmup": 0, "completed": 1},
    ])
    out = analysis.compute_balance({}, sets, exercises)
    lr = out["left_right"][0]
    assert lr["stronger_side"] == "right"
    assert lr["flagged"] is True       # ~20% diff > 10%
    assert lr["diff_pct"] > 10


def test_left_right_not_flagged_when_balanced():
    exercises = pd.DataFrame([{"exercise_id": "bulgarian-split-squat",
                               "name": "Bulgarian Split Squat", "is_unilateral": 1}])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "bulgarian-split-squat", "side": "left",
         "reps": 5, "weight_kg": 48.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s1", "exercise_id": "bulgarian-split-squat", "side": "right",
         "reps": 5, "weight_kg": 50.0, "is_warmup": 0, "completed": 1},
    ])
    out = analysis.compute_balance({}, sets, exercises)
    assert out["left_right"][0]["flagged"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_standards.py -k balance -v`
Expected: FAIL — `AttributeError: ... 'compute_balance'`

- [ ] **Step 3: Append to the strength section of `analysis.py`**

```python


def _left_right_asymmetry(sets_df, exercises_df, flag_pct):
    if (sets_df is None or sets_df.empty
            or exercises_df is None or exercises_df.empty
            or "is_unilateral" not in exercises_df.columns
            or "side" not in sets_df.columns):
        return []
    uni = exercises_df[pd.to_numeric(exercises_df["is_unilateral"], errors="coerce")
                       .fillna(0).astype(int) == 1]
    if uni.empty:
        return []
    uni_ids = set(uni["exercise_id"])
    name_map = dict(zip(exercises_df["exercise_id"], exercises_df["name"]))

    df = sets_df.copy()
    for col, default in (("is_warmup", 0), ("completed", 1)):
        if col not in df.columns:
            df[col] = default
    warm = pd.to_numeric(df["is_warmup"], errors="coerce").fillna(0).astype(int)
    done = pd.to_numeric(df["completed"], errors="coerce").fillna(1).astype(int)
    df = df[(warm == 0) & (done == 1) & df["exercise_id"].isin(uni_ids)]
    if df.empty:
        return []

    out = []
    for ex_id, grp in df.groupby("exercise_id"):
        best = {}
        for side in ("left", "right"):
            sub = grp[grp["side"] == side]
            vals = [estimate_1rm(w, r) for w, r in zip(sub["weight_kg"], sub["reps"])]
            vals = [v for v in vals if v is not None]
            if vals:
                best[side] = max(vals)
        if "left" in best and "right" in best:
            l, r = best["left"], best["right"]
            hi = max(l, r)
            diff = abs(l - r) / hi * 100 if hi > 0 else 0.0
            out.append({
                "name": name_map.get(ex_id, ex_id),
                "left_1rm_kg": round(l, 1), "right_1rm_kg": round(r, 1),
                "diff_pct": round(diff, 1), "flagged": bool(diff > flag_pct),
                "stronger_side": "left" if l > r else ("right" if r > l else "even"),
            })
    return out


def compute_balance(best_1rm_by_exercise, sets_df, exercises_df):
    """Cross-movement strength ratios + left/right asymmetry. Pure."""
    import strength_standards as ss
    best_map = best_1rm_by_exercise or {}
    ratios = []
    for t in ss.BALANCE_TARGETS:
        try:
            num = float(best_map.get(t["numerator"]))
            den = float(best_map.get(t["denominator"]))
        except (TypeError, ValueError):
            continue
        if num <= 0 or den <= 0:
            continue
        r = num / den
        if r < t["low"]:
            status, weak = "under", t["numerator"]
        elif r > t["high"]:
            status, weak = "over", t["denominator"]
        else:
            status, weak = "ok", None
        ratios.append({"label": t["label"], "ratio": round(r, 2),
                       "low": t["low"], "ideal": t["ideal"], "high": t["high"],
                       "status": status, "weak_side": weak, "reason": t["reason"]})
    return {"ratios": ratios,
            "left_right": _left_right_asymmetry(sets_df, exercises_df,
                                                ss.ASYMMETRY_FLAG_PCT)}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_standards.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_strength_standards.py
git commit -m "feat(strength): compute_balance (ratios + left/right)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `analysis.compute_readiness_performance`

**Files:**
- Modify: `analysis.py`
- Test: `tests/test_strength_standards.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_strength_standards.py`:

```python
def _bench_only_exercises():
    return pd.DataFrame([{"exercise_id": "bench-press", "is_bodyweight": 0}])


def test_readiness_perf_insufficient_below_min():
    sessions = pd.DataFrame([
        {"session_id": f"s{i}", "date": f"2026-05-0{i+1}", "bodyweight_kg": 80.0,
         "readiness_score": 70} for i in range(3)])
    sets = pd.DataFrame([
        {"session_id": f"s{i}", "exercise_id": "bench-press", "reps": 5,
         "weight_kg": 100.0, "is_warmup": 0, "completed": 1} for i in range(3)])
    out = analysis.compute_readiness_performance(sessions, sets, _bench_only_exercises())
    assert out["status"] == "insufficient"
    assert out["have"] == 3 and out["need"] == 8


def test_readiness_perf_positive_correlation_when_better_on_high_readiness():
    # 10 sessions: readiness rises with weight → positive correlation
    rows_s, rows_x = [], []
    for i in range(10):
        readiness = 40 + i * 6          # 40..94
        weight = 80 + i * 4             # 80..116 (best at highest readiness)
        rows_s.append({"session_id": f"s{i}", "date": f"2026-05-{i+1:02d}",
                       "bodyweight_kg": 80.0, "readiness_score": readiness})
        rows_x.append({"session_id": f"s{i}", "exercise_id": "bench-press",
                       "reps": 1, "weight_kg": float(weight),
                       "is_warmup": 0, "completed": 1})
    out = analysis.compute_readiness_performance(
        pd.DataFrame(rows_s), pd.DataFrame(rows_x), _bench_only_exercises())
    assert out["status"] == "ok"
    assert out["n"] == 10
    assert out["correlation"] is not None and out["correlation"] > 0.5
    assert set(out["buckets"]).issubset({"Low", "Med", "High"})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_standards.py -k readiness_perf -v`
Expected: FAIL — `AttributeError: ... 'compute_readiness_performance'`

- [ ] **Step 3: Append to the strength section of `analysis.py`**

```python


def compute_readiness_performance(sessions_df, sets_df, exercises_df, min_sessions=8):
    """Correlate the per-session readiness snapshot with normalized lifting
    performance (day-best est-1RM ÷ all-time-best, averaged over the day's
    lifts). Gated until `min_sessions` readiness-tagged sessions exist. Pure.
    """
    insufficient = {"status": "insufficient", "have": 0, "need": min_sessions}
    if (sessions_df is None or sessions_df.empty
            or sets_df is None or sets_df.empty):
        return insufficient
    enr = enrich_strength_sets(sets_df, sessions_df, exercises_df)
    if enr.empty or "est_1rm_kg" not in enr.columns:
        return insufficient
    work = enr
    if "is_warmup" in work.columns:
        work = work[pd.to_numeric(work["is_warmup"], errors="coerce").fillna(0).astype(int) == 0]
    if "completed" in work.columns:
        work = work[pd.to_numeric(work["completed"], errors="coerce").fillna(1).astype(int) == 1]
    work = work.dropna(subset=["est_1rm_kg"])
    if work.empty:
        return insufficient

    all_best = work.groupby("exercise_id")["est_1rm_kg"].max().to_dict()
    day = (work.groupby(["session_id", "exercise_id"])["est_1rm_kg"].max()
               .reset_index())
    day["rel"] = day.apply(
        lambda r: (r["est_1rm_kg"] / all_best[r["exercise_id"]])
        if all_best.get(r["exercise_id"]) else None, axis=1)
    day["is_pr_today"] = day.apply(
        lambda r: abs(r["est_1rm_kg"] - all_best.get(r["exercise_id"], 0)) < 1e-9,
        axis=1)
    sess = (day.groupby("session_id")
               .agg(rel_perf=("rel", "mean"), pr=("is_pr_today", "any"))
               .reset_index())

    ton = summarize_sessions(sessions_df, sets_df, exercises_df)[
        ["session_id", "total_volume_kg"]]
    rsc = sessions_df[["session_id", "readiness_score"]].copy()
    rsc["readiness_score"] = pd.to_numeric(rsc["readiness_score"], errors="coerce")
    merged = (sess.merge(rsc, on="session_id", how="left")
                  .merge(ton, on="session_id", how="left")
                  .dropna(subset=["readiness_score", "rel_perf"]))
    have = int(len(merged))
    if have < min_sessions:
        return {"status": "insufficient", "have": have, "need": min_sessions}

    def bucket(x):
        return "Low" if x < 50 else ("Med" if x <= 75 else "High")
    merged["bucket"] = merged["readiness_score"].apply(bucket)
    buckets = {}
    for b in ("Low", "Med", "High"):
        bb = merged[merged["bucket"] == b]
        if bb.empty:
            continue
        buckets[b] = {
            "n": int(len(bb)),
            "avg_rel_perf": round(float(bb["rel_perf"].mean()), 3),
            "pr_rate": round(float(bb["pr"].mean()), 2),
            "avg_tonnage": round(float(bb["total_volume_kg"].fillna(0).mean()), 0),
        }
    corr = merged["readiness_score"].corr(merged["rel_perf"])
    corr = None if pd.isna(corr) else round(float(corr), 2)
    if corr is not None and corr >= 0.3:
        insight = "You tend to hit better lifts on higher-readiness days."
    elif corr is not None and corr <= -0.3:
        insight = "Your best lifts cluster on lower-readiness days — readiness isn't limiting your lifting."
    else:
        insight = "No strong link between readiness and lifting performance so far."
    return {"status": "ok", "n": have, "buckets": buckets,
            "correlation": corr, "insight": insight}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_standards.py -v`
Expected: PASS (14 passed)

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_strength_standards.py
git commit -m "feat(strength): compute_readiness_performance

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `analysis.summarize_strength`

**Files:**
- Modify: `analysis.py`
- Test: `tests/test_strength_standards.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_strength_standards.py`:

```python
def test_summarize_strength_shape_and_no_raw_sets():
    sessions = pd.DataFrame([{"session_id": "s1", "date": "2026-06-05",
                              "bodyweight_kg": 100.0, "readiness_score": 70}])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "back-squat", "reps": 1,
         "weight_kg": 125.0, "is_warmup": 0, "completed": 1, "side": "both",
         "set_id": "x1", "position": 0, "set_index": 1}])
    exercises = pd.DataFrame([{"exercise_id": "back-squat", "name": "Back Squat",
                               "is_bodyweight": 0, "is_unilateral": 0}])
    out = analysis.summarize_strength(sessions, sets, exercises, {"sex": "male"}, 100.0)
    assert out["status"] == "ok"
    assert out["standards"]["overall"]["level"] == "Intermediate"
    assert "recent" in out and "balance_flags" in out and "readiness_link" in out
    # no raw set fields anywhere in the payload
    import json
    blob = json.dumps(out)
    for forbidden in ("set_id", '"reps"', '"side"', "position", "set_index"):
        assert forbidden not in blob


def test_summarize_strength_empty():
    assert analysis.summarize_strength(pd.DataFrame(), pd.DataFrame(),
                                       pd.DataFrame(), {}, None)["status"] == "no_data"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_standards.py -k summarize_strength -v`
Expected: FAIL — `AttributeError: ... 'summarize_strength'`

- [ ] **Step 3: Append to the strength section of `analysis.py`**

```python


def summarize_strength(sessions_df, sets_df, exercises_df, profile,
                       bodyweight_kg, lookback_days=28):
    """Compact, raw-data-free strength summary for the AI coach. Pure."""
    if sessions_df is None or sessions_df.empty:
        return {"status": "no_data"}

    pr = compute_pr_timeline(sets_df, sessions_df, exercises_df)
    best_map = (pr.groupby("exercise_id")["best_est_1rm_kg"].max().to_dict()
                if not pr.empty else {})
    standards = compute_strength_standards(best_map, profile, bodyweight_kg)
    balance = compute_balance(best_map, sets_df, exercises_df)
    readiness_link = compute_readiness_performance(sessions_df, sets_df, exercises_df)

    sdf = sessions_df.copy()
    sdf["date"] = pd.to_datetime(sdf["date"], errors="coerce")
    last = sdf["date"].max()
    cutoff = last - pd.Timedelta(days=lookback_days)
    recent = sdf[sdf["date"] >= cutoff]

    summ = summarize_sessions(sessions_df, sets_df, exercises_df)
    recent_ids = set(recent["session_id"])
    recent_tonnage = (float(summ[summ["session_id"].isin(recent_ids)]
                            ["total_volume_kg"].sum()) if not summ.empty else 0.0)
    sessions_per_week = round(len(recent) / (lookback_days / 7.0), 1) if len(recent) else 0.0

    name_map = (dict(zip(exercises_df["exercise_id"], exercises_df["name"]))
                if exercises_df is not None and not exercises_df.empty else {})
    recent_prs = []
    if not pr.empty:
        p = pr.copy()
        p["date"] = pd.to_datetime(p["date"], errors="coerce")
        p = p[(p["is_pr"] == True) & (p["date"] >= cutoff)]  # noqa: E712
        for _, r in p.sort_values("date").iterrows():
            recent_prs.append({"exercise": name_map.get(r["exercise_id"], r["exercise_id"]),
                               "est_1rm_kg": round(float(r["best_est_1rm_kg"]), 1),
                               "date": str(r["date"].date())})

    if standards.get("status") == "ok":
        standards_out = {
            "overall": standards["overall"],
            "by_lift": [{"name": l["name"], "level": l["level"],
                         "percentile": l["percentile"]} for l in standards["lifts"]],
        }
    else:
        standards_out = {"status": standards.get("status")}

    if readiness_link.get("status") == "ok":
        readiness_out = {"status": "ok", "correlation": readiness_link.get("correlation"),
                         "insight": readiness_link.get("insight")}
    else:
        readiness_out = {"status": readiness_link.get("status"),
                         "have": readiness_link.get("have"),
                         "need": readiness_link.get("need")}

    return {
        "status": "ok",
        "recent": {"sessions": int(len(recent)), "tonnage_kg": round(recent_tonnage, 0),
                   "sessions_per_week": sessions_per_week, "lookback_days": lookback_days},
        "standards": standards_out,
        "balance_flags": {
            "ratios": [r for r in balance["ratios"] if r["status"] != "ok"],
            "left_right": [lr for lr in balance["left_right"] if lr["flagged"]],
        },
        "readiness_link": readiness_out,
        "recent_prs": recent_prs,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_standards.py -v`
Expected: PASS (16 passed). Also run full suite: `python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_strength_standards.py
git commit -m "feat(strength): summarize_strength for AI

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: AI integration in `ai.py`

**Files:**
- Modify: `ai.py`
- Test: `tests/test_ai_payload.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ai_payload.py`:

```python
import ai


def test_question_payload_includes_strength_and_question():
    payload = ai._question_payload(
        question="how is my bench?",
        summary={"a": 1},
        capacity={"c": 2},
        stress_leak_map={"s": 3},
        grappling_sessions=[{"g": 4}],
        prebed_discovery={"p": 5},
        chat_history=[{"role": "user", "content": "hi"}],
        strength={"standards": {"overall": {"level": "Intermediate"}}},
    )
    assert payload["question"] == "how is my bench?"
    assert payload["metrics_summary"] == {"a": 1}
    assert payload["strength_profile"] == {"standards": {"overall": {"level": "Intermediate"}}}


def test_question_payload_defaults_strength_to_empty():
    payload = ai._question_payload("q", {}, None, None, None, None, None, None)
    assert payload["strength_profile"] == {}


def test_answer_question_accepts_strength_kwarg_without_key(monkeypatch):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "")
    # no key → returns the stub string, but must accept the strength kwarg
    out = ai.answer_question("q", {"a": 1}, strength={"x": 1})
    assert "ANTHROPIC_API_KEY" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_ai_payload.py -v`
Expected: FAIL — `AttributeError: module 'ai' has no attribute '_question_payload'`

- [ ] **Step 3: Edit `ai.py`**

First, extend the `QUESTION_SYSTEM` prompt. Find the line in `QUESTION_SYSTEM`:

```python
only the compact Garmin metrics, capacity-envelope model, stress-leak map,
computed grappling metrics, pre-sleep discovery patterns, and check-in context
provided. You are not a doctor and you must not diagnose disease.
```

Replace it with:

```python
only the compact Garmin metrics, capacity-envelope model, stress-leak map,
computed grappling metrics, pre-sleep discovery patterns, strength-training
profile (standards vs population, muscle-balance flags, lifting load, and any
readiness-vs-performance link), and check-in context provided. You are not a
doctor and you must not diagnose disease.
```

Add a `_question_payload` helper and refactor `answer_question` to use it. Replace the body of `answer_question` from the `payload = {` block. The current code is:

```python
    payload = {
        "question": question,
        "metrics_summary": summary,
        "capacity_envelope": capacity or {},
        "stress_leak_map": stress_leak_map or {},
        "grappling_sessions": grappling_sessions or [],
        "prebed_discovery": prebed_discovery or {},
        "previous_chat": chat_history or [],
    }
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
```

Replace that block with:

```python
    payload = _question_payload(question, summary, capacity, stress_leak_map,
                                grappling_sessions, prebed_discovery, chat_history,
                                strength)
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
```

Change the `answer_question` signature. Current:

```python
def answer_question(
    question: str,
    summary: dict,
    capacity: dict | None = None,
    stress_leak_map: dict | None = None,
    grappling_sessions: list[dict] | None = None,
    prebed_discovery: dict | None = None,
    chat_history: list[dict] | None = None,
    model: str | None = None,
) -> str:
```

Replace with (adds `strength` before `model`, preserving positional compatibility):

```python
def answer_question(
    question: str,
    summary: dict,
    capacity: dict | None = None,
    stress_leak_map: dict | None = None,
    grappling_sessions: list[dict] | None = None,
    prebed_discovery: dict | None = None,
    chat_history: list[dict] | None = None,
    strength: dict | None = None,
    model: str | None = None,
) -> str:
```

Add the `_question_payload` helper immediately **above** `def answer_question(`:

```python
def _question_payload(question, summary, capacity, stress_leak_map,
                      grappling_sessions, prebed_discovery, chat_history,
                      strength=None):
    return {
        "question": question,
        "metrics_summary": summary,
        "capacity_envelope": capacity or {},
        "stress_leak_map": stress_leak_map or {},
        "grappling_sessions": grappling_sessions or [],
        "prebed_discovery": prebed_discovery or {},
        "strength_profile": strength or {},
        "previous_chat": chat_history or [],
    }


```

Finally, thread `strength` into `analyze` for completeness. Change its signature:

```python
def analyze(summary: dict, model: str | None = None) -> str:
```

to:

```python
def analyze(summary: dict, strength: dict | None = None, model: str | None = None) -> str:
```

and change its message content. Current:

```python
            "content": "Here is my recent Garmin summary as JSON:\n\n"
                       + json.dumps(summary, indent=2)
                       + "\n\nAnalyse it.",
```

to:

```python
            "content": "Here is my recent Garmin summary as JSON:\n\n"
                       + json.dumps(summary, indent=2)
                       + "\n\nStrength-training profile:\n\n"
                       + json.dumps(strength or {}, indent=2)
                       + "\n\nAnalyse it.",
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_ai_payload.py -v`
Expected: PASS (3 passed). Full suite: `python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add ai.py tests/test_ai_payload.py
git commit -m "feat(strength): thread strength profile into AI coach

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Wire the strength summary into `app.py`

**Files:**
- Modify: `app.py`

> Streamlit orchestration — verify by AppTest smoke (no unit test).

- [ ] **Step 1: Build the strength summary inside `load()`**

In `app.py`, find the end of `load()`. The current final lines are:

```python
    stress_leaks = analysis.compute_stress_leak_map(daily, stress)
    prebed_discovery = analysis.compute_prebed_discovery(daily, acts, sleep_timing)
    return daily, acts, checkins, body_battery, stress, grappling, stress_leaks, prebed_discovery
```

Replace them with:

```python
    stress_leaks = analysis.compute_stress_leak_map(daily, stress)
    prebed_discovery = analysis.compute_prebed_discovery(daily, acts, sleep_timing)
    strength_sessions = db.load_strength_sessions_df()
    strength_sets = db.load_strength_sets_df()
    exercises = db.load_exercises_df()
    profile = db.load_profile()
    body_metrics = db.load_body_metrics_df()
    bodyweight = None
    if not body_metrics.empty:
        bw = body_metrics.dropna(subset=["weight_kg"]).sort_values("date")
        if not bw.empty:
            bodyweight = float(bw.iloc[-1]["weight_kg"])
    strength_summary = analysis.summarize_strength(
        strength_sessions, strength_sets, exercises, profile, bodyweight)
    return (daily, acts, checkins, body_battery, stress, grappling,
            stress_leaks, prebed_discovery, strength_summary)
```

- [ ] **Step 2: Update the unpack at module level**

Find:

```python
daily, acts, checkins, body_battery, stress, grappling, stress_leaks, prebed_discovery = load(config.LOCAL_TIMEZONE)
```

Replace with:

```python
(daily, acts, checkins, body_battery, stress, grappling, stress_leaks,
 prebed_discovery, strength_summary) = load(config.LOCAL_TIMEZONE)
```

- [ ] **Step 3: Add the strength summary to the AI payload + call**

Find:

```python
    "prebed_discovery": {
        "status": prebed_discovery.get("status"),
        "message": prebed_discovery.get("message"),
        "relationships": prebed_discovery.get("relationships", []),
    },
    "selected_day": selected_day,
}
```

Replace with:

```python
    "prebed_discovery": {
        "status": prebed_discovery.get("status"),
        "message": prebed_discovery.get("message"),
        "relationships": prebed_discovery.get("relationships", []),
    },
    "strength_profile": strength_summary,
    "selected_day": selected_day,
}
```

Find the `ai.answer_question(...)` call:

```python
            answer = ai.answer_question(
                pending_prompt,
                question_summary,
                capacity,
                stress_leaks,
                grappling[:3],
                question_payload["prebed_discovery"],
                history,
            )
```

Replace with (adds the `strength` keyword):

```python
            answer = ai.answer_question(
                pending_prompt,
                question_summary,
                capacity,
                stress_leaks,
                grappling[:3],
                question_payload["prebed_discovery"],
                history,
                strength=strength_summary,
            )
```

- [ ] **Step 4: Verify parse + AppTest smoke of the whole dashboard**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -c "import ast; ast.parse(open('app.py').read()); print('parse ok')"` → `parse ok`

Then:
```bash
cd "/home/jhank/vscode/hanky sin garmin" && source .venv/bin/activate 2>/dev/null; python -c "
from streamlit.testing.v1 import AppTest
at = AppTest.from_file('app.py', default_timeout=60).run()
assert not at.exception, at.exception
print('app.py AppTest render ok')
"
```
Expected: `app.py AppTest render ok` with no exception. If `streamlit.testing` is unavailable, rely on the parse check. A real `at.exception` is a failure — STOP and report BLOCKED with the text.

- [ ] **Step 5: Full suite + commit**

Run: `python -m pytest -q` → all pass.
```bash
git add app.py
git commit -m "feat(strength): feed strength summary to the dashboard AI coach

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Insights render helpers in `cockpit.py`

**Files:**
- Modify: `cockpit.py` (append at end)
- Test: `tests/test_strength_cockpit.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_strength_cockpit.py`:

```python
import plotly.graph_objects as go  # noqa: F811 (safe if already imported)


def test_standards_panel_renders_levels_and_need_profile():
    ok = cockpit.strength_standards_panel({
        "status": "ok",
        "overall": {"level": "Intermediate", "percentile": 55.0},
        "lifts": [{"name": "Back Squat", "level": "Intermediate", "percentile": 50.0,
                   "est_1rm_kg": 125.0, "ratio": 1.25}],
    })
    assert "Back Squat" in ok and "Intermediate" in ok
    need = cockpit.strength_standards_panel({"status": "need_profile",
                                             "missing": ["bodyweight"]})
    assert isinstance(need, str) and "bodyweight" in need.lower()


def test_balance_panel_renders_ratio_and_flag():
    html = cockpit.strength_balance_panel({
        "ratios": [{"label": "Bench : Squat", "ratio": 0.4, "low": 0.5,
                    "ideal": 0.66, "high": 0.8, "status": "under",
                    "weak_side": "bench-press", "reason": "upper vs lower"}],
        "left_right": [{"name": "Split Squat", "left_1rm_kg": 40.0,
                        "right_1rm_kg": 50.0, "diff_pct": 20.0, "flagged": True,
                        "stronger_side": "right"}],
    })
    assert "Bench : Squat" in html and "Split Squat" in html


def test_correlation_panel_ok_and_insufficient():
    fig = cockpit.strength_correlation_panel({
        "status": "ok", "n": 12, "correlation": 0.4,
        "insight": "Better lifts on higher-readiness days.",
        "buckets": {"Low": {"n": 4, "avg_rel_perf": 0.9, "pr_rate": 0.0, "avg_tonnage": 3000},
                    "High": {"n": 8, "avg_rel_perf": 0.98, "pr_rate": 0.25, "avg_tonnage": 4000}},
    })
    assert isinstance(fig, go.Figure)
    msg = cockpit.strength_correlation_panel({"status": "insufficient", "have": 3, "need": 8})
    assert isinstance(msg, str) and "8" in msg
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_cockpit.py -k "standards_panel or balance_panel or correlation_panel" -v`
Expected: FAIL — `AttributeError: module 'cockpit' has no attribute 'strength_standards_panel'`

- [ ] **Step 3: Append to `cockpit.py`**

```python


# ── Strength Insights panels (Phase 2) ────────────────────────────────────────
def strength_standards_panel(standards: dict) -> str:
    """HTML for the standards panel. Accepts the compute_strength_standards dict."""
    standards = standards or {}
    status = standards.get("status")
    if status == "need_profile":
        miss = ", ".join(standards.get("missing", [])) or "profile data"
        return (f"<div style='color:{TEXT_DIM};font-family:Hanken Grotesk,sans-serif;"
                f"font-size:14px'>Set your {html.escape(miss)} to grade your lifts "
                f"against population standards.</div>")
    if status != "ok" or not standards.get("lifts"):
        return (f"<div style='color:{TEXT_DIM};font-family:Hanken Grotesk,sans-serif;"
                f"font-size:14px'>Log the main lifts (squat, bench, deadlift, OHP, row) "
                f"to see strength standards.</div>")
    ov = standards.get("overall") or {}
    rows = [
        f"<div style='background:{SURFACE};border-radius:12px;padding:14px 18px;"
        f"color:{TEXT};font-family:Hanken Grotesk,sans-serif;margin-bottom:10px'>"
        f"<span style='color:{TEXT_DIM};font-size:13px'>Overall</span> "
        f"<b style='color:{ACCENT};font-size:18px'>{_fmt(ov.get('level'))}</b> "
        f"<span style='color:{TEXT_DIM}'>(~{_fmt(ov.get('percentile'))} pct)</span>"
        f"<div style='color:{TEXT_FAINT};font-size:11px;margin-top:4px'>"
        f"approximate, bodyweight-relative</div></div>"
    ]
    for l in standards["lifts"]:
        pct = l.get("percentile") or 0
        rows.append(
            f"<div style='margin:6px 0;font-family:Hanken Grotesk,sans-serif;color:{TEXT}'>"
            f"<div style='display:flex;justify-content:space-between;font-size:14px'>"
            f"<span>{html.escape(str(l['name']))}</span>"
            f"<span style='color:{SERIES2}'>{_fmt(l['level'])} · {_fmt(l.get('est_1rm_kg'),' kg')}</span></div>"
            f"<div style='background:{SURFACE};border-radius:6px;height:8px;margin-top:4px'>"
            f"<div style='background:{ACCENT};height:8px;border-radius:6px;width:{min(100,max(2,pct)):.0f}%'></div>"
            f"</div></div>")
    return "".join(rows)


def strength_balance_panel(balance: dict) -> str:
    """HTML for the muscle-balance panel."""
    balance = balance or {}
    ratios = balance.get("ratios", [])
    lr = balance.get("left_right", [])
    if not ratios and not lr:
        return (f"<div style='color:{TEXT_DIM};font-family:Hanken Grotesk,sans-serif;"
                f"font-size:14px'>Log more of the main lifts (and unilateral lifts per "
                f"side) to see balance.</div>")
    chip = {"ok": SERIES2, "under": ACCENT, "over": AMBER}
    out = []
    for r in ratios:
        color = chip.get(r["status"], TEXT_DIM)
        note = "" if r["status"] == "ok" else f" — weak: {html.escape(str(r.get('weak_side') or ''))}"
        out.append(
            f"<div style='margin:6px 0;font-family:Hanken Grotesk,sans-serif;color:{TEXT};font-size:14px'>"
            f"<span>{html.escape(r['label'])}</span> "
            f"<b style='color:{color}'>{_fmt(r['ratio'])}</b> "
            f"<span style='color:{TEXT_DIM};font-size:12px'>(target {r['low']}–{r['high']})</span>"
            f"<span style='color:{color};font-size:12px'>{note}</span></div>")
    if lr:
        out.append(f"<div style='color:{TEXT_DIM};font-size:12px;margin-top:10px'>Left / right</div>")
        for e in lr:
            color = ACCENT if e.get("flagged") else SERIES2
            out.append(
                f"<div style='margin:4px 0;font-family:Hanken Grotesk,sans-serif;color:{TEXT};font-size:14px'>"
                f"{html.escape(str(e['name']))}: L {_fmt(e.get('left_1rm_kg'))} / R {_fmt(e.get('right_1rm_kg'))} "
                f"<b style='color:{color}'>Δ{_fmt(e.get('diff_pct'))}%</b>"
                f"{' ⚠' if e.get('flagged') else ''}</div>")
    return "".join(out)


def strength_correlation_panel(corr: dict):
    """Plotly bar (readiness bucket vs avg relative performance) when ok, else a
    string message."""
    corr = corr or {}
    if corr.get("status") != "ok":
        need = corr.get("need", 8)
        have = corr.get("have", 0)
        return (f"Log ~{max(0, int(need) - int(have))} more sessions to unlock the "
                f"readiness-vs-performance view (have {have}, need {need}).")
    buckets = corr.get("buckets", {})
    order = [b for b in ("Low", "Med", "High") if b in buckets]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=order, y=[buckets[b]["avg_rel_perf"] for b in order],
        marker_color=ACCENT,
        text=[f"n={buckets[b]['n']}" for b in order], textposition="outside",
    ))
    fig.update_layout(
        title=f"Readiness vs lifting (r={_fmt(corr.get('correlation'))})",
        paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=TEXT),
        yaxis=dict(title="avg rel. performance", range=[0, 1.1]),
        margin=dict(l=40, r=20, t=40, b=30), height=300, showlegend=False,
    )
    return fig
```

(Note: `_fmt`, and tokens `BG/SURFACE/TEXT/TEXT_DIM/TEXT_FAINT/ACCENT/SERIES2/AMBER` already exist in `cockpit.py` from earlier work; `html` and `go` are imported at the top.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_cockpit.py -v`
Expected: PASS (7 passed — 4 prior + 3 new).

- [ ] **Step 5: Commit**

```bash
git add cockpit.py tests/test_strength_cockpit.py
git commit -m "feat(strength): Insights render panels (standards, balance, correlation)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: "Insights" tab in `pages/01_Strength.py`

**Files:**
- Modify: `pages/01_Strength.py`

> Streamlit UI — verify by parse + AppTest (empty + data-backed).

- [ ] **Step 1: Read the file, then change the tabs line**

In `pages/01_Strength.py`, find:

```python
    tab_log, tab_history, tab_body = st.tabs(["Log workout", "History", "Bodyweight"])
```

Replace with:

```python
    tab_log, tab_history, tab_insights, tab_body = st.tabs(
        ["Log workout", "History", "Insights", "Bodyweight"])
```

- [ ] **Step 2: Insert the Insights tab block**

Immediately BEFORE the `with tab_body:` line, insert:

```python
with tab_insights:
    st.subheader("Insights")
    sessions = db.load_strength_sessions_df()
    sets = db.load_strength_sets_df()
    if sessions.empty:
        st.info("Log a few workouts (especially the main lifts) to unlock standards, balance, and readiness insights.")
    else:
        profile = db.load_profile()
        bodyweight = resolve_bodyweight(today_str())
        prs = analysis.compute_pr_timeline(sets, sessions, catalog, config.ONE_RM_FORMULA)
        best_map = (prs.groupby("exercise_id")["best_est_1rm_kg"].max().to_dict()
                    if not prs.empty else {})

        st.markdown("##### Strength standards")
        standards = analysis.compute_strength_standards(best_map, profile, bodyweight)
        st.markdown(cockpit.strength_standards_panel(standards), unsafe_allow_html=True)

        st.divider()
        st.markdown("##### Muscle balance")
        balance = analysis.compute_balance(best_map, sets, catalog)
        st.markdown(cockpit.strength_balance_panel(balance), unsafe_allow_html=True)

        st.divider()
        st.markdown("##### Readiness vs performance")
        corr = analysis.compute_readiness_performance(sessions, sets, catalog)
        panel = cockpit.strength_correlation_panel(corr)
        if isinstance(panel, str):
            st.caption(panel)
        else:
            st.plotly_chart(panel, use_container_width=True)
            if corr.get("insight"):
                st.caption(corr["insight"])
```

- [ ] **Step 3: Verify parse**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -c "import ast; ast.parse(open('pages/01_Strength.py').read()); print('parse ok')"` → `parse ok`

- [ ] **Step 4: AppTest smoke (empty + data-backed)**

Empty DB:
```bash
cd "/home/jhank/vscode/hanky sin garmin" && source .venv/bin/activate 2>/dev/null; python -c "
import os, tempfile
tmp=tempfile.NamedTemporaryFile(suffix='.db',delete=False); tmp.close()
os.environ['DB_PATH']=tmp.name
import importlib, config, db; importlib.reload(config); importlib.reload(db); db.config.DB_PATH=tmp.name; db.init_db()
from streamlit.testing.v1 import AppTest
at=AppTest.from_file('pages/01_Strength.py',default_timeout=30).run()
assert not at.exception, at.exception
print('insights empty ok')
"
```

Data-backed (a graded session so standards + balance render):
```bash
cd "/home/jhank/vscode/hanky sin garmin" && source .venv/bin/activate 2>/dev/null; python -c "
import os, tempfile
tmp=tempfile.NamedTemporaryFile(suffix='.db',delete=False); tmp.close()
os.environ['DB_PATH']=tmp.name
import importlib, config, db; importlib.reload(config); importlib.reload(db); db.config.DB_PATH=tmp.name; db.init_db()
db.upsert_profile({'sex':'male','birth_year':1995,'source':'manual'})
db.upsert_body_metric({'date':'2026-06-05','weight_kg':100.0,'source':'manual'})
db.upsert_strength_session({'session_id':'s1','date':'2026-06-05','name':'Day','bodyweight_kg':100.0,'readiness_score':70})
for i,(ex,w) in enumerate([('back-squat',150.0),('bench-press',100.0),('deadlift',180.0)]):
    db.upsert_strength_set({'set_id':f'x{i}','session_id':'s1','exercise_id':ex,'position':i,'set_index':1,'side':'both','reps':1,'weight_kg':w,'is_warmup':0,'completed':1})
from streamlit.testing.v1 import AppTest
at=AppTest.from_file('pages/01_Strength.py',default_timeout=30).run()
assert not at.exception, at.exception
print('insights data-backed ok')
"
```
Expected: both print `... ok`. If `streamlit.testing` is unavailable, rely on parse. A real `at.exception` is a failure — STOP and report BLOCKED with the text.

- [ ] **Step 5: Full suite + commit**

Run: `python -m pytest -q` → all pass.
```bash
git add pages/01_Strength.py
git commit -m "feat(strength): Insights tab (standards, balance, readiness link)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: Full regression + end-to-end

**Files:** none (verification only)

- [ ] **Step 1: Full test suite**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && source .venv/bin/activate 2>/dev/null; python -m pytest -q`
Expected: all pass (Phase 1 + Phase 2 tests).

- [ ] **Step 2: End-to-end AI-context check**

Confirm the strength summary flows into the AI payload builder without raw data:
```bash
cd "/home/jhank/vscode/hanky sin garmin" && source .venv/bin/activate 2>/dev/null; python -c "
import os, tempfile, json
tmp=tempfile.NamedTemporaryFile(suffix='.db',delete=False); tmp.close()
os.environ['DB_PATH']=tmp.name
import importlib, config, db, analysis, ai
importlib.reload(config); importlib.reload(db); db.config.DB_PATH=tmp.name; db.init_db()
db.upsert_profile({'sex':'male','birth_year':1995,'source':'manual'})
db.upsert_body_metric({'date':'2026-06-05','weight_kg':100.0,'source':'manual'})
db.upsert_strength_session({'session_id':'s1','date':'2026-06-05','name':'Day','bodyweight_kg':100.0,'readiness_score':70})
db.upsert_strength_set({'set_id':'x1','session_id':'s1','exercise_id':'back-squat','position':0,'set_index':1,'side':'both','reps':1,'weight_kg':150.0,'is_warmup':0,'completed':1})
summ = analysis.summarize_strength(db.load_strength_sessions_df(), db.load_strength_sets_df(), db.load_exercises_df(), db.load_profile(), 100.0)
payload = ai._question_payload('how strong am I?', {'a':1}, None,None,None,None,None, summ)
assert payload['strength_profile']['standards']['overall']['level'] in ('Novice','Intermediate','Advanced')
blob = json.dumps(payload)
assert 'set_id' not in blob and '\"reps\"' not in blob
print('E2E ok: strength in AI payload, no raw sets; overall =', summ['standards']['overall'])
"
```
Expected: `E2E ok: ...` with no assertion error.

- [ ] **Step 3: Commit any fixups (if needed)**

```bash
git add -A && git commit -m "test(strength): phase 2 regression pass

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>" || echo "nothing to commit"
```

---

## Done criteria (Phase 2)

- `pytest -q` green; no raw set/time-series data in the AI payload.
- `strength_standards.py` reference tables in place.
- `analysis.py`: `compute_strength_standards`, `compute_balance`, `compute_readiness_performance`, `summarize_strength` — pure, unit-tested.
- `ai.py` `answer_question`/`analyze` accept & use `strength`; prompt updated.
- `app.py` builds and passes the strength summary (visible in `question_payload`).
- `cockpit.py` three Insights panels; `pages/01_Strength.py` "Insights" tab renders (empty + data-backed AppTest green).
