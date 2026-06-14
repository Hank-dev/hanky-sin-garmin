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


def test_experiment_add_load_roundtrip():
    _fresh_db()
    eid = db.add_experiment({
        "name": "Magnesium", "hypothesis": "better sleep",
        "metrics": ["hrv_overnight_avg", "sleep_hours"],
        "baseline_days": 10, "start_date": "2026-06-01"})
    assert isinstance(eid, int) and eid > 0
    df = db.load_experiments_df()
    assert len(df) == 1
    row = df.iloc[0]
    assert row["name"] == "Magnesium"
    assert row["metrics"] == ["hrv_overnight_avg", "sleep_hours"]   # decoded list
    assert row["baseline_days"] == 10
    assert row["status"] == "active"
    assert row["end_date"] is None
    assert row["created_at"] and row["updated_at"]


def test_experiment_update_and_status_and_delete():
    _fresh_db()
    eid = db.add_experiment({"name": "X", "metrics": ["resting_hr"],
                             "start_date": "2026-06-01"})
    db.update_experiment(eid, {"name": "Y", "metrics": ["stress_avg", "energy"]})
    row = db.load_experiments_df().iloc[0]
    assert row["name"] == "Y"
    assert row["metrics"] == ["stress_avg", "energy"]
    db.set_experiment_status(eid, "complete")
    assert db.load_experiments_df().empty                      # default active-only
    assert db.load_experiments_df(status="complete").iloc[0]["name"] == "Y"
    assert len(db.load_experiments_df(status=None)) == 1
    db.delete_experiment(eid)
    assert len(db.load_experiments_df(status=None)) == 0
