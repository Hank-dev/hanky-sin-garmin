use rusqlite::{params, Connection, OpenFlags, Row};
use std::{collections::HashSet, error::Error, path::Path, time::Duration};

pub type Result<T> = std::result::Result<T, Box<dyn Error>>;

// Keep aligned with analysis.py EXPERIMENT_METRICS: unknown keys have no
// defined Python-side comparison and must not be written to the shared DB.
pub const EXPERIMENT_METRICS: [&str; 9] = [
    "hrv_overnight_avg",
    "resting_hr",
    "sleep_hours",
    "sleep_score",
    "body_battery_high",
    "stress_avg",
    "energy",
    "pain",
    "fatigue",
];

fn validate_experiment_metrics(metrics: &[String]) -> Result<()> {
    if metrics.is_empty()
        || metrics
            .iter()
            .any(|key| !EXPERIMENT_METRICS.contains(&key.as_str()))
    {
        return Err("Choose at least one supported experiment metric".into());
    }
    Ok(())
}

fn validate_date(value: &str) -> Result<()> {
    let date = chrono::NaiveDate::parse_from_str(value, "%Y-%m-%d")?;
    if date.format("%Y-%m-%d").to_string() != value {
        return Err("Use YYYY-MM-DD date format".into());
    }
    Ok(())
}

pub struct Store {
    conn: Connection,
}

#[derive(Clone, Default)]
pub struct Daily {
    pub date: String,
    pub resting_hr: Option<f64>,
    pub hrv: Option<f64>,
    pub sleep_seconds: Option<f64>,
    pub sleep_score: Option<f64>,
    pub deep_seconds: Option<f64>,
    pub rem_seconds: Option<f64>,
    pub light_seconds: Option<f64>,
    pub battery: Option<f64>,
    pub stress: Option<f64>,
    pub steps: Option<f64>,
    pub readiness: Option<f64>,
}
impl Daily {
    pub fn sleep_hours(&self) -> Option<f64> {
        self.sleep_seconds.map(|n| n / 3600.0)
    }
}

#[derive(Clone, Default)]
pub struct Activity {
    pub id: String,
    pub date: String,
    pub name: Option<String>,
    pub kind: Option<String>,
    pub duration_s: Option<f64>,
    pub distance_m: Option<f64>,
    pub avg_hr: Option<f64>,
    pub max_hr: Option<f64>,
    pub load: Option<f64>,
    pub aerobic_te: Option<f64>,
    pub anaerobic_te: Option<f64>,
}
#[derive(Clone, Default)]
pub struct Checkin {
    pub date: String,
    pub pain: Option<i64>,
    pub fatigue: Option<i64>,
    pub energy: Option<i64>,
    pub note: Option<String>,
}
#[derive(Clone, Default)]
pub struct Session {
    pub id: String,
    pub date: String,
    pub name: Option<String>,
    pub source: Option<String>,
    pub notes: Option<String>,
}
#[derive(Clone, Default)]
pub struct StrengthSet {
    pub id: String,
    pub session_id: String,
    pub exercise: String,
    pub reps: Option<i64>,
    pub weight_kg: Option<f64>,
    pub rpe: Option<f64>,
    pub warmup: bool,
}
#[derive(Clone, Default)]
pub struct Exercise {
    pub id: String,
    pub name: String,
}
#[derive(Clone, Default)]
pub struct Memory {
    pub id: i64,
    pub category: String,
    pub text: String,
    pub status: String,
}
#[derive(Clone, Default)]
pub struct Experiment {
    pub id: i64,
    pub name: String,
    pub hypothesis: Option<String>,
    pub metrics: String,
    pub baseline_days: i64,
    pub start_date: String,
    pub end_date: Option<String>,
    pub status: String,
}
#[derive(Default)]
pub struct Snapshot {
    pub daily: Vec<Daily>,
    pub activities: Vec<Activity>,
    pub checkins: Vec<Checkin>,
    pub sessions: Vec<Session>,
    pub sets: Vec<StrengthSet>,
    pub exercises: Vec<Exercise>,
    pub memories: Vec<Memory>,
    pub experiments: Vec<Experiment>,
}

impl Store {
    pub fn add_experiment(
        &self,
        name: &str,
        hypothesis: &str,
        metrics: &[String],
        start_date: &str,
        baseline_days: i64,
    ) -> Result<i64> {
        validate_date(start_date)?;
        validate_experiment_metrics(metrics)?;
        if name.trim().is_empty() || !(3..=90).contains(&baseline_days) {
            return Err("Experiment requires a name, metric and 3–90 baseline days".into());
        }
        let now = chrono::Utc::now().to_rfc3339();
        self.conn.execute(
            "INSERT INTO experiments (name, hypothesis, metrics, baseline_days, start_date, status, created_at, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5, 'active', ?6, ?6)",
            params![name.trim(), hypothesis.trim(), serde_json::to_string(metrics)?, baseline_days, start_date, now],
        )?;
        Ok(self.conn.last_insert_rowid())
    }
    pub fn edit_experiment(
        &self,
        id: i64,
        name: &str,
        hypothesis: &str,
        metrics: &[String],
    ) -> Result<()> {
        validate_experiment_metrics(metrics)?;
        if name.trim().is_empty() {
            return Err("Experiment name and metrics are required".into());
        }
        self.conn.execute(
            "UPDATE experiments SET name=?1, hypothesis=?2, metrics=?3, updated_at=?4 WHERE id=?5",
            params![
                name.trim(),
                hypothesis.trim(),
                serde_json::to_string(metrics)?,
                chrono::Utc::now().to_rfc3339(),
                id
            ],
        )?;
        Ok(())
    }
    pub fn set_experiment_status(&self, id: i64, status: &str) -> Result<()> {
        if !["active", "complete"].contains(&status) {
            return Err("Unsupported experiment status".into());
        }
        self.conn.execute(
            "UPDATE experiments SET status=?1, updated_at=?2 WHERE id=?3",
            params![status, chrono::Utc::now().to_rfc3339(), id],
        )?;
        Ok(())
    }
    pub fn delete_experiment(&self, id: i64) -> Result<()> {
        self.conn
            .execute("DELETE FROM experiments WHERE id=?1", [id])?;
        Ok(())
    }

    pub fn add_memory(&self, category: &str, text: &str) -> Result<i64> {
        if category.trim().is_empty() || text.trim().is_empty() {
            return Err("Memory category and text are required".into());
        }
        let now = chrono::Utc::now().to_rfc3339();
        self.conn.execute(
            "INSERT INTO coach_memory (category, text, status, source, created_at, updated_at)
             VALUES (?1, ?2, 'active', 'user', ?3, ?3)",
            params![category.trim(), text.trim(), now],
        )?;
        Ok(self.conn.last_insert_rowid())
    }
    pub fn edit_memory(&self, id: i64, text: &str) -> Result<()> {
        if text.trim().is_empty() {
            return Err("Memory text is required".into());
        }
        self.conn.execute(
            "UPDATE coach_memory SET text=?1, updated_at=?2 WHERE id=?3",
            params![text.trim(), chrono::Utc::now().to_rfc3339(), id],
        )?;
        Ok(())
    }
    pub fn set_memory_status(&self, id: i64, status: &str) -> Result<()> {
        if !["active", "archived"].contains(&status) {
            return Err("Unsupported memory status".into());
        }
        self.conn.execute(
            "UPDATE coach_memory SET status=?1, updated_at=?2 WHERE id=?3",
            params![status, chrono::Utc::now().to_rfc3339(), id],
        )?;
        Ok(())
    }
    pub fn delete_memory(&self, id: i64) -> Result<()> {
        self.conn
            .execute("DELETE FROM coach_memory WHERE id=?1", [id])?;
        Ok(())
    }

    pub fn add_session(&self, date: &str, name: &str) -> Result<String> {
        validate_date(date)?;
        if name.trim().is_empty() {
            return Err("Session name is required".into());
        }
        let id = format!("manual:{}", uuid::Uuid::new_v4());
        self.conn.execute(
            "INSERT INTO strength_sessions (session_id, date, name, source) VALUES (?1, ?2, ?3, 'manual')",
            params![id, date, name.trim()],
        )?;
        Ok(id)
    }

    pub fn add_set(
        &self,
        session_id: &str,
        exercise_id: &str,
        reps: i64,
        weight_kg: f64,
    ) -> Result<String> {
        if !(1..=100).contains(&reps)
            || !weight_kg.is_finite()
            || !(0.0..=1000.0).contains(&weight_kg)
        {
            return Err("Reps must be 1–100 and weight 0–1000 kg".into());
        }
        let has_session: i64 = self.conn.query_row(
            "SELECT count(*) FROM strength_sessions WHERE session_id=?1",
            [session_id],
            |r| r.get(0),
        )?;
        let has_exercise: i64 = self.conn.query_row(
            "SELECT count(*) FROM exercises WHERE exercise_id=?1",
            [exercise_id],
            |r| r.get(0),
        )?;
        if has_session == 0 || has_exercise == 0 {
            return Err("Select an existing session and exercise".into());
        }
        let id = format!("manual:{}", uuid::Uuid::new_v4());
        self.conn.execute(
            "INSERT INTO strength_sets (set_id, session_id, exercise_id, position, set_index, side, reps, weight_kg, is_warmup, completed)
             VALUES (?1, ?2, ?3, (SELECT COALESCE(MAX(position), -1)+1 FROM strength_sets WHERE session_id=?2),
             (SELECT COUNT(*)+1 FROM strength_sets WHERE session_id=?2 AND exercise_id=?3), 'both', ?4, ?5, 0, 1)",
            params![id, session_id, exercise_id, reps, weight_kg],
        )?;
        Ok(id)
    }

    pub fn add_activity(&self, activity: &Activity) -> Result<String> {
        validate_date(&activity.date)?;
        if activity.kind.as_deref().unwrap_or("").trim().is_empty() {
            return Err("Activity type is required".into());
        }
        let duration = activity.duration_s.ok_or("Duration is required")?;
        if !duration.is_finite() || duration <= 0.0 {
            return Err("Duration must be positive".into());
        }
        for number in [
            activity.distance_m,
            activity.avg_hr,
            activity.max_hr,
            activity.load,
            activity.aerobic_te,
            activity.anaerobic_te,
        ]
        .into_iter()
        .flatten()
        {
            if !number.is_finite() || number < 0.0 {
                return Err("Activity metrics must be non-negative and finite".into());
            }
        }
        if let (Some(avg), Some(max)) = (activity.avg_hr, activity.max_hr) {
            if avg > max {
                return Err("Average HR cannot exceed maximum HR".into());
            }
        }
        if [activity.aerobic_te, activity.anaerobic_te]
            .into_iter()
            .flatten()
            .any(|n| n > 5.0)
        {
            return Err("Training effect cannot exceed 5".into());
        }
        let id = format!(
            "manual:{}:{}",
            activity.date,
            &uuid::Uuid::new_v4().simple().to_string()[..12]
        );
        self.conn.execute(
            "INSERT INTO activities (activity_id, date, name, type, duration_s, distance_m, avg_hr, max_hr, training_load, aerobic_te, anaerobic_te)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
            params![id, activity.date, activity.name, activity.kind, duration, activity.distance_m,
                activity.avg_hr, activity.max_hr, activity.load, activity.aerobic_te, activity.anaerobic_te],
        )?;
        Ok(id)
    }

    pub fn save_checkin(&self, entry: &Checkin) -> Result<()> {
        validate_date(&entry.date)?;
        for score in [entry.pain, entry.fatigue, entry.energy]
            .into_iter()
            .flatten()
        {
            if !(1..=10).contains(&score) {
                return Err("Check-in scores must be between 1 and 10".into());
            }
        }
        self.conn.execute(
            "INSERT INTO daily_checkins (date, pain, fatigue, energy, note) VALUES (?1, ?2, ?3, ?4, ?5)
             ON CONFLICT(date) DO UPDATE SET pain=excluded.pain, fatigue=excluded.fatigue,
             energy=excluded.energy, note=excluded.note, updated_at=datetime('now')",
            params![entry.date, entry.pain, entry.fatigue, entry.energy, entry.note],
        )?;
        Ok(())
    }

    pub fn open(path: &Path) -> Result<Self> {
        if !path.is_file() {
            return Err(format!("SQLite database does not exist: {}", path.display()).into());
        }
        let conn = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_WRITE)?;
        conn.busy_timeout(Duration::from_secs(3))?;
        let table_count: i64 = conn.query_row(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='daily_metrics'",
            [],
            |r| r.get(0),
        )?;
        if table_count == 0 {
            return Err("Not a Garmin Coach database (daily_metrics missing)".into());
        }
        Ok(Self { conn })
    }

    // Only static, source-controlled SQL identifiers enter this helper. New columns on a
    // newer Python schema are ignored; columns absent from an older version yield NULL.
    fn rows<T, F>(
        &self,
        table: &str,
        columns: &[&str],
        order: &str,
        limit: usize,
        map: F,
    ) -> Result<Vec<T>>
    where
        F: FnMut(&Row<'_>) -> rusqlite::Result<T>,
    {
        let mut stmt = self.conn.prepare(&format!("PRAGMA table_info({table})"))?;
        let available: HashSet<String> = stmt
            .query_map([], |r| r.get(1))?
            .collect::<rusqlite::Result<_>>()?;
        if available.is_empty() {
            return Ok(Vec::new());
        }
        let selected = columns
            .iter()
            .map(|col| {
                if available.contains(*col) {
                    (*col).to_owned()
                } else {
                    format!("NULL AS {col}")
                }
            })
            .collect::<Vec<_>>()
            .join(", ");
        let ordering = if available.contains(order) {
            format!(" ORDER BY {order} DESC")
        } else {
            String::new()
        };
        let sql = format!("SELECT {selected} FROM {table}{ordering} LIMIT {limit}");
        let mut stmt = self.conn.prepare(&sql)?;
        let records = stmt
            .query_map([], map)?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(records)
    }

    pub fn snapshot(&self) -> Result<Snapshot> {
        Ok(Snapshot {
            daily: self.rows(
                "daily_metrics",
                &[
                    "date",
                    "resting_hr",
                    "hrv_overnight_avg",
                    "sleep_seconds",
                    "sleep_score",
                    "deep_seconds",
                    "rem_seconds",
                    "light_seconds",
                    "body_battery_start",
                    "stress_avg",
                    "steps",
                    "training_readiness_score",
                ],
                "date",
                120,
                |r| {
                    Ok(Daily {
                        date: r.get::<_, Option<String>>(0)?.unwrap_or_default(),
                        resting_hr: r.get(1)?,
                        hrv: r.get(2)?,
                        sleep_seconds: r.get(3)?,
                        sleep_score: r.get(4)?,
                        deep_seconds: r.get(5)?,
                        rem_seconds: r.get(6)?,
                        light_seconds: r.get(7)?,
                        battery: r.get(8)?,
                        stress: r.get(9)?,
                        steps: r.get(10)?,
                        readiness: r.get(11)?,
                    })
                },
            )?,
            activities: self.rows(
                "activities",
                &[
                    "activity_id",
                    "date",
                    "name",
                    "type",
                    "duration_s",
                    "distance_m",
                    "avg_hr",
                    "max_hr",
                    "training_load",
                    "aerobic_te",
                    "anaerobic_te",
                ],
                "date",
                120,
                |r| {
                    Ok(Activity {
                        id: r.get::<_, Option<String>>(0)?.unwrap_or_default(),
                        date: r.get::<_, Option<String>>(1)?.unwrap_or_default(),
                        name: r.get(2)?,
                        kind: r.get(3)?,
                        duration_s: r.get(4)?,
                        distance_m: r.get(5)?,
                        avg_hr: r.get(6)?,
                        max_hr: r.get(7)?,
                        load: r.get(8)?,
                        aerobic_te: r.get(9)?,
                        anaerobic_te: r.get(10)?,
                    })
                },
            )?,
            checkins: self.rows(
                "daily_checkins",
                &["date", "pain", "fatigue", "energy", "note"],
                "date",
                120,
                |r| {
                    Ok(Checkin {
                        date: r.get::<_, Option<String>>(0)?.unwrap_or_default(),
                        pain: r.get(1)?,
                        fatigue: r.get(2)?,
                        energy: r.get(3)?,
                        note: r.get(4)?,
                    })
                },
            )?,
            sessions: self.rows(
                "strength_sessions",
                &["session_id", "date", "name", "source", "notes"],
                "date",
                100,
                |r| {
                    Ok(Session {
                        id: r.get::<_, Option<String>>(0)?.unwrap_or_default(),
                        date: r.get::<_, Option<String>>(1)?.unwrap_or_default(),
                        name: r.get(2)?,
                        source: r.get(3)?,
                        notes: r.get(4)?,
                    })
                },
            )?,
            sets: self.rows(
                "strength_sets",
                &[
                    "set_id",
                    "session_id",
                    "exercise_id",
                    "reps",
                    "weight_kg",
                    "rpe",
                    "is_warmup",
                ],
                "logged_at",
                3000,
                |r| {
                    Ok(StrengthSet {
                        id: r.get::<_, Option<String>>(0)?.unwrap_or_default(),
                        session_id: r.get::<_, Option<String>>(1)?.unwrap_or_default(),
                        exercise: r.get::<_, Option<String>>(2)?.unwrap_or_default(),
                        reps: r.get(3)?,
                        weight_kg: r.get(4)?,
                        rpe: r.get(5)?,
                        warmup: r.get::<_, Option<i64>>(6)?.unwrap_or(0) != 0,
                    })
                },
            )?,
            exercises: self.rows("exercises", &["exercise_id", "name"], "name", 1000, |r| {
                Ok(Exercise {
                    id: r.get::<_, Option<String>>(0)?.unwrap_or_default(),
                    name: r.get::<_, Option<String>>(1)?.unwrap_or_default(),
                })
            })?,
            memories: self.rows(
                "coach_memory",
                &["id", "category", "text", "status"],
                "id",
                200,
                |r| {
                    Ok(Memory {
                        id: r.get(0)?,
                        category: r.get(1)?,
                        text: r.get(2)?,
                        status: r.get(3)?,
                    })
                },
            )?,
            experiments: self.rows(
                "experiments",
                &[
                    "id",
                    "name",
                    "hypothesis",
                    "metrics",
                    "baseline_days",
                    "start_date",
                    "end_date",
                    "status",
                ],
                "id",
                200,
                |r| {
                    Ok(Experiment {
                        id: r.get(0)?,
                        name: r.get(1)?,
                        hypothesis: r.get(2)?,
                        metrics: r.get(3)?,
                        baseline_days: r.get(4)?,
                        start_date: r.get(5)?,
                        end_date: r.get(6)?,
                        status: r.get(7)?,
                    })
                },
            )?,
        })
    }
}
