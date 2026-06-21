import unittest

import pandas as pd

import cockpit


class ChartRenderingTest(unittest.TestCase):
    def test_hero_with_missing_readiness_does_not_emit_inline_style_block(self):
        html = cockpit.hero(
            None,
            "TRAIN EASY",
            "Recovery markers are off and readiness isn't synced - train easy.",
            cockpit.chips("suppressed", 50, 55, 8.0),
        )

        self.assertNotIn("<style", html)
        self.assertIn('style="width:0.0%"', html)
        self.assertIn("TRAIN EASY", html)

    def test_hrv_chart_single_point_uses_marker(self):
        view = pd.DataFrame([{
            "date": "2026-06-04",
            "hrv_overnight_avg": 43,
        }])

        fig = cockpit.chart_hrv(view, (None, None))

        self.assertIn("lines+markers", [trace.mode for trace in fig.data])

    def test_bedtime_hr_chart_single_point_uses_marker(self):
        view = pd.DataFrame([{
            "date": "2026-06-04",
            "hr_bedtime": 65,
        }])

        fig = cockpit.chart_bedtime_hr(view)

        self.assertIn("lines+markers", [trace.mode for trace in fig.data])

    def test_bedtime_hr_chart_uses_unsmoothed_gap_aware_median_series(self):
        view = pd.DataFrame({
            "date": pd.date_range("2026-06-01", periods=5, freq="D"),
            "hr_bedtime": [65, float("nan"), 68, float("nan"), 64],
            "hr_bedtime_7d": [float("nan"), float("nan"), 66.5, 66.5, 65.7],
        })

        fig = cockpit.chart_bedtime_hr(view)
        trace = next(t for t in fig.data if t.name == "10m median")

        self.assertEqual(trace.mode, "lines+markers")
        self.assertEqual(trace.line.shape, "linear")
        self.assertFalse(trace.connectgaps)

    def test_sleep_chart_uses_dynamic_target_label(self):
        view = pd.DataFrame({
            "date": ["2026-06-01"],
            "sleep_hours": [7.4],
        })

        fig = cockpit.chart_sleep(view, target=7.6)

        annotations = list(fig.layout.annotations or [])
        self.assertTrue(any(a.text == "7.6 h" for a in annotations))

    def test_early_waking_chart_renders_body_battery_context(self):
        model = {
            "rows": [
                {
                    "date": "2026-06-01",
                    "early_waking_minutes": 0,
                    "body_battery_at_sleep_start": 55,
                    "pattern": "recovery_window_met",
                    "confidence": "low",
                },
                {
                    "date": "2026-06-02",
                    "early_waking_minutes": 87,
                    "body_battery_at_sleep_start": 20,
                    "pattern": "low_body_battery_early",
                    "confidence": "high",
                },
            ]
        }

        fig = cockpit.chart_early_waking(model)

        self.assertIn("Early for recovery", [trace.name for trace in fig.data])
        self.assertIn("BB at sleep start", [trace.name for trace in fig.data])

    def test_early_waking_classifier_card_shows_latest_pattern_and_evidence(self):
        model = {
            "status": "ready",
            "days_analyzed": 2,
            "latest": {
                "date": "2026-06-02",
                "early_waking_minutes": 87,
                "severity": "meaningful",
                "confidence": "high",
                "pattern": "low_body_battery_early",
                "evidence": ["low Body Battery at sleep start", "low sleep score"],
                "sleep_debt_h": 1.0,
                "prior_sleep_debt_h_7d": 0.0,
                "body_battery_at_sleep_start": 20,
                "recovery_need_h": 8.45,
            },
            "rows": [
                {
                    "date": "2026-06-01",
                    "early_waking_minutes": 0,
                    "severity": "none",
                    "confidence": "low",
                    "pattern": "recovery_window_met",
                },
                {
                    "date": "2026-06-02",
                    "early_waking_minutes": 87,
                    "severity": "meaningful",
                    "confidence": "high",
                    "pattern": "low_body_battery_early",
                },
            ],
        }

        out = cockpit.early_waking_classifier_card(model)

        self.assertIn('class="card early-classifier"', out)
        self.assertIn("Early waking classifier", out)
        self.assertIn("Low Body Battery", out)
        self.assertIn("high confidence", out)
        self.assertIn("low Body Battery at sleep start", out)
        self.assertFalse([ln for ln in out.splitlines() if ln.strip() == ""])

    def test_rhr_chart_trims_leading_no_data_days(self):
        # Short/sparse history: the window spans days with no RHR yet, then
        # data starts. The x-axis should clamp to where RHR exists so the
        # empty leading days don't leave a dead zone (and squash the y-axis).
        view = pd.DataFrame([
            {"date": "2026-06-01", "resting_hr": float("nan"), "rhr_7d": float("nan"), "rhr_28d": float("nan")},
            {"date": "2026-06-02", "resting_hr": float("nan"), "rhr_7d": float("nan"), "rhr_28d": float("nan")},
            {"date": "2026-06-03", "resting_hr": 74.0, "rhr_7d": float("nan"), "rhr_28d": float("nan")},
            {"date": "2026-06-04", "resting_hr": 59.0, "rhr_7d": float("nan"), "rhr_28d": float("nan")},
        ])

        fig = cockpit.chart_rhr(view)

        x0, x1 = fig.layout.xaxis.range
        # Starts after the empty Jun 1–2 days, not at the window's left edge.
        self.assertGreater(pd.Timestamp(x0), pd.Timestamp("2026-06-02"))
        self.assertLess(pd.Timestamp(x0), pd.Timestamp("2026-06-03 12:00"))

    def test_recovery_deviation_chart_trims_leading_no_data_days(self):
        # z-scores only populate once enough baseline history exists, so the
        # early days in the window are NaN. The x-axis should clamp to where
        # the z-scores exist instead of stretching across the empty days.
        dates = pd.date_range("2026-06-01", periods=6, freq="D")
        view = pd.DataFrame({
            "date": dates,
            "hrv_z": [float("nan")] * 4 + [-1.0, 0.5],
            "rhr_z": [float("nan")] * 4 + [0.2, -0.3],
            "sleep_z": [float("nan")] * 6,
            "stress_z": [float("nan")] * 6,
        })

        fig = cockpit.chart_recovery_deviation(view)

        x0, x1 = fig.layout.xaxis.range
        # First z-score is Jun 5; axis starts there, not at the Jun 1 window edge.
        self.assertGreater(pd.Timestamp(x0), pd.Timestamp("2026-06-04"))
        self.assertLess(pd.Timestamp(x0), pd.Timestamp("2026-06-05 12:00"))

    def test_health_research_card_renders_as_one_html_block(self):
        # A panel with no flags used to leave a whitespace-only line in the
        # card HTML. Streamlit's markdown treats that as a blank line, which
        # closes the raw-HTML block — so the following indented HTML renders
        # as a literal code block. The card must contain no blank lines and
        # no >=4-space indentation that could trigger a markdown code block.
        model = {
            "status": "ready",
            "days_analyzed": 18,
            "min_days": 14,
            "message": "Watchlist active.",
            "recovery": {
                "title": "Recovery", "zone": "red",
                "stats": [{"label": "Risk", "value": 76, "sub": "score"}],
                "flags": ["sleep debt >1h"],
            },
            "respiratory": {  # no flags -> previously produced the blank line
                "title": "Respiratory watchlist", "zone": "learning",
                "stats": [{"label": "SpO2", "value": 97, "unit": "%", "sub": "avg"}],
                "flags": [],
            },
            "fitness": {
                "title": "Fitness adaptation", "zone": "red",
                "stats": [{"label": "ACWR", "value": 4.0, "sub": "7d vs 28d"}],
                "flags": ["training load spike"],
            },
        }

        html_out = cockpit.health_research_card(model)
        lines = html_out.splitlines()
        self.assertFalse([ln for ln in lines if ln.strip() == ""],
                         "blank line closes the st.markdown HTML block")
        self.assertFalse([ln for ln in lines if ln[:4] == "    "],
                         ">=4-space indent renders as a markdown code block")
        # Both panels' content survives as real HTML (not escaped text).
        self.assertIn('class="research-panel"', html_out)
        self.assertIn("Fitness adaptation", html_out)

    def test_topbar_has_no_blank_lines_when_sparse(self):
        # When sparse, the synced pill is empty, which left a whitespace-only
        # line mid-markup — the same blank-line trigger that breaks the
        # st.markdown raw-HTML block (see the health card fix).
        out = cockpit.topbar("2026-06-13", sparse=True)
        self.assertFalse([ln for ln in out.splitlines() if ln.strip() == ""],
                         "blank line closes the st.markdown HTML block")
        self.assertIn('class="topbar"', out)

    def test_streamlit_header_does_not_intercept_topbar_controls(self):
        self.assertIn('header[data-testid="stHeader"]{background:transparent;pointer-events:none;}', cockpit.CSS)

    def test_body_battery_and_sleep_score_tiles_are_number_only(self):
        html = cockpit.tiles(
            {"hrv": 43, "rhr": 59, "sleep_h": 7.1, "acwr": 1.0, "batt": 72, "sleep_score": 86},
            {"hrv": [40, 43], "rhr": [61, 59], "sleep_h": [6.8, 7.1], "acwr": [1.0, 1.0], "batt": [50, 72]},
            {"hrv": 42, "rhr": 60, "sleep_h": 7.0, "batt": 60},
            sparse=False,
        )

        start = html.index("Body Battery")
        end = html.index("Sleep Score", start)
        battery_block = html[start:end]
        self.assertIn(">72<", battery_block)
        self.assertNotIn("spark", battery_block)
        self.assertNotIn("vs 28d", battery_block)

        score_block = html[html.index("Sleep Score"):]
        self.assertIn(">86<", score_block)
        self.assertNotIn("spark", score_block)
        self.assertNotIn("vs 28d", score_block)


if __name__ == "__main__":
    unittest.main()
