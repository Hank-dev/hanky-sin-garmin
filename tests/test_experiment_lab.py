import importlib
import tempfile

import pandas as pd

import config
import db
import analysis
import ai
import cockpit


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


def test_experiment_metric_catalog_shapes():
    keys = {m["key"] for m in analysis.EXPERIMENT_METRICS}
    assert {"hrv_overnight_avg", "resting_hr", "sleep_hours", "energy",
            "pain"} <= keys
    by_key = analysis._EXPERIMENT_METRIC_BY_KEY
    assert by_key["resting_hr"]["polarity"] == "lower"
    assert by_key["hrv_overnight_avg"]["polarity"] == "higher"
    assert by_key["energy"]["source"] == "checkin"


def test_t_critical_975():
    assert abs(analysis._t_critical_975(1) - 12.706) < 1e-6
    assert abs(analysis._t_critical_975(10) - 2.228) < 1e-6
    assert abs(analysis._t_critical_975(35) - 2.042) < 1e-6   # nearest <= 35 is 30
    assert abs(analysis._t_critical_975(500) - 1.960) < 1e-6
    assert abs(analysis._t_critical_975(float("nan")) - 1.960) < 1e-6


def _daily_for_experiment():
    # 2026-05-18..2026-06-14. Baseline (14d before 06-01) = 05-18..05-31,
    # intervention = 06-01..06-14. RHR drops 60 -> 52 (improvement, lower=better).
    dates = pd.date_range("2026-05-18", "2026-06-14", freq="D")
    rows = []
    for d in dates:
        intervention = d >= pd.Timestamp("2026-06-01")
        rows.append({
            "date": d,
            "resting_hr": 52.0 if intervention else 60.0,
            "hrv_overnight_avg": 70.0 if intervention else 60.0,
            "sleep_hours": 7.5,
        })
    return pd.DataFrame(rows)


def test_compute_result_windows_and_verdicts():
    daily = _daily_for_experiment()
    exp = {"id": 1, "name": "Mag", "status": "active",
           "metrics": ["resting_hr", "hrv_overnight_avg", "sleep_hours"],
           "baseline_days": 14, "start_date": "2026-06-01", "end_date": None}
    res = analysis.compute_experiment_result(exp, daily, checkins=None)
    assert res["baseline_window"] == ["2026-05-18", "2026-05-31"]
    assert res["intervention_window"] == ["2026-06-01", "2026-06-14"]
    rhr = res["metrics"]["resting_hr"]
    assert rhr["mean_before"] == 60.0 and rhr["mean_after"] == 52.0
    assert rhr["verdict"] == "likely helped"          # RHR down, lower is better
    hrv = res["metrics"]["hrv_overnight_avg"]
    assert hrv["verdict"] == "likely helped"          # HRV up, higher is better
    sleep = res["metrics"]["sleep_hours"]
    assert sleep["verdict"] == "no clear effect"      # identical both windows


def test_compute_result_insufficient_data():
    daily = _daily_for_experiment()
    exp = {"id": 2, "name": "Short", "status": "active",
           "metrics": ["resting_hr"], "baseline_days": 2,
           "start_date": "2026-06-01", "end_date": "2026-06-03"}
    res = analysis.compute_experiment_result(exp, daily, checkins=None)
    assert res["metrics"]["resting_hr"]["verdict"] == "insufficient_data"
    assert res["notes"]


def test_compute_result_checkin_metric():
    daily = _daily_for_experiment()
    cdates = pd.date_range("2026-05-18", "2026-06-14", freq="D")
    checkins = pd.DataFrame([
        {"date": d, "energy": (4 if d >= pd.Timestamp("2026-06-01") else 2)}
        for d in cdates])
    exp = {"id": 3, "name": "E", "status": "active", "metrics": ["energy"],
           "baseline_days": 14, "start_date": "2026-06-01", "end_date": None}
    res = analysis.compute_experiment_result(exp, daily, checkins=checkins)
    assert res["metrics"]["energy"]["verdict"] == "likely helped"


def test_compute_result_checkin_metric_uses_checkin_latest_date():
    daily = pd.DataFrame([{"date": pd.Timestamp("2026-05-31"),
                           "resting_hr": 60.0}])
    cdates = pd.date_range("2026-05-27", "2026-06-07", freq="D")
    checkins = pd.DataFrame([
        {"date": d, "energy": (4 if d >= pd.Timestamp("2026-06-01") else 2)}
        for d in cdates])
    exp = {"id": 4, "name": "E", "status": "active", "metrics": ["energy"],
           "baseline_days": 5, "start_date": "2026-06-01", "end_date": None}
    res = analysis.compute_experiment_result(exp, daily, checkins=checkins)
    assert res["intervention_window"] == ["2026-06-01", "2026-06-07"]
    assert res["metrics"]["energy"]["n_after"] == 7
    assert res["metrics"]["energy"]["verdict"] == "likely helped"


def test_verdict_ci_straddles_zero_and_directions():
    # se>0 path: CI crosses zero -> no clear effect
    assert analysis._experiment_verdict(1.0, -0.5, 2.5, "higher") == "no clear effect"
    # narrow CI above zero, higher-better -> likely helped
    assert analysis._experiment_verdict(1.0, 0.1, 1.9, "higher") == "likely helped"
    # CI below zero, lower-better -> likely helped (metric went down, good)
    assert analysis._experiment_verdict(-2.0, -3.5, -0.5, "lower") == "likely helped"
    # CI above zero, lower-better -> likely hurt (metric went up, bad)
    assert analysis._experiment_verdict(2.0, 0.5, 3.5, "lower") == "likely hurt"


def test_compute_result_daily_none():
    exp = {"id": 9, "name": "None daily", "metrics": ["resting_hr"],
           "baseline_days": 14, "start_date": "2026-06-01", "end_date": None}
    res = analysis.compute_experiment_result(exp, daily=None)
    assert res["metrics"]["resting_hr"]["verdict"] == "insufficient_data"


def test_compute_result_malformed_end_date_treated_as_ongoing():
    daily = _daily_for_experiment()
    exp = {"id": 7, "name": "Bad end", "status": "active",
           "metrics": ["resting_hr"], "baseline_days": 14,
           "start_date": "2026-06-01", "end_date": "ongoing"}
    res = analysis.compute_experiment_result(exp, daily, checkins=None)
    assert res["intervention_window"] == ["2026-06-01", "2026-06-14"]
    assert res["metrics"]["resting_hr"]["verdict"] == "likely helped"


def test_summarize_active_experiments():
    daily = _daily_for_experiment()   # latest date 2026-06-14
    df = pd.DataFrame([
        {"name": "Mag", "hypothesis": "better sleep", "status": "active",
         "metrics": ["hrv_overnight_avg", "sleep_hours"], "start_date": "2026-06-01"},
        {"name": "Done", "hypothesis": None, "status": "complete",
         "metrics": ["resting_hr"], "start_date": "2026-05-01"},
    ])
    out = analysis.summarize_active_experiments(df, daily)
    assert len(out) == 1
    a = out[0]
    assert a["name"] == "Mag"
    assert a["metrics"] == ["HRV (overnight avg)", "Sleep (hours)"]
    assert a["days_running"] == 13      # 06-01 -> 06-14
    assert a["hypothesis"] == "better sleep"


def test_summarize_active_experiments_empty():
    assert analysis.summarize_active_experiments(pd.DataFrame(), pd.DataFrame()) == []


# ---------------------------------------------------------------------------
# Task 5 – ai._experiment_block, active_experiments threading, interpret_experiment
# ---------------------------------------------------------------------------

def test_experiment_block_empty_and_full():
    assert ai._experiment_block(None) == ""
    assert ai._experiment_block([]) == ""
    block = ai._experiment_block([{"name": "Mag", "days_running": 5}])
    assert block.startswith("\n\nActive experiments")
    assert "Mag" in block


def test_question_payload_includes_active_experiments():
    payload = ai._question_payload(
        "q", {"a": 1}, None, None, None, None, None,
        active_experiments=[{"name": "Mag"}])
    assert payload["active_experiments"] == [{"name": "Mag"}]


def test_question_payload_defaults_active_experiments_empty():
    payload = ai._question_payload("q", {}, None, None, None, None, None)
    assert payload["active_experiments"] == []


def test_interpret_experiment_without_key(monkeypatch):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "")
    out = ai.interpret_experiment({"name": "Mag", "metrics": {}})
    assert "ANTHROPIC_API_KEY" in out


def test_experiment_card_renders_verdicts_and_escapes():
    result = {
        "name": "Mag <b>", "baseline_window": ["2026-05-18", "2026-05-31"],
        "intervention_window": ["2026-06-01", "2026-06-14"],
        "metrics": {
            "resting_hr": {"label": "Resting HR", "polarity": "lower",
                           "n_before": 14, "n_after": 14, "mean_before": 60.0,
                           "mean_after": 52.0, "delta": -8.0, "ci_low": -10.0,
                           "ci_high": -6.0, "verdict": "likely helped"},
            "sleep_hours": {"label": "Sleep (hours)", "polarity": "higher",
                            "n_before": 2, "n_after": 2, "mean_before": None,
                            "mean_after": None, "delta": None, "ci_low": None,
                            "ci_high": None, "verdict": "insufficient_data"},
        },
        "notes": ["Sleep (hours): not enough data"],
    }
    out = cockpit.experiment_result_card(result)
    assert "Mag &lt;b&gt;" in out               # escaped
    assert "Resting HR" in out
    assert "likely helped" in out
    assert "insufficient_data" in out


def test_experiment_card_empty_metrics():
    out = cockpit.experiment_result_card({"name": "Empty", "metrics": {}})
    assert "No metrics selected" in out
