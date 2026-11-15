import pandas as pd

import analysis


def timing(rows):
    df = pd.DataFrame(rows, columns=["date", "sleep_start", "sleep_end"])
    df["sleep_start"] = pd.to_datetime(df["sleep_start"])
    df["sleep_end"] = pd.to_datetime(df["sleep_end"])
    df["sleep_midpoint"] = df["sleep_start"] + (df["sleep_end"] - df["sleep_start"]) / 2
    return df


def test_bedtimes_either_side_of_midnight_do_not_wrap():
    rows = []
    for d in range(2, 10):
        start = f"2026-09-{d - 1:02d} 23:50" if d % 2 else f"2026-09-{d:02d} 00:10"
        rows.append((f"2026-09-{d:02d}", start, f"2026-09-{d:02d} 08:00"))
    r = analysis.sleep_timing_regularity(timing(rows))
    assert r["bed_sd"].iloc[-1] < 15  # 23:50 vs 00:10 is 20 min apart, not 23 h
    assert analysis.clock_from_noon(r["bed_min"].iloc[-1]) in ("23:50", "00:10")


def test_steady_schedule_has_near_zero_spread_and_needs_min_nights():
    rows = [(f"2026-09-{d:02d}", f"2026-09-{d - 1:02d} 23:00", f"2026-09-{d:02d} 07:00") for d in range(2, 12)]
    r = analysis.sleep_timing_regularity(timing(rows))
    assert pd.isna(r["mid_sd"].iloc[2])  # 3 nights < min 4
    assert r["mid_sd"].iloc[-1] == 0
    assert analysis.clock_from_noon(r["mid_min"].iloc[-1]) == "03:00"
    assert analysis.clock_from_noon(r["wake_min"].iloc[-1], 1080) == "07:00"


def test_shifting_schedule_shows_large_spread():
    starts = ["22:00", "02:00", "22:30", "01:30", "23:00", "03:00", "22:00"]
    rows = []
    for i, st in enumerate(starts, start=2):
        night = i - 1 if st >= "12:00" else i
        rows.append((f"2026-09-{i:02d}", f"2026-09-{night:02d} {st}",
                     pd.Timestamp(f"2026-09-{night:02d} {st}") + pd.Timedelta(hours=8)))
    r = analysis.sleep_timing_regularity(timing(rows))
    assert r["mid_sd"].iloc[-1] > 60


def test_short_records_are_left_out():
    rows = [(f"2026-09-{d:02d}", f"2026-09-{d - 1:02d} 23:00", f"2026-09-{d:02d} 07:00") for d in range(2, 9)]
    rows.append(("2026-09-09", "2026-09-09 09:00", "2026-09-09 09:50"))  # 50-min nap
    r = analysis.sleep_timing_regularity(timing(rows))
    assert "2026-09-09" not in set(r["date"])
    assert r["mid_sd"].iloc[-1] == 0


def test_empty_input():
    assert analysis.sleep_timing_regularity(None).empty
    assert analysis.clock_from_noon(None) is None
