# Strong-Style Strength UI Multi-Agent Workflow

## Workflow Metadata

- Workflow name: Strong-style strength logger UI
- Date: 2026-06-14
- Repository: Garmin Coach
- Branch or worktree: current local checkout, or a Codex-managed worktree
- Parent owner: main Codex session
- Status: draft

## Goal

Redesign the Strength page's active workout logging experience so it feels much
closer to the Strong workout app screenshot: dark mobile-first workout notebook,
compact exercise sections, previous/kg/reps columns, warmup rows, green completed
rows, check buttons, rest timer bars, top workout timer, and a clear Finish
action.

The result should be a usable Streamlit implementation, not a static mockup.
Users must still be able to start, edit, finish, discard, and save workouts with
the existing local SQLite persistence.

## Visual Target From User Reference

Aim for a high-fidelity Strong-inspired workout logger:

- Full black or near-black active workout surface.
- Top sticky workout bar with collapse/back affordance, rest/timer control,
  elapsed workout time, and blue `FINISH` action.
- Workout title and elapsed duration near the top.
- Exercise title in bright blue, with a compact overflow/actions area.
- Optional exercise note strip in muted yellow/brown.
- Column header row: `SET`, `PREVIOUS`, `KG`, `REPS`, completion check.
- Warmup rows marked `W` in orange.
- Completed rows use deep green background with white text and bright green
  check buttons.
- Pending rows use dark background, gray input pills, and subdued check buttons.
- Rest timer/progress strip appears between sets where useful.
- Mobile-first density: low vertical padding, stable columns, large enough touch
  targets, no card-within-card clutter.

Do not use Strong branding, logos, proprietary assets, or exact marketing copy.
The goal is a familiar workout-notebook interaction style inside Garmin Coach.

## Non-Goals

- Do not rebuild the whole app navigation.
- Do not rewrite strength analytics or standards.
- Do not send strength workout data to AI beyond existing compact summaries.
- Do not change Garmin sync behavior.
- Do not introduce a large frontend framework.
- Do not require a database migration unless a behavior cannot be implemented
  safely with existing fields/session state.

## Shared Context

All agents must read:

- `AGENTS.md`
- `docs/superpowers/specs/2026-06-14-strong-style-strength-ui-multi-agent-workflow.md`
- `pages/01_Strength.py`
- `cockpit.py`
- `analysis.py`, especially `last_session_sets` and strength summary helpers
- `db.py`, especially `strength_sessions` and `strength_sets`
- `tests/test_strength_db.py`
- `tests/test_strength_analysis.py`
- `tests/test_strength_cockpit.py`

Existing implementation notes:

- Active workout state lives in `st.session_state["active"]`.
- Saved sessions and sets are persisted only when the user presses
  `Finish & save`.
- `strength_sets.completed` already exists and should be used for completed
  row state.
- Warmup sets use `is_warmup`.
- Previous-set values are available through `analysis.last_session_sets(...)`.
- `cockpit.CSS` is injected into the page and should hold reusable styling.

## Execution Mode

- [x] Parent-only edits: subagents inspect/report only; parent edits files.
- [ ] Isolated worktrees: each implementation agent works in its own worktree.
- [ ] Review-only fanout: all subagents review the same diff from different angles.

Rationale:

This is mostly one Streamlit page plus shared CSS helpers. Multiple agents
editing the same file would create avoidable merge conflicts. Let subagents
inspect, design, test, and review; the parent owns final edits.

## Agent Roster

| Agent | Role | Can edit files? | Main output |
| --- | --- | --- | --- |
| Parent | Orchestrates workflow, implements final patch, runs verification | Yes | Final implementation, tests, summary |
| Visual UX Agent | Converts the screenshot into Streamlit/CSS requirements | No | UI checklist, layout rules, visual risks |
| Code Explorer Agent | Maps current strength code/state/tests | No | File map and safe implementation path |
| Interaction Agent | Reviews workout behavior: set editing, completion, rest timer, finish/discard | No | State-flow and edge-case checklist |
| Tester Agent | Defines focused and final verification | No | Test commands, manual checks, screenshot checks |
| Reviewer Agent | Reviews patch for regressions, UX issues, privacy, missing tests | No | Findings and blocking/non-blocking feedback |

## Parent Kickoff Prompt

Use this in the main Codex session when ready to implement:

```text
Read AGENTS.md and
docs/superpowers/specs/2026-06-14-strong-style-strength-ui-multi-agent-workflow.md.

Use the workflow in the spec.

Spawn subagents for:
1. Visual UX Agent: convert the user screenshot into concrete Streamlit/CSS
   requirements and acceptance criteria.
2. Code Explorer Agent: inspect pages/01_Strength.py, cockpit.py, analysis.py,
   db.py, and relevant tests; report the safest implementation path.
3. Interaction Agent: review active workout state and propose behavior for
   completed rows, warmups, previous sets, rest timer, finish, discard, and
   notes without unnecessary schema changes.
4. Tester Agent: propose focused tests, full verification, and manual/screenshot
   checks.
5. Reviewer Agent: after implementation, review for bugs, regressions, privacy
   issues, missing tests, and mobile UI problems.

Only the parent agent should edit files. Wait for subagent reports before
finalizing the implementation.
```

## Agent Instructions

### Visual UX Agent

```text
You are the Visual UX Agent.

Read the workflow spec and inspect the current Strength page. Do not edit files.

Translate the Strong-style screenshot into concrete implementation guidance for
Streamlit:
- layout hierarchy
- color palette
- typography and spacing
- row states
- mobile/desktop behavior
- components to avoid
- acceptance criteria

Do not request use of Strong branding, logos, or proprietary assets.
Return a concise UI checklist and risks.
```

### Code Explorer Agent

```text
You are the Code Explorer Agent.

Read AGENTS.md, pages/01_Strength.py, cockpit.py, analysis.py, db.py, and the
strength tests. Do not edit files.

Return:
- relevant functions and state objects
- existing patterns to preserve
- minimal files likely needing edits
- whether schema changes are needed
- tests likely affected
- implementation risks
```

### Interaction Agent

```text
You are the Interaction Agent.

Focus on workout logging behavior. Do not edit files.

Review:
- start workout
- add exercise
- add/remove set
- toggle warmup
- edit kg/reps/RPE/side
- toggle completed state
- previous-set display
- rest timer/progress display
- finish/save and discard
- save routine

Return edge cases and recommended behavior. Prefer using existing active state
and existing DB columns before adding schema.
```

### Tester Agent

```text
You are the Tester Agent.

Do not edit files unless the parent explicitly asks for a test patch.

Return:
- focused pytest commands
- full test command
- manual Streamlit checks
- screenshot checks for mobile and desktop
- likely failure modes in Streamlit widgets/session_state
```

### Reviewer Agent

```text
You are the Reviewer Agent.

Review the final patch like a code owner. Do not edit files.

Findings first, ordered by severity. Prioritize:
- broken workout save/edit behavior
- lost session_state data
- invalid Streamlit widget keys
- mobile layout overflow
- text overlap or illegible contrast
- accidental privacy/data boundary changes
- missing or weak tests

If no issues are found, say that clearly and list residual risk.
```

## Implementation Guidance

Likely files:

- `pages/01_Strength.py`
- `cockpit.py`
- `tests/test_strength_cockpit.py`
- Possibly `tests/test_strength_db.py` only if persistence behavior changes

Preferred approach:

- Keep persistence and analytics behavior stable.
- Move reusable Strong-style HTML/CSS helpers into `cockpit.py` when practical.
- Keep Streamlit widget state in `pages/01_Strength.py`.
- Use existing `completed`, `is_warmup`, `weight_kg`, `reps`, `rpe`, `side`, and
  previous-set data.
- Use a stable, compact row layout with fixed column proportions.
- Add a completed check toggle for each live set if it is not already exposed.
- Preserve current add/remove set behavior.
- If adding exercise notes, start with active-session-only notes unless
  persistence is explicitly required.

Avoid:

- Nesting cards inside cards.
- Huge dashboard-style metric blocks inside the active workout view.
- UI text that explains how to use every control.
- Viewport-scaled font sizes.
- Unstable widget keys based on list indices alone when stable IDs exist.
- Broad DB schema changes for purely visual work.

## Handoff Packet

Every subagent should return this structure:

```json
{
  "agent": "<visual_ux|code_explorer|interaction|tester|reviewer>",
  "status": "ready|blocked|needs_changes",
  "summary": "<short result>",
  "findings": [],
  "changed_files": [],
  "risks": [],
  "recommended_next_action": "<what the parent should do next>"
}
```

## Acceptance Criteria

- Active workout view resembles a Strong-style dark workout notebook.
- Header area includes workout title, elapsed time, and clear Finish action.
- Exercise sections show blue exercise names and compact controls.
- Set table includes `SET`, `PREVIOUS`, `KG`, `REPS`, and completion columns.
- Warmup rows are visually distinct with orange `W`.
- Completed rows are green and have a checked completion control.
- Pending rows are dark/gray and remain easy to edit.
- Previous set values appear where history exists.
- Add set, remove set, warmup toggle, completed toggle, kg/reps edits, and
  finish/save still work.
- Layout is usable at mobile width and desktop width without text overlap.
- History, Insights, and Bodyweight tabs still work.
- No raw Garmin time-series or private local files are sent to AI.

## Test Plan

Focused tests:

```bash
.venv/bin/python -m pytest tests/test_strength_cockpit.py
.venv/bin/python -m pytest tests/test_strength_analysis.py
.venv/bin/python -m pytest tests/test_strength_db.py
```

Full verification:

```bash
.venv/bin/python -m pytest
```

Compile check:

```bash
.venv/bin/python -m py_compile pages/01_Strength.py cockpit.py
```

Manual Streamlit checks:

- Start the app with `.venv/bin/streamlit run app.py --server.port <port>`.
- Open `Strength -> Log workout`.
- Start a blank workout.
- Add an exercise.
- Add warmup and working sets.
- Edit kg and reps.
- Toggle warmup and completed state.
- Remove a set.
- Finish and save the workout.
- Confirm it appears in History.
- Delete a saved workout and confirm its sets disappear.

Visual checks:

- Mobile-ish width around `390x844`.
- Desktop width around `1280x900`.
- No clipped button labels.
- No text overlap in set rows.
- Header and Finish action remain easy to find.
- Inputs do not resize rows unpredictably.

## Validation Gates

The workflow is not complete until:

- [ ] Focused strength tests pass.
- [ ] Full pytest suite passes, or a skipped reason is documented.
- [ ] Streamlit page imports without error.
- [ ] Manual active-workout flow succeeds.
- [ ] Mobile and desktop screenshots are inspected.
- [ ] Privacy boundary is unchanged.
- [ ] Final response lists changed files and verification.

## Failure Handling

If blocked:

- State the exact blocker.
- State what was attempted.
- State what input/tool access is needed.
- Do not guess on schema or persistence changes.

If visual verification fails:

- Identify the failing viewport.
- Identify the exact overlap/clipping/contrast problem.
- Fix CSS or layout constraints before calling the workflow complete.

## Final Report Template

```text
Implemented Strong-style Strength UI.

Changed:
- pages/01_Strength.py: <summary>
- cockpit.py: <summary>
- tests/...: <summary>

Verified:
- <focused test> -> <result>
- .venv/bin/python -m pytest -> <result>
- Streamlit manual check -> <result>

Notes:
- <remaining limitation or follow-up>
```
