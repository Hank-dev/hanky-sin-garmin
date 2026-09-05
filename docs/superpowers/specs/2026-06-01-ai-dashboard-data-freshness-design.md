---
type: note
title: >-
  Data freshness across dashboards — Phase 0: `/ai` + the reusable freshness
  pattern
date: '2026-06-01'
---

# Data freshness across dashboards — Phase 0: `/ai` + the reusable freshness pattern

**Date:** 2026-06-01
**Status:** Design — pending user review
**Author:** brainstorming session (Claude)

## 1. Problem

The dashboards present a lot of data as **hardcoded snapshots that go stale**. Severity is uneven:

- **`/btc`** — fully live (client SWR → `/api/*` routes composing `lib/btc/data` + `lib/btc/calc`). Reference pattern.
- **`/dollar`** — mostly live (server component, 15-min ISR, FRED + CoinGecko in `lib/fetchers.ts` with a `FALLBACK` snapshot). Two metrics are hardcoded `"static"`: Japan 10Y JGB and BOJ policy rate (`lib/metrics.ts`).
- **`/nuclear`** — mixed. Equity quotes + uranium index are live (`lib/nuclearLive.ts`), but the entire structured dataset (player market caps, GW figures, verdict) is a hardcoded snapshot in `lib/nuclearMetrics.ts` dated `2026-05-27`.
- **`/ai`** — worst offender. Nearly everything is static in `lib/aiMetrics.ts` dated `2026-05-27`: market caps, private valuations, user counts, capex, verdict, every prose field. Only the frontier-model price/intelligence chart and the Grok X-summary are live.

Two distinct classes of stale data:
1. **Quantitative facts with a clean API** — equity prices/market caps, FX, yields. *Can be made live.*
2. **Facts with no clean free API** — private valuations, user counts, capex, GW capacity — plus all editorial prose (verdicts, descriptions, "what to watch next"). *Need an AI-assisted refresh.*

## 2. Goals

- Make data with a real API **live** (request-time fetch, snapshot fallback).
- For data with no API, build a **scheduled AI-assisted refresh** that rewrites the snapshot and opens a PR for human review.
- Make **staleness visible** in the UI.
- Establish a **reusable pattern** that later phases (nuclear, dollar, btc) apply with minimal new work.

### Non-goals (Phase 0)

- Migrating `/nuclear`, `/dollar`, `/btc` (later phases; each its own spec). The one exception: `lib/nuclearLive.ts` is refactored onto the new shared `lib/quotes.ts` to avoid duplicating quote logic — a behavior-preserving change.
- Adding a test framework (repo has none; verification is `npm run build` + `npm run lint` + manual).
- Converting the `/ai` client component to SWR. `/ai` stays server-rendered (data changes slowly), consistent with `/dollar`.

## 3. Decisions locked in (from brainstorming)

| Decision | Choice |
|---|---|
| End state | **Both layers** — live APIs where they exist + AI-assisted refresh on top. |
| Refresh mechanism | **Scheduled file rewrite** — snapshot files remain the source of truth. |
| Scheduler | **GitHub Actions → PR** — weekly cron + manual dispatch, opens a PR to review. |
| Decomposition | **Vertical slices**, `/ai` first; each later dashboard its own spec→plan→implement. |
| Refresh scope | **Everything factual + prose** — numbers *and* descriptive prose are refreshable, bounded by a fixed roster and the PR-review gate. |

## 4. Roadmap (decomposition)

| Phase | Slice | Notes |
|---|---|---|
| **0 (this spec)** | `/ai` end-to-end + shared `lib/quotes.ts`, JSON-snapshot pattern, refresh script, GitHub Action, `lib/freshness.ts` | Exercises both layers; proves the CI. |
| 1 | `/nuclear` | Reuses `quotes.ts` (already half-done there); migrate snapshot → JSON; add to refresh scope. |
| 2 | `/dollar` | Make JGB / BOJ live or refreshed; reuse freshness UI. |
| 3 | `/btc` | Audit for stray snapshots; apply freshness UI. |

Only Phase 0 is specified here.

## 5. Architecture — three layers + cross-cutting

### 5.1 Snapshot layer — split volatile content into JSON

**Principle: code holds shape & logic; JSON holds content.** A **fixed roster** (which players/metrics/signals exist, and their stable identity) stays in TypeScript. All **volatile content** for each fixed slot moves to `lib/aiSnapshot.json`. This bounds the refresh: the model fills content into known slots and can never add, drop, or rename slots.

**Stays in `lib/aiMetrics.ts` (code):**
- All `interface`/`type` definitions and `AI_GROUPS`.
- The roster of players: `id`, `kind` (`public`/`private`), `ticker`, `name`, `category`. (`name`/`category` are stable identity; a rename is a deliberate manual code edit.)
- The roster of `marketMetrics`: `id`, `group`.
- The roster of `techSignals`: `id`, `track`.
- The `buildAiDashboard()` builder (replaces the hand-written `getAiDashboardData()` literal).

**Moves to `lib/aiSnapshot.json` (refreshable content):**
- `verdict`: `{ text, asOf }`
- `players.<id>`: `{ marketCap? | valuationEstimate?, adoptionSignal, aiExposure, status, source: { name, url, asOf, confidence } }`
- `marketMetrics.<id>`: `{ value, context, detail, status, source }`
- `techSignals.<id>`: `{ label, summary, watchNext, status, source }`

`buildAiDashboard()` zips roster + JSON content into the existing `AiDashboardData` shape. The committed `aiSnapshot.json` always contains an entry for every roster id (seeded from today's data during implementation; refresh validation in §6 guarantees completeness before any write). If an entry is nonetheless missing on read, the build throws in development (catches drift early) and, in production, logs and omits that single slot so the rest of the page still renders.

`snapshotDate` for the dashboard = the **most recent `asOf`** across all content (computed, not hand-set).

### 5.2 Live layer — shared `lib/quotes.ts`

Extract the Yahoo → Stooq → market-cap-snapshot fallback chain currently inside `lib/nuclearLive.ts` into a standalone, **non-`server-only`** module so both API routes and the refresh script can import it:

```ts
// lib/quotes.ts
export interface EquityQuote {
  symbol: string;
  name: string | null;
  price: number | null;
  changePercent: number | null;
  marketCapUsd: number | null;
  marketCapSource: "live" | "snapshot" | "unavailable";
  currency: string;
  exchange: string | null;
  asOfUnix: number | null;
  sourceUrl: string;
}
export async function fetchEquityQuotes(
  symbols: string[],
  opts?: { snapshotMarketCapUsd?: Record<string, number>; revalidateSeconds?: number },
): Promise<EquityQuote[]>;
```

- `lib/nuclearLive.ts` is refactored to call `fetchEquityQuotes` (passing its existing `MARKET_CAP_USD_BY_SYMBOL` as `snapshotMarketCapUsd`). Public behavior unchanged.
- `/ai` public players use symbols `["NVDA","GOOGL","MSFT","AMZN","AVGO","META"]`. Live `marketCapUsd` is formatted (`$X.XT` / `$XXXB`) and overlaid onto the player's snapshot `marketCap` string.

**Merge precedence:** live quote (public players only) → JSON snapshot value → omit.

A `formatMarketCapUsd(n)` helper lives in `lib/quotes.ts` (or `lib/format.ts` if a shared one is introduced).

### 5.3 Page wiring

`app/ai/page.tsx` becomes `async`:

```ts
export const revalidate = 3600;
export default async function AiPage() {
  const data = await buildAiDashboardLive(); // build snapshot, fetch quotes, overlay
  return <AiDashboard data={data} />;
}
```

- `buildAiDashboardLive()` (in `lib/aiMetrics.ts` or a thin `lib/aiDashboard.ts`) calls `buildAiDashboard()` then overlays live caps via `fetchEquityQuotes`, wrapped in try/catch → falls back to pure snapshot on any failure.
- The client `AiDashboard.tsx` is unchanged except for the staleness UI (§5.6). It still receives a fully-formed `AiDashboardData`.

### 5.4 Refresh script — `scripts/refresh-snapshots.ts`

- Run via `npm run refresh:snapshots`. Added devDependency `tsx` (or Node native `--experimental-strip-types`); npm script `"refresh:snapshots": "tsx scripts/refresh-snapshots.ts"`.
- Reads the current `lib/aiSnapshot.json` + the roster from `lib/aiMetrics.ts` (slots + identity/category to research).
- Calls the Anthropic SDK (`lib/anthropic.ts` client) with the **`web_search` server tool** enabled (this is what `ENABLE_WEB_SEARCH` will finally gate). Model: a capable model (default Sonnet, overridable via env, e.g. `REFRESH_MODEL`). Static instructions use **prompt caching**.
- Requests **strict JSON** matching the slot schema, one request per content group (players / marketMetrics / techSignals / verdict) to keep citations clean and token use bounded.
- Field-level merge of model output over prior JSON, then **schema validation** (see §7), then write `lib/aiSnapshot.json` (pretty-printed, stable key order for clean diffs).
- Emits a machine-readable change summary (changed fields + citations) to stdout / a file for the PR body.

### 5.5 CI — `.github/workflows/refresh-snapshots.yml`

- Triggers: `schedule` (weekly cron, e.g. Mondays 06:00 UTC) + `workflow_dispatch`.
- Steps: checkout → setup Node → `npm ci` → `npm run refresh:snapshots` → open PR via `peter-evans/create-pull-request` on branch `auto/refresh-snapshots`, title `chore: refresh dashboard snapshot`, body = the change summary.
- Secret required: `ANTHROPIC_API_KEY` (documented in README/AGENTS; user adds it in repo settings).
- The PR is the human-review gate — nothing reaches `main` unreviewed.

### 5.6 Staleness UI (cross-cutting)

`lib/freshness.ts`:

```ts
export type Freshness = "fresh" | "aging" | "stale";
export function daysSince(isoDate: string, now?: Date): number;
export function freshnessOf(isoDate: string, opts?: { agingDays?: number; staleDays?: number }): Freshness;
```

Defaults: `aging > 30d`, `stale > 90d` (tunable). In `AiDashboard.tsx`:
- Header shows the freshest `asOf` and an overall freshness dot (replaces static "Curated snapshot · date").
- Each metric/player/signal tile shows a small freshness dot derived from its `source.asOf`.
- Uses existing CSS tokens; no new visual language.

### 5.7 Prompt-grounding contract

`buildAiDashboard()` keeps the `AiDashboardData` shape, so `lib/aiPrompts.ts` keeps working unchanged in structure. Two required adjustments to preserve honesty (CLAUDE.md contract):
- `sharedAiContext` wording updated: data is "a dated snapshot, refreshed periodically, with some public-company market caps as live quotes timestamped at fetch time" — instead of the flat "not live data."
- Keep the rule "do not invent figures beyond what is provided." Live caps merged into the JSON-derived `data` are legitimately "provided," so no contradiction.

## 6. Refresh guardrails (because scope = numbers + prose)

1. **Fixed roster** — model fills content into known slots only; cannot add/drop/rename.
2. **Citation required** — every changed field must carry a `source.url` from web search; uncited changes are rejected and the prior value is kept.
3. **Keep-prior-on-doubt** — if the model can't verify a field, it must return the existing value (instructed explicitly). No blanks, no guesses.
4. **Schema validation before write** — types, `status` enum, `confidence` enum, `asOf` ISO-date, prose non-empty and within length bounds. A field that fails validation reverts to prior; if the document fails to parse, abort the run (write nothing).
5. **Prose length limits** in the prompt to preserve editorial voice/altitude.
6. **PR-review gate** — the human reviews the diff + citations before merge.

## 7. Data model & validation

`lib/aiSnapshot.schema.ts` (or inline validators) defines, per slot type, required keys and constraints. Validation is plain TypeScript guards (no new dependency) run by both the refresh script (before write) and `buildAiDashboard()` (on read, dev-strict / prod-lenient).

`confidence ∈ {high, medium, low}`, `status ∈ {calm, neutral, elevated, stressed}`, `asOf` matches `YYYY-MM-DD`.

## 8. Unit breakdown (what / how-used / depends-on)

| Unit | Does | Used by | Depends on |
|---|---|---|---|
| `lib/aiSnapshot.json` | Volatile AI content | `aiMetrics.ts`, refresh script | — |
| `lib/aiMetrics.ts` | Roster + types + `buildAiDashboard()` + validation-on-read | page, prompts | `aiSnapshot.json` |
| `lib/quotes.ts` | Generic equity quotes + cap formatting | `/ai` page, `nuclearLive.ts`, refresh script | Yahoo/Stooq |
| `lib/freshness.ts` | as-of → freshness level | dashboards | — |
| `scripts/refresh-snapshots.ts` | Claude + web search → rewrite JSON | npm / CI | `anthropic.ts`, `quotes.ts`, schema |
| `.github/workflows/refresh-snapshots.yml` | Schedule + open PR | CI | script, `ANTHROPIC_API_KEY` |
| `app/ai/page.tsx` | async build + live overlay | route | `aiMetrics.ts`, `quotes.ts` |

## 9. Error handling & resilience

- Live quote failure → snapshot value (existing norm); page never breaks with no network/keys.
- Refresh field unverifiable/invalid → prior value kept.
- Refresh document unparseable → abort write, no PR.
- Missing `ANTHROPIC_API_KEY` in CI → workflow fails loudly (no silent stale PR).
- `buildAiDashboard()` roster/JSON mismatch → dev throws; prod logs and skips the affected slot.

## 10. Verification

- `npm run build` (type-check) and `npm run lint` green.
- Manual: `/ai` renders with live caps; with the quote host blocked, falls back to snapshot; prompts still ground correctly.
- `npm run refresh:snapshots` locally produces valid, schema-passing JSON with citations.
- `workflow_dispatch` dry-run opens a PR with a sensible diff + body.
- `nuclearLive` regression: `/nuclear` live panel unchanged after the `quotes.ts` refactor.

## 11. Open items for implementation (not blocking design)

- TS runner choice for the script (`tsx` vs Node native strip-types) — decide during planning.
- Exact cron time and freshness thresholds — sensible defaults above, tune later.
- Whether `formatMarketCapUsd` lives in `quotes.ts` or a shared `lib/format.ts`.
- Use the `claude-api` skill during implementation for the SDK call (caching, web-search tool, structured output).
