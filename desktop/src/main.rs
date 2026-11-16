mod ui;

use eframe::egui;
use garmin_coach_desktop::db_path_from;

fn main() {
    if let Err(error) = run() {
        eprintln!("Garmin Coach: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let path = db_path_from(std::env::args().skip(1), std::env::var("DB_PATH").ok())
        .map_err(|err| err.to_string())?;
    let app = ui::App::open(&path).map_err(|err| err.to_string())?;
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([1100.0, 760.0]),
        ..Default::default()
    };
    eframe::run_native(
        "Garmin Coach • Offline",
        options,
        Box::new(move |_context| Ok(Box::new(app))),
    )
    .map_err(|err| err.to_string())
}
