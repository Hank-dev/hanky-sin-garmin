use garmin_coach_desktop::store::{Activity, Checkin, Store};
use rusqlite::Connection;

fn source_schema_database() -> (tempfile::TempDir, std::path::PathBuf) {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("source-schema.sqlite");
    // Use the actual Python application's declared schema, without importing its config
    // or opening a personal database. A source schema change now exercises this test.
    let source = include_str!("../../db.py");
    let schema = source
        .split_once("SCHEMA = \"\"\"")
        .unwrap()
        .1
        .split_once("\"\"\"")
        .unwrap()
        .0;
    Connection::open(&path)
        .unwrap()
        .execute_batch(schema)
        .unwrap();
    (dir, path)
}

#[test]
fn full_source_schema_reads_and_writes_across_six_page_entities() {
    let (_dir, path) = source_schema_database();
    let db = Connection::open(&path).unwrap();
    db.execute("INSERT INTO daily_metrics (date, sleep_seconds, sleep_score, hrv_overnight_avg) VALUES ('2026-09-26', 28800, 82, 48)", []).unwrap();
    db.execute(
        "INSERT INTO exercises (exercise_id, name) VALUES ('squat', 'Squat')",
        [],
    )
    .unwrap();
    drop(db);
    let store = Store::open(&path).unwrap();
    let before = store.snapshot().unwrap();
    assert_eq!(before.daily[0].sleep_hours(), Some(8.0));
    assert_eq!(before.daily[0].hrv, Some(48.0));
    let record = Activity {
        date: "2026-09-26".into(),
        kind: Some("running".into()),
        name: Some("Synthetic intervals".into()),
        duration_s: Some(2400.0),
        distance_m: Some(5000.0),
        avg_hr: Some(155.0),
        max_hr: Some(174.0),
        load: Some(45.0),
        aerobic_te: Some(3.3),
        anaerobic_te: Some(1.2),
        ..Default::default()
    };
    let id = store.add_activity(&record).unwrap();
    store
        .save_checkin(&Checkin {
            date: record.date.clone(),
            pain: Some(2),
            fatigue: Some(4),
            energy: Some(7),
            note: Some("Synthetic".into()),
        })
        .unwrap();
    let sid = store
        .add_session("2026-09-26", "Synthetic strength")
        .unwrap();
    store.add_set(&sid, "squat", 5, 85.0).unwrap();
    let mid = store.add_memory("goal", "Synthetic goal").unwrap();
    let eid = store
        .add_experiment(
            "Synthetic sleep",
            "More sleep",
            &["sleep_score".into()],
            "2026-09-26",
            14,
        )
        .unwrap();
    let after = Store::open(&path).unwrap().snapshot().unwrap();
    let saved = after.activities.iter().find(|a| a.id == id).unwrap();
    assert_eq!((saved.avg_hr, saved.max_hr), (Some(155.0), Some(174.0)));
    assert_eq!(
        (saved.aerobic_te, saved.anaerobic_te),
        (Some(3.3), Some(1.2))
    );
    assert_eq!(after.checkins[0].energy, Some(7));
    assert!(after.sessions.iter().any(|s| s.id == sid));
    assert_eq!(
        after.memories.iter().find(|m| m.id == mid).unwrap().text,
        "Synthetic goal"
    );
    assert_eq!(
        after
            .experiments
            .iter()
            .find(|e| e.id == eid)
            .unwrap()
            .metrics,
        "[\"sleep_score\"]"
    );
    assert_eq!(
        Connection::open(&path)
            .unwrap()
            .query_row("PRAGMA integrity_check", [], |r| r.get::<_, String>(0))
            .unwrap(),
        "ok"
    );
}

#[test]
fn invalid_experiment_metric_is_rejected_without_a_database_row() {
    let (_dir, path) = source_schema_database();
    let store = Store::open(&path).unwrap();
    assert!(store
        .add_experiment("Bad metric", "", &["not_a_metric".into()], "2026-09-26", 14)
        .is_err());
    assert!(store.snapshot().unwrap().experiments.is_empty());
    let id = store
        .add_experiment("Valid", "", &["sleep_score".into()], "2026-09-26", 14)
        .unwrap();
    assert!(store
        .edit_experiment(id, "Broken", "", &["not_a_metric".into()])
        .is_err());
    assert_eq!(store.snapshot().unwrap().experiments[0].name, "Valid");
}

#[test]
fn invalid_manual_heart_rate_order_is_rejected_without_a_database_row() {
    let (_dir, path) = source_schema_database();
    let store = Store::open(&path).unwrap();
    let invalid = Activity {
        date: "2026-09-26".into(),
        kind: Some("running".into()),
        duration_s: Some(1800.0),
        avg_hr: Some(185.0),
        max_hr: Some(174.0),
        ..Default::default()
    };
    assert!(store.add_activity(&invalid).is_err());
    assert!(store.snapshot().unwrap().activities.is_empty());
}
