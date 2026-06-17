import pandas as pd
import analysis
import strength_standards as ss


def test_levels_and_bands_consistent():
    assert ss.LEVELS == ("Untrained", "Novice", "Intermediate", "Advanced", "Elite")
    assert set(ss.LEVEL_PERCENTILE_BANDS) == set(ss.LEVELS)
    # bands are contiguous 0..100
    lows = [ss.LEVEL_PERCENTILE_BANDS[l][0] for l in ss.LEVELS]
    highs = [ss.LEVEL_PERCENTILE_BANDS[l][1] for l in ss.LEVELS]
    assert lows[0] == 0 and highs[-1] == 100
    assert highs[:-1] == lows[1:]  # each band's high == next band's low


def test_standards_cover_main_lifts_both_sexes():
    for sex in ("male", "female"):
        assert sex in ss.STANDARDS
        for lift in ("back-squat", "bench-press", "deadlift",
                     "overhead-press", "barbell-row"):
            thr = ss.STANDARDS[sex][lift]
            assert len(thr) == 4
            assert list(thr) == sorted(thr)  # strictly increasing thresholds


def test_balance_targets_well_formed():
    for t in ss.BALANCE_TARGETS:
        assert {"numerator", "denominator", "label", "low", "ideal", "high",
                "reason"} <= set(t)
        assert t["low"] <= t["ideal"] <= t["high"]


def test_asymmetry_flag_pct_is_positive_number():
    assert isinstance(ss.ASYMMETRY_FLAG_PCT, (int, float))
    assert ss.ASYMMETRY_FLAG_PCT > 0


def test_standards_levels_and_percentiles_at_boundaries():
    best = {"back-squat": 125.0, "bench-press": 100.0}
    out = analysis.compute_strength_standards(best, {"sex": "male"}, 100.0)
    assert out["status"] == "ok"
    sq = [l for l in out["lifts"] if l["exercise_id"] == "back-squat"][0]
    assert sq["level"] == "Intermediate"
    assert sq["percentile"] == 50.0
    assert out["overall"]["level"] == "Intermediate"


def test_standards_need_profile_when_sex_or_weight_missing():
    assert analysis.compute_strength_standards({"back-squat": 100.0}, {}, 100.0)["status"] == "need_profile"
    assert analysis.compute_strength_standards({"back-squat": 100.0}, {"sex": "male"}, 0)["status"] == "need_profile"


def test_standards_omits_unlogged_lifts_and_handles_none():
    out = analysis.compute_strength_standards({"back-squat": 150.0}, {"sex": "male"}, 100.0)
    assert out["graded_lifts"] == 1
    sq = out["lifts"][0]
    assert sq["level"] == "Intermediate"


def test_standards_no_main_lifts_logged():
    out = analysis.compute_strength_standards({"barbell-curl": 40.0}, {"sex": "male"}, 100.0)
    assert out["status"] == "no_main_lifts"


def test_balance_ratio_ok_and_under():
    out = analysis.compute_balance({"bench-press": 100.0, "back-squat": 125.0},
                                   pd.DataFrame(), pd.DataFrame())
    bs = [r for r in out["ratios"] if r["label"] == "Bench : Squat"][0]
    assert bs["status"] == "ok"
    out2 = analysis.compute_balance({"bench-press": 50.0, "back-squat": 200.0},
                                    pd.DataFrame(), pd.DataFrame())
    bs2 = [r for r in out2["ratios"] if r["label"] == "Bench : Squat"][0]
    assert bs2["status"] == "under"
    assert bs2["weak_side"] == "bench-press"


def test_balance_skips_missing_lift():
    out = analysis.compute_balance({"bench-press": 100.0}, pd.DataFrame(), pd.DataFrame())
    assert not any(r["label"] == "Bench : Squat" for r in out["ratios"])


def test_left_right_asymmetry_flag():
    exercises = pd.DataFrame([{"exercise_id": "bulgarian-split-squat",
                               "name": "Bulgarian Split Squat", "is_unilateral": 1}])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "bulgarian-split-squat", "side": "left",
         "reps": 5, "weight_kg": 40.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s1", "exercise_id": "bulgarian-split-squat", "side": "right",
         "reps": 5, "weight_kg": 50.0, "is_warmup": 0, "completed": 1},
    ])
    out = analysis.compute_balance({}, sets, exercises)
    lr = out["left_right"][0]
    assert lr["stronger_side"] == "right"
    assert lr["flagged"] is True
    assert lr["diff_pct"] > 10


def test_left_right_not_flagged_when_balanced():
    exercises = pd.DataFrame([{"exercise_id": "bulgarian-split-squat",
                               "name": "Bulgarian Split Squat", "is_unilateral": 1}])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "bulgarian-split-squat", "side": "left",
         "reps": 5, "weight_kg": 48.0, "is_warmup": 0, "completed": 1},
        {"session_id": "s1", "exercise_id": "bulgarian-split-squat", "side": "right",
         "reps": 5, "weight_kg": 50.0, "is_warmup": 0, "completed": 1},
    ])
    out = analysis.compute_balance({}, sets, exercises)
    assert out["left_right"][0]["flagged"] is False


def _bench_only_exercises():
    return pd.DataFrame([{"exercise_id": "bench-press", "is_bodyweight": 0}])


def test_readiness_perf_insufficient_below_min():
    sessions = pd.DataFrame([
        {"session_id": f"s{i}", "date": f"2026-05-0{i+1}", "bodyweight_kg": 80.0,
         "recovery_score": 70} for i in range(3)])
    sets = pd.DataFrame([
        {"session_id": f"s{i}", "exercise_id": "bench-press", "reps": 5,
         "weight_kg": 100.0, "is_warmup": 0, "completed": 1} for i in range(3)])
    out = analysis.compute_readiness_performance(sessions, sets, _bench_only_exercises())
    assert out["status"] == "insufficient"
    assert out["have"] == 3 and out["need"] == 8


def test_readiness_perf_positive_correlation_when_better_on_high_readiness():
    rows_s, rows_x = [], []
    for i in range(10):
        readiness = 40 + i * 6
        weight = 80 + i * 4
        rows_s.append({"session_id": f"s{i}", "date": f"2026-05-{i+1:02d}",
                       "bodyweight_kg": 80.0, "recovery_score": readiness})
        rows_x.append({"session_id": f"s{i}", "exercise_id": "bench-press",
                       "reps": 1, "weight_kg": float(weight),
                       "is_warmup": 0, "completed": 1})
    out = analysis.compute_readiness_performance(
        pd.DataFrame(rows_s), pd.DataFrame(rows_x), _bench_only_exercises())
    assert out["status"] == "ok"
    assert out["n"] == 10
    assert out["correlation"] is not None and out["correlation"] > 0.5
    assert set(out["buckets"]).issubset({"Low", "Med", "High"})


def test_summarize_strength_shape_and_no_raw_sets():
    sessions = pd.DataFrame([{"session_id": "s1", "date": "2026-06-05",
                              "bodyweight_kg": 100.0, "recovery_score": 70}])
    sets = pd.DataFrame([
        {"session_id": "s1", "exercise_id": "back-squat", "reps": 1,
         "weight_kg": 125.0, "is_warmup": 0, "completed": 1, "side": "both",
         "set_id": "x1", "position": 0, "set_index": 1}])
    exercises = pd.DataFrame([{"exercise_id": "back-squat", "name": "Back Squat",
                               "is_bodyweight": 0, "is_unilateral": 0}])
    out = analysis.summarize_strength(sessions, sets, exercises, {"sex": "male"}, 100.0)
    assert out["status"] == "ok"
    assert out["standards"]["overall"]["level"] == "Intermediate"
    assert "recent" in out and "balance_flags" in out and "readiness_link" in out
    import json
    blob = json.dumps(out)
    for forbidden in ("set_id", '"reps"', '"side"', "position", "set_index"):
        assert forbidden not in blob


def test_summarize_strength_empty():
    assert analysis.summarize_strength(pd.DataFrame(), pd.DataFrame(),
                                       pd.DataFrame(), {}, None)["status"] == "no_data"


def test_summarize_strength_respects_formula():
    sessions = pd.DataFrame([{"session_id": "s1", "date": "2026-06-05",
                              "bodyweight_kg": 100.0, "recovery_score": 70}])
    sets = pd.DataFrame([{"session_id": "s1", "exercise_id": "back-squat",
                          "reps": 5, "weight_kg": 100.0, "is_warmup": 0,
                          "completed": 1, "side": "both"}])
    exercises = pd.DataFrame([{"exercise_id": "back-squat", "name": "Back Squat",
                               "is_bodyweight": 0, "is_unilateral": 0}])
    epley = analysis.summarize_strength(sessions, sets, exercises, {"sex": "male"}, 100.0, formula="epley")
    brz = analysis.summarize_strength(sessions, sets, exercises, {"sex": "male"}, 100.0, formula="brzycki")
    # reps=5 -> Epley (116.7) and Brzycki (112.5) differ -> the PR est-1RM differs
    assert epley["recent_prs"][0]["est_1rm_kg"] != brz["recent_prs"][0]["est_1rm_kg"]
