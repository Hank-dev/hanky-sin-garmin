# Garmin Coach Desktop (Rust preview)

Native Rust/egui client for the existing Garmin Coach SQLite database. This is a local preview, not a full replacement for the Streamlit app. It does not start a browser or server, and opening a screen makes no network request.

## Build and run (Linux)

From this directory:

    cargo test --locked
    cargo run --release -- --db /absolute/path/to/garmin.db

Or set `DB_PATH` to an existing SQLite file and run `cargo run --release`. The file must already exist and contain the Garmin Coach `daily_metrics` table. A missing or invalid file is rejected rather than silently created. For the original checkout, the existing database is normally at the repository root as `garmin.db`; do not commit or publish that file. Back up the database before making any edits. The client reads and writes the selected SQLite file in place; it does not migrate, copy, or automatically import data. It works offline for the implemented screens. For a first use, make an isolated copy of your DB and pass that path, or create a synthetic test DB; the automated tests never use your personal data.

## Implemented

- Six native sidebar screens with recent records from SQLite, a manual Refresh button, missing-value and empty states. The current snapshot is capped at 120 daily rows and activities, 100 sessions, 3,000 sets, and 200 memories/experiments; older records stay in SQLite but are not shown.
- Cockpit: recorded Garmin readiness, HRV, resting HR, sleep, battery, stress and steps; date-keyed pain/fatigue/energy/note check-ins.
- Sleep: recent recorded sleep scores, stage totals and a compact chart (not a prediction).
- Activities: saved timeline and manual activity entry with duration, distance, HR, training load and training-effect validation.
- Strength: session/set history and a basic local session/set logger using catalogued exercises. This logger is an addition to the source UI; it does not replace Strong/Hevy imports.
- Coach: local memory add/edit/archive/restore/confirm-delete.
- Lab: experiment record add/edit/complete/reactivate/confirm-delete.

Edits refresh the in-memory snapshot. Binary startup rejects a missing DB path; the UI never loads `.env`, Garmin OAuth tokens or an Anthropic key. No password or verification code is requested by this client.

## Not ported (do not infer parity from the six page names)

The original Python/Streamlit app is still needed for Garmin login and synchronization, Strong and Hevy importers, daily/weekly reports, Telegram bot, Anthropic coaching/chat, recovery and capacity algorithms, grappling analysis, predictions, correlation/experiment effects, advanced chart/filter panels and strength standards. Its Python dependencies remain separate. There is no cross-feature parity yet. See `../docs/rust-port-parity.md` for the source-cited full checklist and acceptance tests.

No hard startup-time or memory-use speedup has been established relative to Streamlit. Native UI and SQLite avoid a local web server, but performance must be measured on comparable datasets before promising "fast and snappy" results.

## Development verification

    cargo fmt --check
    cargo test --locked
    cargo clippy --locked --all-targets -- -D warnings

The Rust tests use temporary synthetic databases, including a fixture generated from the source application's checked-in `db.py` schema. The original Python tests should also remain passing. The client is intended for a local desktop session with Wayland or X11; running headlessly is only supported for the unit/integration tests.
