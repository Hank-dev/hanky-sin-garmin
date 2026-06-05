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
