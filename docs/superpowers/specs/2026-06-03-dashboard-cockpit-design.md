# Garmin Coach — "Cockpit" Dashboard Design Spec

**Date:** 2026-06-03
**Status:** Approved for design handoff
**Audience:** A frontend-design agent (`claudedesign` / the `frontend-design` skill)
**Deliverable type:** Static, standalone, front-end mockup (no backend wiring)

---

## 1. What you're building

A **single-page, dark, "athletic cockpit" dashboard** for a private fitness app called **Garmin Coach**. It showcases an athlete's recovery and training state at a glance, backed by trend charts and an **AI coach interpretation**.

This is a **visual prototype / design target**, not the production app. Build it as a self-contained front-end (HTML/CSS/JS) driven by a bundled **sample dataset**. Do **not** wire it to any live API, database, or auth. The real app is a Python/Streamlit dashboard reading a local SQLite file; this mockup exists to nail the *look and information design*, which will later be ported into that app by hand. Keep the design tokens clean and documented so that port is easy.

### Success criteria
- Opening the deliverable in a browser shows a polished, "sleek," WHOOP-grade dark dashboard.
- A first-time viewer instantly understands: *how recovered am I, and what should I do today?*
- The AI interpretation reads as a first-class feature, not an afterthought.
- Trends are legible and not a "wall of charts."
- Works on desktop **and** mobile (responsive — required).
- Sparse/empty/loading states are designed, not left to chance.

---

## 2. Visual direction (locked)

**Dark athletic cockpit** — think WHOOP / a performance car dashboard.

- **Canvas:** near-black background (e.g. `#0B0E11`), cards slightly elevated (e.g. `#14181D` / `#171C22`) with soft borders or subtle inner glow.
- **Accent: green** — a single electric/neon green (e.g. around `#00E676` / `#19E68C`; pick a refined shade) used **sparingly** for the recovery ring, live values, key highlights, and active controls. Restraint is what makes it look premium — don't paint everything green.
- **Alert colors:** amber (`#FFB020`-ish) for caution, red (`#FF4D4D`-ish) for warnings. Reserved strictly for genuine alert states.
- **Typography:** clean geometric grotesk (e.g. Space Grotesk, Inter, or similar). **Tabular numerals** for all stats so digits don't jitter. Oversized display numerals in the hero.
- **Motion:** subtle and performant only — ring fill on load, sparkline draw-in, hover elevation. No gratuitous animation.

A rough ASCII of the intended hero feel:

```
████████████████████████████████████████████
█  GARMIN COACH                ● synced     █
█                                          █
█    ◜◜◜◜◜        RECOVERY 82              █
█   ◜ 82 ◝        ─────────────            █
█   ◝     ◞       TRAIN HARD               █
█    ◞◞◞◞◞        HRV ▲ balanced · RHR ▼   █
█                 · Sleep ●                █
████████████████████████████████████████████
```

---

## 3. Page layout (top → bottom)

Single vertical scroll. Six zones:

### 3.1 Top bar
- Wordmark **"Garmin Coach"** (small, with a runner/heart glyph).
- Current date (e.g. "Tue 3 Jun 2026").
- A subtle **"synced ✓"** status pill.
- A **day-window control**: segmented `7 / 30 / 60d` (affects which range the trend charts show). Default 30d.

### 3.2 Hero band — "How am I, and what do I do?"
The emotional center of the page. Two halves:

- **Left — Recovery ring.** A large circular gauge showing **Training Readiness (0–100)**. The arc fills proportionally and shifts color by zone: green (high) → amber (mid) → red (low). Big readiness number centered in the ring.
- **Right — AI verdict.**
  - One **bold one-liner**: `TRAIN HARD` / `TRAIN EASY` / `REST` (the day's call).
  - A short supporting sentence (one line of the AI's reasoning).
  - Three **status chips**: `HRV ▲ balanced`, `RHR ▼`, `Sleep ●` — each with an up/down/neutral arrow and a state word/color.
- **Alert ribbon** (conditional): a full-width amber/red strip appears in this band when **HRV is suppressed** or **resting HR is elevated**. Example copy: *"⚠ Overnight HRV suppressed vs baseline — bias toward easier training or rest."* Design both the "no alert" and "alert present" versions.

### 3.3 Key-stat row — 5 tiles
A row of five equal stat tiles (wrap/stack on mobile). Each tile:
- Metric label (small, muted).
- **Large tabular value + unit.**
- A small **sparkline** of recent trend.
- A **delta tag** vs baseline (e.g. `▲ +3 vs 28d`, colored by whether the direction is good/bad).

The five metrics (in order): **HRV · Resting HR · Sleep · ACWR · Body Battery**. (See §5 for ranges/units.) Other available metrics — SpO₂, respiration, steps, intensity minutes — are deliberately **kept out of the hero** to preserve focus.

### 3.4 AI coach readout
A prominent, green-accented "coach" card presenting the full interpretation. It renders **three labeled sections** (this exact structure comes from the app's AI layer — preserve it):

1. **Readiness today** — one short paragraph: train hard / easy / rest and why, citing the numbers.
2. **Trends & anomalies (last ~2 weeks)** — bullet points flagging anything moving the wrong way.
3. **What to do** — 2–4 concrete, actionable recommendations.

Include:
- An **"Analyse"** primary action button (in the mockup it just reveals the sample text — optionally with a brief "thinking" state).
- A collapsible **"data sent to model"** disclosure (a JSON snippet), reflecting the app's privacy boundary where only a compact summary — never raw time-series — is sent to the AI.
- Use **representative placeholder prose** in the exact 3-section format (see §6 for sample copy). No live API calls.

### 3.5 Trends
The justification behind the hero. To avoid a wall of plots, put these behind a **`Recovery / Training` segmented toggle**:

**Recovery view:**
- **HRV vs baseline band** — overnight HRV line + a shaded personal baseline band + a dotted 7-day average.
- **Resting HR** — daily line with dotted 7-day and 28-day rolling averages.
- **Sleep** — bars of nightly hours against a target line (8.0h), plus a **stacked sleep-composition** chart (Deep / REM / Light / Awake).

**Training view:**
- **ACWR (Acute:Chronic Workload Ratio)** — the ratio line over a shaded **0.8–1.3 "sweet spot" band**, with acute (7d) and chronic (weekly-avg) load as bars/line behind it.
- **VO₂max** — estimate over time (line).

Restyle these into the dark cockpit aesthetic (dark plot backgrounds, green/secondary lines, minimal gridlines, tabular axis labels). The mockup may use any charting approach (inline SVG, a JS chart lib, or pre-rendered) as long as it looks native to the theme and animates subtly.

### 3.6 Recent activities
A compact list/table of recent workouts: date, type, duration, distance, avg HR, training load, aerobic TE. Keep it dense and quiet — it's supporting detail, not a hero.

---

## 4. Responsive requirements (required)

- **Desktop-first** visual quality, but **fully responsive down to mobile** (~360px).
- Hero: ring and AI verdict stack vertically on narrow screens; ring stays large and central.
- Key-stat row: 5 tiles → 2-up or 1-up grid on mobile, sparklines preserved.
- Trend charts: full-width, vertically stacked, horizontally scroll-free (no tiny squished plots).
- AI readout: comfortable line length on mobile; sections remain clearly delineated.
- Touch-friendly tap targets for the segmented controls and "Analyse" button.

---

## 5. Data dictionary (for realistic sample data)

Use these to generate believable sample values, units, and ranges. The athlete is reasonably fit.

| Metric | Unit | Realistic range | Notes / "good" direction |
|---|---|---|---|
| Training Readiness | score 0–100 | 25–95 | Higher = more ready. Drives the hero ring color. |
| HRV (overnight avg) | ms | 30–100 | Higher generally better; compared to a personal baseline **band**. Flag states: `suppressed` / `balanced` / `elevated`. |
| Resting HR (RHR) | bpm | 40–60 | Lower better. "Elevated" = >5% above 28-day baseline. |
| Sleep | hours | 5.0–9.0 | Target/need = **8.0h**. Debt = need − actual. |
| Sleep score | 0–100 | 40–95 | Higher better. |
| Sleep composition | seconds → hours | — | Deep / REM / Light / Awake, stacks to total sleep. |
| ACWR | ratio | 0.5–2.0 | **Sweet spot ~0.8–1.3**; >1.5 = load spike. |
| Acute load | training-load units | — | Sum of activity training load over trailing 7d. |
| Chronic load | training-load units | — | Avg weekly load over trailing 28d. |
| VO₂max | ml/kg/min | 40–60 | Higher better; moves slowly. |
| Body Battery | 0–100 | low 5–40, high 60–100 | Energy reserve; show high & low. |
| Stress (avg) | 0–100 | 20–60 | Lower better. |
| Activity | — | — | type (run/ride/swim/strength), duration, distance, avg/max HR, training load, aerobic/anaerobic TE. |

**Generate ~60 days** of daily sample data so trends, rolling averages, and sparklines look alive, plus ~15–20 recent activities. Bake in *one or two* interesting moments (e.g. a few days of suppressed HRV + elevated RHR, an ACWR spike) so the alert ribbon and AI readout have something real to describe.

---

## 6. Sample AI copy (use verbatim-style placeholder)

Render the coach readout with prose in this shape and tone — specific, quantitative, no medical disclaimers, no padding:

> **Readiness today**
> Train hard. Overnight HRV (64 ms) sits in the upper half of your baseline band, resting HR (48 bpm) is 2 bpm below your 28-day average, and you logged 7.8 h of sleep. The body looks primed to absorb a quality session.
>
> **Trends & anomalies (last ~2 weeks)**
> - HRV trend: rising (+6% vs the prior week) — a good adaptation signal.
> - Sleep debt: 2.1 h accumulated over 14 days, driven by three short nights last week.
> - ACWR at 1.18 — inside the sweet spot, but trending up; watch the next two sessions.
> - No suppressed-HRV days in the last week.
>
> **What to do**
> 1. Green-light a hard/threshold session today while readiness is high.
> 2. Protect tonight's sleep — aim 8.5 h to chip at the 2.1 h debt.
> 3. Keep the next easy day genuinely easy to hold ACWR under 1.3.

Also design an **alert-state variant** of the readout (e.g. suppressed HRV → "Train easy / rest" verdict, red chips) so both moods are represented.

---

## 7. States to design (don't skip)

1. **Nominal** — full data, all metrics present (the default showcase).
2. **Alert** — HRV suppressed and/or RHR elevated: ribbon visible, ring amber/red, AI verdict = easy/rest.
3. **Sparse / first-run** — only ~1 day of data exists. (This is the *real* current state of the app.) Design graceful placeholders: "Not enough data yet — sync more history," em-dash (`—`) for null values, ring in a neutral "no score" state, sparklines hidden or flat-stubbed. The page must not look broken when empty.
4. **AI thinking** — the "Analyse" action shows a brief loading/skeleton state before the readout appears.

---

## 8. Out of scope (YAGNI)

- No real Garmin or Anthropic API calls; no database; no auth; no settings screen; no multi-user.
- No raw-data spreadsheet/table view.
- No data editing or sync controls beyond the cosmetic "synced ✓" pill.
- **Not** the Streamlit port — that's a separate, later task once the look is approved.

---

## 9. Deliverables

1. A **self-contained front-end** that runs by opening a file in a browser — `index.html` plus CSS/JS assets and a `sample-data.json` (or inlined sample data). No build step required to view.
2. **Documented design tokens** — color palette (hex), type scale, spacing scale, radii, shadows — in a short `DESIGN-TOKENS.md` or a clearly-commented CSS `:root` block, so the visual language can be re-implemented in Streamlit later.
3. All four states from §7 viewable (via a toggle, query param, or separate sample files — your call).

---

## 10. Context the designer should know

- This is a **single-user, private, local** app. No marketing, onboarding, or sign-up surfaces needed — it opens straight into the dashboard.
- The metrics, flags (HRV suppressed, RHR elevated), ACWR sweet-spot band, and the **three-section AI format** are all real features of the existing app — honor them so the mockup maps cleanly onto production.
- "Sleek" here means **calm confidence and information clarity**, not flashiness. The data is the hero; green is the spark.
