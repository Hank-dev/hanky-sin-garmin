# AGENTS.md

Guidance for coding agents working in this repository.

## Project

Garmin Coach is a private, single-user fitness dashboard. It syncs Garmin Connect
data into local SQLite, derives recovery and training metrics, displays them in
Streamlit, and can send compact summaries to Anthropic for coaching-style
analysis.

Keep the local privacy boundary intact:

- Do not commit or expose `.env`, `.garmin_tokens/`, `garmin.db`, `sync.log`, or
  raw Garmin payloads.
- AI features should receive compact summaries and derived metrics only, not raw
  time-series data.
- Garmin access uses unofficial `garminconnect`/`garth` endpoints. Treat field
  mappings as best-effort and expect endpoint shapes to change.

## Main Commands

```bash
# Install dependencies
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# Run tests
python -m pytest

# Run the dashboard
streamlit run app.py

# Garmin login and sync
python sync.py --login
python sync.py --days 90
python sync.py
```

`sync.py --login` is interactive and may require MFA. Do not run it unless the
user asked for it or explicitly approved it. Headless syncs should use cached
tokens with `interactive=False`.

## Architecture

- `config.py`: central environment/config loading. Prefer changing behavior here
  or via `.env` instead of hardcoding values in feature modules.
- `garmin_client.py`: Garmin authentication and token reuse.
- `ingest.py`: Garmin endpoint fetching and JSON-to-record mapping.
- `db.py`: SQLite schema, idempotent upserts, and pandas loaders.
- `analysis.py`: pure derived metrics and summaries. Keep network, UI, and DB I/O
  out of this module.
- `ai.py`: Anthropic API boundary and prompts. Preserve the summary-only payload
  contract.
- `app.py`: main Streamlit recovery dashboard.
- `pages/01_Strength.py` and `pages/02_Coach.py`: Streamlit multipage views.
- `strength_catalog.py`, `strength_standards.py`, and `cockpit.py`: domain and UI
  helpers used by the dashboard pages.
- `tests/`: pytest coverage for analytics, ingest, UI helpers, sync planning,
  strength features, and AI payloads.

Dates are stored and passed around as `YYYY-MM-DD` strings. Daily data is keyed
by date; activities are keyed by Garmin `activity_id` and joined to daily data by
date where needed.

## Garmin Field Mapping

Garmin JSON fields are undocumented and can change. `ingest.py` centralizes
field extraction through the `dig(obj, *paths)` pattern. When a dashboard field is
empty, inspect the relevant stored `raw_json` row, find the current key path, and
add it to the appropriate `dig()` call.

All sync writes should be idempotent. Re-syncing a date must be safe, and Garmin
sync must not overwrite user-entered `daily_checkins`.

## Testing Guidance

Use focused pytest runs while editing:

```bash
python -m pytest tests/test_strength_analysis.py
python -m pytest tests/test_ai_payload.py
python -m pytest
```

Add or update tests when changing shared analytics, DB contracts, Garmin ingest
mapping, AI payload construction, or Streamlit helper behavior. For narrow UI
copy/layout changes, a smoke run can be enough if behavior is unchanged.

## Coding Style

- Follow the existing small-module Python style.
- Prefer explicit pandas/numpy transformations over hidden side effects.
- Keep `analysis.py` deterministic and unit-testable.
- Keep Streamlit rendering code separate from pure calculations when practical.
- Use config values from `config.py` instead of duplicating environment reads.
- Avoid broad refactors unless they are required for the requested change.

