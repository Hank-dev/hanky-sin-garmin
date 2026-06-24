# Persistent Coach Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the AI a durable, user-curated memory of the athlete (goals, injuries, observed patterns, coaching log) that it reads before every answer and that grows through manual entry plus AI-suggested entries the user approves.

**Architecture:** A new `coach_memory` SQLite table with id-keyed CRUD in `db.py`. A pure `analysis.build_coach_memory_digest()` shapes active memories into a compact dict that is injected into the three `ai.py` calls (`analyze`, `weekly_summary`, `answer_question`). A new `ai.suggest_memories()` proposes structured candidates (parsed by a pure helper) that the user approves on a new `pages/02_Coach.py` page; a `cockpit.coach_memory_peek()` card surfaces memory on the main dashboard.

**Tech Stack:** Python, SQLite (stdlib `sqlite3`), pandas, Streamlit, Anthropic SDK, pytest.

**Spec:** [docs/superpowers/specs/2026-06-14-coach-memory-design.md](../specs/2026-06-14-coach-memory-design.md)

---

## File Structure

- **`db.py`** (modify) — add the `coach_memory` table to `SCHEMA`, a `COACH_MEMORY_COLS` list, and CRUD helpers: `add_memory`, `update_memory`, `archive_memory`, `delete_memory`, `load_memory_df`.
- **`analysis.py`** (modify) — add the pure `build_coach_memory_digest(memory_df)`.
- **`ai.py`** (modify) — add `_memory_block()`, `_parse_memory_candidates()`, `suggest_memories()`, `SUGGEST_SYSTEM`; add a `coach_memory` argument to `analyze`/`weekly_summary`/`answer_question` and the memory paragraph to the three system prompts.
- **`cockpit.py`** (modify) — add `coach_memory_peek(digest)` renderer.
- **`app.py`** (modify) — load memory, build digest, inject into AI calls, render the peek + a quick-add box.
- **`pages/02_Coach.py`** (create) — the Coach page (view/curate memories, quick-add, suggestion approval).
- **`tests/test_coach_memory.py`** (create) — db CRUD, digest, ai helper, and renderer tests.

---

## Task 1: `coach_memory` table + CRUD in db.py

**Files:**
- Modify: `db.py` (SCHEMA block, `COACH_MEMORY_COLS`, new functions)
- Test: `tests/test_coach_memory.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_coach_memory.py`:

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


def test_memory_add_load_roundtrip():
    _fresh_db()
    mid = db.add_memory({"category": "goal", "text": "BJJ comp in August",
                         "source": "user", "target_date": "2026-08-15"})
    assert isinstance(mid, int) and mid > 0
    df = db.load_memory_df()
    assert len(df) == 1
    row = df.iloc[0]
    assert row["category"] == "goal"
    assert row["text"] == "BJJ comp in August"
    assert row["status"] == "active"
    assert row["source"] == "user"
    assert row["target_date"] == "2026-08-15"
    assert row["created_at"] and row["updated_at"]


def test_memory_update_bumps_updated_at():
    _fresh_db()
    mid = db.add_memory({"category": "note", "text": "old", "source": "user"})
    before = db.load_memory_df().iloc[0]["updated_at"]
    db.update_memory(mid, {"text": "new"})
    row = db.load_memory_df().iloc[0]
    assert row["text"] == "new"
    assert row["updated_at"] >= before


def test_memory_archive_hides_from_active_load():
    _fresh_db()
    mid = db.add_memory({"category": "injury", "text": "left knee",
                         "source": "user", "body_part": "knee"})
    db.archive_memory(mid)
    assert len(db.load_memory_df()) == 0                 # default: active only
    assert len(db.load_memory_df(status=None)) == 1      # all
    assert db.load_memory_df(status="archived").iloc[0]["body_part"] == "knee"


def test_memory_delete_removes_row():
    _fresh_db()
    mid = db.add_memory({"category": "note", "text": "x", "source": "user"})
    db.delete_memory(mid)
    assert len(db.load_memory_df(status=None)) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_coach_memory.py -v`
Expected: FAIL with `AttributeError: module 'db' has no attribute 'add_memory'`.

- [ ] **Step 3: Add the table to `SCHEMA`**

In `db.py`, inside the `SCHEMA = """ ... """` string, add this table (after the `weekly_summaries` table is fine):

```sql
CREATE TABLE IF NOT EXISTS coach_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    source TEXT NOT NULL,
    confidence TEXT,
    target_date TEXT,
    body_part TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

- [ ] **Step 4: Add `COACH_MEMORY_COLS` and the CRUD functions**

In `db.py`, add the column list next to the other `*_COLS` definitions:

```python
COACH_MEMORY_COLS = [
    "id", "category", "text", "status", "source",
    "confidence", "target_date", "body_part", "created_at", "updated_at",
]
```

Then add these functions (near the other loaders/upserts):

```python
def add_memory(record: dict) -> int:
    """Insert one coach memory. Returns the new row id. `category` and `text`
    are required; `status` defaults to 'active', `source` to 'user'."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fields = {
        "category": record["category"],
        "text": record["text"],
        "status": record.get("status", "active"),
        "source": record.get("source", "user"),
        "confidence": record.get("confidence"),
        "target_date": record.get("target_date"),
        "body_part": record.get("body_part"),
        "created_at": now,
        "updated_at": now,
    }
    cols = list(fields)
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO coach_memory ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})",
            [fields[c] for c in cols],
        )
        return int(cur.lastrowid)


def update_memory(memory_id: int, fields: dict):
    """Update editable fields of one memory and bump updated_at."""
    allowed = ("category", "text", "status", "confidence",
               "target_date", "body_part")
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    sets["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    assignments = ", ".join(f"{k}=?" for k in sets)
    with connect() as conn:
        conn.execute(f"UPDATE coach_memory SET {assignments} WHERE id=?",
                     [*sets.values(), memory_id])


def archive_memory(memory_id: int):
    update_memory(memory_id, {"status": "archived"})


def delete_memory(memory_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM coach_memory WHERE id=?", (memory_id,))


def load_memory_df(status: str | None = "active"):
    """Load coach memories. status=None loads all; otherwise filters by status."""
    import pandas as pd
    with connect() as conn:
        if status is None:
            df = pd.read_sql_query(
                "SELECT * FROM coach_memory ORDER BY created_at", conn)
        else:
            df = pd.read_sql_query(
                "SELECT * FROM coach_memory WHERE status=? ORDER BY created_at",
                conn, params=(status,))
    return df
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_coach_memory.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add db.py tests/test_coach_memory.py
git commit -m "feat(coach-memory): coach_memory table + CRUD in db.py"
```

---

## Task 2: `analysis.build_coach_memory_digest` (pure)

**Files:**
- Modify: `analysis.py` (new pure function)
- Test: `tests/test_coach_memory.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_coach_memory.py`:

```python
import pandas as pd
import analysis


def _mem_df(rows):
    cols = ["id", "category", "text", "status", "source", "confidence",
            "target_date", "body_part", "created_at", "updated_at"]
    return pd.DataFrame([{c: r.get(c) for c in cols} for r in rows])


def test_digest_empty_returns_empty_dict():
    assert analysis.build_coach_memory_digest(pd.DataFrame()) == {}
    df = _mem_df([{"category": "note", "text": "x", "status": "archived"}])
    assert analysis.build_coach_memory_digest(df) == {}


def test_digest_groups_and_shapes_active_only():
    df = _mem_df([
        {"category": "goal", "text": "comp", "status": "active",
         "target_date": "2026-08-15"},
        {"category": "injury", "text": "knee", "status": "active",
         "body_part": "knee"},
        {"category": "pattern", "text": "late coffee → low HRV",
         "status": "active", "confidence": "high"},
        {"category": "note", "text": "ignored", "status": "archived"},
    ])
    d = analysis.build_coach_memory_digest(df)
    assert d["goals"] == [{"text": "comp", "target_date": "2026-08-15"}]
    assert d["injuries"] == [{"text": "knee", "body_part": "knee"}]
    assert d["patterns"] == [{"text": "late coffee → low HRV",
                              "confidence": "high"}]
    assert "notes" not in d            # the only note was archived


def test_digest_coaching_recent_first_and_capped():
    rows = [{"category": "coaching", "text": f"advice {i}", "status": "active",
             "created_at": f"2026-06-0{i}T00:00:00"} for i in range(1, 8)]
    d = analysis.build_coach_memory_digest(_mem_df(rows), coaching_cap=3)
    assert [c["text"] for c in d["coaching"]] == ["advice 7", "advice 6", "advice 5"]
    assert d["coaching"][0]["date"] == "2026-06-07"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_coach_memory.py -k digest -v`
Expected: FAIL with `AttributeError: module 'analysis' has no attribute 'build_coach_memory_digest'`.

- [ ] **Step 3: Implement the function**

Add to `analysis.py` (it already imports `pandas as pd` at module top):

```python
def build_coach_memory_digest(memory_df, per_category_cap: int = 8,
                              coaching_cap: int = 5) -> dict:
    """Shape active coach memories into a compact dict for the AI.

    Pure: takes the memory DataFrame, returns a category-grouped dict. Only
    'active' rows are included, empty categories are omitted, and each category
    is capped to bound the AI token budget. Returns {} when nothing is active.
    """
    if memory_df is None or len(memory_df) == 0:
        return {}
    df = memory_df
    if "status" in df.columns:
        df = df[df["status"] == "active"]
    if len(df) == 0:
        return {}

    def _clean(v):
        return None if v is None or (isinstance(v, float) and pd.isna(v)) else v

    def _rows(cat):
        return df[df["category"] == cat]

    out: dict = {}

    goals = _rows("goal").head(per_category_cap)
    if len(goals):
        out["goals"] = [{"text": str(r["text"]),
                         "target_date": _clean(r.get("target_date"))}
                        for _, r in goals.iterrows()]

    injuries = _rows("injury").head(per_category_cap)
    if len(injuries):
        out["injuries"] = [{"text": str(r["text"]),
                            "body_part": _clean(r.get("body_part"))}
                           for _, r in injuries.iterrows()]

    patterns = _rows("pattern").head(per_category_cap)
    if len(patterns):
        out["patterns"] = [{"text": str(r["text"]),
                            "confidence": _clean(r.get("confidence"))}
                           for _, r in patterns.iterrows()]

    coaching = _rows("coaching")
    if len(coaching):
        coaching = coaching.sort_values("created_at", ascending=False).head(coaching_cap)
        out["coaching"] = [{"text": str(r["text"]),
                            "date": str(r["created_at"])[:10]}
                           for _, r in coaching.iterrows()]

    notes = _rows("note").head(per_category_cap)
    if len(notes):
        out["notes"] = [str(r["text"]) for _, r in notes.iterrows()]

    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_coach_memory.py -k digest -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add analysis.py tests/test_coach_memory.py
git commit -m "feat(coach-memory): build_coach_memory_digest pure shaper"
```

---

## Task 3: Inject memory into the AI calls (ai.py)

**Files:**
- Modify: `ai.py` (`_memory_block`, three call signatures, three system prompts)
- Test: `tests/test_coach_memory.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_coach_memory.py`:

```python
import ai


def test_memory_block_empty_is_blank():
    assert ai._memory_block(None) == ""
    assert ai._memory_block({}) == ""


def test_memory_block_includes_json():
    block = ai._memory_block({"goals": [{"text": "comp", "target_date": None}]})
    assert "Coach memory" in block
    assert "comp" in block


def test_question_payload_includes_coach_memory():
    payload = ai._question_payload(
        "q", {"a": 1}, None, None, None, None, None,
        strength=None, health_research=None,
        coach_memory={"goals": [{"text": "comp"}]})
    assert payload["coach_memory"] == {"goals": [{"text": "comp"}]}


def test_question_payload_defaults_coach_memory_empty():
    payload = ai._question_payload("q", {}, None, None, None, None, None)
    assert payload["coach_memory"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_coach_memory.py -k "memory_block or coach_memory" -v`
Expected: FAIL with `AttributeError: module 'ai' has no attribute '_memory_block'`.

- [ ] **Step 3: Add `_memory_block` and thread `coach_memory` through**

In `ai.py`, add the helper near the top (after the prompt constants):

```python
def _memory_block(coach_memory: dict | None) -> str:
    if not coach_memory:
        return ""
    return ("\n\nCoach memory (durable, user-approved facts about this athlete):\n\n"
            + json.dumps(coach_memory, indent=2))
```

Update `analyze` to accept and inject it:

```python
def analyze(summary: dict, strength: dict | None = None,
            coach_memory: dict | None = None, model: str | None = None) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable AI analysis._"
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=1200,
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": "Here is my recent Garmin summary as JSON:\n\n"
                       + json.dumps(summary, indent=2)
                       + "\n\nStrength-training profile:\n\n"
                       + json.dumps(strength or {}, indent=2)
                       + _memory_block(coach_memory)
                       + "\n\nAnalyse it.",
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")
```

Update `weekly_summary` similarly:

```python
def weekly_summary(week_payload: dict, coach_memory: dict | None = None,
                   model: str | None = None) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable the weekly summary._"
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=900,
        system=WEEKLY_SYSTEM,
        messages=[{
            "role": "user",
            "content": "Here is my completed-week summary as JSON:\n\n"
                       + json.dumps(week_payload, indent=2)
                       + _memory_block(coach_memory)
                       + "\n\nWrite the recap.",
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")
```

Add `coach_memory` to `_question_payload` (new keyword arg + key):

```python
def _question_payload(question, summary, capacity, stress_leak_map,
                      grappling_sessions, prebed_discovery, chat_history,
                      strength=None, health_research=None, coach_memory=None):
    return {
        "question": question,
        "metrics_summary": summary,
        "capacity_envelope": capacity or {},
        "stress_leak_map": stress_leak_map or {},
        "grappling_sessions": grappling_sessions or [],
        "prebed_discovery": prebed_discovery or {},
        "health_research": health_research or {},
        "strength_profile": strength or {},
        "coach_memory": coach_memory or {},
        "previous_chat": chat_history or [],
    }
```

Add the `coach_memory` keyword to `answer_question` and pass it into `_question_payload`:

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
    health_research: dict | None = None,
    coach_memory: dict | None = None,
    model: str | None = None,
) -> str:
    if not config.ANTHROPIC_API_KEY:
        return "_Set ANTHROPIC_API_KEY in .env to enable AI questions._"
    question = (question or "").strip()
    if not question:
        return "_Ask a question first._"
    payload = _question_payload(question, summary, capacity, stress_leak_map,
                                grappling_sessions, prebed_discovery, chat_history,
                                strength, health_research, coach_memory)
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=1000,
        system=QUESTION_SYSTEM,
        messages=[{
            "role": "user",
            "content": "Answer my question using this compact local health context:\n\n"
                       + json.dumps(payload, indent=2)
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text")
```

- [ ] **Step 4: Add the memory paragraph to the three system prompts**

Append this sentence to the end of `SYSTEM`, `WEEKLY_SYSTEM`, and `QUESTION_SYSTEM` (inside each triple-quoted string):

```
You may also receive coach_memory — durable, user-approved facts about this
athlete (goals, injuries, observed patterns, prior coaching). When present,
honor injuries when advising load, orient advice toward the athlete's goals,
build on prior coaching, and reference these facts naturally so the athlete
feels known. They are curated facts, not raw data.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_coach_memory.py tests/test_ai_payload.py -v`
Expected: PASS (new memory tests + the existing `test_ai_payload.py` tests still green — `_question_payload`'s new arg is keyword/defaulted, so old calls are unaffected).

- [ ] **Step 6: Commit**

```bash
git add ai.py tests/test_coach_memory.py
git commit -m "feat(coach-memory): inject memory digest into the AI calls"
```

---

## Task 4: `ai.suggest_memories` + candidate parser

**Files:**
- Modify: `ai.py` (`SUGGEST_SYSTEM`, `_parse_memory_candidates`, `suggest_memories`)
- Test: `tests/test_coach_memory.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_coach_memory.py`:

```python
def test_parse_candidates_clean_array():
    text = '[{"category":"goal","text":"deadlift 200kg","target_date":"2026-12-01"}]'
    out = ai._parse_memory_candidates(text)
    assert out == [{"category": "goal", "text": "deadlift 200kg",
                    "target_date": "2026-12-01"}]


def test_parse_candidates_strips_code_fence_and_prose():
    text = ('Here you go:\n```json\n'
            '[{"category":"pattern","text":"late coffee lowers HRV",'
            '"confidence":"high"}]\n```\nhope that helps')
    out = ai._parse_memory_candidates(text)
    assert out == [{"category": "pattern", "text": "late coffee lowers HRV",
                    "confidence": "high"}]


def test_parse_candidates_drops_bad_items():
    text = ('[{"category":"goal","text":"keep"},'
            '{"category":"unknown","text":"bad category"},'
            '{"category":"note","text":""},'
            '"not an object"]')
    out = ai._parse_memory_candidates(text)
    assert out == [{"category": "goal", "text": "keep"}]


def test_parse_candidates_malformed_returns_empty():
    assert ai._parse_memory_candidates("not json at all") == []
    assert ai._parse_memory_candidates("") == []


def test_suggest_memories_without_key_returns_empty(monkeypatch):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "")
    assert ai.suggest_memories({"a": 1}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_coach_memory.py -k "candidates or suggest" -v`
Expected: FAIL with `AttributeError: module 'ai' has no attribute '_parse_memory_candidates'`.

- [ ] **Step 3: Implement the parser, prompt, and call**

At the top of `ai.py`, add `import re` next to the existing imports.

Add the allowed-category constant and parser:

```python
_MEMORY_CATEGORIES = ("goal", "injury", "pattern", "coaching", "note")


def _parse_memory_candidates(text: str) -> list[dict]:
    """Extract a JSON array of memory candidates from a model response.

    Tolerates ```json fences and surrounding prose. Drops items that aren't
    objects, lack a non-empty 'text', or carry an unknown 'category'. Keeps
    only known fields. Returns [] on any failure.
    """
    if not text:
        return []
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    if not raw.startswith("["):
        span = re.search(r"\[.*\]", raw, re.DOTALL)
        raw = span.group(0) if span else raw
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cat = str(it.get("category", "")).strip().lower()
        txt = str(it.get("text", "")).strip()
        if cat not in _MEMORY_CATEGORIES or not txt:
            continue
        cand = {"category": cat, "text": txt}
        for opt in ("confidence", "target_date", "body_part", "rationale"):
            v = it.get(opt)
            if v not in (None, ""):
                cand[opt] = str(v).strip()
        out.append(cand)
    return out
```

Add the suggestion prompt next to the other prompt constants:

```python
SUGGEST_SYSTEM = """You help maintain a coach's long-term memory of one athlete.
Given a compact metrics summary, the athlete's strength profile, and the memories
the coach ALREADY has, propose between 0 and 5 NEW durable facts worth remembering
for weeks or months. Never duplicate an existing memory. Never record transient
day-to-day noise (a single night's HRV, today's readiness). Only propose what a
good coach would want to remember long-term: stable patterns, goals, injuries, or
constraints implied by the data. If nothing durable stands out, return [].

Respond with ONLY a JSON array (no prose). Each item:
{"category": "goal|injury|pattern|coaching|note",
 "text": "<short fact>",
 "confidence": "low|med|high",   // optional
 "target_date": "YYYY-MM-DD",    // optional, goals
 "body_part": "<area>",          // optional, injuries
 "rationale": "<one short clause on why>"}"""
```

Add the call:

```python
def suggest_memories(summary: dict, strength: dict | None = None,
                     existing_memories: dict | None = None,
                     model: str | None = None) -> list[dict]:
    if not config.ANTHROPIC_API_KEY:
        return []
    payload = {
        "metrics_summary": summary or {},
        "strength_profile": strength or {},
        "existing_memories": existing_memories or {},
    }
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=700,
        system=SUGGEST_SYSTEM,
        messages=[{
            "role": "user",
            "content": "Propose new coach memories from this context:\n\n"
                       + json.dumps(payload, indent=2),
        }],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    return _parse_memory_candidates(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_coach_memory.py -k "candidates or suggest" -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add ai.py tests/test_coach_memory.py
git commit -m "feat(coach-memory): ai.suggest_memories + candidate parser"
```

---

## Task 5: `cockpit.coach_memory_peek` renderer

**Files:**
- Modify: `cockpit.py` (new renderer)
- Test: `tests/test_coach_memory.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_coach_memory.py`:

```python
import cockpit


def test_peek_empty_shows_prompt():
    html_out = cockpit.coach_memory_peek({})
    assert "Coach knows" in html_out
    assert "Nothing remembered yet" in html_out


def test_peek_lists_goals_and_injuries_and_escapes():
    digest = {
        "goals": [{"text": "comp <b>", "target_date": "2026-08-15"}],
        "injuries": [{"text": "left knee", "body_part": "knee"}],
        "patterns": [{"text": "p", "confidence": "high"}],
    }
    html_out = cockpit.coach_memory_peek(digest)
    assert "comp &lt;b&gt;" in html_out          # html-escaped
    assert "2026-08-15" in html_out
    assert "left knee" in html_out
    assert "Goals" in html_out and "Injuries" in html_out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_coach_memory.py -k peek -v`
Expected: FAIL with `AttributeError: module 'cockpit' has no attribute 'coach_memory_peek'`.

- [ ] **Step 3: Implement the renderer**

Add to `cockpit.py` (it already imports `html` and defines `_SPARK`, `_collapse_html`):

```python
def coach_memory_peek(digest: dict) -> str:
    """Compact 'Coach knows' card for the main dashboard."""
    head = (f'<div class="coach-head"><span class="glyph">{_SPARK}</span>'
            f'<div><h3>Coach knows</h3>'
            f'<div class="meta">your long-term context</div></div></div>')
    if not digest:
        body = ('<div class="empty-note" style="margin:0"><span class="ico">🧠</span> '
                'Nothing remembered yet — add goals, injuries, or notes on the '
                'Coach page.</div>')
        return _collapse_html(f'<div class="card coach">{head}{body}</div>')

    chip_style = ("display:inline-block;padding:2px 8px;margin:0 6px 6px 0;"
                  "border-radius:10px;background:rgba(255,255,255,.06);"
                  "font-size:12px;opacity:.85")
    chips = "".join(
        f'<span style="{chip_style}">{html.escape(label)}: {len(digest.get(key, []))}</span>'
        for label, key in (("Goals", "goals"), ("Injuries", "injuries"),
                            ("Patterns", "patterns"), ("Coaching", "coaching"),
                            ("Notes", "notes"))
        if digest.get(key))

    lines = []
    for g in digest.get("goals", [])[:2]:
        when = (f' · {html.escape(str(g["target_date"]))}'
                if g.get("target_date") else "")
        lines.append(f'<div style="margin:2px 0">🎯 {html.escape(str(g["text"]))}{when}</div>')
    for inj in digest.get("injuries", [])[:2]:
        where = (f' ({html.escape(str(inj["body_part"]))})'
                 if inj.get("body_part") else "")
        lines.append(f'<div style="margin:2px 0">🩹 {html.escape(str(inj["text"]))}{where}</div>')

    body = (f'<div style="margin-bottom:6px">{chips}</div>'
            + "".join(lines))
    return _collapse_html(f'<div class="card coach">{head}{body}</div>')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_coach_memory.py -k peek -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add cockpit.py tests/test_coach_memory.py
git commit -m "feat(coach-memory): coach_memory_peek dashboard card"
```

---

## Task 6: Wire memory into app.py (load, inject, peek, quick-add)

**Files:**
- Modify: `app.py`

This is Streamlit UI; verify by running the app. No unit test.

- [ ] **Step 1: Load memory + build the digest (outside the cached `load()`)**

In `app.py`, immediately after the line that unpacks `load(...)`:

```python
(daily, acts, checkins, body_battery, stress, grappling, stress_leaks,
 prebed_discovery, health_research, strength_summary) = load(config.LOCAL_TIMEZONE)
```

add:

```python
coach_memory_df = db.load_memory_df()                       # fresh: not cached
coach_memory_digest = analysis.build_coach_memory_digest(coach_memory_df)
```

(Loading outside the `@st.cache_data` `load()` keeps memory edits visible immediately after a `st.rerun()`.)

- [ ] **Step 2: Pass the digest into the weekly summary call**

Find the weekly summary block (the `md = ai.weekly_summary(week)` line) and change it to:

```python
md = ai.weekly_summary(week, coach_memory=coach_memory_digest)
```

- [ ] **Step 3: Pass the digest into the question call**

Find the `answer = ai.answer_question(...)` call and add the keyword argument (anywhere before `model=`), e.g. after `health_research=question_payload["health_research"],`:

```python
                coach_memory=coach_memory_digest,
```

- [ ] **Step 4: Render the peek + quick-add in the Coach section**

Find the Coach section header line:

```python
st.markdown(cockpit.section_label("Coach"), unsafe_allow_html=True)
```

Immediately after it, add:

```python
st.markdown(cockpit.coach_memory_peek(coach_memory_digest), unsafe_allow_html=True)
with st.form("coach_quickadd", clear_on_submit=True):
    qa_cols = st.columns([1, 3, 1])
    with qa_cols[0]:
        qcat = st.selectbox("Remember a",
                            ["note", "goal", "injury", "pattern", "coaching"],
                            key="qa_cat")
    with qa_cols[1]:
        qtext = st.text_input("Tell the coach something",
                              placeholder="e.g. tweaked left knee in BJJ", key="qa_text")
    with qa_cols[2]:
        qa_submit = st.form_submit_button("Remember", width="stretch")
    if qa_submit and qtext.strip():
        db.add_memory({"category": qcat, "text": qtext.strip(), "source": "user"})
        st.rerun()
st.page_link("pages/02_Coach.py", label="Manage everything the coach knows →")
```

- [ ] **Step 5: Verify by running the app**

Run: `streamlit run app.py`
Expected: under the **Coach** section header a "Coach knows" card appears (empty-state prompt at first); typing into the quick-add and pressing **Remember** adds a memory and the card updates after rerun. No exceptions in the terminal.

- [ ] **Step 6: Run the full test suite (no regressions)**

Run: `pytest -q`
Expected: PASS (all existing tests + the new `test_coach_memory.py`).

- [ ] **Step 7: Commit**

```bash
git add app.py
git commit -m "feat(coach-memory): wire memory digest + quick-add into dashboard"
```

---

## Task 7: The Coach page (`pages/02_Coach.py`)

**Files:**
- Create: `pages/02_Coach.py`

Streamlit UI; verify by running the app. No unit test (logic it uses is already tested in Tasks 1–4).

- [ ] **Step 1: Create the page**

Create `pages/02_Coach.py`:

```python
"""Coach memory — view and curate what the coach knows about you, and approve
AI-suggested memories. Manual entries save instantly; AI suggestions require
your approval before they are stored."""
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

st.set_page_config(page_title="Coach — Hankø", page_icon="🧠", layout="wide")
st.markdown(cockpit.CSS, unsafe_allow_html=True)

db.init_db()

CATEGORIES = ["goal", "injury", "pattern", "coaching", "note"]
LABELS = {"goal": "🎯 Goals", "injury": "🩹 Injuries", "pattern": "🔁 Patterns",
          "coaching": "🗒️ Coaching log", "note": "📌 Notes"}

st.markdown(cockpit.section_label("What the coach knows"), unsafe_allow_html=True)

memory = db.load_memory_df()           # active only

# ── add a memory ─────────────────────────────────────────────────────────────
with st.expander("➕ Add a memory", expanded=memory.empty):
    with st.form("add_memory", clear_on_submit=True):
        c = st.columns([1, 3])
        with c[0]:
            cat = st.selectbox("Category", CATEGORIES)
        with c[1]:
            text = st.text_input("What should the coach remember?")
        extra = st.columns(2)
        with extra[0]:
            target_date = st.text_input("Target date (goals, YYYY-MM-DD)", "")
        with extra[1]:
            body_part = st.text_input("Body part (injuries)", "")
        if st.form_submit_button("Save") and text.strip():
            rec = {"category": cat, "text": text.strip(), "source": "user"}
            if target_date.strip():
                rec["target_date"] = target_date.strip()
            if body_part.strip():
                rec["body_part"] = body_part.strip()
            db.add_memory(rec)
            st.rerun()

# ── grouped list with edit / archive / delete ────────────────────────────────
if memory.empty:
    st.caption("No active memories yet. Add one above, or use **Find things to "
               "remember** below.")
else:
    for cat in CATEGORIES:
        rows = memory[memory["category"] == cat]
        if rows.empty:
            continue
        st.markdown(f"#### {LABELS[cat]}")
        for _, r in rows.iterrows():
            mid = int(r["id"])
            cols = st.columns([6, 1, 1])
            with cols[0]:
                meta = []
                if r.get("target_date"):
                    meta.append(f"target {r['target_date']}")
                if r.get("body_part"):
                    meta.append(str(r["body_part"]))
                if r.get("source") == "ai":
                    meta.append("ai")
                suffix = f"  ·  _{', '.join(meta)}_" if meta else ""
                new_text = st.text_input(f"edit-{mid}", value=str(r["text"]),
                                         label_visibility="collapsed")
                if suffix:
                    st.caption(suffix)
                if new_text.strip() and new_text.strip() != str(r["text"]):
                    db.update_memory(mid, {"text": new_text.strip()})
                    st.rerun()
            with cols[1]:
                if st.button("Archive", key=f"arch-{mid}", width="stretch"):
                    db.archive_memory(mid)
                    st.rerun()
            with cols[2]:
                if st.button("Delete", key=f"del-{mid}", width="stretch"):
                    db.delete_memory(mid)
                    st.rerun()

# ── AI suggestions (button-triggered, approve before save) ────────────────────
st.markdown(cockpit.section_label("Find things to remember"), unsafe_allow_html=True)

if not config.ANTHROPIC_API_KEY:
    st.caption("Set `ANTHROPIC_API_KEY` in .env to enable AI suggestions.")
else:
    if st.button("✨ Find things to remember"):
        daily = db.load_daily_df()
        acts = db.load_activities_df()
        summary = (analysis.summarize(daily, acts, lookback=14)
                   if not daily.empty else {})
        strength = analysis.summarize_strength(
            db.load_strength_sessions_df(), db.load_strength_sets_df(),
            db.load_exercises_df(), db.load_profile(), None,
            formula=config.ONE_RM_FORMULA)
        digest = analysis.build_coach_memory_digest(memory)
        with st.spinner("Looking for durable patterns worth remembering…"):
            st.session_state["mem_candidates"] = ai.suggest_memories(
                summary, strength, digest)

    candidates = st.session_state.get("mem_candidates", [])
    if candidates == []:
        st.caption("No pending suggestions. Press the button to generate some.")
    for i, cand in enumerate(candidates):
        with st.container(border=True):
            st.markdown(f"**{cand['category']}** — {cand['text']}")
            if cand.get("rationale"):
                st.caption(cand["rationale"])
            b = st.columns([1, 1, 4])
            with b[0]:
                if st.button("Approve", key=f"appr-{i}", width="stretch"):
                    rec = {"category": cand["category"], "text": cand["text"],
                           "source": "ai"}
                    for k in ("confidence", "target_date", "body_part"):
                        if cand.get(k):
                            rec[k] = cand[k]
                    db.add_memory(rec)
                    st.session_state["mem_candidates"] = [
                        c for j, c in enumerate(candidates) if j != i]
                    st.rerun()
            with b[1]:
                if st.button("Reject", key=f"rej-{i}", width="stretch"):
                    st.session_state["mem_candidates"] = [
                        c for j, c in enumerate(candidates) if j != i]
                    st.rerun()
```

- [ ] **Step 2: Verify by running the app**

Run: `streamlit run app.py`
Then open the **Coach** page from the sidebar (it appears below **Strength**). Verify:
- Adding a memory (e.g. a `goal` with a target date) shows it under the right heading.
- **Edit** (change the text), **Archive**, and **Delete** each work and the list updates.
- With an API key set, **Find things to remember** returns candidate cards; **Approve** stores one as a `source=ai` memory and it appears in the list above; **Reject** discards it.
- No exceptions in the terminal.

- [ ] **Step 3: Verify the coach actually uses memory (end-to-end)**

On the main dashboard, add a memory via quick-add (e.g. injury "left knee, healing"), then ask a question in the **Coach** chat like "should I train legs hard today?" Confirm the answer references the knee. This exercises the digest → `answer_question` injection from Task 3/6.

- [ ] **Step 4: Commit**

```bash
git add pages/02_Coach.py
git commit -m "feat(coach-memory): Coach page — curate memories + approve AI suggestions"
```

---

## Self-Review

**1. Spec coverage**

| Spec item | Task |
|---|---|
| `coach_memory` table + CRUD | Task 1 |
| `build_coach_memory_digest` (pure, active-only, capped) | Task 2 |
| Inject digest into `analyze` / `weekly_summary` / `answer_question` + prompts | Task 3 (+ wired live in Task 6) |
| `ai.suggest_memories` + JSON candidate parser | Task 4 |
| `pages/02_Coach.py` (view/curate, quick-add, suggest+approve, coaching log) | Task 7 |
| Cockpit peek (counts + goals/injuries + quick-add + link) | Tasks 5 + 6 |
| Tests: digest, db CRUD, parser | Tasks 1, 2, 4 |
| Privacy: curated facts only, no raw time-series; user approves AI entries | Digest shapes only stored facts (Task 2); approval flow (Task 7) |
| Edge cases: no memories → `{}`; no key → `[]`; malformed JSON dropped | Tasks 2, 4 (tested) |

Coaching-log view is the `coaching`-category section in Task 7. `analyze()` is updated for signature consistency in Task 3 though it is not currently rendered in the UI — noted, low cost, keeps the three calls uniform.

**2. Placeholder scan:** None — every code step contains complete code; every command has expected output.

**3. Type consistency:** `add_memory(record)->int`, `update_memory(id, fields)`, `archive_memory(id)`, `delete_memory(id)`, `load_memory_df(status="active")`, `build_coach_memory_digest(memory_df, per_category_cap, coaching_cap)`, `_memory_block(coach_memory)`, `_parse_memory_candidates(text)->list[dict]`, `suggest_memories(summary, strength, existing_memories)`, `coach_memory_peek(digest)`. Category set `("goal","injury","pattern","coaching","note")` is identical across the table, digest, parser, and pages. Digest keys (`goals/injuries/patterns/coaching/notes`) are consistent between Task 2, Task 5, and Task 7.
