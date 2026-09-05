---
type: note
title: AI Dashboard Data Freshness — Implementation Plan
date: '2026-06-01'
---

# AI Dashboard Data Freshness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the `/ai` dashboard from a hardcoded snapshot into a live + AI-refreshed data model, and build the reusable freshness pieces (`lib/quotes.ts`, JSON snapshot layer, refresh script, GitHub Action) that later dashboards will reuse.

**Architecture:** Code holds the fixed roster + types + builders; volatile content lives in `lib/aiSnapshot.json`. Public-player market caps are fetched live at request time via a shared `lib/quotes.ts` (extracted from `nuclearLive.ts`) and overlaid on the snapshot. A `scripts/refresh-snapshots.ts` job uses Claude + web search to rewrite the JSON; a weekly GitHub Action runs it and opens a PR for review.

**Tech Stack:** Next.js 16 (App Router), React 19, TypeScript strict, `@anthropic-ai/sdk` ^0.98 (web_search tool), `tsx` for running the script, GitHub Actions (`peter-evans/create-pull-request`).

**Verification model:** This repo has **no test framework** (per CLAUDE.md). Each task is verified with `npm run build` (type-check), `npm run lint`, and — for pure logic — a one-off smoke check via `npx tsx -e`. No test framework is added.

**Spec:** `docs/superpowers/specs/2026-06-01-ai-dashboard-data-freshness-design.md`

---

## File Structure

**Create:**
- `lib/freshness.ts` — as-of date → freshness level (pure, no deps)
- `lib/quotes.ts` — generic equity quote fetcher + market-cap formatter (extracted from `nuclearLive.ts`)
- `lib/aiSnapshot.schema.ts` — TS types + runtime validators for the snapshot JSON
- `lib/aiSnapshot.json` — volatile AI content (seeded from current `aiMetrics.ts`)
- `scripts/refresh-snapshots.ts` — Claude + web search → rewrites `aiSnapshot.json`
- `.github/workflows/refresh-snapshots.yml` — weekly cron → opens PR

**Modify:**
- `lib/nuclearLive.ts` — consume `lib/quotes.ts` (behavior-preserving)
- `lib/aiMetrics.ts` — keep roster + types; `getAiDashboardData()` builds from roster + JSON; add async `getAiDashboardDataLive()`
- `app/ai/page.tsx` — async, live overlay, `revalidate`
- `components/ai/AiDashboard.tsx` — freshness indicators
- `lib/aiPrompts.ts` — honesty wording
- `package.json` — add `tsx` devDep + `refresh:snapshots` script
- `.env.example`, `README.md`, `AGENTS.md` — document the secret + flag

**Untouched (verified, not changed):** `app/api/ai/ask/route.ts`, `app/api/ai/explain/route.ts` — they keep calling the sync `getAiDashboardData()`.

---

## Task 1: `lib/freshness.ts` + `tsx` tooling

**Files:**
- Modify: `package.json` (add `tsx` devDependency)
- Create: `lib/freshness.ts`

- [ ] **Step 1: Add the `tsx` dev tool**

Run: `npm install --save-dev tsx`
Expected: `tsx` appears under `devDependencies` in `package.json`; install succeeds.

- [ ] **Step 2: Create `lib/freshness.ts`**

```ts
// Shared "how stale is this?" helper, reused across dashboards.
export type Freshness = "fresh" | "aging" | "stale";

export interface FreshnessThresholds {
  agingDays?: number;
  staleDays?: number;
}

const MS_PER_DAY = 24 * 60 * 60 * 1000;
const ORDER: Freshness[] = ["fresh", "aging", "stale"];

export function daysSince(isoDate: string, now: Date = new Date()): number {
  const then = new Date(`${isoDate}T00:00:00Z`).getTime();
  if (!Number.isFinite(then)) return Number.POSITIVE_INFINITY;
  return Math.floor((now.getTime() - then) / MS_PER_DAY);
}

export function freshnessOf(
  isoDate: string,
  { agingDays = 30, staleDays = 90 }: FreshnessThresholds = {},
): Freshness {
  const age = daysSince(isoDate);
  if (age > staleDays) return "stale";
  if (age > agingDays) return "aging";
  return "fresh";
}

// Worst (most stale) value wins — for an at-a-glance overall indicator.
export function overallFreshness(
  isoDates: string[],
  thresholds?: FreshnessThresholds,
): Freshness {
  return isoDates.reduce<Freshness>((worst, date) => {
    const f = freshnessOf(date, thresholds);
    return ORDER.indexOf(f) > ORDER.indexOf(worst) ? f : worst;
  }, "fresh");
}
```

- [ ] **Step 3: Smoke-check the logic**

Run: `npx tsx -e "import {freshnessOf, overallFreshness} from './lib/freshness.ts'; console.log(freshnessOf('2020-01-01'), freshnessOf(new Date().toISOString().slice(0,10)), overallFreshness(['2020-01-01', new Date().toISOString().slice(0,10)]));"`
Expected: `stale fresh stale`

- [ ] **Step 4: Type-check + lint**

Run: `npm run build && npm run lint`
Expected: build succeeds, lint clean.

- [ ] **Step 5: Commit**

```bash
git add package.json package-lock.json lib/freshness.ts
git commit -m "feat: add lib/freshness.ts staleness helper + tsx tooling"
```

---

## Task 2: `lib/quotes.ts` — generic equity quotes

**Files:**
- Create: `lib/quotes.ts`

Source of truth for the extracted logic: `lib/nuclearLive.ts` (`fetchYahooQuotes`, `fetchYahooQuotesFromHost`, `normalizeQuote`, `fetchStooqQuotes`, `fetchStooqQuote`, `finiteOrNull`). Generalize: symbol list, snapshot market caps, and names become parameters.

- [ ] **Step 1: Create `lib/quotes.ts`**

```ts
// Generic equity quote fetcher (Yahoo → Stooq fallback). NOT server-only:
// imported by API routes, the /ai server page, and scripts. Extracted from
// lib/nuclearLive.ts so multiple dashboards share one quote path.

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

export interface FetchEquityQuotesOptions {
  snapshotMarketCapUsd?: Record<string, number>;
  nameBySymbol?: Record<string, string>;
  revalidateSeconds?: number;
}

export interface EquityQuotesResult {
  quotes: EquityQuote[];
  source: "yahoo" | "stooq" | "none";
  errors: string[];
}

const DEFAULT_REVALIDATE = 3600;
const HOSTS = [
  "https://query1.finance.yahoo.com",
  "https://query2.finance.yahoo.com",
];
const BROWSER_HEADERS: Record<string, string> = {
  "User-Agent":
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
  Accept: "application/json, text/plain, */*",
  "Accept-Language": "en-US,en;q=0.9",
};

type YahooQuote = {
  symbol?: string;
  shortName?: string;
  longName?: string;
  regularMarketPrice?: number;
  regularMarketChangePercent?: number;
  marketCap?: number;
  currency?: string;
  fullExchangeName?: string;
  exchange?: string;
  regularMarketTime?: number;
};

type YahooQuoteResponse = {
  quoteResponse?: { result?: YahooQuote[]; error?: { description?: string } | null };
};

export async function fetchEquityQuotes(
  symbols: string[],
  opts: FetchEquityQuotesOptions = {},
): Promise<EquityQuotesResult> {
  const errors: string[] = [];
  try {
    return { quotes: await fetchYahooQuotes(symbols, opts), source: "yahoo", errors };
  } catch (err) {
    errors.push(`Yahoo: ${err instanceof Error ? err.message : String(err)}`);
  }
  try {
    return { quotes: await fetchStooqQuotes(symbols, opts), source: "stooq", errors };
  } catch (err) {
    errors.push(`Stooq: ${err instanceof Error ? err.message : String(err)}`);
  }
  return { quotes: [], source: "none", errors };
}

export function formatMarketCapUsd(value: number | null): string | null {
  if (value == null || !Number.isFinite(value) || value <= 0) return null;
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`;
  if (value >= 1e9) return `$${Math.round(value / 1e9)}B`;
  if (value >= 1e6) return `$${Math.round(value / 1e6)}M`;
  return `$${Math.round(value)}`;
}

async function fetchYahooQuotes(
  symbols: string[],
  opts: FetchEquityQuotesOptions,
): Promise<EquityQuote[]> {
  let lastErr: unknown = null;
  for (const host of HOSTS) {
    try {
      return await fetchYahooQuotesFromHost(host, symbols, opts);
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error("Yahoo quote request failed.");
}

async function fetchYahooQuotesFromHost(
  host: string,
  symbols: string[],
  opts: FetchEquityQuotesOptions,
): Promise<EquityQuote[]> {
  const revalidate = opts.revalidateSeconds ?? DEFAULT_REVALIDATE;
  const url = `${host}/v7/finance/quote?symbols=${symbols.map(encodeURIComponent).join(",")}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 3500);
  const res = await fetch(url, {
    next: { revalidate },
    headers: BROWSER_HEADERS,
    signal: controller.signal,
  }).finally(() => clearTimeout(timeout));
  if (!res.ok) throw new Error(`Yahoo quote API returned ${res.status}`);

  const body = (await res.json()) as YahooQuoteResponse;
  const error = body.quoteResponse?.error;
  if (error) throw new Error(error.description ?? "Yahoo quote API error");

  return (body.quoteResponse?.result ?? [])
    .map((raw) => normalizeYahoo(raw, opts))
    .filter((quote): quote is EquityQuote => Boolean(quote));
}

function normalizeYahoo(raw: YahooQuote, opts: FetchEquityQuotesOptions): EquityQuote | null {
  if (!raw.symbol) return null;
  const symbol = raw.symbol.toUpperCase();
  const liveCap = finiteOrNull(raw.marketCap);
  const snapshotCap = opts.snapshotMarketCapUsd?.[symbol] ?? null;
  return {
    symbol,
    name: raw.shortName ?? raw.longName ?? opts.nameBySymbol?.[symbol] ?? symbol,
    price: finiteOrNull(raw.regularMarketPrice),
    changePercent: finiteOrNull(raw.regularMarketChangePercent),
    marketCapUsd: liveCap ?? snapshotCap,
    marketCapSource: liveCap != null ? "live" : snapshotCap != null ? "snapshot" : "unavailable",
    currency: raw.currency ?? "USD",
    exchange: raw.fullExchangeName ?? raw.exchange ?? null,
    asOfUnix: finiteOrNull(raw.regularMarketTime),
    sourceUrl: `https://finance.yahoo.com/quote/${encodeURIComponent(symbol)}`,
  };
}

async function fetchStooqQuotes(
  symbols: string[],
  opts: FetchEquityQuotesOptions,
): Promise<EquityQuote[]> {
  const settled = await Promise.allSettled(symbols.map((s) => fetchStooqQuote(s, opts)));
  const quotes: EquityQuote[] = [];
  const errors: string[] = [];
  settled.forEach((result, index) => {
    if (result.status === "fulfilled") quotes.push(result.value);
    else errors.push(`${symbols[index]} ${result.reason instanceof Error ? result.reason.message : "failed"}`);
  });
  if (quotes.length === 0) throw new Error(errors.join("; ") || "No Stooq quotes returned");
  return quotes;
}

async function fetchStooqQuote(symbol: string, opts: FetchEquityQuotesOptions): Promise<EquityQuote> {
  const revalidate = opts.revalidateSeconds ?? DEFAULT_REVALIDATE;
  const stooqSymbol = `${symbol.toLowerCase()}.us`;
  const url = `https://stooq.com/q/l/?s=${encodeURIComponent(stooqSymbol)}&f=sd2t2ohlcv&h`;
  const res = await fetch(url, { next: { revalidate }, headers: { Accept: "text/csv,*/*" } });
  if (!res.ok) throw new Error(`returned ${res.status}`);

  const csv = await res.text();
  const [, row] = csv.trim().split(/\r?\n/);
  if (!row) throw new Error("empty response");

  const [rawSymbol, date, time, openRaw, , , closeRaw] = row.split(",");
  if (!rawSymbol || date === "N/D" || closeRaw === "N/D") throw new Error("no quote data");

  const open = Number(openRaw);
  const close = Number(closeRaw);
  const changePercent =
    Number.isFinite(open) && open > 0 && Number.isFinite(close)
      ? ((close - open) / open) * 100
      : null;
  const marketTime = Date.parse(`${date}T${time || "00:00:00"}Z`);
  const snapshotCap = opts.snapshotMarketCapUsd?.[symbol.toUpperCase()] ?? null;

  return {
    symbol: symbol.toUpperCase(),
    name: opts.nameBySymbol?.[symbol.toUpperCase()] ?? symbol.toUpperCase(),
    price: Number.isFinite(close) ? close : null,
    changePercent,
    marketCapUsd: snapshotCap,
    marketCapSource: snapshotCap != null ? "snapshot" : "unavailable",
    currency: "USD",
    exchange: "Stooq",
    asOfUnix: Number.isFinite(marketTime) ? Math.floor(marketTime / 1000) : null,
    sourceUrl: `https://stooq.com/q/?s=${encodeURIComponent(stooqSymbol)}`,
  };
}

function finiteOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
```

- [ ] **Step 2: Smoke-check the formatter (no network)**

Run: `npx tsx -e "import {formatMarketCapUsd} from './lib/quotes.ts'; console.log(formatMarketCapUsd(5.2e12), formatMarketCapUsd(1.5e12), formatMarketCapUsd(840e9), formatMarketCapUsd(null));"`
Expected: `$5.2T $1.5T $840B null`

- [ ] **Step 3: Type-check + lint**

Run: `npm run build && npm run lint`
Expected: build succeeds, lint clean.

- [ ] **Step 4: Commit**

```bash
git add lib/quotes.ts
git commit -m "feat: add lib/quotes.ts generic equity quote fetcher"
```

---

## Task 3: Refactor `lib/nuclearLive.ts` onto `lib/quotes.ts`

**Files:**
- Modify: `lib/nuclearLive.ts`

Goal: no behavior change to `/nuclear`. Replace the in-file Yahoo/Stooq helpers with `fetchEquityQuotes`, mapping `EquityQuote` → `NuclearQuote`.

- [ ] **Step 1: Replace the quote-fetching internals**

In `lib/nuclearLive.ts`:
- Add import: `import { fetchEquityQuotes, type EquityQuote } from "./quotes";`
- Delete the now-duplicated helpers: `fetchYahooQuotes`, `fetchYahooQuotesFromHost`, `normalizeQuote`, `fetchStooqQuotes`, `fetchStooqQuote`, the `YahooQuote`/`YahooQuoteResponse` types, `HOSTS`, `BROWSER_HEADERS`, and `finiteOrNull` (uranium index keeps using its own logic; if `finiteOrNull` is still referenced elsewhere, keep it).
- Keep `MARKET_CAP_USD_BY_SYMBOL`, `NAME_BY_SYMBOL`, `PUBLIC_SYMBOLS`, `URANIUM_PROXY_SYMBOLS`, `REFRESH_CADENCE_SECONDS`, `fetchUraniumIndex`, and all interfaces/response shaping.
- Rewrite the quote-acquisition section of `fetchNuclearMarketLive` to:

```ts
  const { quotes: equityQuotes, source: quoteSource, errors: quoteErrors } =
    await fetchEquityQuotes(symbols, {
      snapshotMarketCapUsd: MARKET_CAP_USD_BY_SYMBOL,
      nameBySymbol: NAME_BY_SYMBOL,
      revalidateSeconds: REFRESH_CADENCE_SECONDS,
    });
  errors.push(...quoteErrors);

  let source = "Yahoo Finance quote API";
  let note =
    "Public equities use live/delayed exchange quotes. Market caps fall back to the dashboard snapshot if the quote source does not provide them. Uranium proxies are equity ETFs.";
  if (quoteSource === "stooq") {
    source = "Stooq quote CSV fallback";
    note =
      "Public equities use delayed Stooq quotes. Market caps use the dashboard snapshot because Stooq does not provide them; percentage moves are calculated from the daily open. Uranium proxies are equity ETFs.";
  }

  const quotes: NuclearQuote[] = equityQuotes.map(toNuclearQuote);
```

- Add the mapper:

```ts
function toNuclearQuote(q: EquityQuote): NuclearQuote {
  return {
    symbol: q.symbol,
    name: q.name ?? q.symbol,
    price: q.price,
    changePercent: q.changePercent,
    marketCapUsd: q.marketCapUsd,
    marketCapSource: q.marketCapSource,
    currency: q.currency,
    exchange: q.exchange,
    regularMarketTime: q.asOfUnix,
    sourceUrl: q.sourceUrl,
  };
}
```

- Ensure the `return { ... }` still uses `checkedAt`, `refreshCadenceSeconds: REFRESH_CADENCE_SECONDS`, `source`, `note`, `publicEquities`, `uraniumProxies`, `totalPublicMarketCapUsd`, `uraniumIndex`, `errors` (unchanged shaping; `bySymbol`/`publicEquities`/`uraniumProxies`/`sumMarketCap` logic stays).

- [ ] **Step 2: Type-check + lint**

Run: `npm run build && npm run lint`
Expected: build succeeds, lint clean. (Watch for unused-symbol lint errors from deleted helpers.)

- [ ] **Step 3: Manual regression check**

Run: `npm run dev`, open `http://localhost:3000/nuclear`, confirm the live market panel still renders quotes, market caps, and the uranium index (or shows the same graceful fallback as before). Stop the dev server.

- [ ] **Step 4: Commit**

```bash
git add lib/nuclearLive.ts
git commit -m "refactor: nuclearLive consumes shared lib/quotes.ts (no behavior change)"
```

---

## Task 4: `lib/aiSnapshot.schema.ts` — types + validators

**Files:**
- Create: `lib/aiSnapshot.schema.ts`

- [ ] **Step 1: Create the schema module**

```ts
// Shape + runtime validation for lib/aiSnapshot.json. Used by aiMetrics.ts
// (validate on read) and scripts/refresh-snapshots.ts (validate before write).
import type { Status } from "./metrics";
import type { Confidence } from "./aiMetrics";

export interface SnapshotSource {
  name: string;
  url: string;
  asOf: string; // YYYY-MM-DD
  confidence: Confidence;
}

export interface SnapshotPlayer {
  marketCap?: string;
  valuationEstimate?: string;
  adoptionSignal: string;
  aiExposure: string;
  status: Status;
  source: SnapshotSource;
}

export interface SnapshotMetric {
  value: string;
  context: string;
  detail: string;
  status: Status;
  source: SnapshotSource;
}

export interface SnapshotSignal {
  label: string;
  summary: string;
  watchNext: string;
  status: Status;
  source: SnapshotSource;
}

export interface AiSnapshot {
  verdict: { text: string; asOf: string };
  players: Record<string, SnapshotPlayer>;
  marketMetrics: Record<string, SnapshotMetric>;
  techSignals: Record<string, SnapshotSignal>;
}

const STATUSES: Status[] = ["calm", "neutral", "elevated", "stressed"];
const CONFIDENCES: Confidence[] = ["high", "medium", "low"];
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function str(v: unknown, max = 600): v is string {
  return typeof v === "string" && v.trim().length > 0 && v.length <= max;
}

function isSource(v: unknown): v is SnapshotSource {
  const s = v as SnapshotSource;
  return (
    !!s &&
    str(s.name, 200) &&
    str(s.url, 500) &&
    typeof s.asOf === "string" &&
    ISO_DATE.test(s.asOf) &&
    CONFIDENCES.includes(s.confidence)
  );
}

// Returns [] when valid, otherwise a list of human-readable problems.
export function validateAiSnapshot(data: unknown, rosterIds: {
  players: string[];
  marketMetrics: string[];
  techSignals: string[];
}): string[] {
  const errors: string[] = [];
  const snap = data as AiSnapshot;
  if (!snap || typeof snap !== "object") return ["snapshot is not an object"];

  if (!snap.verdict || !str(snap.verdict.text, 1200) || !ISO_DATE.test(snap.verdict.asOf ?? "")) {
    errors.push("verdict: missing text or invalid asOf");
  }

  for (const id of rosterIds.players) {
    const p = snap.players?.[id];
    if (!p) { errors.push(`players.${id}: missing`); continue; }
    if (!p.marketCap && !p.valuationEstimate)
      errors.push(`players.${id}: needs marketCap or valuationEstimate`);
    if (!str(p.adoptionSignal) || !str(p.aiExposure)) errors.push(`players.${id}: prose invalid`);
    if (!STATUSES.includes(p.status)) errors.push(`players.${id}: bad status`);
    if (!isSource(p.source)) errors.push(`players.${id}: bad source`);
  }

  for (const id of rosterIds.marketMetrics) {
    const m = snap.marketMetrics?.[id];
    if (!m) { errors.push(`marketMetrics.${id}: missing`); continue; }
    if (!str(m.value, 60) || !str(m.context, 120) || !str(m.detail)) errors.push(`marketMetrics.${id}: prose invalid`);
    if (!STATUSES.includes(m.status)) errors.push(`marketMetrics.${id}: bad status`);
    if (!isSource(m.source)) errors.push(`marketMetrics.${id}: bad source`);
  }

  for (const id of rosterIds.techSignals) {
    const t = snap.techSignals?.[id];
    if (!t) { errors.push(`techSignals.${id}: missing`); continue; }
    if (!str(t.label, 120) || !str(t.summary) || !str(t.watchNext)) errors.push(`techSignals.${id}: prose invalid`);
    if (!STATUSES.includes(t.status)) errors.push(`techSignals.${id}: bad status`);
    if (!isSource(t.source)) errors.push(`techSignals.${id}: bad source`);
  }

  return errors;
}
```

- [ ] **Step 2: Type-check + lint**

Run: `npm run build && npm run lint`
Expected: build succeeds (note: `Confidence` must be exported from `aiMetrics.ts` — it already is, line `export type Confidence`), lint clean.

- [ ] **Step 3: Commit**

```bash
git add lib/aiSnapshot.schema.ts
git commit -m "feat: add aiSnapshot schema + validator"
```

---

## Task 5: `lib/aiSnapshot.json` — seed from current data

**Files:**
- Create: `lib/aiSnapshot.json`

**Extraction rule (deterministic):** Copy every volatile field out of the current `lib/aiMetrics.ts` literal into JSON, **verbatim**. For each player/metric/signal, lift its `source` from the referenced `s.<key>` object in `aiMetrics.ts` (the `name`, `url`, `asOf`, `confidence`). The roster ids and counts must match exactly: **11 players** (`nvidia, alphabet, microsoft, amazon, broadcom, meta, openai, anthropic, databricks, cursor, perplexity`), **6 marketMetrics** (`capex-race, private-valuation, consumer-scale, coding-agent, open-pressure, agent-reliability`), **4 techSignals** (`frontier-models, agents, ai-ides, compute-stack`). `verdict.text` = the current `getAiDashboardData()` verdict string; `verdict.asOf` = `"2026-05-27"` (the current `snapshotDate`).

- [ ] **Step 1: Create `lib/aiSnapshot.json` following the shape below**

Worked examples (one per shape — fill the rest the same way from `aiMetrics.ts`):

```jsonc
{
  "verdict": {
    "text": "AI is no longer a feature cycle; it is a capital cycle. Public value is concentrated in compute and cloud, private value is concentrated in frontier labs and workflow agents, and the next proof point is whether agents can convert huge usage into durable, auditable revenue.",
    "asOf": "2026-05-27"
  },
  "players": {
    "nvidia": {
      "marketCap": "$5.2T",
      "adoptionSignal": "Default accelerator stack for training and inference clusters.",
      "aiExposure": "Cleanest public-market proxy for frontier AI compute demand.",
      "status": "stressed",
      "source": {
        "name": "StockAnalysis / public market-cap snapshots",
        "url": "https://stockanalysis.com/stocks/nvda/market-cap/",
        "asOf": "2026-05-22",
        "confidence": "medium"
      }
    },
    "openai": {
      "valuationEstimate": "~$840B post-money",
      "adoptionSignal": "ChatGPT reported 900M weekly active users and 50M paid subscribers.",
      "aiExposure": "Consumer AI distribution leader with enterprise, API, coding, and agent ambitions.",
      "status": "stressed",
      "source": {
        "name": "TechCrunch, OpenAI funding and ChatGPT users",
        "url": "https://techcrunch.com/2026/02/27/openai-raises-110b-in-one-of-the-largest-private-funding-rounds-in-history/",
        "asOf": "2026-02-27",
        "confidence": "medium"
      }
    }
    // ... alphabet, microsoft, amazon, broadcom, meta (public),
    //     anthropic, databricks, cursor, perplexity (private)
  },
  "marketMetrics": {
    "consumer-scale": {
      "value": "900M WAU",
      "context": "Reported February 2026",
      "detail": "Consumer AI has crossed mass-market scale; the open question is revenue per active user and retention by task.",
      "status": "stressed",
      "source": {
        "name": "TechCrunch, ChatGPT weekly active users",
        "url": "https://techcrunch.com/2026/02/27/chatgpt-reaches-900m-weekly-active-users/",
        "asOf": "2026-02-27",
        "confidence": "medium"
      }
    }
    // ... capex-race, private-valuation, coding-agent, open-pressure, agent-reliability
  },
  "techSignals": {
    "frontier-models": {
      "label": "Frontier models are multimodal operating systems",
      "summary": "The leading labs are bundling text, code, vision, voice, memory, tools, and computer use into one platform surface.",
      "watchNext": "Watch whether model gains translate into lower cost per completed task, not just higher benchmark scores.",
      "status": "elevated",
      "source": {
        "name": "TechCrunch, OpenAI funding and ChatGPT users",
        "url": "https://techcrunch.com/2026/02/27/openai-raises-110b-in-one-of-the-largest-private-funding-rounds-in-history/",
        "asOf": "2026-02-27",
        "confidence": "medium"
      }
    }
    // ... agents, ai-ides, compute-stack
  }
}
```

(Remove the `//` comments — strict JSON.)

- [ ] **Step 2: Verify it parses and passes schema**

Run:
```bash
npx tsx -e "import s from './lib/aiSnapshot.json' with { type: 'json' }; import {validateAiSnapshot} from './lib/aiSnapshot.schema.ts'; const ids={players:['nvidia','alphabet','microsoft','amazon','broadcom','meta','openai','anthropic','databricks','cursor','perplexity'],marketMetrics:['capex-race','private-valuation','consumer-scale','coding-agent','open-pressure','agent-reliability'],techSignals:['frontier-models','agents','ai-ides','compute-stack']}; const e=validateAiSnapshot(s,ids); console.log(e.length? e : 'VALID');"
```
Expected: `VALID`. If it prints errors, fix the JSON until it prints `VALID`.

- [ ] **Step 3: Commit**

```bash
git add lib/aiSnapshot.json
git commit -m "feat: seed lib/aiSnapshot.json from current AI snapshot"
```

---

## Task 6: Refactor `lib/aiMetrics.ts` to build from roster + JSON

**Files:**
- Modify: `lib/aiMetrics.ts`

Keep all `interface`/`type` exports and `AI_GROUPS`. Replace the giant `players`/`marketMetrics`/`techSignals` literals and the `s` source map with a **roster** (identity only) and a builder that merges `aiSnapshot.json`. Add an async live variant.

- [ ] **Step 1: Replace the data literals with rosters**

Remove the `const source = ...`, the `const s = {...}` map, and the three full literal arrays (`players`, `marketMetrics`, `techSignals`). Replace with roster constants (identity fields only):

```ts
import snapshot from "./aiSnapshot.json" with { type: "json" };
import { validateAiSnapshot, type AiSnapshot } from "./aiSnapshot.schema";
import { fetchEquityQuotes, formatMarketCapUsd } from "./quotes";

type PlayerRoster = Pick<AiPlayer, "id" | "kind" | "name" | "category"> & { ticker?: string };
type MetricRoster = Pick<AiMarketMetric, "id" | "group">;
type SignalRoster = Pick<AiTechSignal, "id" | "track">;

const PLAYER_ROSTER: PlayerRoster[] = [
  { id: "nvidia", kind: "public", name: "NVIDIA", ticker: "NVDA", category: "AI compute" },
  { id: "alphabet", kind: "public", name: "Alphabet", ticker: "GOOGL", category: "Models, search, cloud" },
  { id: "microsoft", kind: "public", name: "Microsoft", ticker: "MSFT", category: "Enterprise agents" },
  { id: "amazon", kind: "public", name: "Amazon", ticker: "AMZN", category: "Cloud and retail agents" },
  { id: "broadcom", kind: "public", name: "Broadcom", ticker: "AVGO", category: "AI networking and ASICs" },
  { id: "meta", kind: "public", name: "Meta", ticker: "META", category: "Consumer AI and open models" },
  { id: "openai", kind: "private", name: "OpenAI", category: "Frontier lab and agent platform" },
  { id: "anthropic", kind: "private", name: "Anthropic", category: "Frontier lab" },
  { id: "databricks", kind: "private", name: "Databricks", category: "Data and AI platform" },
  { id: "cursor", kind: "private", name: "Cursor / Anysphere", category: "Coding agent" },
  { id: "perplexity", kind: "private", name: "Perplexity", category: "Answer engine and agents" },
];

const METRIC_ROSTER: MetricRoster[] = [
  { id: "capex-race", group: "capital" },
  { id: "private-valuation", group: "capital" },
  { id: "consumer-scale", group: "adoption" },
  { id: "coding-agent", group: "adoption" },
  { id: "open-pressure", group: "technology" },
  { id: "agent-reliability", group: "risk" },
];

const SIGNAL_ROSTER: SignalRoster[] = [
  { id: "frontier-models", track: "Models" },
  { id: "agents", track: "Agents" },
  { id: "ai-ides", track: "Tools" },
  { id: "compute-stack", track: "Infra" },
];

const ROSTER_IDS = {
  players: PLAYER_ROSTER.map((p) => p.id),
  marketMetrics: METRIC_ROSTER.map((m) => m.id),
  techSignals: SIGNAL_ROSTER.map((s) => s.id),
};

const SNAPSHOT = snapshot as AiSnapshot;
```

- [ ] **Step 2: Add the source mapper + builder, replacing `getAiDashboardData()`**

`AiSource` has `{ name, url, asOf, confidence }` — the JSON `source` is identical, so it maps directly. Replace the old `getAiDashboardData` with:

```ts
function freshestAsOf(): string {
  const dates = [
    SNAPSHOT.verdict.asOf,
    ...Object.values(SNAPSHOT.players).map((p) => p.source.asOf),
    ...Object.values(SNAPSHOT.marketMetrics).map((m) => m.source.asOf),
    ...Object.values(SNAPSHOT.techSignals).map((t) => t.source.asOf),
  ].filter(Boolean);
  return dates.sort().at(-1) ?? SNAPSHOT.verdict.asOf;
}

export function getAiDashboardData(): AiDashboardData {
  if (process.env.NODE_ENV !== "production") {
    const errors = validateAiSnapshot(SNAPSHOT, ROSTER_IDS);
    if (errors.length) throw new Error(`aiSnapshot.json invalid:\n${errors.join("\n")}`);
  }

  const players: AiPlayer[] = PLAYER_ROSTER.map((r) => {
    const c = SNAPSHOT.players[r.id];
    return {
      ...r,
      marketCap: c?.marketCap,
      valuationEstimate: c?.valuationEstimate,
      adoptionSignal: c?.adoptionSignal ?? "",
      aiExposure: c?.aiExposure ?? "",
      status: c?.status ?? "neutral",
      source: c.source,
    };
  });

  const marketMetrics: AiMarketMetric[] = METRIC_ROSTER.map((r) => {
    const c = SNAPSHOT.marketMetrics[r.id];
    return { ...r, label: metricLabel(r.id), value: c.value, context: c.context, detail: c.detail, status: c.status, source: c.source };
  });

  const techSignals: AiTechSignal[] = SIGNAL_ROSTER.map((r) => {
    const c = SNAPSHOT.techSignals[r.id];
    return { ...r, label: c.label, status: c.status, summary: c.summary, watchNext: c.watchNext, source: c.source };
  });

  return { snapshotDate: freshestAsOf(), verdict: SNAPSHOT.verdict.text, players, marketMetrics, techSignals };
}
```

Note: `AiMarketMetric` has a `label` field that was prose-ish in the original (e.g. "Hyperscaler AI capex"). Keep those labels stable in code via a small map (they describe the metric identity, not a volatile figure):

```ts
const METRIC_LABELS: Record<string, string> = {
  "capex-race": "Hyperscaler AI capex",
  "private-valuation": "Private lab valuations",
  "consumer-scale": "ChatGPT reach",
  "coding-agent": "Coding assistants",
  "open-pressure": "Open-model pressure",
  "agent-reliability": "Agent reliability",
};
function metricLabel(id: string): string { return METRIC_LABELS[id] ?? id; }
```

- [ ] **Step 3: Add the async live builder**

```ts
const PUBLIC_TICKERS: Record<string, string> = {
  nvidia: "NVDA", alphabet: "GOOGL", microsoft: "MSFT", amazon: "AMZN", broadcom: "AVGO", meta: "META",
};

export async function getAiDashboardDataLive(): Promise<AiDashboardData> {
  const data = getAiDashboardData();
  try {
    const symbols = Object.values(PUBLIC_TICKERS);
    const { quotes } = await fetchEquityQuotes(symbols);
    const capBySymbol = new Map(
      quotes.filter((q) => q.marketCapSource === "live").map((q) => [q.symbol, q.marketCapUsd]),
    );
    data.players = data.players.map((p) => {
      const ticker = PUBLIC_TICKERS[p.id];
      const cap = ticker ? capBySymbol.get(ticker) : null;
      const formatted = formatMarketCapUsd(cap ?? null);
      return formatted ? { ...p, marketCap: formatted } : p;
    });
  } catch {
    // keep snapshot values on any failure (resilience norm)
  }
  return data;
}
```

- [ ] **Step 4: Type-check + lint**

Run: `npm run build && npm run lint`
Expected: build succeeds, lint clean. The ask/explain routes still compile (they import `getAiDashboardData`, unchanged).

- [ ] **Step 5: Commit**

```bash
git add lib/aiMetrics.ts
git commit -m "refactor: aiMetrics builds from roster + aiSnapshot.json; add live builder"
```

---

## Task 7: Wire `app/ai/page.tsx` to the live builder

**Files:**
- Modify: `app/ai/page.tsx`

- [ ] **Step 1: Make the page async + live**

Replace the body with:

```tsx
import type { Metadata } from "next";
import AiDashboard from "@/components/ai/AiDashboard";
import { getAiDashboardDataLive } from "@/lib/aiMetrics";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "AI & Agent World Monitor",
  description:
    "Curated investor/founder dashboard for AI market leaders, private labs, agent adoption, and technology signals.",
};

export default async function AiPage() {
  const data = await getAiDashboardDataLive();
  return <AiDashboard data={data} />;
}
```

- [ ] **Step 2: Type-check + lint**

Run: `npm run build && npm run lint`
Expected: build succeeds, lint clean.

- [ ] **Step 3: Manual check**

Run: `npm run dev`, open `/ai`. Confirm public-player market caps render (live values if the quote API is reachable; snapshot strings otherwise) and the page renders fully. Stop dev server.

- [ ] **Step 4: Commit**

```bash
git add app/ai/page.tsx
git commit -m "feat: /ai page fetches live market caps with snapshot fallback"
```

---

## Task 8: Freshness indicators in `components/ai/AiDashboard.tsx`

**Files:**
- Modify: `components/ai/AiDashboard.tsx`

- [ ] **Step 1: Add a freshness dot + header label**

At the top of the file, add:

```tsx
import { freshnessOf, overallFreshness, type Freshness } from "@/lib/freshness";
```

Add a small component near `StatusDot`:

```tsx
const FRESHNESS_TITLE: Record<Freshness, string> = {
  fresh: "Recently refreshed",
  aging: "Aging — over 30 days old",
  stale: "Stale — over 90 days old",
};
const FRESHNESS_COLOR: Record<Freshness, string> = {
  fresh: "var(--accent-purple)",
  aging: "oklch(0.82 0.14 80)",
  stale: "oklch(0.70 0.20 25)",
};

function FreshnessDot({ asOf }: { asOf: string }) {
  const level = freshnessOf(asOf);
  return (
    <span
      title={`${FRESHNESS_TITLE[level]} · as of ${asOf}`}
      aria-label={FRESHNESS_TITLE[level]}
      style={{ display: "inline-block", width: 6, height: 6, borderRadius: 9999, background: FRESHNESS_COLOR[level] }}
    />
  );
}
```

- [ ] **Step 2: Use overall freshness in the header**

In `AiDashboard`, compute and render it next to the existing date line. Replace the header's right-hand `<p>` (currently `Curated snapshot · {displayDate}`) with:

```tsx
        <p className="mono inline-flex items-center gap-1.5 text-[11.5px] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">
          <FreshnessDot asOf={data.snapshotDate} />
          Snapshot · refreshed {displayDate}
        </p>
```

Where `overallFreshness` is available if you prefer an aggregate; the simplest correct version dots the header by `data.snapshotDate` (the freshest as-of). (Keep the `overallFreshness` import only if used; otherwise drop it to satisfy lint.)

- [ ] **Step 3: Add per-item dots**

In `MetricTile`, add a `<FreshnessDot asOf={metric.source.asOf} />` inside the top row next to the `i` affordance. In `PlayerPanel`'s row, add `<FreshnessDot asOf={player.source.asOf} />` in the value column. In `SignalTile`, add it in the header row. Keep changes minimal and use existing flex containers.

- [ ] **Step 4: Type-check + lint**

Run: `npm run build && npm run lint`
Expected: build succeeds, lint clean (remove any unused import).

- [ ] **Step 5: Manual check**

Run `npm run dev`, open `/ai`, confirm dots appear and hover titles show the as-of date. Stop dev server.

- [ ] **Step 6: Commit**

```bash
git add components/ai/AiDashboard.tsx
git commit -m "feat: surface data freshness on the /ai dashboard"
```

---

## Task 9: Honesty wording in `lib/aiPrompts.ts`

**Files:**
- Modify: `lib/aiPrompts.ts`

- [ ] **Step 1: Update `sharedAiContext`**

Replace the first paragraph of `sharedAiContext` with wording that stays truthful once live caps are merged:

```ts
  return `You are an AI market analyst embedded in a dashboard called
"AI & Agent World Monitor". You are given a dated SNAPSHOT last refreshed on
${data.snapshotDate}, plus a few public-company market caps that may be live
exchange quotes. Treat every figure as provided context. Do not imply broader
real-time knowledge, and never invent user counts, valuations, market caps,
revenue, or funding beyond what the snapshot provides.
```

(Keep the `Snapshot (JSON): ${JSON.stringify(data, null, 2)}` block and all "Ground rules" lines unchanged.)

- [ ] **Step 2: Type-check + lint**

Run: `npm run build && npm run lint`
Expected: build succeeds, lint clean.

- [ ] **Step 3: Commit**

```bash
git add lib/aiPrompts.ts
git commit -m "chore: prompt wording reflects snapshot + live caps honestly"
```

---

## Task 10: `scripts/refresh-snapshots.ts` + npm script

**Files:**
- Create: `scripts/refresh-snapshots.ts`
- Modify: `package.json` (add `refresh:snapshots` script)

> **Implementation note:** Invoke the `claude-api` skill while writing the SDK call — confirm the exact `web_search` tool block and prompt-caching syntax for `@anthropic-ai/sdk` ^0.98. The block below targets `web_search_20250305` (verified present in the installed SDK types).

- [ ] **Step 1: Add the npm script**

In `package.json` `scripts`, add: `"refresh:snapshots": "tsx scripts/refresh-snapshots.ts"`.

- [ ] **Step 2: Create `scripts/refresh-snapshots.ts`**

```ts
/**
 * Refreshes lib/aiSnapshot.json using Claude + web search.
 * Run: ENABLE_WEB_SEARCH=true ANTHROPIC_API_KEY=... npm run refresh:snapshots [-- --dry-run]
 * Guardrails: every changed field must cite a source; unverifiable fields keep
 * their prior value; the document is schema-validated before any write.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import Anthropic from "@anthropic-ai/sdk";
import { validateAiSnapshot, type AiSnapshot } from "../lib/aiSnapshot.schema";

const ROSTER_IDS = {
  players: ["nvidia", "alphabet", "microsoft", "amazon", "broadcom", "meta", "openai", "anthropic", "databricks", "cursor", "perplexity"],
  marketMetrics: ["capex-race", "private-valuation", "consumer-scale", "coding-agent", "open-pressure", "agent-reliability"],
  techSignals: ["frontier-models", "agents", "ai-ides", "compute-stack"],
};

const SNAPSHOT_PATH = resolve(process.cwd(), "lib/aiSnapshot.json");
const MODEL = process.env.REFRESH_MODEL ?? "claude-sonnet-4-6";
const DRY_RUN = process.argv.includes("--dry-run");

function die(msg: string): never {
  console.error(`refresh-snapshots: ${msg}`);
  process.exit(1);
}

async function main() {
  if (process.env.ENABLE_WEB_SEARCH !== "true") die("set ENABLE_WEB_SEARCH=true to run the refresh");
  if (!process.env.ANTHROPIC_API_KEY) die("ANTHROPIC_API_KEY is required");

  const prior = JSON.parse(readFileSync(SNAPSHOT_PATH, "utf8")) as AiSnapshot;
  const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

  const system = [
    "You update a JSON snapshot for an AI-market dashboard. You are given the CURRENT snapshot.",
    "Use web search to verify each value. Return ONLY a JSON object with the SAME keys and structure as the input.",
    "Rules:",
    "- Keep the exact same top-level keys and the exact same ids under players/marketMetrics/techSignals. Do not add, remove, or rename ids.",
    "- For every field you change, set source.url to a web page you actually consulted and source.asOf to the publication/observation date (YYYY-MM-DD), and set source.confidence (high|medium|low).",
    "- If you cannot verify a field from a credible source, return its PRIOR value unchanged. Never guess, never blank.",
    "- status is one of: calm, neutral, elevated, stressed.",
    "- Keep prose fields roughly the same length and neutral analyst tone (adoptionSignal/aiExposure ≤ ~160 chars; detail/summary/watchNext ≤ ~220 chars; verdict.text ≤ ~600 chars).",
    "- Output strict JSON only. No markdown, no commentary.",
  ].join("\n");

  const response = await anthropic.messages.create({
    model: MODEL,
    max_tokens: 8000,
    tools: [{ type: "web_search_20250305", name: "web_search", max_uses: 8 }],
    system: [{ type: "text", text: system, cache_control: { type: "ephemeral" } }],
    messages: [
      { role: "user", content: `CURRENT snapshot:\n${JSON.stringify(prior, null, 2)}\n\nReturn the updated snapshot as strict JSON.` },
    ],
  });

  const text = response.content
    .filter((b): b is Anthropic.TextBlock => b.type === "text")
    .map((b) => b.text)
    .join("");
  const next = extractJson(text);
  if (!next) die("model did not return parseable JSON");

  const merged = mergeKnownKeys(prior, next as AiSnapshot);
  const errors = validateAiSnapshot(merged, ROSTER_IDS);
  if (errors.length) die(`refreshed snapshot failed validation:\n${errors.join("\n")}`);

  const changed = diffSummary(prior, merged);
  if (DRY_RUN) {
    console.log("DRY RUN — changes that would be written:\n" + (changed || "(none)"));
    return;
  }
  writeFileSync(SNAPSHOT_PATH, JSON.stringify(merged, null, 2) + "\n", "utf8");
  console.log("Wrote lib/aiSnapshot.json\nChanges:\n" + (changed || "(none)"));
}

function extractJson(text: string): unknown {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) return null;
  try { return JSON.parse(text.slice(start, end + 1)); } catch { return null; }
}

// Only copy keys that already exist in `prior` — prevents id drift / injection.
function mergeKnownKeys(prior: AiSnapshot, next: AiSnapshot): AiSnapshot {
  const out: AiSnapshot = JSON.parse(JSON.stringify(prior));
  out.verdict = { text: next.verdict?.text ?? prior.verdict.text, asOf: next.verdict?.asOf ?? prior.verdict.asOf };
  for (const id of Object.keys(prior.players)) if (next.players?.[id]) out.players[id] = next.players[id];
  for (const id of Object.keys(prior.marketMetrics)) if (next.marketMetrics?.[id]) out.marketMetrics[id] = next.marketMetrics[id];
  for (const id of Object.keys(prior.techSignals)) if (next.techSignals?.[id]) out.techSignals[id] = next.techSignals[id];
  return out;
}

function diffSummary(prior: AiSnapshot, next: AiSnapshot): string {
  const lines: string[] = [];
  const a = JSON.stringify(prior), b = JSON.stringify(next);
  if (a === b) return "";
  const walk = (pa: Record<string, unknown>, pb: Record<string, unknown>, path: string) => {
    for (const k of Object.keys(pb)) {
      const va = (pa as Record<string, unknown>)?.[k], vb = pb[k];
      if (typeof vb === "object" && vb) walk((va ?? {}) as Record<string, unknown>, vb as Record<string, unknown>, `${path}${k}.`);
      else if (JSON.stringify(va) !== JSON.stringify(vb)) lines.push(`${path}${k}: ${JSON.stringify(va)} → ${JSON.stringify(vb)}`);
    }
  };
  walk(prior as unknown as Record<string, unknown>, next as unknown as Record<string, unknown>, "");
  return lines.join("\n");
}

main().catch((e) => die(e instanceof Error ? e.message : String(e)));
```

- [ ] **Step 3: Guardrail check without an API key (must refuse cleanly)**

Run: `npm run refresh:snapshots`
Expected: exits non-zero with `refresh-snapshots: set ENABLE_WEB_SEARCH=true to run the refresh`.

- [ ] **Step 4: Type-check + lint**

Run: `npm run build && npm run lint`
Expected: build succeeds (the script is type-checked by `tsc` via the build/`tsx`), lint clean.

- [ ] **Step 5: (Optional, needs a real key) live dry-run**

Run: `ENABLE_WEB_SEARCH=true ANTHROPIC_API_KEY=sk-... npm run refresh:snapshots -- --dry-run`
Expected: prints a change list (or "(none)") and writes nothing. If validation fails, the script exits non-zero without writing — that is correct behavior.

- [ ] **Step 6: Commit**

```bash
git add scripts/refresh-snapshots.ts package.json
git commit -m "feat: add AI snapshot refresh script (Claude + web search)"
```

---

## Task 11: GitHub Action + docs

**Files:**
- Create: `.github/workflows/refresh-snapshots.yml`
- Modify: `.env.example`, `README.md`, `AGENTS.md`

- [ ] **Step 1: Create the workflow**

```yaml
name: Refresh dashboard snapshots
on:
  schedule:
    - cron: "0 6 * * 1" # Mondays 06:00 UTC
  workflow_dispatch: {}

jobs:
  refresh:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - name: Refresh snapshots
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          ENABLE_WEB_SEARCH: "true"
        run: npm run refresh:snapshots
      - name: Open PR
        uses: peter-evans/create-pull-request@v6
        with:
          branch: auto/refresh-snapshots
          title: "chore: refresh dashboard snapshot"
          commit-message: "chore: refresh dashboard snapshot"
          body: |
            Automated weekly refresh of `lib/aiSnapshot.json` (Claude + web search).
            Review the diff and the cited sources before merging.
          labels: automated, data-refresh
          delete-branch: true
```

- [ ] **Step 2: Document the secret + flag**

- In `.env.example`, change `ENABLE_WEB_SEARCH=false` line to keep `false` for local dev but add a comment: `# Set true to allow scripts/refresh-snapshots.ts to use Claude web search.`
- In `README.md`, add a short "Snapshot refresh" subsection: the weekly Action runs `npm run refresh:snapshots` and opens a PR; it needs the repo secret `ANTHROPIC_API_KEY`; run locally with `ENABLE_WEB_SEARCH=true ANTHROPIC_API_KEY=... npm run refresh:snapshots -- --dry-run`.
- In `AGENTS.md`, add one line under data conventions: the `/ai` snapshot lives in `lib/aiSnapshot.json` and is regenerated by `scripts/refresh-snapshots.ts`; edit data there, not in `lib/aiMetrics.ts` (which holds only the roster + builder).

- [ ] **Step 3: Lint YAML / build**

Run: `npm run build && npm run lint`
Expected: build + lint unaffected (no TS change). Confirm the YAML is valid (no tabs, correct indentation).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/refresh-snapshots.yml .env.example README.md AGENTS.md
git commit -m "ci: weekly snapshot refresh workflow that opens a PR"
```

- [ ] **Step 5: Post-merge manual step (cannot be done from the plan)**

After this branch merges: in GitHub repo settings add the `ANTHROPIC_API_KEY` secret, then trigger the workflow via **Actions → Refresh dashboard snapshots → Run workflow** (`workflow_dispatch`) and confirm it opens a PR with a sensible diff. Document this as a checklist item for the user.

---

## Final verification (whole feature)

- [ ] `npm run build` and `npm run lint` are green on the full branch.
- [ ] `/ai` renders with live market caps (snapshot fallback when the quote host is blocked).
- [ ] `/nuclear` live panel is unchanged after the `quotes.ts` refactor.
- [ ] `getAiDashboardData()` still works for the ask/explain routes (open the explain drawer on `/ai`).
- [ ] Freshness dots show on the `/ai` header and tiles.
- [ ] `npm run refresh:snapshots` refuses without `ENABLE_WEB_SEARCH=true`; with a key + `--dry-run` it prints a change list and writes nothing.

---

## Self-Review (completed during planning)

**Spec coverage:** §5.1 snapshot split → Tasks 4–6; §5.2 quotes.ts → Tasks 2–3; §5.3 page wiring → Task 7; §5.4 refresh script → Task 10; §5.5 CI → Task 11; §5.6 staleness UI → Tasks 1, 8; §5.7 prompt contract → Task 9; §6 guardrails → Tasks 4, 10 (validation, mergeKnownKeys, keep-prior, ENABLE_WEB_SEARCH gate, PR review). Roadmap non-goals respected (nuclear refactor is the only allowed cross-cut, Task 3).

**Type consistency:** `EquityQuote.asOfUnix` ↔ `NuclearQuote.regularMarketTime` mapped in `toNuclearQuote` (Task 3). `getAiDashboardData()` name preserved for routes; `getAiDashboardDataLive()` added (Tasks 6–7). `validateAiSnapshot(data, rosterIds)` signature consistent across Tasks 4, 6, 10. `AiSnapshot`/`Confidence`/`Status` types shared.

**Placeholder scan:** Task 5 uses a deterministic extraction rule + full per-shape worked examples (data already exists verbatim in `aiMetrics.ts`); not a placeholder. One explicit human-only post-merge step (Task 11 Step 5: add repo secret) is called out as such.
