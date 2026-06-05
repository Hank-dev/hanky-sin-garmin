"""Pure analytics over the stored metrics. No network, no AI.

Produces (a) an enriched daily dataframe for charting and (b) a compact
summary dict that the AI layer turns into prose. Everything here is
deterministic and unit-testable.
"""
import pandas as pd
import numpy as np
import config


GRAPPLING_PATTERNS = (
    "bjj", "jiu-jitsu", "jiu jitsu", "grappling", "martial",
    "combat", "wrestling", "submission",
)


def enrich_daily(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.sort_values("date").copy()

    # Rolling baselines
    df["rhr_7d"] = df["resting_hr"].rolling(7, min_periods=3).mean()
    df["rhr_28d"] = df["resting_hr"].rolling(28, min_periods=7).mean()
    df["hrv_7d"] = df["hrv_overnight_avg"].rolling(7, min_periods=3).mean()
    if "hr_overnight_low" in df:
        df["hr_overnight_low_7d"] = df["hr_overnight_low"].rolling(7, min_periods=3).mean()
    if "hr_bedtime" in df:
        df["hr_bedtime_7d"] = df["hr_bedtime"].rolling(7, min_periods=3).mean()
    df["sleep_hours"] = df["sleep_seconds"] / 3600.0
    df["sleep_hours_7d"] = df["sleep_hours"].rolling(7, min_periods=3).mean()

    # HRV deviation vs personal baseline band (from Garmin) when present,
    # else vs 28d rolling mean +/- 1 SD.
    base_mid = df[["hrv_baseline_low", "hrv_baseline_high"]].mean(axis=1)
    df["hrv_baseline_mid"] = base_mid.fillna(
        df["hrv_overnight_avg"].rolling(28, min_periods=7).mean()
    )

    def hrv_flag(row):
        v = row["hrv_overnight_avg"]
        if pd.isna(v):
            return None
        lo, hi = row["hrv_baseline_low"], row["hrv_baseline_high"]
        if pd.notna(lo) and pd.notna(hi):
            if v < lo:
                return "suppressed"
            if v > hi:
                return "elevated"
            return "balanced"
        mid = row["hrv_baseline_mid"]
        if pd.isna(mid):
            return None
        return "suppressed" if v < 0.9 * mid else ("elevated" if v > 1.1 * mid else "balanced")

    df["hrv_flag"] = df.apply(hrv_flag, axis=1)

    # RHR elevation vs 28d baseline (>+5% is a common under-recovery heuristic)
    df["rhr_elevated"] = (df["resting_hr"] > 1.05 * df["rhr_28d"]).where(df["rhr_28d"].notna())

    # Sleep debt vs personal need
    df["sleep_debt_h"] = config.SLEEP_NEED_HOURS - df["sleep_hours"]

    return df


def compute_acwr(activities: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Acute:Chronic Workload Ratio from per-activity training load.

    acute  = sum of training load over trailing 7 days
    chronic = average weekly load over trailing 28 days
    ratio = acute / chronic. ~0.8-1.3 is the commonly cited 'sweet spot';
    >1.5 flags a load spike. (Note: ACWR is contested in the literature -
    treat it as one signal, not gospel.)
    """
    if daily.empty:
        return daily
    idx = pd.to_datetime(daily["date"])
    load = pd.Series(0.0, index=idx.values)
    if not activities.empty and activities["training_load"].notna().any():
        a = activities.dropna(subset=["date"]).copy()
        a["date"] = pd.to_datetime(a["date"])
        daily_load = a.groupby("date")["training_load"].sum()
        load = daily_load.reindex(idx.values, fill_value=0.0)
    s = pd.Series(load.values, index=idx.values).sort_index()
    acute = s.rolling("7D").sum()
    chronic_28 = s.rolling("28D").sum() / 4.0  # avg weekly over 28d
    out = daily.sort_values("date").copy()
    out["acute_load"] = acute.values
    out["chronic_load"] = chronic_28.values
    ratio = np.full(len(out), np.nan, dtype=float)
    np.divide(acute.values, chronic_28.values, out=ratio, where=chronic_28.values > 0)
    out["acwr"] = ratio
    return out


def compute_capacity_envelope(
    daily: pd.DataFrame,
    activities: pd.DataFrame,
    checkins: pd.DataFrame,
    min_days: int = 14,
) -> dict:
    """Estimate a personal load tolerance envelope from Garmin + check-ins.

    The envelope is intentionally conservative: it looks for days where the
    following day's recovery response was stable, then uses those load days to
    estimate a current safe range. It is a tolerance model, not an activity goal.
    """
    if daily.empty:
        return {
            "status": "no_data",
            "zone": "learning",
            "message": "Sync Garmin data and add daily check-ins to start learning your capacity envelope.",
            "metrics": [],
            "flags": [],
            "learned_days": 0,
            "min_days": min_days,
        }

    df = daily.sort_values("date").copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = _attach_activity_load(df, activities)
    df = _attach_checkins(df, checkins)

    response = _capacity_response_flags(df)
    df["poor_recovery_response"] = response["poor"]
    df["response_flag_count"] = response["flag_count"]

    next_response = df["poor_recovery_response"].shift(-1)
    has_next_response = next_response.notna()
    stable_load_days = has_next_response & (next_response == False)
    stable = df.loc[stable_load_days].copy()
    history = df.iloc[:-1].copy() if len(df) > 1 else df.iloc[0:0].copy()

    learned_days = int(len(df))
    enough_history = learned_days >= min_days and len(stable) >= 3
    latest = df.iloc[-1]
    latest_flags = _latest_capacity_flags(latest)

    metrics = _capacity_metrics(stable if enough_history else history, latest)
    max_excess = max(
        [m["excess_ratio"] for m in metrics if m["excess_ratio"] is not None] or [0.0]
    )
    current_poor = bool(latest.get("poor_recovery_response"))
    severe_checkin = (
        _ge(latest.get("pain"), 7)
        or _ge(latest.get("fatigue"), 8)
        or _le(latest.get("energy"), 2)
    )

    if not enough_history:
        zone = "learning"
    elif severe_checkin or max_excess >= 0.25 or (max_excess >= 0.10 and current_poor):
        zone = "red"
    elif max_excess >= 0.05 or current_poor:
        zone = "yellow"
    else:
        zone = "green"

    status = "ready" if enough_history else "learning"
    return {
        "status": status,
        "zone": zone,
        "as_of": str(latest["date"])[:10],
        "learned_days": learned_days,
        "stable_days": int(len(stable)),
        "min_days": min_days,
        "message": _capacity_message(status, zone, metrics, max_excess, latest_flags, learned_days, min_days),
        "metrics": metrics,
        "flags": latest_flags,
        "missing": _capacity_missing(df, activities),
    }


def compute_grappling_sessions(
    daily: pd.DataFrame,
    activities: pd.DataFrame,
    detail_payloads: dict | None = None,
    zone_payloads: dict | None = None,
) -> list[dict]:
    """Analyze auto-detected BJJ/grappling sessions from activity HR detail."""
    if activities is None or activities.empty:
        return []

    detail_payloads = detail_payloads or {}
    zone_payloads = zone_payloads or {}
    sessions = []
    for _, row in activities.iterrows():
        rec = row.to_dict()
        if not _is_grappling_activity(rec):
            continue
        activity_id = str(rec.get("activity_id") or "")
        details = detail_payloads.get(activity_id)
        zones = zone_payloads.get(activity_id)
        hr = _parse_activity_hr_samples(details)
        round_info = _detect_grappling_rounds(hr)
        high_zone_min = _parse_high_zone_minutes(zones)
        threshold_source = "garmin_zones" if high_zone_min is not None else "session_estimate"
        if high_zone_min is None:
            high_zone_min = _time_above_threshold(hr, round_info.get("threshold_hr"))

        duration_min = _activity_duration_minutes(rec, hr)
        peak_hr = _first_number(rec.get("max_hr"), hr["hr"].max() if not hr.empty else None)
        avg_hr = _first_number(rec.get("avg_hr"), hr["hr"].mean() if not hr.empty else None)
        round_count = len(round_info["rounds"]) if round_info["available"] else None
        poor_recovery_rounds = (
            round_info["poor_recovery_rounds"] if round_info["available"] else None
        )
        classification, confidence = _classify_grappling_session(
            round_count, high_zone_min, peak_hr, duration_min, round_info["available"]
        )
        mat_cost = _mat_stress_cost(
            duration_min, high_zone_min, peak_hr, round_count, poor_recovery_rounds
        )
        next_day = _grappling_next_day_impact(daily, rec.get("date"))
        warning = _grappling_warning(mat_cost, next_day)

        sessions.append({
            "activity_id": activity_id,
            "date": str(rec.get("date"))[:10],
            "name": rec.get("name") or "Grappling session",
            "type": rec.get("type") or "",
            "duration_min": _round_or_none(duration_min, 1),
            "avg_hr": _round_or_none(avg_hr, 0),
            "peak_hr": _round_or_none(peak_hr, 0),
            "high_zone_min": _round_or_none(high_zone_min, 1),
            "threshold_source": threshold_source,
            "round_detection": "available" if round_info["available"] else "unavailable",
            "rounds": round_info["rounds"],
            "round_count": round_count,
            "avg_recovery_drop": _round_or_none(round_info.get("avg_recovery_drop"), 0),
            "poor_recovery_rounds": poor_recovery_rounds,
            "recovery_quality": _recovery_quality(round_info),
            "classification": classification,
            "classification_confidence": confidence,
            "mat_stress_cost": int(round(mat_cost)),
            "next_day": next_day,
            "warning": warning,
            "has_hr_detail": not hr.empty,
        })

    return sorted(sessions, key=lambda s: (s.get("date") or "", s.get("activity_id") or ""), reverse=True)


def compute_stress_leak_map(daily: pd.DataFrame, stress: pd.DataFrame, min_days: int = 5) -> dict:
    """Find recurring intraday stress leak windows and rank recovery impact."""
    if stress is None or stress.empty:
        return {
            "status": "no_data",
            "message": "No intraday stress samples stored yet. Sync Garmin all-day stress to build a leak map.",
            "days_analyzed": 0,
            "leaks": [],
            "top_leak": None,
        }

    s = stress.copy()
    s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
    s["value"] = pd.to_numeric(s["value"], errors="coerce")
    s = s.dropna(subset=["timestamp", "value"])
    s = s[(s["value"] >= 0) & (s["value"] <= 100)]
    if s.empty:
        return {
            "status": "no_data",
            "message": "No measured stress samples are available yet.",
            "days_analyzed": 0,
            "leaks": [],
            "top_leak": None,
        }
    parsed_dates = pd.to_datetime(s.get("date"), errors="coerce") if "date" in s else None
    if parsed_dates is None:
        s["date"] = s["timestamp"].dt.strftime("%Y-%m-%d")
    else:
        s["date"] = parsed_dates.dt.strftime("%Y-%m-%d").fillna(
            s["timestamp"].dt.strftime("%Y-%m-%d")
        )
    s["minute"] = s["timestamp"].dt.hour * 60 + s["timestamp"].dt.minute
    s["bucket_min"] = (s["minute"] // 30) * 30
    s["high"] = s["value"] >= 50
    sample_min = _stress_sample_minutes(s)
    days = sorted(s["date"].unique())
    day_impacts = _daily_recovery_impact(daily)

    grouped = (
        s.groupby(["date", "bucket_min"])
        .agg(avg_stress=("value", "mean"), high_samples=("high", "sum"), samples=("value", "size"))
        .reset_index()
    )
    grouped["high_min"] = grouped["high_samples"] * sample_min
    grouped["measured_min"] = grouped["samples"] * sample_min
    grouped["is_leak_day"] = (grouped["avg_stress"] >= 50) | (grouped["high_min"] >= 12)
    grouped["next_flags"] = grouped["date"].map(day_impacts).fillna(0)

    bucket_rows = []
    for bucket, g in grouped.groupby("bucket_min"):
        days_seen = int(g["date"].nunique())
        leak_days = int(g["is_leak_day"].sum())
        if days_seen == 0:
            continue
        avg_stress = float(g["avg_stress"].mean())
        avg_high_min = float(g["high_min"].mean())
        recurrence = leak_days / days_seen
        if avg_stress < 45 and avg_high_min < 8:
            continue
        impact = (
            avg_stress
            + recurrence * 25
            + min(avg_high_min, 30) * 0.7
            + _time_impact_weight(bucket)
            + float(g.loc[g["is_leak_day"], "next_flags"].mean() if leak_days else 0) * 8
        )
        bucket_rows.append({
            "start_min": int(bucket),
            "end_min": int(bucket + 30),
            "avg_stress": avg_stress,
            "avg_high_min": avg_high_min,
            "days_seen": days_seen,
            "days_high": leak_days,
            "recurrence": recurrence,
            "next_flags": float(g.loc[g["is_leak_day"], "next_flags"].mean() if leak_days else 0),
            "impact_score": impact,
        })

    windows = _merge_stress_leak_buckets(bucket_rows)
    windows = sorted(windows, key=lambda x: x["impact_score"], reverse=True)[:5]
    for window in windows:
        window["label"] = _stress_window_label(window["start_min"], window["end_min"])
        window["time_range"] = f"{_fmt_clock(window['start_min'])}-{_fmt_clock(window['end_min'])}"
        window["reason"] = _stress_leak_reason(window)

    status = "ready" if len(days) >= min_days else "learning"
    top = windows[0] if windows else None
    if top is None:
        message = "No clear stress leak window yet. More all-day stress samples will make the map sharper."
    elif status == "learning":
        message = (
            f"Learning stress leaks from {len(days)}/{min_days} days. The strongest observed leak is "
            f"{top['time_range']} ({top['label']})."
        )
    else:
        message = (
            f"Highest-impact intervention: reduce the {top['time_range']} stress leak "
            f"({top['label']})."
        )

    return {
        "status": status,
        "message": message,
        "days_analyzed": int(len(days)),
        "sample_minutes": round(sample_min, 1),
        "leaks": windows,
        "top_leak": top,
        "missing": _stress_leak_missing(s, len(days), min_days),
    }


def compute_prebed_discovery(
    daily: pd.DataFrame,
    activities: pd.DataFrame | None = None,
    sleep_timing: pd.DataFrame | None = None,
    min_pairs: int = 5,
) -> dict:
    """Discover sleep-adjacent links to sleep quality and next-day stress.

    `hr_bedtime` is the Garmin HR sample nearest sleep start, usually from the
    30 minutes before sleep. `hrv_overnight_avg` is treated as sleep HRV.
    Relationships are associations only: this ranks paired observations and
    split effects, not causal mechanisms.
    """
    if daily is None or daily.empty:
        return {
            "status": "no_data",
            "message": "No daily metrics stored yet.",
            "relationships": [],
            "rows": [],
            "missing": ["sync daily sleep and heart-rate metrics"],
        }
    df = daily.sort_values("date").copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df = _attach_cardio_load(df, activities)
    df = _attach_sleep_regularity(df, sleep_timing)
    df = _add_bedtime_hr_delta(df)
    df = _add_activity_buckets(df)
    df = _add_body_battery_recharge(df)
    for col in ("hr_bedtime", "hrv_overnight_avg", "resting_hr", "sleep_score", "sleep_hours",
                "stress_avg", "cardio_load", "bedtime_hr_delta",
                "sleep_midpoint_variability_7d", "activity_bucket_code",
                "body_battery_recharge"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["date"])
    has_prebed = "hr_bedtime" in df and df["hr_bedtime"].notna().any()
    has_hrv = "hrv_overnight_avg" in df and df["hrv_overnight_avg"].notna().any()
    has_cardio_load = "cardio_load" in df and df["cardio_load"].notna().any()
    if not has_prebed and not has_hrv and not has_cardio_load:
        return {
            "status": "no_data",
            "message": "No pre-sleep heart-rate, overnight HRV, or activity load values are stored yet.",
            "relationships": [],
            "rows": [],
            "missing": ["sync sleep, HRV, activities, and daily stress metrics"],
        }

    stress_by_date = df.set_index("date")["stress_avg"] if "stress_avg" in df else pd.Series(dtype=float)
    hrv_by_date = df.set_index("date")["hrv_overnight_avg"] if "hrv_overnight_avg" in df else pd.Series(dtype=float)
    recharge_by_date = df.set_index("date")["body_battery_recharge"] if "body_battery_recharge" in df else pd.Series(dtype=float)
    df["next_date"] = df["date"] + pd.Timedelta(days=1)
    df["next_day_stress"] = df["next_date"].map(stress_by_date)
    df["next_day_hrv"] = df["next_date"].map(hrv_by_date)
    df["next_day_body_battery_recharge"] = df["next_date"].map(recharge_by_date)

    sleep_col = None
    sleep_label = None
    sleep_unit = ""
    if has_prebed and "sleep_score" in df and int(df[["hr_bedtime", "sleep_score"]].dropna().shape[0]) >= 3:
        sleep_col = "sleep_score"
        sleep_label = "Sleep score"
    elif has_prebed and "sleep_hours" in df:
        sleep_col = "sleep_hours"
        sleep_label = "Sleep duration"
        sleep_unit = "h"

    relationships = []
    if "bedtime_hr_delta" in df and df["bedtime_hr_delta"].notna().any():
        bedtime_targets = [
            ("sleep_score", "Sleep score", "", -1, "Bedtime HR deviation vs sleep quality"),
            ("hrv_overnight_avg", "Overnight HRV", "ms", -1, "Bedtime HR deviation vs overnight HRV"),
            ("resting_hr", "Resting HR", "bpm", 1, "Bedtime HR deviation vs overnight resting HR"),
        ]
        for y_col, y_label, y_unit, desired, label in bedtime_targets:
            rel = _prebed_relationship(
                df,
                x_col="bedtime_hr_delta",
                x_label="Bedtime HR deviation",
                x_unit="bpm",
                y_col=y_col,
                label=label,
                y_label=y_label,
                y_unit=y_unit,
                desired_direction=desired,
                min_pairs=min_pairs,
            )
            if rel:
                relationships.append(rel)

    if has_prebed and sleep_col is not None:
        sleep_rel = _prebed_relationship(
            df,
            x_col="hr_bedtime",
            x_label="Pre-sleep HR",
            x_unit="bpm",
            y_col=sleep_col,
            label="Pre-sleep HR vs same-night sleep quality",
            y_label=sleep_label,
            y_unit=sleep_unit,
            desired_direction=-1,
            min_pairs=min_pairs,
        )
        if sleep_rel:
            relationships.append(sleep_rel)

    if has_prebed:
        stress_rel = _prebed_relationship(
            df,
            x_col="hr_bedtime",
            x_label="Pre-sleep HR",
            x_unit="bpm",
            y_col="next_day_stress",
            label="Pre-sleep HR vs next-day stress",
            y_label="Next-day avg stress",
            y_unit="",
            desired_direction=1,
            min_pairs=min_pairs,
        )
        if stress_rel:
            relationships.append(stress_rel)

    if has_hrv:
        hrv_stress_rel = _prebed_relationship(
            df,
            x_col="hrv_overnight_avg",
            x_label="Overnight HRV",
            x_unit="ms",
            y_col="next_day_stress",
            label="Overnight HRV vs next-day stress",
            y_label="Next-day avg stress",
            y_unit="",
            desired_direction=-1,
            min_pairs=min_pairs,
        )
        if hrv_stress_rel:
            relationships.append(hrv_stress_rel)

    if has_cardio_load:
        cardio_stress_rel = _prebed_relationship(
            df,
            x_col="cardio_load",
            x_label="Cardiovascular load",
            x_unit="load",
            y_col="next_day_stress",
            label="Cardiovascular load vs next-day stress",
            y_label="Next-day avg stress",
            y_unit="",
            desired_direction=1,
            min_pairs=min_pairs,
        )
        if cardio_stress_rel:
            relationships.append(cardio_stress_rel)

    if "sleep_midpoint_variability_7d" in df and df["sleep_midpoint_variability_7d"].notna().any():
        regularity_targets = [
            ("next_day_stress", "Next-day avg stress", "", 1, "Sleep midpoint variability vs next-day stress"),
            ("hrv_overnight_avg", "Overnight HRV", "ms", -1, "Sleep midpoint variability vs overnight HRV"),
        ]
        for y_col, y_label, y_unit, desired, label in regularity_targets:
            rel = _prebed_relationship(
                df,
                x_col="sleep_midpoint_variability_7d",
                x_label="Sleep midpoint variability",
                x_unit="min",
                y_col=y_col,
                label=label,
                y_label=y_label,
                y_unit=y_unit,
                desired_direction=desired,
                min_pairs=min_pairs,
            )
            if rel:
                relationships.append(rel)

    if "activity_bucket_code" in df and df["activity_bucket_code"].notna().any():
        bucket_targets = [
            ("next_day_stress", "Next-day avg stress", "", False, "Activity sweet spot vs next-day stress"),
            ("next_day_hrv", "Next-day overnight HRV", "ms", True, "Activity sweet spot vs next-day HRV"),
            ("next_day_body_battery_recharge", "Next-day Body Battery recharge", "", True, "Activity sweet spot vs Body Battery recharge"),
        ]
        for y_col, y_label, y_unit, higher_is_better, label in bucket_targets:
            rel = _bucket_relationship(
                df,
                bucket_col="activity_bucket",
                code_col="activity_bucket_code",
                y_col=y_col,
                label=label,
                y_label=y_label,
                y_unit=y_unit,
                higher_is_better=higher_is_better,
                min_pairs=min_pairs,
            )
            if rel:
                relationships.append(rel)

    rows = []
    if has_prebed:
        row_cols = ["date", "hr_bedtime", "next_day_stress"]
        if sleep_col is not None:
            row_cols.append(sleep_col)
        for _, row in df[row_cols].dropna(subset=["hr_bedtime"]).tail(21).iterrows():
            rows.append({
                "date": str(row["date"].date()),
                "prebed_hr": _round_or_none(row.get("hr_bedtime"), 0),
                "sleep_quality": _round_or_none(row.get(sleep_col), 1) if sleep_col else None,
                "next_day_stress": _round_or_none(row.get("next_day_stress"), 0),
            })

    paired_counts = [r["pairs"] for r in relationships]
    status = "ready" if paired_counts and max(paired_counts) >= min_pairs else "learning"
    missing = _prebed_missing(df, sleep_col, min_pairs, paired_counts)
    top = relationships[0] if relationships else None
    if not relationships:
        message = "Correlation inputs are synced, but there are not enough paired stress observations yet."
    elif status == "learning":
        message = f"Learning from {max(paired_counts)}/{min_pairs} paired days. Early strongest pattern: {top['summary']}"
    else:
        message = f"Strongest correlation pattern: {top['summary']}"

    return {
        "status": status,
        "message": message,
        "days_analyzed": int(df["date"].nunique()),
        "min_pairs": int(min_pairs),
        "sleep_metric": sleep_col,
        "sleep_label": sleep_label,
        "sleep_unit": sleep_unit,
        "relationships": relationships,
        "rows": rows,
        "missing": missing,
    }


def _prebed_relationship(
    df: pd.DataFrame,
    x_col: str,
    x_label: str,
    x_unit: str,
    y_col: str,
    label: str,
    y_label: str,
    y_unit: str,
    desired_direction: int,
    min_pairs: int,
) -> dict | None:
    if x_col not in df or y_col not in df:
        return None
    pairs = df[["date", x_col, y_col]].dropna().copy()
    if pairs.empty:
        return None
    corr = None
    if len(pairs) >= 3 and pairs[x_col].nunique() > 1 and pairs[y_col].nunique() > 1:
        corr = float(pairs[x_col].corr(pairs[y_col]))
        if pd.isna(corr):
            corr = None

    median_x = pairs[x_col].median()
    low = pairs[pairs[x_col] <= median_x][y_col]
    high = pairs[pairs[x_col] > median_x][y_col]
    low_mean = float(low.mean()) if not low.empty else None
    high_mean = float(high.mean()) if not high.empty else None
    delta = high_mean - low_mean if low_mean is not None and high_mean is not None else None
    strength = abs(corr) if corr is not None else 0.0
    confidence = "high" if len(pairs) >= 20 and strength >= 0.45 else (
        "medium" if len(pairs) >= min_pairs and strength >= 0.30 else "low"
    )
    direction_word = "higher" if delta is not None and delta > 0 else "lower"
    effect = _fmt_signed(delta, y_unit) if delta is not None else "unclear"
    correlation_text = "insufficient variance" if corr is None else f"r={corr:+.2f}"
    helpful = (
        corr is not None
        and ((desired_direction == 1 and corr > 0) or (desired_direction == -1 and corr < 0))
    )
    if delta is None:
        summary = f"{label} has {len(pairs)} paired days, but the split effect is not clear yet."
    elif helpful:
        summary = (
            f"higher {x_label.lower()} lines up with {direction_word} {y_label.lower()} "
            f"({effect} on high-{x_label.lower()} nights, {correlation_text}, n={len(pairs)})."
        )
    else:
        summary = (
            f"{x_label} has a weak or mixed link with {y_label.lower()} "
            f"({effect} on high-{x_label.lower()} nights, {correlation_text}, n={len(pairs)})."
        )

    return {
        "label": label,
        "x_col": x_col,
        "x_label": x_label,
        "x_unit": x_unit,
        "y_col": y_col,
        "y_label": y_label,
        "y_unit": y_unit,
        "pairs": int(len(pairs)),
        "correlation": _round_or_none(corr, 2),
        "median_prebed_hr": _round_or_none(median_x, 0),
        "median_x": _round_or_none(median_x, 0),
        "low_x_mean": _round_or_none(low_mean, 1),
        "high_x_mean": _round_or_none(high_mean, 1),
        "high_vs_low_delta": _round_or_none(delta, 1),
        "confidence": confidence,
        "summary": summary,
        "rows": [
            {
                "date": str(row["date"].date()),
                "prebed_hr": _round_or_none(row[x_col], 0),
                "x": _round_or_none(row[x_col], 1),
                "value": _round_or_none(row[y_col], 1),
            }
            for _, row in pairs.tail(90).iterrows()
        ],
    }


def _bucket_relationship(
    df: pd.DataFrame,
    bucket_col: str,
    code_col: str,
    y_col: str,
    label: str,
    y_label: str,
    y_unit: str,
    higher_is_better: bool,
    min_pairs: int,
) -> dict | None:
    if bucket_col not in df or code_col not in df or y_col not in df:
        return None
    pairs = df[["date", bucket_col, code_col, y_col]].dropna().copy()
    if pairs.empty:
        return None
    corr = None
    if len(pairs) >= 3 and pairs[code_col].nunique() > 1 and pairs[y_col].nunique() > 1:
        corr = float(pairs[code_col].corr(pairs[y_col]))
        if pd.isna(corr):
            corr = None

    grouped = (
        pairs.groupby([bucket_col, code_col], observed=True)[y_col]
        .agg(["mean", "count"])
        .reset_index()
        .sort_values(code_col)
    )
    bucket_means = [
        {
            "bucket": str(row[bucket_col]),
            "code": int(row[code_col]),
            "mean": _round_or_none(row["mean"], 1),
            "count": int(row["count"]),
        }
        for _, row in grouped.iterrows()
    ]
    if grouped.empty:
        best = None
    elif higher_is_better:
        best = grouped.loc[grouped["mean"].idxmax()]
    else:
        best = grouped.loc[grouped["mean"].idxmin()]
    best_bucket = str(best[bucket_col]) if best is not None else None
    best_value = _round_or_none(best["mean"], 1) if best is not None else None
    strength = abs(corr) if corr is not None else 0.0
    confidence = "high" if len(pairs) >= 20 and strength >= 0.45 else (
        "medium" if len(pairs) >= min_pairs and (strength >= 0.30 or len(grouped) >= 3) else "low"
    )
    target_word = "highest" if higher_is_better else "lowest"
    summary = (
        f"{label} has {len(pairs)} paired days. Best observed bucket: "
        f"{best_bucket or 'unclear'} ({target_word} {y_label.lower()} around "
        f"{_cap_like_num(best_value) if best_value is not None else '—'})."
    )

    return {
        "label": label,
        "x_col": code_col,
        "x_label": "Activity load bucket",
        "x_unit": "",
        "y_col": y_col,
        "y_label": y_label,
        "y_unit": y_unit,
        "pairs": int(len(pairs)),
        "correlation": _round_or_none(corr, 2),
        "median_x": None,
        "high_vs_low_delta": None,
        "confidence": confidence,
        "summary": summary,
        "bucket_means": bucket_means,
        "bucket_labels": ["very low", "low", "moderate", "high", "very high"],
        "rows": [
            {
                "date": str(row["date"].date()),
                "x": _round_or_none(row[code_col], 0),
                "bucket": str(row[bucket_col]),
                "value": _round_or_none(row[y_col], 1),
            }
            for _, row in pairs.tail(90).iterrows()
        ],
    }


def _fmt_signed(value, unit="") -> str:
    if value is None or pd.isna(value):
        return "unclear"
    n = float(value)
    suffix = unit or "pts"
    return f"{n:+.1f} {suffix}".strip()


def _prebed_missing(df: pd.DataFrame, sleep_col: str | None, min_pairs: int, paired_counts: list[int]) -> list[str]:
    missing = []
    max_pairs = max(paired_counts or [0])
    if max_pairs < min_pairs:
        missing.append(f"{min_pairs - max_pairs} more paired days before the pattern is trusted")
    if sleep_col is None:
        missing.append("sleep score or sleep duration is missing")
    if "stress_avg" not in df or not df["stress_avg"].notna().any():
        missing.append("next-day stress needs daily stress averages")
    if "hr_bedtime" not in df or int(df["hr_bedtime"].notna().sum()) < min_pairs:
        missing.append("more pre-sleep HR samples needed")
    if "hrv_overnight_avg" not in df or int(df["hrv_overnight_avg"].notna().sum()) < min_pairs:
        missing.append("more overnight HRV samples needed")
    if "cardio_load" not in df or int(df["cardio_load"].notna().sum()) < min_pairs:
        missing.append("more activity load samples needed")
    if "sleep_midpoint_variability_7d" not in df or int(df["sleep_midpoint_variability_7d"].notna().sum()) < min_pairs:
        missing.append("more sleep timing samples needed")
    return missing


def _add_bedtime_hr_delta(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("date").copy()
    if "hr_bedtime" not in out:
        out["bedtime_hr_delta"] = np.nan
        return out
    baseline = out["hr_bedtime"].rolling(30, min_periods=3).median().shift(1)
    out["bedtime_hr_baseline_30d"] = baseline
    out["bedtime_hr_delta"] = out["hr_bedtime"] - baseline
    return out


def _attach_sleep_regularity(df: pd.DataFrame, sleep_timing: pd.DataFrame | None) -> pd.DataFrame:
    out = df.copy()
    for col in (
        "bedtime_minute",
        "wake_time_minute",
        "sleep_midpoint_minute",
        "bedtime_variability_7d",
        "wake_time_variability_7d",
        "sleep_midpoint_variability_7d",
    ):
        out[col] = np.nan
    if sleep_timing is None or sleep_timing.empty or "date" not in sleep_timing:
        return out

    t = sleep_timing.copy()
    t["date"] = pd.to_datetime(t["date"], errors="coerce").dt.normalize()
    for col in ("sleep_start", "sleep_end", "sleep_midpoint"):
        if col in t:
            t[col] = pd.to_datetime(t[col], errors="coerce")
    t = t.dropna(subset=["date", "sleep_start", "sleep_end", "sleep_midpoint"])
    if t.empty:
        return out

    t["bedtime_minute"] = t["sleep_start"].map(_bedtime_minute)
    t["wake_time_minute"] = t["sleep_end"].map(_wake_time_minute)
    t["sleep_midpoint_minute"] = t["sleep_midpoint"].map(_minute_of_day)
    t = t.sort_values("date")
    for src, dst in (
        ("bedtime_minute", "bedtime_variability_7d"),
        ("wake_time_minute", "wake_time_variability_7d"),
        ("sleep_midpoint_minute", "sleep_midpoint_variability_7d"),
    ):
        t[dst] = t[src].rolling(7, min_periods=3).std()

    keep = [
        "date",
        "bedtime_minute",
        "wake_time_minute",
        "sleep_midpoint_minute",
        "bedtime_variability_7d",
        "wake_time_variability_7d",
        "sleep_midpoint_variability_7d",
    ]
    out = out.merge(t[keep], on="date", how="left", suffixes=("", "_timing"))
    for col in keep[1:]:
        timing_col = f"{col}_timing"
        if timing_col in out:
            out[col] = out[timing_col].combine_first(out[col])
            out = out.drop(columns=[timing_col])
    return out


def _minute_of_day(ts) -> float | None:
    if ts is None or pd.isna(ts):
        return None
    ts = pd.Timestamp(ts)
    return float(ts.hour * 60 + ts.minute + ts.second / 60.0)


def _bedtime_minute(ts) -> float | None:
    minute = _minute_of_day(ts)
    if minute is None:
        return None
    return minute + 1440 if minute < 12 * 60 else minute


def _wake_time_minute(ts) -> float | None:
    minute = _minute_of_day(ts)
    if minute is None:
        return None
    return minute - 1440 if minute > 12 * 60 else minute


def _add_activity_buckets(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["activity_bucket"] = None
    out["activity_bucket_code"] = np.nan
    if "cardio_load" not in out or not out["cardio_load"].notna().any():
        return out
    labels = ["very low", "low", "moderate", "high", "very high"]
    ranks = out["cardio_load"].rank(pct=True, method="average")
    codes = pd.Series(np.nan, index=out.index, dtype=float)
    codes = codes.mask(ranks <= 0.2, 0)
    codes = codes.mask((ranks > 0.2) & (ranks <= 0.4), 1)
    codes = codes.mask((ranks > 0.4) & (ranks <= 0.6), 2)
    codes = codes.mask((ranks > 0.6) & (ranks <= 0.8), 3)
    codes = codes.mask(ranks > 0.8, 4)
    out["activity_bucket_code"] = codes
    out["activity_bucket"] = codes.map(lambda c: labels[int(c)] if pd.notna(c) else None)
    return out


def _add_body_battery_recharge(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["body_battery_recharge"] = np.nan
    if {"body_battery_start", "body_battery_low"}.issubset(out.columns):
        start = pd.to_numeric(out["body_battery_start"], errors="coerce")
        low = pd.to_numeric(out["body_battery_low"], errors="coerce")
        out["body_battery_recharge"] = (start - low).clip(lower=0)
    return out


def _attach_cardio_load(df: pd.DataFrame, activities: pd.DataFrame | None) -> pd.DataFrame:
    out = df.copy()
    out["cardio_load"] = np.nan
    if activities is None or activities.empty or "date" not in activities:
        return out

    a = activities.dropna(subset=["date"]).copy()
    if a.empty:
        return out
    a["date"] = pd.to_datetime(a["date"], errors="coerce").dt.normalize()
    a = a.dropna(subset=["date"])
    if a.empty:
        return out

    if "training_load" in a and pd.to_numeric(a["training_load"], errors="coerce").notna().any():
        a["cardio_load"] = pd.to_numeric(a["training_load"], errors="coerce")
    elif {"duration_s", "avg_hr"}.issubset(a.columns):
        duration_min = pd.to_numeric(a["duration_s"], errors="coerce") / 60.0
        avg_hr = pd.to_numeric(a["avg_hr"], errors="coerce")
        a["cardio_load"] = duration_min * avg_hr / 100.0
    else:
        return out

    loads = a.dropna(subset=["cardio_load"]).groupby("date")["cardio_load"].sum()
    out = out.set_index("date")
    out["cardio_load"] = loads.reindex(out.index)
    return out.reset_index()


def _stress_sample_minutes(stress: pd.DataFrame) -> float:
    intervals = []
    if stress is None or stress.empty or "timestamp" not in stress:
        return 3.0
    for _, day in stress.sort_values("timestamp").groupby("date"):
        diffs = day["timestamp"].diff().dt.total_seconds().div(60).dropna()
        diffs = diffs[(diffs > 0) & (diffs <= 30)]
        intervals.extend(diffs.tolist())
    if not intervals:
        return 3.0
    return float(np.clip(np.median(intervals), 1.0, 15.0))


def _daily_recovery_impact(daily: pd.DataFrame) -> dict[str, int]:
    """Map load/stress date -> next-day recovery flag count."""
    if daily is None or daily.empty or "date" not in daily:
        return {}
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"])
    impact = {}
    for _, row in df.iterrows():
        flags = _latest_capacity_flags(row)
        if _ge(row.get("stress_avg"), 60):
            flags.append("next-day stress high")
        key = str((row["date"] - pd.Timedelta(days=1)).date())
        impact[key] = len(flags)
    return impact


def _time_impact_weight(start_min: int) -> float:
    center = (int(start_min) + 15) % 1440
    if center >= 21 * 60 or center < 60:
        return 24.0
    if center >= 20 * 60:
        return 18.0
    if center >= 18 * 60:
        return 10.0
    if 9 * 60 <= center < 17 * 60:
        return 5.0
    return 0.0


def _merge_stress_leak_buckets(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    windows = []
    for row in sorted(rows, key=lambda x: x["start_min"]):
        cur = dict(row)
        cur["_bucket_count"] = 1
        cur["_stress_sum"] = float(cur["avg_stress"])
        cur["_score_sum"] = float(cur["impact_score"])
        cur["_score_max"] = float(cur["impact_score"])
        prev_duration = windows[-1]["end_min"] - windows[-1]["start_min"] if windows else 0
        if windows and cur["start_min"] <= windows[-1]["end_min"] and prev_duration < 120:
            prev = windows[-1]
            prev["end_min"] = max(prev["end_min"], cur["end_min"])
            prev["_bucket_count"] += 1
            prev["_stress_sum"] += cur["_stress_sum"]
            prev["_score_sum"] += cur["_score_sum"]
            prev["_score_max"] = max(prev["_score_max"], cur["_score_max"])
            prev["avg_stress"] = prev["_stress_sum"] / prev["_bucket_count"]
            prev["avg_high_min"] += cur["avg_high_min"]
            prev["days_seen"] = max(prev["days_seen"], cur["days_seen"])
            prev["days_high"] = max(prev["days_high"], cur["days_high"])
            prev["recurrence"] = max(prev["recurrence"], cur["recurrence"])
            prev["next_flags"] = max(prev["next_flags"], cur["next_flags"])
            prev["impact_score"] = prev["_score_max"] + 0.2 * (
                prev["_score_sum"] - prev["_score_max"]
            )
        else:
            windows.append(cur)

    cleaned = []
    for window in windows:
        out = {k: v for k, v in window.items() if not k.startswith("_")}
        out["end_min"] = min(int(out["end_min"]), 1440)
        out["avg_stress"] = round(float(out["avg_stress"]), 1)
        out["avg_high_min"] = round(float(out["avg_high_min"]), 1)
        out["recurrence"] = round(float(out["recurrence"]), 2)
        out["next_flags"] = round(float(out["next_flags"]), 1)
        out["impact_score"] = int(round(float(out["impact_score"])))
        cleaned.append(out)
    return cleaned


def _stress_window_label(start_min: int, end_min: int) -> str:
    center = ((int(start_min) + int(end_min)) / 2) % 1440
    if center >= 21 * 60 or center < 60:
        return "pre-bed / evening"
    if center < 5 * 60:
        return "overnight"
    if center < 9 * 60:
        return "morning"
    if 9 * 60 <= center < 12 * 60:
        return "late morning / work block"
    if 12 * 60 <= center < 14 * 60:
        return "midday / meal-adjacent"
    if 14 * 60 <= center < 18 * 60:
        return "afternoon / work block"
    if 18 * 60 <= center < 21 * 60:
        return "evening"
    return "mixed day block"


def _fmt_clock(minute: int) -> str:
    minute = int(minute) % 1440
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _stress_leak_reason(window: dict) -> str:
    base = (
        f"Avg stress {_cap_like_num(window.get('avg_stress'))}, "
        f"{int(window.get('days_high') or 0)}/{int(window.get('days_seen') or 0)} days, "
        f"{_cap_like_num(window.get('avg_high_min'))} high-stress min/day."
    )
    if window.get("label") == "pre-bed / evening":
        return base + " Pre-bed timing gets extra recovery weight."
    if float(window.get("next_flags") or 0) >= 2:
        return base + " It often precedes multiple next-day recovery flags."
    return base


def _stress_leak_missing(stress: pd.DataFrame, day_count: int, min_days: int) -> list[str]:
    missing = []
    if day_count < min_days:
        missing.append(f"{min_days - day_count} more synced days before recurrence is trusted")
    if stress is None or stress.empty:
        return missing
    samples_per_day = stress.groupby("date").size()
    if not samples_per_day.empty and samples_per_day.median() < 60:
        missing.append("all-day stress samples are sparse")
    evening = stress[(stress["minute"] >= 21 * 60) & (stress["minute"] < 24 * 60)]
    if evening.empty:
        missing.append("no 21:00-00:00 stress samples yet")
    return missing


def _cap_like_num(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    n = float(value)
    return f"{n:,.0f}" if abs(n) >= 1000 or n.is_integer() else f"{n:.1f}"


def summarize(df: pd.DataFrame, activities: pd.DataFrame, lookback: int = 14) -> dict:
    """Compact, AI-ready summary of the most recent `lookback` days."""
    if df.empty:
        return {"error": "no data"}
    recent = df.tail(lookback)
    latest = df.iloc[-1]

    def f(x):
        return None if pd.isna(x) else round(float(x), 1)

    summary = {
        "as_of": str(latest["date"])[:10],
        "days_of_data": int(len(df)),
        "latest": {
            "resting_hr": f(latest.get("resting_hr")),
            "rhr_28d_baseline": f(latest.get("rhr_28d")),
            "rhr_elevated_vs_baseline": bool(latest.get("rhr_elevated"))
            if pd.notna(latest.get("rhr_elevated")) else None,
            "sleeping_hr_overnight_low": f(latest.get("hr_overnight_low")),
            "sleeping_hr_at_bedtime": f(latest.get("hr_bedtime")),
            "hrv_overnight": f(latest.get("hrv_overnight_avg")),
            "hrv_status": latest.get("hrv_status"),
            "hrv_flag": latest.get("hrv_flag"),
            "sleep_hours": f(latest.get("sleep_hours")),
            "sleep_score": f(latest.get("sleep_score")),
            "body_battery_high": f(latest.get("body_battery_high")),
            "stress_avg": f(latest.get("stress_avg")),
            "training_readiness": f(latest.get("training_readiness_score")),
            "acwr": f(latest.get("acwr")) if "acwr" in latest else None,
            "vo2max": f(latest.get("vo2max")),
        },
        "trends_14d": {
            "avg_sleep_hours": f(recent["sleep_hours"].mean()),
            "sleep_debt_total_h": f((config.SLEEP_NEED_HOURS - recent["sleep_hours"]).sum()),
            "avg_hrv": f(recent["hrv_overnight_avg"].mean()),
            "hrv_trend": _direction(recent["hrv_overnight_avg"]),
            "avg_rhr": f(recent["resting_hr"].mean()),
            "rhr_trend": _direction(recent["resting_hr"]),
            "avg_sleeping_hr_low": f(recent["hr_overnight_low"].mean())
            if "hr_overnight_low" in recent else None,
            "sleeping_hr_low_trend": _direction(recent["hr_overnight_low"])
            if "hr_overnight_low" in recent else "insufficient_data",
            "suppressed_hrv_days": int((recent.get("hrv_flag") == "suppressed").sum())
            if "hrv_flag" in recent else None,
            "avg_stress": f(recent["stress_avg"].mean()),
        },
    }
    if not activities.empty:
        a = activities.tail(20)
        summary["recent_activities"] = [
            {
                "date": str(r["date"])[:10],
                "type": r["type"],
                "duration_min": f(r["duration_s"] / 60.0) if pd.notna(r["duration_s"]) else None,
                "distance_km": f(r["distance_m"] / 1000.0) if pd.notna(r["distance_m"]) else None,
                "avg_hr": f(r["avg_hr"]),
                "training_load": f(r["training_load"]),
            }
            for _, r in a.iterrows()
        ]
    return summary


def _is_grappling_activity(record: dict) -> bool:
    text = f"{record.get('name') or ''} {record.get('type') or ''}".lower()
    return any(p in text for p in GRAPPLING_PATTERNS)


def _parse_activity_hr_samples(payload) -> pd.DataFrame:
    records = []
    if not payload:
        return pd.DataFrame(columns=["t_s", "hr"])

    descriptor_map = _activity_metric_descriptor_map(payload)

    def add_point(t, hr):
        h = _first_number(hr)
        ts = _activity_time_seconds(t)
        if h is None or ts is None:
            return
        if 30 <= h <= 240:
            records.append({"raw_t": ts, "hr": h})

    def parse_named_array(value):
        if not isinstance(value, list):
            return
        for sample in value:
            if isinstance(sample, (list, tuple)) and len(sample) >= 2:
                add_point(sample[0], sample[1])
            elif isinstance(sample, dict):
                add_point(
                    _first_present(sample, "timestamp", "timestampGMT", "timestampLocal",
                                   "directTimestamp", "elapsedDuration", "sumDuration", "time"),
                    _first_present(sample, "heartRate", "heartRateValue", "heartRateBpm",
                                   "averageHR", "hr"),
                )

    def parse_metrics_list(metrics):
        if not isinstance(metrics, list) or not descriptor_map:
            return
        by_index = {}
        for m in metrics:
            if not isinstance(m, dict):
                continue
            idx = _first_present(m, "metricsIndex", "metricIndex", "index")
            val = _first_present(m, "value", "metricsValue", "metricValue")
            if idx is not None:
                by_index[int(idx)] = val
        time_val = None
        hr_val = None
        for idx, key in descriptor_map.items():
            low = key.lower()
            if time_val is None and (
                "timestamp" in low or "duration" in low or low in ("time", "elapsedtime")
            ):
                time_val = by_index.get(idx)
            if hr_val is None and "heart" in low and "rate" in low:
                hr_val = by_index.get(idx)
        add_point(time_val, hr_val)

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                low = str(key).lower()
                if low in ("heartratevalues", "heartratevaluesarray", "heartratevaluelist"):
                    parse_named_array(value)
                elif low == "metrics":
                    parse_metrics_list(value)
                elif isinstance(value, (dict, list)):
                    walk(value)
            add_point(
                _first_present(node, "timestamp", "timestampGMT", "timestampLocal",
                               "directTimestamp", "elapsedDuration", "sumDuration", "time"),
                _first_present(node, "heartRate", "heartRateValue", "heartRateBpm",
                               "averageHR", "hr"),
            )
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    if not records:
        return pd.DataFrame(columns=["t_s", "hr"])

    out = pd.DataFrame(records)
    out = out.dropna(subset=["raw_t", "hr"]).sort_values("raw_t")
    out["t_s"] = out["raw_t"] - out["raw_t"].min()
    out = out.drop_duplicates("t_s")
    return out[["t_s", "hr"]].reset_index(drop=True)


def _activity_metric_descriptor_map(payload) -> dict[int, str]:
    mapping = {}

    def walk(node):
        if isinstance(node, dict):
            idx = _first_present(node, "metricsIndex", "metricIndex", "index")
            key = _first_present(node, "key", "metricKey", "name", "displayName")
            if idx is not None and key is not None:
                try:
                    mapping[int(idx)] = str(key)
                except (TypeError, ValueError):
                    pass
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return mapping


def _activity_time_seconds(value):
    if value is None or isinstance(value, (list, tuple, dict)):
        return None
    if pd.isna(value):
        return None
    if isinstance(value, str):
        ts = pd.to_datetime(value, errors="coerce")
        if pd.notna(ts):
            return ts.timestamp()
        try:
            return float(value)
        except ValueError:
            return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 1_000_000_000_000:
        return v / 1000.0
    return v


def _detect_grappling_rounds(hr: pd.DataFrame) -> dict:
    if hr is None or hr.empty or len(hr) < 8:
        return {
            "available": False, "rounds": [], "threshold_hr": None,
            "poor_recovery_rounds": None, "avg_recovery_drop": None,
        }

    s = hr.sort_values("t_s").copy()
    smooth = s["hr"].rolling(5, center=True, min_periods=1).median()
    peak = float(smooth.max())
    avg = float(smooth.mean())
    if peak < 145:
        return {
            "available": True, "rounds": [], "threshold_hr": 140.0,
            "poor_recovery_rounds": 0, "avg_recovery_drop": None,
        }

    threshold = max(140.0, min(peak - 8.0, avg + 0.42 * (peak - avg)))
    sample_dt = _sample_dt_seconds(s["t_s"])
    segments = []
    start = None
    end = None
    for t, h in zip(s["t_s"], smooth):
        if h >= threshold:
            if start is None:
                start = float(t)
            end = float(t)
        elif start is not None:
            segments.append([start, end + sample_dt])
            start = end = None
    if start is not None:
        segments.append([start, end + sample_dt])

    merged = []
    for seg in segments:
        if merged and seg[0] - merged[-1][1] <= 45:
            merged[-1][1] = seg[1]
        else:
            merged.append(seg)

    rounds = []
    for start_s, end_s in merged:
        if end_s - start_s < 90:
            continue
        window = s[(s["t_s"] >= start_s) & (s["t_s"] <= end_s)]
        if window.empty:
            continue
        rounds.append({
            "start_s": round(float(start_s), 1),
            "end_s": round(float(end_s), 1),
            "duration_s": round(float(end_s - start_s), 1),
            "peak_hr": round(float(window["hr"].max()), 1),
            "avg_hr": round(float(window["hr"].mean()), 1),
        })

    drops = []
    poor = 0
    for i in range(len(rounds) - 1):
        gap = s[(s["t_s"] > rounds[i]["end_s"]) & (s["t_s"] < rounds[i + 1]["start_s"])]
        if gap.empty:
            continue
        end_zone = s[(s["t_s"] >= rounds[i]["end_s"] - 30) & (s["t_s"] <= rounds[i]["end_s"])]
        end_hr = float(end_zone["hr"].median()) if not end_zone.empty else rounds[i]["peak_hr"]
        low_gap = float(gap["hr"].min())
        drop = max(0.0, end_hr - low_gap)
        drops.append(drop)
        if drop < 12:
            poor += 1

    return {
        "available": True,
        "rounds": rounds,
        "threshold_hr": round(float(threshold), 1),
        "poor_recovery_rounds": poor,
        "avg_recovery_drop": float(np.mean(drops)) if drops else None,
    }


def _time_above_threshold(hr: pd.DataFrame, threshold) -> float | None:
    if hr is None or hr.empty or threshold is None:
        return None
    sample_dt = _sample_dt_seconds(hr["t_s"])
    return float((hr["hr"] >= threshold).sum() * sample_dt / 60.0)


def _sample_dt_seconds(times: pd.Series) -> float:
    diffs = pd.Series(times).sort_values().diff().dropna()
    diffs = diffs[(diffs > 0) & (diffs <= 120)]
    if diffs.empty:
        return 15.0
    return float(diffs.median())


def _parse_high_zone_minutes(payload) -> float | None:
    if not payload:
        return None
    minutes = []

    def add_duration(zone, value, key=""):
        if zone is None or zone < 4 or value is None:
            return
        mins = _duration_to_minutes(value, key)
        if mins is not None and mins >= 0:
            minutes.append(mins)

    def zone_from_key(key):
        import re
        m = re.search(r"zone[\s_-]*([1-5])", str(key).lower())
        return int(m.group(1)) if m else None

    def zone_from_value(value):
        if value is None:
            return None
        if isinstance(value, str):
            z = zone_from_key(value)
            if z is not None:
                return z
        try:
            z = int(value)
        except (TypeError, ValueError):
            return None
        return z if 1 <= z <= 5 else None

    def duration_from_dict(node):
        for key in (
            "duration", "durationS", "durationSeconds", "seconds", "timeInZone",
            "timeInZoneSeconds", "zoneTime", "zoneTimeSeconds", "value",
        ):
            if key in node and node[key] is not None:
                return key, node[key]
        return "", None

    def walk(node, list_zone=None):
        if isinstance(node, dict):
            zone = (
                zone_from_value(_first_present(node, "zoneNumber", "zone", "zoneIndex", "hrZone"))
                or list_zone
            )
            key, duration = duration_from_dict(node)
            add_duration(zone, duration, key)
            for key, value in node.items():
                key_zone = zone_from_key(key)
                if isinstance(value, (int, float)):
                    add_duration(key_zone, value, key)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        inferred = key_zone
                        if inferred is None and "zone" in str(key).lower():
                            inferred = i + 1
                        walk(item, inferred)
                elif isinstance(value, dict):
                    walk(value, key_zone)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, i + 1)

    walk(payload)
    return float(sum(minutes)) if minutes else None


def _duration_to_minutes(value, key=""):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    low = str(key).lower()
    if "minute" in low:
        return v
    if v > 24 * 60 * 60:
        return v / 1000.0 / 60.0
    return v / 60.0


def _activity_duration_minutes(rec: dict, hr: pd.DataFrame) -> float | None:
    dur = _first_number(rec.get("duration_s"))
    if dur is not None:
        return dur / 60.0
    if hr is not None and not hr.empty:
        return float((hr["t_s"].max() - hr["t_s"].min()) / 60.0)
    return None


def _classify_grappling_session(round_count, high_min, peak_hr, duration_min, has_hr_detail):
    if not has_hr_detail:
        return "summary only", "low"
    rc = round_count or 0
    high = high_min or 0
    peak = peak_hr or 0
    dur = duration_min or 0
    high_share = high / dur if dur > 0 else 0
    if rc >= 3 and (high >= 10 or peak >= 170 or high_share >= 0.25):
        return "rolling", "high" if rc >= 4 and high >= 12 else "medium"
    if rc <= 1 and high < 5 and peak < 150:
        return "drilling", "high"
    return "mixed", "medium"


def _mat_stress_cost(duration_min, high_min, peak_hr, round_count, poor_recovery_rounds) -> float:
    dur = duration_min or 0
    high = high_min or 0
    peak = peak_hr or 0
    rounds = round_count or 0
    poor = poor_recovery_rounds or 0
    score = 0.18 * dur + 1.4 * high + 5.0 * rounds + 8.0 * poor + max(0, peak - 150) * 0.5
    return max(0.0, min(100.0, score))


def _grappling_next_day_impact(daily: pd.DataFrame, date_value) -> dict:
    if daily is None or daily.empty or date_value is None or pd.isna(date_value):
        return {"available": False, "flags": [], "message": "No next-day recovery data yet."}
    d = pd.to_datetime(str(date_value)[:10], errors="coerce")
    if pd.isna(d):
        return {"available": False, "flags": [], "message": "No next-day recovery data yet."}
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    row = df[df["date"] == (d.normalize() + pd.Timedelta(days=1))]
    if row.empty:
        return {"available": False, "flags": [], "message": "No next-day recovery data yet."}
    latest = row.iloc[0]
    flags = _latest_capacity_flags(latest)
    metrics = {
        "date": str(latest["date"])[:10],
        "hrv_flag": latest.get("hrv_flag"),
        "resting_hr": _round_or_none(latest.get("resting_hr"), 0),
        "rhr_elevated": bool(latest.get("rhr_elevated")) if pd.notna(latest.get("rhr_elevated")) else None,
        "sleep_hours": _round_or_none(latest.get("sleep_hours"), 1),
        "body_battery_current": _round_or_none(latest.get("body_battery_current"), 0),
        "stress_avg": _round_or_none(latest.get("stress_avg"), 0),
    }
    msg = "Next-day recovery looks stable." if not flags else "Next-day flags: " + ", ".join(flags[:4]) + "."
    return {"available": True, "flags": flags, "metrics": metrics, "message": msg}


def _grappling_warning(mat_cost, next_day: dict) -> str | None:
    flags = next_day.get("flags") or []
    if mat_cost >= 85:
        return "You cooked yourself: mat stress was very high."
    if mat_cost >= 70 and flags:
        return "You cooked yourself: high mat stress stacked with poor next-day recovery."
    if mat_cost >= 55 and len(flags) >= 2:
        return "Grappling cost was moderate-high and recovery markers are not clean."
    return None


def _recovery_quality(round_info: dict) -> str:
    if not round_info.get("available"):
        return "unavailable"
    rounds = round_info.get("rounds") or []
    if len(rounds) < 2:
        return "not enough rounds"
    poor = round_info.get("poor_recovery_rounds") or 0
    drop = round_info.get("avg_recovery_drop")
    if poor == 0 and drop is not None and drop >= 20:
        return "good"
    if poor <= 1 and drop is not None and drop >= 12:
        return "fair"
    return "poor"


def _first_present(obj: dict, *keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None


def _first_number(*values):
    for value in values:
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _round_or_none(value, digits=1):
    value = _first_number(value)
    if value is None:
        return None
    if digits == 0:
        return int(round(value))
    return round(value, digits)


def _attach_activity_load(df: pd.DataFrame, activities: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["activity_load"] = np.nan
    if activities is None or activities.empty or "training_load" not in activities:
        return out
    a = activities.dropna(subset=["date"]).copy()
    if a.empty or not a["training_load"].notna().any():
        return out
    a["date"] = pd.to_datetime(a["date"]).dt.normalize()
    loads = a.groupby("date")["training_load"].sum()
    out = out.set_index("date")
    out["activity_load"] = loads.reindex(out.index)
    return out.reset_index()


def _attach_checkins(df: pd.DataFrame, checkins: pd.DataFrame) -> pd.DataFrame:
    if checkins is None or checkins.empty:
        for col in ("pain", "fatigue", "energy", "note"):
            df[col] = np.nan if col != "note" else None
        return df
    c = checkins.copy()
    c["date"] = pd.to_datetime(c["date"]).dt.normalize()
    cols = [x for x in ("date", "pain", "fatigue", "energy", "note") if x in c]
    return df.merge(c[cols], on="date", how="left")


def _capacity_response_flags(df: pd.DataFrame) -> dict:
    flag_count = pd.Series(0, index=df.index, dtype=int)

    def add(mask):
        nonlocal flag_count
        flag_count = flag_count + mask.fillna(False).astype(int)

    add(df.get("hrv_flag", pd.Series(index=df.index, dtype=object)).eq("suppressed"))
    add(df.get("rhr_elevated", pd.Series(False, index=df.index)).fillna(False).astype(bool))
    if "sleep_hours" in df:
        add(df["sleep_hours"] < (config.SLEEP_NEED_HOURS - 1.0))
    if "body_battery_current" in df:
        add(df["body_battery_current"] < 35)
    if "pain" in df:
        add(df["pain"] >= 6)
    if "fatigue" in df:
        add(df["fatigue"] >= 7)
    if "energy" in df:
        add(df["energy"] <= 3)

    poor = flag_count >= 2
    if "pain" in df:
        poor = poor | (df["pain"] >= 7).fillna(False)
    if "fatigue" in df:
        poor = poor | (df["fatigue"] >= 8).fillna(False)
    if "energy" in df:
        poor = poor | (df["energy"] <= 2).fillna(False)
    return {"poor": poor.astype(bool), "flag_count": flag_count}


def _capacity_metrics(history: pd.DataFrame, latest: pd.Series) -> list[dict]:
    specs = [
        ("steps", "Steps", "steps", 100),
        ("intensity_minutes", "Active minutes", "min", 5),
        ("activity_load", "Activity load", "load", 5),
        ("stress_high_minutes", "High-stress minutes", "min", 5),
    ]
    metrics = []
    for col, label, unit, step in specs:
        current = _clean_num(latest.get(col))
        vals = history[col].dropna() if col in history else pd.Series(dtype=float)
        if col == "activity_load":
            vals = vals[vals > 0]
        vals = vals.astype(float)
        lo = hi = None
        samples = int(len(vals))
        if samples >= 3:
            lo = _round_to(vals.quantile(0.25), step)
            hi = _round_to(vals.quantile(0.75), step)
            if hi is not None and lo is not None and hi < lo:
                hi = lo
        excess = None
        if current is not None and hi is not None and hi > 0:
            excess = max(0.0, (current / hi) - 1.0)
        metrics.append({
            "key": col,
            "label": label,
            "unit": unit,
            "current": current,
            "low": lo,
            "high": hi,
            "samples": samples,
            "excess_ratio": excess,
        })
    return metrics


def _latest_capacity_flags(latest: pd.Series) -> list[str]:
    flags = []
    if latest.get("hrv_flag") == "suppressed":
        flags.append("HRV suppressed")
    if bool(latest.get("rhr_elevated")) if pd.notna(latest.get("rhr_elevated")) else False:
        flags.append("resting HR elevated")
    if _lt(latest.get("sleep_hours"), config.SLEEP_NEED_HOURS - 1.0):
        flags.append("short sleep")
    if _lt(latest.get("body_battery_current"), 35):
        flags.append("low Body Battery")
    if _ge(latest.get("pain"), 6):
        flags.append("pain check-in high")
    if _ge(latest.get("fatigue"), 7):
        flags.append("fatigue check-in high")
    if _le(latest.get("energy"), 3):
        flags.append("energy check-in low")
    return flags


def _capacity_message(status, zone, metrics, max_excess, flags, learned_days, min_days) -> str:
    if status != "ready":
        return (
            f"Learning your capacity envelope: {learned_days}/{min_days} Garmin days logged. "
            "Add pain, fatigue, and energy ratings daily; after two weeks this will start "
            "giving personal activity ceilings."
        )

    pieces = []
    for key in ("steps", "intensity_minutes", "activity_load", "stress_high_minutes"):
        m = next((x for x in metrics if x["key"] == key), None)
        if m and m["low"] is not None and m["high"] is not None:
            label = m["label"].lower()
            pieces.append(
                f"{label}: {_fmt_metric(m['low'])}-{_fmt_metric(m['high'])} {m['unit']}".strip()
            )
    envelope = ", ".join(pieces[:3]) if pieces else "a conservative range"
    if max_excess > 0:
        load_text = f"The latest synced day exceeded that by {max_excess * 100:.0f}%."
    else:
        load_text = "The latest synced day stayed inside that range."
    if flags:
        response = "Recovery response is cautious: " + ", ".join(flags[:3]) + "."
    else:
        response = "Recovery response looks stable."
    zone_text = {
        "green": "Green zone",
        "yellow": "Yellow zone",
        "red": "Red zone",
    }.get(zone, "Learning")
    return f"{zone_text}: your current stable envelope seems to be {envelope}. {load_text} {response}"


def _capacity_missing(df: pd.DataFrame, activities: pd.DataFrame) -> list[str]:
    missing = []
    if "stress_high_minutes" not in df or not df["stress_high_minutes"].notna().any():
        missing.append("high-stress minutes need a fresh sync with the updated ingester")
    if activities is None or activities.empty or "training_load" not in activities:
        missing.append("activity load unavailable until activities sync")
    if "body_battery_start" not in df or not df["body_battery_start"].notna().any():
        missing.append("Body Battery start is not present in current Garmin payloads")
    missing.append("late high-stress after 20:00 is not available from the current aggregate endpoint")
    return missing


def _clean_num(x):
    return None if x is None or pd.isna(x) else float(x)


def _round_to(x, step):
    if x is None or pd.isna(x):
        return None
    if step <= 1:
        return round(float(x), 1)
    return int(round(float(x) / step) * step)


def _fmt_metric(x):
    if x is None:
        return "-"
    if abs(float(x)) >= 1000:
        return f"{float(x):,.0f}"
    return f"{float(x):.0f}"


def _ge(x, threshold):
    return x is not None and pd.notna(x) and float(x) >= threshold


def _le(x, threshold):
    return x is not None and pd.notna(x) and float(x) <= threshold


def _lt(x, threshold):
    return x is not None and pd.notna(x) and float(x) < threshold


def _direction(series: pd.Series) -> str:
    s = series.dropna()
    if len(s) < 4:
        return "insufficient_data"
    half = len(s) // 2
    early, late = s.iloc[:half].mean(), s.iloc[half:].mean()
    if late > early * 1.03:
        return "rising"
    if late < early * 0.97:
        return "falling"
    return "stable"


# ── Strength training (pure analytics; no I/O) ────────────────────────────────
def estimate_1rm(weight, reps, formula="epley"):
    """Estimated one-rep max from a working set. Epley default; Brzycki optional.

    Returns None for non-positive weight/reps or unparseable input.
    """
    try:
        w = float(weight)
        r = int(reps)
    except (TypeError, ValueError):
        return None
    if w <= 0 or r <= 0:
        return None
    if r == 1:
        return w
    if formula == "brzycki":
        if r >= 37:
            return None
        return w * 36.0 / (37.0 - r)
    return w * (1.0 + r / 30.0)  # epley


def enrich_strength_sets(sets_df, sessions_df, exercises_df, formula="epley"):
    """Add effective_load_kg and est_1rm_kg to a sets DataFrame.

    Bodyweight exercises use the session's snapshot bodyweight_kg + added load
    so historical numbers stay stable. Warmup sets get no 1RM. Pure.
    """
    if sets_df is None or sets_df.empty:
        base_cols = list(sets_df.columns) if sets_df is not None else []
        return pd.DataFrame(columns=base_cols + ["effective_load_kg", "est_1rm_kg"])

    df = sets_df.copy()
    bw = (sessions_df[["session_id", "bodyweight_kg"]]
          if sessions_df is not None and not sessions_df.empty
          else pd.DataFrame(columns=["session_id", "bodyweight_kg"]))
    df = df.merge(bw, on="session_id", how="left")
    isbw = (exercises_df[["exercise_id", "is_bodyweight"]]
            if exercises_df is not None and not exercises_df.empty
            else pd.DataFrame(columns=["exercise_id", "is_bodyweight"]))
    df = df.merge(isbw, on="exercise_id", how="left", suffixes=("", "_ex"))

    df["is_bodyweight"] = pd.to_numeric(df.get("is_bodyweight"), errors="coerce").fillna(0).astype(int)
    body = pd.to_numeric(df.get("bodyweight_kg"), errors="coerce").fillna(0.0)
    added = pd.to_numeric(df.get("weight_kg"), errors="coerce").fillna(0.0)
    df["effective_load_kg"] = added + df["is_bodyweight"] * body

    warm = pd.to_numeric(
        df["is_warmup"] if "is_warmup" in df.columns else pd.Series(0, index=df.index),
        errors="coerce").fillna(0).astype(int)

    def _row_1rm(i):
        if warm.iloc[i] == 1:
            return None
        return estimate_1rm(df["effective_load_kg"].iloc[i], df["reps"].iloc[i], formula)

    df["est_1rm_kg"] = [_row_1rm(i) for i in range(len(df))]
    return df


def summarize_sessions(sessions_df, sets_df, exercises_df, formula="epley"):
    """Per-session tonnage, working-set count, and top est-1RM. Pure."""
    cols = ["session_id", "date", "total_volume_kg", "working_sets", "top_est_1rm_kg"]
    if sessions_df is None or sessions_df.empty:
        return pd.DataFrame(columns=cols)

    enr = enrich_strength_sets(sets_df, sessions_df, exercises_df, formula)
    if not enr.empty:
        warm = pd.to_numeric(
            enr["is_warmup"] if "is_warmup" in enr.columns else pd.Series(0, index=enr.index),
            errors="coerce").fillna(0).astype(int)
        done = pd.to_numeric(
            enr["completed"] if "completed" in enr.columns else pd.Series(1, index=enr.index),
            errors="coerce").fillna(1).astype(int)
        work = enr[(warm == 0) & (done == 1)]
    else:
        work = enr

    rows = []
    for _, s in sessions_df.iterrows():
        sid = s["session_id"]
        ss = work[work["session_id"] == sid] if not work.empty else work
        if ss.empty:
            rows.append({"session_id": sid, "date": s.get("date"),
                         "total_volume_kg": 0.0, "working_sets": 0,
                         "top_est_1rm_kg": None})
            continue
        reps = pd.to_numeric(ss["reps"], errors="coerce").fillna(0)
        load = pd.to_numeric(ss["effective_load_kg"], errors="coerce").fillna(0)
        tonnage = float((reps * load).sum())
        top = pd.to_numeric(ss["est_1rm_kg"], errors="coerce").max()
        rows.append({"session_id": sid, "date": s.get("date"),
                     "total_volume_kg": tonnage, "working_sets": int(len(ss)),
                     "top_est_1rm_kg": (None if pd.isna(top) else float(top))})
    return pd.DataFrame(rows, columns=cols)


def compute_pr_timeline(sets_df, sessions_df, exercises_df, formula="epley"):
    """Best est-1RM per exercise per session over time, with a PR flag. Pure."""
    cols = ["exercise_id", "date", "session_id", "best_est_1rm_kg", "is_pr"]
    if (sessions_df is None or sessions_df.empty
            or sets_df is None or sets_df.empty):
        return pd.DataFrame(columns=cols)

    enr = enrich_strength_sets(sets_df, sessions_df, exercises_df, formula)
    enr = enr.merge(sessions_df[["session_id", "date"]], on="session_id",
                    how="left", suffixes=("", "_sess"))
    enr = enr.dropna(subset=["est_1rm_kg"])
    if enr.empty:
        return pd.DataFrame(columns=cols)

    grp = (enr.groupby(["exercise_id", "session_id", "date"], as_index=False)
              ["est_1rm_kg"].max()
              .rename(columns={"est_1rm_kg": "best_est_1rm_kg"}))
    grp = grp.sort_values(["exercise_id", "date"])
    grp["prev_max"] = grp.groupby("exercise_id")["best_est_1rm_kg"].cummax().shift(1)
    # cummax().shift(1) leaks across exercises at the boundary; re-mask first row
    grp["is_first"] = ~grp.duplicated("exercise_id")
    grp["is_pr"] = grp["is_first"] | (grp["best_est_1rm_kg"] > grp["prev_max"])
    return grp[cols].reset_index(drop=True)


def readiness_snapshot_from_daily(daily_row):
    """Map an enriched daily-metrics row -> session readiness snapshot dict.

    daily_row may be a pandas Series, a dict, or None. Returns the eight
    snapshot keys, None where missing/NaN. Pure — caller does the DB read/write.
    """
    def g(key):
        if daily_row is None:
            return None
        try:
            val = daily_row[key]
        except (KeyError, IndexError, TypeError):
            return None
        if val is None:
            return None
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        return val

    return {
        "readiness_score": g("training_readiness_score"),
        "readiness_level": g("training_readiness_level"),
        "hrv_status": g("hrv_status"),
        "hrv_overnight_avg": g("hrv_overnight_avg"),
        "body_battery_start": g("body_battery_start"),
        "sleep_score": g("sleep_score"),
        "resting_hr": g("resting_hr"),
        "acwr": g("acwr"),
    }


def compute_strength_standards(best_1rm_by_exercise, profile, bodyweight_kg):
    """Grade main-lift est-1RMs against population norms (ratio table). Pure.

    best_1rm_by_exercise: {exercise_id: best_est_1rm_kg}. Returns
    {status:'ok', lifts:[...], overall:{level,percentile}, graded_lifts:n} or a
    {status:'need_profile'/'no_main_lifts'} marker.
    """
    import strength_standards as ss
    profile = profile or {}
    sex = (profile.get("sex") or "").strip().lower()
    missing = []
    if sex not in ss.STANDARDS:
        missing.append("sex")
    try:
        bw = float(bodyweight_kg)
    except (TypeError, ValueError):
        bw = 0.0
    if bw <= 0:
        missing.append("bodyweight")
    if missing:
        return {"status": "need_profile", "missing": missing}

    best_map = best_1rm_by_exercise or {}
    lifts = []
    for ex_id, thr in ss.STANDARDS[sex].items():
        try:
            best = float(best_map.get(ex_id))
        except (TypeError, ValueError):
            continue
        if best <= 0:
            continue
        ratio = best / bw
        nov, inter, adv, eli = thr
        if ratio < nov:
            level, lo, hi = "Untrained", 0.0, nov
        elif ratio < inter:
            level, lo, hi = "Novice", nov, inter
        elif ratio < adv:
            level, lo, hi = "Intermediate", inter, adv
        elif ratio < eli:
            level, lo, hi = "Advanced", adv, eli
        else:
            level, lo, hi = "Elite", eli, eli * 1.25
        plo, phi = ss.LEVEL_PERCENTILE_BANDS[level]
        frac = 1.0 if hi <= lo else (ratio - lo) / (hi - lo)
        frac = min(max(frac, 0.0), 1.0)
        pct = round(plo + frac * (phi - plo), 1)
        lifts.append({
            "exercise_id": ex_id, "name": ss.MAIN_LIFT_NAMES.get(ex_id, ex_id),
            "est_1rm_kg": round(best, 1), "ratio": round(ratio, 2),
            "level": level, "percentile": pct,
        })

    if not lifts:
        return {"status": "no_main_lifts", "lifts": [], "overall": None,
                "graded_lifts": 0}
    mean_pct = sum(l["percentile"] for l in lifts) / len(lifts)
    overall_level = "Elite"
    for lv in ss.LEVELS:
        if mean_pct < ss.LEVEL_PERCENTILE_BANDS[lv][1]:
            overall_level = lv
            break
    return {"status": "ok", "lifts": lifts,
            "overall": {"level": overall_level, "percentile": round(mean_pct, 1)},
            "graded_lifts": len(lifts)}


def _left_right_asymmetry(sets_df, exercises_df, flag_pct, formula="epley"):
    if (sets_df is None or sets_df.empty
            or exercises_df is None or exercises_df.empty
            or "is_unilateral" not in exercises_df.columns
            or "side" not in sets_df.columns):
        return []
    uni = exercises_df[pd.to_numeric(exercises_df["is_unilateral"], errors="coerce")
                       .fillna(0).astype(int) == 1]
    if uni.empty:
        return []
    uni_ids = set(uni["exercise_id"])
    name_map = dict(zip(exercises_df["exercise_id"], exercises_df["name"]))

    df = sets_df.copy()
    for col, default in (("is_warmup", 0), ("completed", 1)):
        if col not in df.columns:
            df[col] = default
    warm = pd.to_numeric(df["is_warmup"], errors="coerce").fillna(0).astype(int)
    done = pd.to_numeric(df["completed"], errors="coerce").fillna(1).astype(int)
    df = df[(warm == 0) & (done == 1) & df["exercise_id"].isin(uni_ids)]
    if df.empty:
        return []

    out = []
    for ex_id, grp in df.groupby("exercise_id"):
        best = {}
        for side in ("left", "right"):
            sub = grp[grp["side"] == side]
            vals = [estimate_1rm(w, r, formula) for w, r in zip(sub["weight_kg"], sub["reps"])]
            vals = [v for v in vals if v is not None]
            if vals:
                best[side] = max(vals)
        if "left" in best and "right" in best:
            l, r = best["left"], best["right"]
            hi = max(l, r)
            diff = abs(l - r) / hi * 100 if hi > 0 else 0.0
            out.append({
                "name": name_map.get(ex_id, ex_id),
                "left_1rm_kg": round(l, 1), "right_1rm_kg": round(r, 1),
                "diff_pct": round(diff, 1), "flagged": bool(diff > flag_pct),
                "stronger_side": "left" if l > r else ("right" if r > l else "even"),
            })
    return out


def compute_balance(best_1rm_by_exercise, sets_df, exercises_df, formula="epley"):
    """Cross-movement strength ratios + left/right asymmetry. Pure."""
    import strength_standards as ss
    best_map = best_1rm_by_exercise or {}
    ratios = []
    for t in ss.BALANCE_TARGETS:
        try:
            num = float(best_map.get(t["numerator"]))
            den = float(best_map.get(t["denominator"]))
        except (TypeError, ValueError):
            continue
        if num <= 0 or den <= 0:
            continue
        r = num / den
        if r < t["low"]:
            status, weak = "under", t["numerator"]
        elif r > t["high"]:
            status, weak = "over", t["denominator"]
        else:
            status, weak = "ok", None
        ratios.append({"label": t["label"], "ratio": round(r, 2),
                       "low": t["low"], "ideal": t["ideal"], "high": t["high"],
                       "status": status, "weak_side": weak, "reason": t["reason"]})
    return {"ratios": ratios,
            "left_right": _left_right_asymmetry(sets_df, exercises_df,
                                                ss.ASYMMETRY_FLAG_PCT, formula)}


def compute_readiness_performance(sessions_df, sets_df, exercises_df, min_sessions=8,
                                  formula="epley"):
    """Correlate the per-session readiness snapshot with normalized lifting
    performance (day-best est-1RM ÷ all-time-best, averaged over the day's
    lifts). Gated until `min_sessions` readiness-tagged sessions exist. Pure.
    """
    insufficient = {"status": "insufficient", "have": 0, "need": min_sessions}
    if (sessions_df is None or sessions_df.empty
            or sets_df is None or sets_df.empty):
        return insufficient
    enr = enrich_strength_sets(sets_df, sessions_df, exercises_df, formula)
    if enr.empty or "est_1rm_kg" not in enr.columns:
        return insufficient
    work = enr
    if "is_warmup" in work.columns:
        work = work[pd.to_numeric(work["is_warmup"], errors="coerce").fillna(0).astype(int) == 0]
    if "completed" in work.columns:
        work = work[pd.to_numeric(work["completed"], errors="coerce").fillna(1).astype(int) == 1]
    work = work.dropna(subset=["est_1rm_kg"])
    if work.empty:
        return insufficient

    all_best = work.groupby("exercise_id")["est_1rm_kg"].max().to_dict()
    day = (work.groupby(["session_id", "exercise_id"])["est_1rm_kg"].max()
               .reset_index())
    day["rel"] = day.apply(
        lambda r: (r["est_1rm_kg"] / all_best[r["exercise_id"]])
        if all_best.get(r["exercise_id"]) else None, axis=1)
    day["is_pr_today"] = day.apply(
        lambda r: abs(r["est_1rm_kg"] - all_best.get(r["exercise_id"], 0)) < 1e-9,
        axis=1)
    sess = (day.groupby("session_id")
               .agg(rel_perf=("rel", "mean"), pr=("is_pr_today", "any"))
               .reset_index())

    ton = summarize_sessions(sessions_df, sets_df, exercises_df, formula)[
        ["session_id", "total_volume_kg"]]
    rsc = sessions_df[["session_id", "readiness_score"]].copy()
    rsc["readiness_score"] = pd.to_numeric(rsc["readiness_score"], errors="coerce")
    merged = (sess.merge(rsc, on="session_id", how="left")
                  .merge(ton, on="session_id", how="left")
                  .dropna(subset=["readiness_score", "rel_perf"]))
    have = int(len(merged))
    if have < min_sessions:
        return {"status": "insufficient", "have": have, "need": min_sessions}

    def bucket(x):
        return "Low" if x < 50 else ("Med" if x <= 75 else "High")
    merged["bucket"] = merged["readiness_score"].apply(bucket)
    buckets = {}
    for b in ("Low", "Med", "High"):
        bb = merged[merged["bucket"] == b]
        if bb.empty:
            continue
        buckets[b] = {
            "n": int(len(bb)),
            "avg_rel_perf": round(float(bb["rel_perf"].mean()), 3),
            "pr_rate": round(float(bb["pr"].mean()), 2),
            "avg_tonnage": round(float(bb["total_volume_kg"].fillna(0).mean()), 0),
        }
    corr = merged["readiness_score"].corr(merged["rel_perf"])
    corr = None if pd.isna(corr) else round(float(corr), 2)
    if corr is not None and corr >= 0.3:
        insight = "You tend to hit better lifts on higher-readiness days."
    elif corr is not None and corr <= -0.3:
        insight = "Your best lifts cluster on lower-readiness days — readiness isn't limiting your lifting."
    else:
        insight = "No strong link between readiness and lifting performance so far."
    return {"status": "ok", "n": have, "buckets": buckets,
            "correlation": corr, "insight": insight}


def summarize_strength(sessions_df, sets_df, exercises_df, profile,
                       bodyweight_kg, lookback_days=28, formula="epley"):
    """Compact, raw-data-free strength summary for the AI coach. Pure."""
    if sessions_df is None or sessions_df.empty:
        return {"status": "no_data"}

    pr = compute_pr_timeline(sets_df, sessions_df, exercises_df, formula)
    best_map = (pr.groupby("exercise_id")["best_est_1rm_kg"].max().to_dict()
                if not pr.empty else {})
    standards = compute_strength_standards(best_map, profile, bodyweight_kg)
    balance = compute_balance(best_map, sets_df, exercises_df, formula)
    readiness_link = compute_readiness_performance(sessions_df, sets_df, exercises_df,
                                                   formula=formula)

    sdf = sessions_df.copy()
    sdf["date"] = pd.to_datetime(sdf["date"], errors="coerce")
    last = sdf["date"].max()
    cutoff = last - pd.Timedelta(days=lookback_days)
    recent = sdf[sdf["date"] >= cutoff]

    summ = summarize_sessions(sessions_df, sets_df, exercises_df, formula)
    recent_ids = set(recent["session_id"])
    recent_tonnage = (float(summ[summ["session_id"].isin(recent_ids)]
                            ["total_volume_kg"].sum()) if not summ.empty else 0.0)
    sessions_per_week = round(len(recent) / (lookback_days / 7.0), 1) if len(recent) else 0.0

    name_map = (dict(zip(exercises_df["exercise_id"], exercises_df["name"]))
                if exercises_df is not None and not exercises_df.empty else {})
    recent_prs = []
    if not pr.empty:
        p = pr.copy()
        p["date"] = pd.to_datetime(p["date"], errors="coerce")
        p = p[(p["is_pr"] == True) & (p["date"] >= cutoff)]  # noqa: E712
        for _, r in p.sort_values("date").iterrows():
            recent_prs.append({"exercise": name_map.get(r["exercise_id"], r["exercise_id"]),
                               "est_1rm_kg": round(float(r["best_est_1rm_kg"]), 1),
                               "date": str(r["date"].date())})

    if standards.get("status") == "ok":
        standards_out = {
            "overall": standards["overall"],
            "by_lift": [{"name": l["name"], "level": l["level"],
                         "percentile": l["percentile"]} for l in standards["lifts"]],
        }
    else:
        standards_out = {"status": standards.get("status")}

    if readiness_link.get("status") == "ok":
        readiness_out = {"status": "ok", "correlation": readiness_link.get("correlation"),
                         "insight": readiness_link.get("insight")}
    else:
        readiness_out = {"status": readiness_link.get("status"),
                         "have": readiness_link.get("have"),
                         "need": readiness_link.get("need")}

    return {
        "status": "ok",
        "recent": {"sessions": int(len(recent)), "tonnage_kg": round(recent_tonnage, 0),
                   "sessions_per_week": sessions_per_week, "lookback_days": lookback_days},
        "standards": standards_out,
        "balance_flags": {
            "ratios": [r for r in balance["ratios"] if r["status"] != "ok"],
            "left_right": [lr for lr in balance["left_right"] if lr["flagged"]],
        },
        "readiness_link": readiness_out,
        "recent_prs": recent_prs,
    }


def last_session_sets(exercise_id, sessions_df, sets_df):
    """Working sets (kg, reps) from the most recent saved session that included
    `exercise_id`, ordered by set_index, warmups excluded. Pure. [] if none.
    """
    if (sessions_df is None or sessions_df.empty
            or sets_df is None or sets_df.empty
            or "exercise_id" not in sets_df.columns):
        return []
    ex_sets = sets_df[sets_df["exercise_id"] == exercise_id]
    if ex_sets.empty:
        return []
    sdf = sessions_df[sessions_df["session_id"].isin(set(ex_sets["session_id"]))].copy()
    if sdf.empty:
        return []
    sort_cols = [c for c in ("date", "started_at") if c in sdf.columns]
    if sort_cols:
        sdf = sdf.sort_values(sort_cols)
    last_sid = sdf.iloc[-1]["session_id"]
    rows = ex_sets[ex_sets["session_id"] == last_sid].copy()
    if "is_warmup" in rows.columns:
        rows = rows[pd.to_numeric(rows["is_warmup"], errors="coerce").fillna(0).astype(int) == 0]
    if "completed" in rows.columns:
        rows = rows[pd.to_numeric(rows["completed"], errors="coerce").fillna(1).astype(int) == 1]
    if "set_index" in rows.columns:
        rows = rows.sort_values("set_index")
    out = []
    for _, r in rows.iterrows():
        w, reps = r["weight_kg"], r["reps"]
        if pd.isna(w) or pd.isna(reps):
            continue
        try:
            out.append({"weight_kg": float(w), "reps": int(reps)})
        except (TypeError, ValueError):
            continue
    return out
