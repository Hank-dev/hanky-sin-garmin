"""Nightly correlation mining engine.

Tests curated, hypothesis-driven pairs across all daily Garmin metrics
with lag structure (today's X → tomorrow's Y). Uses the existing stats
engine (BH correction, confidence intervals, evidence levels) from
analysis.py. Only reports NEW findings at strong/suggestive evidence
level — silent otherwise.

Usage:
    cd /home/johannes/apps/hanky-sin-garmin
    .venv/bin/python correlations.py
"""
import sys
import os
import json
from pathlib import Path
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))

import db
import analysis
import config
import pandas as pd

CACHE_PATH = Path(__file__).resolve().parent / ".correlation_cache.json"
MIN_PAIRS = 8
REPORT_EVIDENCE = ("strong", "suggestive")

# Curated pairs: (x_col, y_col, label_x, label_y)
# Pairs NOT already covered by compute_prebed_discovery().
# Removed overlaps: stress→HRV, stress→sleep_score, hr_bedtime→HRV,
# hr_bedtime→sleep_score, HRV→stress (all tested in prebed discovery).
LAG1_PAIRS = [
    ("cardio_load", "hrv_overnight_avg", "Trening", "HRV neste dag"),
    ("cardio_load", "resting_hr", "Trening", "Hvilepuls neste dag"),
    ("cardio_load", "sleep_score", "Trening", "Søvnscore neste dag"),
    ("stress_avg", "body_battery_high", "Stress", "Body Battery neste dag"),
    ("sleep_hours", "hrv_overnight_avg", "Søvntid", "HRV neste dag"),
    ("sleep_hours", "stress_avg", "Søvntid", "Stress neste dag"),
    ("sleep_hours", "resting_hr", "Søvntid", "Hvilepuls neste dag"),
    ("steps", "sleep_hours", "Skritt", "Søvn neste dag"),
    ("steps", "hrv_overnight_avg", "Skritt", "HRV neste dag"),
    ("intensity_minutes", "resting_hr", "Intensitet", "Hvilepuls neste dag"),
    ("spo2_avg", "hrv_overnight_avg", "SpO2", "HRV neste dag"),
    ("spo2_avg", "sleep_score", "SpO2", "Søvnscore neste dag"),
    ("respiration_avg", "hrv_overnight_avg", "Pust", "HRV neste dag"),
    ("respiration_avg", "sleep_score", "Pust", "Søvnscore neste dag"),
    ("body_battery_high", "hrv_overnight_avg", "Body Battery", "HRV neste dag"),
    ("body_battery_high", "stress_avg", "Body Battery", "Stress neste dag"),
    ("sleep_score", "hrv_overnight_avg", "Søvnscore", "HRV neste dag"),
    ("hrv_overnight_avg", "sleep_score", "HRV", "Søvnscore neste dag"),
]

LAG0_PAIRS = [
    ("hrv_overnight_avg", "resting_hr", "HRV", "Hvilepuls"),
    ("hrv_overnight_avg", "sleep_score", "HRV", "Søvnscore"),
    ("hrv_overnight_avg", "body_battery_high", "HRV", "Body Battery"),
    ("sleep_hours", "sleep_score", "Søvntid", "Søvnscore"),
    ("stress_avg", "body_battery_high", "Stress", "Body Battery"),
    ("stress_avg", "sleep_score", "Stress", "Søvnscore"),
    ("spo2_avg", "respiration_avg", "SpO2", "Pust"),
    ("spo2_avg", "hrv_overnight_avg", "SpO2", "HRV"),
    ("respiration_avg", "resting_hr", "Pust", "Hvilepuls"),
    ("sleep_hours", "stress_avg", "Søvntid", "Stress"),
]

EVIDENCE_ORDER = {"strong": 4, "suggestive": 3, "exploratory": 2, "learning": 1}


def _build_pairs_df(df, x_col, y_col, lag):
    work = df[["date", x_col, y_col]].copy()
    work[x_col] = pd.to_numeric(work[x_col], errors="coerce")
    work[y_col] = pd.to_numeric(work[y_col], errors="coerce")
    if lag == 1:
        work[y_col] = work[y_col].shift(-1)
    return work.dropna(subset=[x_col, y_col])


def _mine():
    daily = analysis.enrich_daily(db.load_daily_df())
    activities = db.load_activities_df()
    daily = analysis._attach_cardio_load(daily, activities)
    if "sleep_hours" not in daily and "sleep_seconds" in daily:
        daily["sleep_hours"] = pd.to_numeric(
            daily["sleep_seconds"], errors="coerce") / 3600.0

    results = []
    for x, y, lx, ly in LAG1_PAIRS:
        if x not in daily or y not in daily:
            continue
        pairs = _build_pairs_df(daily, x, y, lag=1)
        stats = analysis._correlation_stats(pairs, x, y)
        results.append({"pair_id": f"{x}->{y}_lag1", "lag": 1,
                        "label_x": lx, "label_y": ly,
                        "n": len(pairs), "pairs": len(pairs), **stats})
    for x, y, lx, ly in LAG0_PAIRS:
        if x not in daily or y not in daily:
            continue
        pairs = _build_pairs_df(daily, x, y, lag=0)
        stats = analysis._correlation_stats(pairs, x, y)
        results.append({"pair_id": f"{x}<->{y}_lag0", "lag": 0,
                        "label_x": lx, "label_y": ly,
                        "n": len(pairs), "pairs": len(pairs), **stats})

    p_values = [r.get("p_value") for r in results]
    adjusted = analysis._bh_adjusted_p_values(p_values)
    for r, adj in zip(results, adjusted):
        r["p_adjusted"] = adj
        r["evidence"] = analysis._evidence_level(r, MIN_PAIRS)
    return results


def _load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"reported": {}}


def _save_cache(cache):
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
    except OSError:
        pass


def _fmt_finding(r):
    corr = r.get("correlation")
    n = r.get("n", 0)
    ev = r.get("evidence", "?")
    if corr is None:
        return f"n={n}, {ev}"
    mag = abs(corr)
    strength = "sterk" if mag >= 0.6 else ("moderat" if mag >= 0.4 else "svak")
    sign = "neg" if corr < 0 else "pos"
    ci_lo = r.get("corr_ci_low")
    ci_hi = r.get("corr_ci_high")
    ci = ""
    if ci_lo is not None and ci_hi is not None:
        ci = f" [{ci_lo:.2f}, {ci_hi:.2f}]"
    return f"r={corr:+.2f} ({strength} {sign}, n={n}, {ev}){ci}"


def main():
    results = _mine()

    significant = [r for r in results if r["evidence"] in REPORT_EVIDENCE]
    significant.sort(
        key=lambda r: (EVIDENCE_ORDER.get(r["evidence"], 0),
                       abs(r.get("correlation") or 0)),
        reverse=True,
    )

    cache = _load_cache()
    reported = cache.get("reported", {})

    new = []
    for r in significant:
        pid = r["pair_id"]
        prev = reported.get(pid)
        if prev is None:
            new.append(r)
        elif EVIDENCE_ORDER.get(r["evidence"], 0) > \
                EVIDENCE_ORDER.get(prev.get("evidence", ""), 0):
            new.append(r)

    for r in significant:
        reported[r["pair_id"]] = {
            "evidence": r["evidence"],
            "correlation": r.get("correlation"),
            "n": r.get("n"),
        }
    cache["reported"] = reported
    cache["last_run"] = date.today().isoformat()
    _save_cache(cache)

    if not new:
        return  # silent — nothing new

    lag1 = [r for r in new if r["lag"] == 1]
    lag0 = [r for r in new if r["lag"] == 0]

    print("**📊 Nye korrelasjoner i dine data**")
    print()
    if lag1:
        print("**I går → i dag (prediktivt):**")
        for r in lag1:
            print(f"• {r['label_x']} → {r['label_y']}: {_fmt_finding(r)}")
        print()
    if lag0:
        print("**Samme dag:**")
        for r in lag0:
            print(f"• {r['label_x']} ↔ {r['label_y']}: {_fmt_finding(r)}")
    total_sig = len(significant)
    total_tested = len(results)
    print()
    print(f"_{total_sig} signifikante av {total_tested} testede par. "
          f"Alle justert for multippel testing (BH)._")


if __name__ == "__main__":
    main()
