use eframe::egui::{self, Color32, Sense, Ui};
use garmin_coach_desktop::store::{Activity, Checkin, Snapshot, Store, EXPERIMENT_METRICS};
use std::{path::Path, str::FromStr};

type Result<T> = garmin_coach_desktop::store::Result<T>;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Route {
    Cockpit,
    Sleep,
    Activities,
    Strength,
    Coach,
    Lab,
}
impl Route {
    pub const ALL: [Self; 6] = [
        Self::Cockpit,
        Self::Sleep,
        Self::Activities,
        Self::Strength,
        Self::Coach,
        Self::Lab,
    ];
    fn name(self) -> &'static str {
        match self {
            Self::Cockpit => "Cockpit",
            Self::Sleep => "Sleep",
            Self::Activities => "Activities",
            Self::Strength => "Strength",
            Self::Coach => "Coach",
            Self::Lab => "Lab",
        }
    }
}

#[derive(Default)]
pub struct CheckinDraft {
    pub date: String,
    pub pain: String,
    pub fatigue: String,
    pub energy: String,
    pub note: String,
}
#[derive(Default)]
pub struct ActivityDraft {
    pub date: String,
    pub name: String,
    pub kind: String,
    pub duration_min: String,
    pub distance_km: String,
    pub avg_hr: String,
    pub max_hr: String,
    pub load: String,
    pub aerobic_te: String,
    pub anaerobic_te: String,
}
#[derive(Default)]
pub struct SessionDraft {
    pub date: String,
    pub name: String,
}
#[derive(Default)]
pub struct SetDraft {
    pub exercise_id: String,
    pub reps: String,
    pub weight_kg: String,
}
#[derive(Default)]
pub struct MemoryDraft {
    pub category: String,
    pub text: String,
}
#[derive(Default)]
pub struct ExperimentDraft {
    pub name: String,
    pub hypothesis: String,
    pub metrics: String,
    pub start_date: String,
    pub baseline_days: String,
}

#[derive(Clone, Copy)]
pub enum Action {
    Refresh,
    SaveCheckin,
    AddActivity,
    AddSession,
    AddSet,
    AddMemory,
    EditMemory(i64),
    SetMemoryStatus(i64, &'static str),
    DeleteMemory(i64),
    AddExperiment,
    EditExperiment(i64),
    SetExperimentStatus(i64, &'static str),
    DeleteExperiment(i64),
}

pub struct App {
    store: Store,
    pub snapshot: Snapshot,
    pub route: Route,
    pub error: Option<String>,
    pub notice: Option<String>,
    pub checkin: CheckinDraft,
    pub activity: ActivityDraft,
    pub session: SessionDraft,
    pub set: SetDraft,
    pub memory: MemoryDraft,
    pub experiment: ExperimentDraft,
    pub selected_session: String,
    editing_memory: Option<i64>,
    editing_experiment: Option<i64>,
    confirm_memory: Option<i64>,
    confirm_experiment: Option<i64>,
}

fn optional<T: FromStr>(text: &str, label: &str) -> Result<Option<T>> {
    if text.trim().is_empty() {
        return Ok(None);
    }
    text.trim()
        .parse::<T>()
        .map(Some)
        .map_err(|_| format!("{label} must be a valid number").into())
}
fn required<T: FromStr>(text: &str, label: &str) -> Result<T> {
    optional(text, label)?.ok_or_else(|| format!("{label} is required").into())
}
fn metric(value: Option<f64>, decimals: usize) -> String {
    value
        .map(|n| format!("{n:.decimals$}"))
        .unwrap_or_else(|| "—".into())
}

impl App {
    pub fn open(path: &Path) -> Result<Self> {
        let store = Store::open(path)?;
        let snapshot = store.snapshot()?;
        let date = snapshot
            .daily
            .first()
            .map(|d| d.date.clone())
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| chrono::Local::now().format("%Y-%m-%d").to_string());
        let selected_session = snapshot
            .sessions
            .first()
            .map(|s| s.id.clone())
            .unwrap_or_default();
        let exercise_id = snapshot
            .exercises
            .first()
            .map(|e| e.id.clone())
            .unwrap_or_default();
        Ok(Self {
            store,
            snapshot,
            route: Route::Cockpit,
            error: None,
            notice: None,
            checkin: CheckinDraft {
                date: date.clone(),
                ..Default::default()
            },
            activity: ActivityDraft {
                date: date.clone(),
                ..Default::default()
            },
            session: SessionDraft {
                date: date.clone(),
                ..Default::default()
            },
            set: SetDraft {
                exercise_id,
                ..Default::default()
            },
            memory: MemoryDraft {
                category: "goal".into(),
                ..Default::default()
            },
            experiment: ExperimentDraft {
                start_date: date,
                baseline_days: "14".into(),
                ..Default::default()
            },
            selected_session,
            editing_memory: None,
            editing_experiment: None,
            confirm_memory: None,
            confirm_experiment: None,
        })
    }

    pub fn apply(&mut self, action: Action) {
        let refreshed = matches!(action, Action::Refresh);
        let outcome: Result<()> = (|| {
            match action {
                Action::Refresh => (),
                Action::SaveCheckin => {
                    self.store.save_checkin(&Checkin {
                        date: self.checkin.date.trim().to_owned(),
                        pain: optional(&self.checkin.pain, "Pain")?,
                        fatigue: optional(&self.checkin.fatigue, "Fatigue")?,
                        energy: optional(&self.checkin.energy, "Energy")?,
                        note: Some(self.checkin.note.trim().to_owned()).filter(|s| !s.is_empty()),
                    })?;
                }
                Action::AddActivity => {
                    let duration_min: f64 =
                        required(&self.activity.duration_min, "Duration (minutes)")?;
                    let activity = Activity {
                        date: self.activity.date.trim().to_owned(),
                        name: Some(self.activity.name.trim().to_owned()).filter(|s| !s.is_empty()),
                        kind: Some(self.activity.kind.trim().to_owned()),
                        duration_s: Some(duration_min * 60.0),
                        distance_m: optional::<f64>(&self.activity.distance_km, "Distance (km)")?
                            .map(|v| v * 1000.0),
                        avg_hr: optional(&self.activity.avg_hr, "Average HR")?,
                        max_hr: optional(&self.activity.max_hr, "Maximum HR")?,
                        load: optional(&self.activity.load, "Training load")?,
                        aerobic_te: optional(&self.activity.aerobic_te, "Aerobic TE")?,
                        anaerobic_te: optional(&self.activity.anaerobic_te, "Anaerobic TE")?,
                        ..Default::default()
                    };
                    self.store.add_activity(&activity)?;
                }
                Action::AddSession => {
                    self.selected_session = self
                        .store
                        .add_session(&self.session.date, &self.session.name)?;
                }
                Action::AddSet => {
                    let reps: i64 = required(&self.set.reps, "Reps")?;
                    let weight: f64 = required(&self.set.weight_kg, "Weight (kg)")?;
                    self.store.add_set(
                        &self.selected_session,
                        &self.set.exercise_id,
                        reps,
                        weight,
                    )?;
                }
                Action::AddMemory => {
                    self.store
                        .add_memory(&self.memory.category, &self.memory.text)?;
                }
                Action::EditMemory(id) => {
                    self.store.edit_memory(id, &self.memory.text)?;
                    self.editing_memory = None;
                }
                Action::SetMemoryStatus(id, status) => self.store.set_memory_status(id, status)?,
                Action::DeleteMemory(id) => {
                    self.store.delete_memory(id)?;
                    self.confirm_memory = None;
                }
                Action::AddExperiment => {
                    let metrics = self.experiment_metrics();
                    let days = required(&self.experiment.baseline_days, "Baseline days")?;
                    self.store.add_experiment(
                        &self.experiment.name,
                        &self.experiment.hypothesis,
                        &metrics,
                        &self.experiment.start_date,
                        days,
                    )?;
                }
                Action::EditExperiment(id) => {
                    self.store.edit_experiment(
                        id,
                        &self.experiment.name,
                        &self.experiment.hypothesis,
                        &self.experiment_metrics(),
                    )?;
                    self.editing_experiment = None;
                }
                Action::SetExperimentStatus(id, status) => {
                    self.store.set_experiment_status(id, status)?
                }
                Action::DeleteExperiment(id) => {
                    self.store.delete_experiment(id)?;
                    self.confirm_experiment = None;
                }
            }
            self.snapshot = self.store.snapshot()?;
            Ok(())
        })();
        match outcome {
            Ok(()) => {
                self.error = None;
                self.notice = Some(
                    if refreshed {
                        "Database refreshed"
                    } else {
                        "Saved; local snapshot refreshed"
                    }
                    .into(),
                );
            }
            Err(err) => {
                self.error = Some(err.to_string());
                self.notice = None;
            }
        }
    }

    fn experiment_metrics(&self) -> Vec<String> {
        self.experiment
            .metrics
            .split(',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_owned)
            .collect()
    }

    pub fn show(&mut self, ctx: &egui::Context) {
        let mut action = None;
        egui::SidePanel::left("navigation")
            .default_width(160.0)
            .show(ctx, |ui| {
                ui.heading("Garmin Coach");
                ui.label("Offline desktop");
                ui.separator();
                for route in Route::ALL {
                    if ui
                        .selectable_label(self.route == route, route.name())
                        .clicked()
                    {
                        self.route = route;
                        self.error = None;
                    }
                }
                ui.separator();
                if ui.button("Refresh database").clicked() {
                    action = Some(Action::Refresh);
                }
                ui.small("SQLite only • no network calls");
            });
        egui::CentralPanel::default().show(ctx, |ui| {
            egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
                if let Some(error) = &self.error { ui.colored_label(Color32::LIGHT_RED, format!("Error: {error}")); }
                if let Some(notice) = &self.notice { ui.colored_label(Color32::LIGHT_GREEN, notice); }
                match self.route {
                    Route::Cockpit => self.cockpit(ui, &mut action),
                    Route::Sleep => self.sleep(ui),
                    Route::Activities => self.activities(ui, &mut action),
                    Route::Strength => self.strength(ui, &mut action),
                    Route::Coach => self.coach(ui, &mut action),
                    Route::Lab => self.lab(ui, &mut action),
                }
                ui.separator();
                ui.small("Snapshot display, not a medical assessment. Advanced analytics, AI, Garmin sync and imports are not available in this native client.");
            });
        });
        if let Some(action) = action {
            self.apply(action);
        }
    }

    fn cockpit(&mut self, ui: &mut Ui, action: &mut Option<Action>) {
        ui.heading("Cockpit — Today");
        if let Some(day) = self.snapshot.daily.first() {
            ui.label(format!("Latest recorded date: {}", day.date));
            ui.horizontal_wrapped(|ui| {
                for (name, value, unit) in [
                    ("Readiness (Garmin)", day.readiness, ""),
                    ("Resting HR", day.resting_hr, " bpm"),
                    ("HRV", day.hrv, " ms"),
                    ("Sleep", day.sleep_hours(), " h"),
                    ("Body Battery", day.battery, ""),
                    ("Stress", day.stress, ""),
                    ("Steps", day.steps, ""),
                ] {
                    ui.group(|ui| {
                        ui.label(name);
                        ui.strong(format!(
                            "{}{}",
                            metric(value, if name == "Sleep" { 1 } else { 0 }),
                            unit
                        ));
                    });
                }
            });
            ui.small("Recorded Garmin values only; missing readings remain blank. No inferred readiness or recovery verdict.");
        } else {
            ui.label("No daily metrics yet. Nothing to score.");
        }
        ui.separator();
        ui.heading("Daily check-in");
        for row in &self.snapshot.checkins {
            ui.label(format!(
                "{} • pain {} • fatigue {} • energy {} • {}",
                row.date,
                row.pain.map_or("—".into(), |v| v.to_string()),
                row.fatigue.map_or("—".into(), |v| v.to_string()),
                row.energy.map_or("—".into(), |v| v.to_string()),
                row.note.as_deref().unwrap_or("")
            ));
        }
        ui.label("Date (YYYY-MM-DD)");
        ui.text_edit_singleline(&mut self.checkin.date);
        ui.horizontal(|ui| {
            for (label, field) in [
                ("Pain 1–10", &mut self.checkin.pain),
                ("Fatigue 1–10", &mut self.checkin.fatigue),
                ("Energy 1–10", &mut self.checkin.energy),
            ] {
                ui.vertical(|ui| {
                    ui.label(label);
                    ui.add(egui::TextEdit::singleline(field).desired_width(85.0));
                });
            }
        });
        ui.label("Note");
        ui.text_edit_multiline(&mut self.checkin.note);
        if ui.button("Save check-in").clicked() {
            *action = Some(Action::SaveCheckin);
        }
    }

    fn sleep(&mut self, ui: &mut Ui) {
        ui.heading("Sleep — Nights");
        let nights: Vec<_> = self
            .snapshot
            .daily
            .iter()
            .filter(|d| d.sleep_seconds.is_some() || d.sleep_score.is_some())
            .collect();
        if nights.is_empty() {
            ui.label("No sleep measurements recorded.");
            return;
        }
        ui.label("Recorded sleep score by date (latest 30 nights; blank dates omitted)");
        let scored: Vec<_> = nights
            .iter()
            .take(30)
            .rev()
            .filter_map(|d| d.sleep_score.map(|s| (d.date.as_str(), s)))
            .collect();
        if scored.is_empty() {
            ui.label("No sleep scores available for a chart.");
        } else {
            let (rect, _) = ui.allocate_exact_size(
                egui::vec2(ui.available_width().max(120.0), 150.0),
                Sense::hover(),
            );
            let painter = ui.painter_at(rect);
            let width = rect.width() / scored.len() as f32;
            for (i, (_, score)) in scored.iter().enumerate() {
                let fraction = (*score / 100.0).clamp(0.0, 1.0) as f32;
                let x = rect.left() + width * i as f32;
                painter.rect_filled(
                    egui::Rect::from_min_max(
                        egui::pos2(x + 2.0, rect.bottom() - rect.height() * fraction),
                        egui::pos2(x + width - 2.0, rect.bottom()),
                    ),
                    2.0,
                    Color32::from_rgb(70, 145, 195),
                );
            }
            ui.small(format!(
                "{} → {} • chart scale 0–100",
                scored.first().unwrap().0,
                scored.last().unwrap().0
            ));
        }
        ui.separator();
        for day in nights.iter().take(30) {
            ui.group(|ui| {
                ui.strong(format!(
                    "{}  •  {} h  •  score {}",
                    day.date,
                    metric(day.sleep_hours(), 1),
                    metric(day.sleep_score, 0)
                ));
                ui.label(format!(
                    "Deep {} h  |  REM {} h  |  Light {} h",
                    metric(day.deep_seconds.map(|v| v / 3600.0), 1),
                    metric(day.rem_seconds.map(|v| v / 3600.0), 1),
                    metric(day.light_seconds.map(|v| v / 3600.0), 1)
                ));
            });
        }
        ui.small("Sleep predictions, learned need, early-waking inference and AI coaching are not implemented.");
    }

    fn activities(&mut self, ui: &mut Ui, action: &mut Option<Action>) {
        ui.heading("Activities — Log");
        if self.snapshot.activities.is_empty() {
            ui.label("No activities recorded.");
        }
        for entry in &self.snapshot.activities {
            ui.group(|ui| {
                ui.strong(format!(
                    "{} • {}",
                    entry.date,
                    entry.name.as_deref().unwrap_or("Unnamed activity")
                ));
                ui.label(format!(
                    "{} • {} min • {} km • avg HR {} • load {}",
                    entry.kind.as_deref().unwrap_or("unknown"),
                    metric(entry.duration_s.map(|v| v / 60.0), 0),
                    metric(entry.distance_m.map(|v| v / 1000.0), 2),
                    metric(entry.avg_hr, 0),
                    metric(entry.load, 0)
                ));
                ui.small(format!("ID: {}", entry.id));
            });
        }
        ui.separator();
        ui.heading("Manual activity");
        ui.label("Date (YYYY-MM-DD)");
        ui.text_edit_singleline(&mut self.activity.date);
        ui.label("Type (required, e.g. running, bjj, strength)");
        ui.text_edit_singleline(&mut self.activity.kind);
        ui.label("Name");
        ui.text_edit_singleline(&mut self.activity.name);
        ui.horizontal_wrapped(|ui| {
            for (label, field) in [
                ("Duration (minutes)", &mut self.activity.duration_min),
                ("Distance (km)", &mut self.activity.distance_km),
                ("Average HR", &mut self.activity.avg_hr),
                ("Maximum HR", &mut self.activity.max_hr),
                ("Training load", &mut self.activity.load),
                ("Aerobic TE", &mut self.activity.aerobic_te),
                ("Anaerobic TE", &mut self.activity.anaerobic_te),
            ] {
                ui.vertical(|ui| {
                    ui.label(label);
                    ui.add(egui::TextEdit::singleline(field).desired_width(100.0));
                });
            }
        });
        if ui.button("Add activity").clicked() {
            *action = Some(Action::AddActivity);
        }
        ui.small("Manual entries are local; grappling analysis and Garmin data sync are not implemented.");
    }

    fn strength(&mut self, ui: &mut Ui, action: &mut Option<Action>) {
        ui.heading("Strength — Sessions");
        if self.snapshot.sessions.is_empty() {
            ui.label("No strength sessions recorded.");
        }
        for session in &self.snapshot.sessions {
            ui.group(|ui| {
                ui.strong(format!(
                    "{} • {}",
                    session.date,
                    session.name.as_deref().unwrap_or("Unnamed session")
                ));
                ui.small(format!(
                    "Source: {}",
                    session.source.as_deref().unwrap_or("unknown")
                ));
                for set in self
                    .snapshot
                    .sets
                    .iter()
                    .filter(|set| set.session_id == session.id)
                {
                    let exercise = self
                        .snapshot
                        .exercises
                        .iter()
                        .find(|ex| ex.id == set.exercise)
                        .map_or(set.exercise.as_str(), |ex| ex.name.as_str());
                    ui.label(format!(
                        "{} • {} reps × {} kg{}",
                        exercise,
                        set.reps.map_or("—".into(), |n| n.to_string()),
                        metric(set.weight_kg, 1),
                        if set.warmup { " (warm-up)" } else { "" }
                    ));
                }
            });
        }
        ui.separator();
        ui.heading("Add local session");
        ui.label("Date (YYYY-MM-DD)");
        ui.text_edit_singleline(&mut self.session.date);
        ui.label("Name");
        ui.text_edit_singleline(&mut self.session.name);
        if ui.button("Add session").clicked() {
            *action = Some(Action::AddSession);
        }
        ui.separator();
        ui.heading("Add set to existing session");
        egui::ComboBox::from_id_salt("session-select")
            .selected_text(
                self.snapshot
                    .sessions
                    .iter()
                    .find(|s| s.id == self.selected_session)
                    .and_then(|s| s.name.as_deref())
                    .unwrap_or("Select session"),
            )
            .show_ui(ui, |ui| {
                for session in &self.snapshot.sessions {
                    ui.selectable_value(
                        &mut self.selected_session,
                        session.id.clone(),
                        format!(
                            "{} • {}",
                            session.date,
                            session.name.as_deref().unwrap_or("Unnamed")
                        ),
                    );
                }
            });
        egui::ComboBox::from_id_salt("exercise-select")
            .selected_text(
                self.snapshot
                    .exercises
                    .iter()
                    .find(|e| e.id == self.set.exercise_id)
                    .map_or("Select exercise", |e| e.name.as_str()),
            )
            .show_ui(ui, |ui| {
                for exercise in &self.snapshot.exercises {
                    ui.selectable_value(
                        &mut self.set.exercise_id,
                        exercise.id.clone(),
                        &exercise.name,
                    );
                }
            });
        ui.horizontal(|ui| {
            ui.label("Reps");
            ui.add(egui::TextEdit::singleline(&mut self.set.reps).desired_width(70.0));
            ui.label("Weight kg");
            ui.add(egui::TextEdit::singleline(&mut self.set.weight_kg).desired_width(70.0));
        });
        if ui
            .add_enabled(
                !self.selected_session.is_empty() && !self.set.exercise_id.is_empty(),
                egui::Button::new("Add set"),
            )
            .clicked()
        {
            *action = Some(Action::AddSet);
        }
        if self.snapshot.exercises.is_empty() {
            ui.small("No exercises catalogued; add-set requires an existing exercise ID in the database.");
        }
        ui.small("Imported strength is shown as stored. PRs, 1RM, trends, bodyweight and import tools are not implemented.");
    }

    fn coach(&mut self, ui: &mut Ui, action: &mut Option<Action>) {
        ui.heading("Coach — Memories");
        ui.small("Local memories only. AI chat, session planning and lifestyle-context parsing are not implemented.");
        if self.snapshot.memories.is_empty() {
            ui.label("No saved memories.");
        }
        for entry in &self.snapshot.memories {
            ui.group(|ui| {
                ui.strong(format!("{} • {}", entry.category, entry.status));
                ui.label(&entry.text);
                ui.horizontal_wrapped(|ui| {
                    if ui.button(format!("Edit##{}", entry.id)).clicked() {
                        self.editing_memory = Some(entry.id);
                        self.memory.category = entry.category.clone();
                        self.memory.text = entry.text.clone();
                    }
                    if ui
                        .button(if entry.status == "active" {
                            "Archive"
                        } else {
                            "Restore"
                        })
                        .clicked()
                    {
                        *action = Some(Action::SetMemoryStatus(
                            entry.id,
                            if entry.status == "active" {
                                "archived"
                            } else {
                                "active"
                            },
                        ));
                    }
                    if self.confirm_memory == Some(entry.id) {
                        if ui.button("Confirm delete").clicked() {
                            *action = Some(Action::DeleteMemory(entry.id));
                        }
                        if ui.button("Cancel").clicked() {
                            self.confirm_memory = None;
                        }
                    } else if ui.button("Delete…").clicked() {
                        self.confirm_memory = Some(entry.id);
                    }
                });
            });
        }
        ui.separator();
        ui.heading(if self.editing_memory.is_some() {
            "Edit memory"
        } else {
            "New memory"
        });
        ui.label("Category (new memories)");
        ui.text_edit_singleline(&mut self.memory.category);
        ui.label("Text");
        ui.text_edit_multiline(&mut self.memory.text);
        if ui
            .button(if self.editing_memory.is_some() {
                "Save edit"
            } else {
                "Add memory"
            })
            .clicked()
        {
            *action = Some(
                self.editing_memory
                    .map_or(Action::AddMemory, Action::EditMemory),
            );
        }
        if self.editing_memory.is_some() && ui.button("Cancel edit").clicked() {
            self.editing_memory = None;
        }
    }

    fn lab(&mut self, ui: &mut Ui, action: &mut Option<Action>) {
        ui.heading("Lab — Experiments");
        ui.small("Experiment records only. No inferred effects, correlations, recovery model or AI interpretation.");
        if self.snapshot.experiments.is_empty() {
            ui.label("No experiments recorded.");
        }
        for entry in &self.snapshot.experiments {
            ui.group(|ui| {
                ui.strong(format!("{} • {}", entry.name, entry.status));
                ui.label(format!(
                    "{} • baseline {} days • metrics {}",
                    entry.start_date,
                    entry.baseline_days,
                    serde_json::from_str::<Vec<String>>(&entry.metrics)
                        .map(|v| v.join(", "))
                        .unwrap_or_else(|_| entry.metrics.clone())
                ));
                if let Some(hypothesis) = &entry.hypothesis {
                    ui.label(format!("Hypothesis: {hypothesis}"));
                }
                ui.horizontal_wrapped(|ui| {
                    if ui.button(format!("Edit##{}", entry.id)).clicked() {
                        self.editing_experiment = Some(entry.id);
                        self.experiment.name = entry.name.clone();
                        self.experiment.hypothesis = entry.hypothesis.clone().unwrap_or_default();
                        self.experiment.metrics =
                            serde_json::from_str::<Vec<String>>(&entry.metrics)
                                .map(|v| v.join(", "))
                                .unwrap_or_else(|_| entry.metrics.clone());
                        self.experiment.start_date = entry.start_date.clone();
                        self.experiment.baseline_days = entry.baseline_days.to_string();
                    }
                    if ui
                        .button(if entry.status == "active" {
                            "Mark complete"
                        } else {
                            "Reactivate"
                        })
                        .clicked()
                    {
                        *action = Some(Action::SetExperimentStatus(
                            entry.id,
                            if entry.status == "active" {
                                "complete"
                            } else {
                                "active"
                            },
                        ));
                    }
                    if self.confirm_experiment == Some(entry.id) {
                        if ui.button("Confirm delete").clicked() {
                            *action = Some(Action::DeleteExperiment(entry.id));
                        }
                        if ui.button("Cancel").clicked() {
                            self.confirm_experiment = None;
                        }
                    } else if ui.button("Delete…").clicked() {
                        self.confirm_experiment = Some(entry.id);
                    }
                });
            });
        }
        ui.separator();
        ui.heading(if self.editing_experiment.is_some() {
            "Edit experiment"
        } else {
            "New experiment"
        });
        ui.label("Name");
        ui.text_edit_singleline(&mut self.experiment.name);
        ui.label("Hypothesis");
        ui.text_edit_singleline(&mut self.experiment.hypothesis);
        ui.label("Metrics (comma-separated keys from the supported list)");
        ui.small(format!("Supported: {}", EXPERIMENT_METRICS.join(", ")));
        ui.text_edit_singleline(&mut self.experiment.metrics);
        if self.editing_experiment.is_none() {
            ui.label("Start date (YYYY-MM-DD)");
            ui.text_edit_singleline(&mut self.experiment.start_date);
            ui.label("Baseline days (3–90)");
            ui.text_edit_singleline(&mut self.experiment.baseline_days);
        }
        if ui
            .button(if self.editing_experiment.is_some() {
                "Save edit"
            } else {
                "Add experiment"
            })
            .clicked()
        {
            *action = Some(
                self.editing_experiment
                    .map_or(Action::AddExperiment, Action::EditExperiment),
            );
        }
        if self.editing_experiment.is_some() && ui.button("Cancel edit").clicked() {
            self.editing_experiment = None;
        }
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.show(ctx);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;
    use std::path::PathBuf;

    fn fixture() -> (tempfile::TempDir, PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("synthetic.sqlite");
        Connection::open(&path).unwrap().execute_batch(
            "CREATE TABLE daily_metrics (date TEXT PRIMARY KEY, resting_hr REAL, hrv_overnight_avg REAL, sleep_seconds REAL, sleep_score REAL, deep_seconds REAL, rem_seconds REAL, light_seconds REAL, body_battery_start REAL, stress_avg REAL, steps REAL, training_readiness_score REAL);
             CREATE TABLE activities (activity_id TEXT PRIMARY KEY, date TEXT, name TEXT, type TEXT, duration_s REAL, distance_m REAL, avg_hr REAL, training_load REAL, max_hr REAL, aerobic_te REAL, anaerobic_te REAL);
             CREATE TABLE daily_checkins (date TEXT PRIMARY KEY, pain INTEGER, fatigue INTEGER, energy INTEGER, note TEXT, updated_at TEXT);
             CREATE TABLE exercises (exercise_id TEXT PRIMARY KEY, name TEXT);
             CREATE TABLE strength_sessions (session_id TEXT PRIMARY KEY, date TEXT, name TEXT, source TEXT, notes TEXT);
             CREATE TABLE strength_sets (set_id TEXT PRIMARY KEY, session_id TEXT, exercise_id TEXT, position INTEGER, set_index INTEGER, side TEXT, reps INTEGER, weight_kg REAL, rpe REAL, is_warmup INTEGER, completed INTEGER);
             CREATE TABLE coach_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
             CREATE TABLE experiments (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, hypothesis TEXT, metrics TEXT NOT NULL, baseline_days INTEGER NOT NULL, start_date TEXT NOT NULL, end_date TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
             INSERT INTO daily_metrics (date, resting_hr, sleep_seconds, sleep_score, deep_seconds, rem_seconds, light_seconds, training_readiness_score) VALUES ('2026-09-26', 52, 28800, 82, 7200, 5400, 16200, 73);
             INSERT INTO activities (activity_id, date, name, type, duration_s) VALUES ('sample-activity', '2026-09-26', 'Trail run', 'running', 3600);
             INSERT INTO exercises (exercise_id, name) VALUES ('squat', 'Squat');
             INSERT INTO strength_sessions (session_id, date, name, source) VALUES ('sample-session', '2026-09-26', 'Lower body', 'imported');
             INSERT INTO strength_sets (set_id, session_id, exercise_id, reps, weight_kg) VALUES ('sample-set', 'sample-session', 'squat', 5, 80);
             INSERT INTO coach_memory (category, text, status, source, created_at, updated_at) VALUES ('goal', 'Keep it easy', 'active', 'user', '2026-09-26', '2026-09-26');
             INSERT INTO experiments (name, hypothesis, metrics, baseline_days, start_date, status, created_at, updated_at) VALUES ('Bedtime routine', 'more rest', '[\"sleep_score\"]', 14, '2026-09-26', 'active', '2026-09-26', '2026-09-26');"
        ).unwrap();
        (dir, path)
    }

    #[test]
    fn each_native_route_renders_its_own_snapshot_data() {
        let (_dir, path) = fixture();
        let mut app = App::open(&path).unwrap();
        let cases = [
            (Route::Cockpit, "Cockpit — Today", "73"),
            (Route::Sleep, "Sleep — Nights", "8.0"),
            (Route::Activities, "Activities — Log", "Trail run"),
            (Route::Strength, "Strength — Sessions", "Lower body"),
            (Route::Coach, "Coach — Memories", "Keep it easy"),
            (Route::Lab, "Lab — Experiments", "Bedtime routine"),
        ];
        assert_eq!(Route::ALL.len(), cases.len());
        let ctx = egui::Context::default();
        for (route, title, data) in cases {
            app.route = route;
            let output = ctx.run(egui::RawInput::default(), |ctx| app.show(ctx));
            let text = output
                .shapes
                .iter()
                .filter_map(|shape| match &shape.shape {
                    egui::Shape::Text(t) => Some(t.galley.text().to_owned()),
                    _ => None,
                })
                .collect::<Vec<_>>()
                .join(" ");
            assert!(text.contains(title), "{route:?} title absent: {text}");
            assert!(text.contains(data), "{route:?} fixture data absent: {text}");
        }
    }

    #[test]
    fn successful_actions_refresh_the_snapshot_and_reject_invalid_input() {
        let (_dir, path) = fixture();
        let mut app = App::open(&path).unwrap();
        app.checkin.date = "2026-09-26".into();
        app.checkin.pain = "3".into();
        app.checkin.energy = "7".into();
        app.apply(Action::SaveCheckin);
        assert_eq!(app.snapshot.checkins[0].energy, Some(7));
        app.activity.date = "2026-09-26".into();
        app.activity.kind = "running".into();
        app.activity.name = "New manual run".into();
        app.activity.duration_min = "0".into();
        app.apply(Action::AddActivity);
        assert!(app.error.is_some());
        assert_eq!(app.snapshot.activities.len(), 1);
        app.activity.duration_min = "25".into();
        app.apply(Action::AddActivity);
        assert!(app.error.is_none(), "{:?}", app.error);
        assert_eq!(app.snapshot.activities.len(), 2);
        assert_eq!(
            app.snapshot
                .activities
                .iter()
                .find(|a| a.name.as_deref() == Some("New manual run"))
                .unwrap()
                .duration_s,
            Some(1500.0)
        );
        app.memory.category = "goal".into();
        app.memory.text = "Get stronger".into();
        app.apply(Action::AddMemory);
        assert_eq!(app.snapshot.memories.len(), 2);
        app.experiment.name = "Recovery trial".into();
        app.experiment.metrics = "sleep_score".into();
        app.experiment.start_date = "2026-09-26".into();
        app.experiment.baseline_days = "14".into();
        app.apply(Action::AddExperiment);
        assert_eq!(app.snapshot.experiments.len(), 2);
        let reopened = App::open(&path).unwrap();
        assert_eq!(reopened.snapshot.activities.len(), 2);
        assert_eq!(reopened.snapshot.experiments.len(), 2);
        assert_eq!(reopened.snapshot.checkins[0].pain, Some(3));
    }

    #[test]
    fn activity_optional_hr_and_training_effect_fields_roundtrip_and_validate() {
        let (_dir, path) = fixture();
        let mut app = App::open(&path).unwrap();
        app.activity.date = "2026-09-27".into();
        app.activity.kind = "cycling".into();
        app.activity.name = "Indoor ride".into();
        app.activity.duration_min = "30".into();
        app.activity.avg_hr = "180".into();
        app.activity.max_hr = "170".into();
        app.apply(Action::AddActivity);
        assert!(app.error.is_some());
        assert_eq!(app.snapshot.activities.len(), 1);
        app.activity.avg_hr = "140".into();
        app.activity.aerobic_te = "2.4".into();
        app.activity.anaerobic_te = "0.6".into();
        app.apply(Action::AddActivity);
        assert!(app.error.is_none(), "{:?}", app.error);
        let entry = app
            .snapshot
            .activities
            .iter()
            .find(|a| a.name.as_deref() == Some("Indoor ride"))
            .unwrap();
        assert_eq!(
            (entry.max_hr, entry.aerobic_te, entry.anaerobic_te),
            (Some(170.0), Some(2.4), Some(0.6))
        );
        let reopened = App::open(&path).unwrap();
        assert_eq!(reopened.snapshot.activities.len(), 2);
    }

    #[test]
    fn refresh_reloads_external_changes_without_claiming_to_save() {
        let (_dir, path) = fixture();
        let mut app = App::open(&path).unwrap();
        Connection::open(&path)
            .unwrap()
            .execute(
                "INSERT INTO daily_metrics (date, sleep_score) VALUES ('2026-09-27', 91)",
                [],
            )
            .unwrap();
        app.apply(Action::Refresh);
        assert_eq!(app.snapshot.daily[0].sleep_score, Some(91.0));
        assert_eq!(app.notice.as_deref(), Some("Database refreshed"));
    }

    #[test]
    fn lab_form_names_supported_metric_keys() {
        let (_dir, path) = fixture();
        let mut app = App::open(&path).unwrap();
        app.route = Route::Lab;
        let output = egui::Context::default().run(egui::RawInput::default(), |ctx| app.show(ctx));
        let text = output
            .shapes
            .iter()
            .filter_map(|shape| match &shape.shape {
                egui::Shape::Text(t) => Some(t.galley.text().to_owned()),
                _ => None,
            })
            .collect::<Vec<_>>()
            .join(" ");
        assert!(
            text.contains("sleep_hours"),
            "Metric choices absent: {text}"
        );
        assert!(
            text.contains("hrv_overnight_avg"),
            "Metric choices absent: {text}"
        );
    }

    #[test]
    fn strength_and_crud_actions_use_store_and_refresh() {
        let (_dir, path) = fixture();
        let mut app = App::open(&path).unwrap();
        app.session.date = "2026-09-27".into();
        app.session.name = "Manual lower".into();
        app.apply(Action::AddSession);
        assert_eq!(app.snapshot.sessions.len(), 2);
        assert!(app.selected_session.starts_with("manual:"));
        app.set.exercise_id = "squat".into();
        app.set.reps = "6".into();
        app.set.weight_kg = "90".into();
        app.apply(Action::AddSet);
        assert_eq!(app.snapshot.sets.len(), 2);
        let memory_id = app.snapshot.memories[0].id;
        app.memory.text = "Updated".into();
        app.apply(Action::EditMemory(memory_id));
        assert_eq!(app.snapshot.memories[0].text, "Updated");
        app.apply(Action::SetMemoryStatus(memory_id, "archived"));
        assert_eq!(app.snapshot.memories[0].status, "archived");
        app.apply(Action::DeleteMemory(memory_id));
        assert_eq!(app.snapshot.memories.len(), 0);
        let experiment_id = app.snapshot.experiments[0].id;
        app.experiment.name = "Updated trial".into();
        app.experiment.metrics = "stress_avg".into();
        app.apply(Action::EditExperiment(experiment_id));
        assert_eq!(app.snapshot.experiments[0].name, "Updated trial");
        app.apply(Action::SetExperimentStatus(experiment_id, "complete"));
        assert_eq!(app.snapshot.experiments[0].status, "complete");
        app.apply(Action::DeleteExperiment(experiment_id));
        assert!(app.snapshot.experiments.is_empty());
    }
}
