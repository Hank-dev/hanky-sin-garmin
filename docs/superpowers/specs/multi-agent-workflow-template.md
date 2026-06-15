# Multi-Agent Workflow Template

Copy this file to a dated spec, for example:

`docs/superpowers/specs/YYYY-MM-DD-feature-name-multi-agent-workflow.md`

Use this as the contract for a parent Codex session that explicitly spawns
specialized subagents. The default pattern is: subagents inspect and report;
the parent agent owns final edits.

## Workflow Metadata

- Workflow name: `<name>`
- Date: `<YYYY-MM-DD>`
- Repository: `<repo/project>`
- Branch or worktree: `<branch/worktree>`
- Parent owner: `<person/session>`
- Status: `draft | active | complete | blocked`

## Goal

Describe the outcome in one or two concrete sentences.

Example:

> Add a coach-memory workflow that records user notes and injuries with metadata,
> sends compact context to the AI coach, and verifies the privacy boundary.

## Non-Goals

- `<thing this workflow must not do>`
- `<thing that belongs in a future workflow>`
- `<risky/ambiguous area to avoid>`

## Shared Context

All agents must read:

- `AGENTS.md`
- `<feature spec or plan>`
- `<important source files>`
- `<relevant tests>`

Project constraints:

- Preserve local data privacy boundaries.
- Do not send raw Garmin time-series data to AI.
- Do not overwrite unrelated user changes.
- Keep changes scoped to the requested behavior.
- Run focused tests first; run the full suite when shared behavior changes.

## Execution Mode

Choose one:

- [ ] Parent-only edits: subagents inspect/report only; parent edits files.
- [ ] Isolated worktrees: each implementation agent works in its own worktree.
- [ ] Review-only fanout: all subagents review the same diff from different angles.

Default recommendation:

> Use parent-only edits unless multiple agents need to implement separate,
> independent branches of work. This avoids merge conflicts and duplicated edits.

## Agent Roster

| Agent | Role | Can edit files? | Main output |
| --- | --- | --- | --- |
| Parent | Orchestrates workflow, owns final implementation and response | Yes | Final patch, verification, summary |
| Planner | Turns the request into steps, risks, and acceptance criteria | No | Plan and task breakdown |
| Explorer | Reads code/docs/tests and maps affected areas | No | File map and implementation notes |
| Tester | Defines and runs verification strategy | Usually no | Test commands and results |
| Reviewer | Reviews for bugs, regressions, missing tests, and privacy issues | No | Findings with severity and file refs |

Optional implementation agents:

| Agent | Role | Can edit files? | Main output |
| --- | --- | --- | --- |
| Worker A | Implements isolated subtask A | Only in assigned worktree | Patch summary |
| Worker B | Implements isolated subtask B | Only in assigned worktree | Patch summary |

## Parent Kickoff Prompt

Use this prompt in the main Codex session:

```text
Read AGENTS.md and docs/superpowers/specs/<this-file>.md.

Use the workflow in the spec.

Spawn subagents for:
1. Planner: produce a task plan, risks, acceptance criteria, and likely files.
2. Explorer: inspect the codebase and report affected modules/tests.
3. Tester: propose focused and final verification commands.
4. Reviewer: review the planned/implemented change for regressions, privacy
   issues, and missing tests.

Only the parent agent should edit files unless this spec explicitly assigns
separate worktrees. Wait for all subagent reports before finalizing the work.
```

## Agent Instructions

### Planner Agent

```text
You are the planner agent for this workflow.

Read the workflow spec and relevant repo guidance. Do not edit files.

Return:
- summary of the user goal
- assumptions
- step-by-step task plan
- affected files/modules
- risks
- acceptance criteria
- tests that should pass
```

### Explorer Agent

```text
You are the explorer agent for this workflow.

Read the workflow spec, repo guidance, and likely source/test files. Do not edit
files.

Return:
- relevant files and what each does
- existing patterns to follow
- edge cases
- current tests that cover the area
- missing coverage
```

### Tester Agent

```text
You are the tester agent for this workflow.

Read the workflow spec and changed/likely files. Do not edit files unless the
parent explicitly asks for a test patch.

Return:
- focused test commands
- full verification command, if needed
- expected failure modes
- any setup required
- final pass/fail interpretation
```

### Reviewer Agent

```text
You are the reviewer agent for this workflow.

Review like a code owner. Do not edit files.

Prioritize:
- correctness bugs
- behavior regressions
- data/privacy boundary problems
- missing tests
- UX issues that block the intended workflow

Return findings first, ordered by severity. Include file and line references
when possible. If no issues are found, say that clearly and list residual risk.
```

## Handoff Packet

Every subagent should return this structure:

```json
{
  "agent": "<planner|explorer|tester|reviewer|worker>",
  "status": "ready|blocked|needs_changes",
  "summary": "<short result>",
  "findings": [],
  "changed_files": [],
  "risks": [],
  "recommended_next_action": "<what the parent should do next>"
}
```

## File Ownership Rules

- Parent agent owns final edits in the main checkout.
- Subagents are read-only unless explicitly assigned a worktree.
- If two agents propose conflicting changes, parent chooses one approach and
  records why.
- Never revert unrelated user changes.
- Never run destructive git commands unless explicitly requested.

## Validation Gates

The workflow is not complete until:

- [ ] Acceptance criteria are met.
- [ ] Focused tests pass.
- [ ] Full test suite passes, or skipped reason is documented.
- [ ] Privacy/data boundary is unchanged or improved.
- [ ] UI changes are reachable in the app.
- [ ] Schema changes include migration/backward compatibility.
- [ ] Final response lists changed files and verification.

## Acceptance Criteria

- `<criterion 1>`
- `<criterion 2>`
- `<criterion 3>`

## Test Plan

Focused tests:

```bash
<focused test command>
```

Full verification:

```bash
<full test command>
```

Manual verification:

- `<open page or feature>`
- `<perform action>`
- `<expected result>`

## Failure Handling

If blocked, the parent response must include:

- exact blocker
- what was attempted
- why guessing would be risky
- what user input or external change is needed

If tests fail:

- record failing command
- record relevant failure output
- fix the issue or explain why it is unrelated
- rerun the focused test after the fix

## Final Report Template

```text
Implemented <feature/change>.

Changed:
- <file>: <what changed>
- <file>: <what changed>

Verified:
- <command> -> <result>
- <manual check> -> <result>

Notes:
- <known limitation or follow-up, if any>
```

## Optional Custom Agent TOML

Use these only if you want reusable Codex agent roles.

Create files under `.codex/agents/`.

### `.codex/agents/planner.toml`

```toml
name = "planner"
description = "Plans feature work, risks, acceptance criteria, and verification."
developer_instructions = """
You are a planning-only agent.
Do not edit files.
Read repo guidance and relevant docs, then return a concrete implementation
plan, risks, acceptance criteria, and test strategy.
"""
sandbox_mode = "read-only"
```

### `.codex/agents/reviewer.toml`

```toml
name = "reviewer"
description = "Reviews changes for correctness, regressions, privacy issues, and missing tests."
developer_instructions = """
You are a review-only agent.
Do not edit files.
Prioritize correctness bugs, behavior regressions, privacy boundary violations,
and missing tests. Return findings first with file/line references when possible.
"""
sandbox_mode = "read-only"
```

### `.codex/agents/tester.toml`

```toml
name = "tester"
description = "Chooses and runs verification for a scoped code change."
developer_instructions = """
You are a testing-focused agent.
Prefer focused tests first, then broader verification when shared behavior
changes. Report commands, results, failures, and likely causes.
"""
```

