# Strong-Style Set Rows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the live "Log workout" set-entry UI in `pages/01_Strength.py` with Strong-style editable rows (Set badge/warmup toggle · Previous · kg · Reps · remove), a "+ Add Set" button, a per-exercise RPE toggle, and L/R selectors for unilateral lifts.

**Architecture:** One new pure helper `analysis.last_session_sets` powers the greyed "Previous" column from history. The page rewrites only the per-exercise set block: each set renders as a row of widgets whose return values are assigned straight back into `st.session_state["active"]`, and the top metrics move into a placeholder filled after the rows so they stay live. Finish/persistence, the other tabs, and the add-exercise/custom-exercise controls are unchanged.

**Tech Stack:** Python, Streamlit, pandas, `pytest`, Streamlit `AppTest`.

**Spec:** `docs/superpowers/specs/2026-06-05-strong-style-set-rows-design.md`

> **Git:** normal repo on `master`. Branch first: `git checkout -b feat/strong-style-set-rows`. Commit per task.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `analysis.py` | `last_session_sets` (pure history lookup) | Modify |
| `pages/01_Strength.py` | Strong-style set rows + metrics placeholder | Modify |
| `tests/test_strength_analysis.py` | `last_session_sets` unit tests | Modify |

- [ ] **Task 0: Branch**

```bash
cd "/home/jhank/vscode/hanky sin garmin" && git checkout master && git checkout -b feat/strong-style-set-rows && git branch --show-current
```
Expected: `feat/strong-style-set-rows`

---

## Task 1: `analysis.last_session_sets` (pure)

**Files:**
- Modify: `analysis.py` (append to the strength section at end of file)
- Test: `tests/test_strength_analysis.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_strength_analysis.py`:

```python
def test_last_session_sets_picks_most_recent_and_orders():
    sessions = pd.DataFrame([
        {"session_id": "s1", "date": "2026-06-01", "started_at": "2026-06-01T10:00"},
        {"session_id": "s2", "date": "2026-06-03", "started_at": "2026-06-03T10:00"},
    ])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "bench-press", "set_index": 1,
         "weight_kg": 80.0, "reps": 8, "is_warmup": 0, "completed": 1},
        {"session_id": "s2", "exercise_id": "bench-press", "set_index": 2,
         "weight_kg": 100.0, "reps": 5, "is_warmup": 0, "completed": 1},
        {"session_id": "s2", "exercise_id": "bench-press", "set_index": 1,
         "weight_kg": 90.0, "reps": 5, "is_warmup": 0, "completed": 1},
        {"session_id": "s2", "exercise_id": "bench-press", "set_index": 0,
         "weight_kg": 40.0, "reps": 10, "is_warmup": 1, "completed": 1},  # warmup excluded
    ])
    out = analysis.last_session_sets("bench-press", sessions, sets)
    assert out == [{"weight_kg": 90.0, "reps": 5}, {"weight_kg": 100.0, "reps": 5}]


def test_last_session_sets_unlogged_and_empty():
    assert analysis.last_session_sets("squat", pd.DataFrame(), pd.DataFrame()) == []
    sessions = pd.DataFrame([{"session_id": "s1", "date": "2026-06-01"}])
    sets = pd.DataFrame([{"session_id": "s1", "exercise_id": "bench-press",
                          "set_index": 1, "weight_kg": 80.0, "reps": 8,
                          "is_warmup": 0, "completed": 1}])
    assert analysis.last_session_sets("deadlift", sessions, sets) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && source .venv/bin/activate 2>/dev/null; python -m pytest tests/test_strength_analysis.py -k last_session_sets -v`
Expected: FAIL — `AttributeError: module 'analysis' has no attribute 'last_session_sets'`

- [ ] **Step 3: Append to the strength section of `analysis.py`**

```python


def last_session_sets(exercise_id, sessions_df, sets_df):
    """Working sets (kg, reps) from the most recent saved session that included
    `exercise_id`, ordered by set_index, warmups excluded. Pure. [] if none.
    """
    if (sessions_df is None or sessions_df.empty
            or sets_df is None or sets_df.empty
            or "exercise_id" not in sets_df.columns):
        return []
    ex_sets = sets_df[sets_df["exercise_id"] == exercise_id]
    if ex_sets.empty:
        return []
    sdf = sessions_df[sessions_df["session_id"].isin(set(ex_sets["session_id"]))].copy()
    if sdf.empty:
        return []
    sort_cols = [c for c in ("date", "started_at") if c in sdf.columns]
    if sort_cols:
        sdf = sdf.sort_values(sort_cols)
    last_sid = sdf.iloc[-1]["session_id"]
    rows = ex_sets[ex_sets["session_id"] == last_sid].copy()
    if "is_warmup" in rows.columns:
        rows = rows[pd.to_numeric(rows["is_warmup"], errors="coerce").fillna(0).astype(int) == 0]
    if "completed" in rows.columns:
        rows = rows[pd.to_numeric(rows["completed"], errors="coerce").fillna(1).astype(int) == 1]
    if "set_index" in rows.columns:
        rows = rows.sort_values("set_index")
    out = []
    for _, r in rows.iterrows():
        try:
            out.append({"weight_kg": float(r["weight_kg"]), "reps": int(r["reps"])})
        except (TypeError, ValueError):
            continue
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -m pytest tests/test_strength_analysis.py -k last_session_sets -v`
Expected: PASS (2 passed). Full suite: `python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_strength_analysis.py
git commit -m "feat(strength): last_session_sets for the Previous column

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Strong-style set rows in `pages/01_Strength.py`

**Files:**
- Modify: `pages/01_Strength.py` (two edits in the active-workout block)

> Streamlit UI — verify by parse + AppTest.

- [ ] **Step 1: Move the metrics into a top placeholder**

Read `pages/01_Strength.py`. Find this block (the active-workout header + metrics):

```python
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
```

Replace it with:

```python
    st.subheader(f"🟢 {active['name']} — {active['date']}")
    metrics_ph = st.container()  # filled after the set rows so it reflects live edits
```

- [ ] **Step 2: Rewrite the per-exercise set block**

Find this block (the old per-exercise set logging):

```python
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
```

Replace it with:

```python
    # per-exercise Strong-style set rows
    hist_sessions = db.load_strength_sessions_df()
    hist_sets = db.load_strength_sets_df()
    DIM = "#8A6063"

    for ei, ex in enumerate(active["exercises"]):
        st.markdown(f"**:blue[{ex['name']}]**")
        uni = bool(ex["is_unilateral"])
        show_rpe = st.toggle("RPE", key=f"showrpe_{ei}")
        prev = analysis.last_session_sets(ex["exercise_id"], hist_sessions, hist_sets)

        widths = [0.9, 1.8, 1.3, 1.3]
        if show_rpe:
            widths.append(1.0)
        if uni:
            widths.append(1.2)
        widths.append(0.7)

        hdr = st.columns(widths)
        hdr[0].caption("Set")
        hdr[1].caption("Previous")
        hdr[2].caption("kg")
        hdr[3].caption("Reps")

        work_n = 0
        for si, stt in enumerate(ex["sets"]):
            row = st.columns(widths)
            if stt["is_warmup"]:
                badge = "W"
            else:
                work_n += 1
                badge = str(work_n)
            if row[0].button(badge, key=f"badge_{stt['set_id']}", help="Tap to toggle warmup"):
                stt["is_warmup"] = 0 if stt["is_warmup"] else 1
                st.rerun()
            if si < len(prev):
                p = prev[si]
                row[1].markdown(
                    f"<span style='color:{DIM}'>{p['weight_kg']:g} kg × {p['reps']}</span>",
                    unsafe_allow_html=True)
            else:
                row[1].markdown(f"<span style='color:{DIM}'>—</span>",
                                unsafe_allow_html=True)
            stt["weight_kg"] = row[2].number_input(
                "kg", min_value=0.0, step=1.0, value=float(stt["weight_kg"]),
                key=f"kg_{stt['set_id']}", label_visibility="collapsed")
            stt["reps"] = int(row[3].number_input(
                "reps", min_value=0, step=1, value=int(stt["reps"]),
                key=f"reps_{stt['set_id']}", label_visibility="collapsed"))
            ci = 4
            if show_rpe:
                rpe_val = row[ci].number_input(
                    "rpe", min_value=0.0, max_value=10.0, step=0.5,
                    value=float(stt.get("rpe") or 0.0),
                    key=f"rpe_{stt['set_id']}", label_visibility="collapsed")
                stt["rpe"] = rpe_val or None
                ci += 1
            if uni:
                stt["side"] = row[ci].selectbox(
                    "side", ["left", "right"],
                    index=(1 if stt.get("side") == "right" else 0),
                    key=f"side_{stt['set_id']}", label_visibility="collapsed")
                ci += 1
            if row[ci].button("—", key=f"del_{stt['set_id']}", help="Remove set"):
                ex["sets"].pop(si)
                for j, t in enumerate(ex["sets"]):
                    t["set_index"] = j + 1
                st.rerun()

        if st.button("➕ Add Set", key=f"addset_{ei}"):
            last = ex["sets"][-1] if ex["sets"] else None
            ex["sets"].append({
                "set_id": str(uuid.uuid4()),
                "set_index": len(ex["sets"]) + 1,
                "side": (last["side"] if last else ("left" if uni else "both")),
                "reps": (int(last["reps"]) if last else 5),
                "weight_kg": (float(last["weight_kg"]) if last else 20.0),
                "rpe": None, "is_warmup": 0, "completed": 1,
            })
            st.rerun()

    # live metrics (computed after the rows so they reflect edits) → top placeholder
    sessions_df, sets_df = active_to_frames(active)
    summary = analysis.summarize_sessions(sessions_df, sets_df, catalog,
                                          config.ONE_RM_FORMULA)
    s = summary.iloc[0] if not summary.empty else {}
    with metrics_ph:
        c1, c2, c3 = st.columns(3)
        c1.metric("Volume", f"{(s.get('total_volume_kg') or 0):,.0f} kg")
        c2.metric("Working sets", int(s.get("working_sets") or 0))
        top = s.get("top_est_1rm_kg")
        c3.metric("Top est-1RM", f"{top:,.0f} kg" if top else "—")
```

- [ ] **Step 3: Verify parse**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && python -c "import ast; ast.parse(open('pages/01_Strength.py').read()); print('parse ok')"` → `parse ok`

- [ ] **Step 4: AppTest smoke (data-backed active workout)**

```bash
cd "/home/jhank/vscode/hanky sin garmin" && source .venv/bin/activate 2>/dev/null; python -c "
import os, tempfile
tmp=tempfile.NamedTemporaryFile(suffix='.db',delete=False); tmp.close(); os.environ['DB_PATH']=tmp.name
import importlib, config, db; importlib.reload(config); importlib.reload(db); db.config.DB_PATH=tmp.name; db.init_db()
# a prior saved session so the Previous column populates
db.upsert_strength_session({'session_id':'old','date':'2026-06-01','name':'Prev','bodyweight_kg':100.0})
for i,(reps,w) in enumerate([(8,80.0),(5,90.0)]):
    db.upsert_strength_set({'set_id':f'o{i}','session_id':'old','exercise_id':'bench-press','position':0,'set_index':i+1,'side':'both','reps':reps,'weight_kg':w,'is_warmup':0,'completed':1})
from streamlit.testing.v1 import AppTest
at=AppTest.from_file('pages/01_Strength.py',default_timeout=30)
at.session_state['active']={'session_id':'s1','name':'Push','date':'2026-06-05',
  'started_at':'2026-06-05T10:00:00','bodyweight_kg':100.0,'routine_id':None,
  'exercises':[
    {'position':0,'exercise_id':'bench-press','name':'Bench Press','is_unilateral':0,'is_bodyweight':0,
     'sets':[
       {'set_id':'w0','set_index':1,'side':'both','reps':10,'weight_kg':40.0,'rpe':None,'is_warmup':1,'completed':1},
       {'set_id':'a1','set_index':2,'side':'both','reps':5,'weight_kg':100.0,'rpe':8.0,'is_warmup':0,'completed':1},
     ]},
    {'position':1,'exercise_id':'bulgarian-split-squat','name':'Bulgarian Split Squat','is_unilateral':1,'is_bodyweight':0,
     'sets':[{'set_id':'b1','set_index':1,'side':'left','reps':8,'weight_kg':20.0,'rpe':None,'is_warmup':0,'completed':1}]},
  ]}
at.run()
assert not at.exception, at.exception
print('set-rows render ok')
# toggle RPE on for the first exercise and re-run
ts=[t for t in at.toggle if t.key=='showrpe_0']
if ts:
    ts[0].set_value(True); at.run(); assert not at.exception, at.exception
    print('rpe toggle ok')
" 2>&1 | grep -v "ScriptRunContext\|use_container_width\|will be removed\|width=\|^$"
```
Expected: `set-rows render ok` (and `rpe toggle ok`), no exception. If `streamlit.testing` is unavailable, rely on the parse check. A real `at.exception` is a failure — STOP and report BLOCKED with the text.

- [ ] **Step 5: Full suite + commit**

Run: `python -m pytest -q` → all pass.
```bash
git add pages/01_Strength.py
git commit -m "feat(strength): Strong-style editable set rows in the logger

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Regression + manual check

**Files:** none (verification only)

- [ ] **Step 1: Full suite**

Run: `cd "/home/jhank/vscode/hanky sin garmin" && source .venv/bin/activate 2>/dev/null; python -m pytest -q`
Expected: all pass.

- [ ] **Step 2: Manual browser walk-through (user)**

Run: `streamlit run app.py` → Strength → Log: Start a workout, add an exercise. Confirm:
1. Each set is its own row: Set badge · Previous · kg · Reps · — remove.
2. Editing kg/Reps updates the top Volume / Working-sets / Top-1RM metrics.
3. Tapping the Set badge toggles warmup (shows "W"; warmup excluded from volume).
4. "+ Add Set" appends a row copying the last set's kg/reps.
5. The "RPE" toggle reveals an RPE cell; unilateral lifts show an L/R selector.
6. "Previous" shows last session's kg × reps once you've logged that exercise before.
7. Finish & save still persists correctly; History/Insights/Bodyweight unchanged.

- [ ] **Step 3: Commit any fixups (if needed)**

```bash
git add -A && git commit -m "test(strength): set-rows regression pass

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>" || echo "nothing to commit"
```

---

## Done criteria

- `analysis.last_session_sets` implemented + unit-tested (pure).
- The logger's per-exercise block renders Strong-style editable rows with live metrics, warmup toggle, + Add Set, RPE toggle, L/R selector, and a Previous column.
- Finish/persistence, metrics correctness, and the other tabs unchanged.
- `pytest` green; set-rows AppTest smoke green.
