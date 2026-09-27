pub mod store;

use std::path::PathBuf;

pub fn db_path_from(
    args: impl IntoIterator<Item = String>,
    fallback: Option<String>,
) -> store::Result<PathBuf> {
    let mut args = args.into_iter();
    match args.next() {
        Some(flag) if flag == "--db" => {
            let path = args
                .next()
                .filter(|p| !p.is_empty() && !p.starts_with("--"))
                .ok_or("Usage: garmin-coach-desktop --db <existing-sqlite-file>")?;
            if args.next().is_some() {
                return Err("Unexpected extra arguments".into());
            }
            Ok(PathBuf::from(path))
        }
        Some(_) => Err("Usage: garmin-coach-desktop --db <existing-sqlite-file>".into()),
        None => fallback
            .filter(|p| !p.is_empty())
            .map(PathBuf::from)
            .ok_or_else(|| "Set DB_PATH or pass --db <existing-sqlite-file>".into()),
    }
}
