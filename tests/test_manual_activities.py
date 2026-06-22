import importlib

import config
import db


def test_add_manual_activity_generates_manual_id_and_persists(tmp_path, monkeypatch):
    dbfile = tmp_path / "manual-activities.db"
    monkeypatch.setattr(config, "DB_PATH", str(dbfile))
    importlib.reload(db)
    db.config.DB_PATH = str(dbfile)
    db.init_db()

    activity_id = db.add_manual_activity({
        "date": "2026-06-22",
        "name": "Easy run",
        "type": "running",
        "duration_s": 2700,
        "distance_m": 6200,
        "avg_hr": 141,
        "max_hr": 168,
        "training_load": 72,
        "aerobic_te": 2.8,
        "anaerobic_te": None,
    })

    acts = db.load_activities_df()

    assert activity_id.startswith("manual:2026-06-22:")
    assert len(acts) == 1
    row = acts.iloc[0]
    assert row["activity_id"] == activity_id
    assert row["name"] == "Easy run"
    assert row["type"] == "running"
    assert row["duration_s"] == 2700
    assert row["distance_m"] == 6200
