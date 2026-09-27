use garmin_coach_desktop::db_path_from;
use garmin_coach_desktop::store::{Activity, Checkin, Store};
use rusqlite::Connection;

fn synthetic_database() -> (tempfile::TempDir, std::path::PathBuf) {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("synthetic.sqlite");
    let db = Connection::open(&path).unwrap();
    db.execute_batch(
        "CREATE TABLE daily_metrics (date TEXT PRIMARY KEY, resting_hr REAL, hrv_overnight_avg REAL,
          sleep_seconds REAL, sleep_score REAL, deep_seconds REAL, rem_seconds REAL,
          light_seconds REAL, body_battery_start REAL, stress_avg REAL, steps REAL,
          training_readiness_score REAL);
         CREATE TABLE activities (activity_id TEXT PRIMARY KEY, date TEXT, name TEXT, type TEXT,
          duration_s REAL, distance_m REAL, avg_hr REAL, max_hr REAL, training_load REAL,
          aerobic_te REAL, anaerobic_te REAL);
         CREATE TABLE daily_checkins (date TEXT PRIMARY KEY, pain INTEGER, fatigue INTEGER,
          energy INTEGER, note TEXT, updated_at TEXT);
         CREATE TABLE exercises (exercise_id TEXT PRIMARY KEY, name TEXT);
         CREATE TABLE strength_sessions (session_id TEXT PRIMARY KEY, date TEXT, name TEXT,
          source TEXT, notes TEXT, updated_at TEXT);
         CREATE TABLE strength_sets (set_id TEXT PRIMARY KEY, session_id TEXT, exercise_id TEXT,
          position INTEGER, set_index INTEGER, side TEXT, reps INTEGER, weight_kg REAL,
          rpe REAL, is_warmup INTEGER, completed INTEGER);
         CREATE TABLE coach_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL,
          text TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
         CREATE TABLE experiments (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
          hypothesis TEXT, metrics TEXT NOT NULL, baseline_days INTEGER NOT NULL,
          start_date TEXT NOT NULL, end_date TEXT, status TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);",
    ).unwrap();
    drop(db);
    (dir, path)
}

#[test]
fn missing_database_is_rejected_without_creating_any_file() {
    let dir = tempfile::tempdir().unwrap();
    let missing = dir.path().join("does-not-exist.sqlite");
    assert!(Store::open(&missing).is_err());
    assert!(!missing.exists());
}

#[test]
fn snapshot_reads_real_rows_and_nullable_metrics_from_existing_schema() {
    let (_dir, path) = synthetic_database();
    let db = Connection::open(&path).unwrap();
    db.execute("INSERT INTO daily_metrics (date, sleep_seconds, sleep_score) VALUES ('2026-09-26', 28800, 82)", []).unwrap();
    db.execute("INSERT INTO activities (activity_id, date, name, type, duration_s) VALUES ('garmin-1', '2026-09-26', 'Run', 'running', 1800)", []).unwrap();
    drop(db);
    let snapshot = Store::open(&path).unwrap().snapshot().unwrap();
    assert_eq!(snapshot.daily.len(), 1);
    assert_eq!(snapshot.daily[0].date, "2026-09-26");
    assert_eq!(snapshot.daily[0].sleep_hours(), Some(8.0));
    assert_eq!(snapshot.daily[0].resting_hr, None);
    assert_eq!(snapshot.activities[0].name.as_deref(), Some("Run"));
    assert!(snapshot.sessions.is_empty());
}

#[test]
fn checkin_upsert_replaces_only_selected_date_not_garmin_metrics() {
    let (_dir, path) = synthetic_database();
    let db = Connection::open(&path).unwrap();
    db.execute(
        "INSERT INTO daily_metrics (date, sleep_score) VALUES ('2026-09-26', 82)",
        [],
    )
    .unwrap();
    drop(db);
    let store = Store::open(&path).unwrap();
    let mut entry = Checkin {
        date: "2026-09-26".into(),
        pain: Some(3),
        fatigue: Some(6),
        energy: Some(4),
        note: Some("sore".into()),
    };
    store.save_checkin(&entry).unwrap();
    entry.energy = Some(7);
    store.save_checkin(&entry).unwrap();
    let snap = store.snapshot().unwrap();
    assert_eq!(snap.checkins.len(), 1);
    assert_eq!(snap.checkins[0].energy, Some(7));
    assert_eq!(snap.daily[0].sleep_score, Some(82.0));
}

#[test]
fn manual_activity_roundtrips_with_distinct_local_id() {
    let (_dir, path) = synthetic_database();
    let store = Store::open(&path).unwrap();
    let record = Activity {
        date: "2026-09-26".into(),
        kind: Some("bjj".into()),
        name: Some("Open mat".into()),
        duration_s: Some(3600.0),
        distance_m: None,
        ..Default::default()
    };
    let id = store.add_activity(&record).unwrap();
    assert!(id.starts_with("manual:2026-09-26:"));
    let snap = store.snapshot().unwrap();
    assert_eq!(snap.activities[0].id, id);
    assert_eq!(snap.activities[0].duration_s, Some(3600.0));
}

#[test]
fn logged_strength_session_and_set_are_visible_together() {
    let (_dir, path) = synthetic_database();
    Connection::open(&path)
        .unwrap()
        .execute(
            "INSERT INTO exercises (exercise_id, name) VALUES ('squat', 'Squat')",
            [],
        )
        .unwrap();
    let store = Store::open(&path).unwrap();
    let sid = store.add_session("2026-09-26", "Lower body").unwrap();
    let set_id = store.add_set(&sid, "squat", 5, 80.0).unwrap();
    let snap = store.snapshot().unwrap();
    assert_eq!(snap.sessions[0].id, sid);
    assert_eq!(snap.sessions[0].source.as_deref(), Some("manual"));
    assert_eq!(snap.sets[0].id, set_id);
    assert_eq!(snap.sets[0].weight_kg, Some(80.0));
    assert_eq!(snap.sets[0].exercise, "squat");
}

#[test]
fn coach_memory_create_edit_archive_delete_lifecycle() {
    let (_dir, path) = synthetic_database();
    let store = Store::open(&path).unwrap();
    let id = store.add_memory("goal", "Run faster").unwrap();
    store.edit_memory(id, "Run a 5K").unwrap();
    assert_eq!(store.snapshot().unwrap().memories[0].text, "Run a 5K");
    store.set_memory_status(id, "archived").unwrap();
    assert_eq!(store.snapshot().unwrap().memories[0].status, "archived");
    store.delete_memory(id).unwrap();
    assert!(store.snapshot().unwrap().memories.is_empty());
}

#[test]
fn lab_experiment_json_metrics_survive_edit_completion_and_delete() {
    let (_dir, path) = synthetic_database();
    let store = Store::open(&path).unwrap();
    let id = store
        .add_experiment(
            "Early bedtime",
            "More sleep",
            &["sleep_score".into(), "hrv_overnight_avg".into()],
            "2026-09-26",
            14,
        )
        .unwrap();
    assert_eq!(
        store.snapshot().unwrap().experiments[0].metrics,
        "[\"sleep_score\",\"hrv_overnight_avg\"]"
    );
    store
        .edit_experiment(id, "No screens", "Less stress", &["stress_avg".into()])
        .unwrap();
    store.set_experiment_status(id, "complete").unwrap();
    let row = store.snapshot().unwrap().experiments.remove(0);
    assert_eq!(row.name, "No screens");
    assert_eq!(row.metrics, "[\"stress_avg\"]");
    assert_eq!(row.status, "complete");
    store.delete_experiment(id).unwrap();
    assert!(store.snapshot().unwrap().experiments.is_empty());
}

#[test]
fn cli_requires_explicit_database_and_rejects_incomplete_flags() {
    assert!(db_path_from(Vec::<String>::new(), None).is_err());
    assert!(db_path_from(vec!["--db".into()], None).is_err());
    assert!(db_path_from(vec!["--unknown".into()], Some("fallback.db".into())).is_err());
    assert_eq!(
        db_path_from(
            vec!["--db".into(), "chosen.db".into()],
            Some("fallback.db".into())
        )
        .unwrap()
        .to_str(),
        Some("chosen.db")
    );
    assert_eq!(
        db_path_from(Vec::<String>::new(), Some("fallback.db".into()))
            .unwrap()
            .to_str(),
        Some("fallback.db")
    );
}
