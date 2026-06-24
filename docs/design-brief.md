# Design brief — "Garmin Coach" (Hankø) recovery & training app

## What it is
A private, single-user fitness dashboard. It pulls my Garmin watch data (sleep,
heart rate, HRV, stress, workouts) into a local database and turns it into a
**daily readiness verdict** plus AI coaching. Think "personal recovery cockpit" —
calm, data-dense, but with one bold headline call each morning. It runs as a
desktop + mobile web app (Streamlit). It is for me only, so it can be opinionated
and characterful, not a generic SaaS dashboard.

## Redesign goal
**Keep the structure and information design — give it a brand-new color palette
and new textures/material language.** I'm tired of the current look (deep teal +
neon green + leather grain). I want a fresh, distinctive skin. Dark mode is
strongly preferred (I read it at 6am and at night), but surprise me with the
palette and surface treatment.

## The four screens

**1. Recovery Cockpit (home — the hero screen)**
- Top bar: brand mark + name, today's date, a "synced" status pill (live pulse dot).
- Time-range toggle: 7d / 30d / 60d.
- **Hero panel:** a big circular **readiness ring** (0–100 score) next to a giant
  headline verdict like **"TRAIN HARD"** / "RECOVER" / "EASE IN", a one-line
  subtitle, and 3 status chips (HRV ▲ balanced, RHR ▼ low, Sleep ● on target).
- **"Today's signals":** a row of 5 metric cards — HRV, Resting HR, Sleep, ACWR
  (training load ratio), Body Battery — each with a number, unit, a small
  sparkline, and a delta vs baseline.
- **Coach block:** an "Analyse" button + an AI coach readout card (verdict, trend
  flags, concrete next steps) with a collapsible "data sent to model" disclosure.
- **Charts** (dark Plotly): Overnight HRV trend (with a target band), Resting HR,
  Sleep duration (bars, green/amber by target), Sleep composition (stacked
  deep/REM/light/awake).
- **Activities table:** recent workouts with type icon, date, duration, distance,
  avg HR, load.

**2. Strength** — imported workout history, estimated 1RM progress charts,
strength-standard ratings, muscle-balance breakdown, readiness-vs-performance,
and bodyweight trend.

**3. Coach** — "What the coach knows" (categorized facts/context the AI uses) and
"Find things to remember."

**4. Experiments** — an "experiment lab" to create/run/complete self-experiments,
plus a "Completed" archive.

## Current look — what to move *away from* (for reference)
- Base: near-black deep teal `#0C1A1A`, surfaces `#112A2B`–`#1B3F41`.
- Accent: neon teal-green `#3FB6A8` (ring, sparklines, highlights).
- Secondary: champagne/brass `#E3BE85`; warn amber `#E4AB66`; alarm orange `#E0763C`.
- Texture: subtle fractal **film grain** over "leather-grained" panels, brass
  top-hairline on cards, soft inset highlights, big soft drop shadows.
- Type: Hanken Grotesk (sans), Instrument Serif (the big serif numerals — a
  signature), IBM Plex Mono (tiny uppercase labels/kickers, wide letter-spacing).
- Radii 4–14px, generous dark-card elevation.

## What I want from the redesign
1. **A new color system** — 1 base/background family, 2–3 surface elevations, a
   primary accent (readiness ring + positive signals), and a clear semantic set for
   **good / caution / alarm**. Keep enough contrast for charts and tiny mono labels.
2. **New textures / material language** — replace the leather-grain + brass-hairline
   treatment with something with its own character (see directions below).
3. **Keep the bones:** the readiness ring, the big headline verdict, the sparkline
   signal cards, the mono micro-labels, and the serif-numeral signature can stay as
   *patterns* — just re-skinned. Hierarchy and density should stay.
4. Must read well on both a wide desktop layout and a narrow mobile column.

## Pick a direction (choose one, or blend)
- **A — Warm clay / terracotta:** earthy charcoal base, terracotta + sand accents,
  matte paper/risograph grain. Athletic but organic.
- **B — Frosted slate / ice:** cool graphite + glassmorphism, frosted translucent
  panels, electric ice-blue or cyan accent, faint noise. Clinical, "lab instrument."
- **C — Brushed metal / graphite:** near-monochrome gunmetal with a single
  high-voltage accent (acid lime, electric orange, or magenta), subtle brushed-metal
  striations and machined bevels. Industrial cockpit.
- **D — Deep aurora / dusk:** very dark indigo-to-plum gradient base, soft aurora
  glows, a luminous accent (violet→teal), glassy cards. Moody, premium, nocturnal.

## Practical constraints
- It's a **Streamlit** app: the redesign needs to translate to CSS variables +
  custom CSS, and chart colors (Plotly) should be specified to match the palette.
- Deliverables I'd love: a palette (hex + roles), 2–3 texture/material treatments,
  type pairing, and a styled mock of the **Cockpit hero + signal cards** as the
  flagship.
