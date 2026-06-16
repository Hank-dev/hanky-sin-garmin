"""Presentation layer for the Garmin Coach "athletic cockpit" dashboard.

Pure rendering helpers — they take plain Python values (or a windowed
DataFrame for charts) and return HTML strings / Plotly figures. No Streamlit
imports, no DB, no network, so the visual language stays separable from app.py.

Ported from the Claude Design "Graphite Voltage" handoff
(`Recovery Cockpit - Graphite Voltage.dc.html`), re-skinned to a high-contrast
sport direction: gunmetal surfaces (#121316 base) with brushed-metal striations
+ machined bevels, an electric-lime accent (#C6F23B) for the readiness ring +
brand + positive signals, ice-blue (#7FD3FF) as the cool secondary, gold
(#F2C14E) for caution, red (#FF5A4D) for alarm, and a Spectral serif display
face for the big readiness numeral and headings (Archivo body, JetBrains Mono
micro-labels). The serif numeric hero + sparklines and the design tokens mirror
the handoff's token panel; the trend charts are re-implemented as dark Plotly
per the bundle's colorway (["#C6F23B","#7FD3FF","#F2C14E"], paper #121316, grid
rgba(255,255,255,.06)).
"""
from __future__ import annotations
import html
import json
import re
import itertools

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# ── design tokens (hex mirrors :root below; Plotly needs literals) ────────────
#  "Graphite Voltage" direction — gunmetal surfaces (#121316 base) with
#  brushed-metal striations + machined bevels, an electric-lime accent
#  (#C6F23B) for the readiness ring + brand + positive signals, ice-blue
#  (#7FD3FF) as the cool secondary, gold (#F2C14E) caution, red (#FF5A4D)
#  alarm. High-contrast sport/performance. Mirrors the Claude Design
#  "Graphite Voltage" handoff tokens and Plotly colorway.
BG        = "#121316"   # gunmetal base
BG2       = "#0E1013"   # deepest recess (code blocks, token footer)
SURFACE   = "#16181C"   # card surface
SURFACE2  = "#1C1F24"   # elevated surface (tiles, chips, pills)
SURFACE3  = "#23262C"   # highest surface (brushed panels, icons, badges)
TEXT      = "#E8ECEF"
TEXT_DIM  = "#AEB4BA"
TEXT_FAINT = "#8E959C"
ACCENT    = "#C6F23B"   # volt lime     (ring + brand + positive)
ACCENT2   = "#A6CC2E"   # deeper lime
GOOD      = "#C6F23B"   # volt lime     (positive = accent; GV does not split)
SERIES2   = "#7FD3FF"   # ice blue      (secondary series)
AMBER     = "#F2C14E"   # gold          (caution)
RED       = "#FF5A4D"   # red           (alarm)
GRID      = "rgba(255,255,255,0.06)"

_ids = itertools.count(1)
def _uid() -> str:
    return f"gc{next(_ids)}"


# ════════════════════════════════════════════════════════════════════════════
#  GLOBAL CSS  (injected once by app.py via st.markdown)
# ════════════════════════════════════════════════════════════════════════════
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=Spectral:ital,wght@0,400;0,500;0,600;1,400&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root{
  --bg:#121316; --bg-2:#0E1013; --surface:#16181C; --surface-2:#1C1F24; --surface-3:#23262C;
  --border:rgba(255,255,255,.08); --border-2:rgba(255,255,255,.16);
  --hairline:rgba(255,255,255,.06); --inset-hi:rgba(255,255,255,.05);
  --brass:rgba(255,255,255,.10);
  --text:#E8ECEF; --text-dim:#AEB4BA; --text-faint:#8E959C;
  --accent:#C6F23B; --accent-2:#A6CC2E; --accent-ink:#121316;
  --good:#C6F23B; --series-2:#7FD3FF; --amber:#F2C14E; --red:#FF5A4D;
  --ring-track:rgba(255,255,255,.08);
  --font-sans:"Archivo",system-ui,sans-serif;
  --font-display:"Archivo",system-ui,sans-serif;
  --font-serif:"Spectral",Georgia,serif;
  --font-mono:"JetBrains Mono",ui-monospace,monospace;
  --r-sm:4px; --r-md:8px; --r-lg:14px; --r-xl:18px;
  --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px;
  --sh-card:inset 0 1px 0 var(--inset-hi),0 16px 40px -20px rgba(0,0,0,.8);
  /* brushed-metal striations (1px vertical hairlines) reused across panels */
  --grain:repeating-linear-gradient(90deg, rgba(255,255,255,0.016) 0px, rgba(255,255,255,0.016) 1px, transparent 1px, transparent 3px);
  /* fine machine-noise veil for the whole stage (feTurbulence .85, overlay) */
  --noise:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

/* ── Streamlit chrome → cockpit canvas ─────────────────────────────── */
.stApp{
  background-color:var(--bg);
  background-image:
    var(--grain),
    radial-gradient(900px 480px at 16% -4%, rgba(198,242,59,.10), transparent 62%),
    radial-gradient(120% 80% at 50% 0%, #16181C 0%, #121316 46%, #0E1013 100%);
  background-size:3px 100%, 100% 100%, 100% 100%;
  color:var(--text);
  font-family:var(--font-sans);
}
/* fine machine-noise veil over the whole stage (overlay, very low opacity) */
.stApp::after{
  content:"";position:fixed;inset:0;z-index:9999;pointer-events:none;
  background-image:var(--noise);background-size:180px 180px;
  mix-blend-mode:overlay;opacity:.04;
}
header[data-testid="stHeader"]{background:transparent;pointer-events:none;}
#MainMenu, footer, [data-testid="stToolbar"]{visibility:hidden;}
/* …but keep the "open sidebar" button usable: on narrow screens the sidebar
   auto-collapses and this button is the only way back to the nav. It's nested in
   the hidden toolbar / pointer-events:none header, so re-enable both for it. */
[data-testid="stExpandSidebarButton"], [data-testid="stExpandSidebarButton"] *{visibility:visible!important;}
[data-testid="stExpandSidebarButton"]{pointer-events:auto!important;}
.block-container{max-width:1240px; padding-top:1.2rem; padding-bottom:4rem;}
html, body, [class*="css"]{font-family:var(--font-sans);}
.tnum{font-variant-numeric:tabular-nums;}

/* tighten vertical rhythm between our blocks */
[data-testid="stVerticalBlock"]{gap:.6rem;}

/* ── top bar ───────────────────────────────────────────────────────── */
.topbar{display:flex; align-items:center; gap:var(--s4); margin-bottom:0;}
.brand{display:flex; align-items:center; gap:var(--s3);}
.brand .mark{width:26px;height:26px;flex:0 0 auto;transform:rotate(45deg);
  border:2px solid var(--accent);border-radius:6px;
  box-shadow:inset 0 0 0 3px var(--bg), 0 0 18px color-mix(in srgb,var(--accent) 45%,transparent);}
.brand .name{font-family:var(--font-display);font-weight:700;font-size:18px;letter-spacing:.05em;
  line-height:1.12;text-transform:uppercase;color:var(--text);}
.brand .sub{font-family:var(--font-mono);font-size:9px;color:var(--text-faint);letter-spacing:.24em;text-transform:uppercase;}
.topbar .date{color:var(--text-dim);font-size:13.5px;font-variant-numeric:tabular-nums;}
.topbar .spacer{flex:1;}
.pill{display:inline-flex;align-items:center;gap:7px;padding:6px 12px 6px 10px;border-radius:999px;
  background:var(--surface);border:1px solid var(--border);
  color:var(--text-dim);font-size:12px;font-weight:500;}
.pill .dot{width:6px;height:6px;border-radius:50%;background:var(--good);position:relative;}
.pill .dot::after{content:"";position:absolute;inset:-4px;border-radius:50%;
  border:1px solid var(--good);opacity:.35;animation:ring-pulse 2.8s ease-out infinite;}
@keyframes ring-pulse{0%{transform:scale(.6);opacity:.5;}80%,100%{transform:scale(1.5);opacity:0;}}

/* ── card primitive + bordered Streamlit containers become cards ───── */
/* brushed-metal panels: gunmetal gradient, machined top bevel, vertical striations */
.card{
  background:var(--grain),linear-gradient(180deg,var(--surface-2),var(--surface) 64%,#101216);
  background-size:3px 100%,100% 100%; background-blend-mode:normal,normal;
  border:1px solid var(--border);border-top-color:var(--brass);
  border-radius:var(--r-lg);box-shadow:var(--sh-card);}
[data-testid="stVerticalBlockBorderWrapper"]{
  background:var(--grain),linear-gradient(180deg,var(--surface-2),var(--surface) 64%,#101216);
  background-size:3px 100%,100% 100%; background-blend-mode:normal,normal;
  border:1px solid var(--border)!important;border-top-color:var(--brass)!important;
  border-radius:var(--r-lg);box-shadow:var(--sh-card); padding:6px 18px 10px;}
.section-label{display:flex;align-items:center;gap:var(--s3);font-family:var(--font-mono);
  font-size:10px;font-weight:500;letter-spacing:.22em;text-transform:uppercase;
  color:var(--text-faint);margin:var(--s5) 0 var(--s3);}
.section-label::after{content:"";flex:1;height:1px;background:var(--hairline);}

/* ── hero (serif numeric — the volt signature) ─────────────────────── */
.hero{padding:var(--s6);}
.hero.hero-numeric{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);
  gap:var(--s6);align-items:center;
  background:var(--grain),linear-gradient(180deg,#1A1D22,#16181C 66%,#101216);
  background-size:3px 100%,100% 100%;background-blend-mode:normal,normal;}
.num-block{display:flex;flex-direction:column;gap:14px;min-width:0;}
.kicker{font-family:var(--font-mono);font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:var(--text-faint);}
.bignum{font-family:var(--font-serif);font-weight:400;line-height:.82;letter-spacing:-.02em;
  color:var(--ring-color,var(--accent));display:flex;align-items:baseline;gap:12px;}
.bignum .score{font-size:clamp(96px,12.5vw,170px);font-variant-numeric:tabular-nums;
  text-shadow:0 0 40px color-mix(in oklab,var(--ring-color,var(--accent)) 30%,transparent);}
.bignum.no-score .score{color:var(--text-faint);text-shadow:none;font-size:clamp(64px,8vw,108px);}
.bignum .den{font-family:var(--font-mono);font-size:17px;color:var(--text-faint);letter-spacing:.02em;}
.num-track{height:3px;border-radius:999px;background:var(--ring-track);overflow:hidden;}
.num-fill{display:block;height:100%;border-radius:999px;
  background:linear-gradient(90deg,var(--ring-color,var(--accent)),var(--series-2));}
.verdict{display:flex;flex-direction:column;gap:var(--s4);min-width:0;}
.verdict .vbig{font-family:var(--font-serif);font-weight:400;font-size:clamp(40px,5vw,64px);
  line-height:.98;letter-spacing:0;color:var(--ring-color,var(--accent));
  text-shadow:0 0 28px color-mix(in oklab,var(--ring-color,var(--accent)) 24%,transparent);}
.verdict .vsub{font-family:var(--font-serif);font-style:italic;font-size:21px;line-height:1.34;
  color:var(--text-dim);max-width:36ch;}
.chips{display:flex;flex-wrap:wrap;gap:var(--s2);}
.chip{display:inline-flex;align-items:center;gap:7px;padding:8px 13px;border-radius:999px;font-size:13px;
  font-weight:500;background:var(--surface-2);border:1px solid var(--border);}
.chip .k{color:var(--text-faint);font-family:var(--font-mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;}
.chip .v{font-weight:600;} .chip .ar{font-size:11px;line-height:1;}
.chip.good{border-color:color-mix(in srgb,var(--good) 35%,transparent);
  background:color-mix(in srgb,var(--good) 8%,var(--surface-2));} .chip.good .ar,.chip.good .v{color:var(--good);}
.chip.warn{border-color:color-mix(in srgb,var(--amber) 38%,transparent);
  background:color-mix(in srgb,var(--amber) 8%,var(--surface-2));} .chip.warn .ar,.chip.warn .v{color:var(--amber);}
.chip.bad{border-color:color-mix(in srgb,var(--red) 40%,transparent);
  background:color-mix(in srgb,var(--red) 8%,var(--surface-2));} .chip.bad .ar,.chip.bad .v{color:var(--red);}
.chip.neutral .ar,.chip.neutral .v{color:var(--text);}

/* alert ribbon */
.ribbon{display:flex;align-items:center;gap:var(--s3);margin:0 0 var(--s4);padding:14px var(--s5);
  border-radius:var(--r-md);font-size:14px;font-weight:500;
  background:color-mix(in srgb,var(--red) 12%,var(--surface));
  border:1px solid color-mix(in srgb,var(--red) 34%,transparent);
  color:color-mix(in srgb,var(--red) 60%,var(--text));}
.ribbon.amber{background:color-mix(in srgb,var(--amber) 12%,var(--surface));
  border-color:color-mix(in srgb,var(--amber) 36%,transparent);
  color:color-mix(in srgb,var(--amber) 66%,var(--text));}
.ribbon .ico{font-size:15px;}

/* ── key-stat tiles ────────────────────────────────────────────────── */
.tiles{display:grid;grid-template-columns:repeat(6,1fr);gap:var(--s4);}
.tile{padding:var(--s4) var(--s4) var(--s3);display:flex;flex-direction:column;gap:var(--s2);
  transition:border-color .18s,transform .18s;}
.tile:hover{border-color:var(--border-2);transform:translateY(-2px);}
.tile .tl{font-family:var(--font-mono);font-size:9.5px;font-weight:500;letter-spacing:.16em;
  text-transform:uppercase;color:var(--text-faint);}
.tile .tv{font-family:var(--font-serif);font-weight:400;font-size:38px;line-height:1;
  font-variant-numeric:tabular-nums;letter-spacing:0;display:flex;align-items:baseline;gap:5px;}
.tile .tv u{font-family:var(--font-sans);font-size:13px;font-weight:500;color:var(--text-dim);text-decoration:none;}
.tile .spark{width:100%;height:36px;display:block;}
.tile .spark-empty{height:36px;border-bottom:1px dashed var(--border-2);opacity:.5;}
.delta{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;
  font-variant-numeric:tabular-nums;} .delta .lbl{color:var(--text-faint);font-weight:500;}
.delta.good{color:var(--good);} .delta.bad{color:var(--red);} .delta.flat{color:var(--text-dim);}

/* ── horizontal day rail ───────────────────────────────────────────── */
.day-rail{display:flex;gap:var(--s3);overflow-x:auto;padding:2px 0 9px;scrollbar-width:thin;
  scrollbar-color:rgba(255,255,255,.2) transparent;}
.day-card{min-width:178px;max-width:178px;text-decoration:none;color:var(--text);
  padding:var(--s4) var(--s3);border-radius:var(--r-md);border:1px solid var(--border);border-top-color:var(--brass);
  background:linear-gradient(180deg,var(--surface-2),var(--surface));
  display:grid;gap:11px;box-shadow:var(--sh-card);transition:border-color .16s,transform .16s,box-shadow .16s;}
.day-card:hover{transform:translateY(-2px);border-color:var(--border-2);
  box-shadow:0 14px 30px -18px rgba(0,0,0,.8),var(--sh-card);}
.day-card.selected{border-color:color-mix(in srgb,var(--accent) 50%,transparent);
  box-shadow:0 0 0 1px color-mix(in srgb,var(--accent) 16%,transparent),var(--sh-card);}
.day-top{display:flex;align-items:center;justify-content:space-between;gap:8px;
  padding-bottom:9px;border-bottom:1px solid var(--hairline);}
.day-date{font-weight:600;font-size:13.5px;line-height:1.1;letter-spacing:-.01em;}
.day-flag{display:inline-flex;align-items:center;gap:6px;font-family:var(--font-mono);
  font-size:8.5px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:var(--text-faint);}
.day-tone{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--text-faint);flex:0 0 auto;}
.day-card.good .day-flag{color:var(--good);} .day-card.warn .day-flag{color:var(--amber);} .day-card.bad .day-flag{color:var(--red);}
.day-card.good .day-tone{background:var(--good);box-shadow:0 0 8px color-mix(in srgb,var(--good) 45%,transparent);}
.day-card.warn .day-tone{background:var(--amber);box-shadow:0 0 8px color-mix(in srgb,var(--amber) 40%,transparent);}
.day-card.bad .day-tone{background:var(--red);box-shadow:0 0 8px color-mix(in srgb,var(--red) 40%,transparent);}
.day-stats{display:grid;grid-template-columns:1fr 1fr;gap:7px 14px;}
.day-stat{display:flex;align-items:baseline;justify-content:space-between;gap:7px;min-width:0;}
.day-stat .dl{font-family:var(--font-mono);font-size:8.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-faint);}
.day-stat b{color:var(--text);font-weight:600;font-size:12.5px;font-variant-numeric:tabular-nums;white-space:nowrap;}
.day-acts{display:flex;flex-wrap:wrap;gap:5px;min-height:20px;}
.day-act{display:inline-flex;align-items:center;max-width:100%;padding:3px 7px;border-radius:6px;
  font-size:10px;font-weight:600;color:var(--text-dim);border:1px solid var(--border);
  background:rgba(255,255,255,.025);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.day-act.bjj{color:var(--amber);border-color:color-mix(in srgb,var(--amber) 28%,transparent);
  background:color-mix(in srgb,var(--amber) 10%,transparent);}
.day-empty{color:var(--text-faint);font-size:11px;}

/* ── AI coach readout ──────────────────────────────────────────────── */
.coach{padding:var(--s6);position:relative;overflow:hidden;
  border-color:color-mix(in srgb,var(--accent) 18%,var(--border));
  background:var(--grain),linear-gradient(180deg,#1A1D22,#16181C 66%,#101216);
  background-size:3px 100%,100% 100%;background-blend-mode:normal,normal;}
.coach::before{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;
  background:var(--series-2);opacity:.9;}
.coach-head{display:flex;align-items:center;gap:var(--s3);margin-bottom:var(--s4);}
.coach-head .glyph{width:32px;height:32px;border-radius:9px;display:grid;place-items:center;
  background:color-mix(in srgb,var(--good) 12%,var(--surface));
  border:1px solid color-mix(in srgb,var(--good) 30%,transparent);color:var(--good);}
.coach-head h3{font-family:var(--font-serif);font-size:24px;font-weight:400;margin:0;}
.coach-head .meta{font-size:12px;color:var(--text-faint);}
.coach-body{display:grid;gap:var(--s4);}
.coach-sec h4{font-family:var(--font-mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--text-faint);font-weight:500;margin:0 0 8px;}
.coach-sec p{margin:0;color:var(--text);max-width:74ch;line-height:1.62;}
.coach-sec ul{margin:0;padding:0;list-style:none;display:grid;gap:8px;}
.coach-sec ul li{position:relative;padding-left:18px;color:var(--text);max-width:74ch;line-height:1.55;}
.coach-sec.trends ul li::before{content:"";position:absolute;left:2px;top:9px;width:5px;height:5px;
  border-radius:50%;background:var(--good);}
.coach-sec.todo ol{margin:0;padding:0;list-style:none;counter-reset:t;display:grid;gap:10px;}
.coach-sec.todo li{position:relative;padding-left:30px;counter-increment:t;line-height:1.55;max-width:74ch;}
.coach-sec.todo li::before{content:counter(t);position:absolute;left:0;top:-1px;width:22px;height:22px;
  border-radius:6px;display:grid;place-items:center;font-family:var(--font-mono);font-size:11px;font-weight:500;
  color:var(--accent);background:color-mix(in srgb,var(--accent) 11%,var(--surface));
  border:1px solid color-mix(in srgb,var(--accent) 28%,transparent);}
.coach .prompt{color:var(--text-dim);font-size:14.5px;line-height:1.6;max-width:70ch;}
.disclosure{margin-top:var(--s4);border-top:1px solid var(--hairline);padding-top:var(--s3);}
.disclosure summary{cursor:pointer;font-family:var(--font-mono);font-size:12px;color:var(--text-dim);
  list-style:none;display:inline-flex;align-items:center;gap:7px;letter-spacing:.02em;}
.disclosure summary::-webkit-details-marker{display:none;}
.disclosure summary .caret{font-size:9px;color:var(--text-faint);}
.disclosure[open] summary .caret{transform:rotate(90deg);}
.disclosure pre{margin:var(--s3) 0 0;padding:var(--s4);border-radius:var(--r-md);background:var(--bg-2);
  border:1px solid var(--border);overflow:auto;font-family:var(--font-mono);font-size:12px;
  line-height:1.65;color:var(--text-dim);}
.disclosure pre .k{color:var(--series-2);} .disclosure pre .n{color:var(--accent);} .disclosure pre .s{color:#AAB1B8;}

/* ── capacity envelope ────────────────────────────────────────────── */
.capacity{padding:var(--s6);border-color:color-mix(in srgb,var(--series-2) 16%,var(--border));
  background:var(--grain),linear-gradient(180deg,var(--surface-2),var(--surface) 64%,#101216);
  background-size:3px 100%,100% 100%;background-blend-mode:normal,normal;}
.capacity-head{display:flex;align-items:flex-start;gap:var(--s4);justify-content:space-between;margin-bottom:var(--s4);}
.capacity-head h3{font-family:var(--font-serif);font-size:24px;font-weight:400;margin:0 0 3px;}
.capacity-head .meta{font-size:12px;color:var(--text-faint);}
.cap-zone{display:inline-flex;align-items:center;gap:7px;border-radius:999px;padding:6px 11px;
  font-family:var(--font-mono);font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:.08em;border:1px solid var(--border);}
.cap-zone.green{color:var(--good);border-color:color-mix(in srgb,var(--good) 28%,transparent);background:color-mix(in srgb,var(--good) 8%,transparent);}
.cap-zone.yellow{color:var(--amber);border-color:color-mix(in srgb,var(--amber) 30%,transparent);background:color-mix(in srgb,var(--amber) 9%,transparent);}
.cap-zone.red{color:var(--red);border-color:color-mix(in srgb,var(--red) 32%,transparent);background:color-mix(in srgb,var(--red) 10%,transparent);}
.cap-zone.learning{color:var(--series-2);border-color:color-mix(in srgb,var(--series-2) 30%,transparent);background:color-mix(in srgb,var(--series-2) 8%,transparent);}
.cap-message{color:var(--text);font-size:15px;line-height:1.55;max-width:82ch;margin-bottom:var(--s4);}
.cap-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:var(--s3);}
.cap-metric{border:1px solid var(--border);border-radius:var(--r-md);padding:var(--s3);background:rgba(255,255,255,.02);}
.cap-metric .lab{font-family:var(--font-mono);font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-faint);font-weight:500;}
.cap-metric .now{font-family:var(--font-serif);font-size:28px;font-weight:400;font-variant-numeric:tabular-nums;margin-top:6px;}
.cap-metric .range{font-size:12px;color:var(--text-dim);margin-top:3px;}
.cap-metric.good .now{color:var(--good);} .cap-metric.warn .now{color:var(--amber);}
.cap-metric.bad .now{color:var(--red);} .cap-metric.flat .now{color:var(--text-dim);}
.cap-flags{display:flex;flex-wrap:wrap;gap:var(--s2);margin-top:var(--s4);}
.cap-flag{font-size:12px;color:var(--text-dim);border:1px solid var(--border);border-radius:999px;
  padding:5px 9px;background:rgba(255,255,255,.02);}
.cap-flag.warn{color:var(--amber);border-color:color-mix(in srgb,var(--amber) 25%,transparent);background:color-mix(in srgb,var(--amber) 8%,transparent);}
@media (max-width:900px){ .cap-grid{grid-template-columns:repeat(2,1fr);} }
@media (max-width:420px){ .cap-grid{grid-template-columns:1fr;} .capacity-head{display:grid;} }

/* ── stress leak map ───────────────────────────────────────────────── */
.leak{padding:var(--s6);border-color:color-mix(in srgb,var(--red) 16%,var(--border));
  background:var(--grain),linear-gradient(180deg,var(--surface-2),var(--surface) 64%,#101216);
  background-size:3px 100%,100% 100%;background-blend-mode:normal,normal;}
.leak-head{display:flex;justify-content:space-between;gap:var(--s4);align-items:flex-start;margin-bottom:var(--s4);}
.leak-head h3{font-family:var(--font-serif);font-size:24px;font-weight:400;margin:0 0 3px;}
.leak-head .meta{font-size:12px;color:var(--text-faint);}
.leak-pill{display:inline-flex;align-items:center;border-radius:999px;padding:6px 11px;
  font-family:var(--font-mono);font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;
  border:1px solid var(--border);background:rgba(255,255,255,.025);}
.leak-pill.ready{color:var(--red);border-color:color-mix(in srgb,var(--red) 32%,transparent);background:color-mix(in srgb,var(--red) 8%,transparent);}
.leak-pill.learning{color:var(--series-2);border-color:color-mix(in srgb,var(--series-2) 30%,transparent);background:color-mix(in srgb,var(--series-2) 8%,transparent);}
.leak-message{color:var(--text);font-size:15px;line-height:1.55;max-width:82ch;margin-bottom:var(--s4);}
.leak-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:var(--s3);margin-bottom:var(--s4);}
.leak-stat{border:1px solid var(--border);border-radius:var(--r-md);padding:var(--s3);background:rgba(255,255,255,.02);}
.leak-stat .lab{font-family:var(--font-mono);font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-faint);font-weight:500;}
.leak-stat .val{font-family:var(--font-serif);font-size:28px;font-weight:400;font-variant-numeric:tabular-nums;margin-top:6px;}
.leak-stat .sub{font-size:12px;color:var(--text-dim);margin-top:3px;}
.leak-reason{font-size:13px;color:var(--text-dim);line-height:1.5;margin-bottom:var(--s4);}
.leak-flags{display:flex;flex-wrap:wrap;gap:var(--s2);margin-bottom:var(--s4);}
.leak-flag{font-size:12px;color:var(--text-dim);border:1px solid var(--border);border-radius:999px;
  padding:5px 9px;background:rgba(255,255,255,.02);}
.leak-table{width:100%;border-collapse:collapse;}
.leak-table th,.leak-table td{font-size:12.5px;text-align:right;padding:9px var(--s3);border-top:1px solid var(--hairline);}
.leak-table th{font-family:var(--font-mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-faint);font-weight:500;}
.leak-table th:first-child,.leak-table td:first-child{text-align:left;}
@media (max-width:980px){ .leak-grid{grid-template-columns:repeat(3,1fr);} }
@media (max-width:560px){ .leak-grid{grid-template-columns:repeat(2,1fr);} .leak{overflow-x:auto;} .leak-table{min-width:680px;} }

/* ── discovery panel ──────────────────────────────────────────────── */
.discovery{padding:var(--s6);border-color:color-mix(in srgb,var(--series-2) 18%,var(--border));
  background:var(--grain),linear-gradient(180deg,var(--surface-2),var(--surface) 64%,#101216);
  background-size:3px 100%,100% 100%;background-blend-mode:normal,normal;}
.discovery-head{display:flex;justify-content:space-between;gap:var(--s4);align-items:flex-start;margin-bottom:var(--s4);}
.discovery-head h3{font-family:var(--font-serif);font-size:24px;font-weight:400;margin:0 0 3px;}
.discovery-head .meta{font-size:12px;color:var(--text-faint);}
.discovery-pill{display:inline-flex;align-items:center;border-radius:999px;padding:6px 11px;
  font-family:var(--font-mono);font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;
  border:1px solid var(--border);background:rgba(255,255,255,.025);}
.discovery-pill.ready{color:var(--series-2);border-color:color-mix(in srgb,var(--series-2) 32%,transparent);background:color-mix(in srgb,var(--series-2) 8%,transparent);}
.discovery-pill.learning{color:var(--text-dim);border-color:var(--border-2);}
.discovery-message{color:var(--text);font-size:15px;line-height:1.55;max-width:82ch;margin-bottom:var(--s4);}
.discovery-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:var(--s3);margin-bottom:var(--s4);}
.discovery-stat{border:1px solid var(--border);border-radius:var(--r-md);padding:var(--s3);background:rgba(255,255,255,.02);}
.discovery-stat .lab{font-family:var(--font-mono);font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-faint);font-weight:500;}
.discovery-stat .val{font-family:var(--font-serif);font-size:28px;font-weight:400;font-variant-numeric:tabular-nums;margin-top:6px;}
.discovery-stat .sub{font-size:12px;color:var(--text-dim);margin-top:3px;}
.discovery-list{display:grid;gap:9px;margin-bottom:var(--s4);}
.discovery-item{border-top:1px solid var(--hairline);padding-top:10px;color:var(--text-dim);font-size:13px;line-height:1.5;}
.discovery-item b{color:var(--text);font-weight:600;}
@media (max-width:980px){ .discovery-grid{grid-template-columns:repeat(2,1fr);} }
@media (max-width:520px){ .discovery-grid{grid-template-columns:1fr;} .discovery-head{display:grid;} }

/* ── research health panels ───────────────────────────────────────── */
.research{padding:var(--s6);border-color:color-mix(in srgb,var(--accent) 18%,var(--border));
  background:var(--grain),linear-gradient(180deg,var(--surface-2),var(--surface) 64%,#101216);
  background-size:3px 100%,100% 100%;background-blend-mode:normal,normal;}
.research-head{display:flex;justify-content:space-between;gap:var(--s4);align-items:flex-start;margin-bottom:var(--s4);}
.research-head h3{font-family:var(--font-serif);font-size:24px;font-weight:400;margin:0 0 3px;}
.research-head .meta{font-size:12px;color:var(--text-faint);}
.research-pill{display:inline-flex;align-items:center;border-radius:999px;padding:6px 11px;
  font-family:var(--font-mono);font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;
  border:1px solid var(--border);background:rgba(255,255,255,.025);}
.research-pill.ready,.research-pill.green{color:var(--good);border-color:color-mix(in srgb,var(--good) 30%,transparent);background:color-mix(in srgb,var(--good) 8%,transparent);}
.research-pill.learning,.research-pill.yellow{color:var(--amber);border-color:color-mix(in srgb,var(--amber) 30%,transparent);background:color-mix(in srgb,var(--amber) 8%,transparent);}
.research-pill.no_data,.research-pill.red{color:var(--red);border-color:color-mix(in srgb,var(--red) 30%,transparent);background:color-mix(in srgb,var(--red) 8%,transparent);}
.research-message{color:var(--text);font-size:15px;line-height:1.55;max-width:82ch;margin-bottom:var(--s4);}
.research-panels{display:grid;grid-template-columns:repeat(2,1fr);gap:var(--s4);margin-bottom:var(--s4);}
.research-panel{border:1px solid var(--border);border-radius:var(--r-md);padding:var(--s4);background:rgba(255,255,255,.02);}
.research-panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--s3);margin-bottom:var(--s3);}
.research-panel h4{font-family:var(--font-serif);font-size:20px;font-weight:400;margin:0;}
.research-panel p{color:var(--text-dim);font-size:13.5px;line-height:1.5;margin:0 0 var(--s3);}
.research-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:var(--s2);}
.research-stat{border-top:1px solid var(--hairline);padding-top:9px;min-width:0;}
.research-stat .lab{font-family:var(--font-mono);font-size:8.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-faint);font-weight:500;}
.research-stat .val{font-family:var(--font-serif);font-size:26px;font-weight:400;font-variant-numeric:tabular-nums;margin-top:4px;white-space:nowrap;}
.research-stat .sub{font-size:11.5px;color:var(--text-dim);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.research-flags{display:flex;flex-wrap:wrap;gap:var(--s2);margin-top:var(--s3);}
.research-quality{display:flex;flex-wrap:wrap;gap:var(--s2);border-top:1px solid var(--hairline);padding-top:var(--s3);}
@media (max-width:980px){ .research-panels{grid-template-columns:1fr;} }
@media (max-width:640px){ .research-stats{grid-template-columns:repeat(2,1fr);} .research-head,.research-panel-head{display:grid;} }

/* ── grappling mode ───────────────────────────────────────────────── */
.grapple{padding:var(--s6);border-color:color-mix(in srgb,var(--amber) 18%,var(--border));
  background:var(--grain),linear-gradient(180deg,var(--surface-2),var(--surface) 64%,#101216);
  background-size:3px 100%,100% 100%;background-blend-mode:normal,normal;}
.grapple-head{display:flex;justify-content:space-between;gap:var(--s4);align-items:flex-start;margin-bottom:var(--s4);}
.grapple-head h3{font-family:var(--font-serif);font-size:24px;font-weight:400;margin:0 0 3px;}
.grapple-head .meta{font-size:12px;color:var(--text-faint);}
.grapple-pill{display:inline-flex;align-items:center;border-radius:999px;padding:6px 11px;
  font-family:var(--font-mono);font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;
  color:var(--amber);border:1px solid color-mix(in srgb,var(--amber) 32%,transparent);background:color-mix(in srgb,var(--amber) 8%,transparent);}
.grapple-warning{padding:11px 13px;border-radius:var(--r-md);margin-bottom:var(--s4);
  color:var(--amber);border:1px solid color-mix(in srgb,var(--amber) 30%,transparent);background:color-mix(in srgb,var(--amber) 8%,transparent);}
.grapple-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:var(--s3);margin-bottom:var(--s4);}
.grapple-stat{border:1px solid var(--border);border-radius:var(--r-md);padding:var(--s3);background:rgba(255,255,255,.02);}
.grapple-stat .lab{font-family:var(--font-mono);font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-faint);font-weight:500;}
.grapple-stat .val{font-family:var(--font-serif);font-size:28px;font-weight:400;font-variant-numeric:tabular-nums;margin-top:6px;}
.grapple-stat .sub{font-size:12px;color:var(--text-dim);margin-top:3px;}
.grapple-note{font-size:13px;color:var(--text-dim);line-height:1.5;margin-bottom:var(--s4);}
.grapple-table{width:100%;border-collapse:collapse;}
.grapple-table th,.grapple-table td{font-size:12.5px;text-align:right;padding:9px var(--s3);border-top:1px solid var(--hairline);}
.grapple-table th{font-family:var(--font-mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-faint);font-weight:500;}
.grapple-table th:first-child,.grapple-table td:first-child{text-align:left;}
@media (max-width:980px){ .grapple-grid{grid-template-columns:repeat(3,1fr);} }
@media (max-width:560px){ .grapple-grid{grid-template-columns:repeat(2,1fr);} .grapple{overflow-x:auto;} .grapple-table{min-width:720px;} }

/* ── activities table ──────────────────────────────────────────────── */
.acts{padding:2px 0;}
.acts table{width:100%;border-collapse:collapse;}
.acts thead th{text-align:right;font-family:var(--font-mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--text-faint);font-weight:500;padding:10px var(--s4);}
.acts thead th:first-child,.acts tbody td:first-child{text-align:left;}
.acts tbody td{text-align:right;padding:11px var(--s4);font-size:13.5px;font-variant-numeric:tabular-nums;
  border-top:1px solid var(--hairline);color:var(--text);}
.acts tbody tr:hover td{background:rgba(255,255,255,.02);}
.acts .act-type{display:inline-flex;align-items:center;gap:9px;font-weight:500;}
.acts .act-ico{width:26px;height:26px;border-radius:7px;display:grid;place-items:center;
  background:var(--surface-3);border:1px solid var(--border);color:var(--text-dim);}
.acts .act-ico svg{width:14px;height:14px;} .acts .muted{color:var(--text-faint);}
.te-badge{display:inline-block;min-width:34px;padding:2px 7px;border-radius:6px;font-size:12px;
  font-weight:600;background:var(--surface-3);}
.te-badge.hi{background:color-mix(in srgb,var(--good) 12%,var(--surface));color:var(--good);}
.te-badge.mid{background:color-mix(in srgb,var(--amber) 12%,var(--surface));color:var(--amber);}

/* ── sparse / empty ────────────────────────────────────────────────── */
.empty-note{display:flex;align-items:center;gap:var(--s3);padding:14px var(--s5);border-radius:var(--r-md);
  background:color-mix(in srgb,var(--accent) 6%,var(--surface));
  border:1px solid color-mix(in srgb,var(--accent) 20%,transparent);color:var(--text-dim);
  font-size:13.5px;margin-bottom:var(--s4);} .empty-note .ico{color:var(--accent);}
.dash{color:var(--text-faint);}

/* ── Streamlit widgets → cockpit ───────────────────────────────────── */
.stButton>button{background:var(--accent);color:var(--accent-ink);border:0;font-family:var(--font-sans);
  font-weight:600;font-size:13.5px;border-radius:var(--r-md);padding:9px 16px;white-space:nowrap;min-height:0;
  box-shadow:0 1px 2px rgba(0,0,0,.3),0 0 18px color-mix(in srgb,var(--accent) 18%,transparent);}
.stButton>button:hover{filter:brightness(1.07);color:var(--accent-ink);border:0;}
.stButton>button:disabled{opacity:.55;}

/* ── header utility controls → small dark pills (Sync + horizon popover) ───── */
/* (popover body — the 7/30/60 toggle — is styled by the rules below) */
.st-key-sync_btn button,
[data-testid="stPopoverButton"],[data-testid="stPopover"]>div>button,[data-testid="stPopover"]>button{
  background:var(--surface)!important;border:1px solid var(--border)!important;color:var(--text-dim)!important;
  font-family:var(--font-mono)!important;font-weight:500!important;font-size:11.5px!important;letter-spacing:.02em!important;
  padding:5px 11px!important;min-height:0!important;height:auto!important;border-radius:var(--r-md)!important;
  white-space:nowrap!important;box-shadow:inset 0 1px 0 var(--inset-hi)!important;}
.st-key-sync_btn button:hover,
[data-testid="stPopoverButton"]:hover,[data-testid="stPopover"]>div>button:hover,[data-testid="stPopover"]>button:hover{
  border-color:var(--border-2)!important;color:var(--text)!important;background:var(--surface-2)!important;filter:none!important;}

/* ── window range toggle → compact non-wrapping pill group (matches design) ── */
[data-testid="stSegmentedControl"]{width:auto;}
[data-testid="stSegmentedControl"] [role="radiogroup"]{
  display:inline-flex!important;flex-wrap:nowrap!important;gap:2px;padding:3px;width:auto!important;
  border-radius:var(--r-lg);background:var(--surface);border:1px solid var(--border);
  box-shadow:inset 0 1px 0 var(--inset-hi);}
[data-testid="stSegmentedControl"] [role="radiogroup"]>*{flex:0 0 auto!important;}
[data-testid="stSegmentedControl"] button{
  border:0!important;background:transparent!important;color:var(--text-faint)!important;
  font-family:var(--font-mono)!important;font-size:11px!important;font-weight:500!important;letter-spacing:.02em!important;
  padding:6px 12px!important;border-radius:8px!important;min-height:0!important;min-width:0!important;white-space:nowrap!important;}
[data-testid="stSegmentedControl"] button:hover{color:var(--text)!important;background:var(--surface-2)!important;}
[data-testid="stSegmentedControl"] button[aria-checked="true"],
[data-testid="stSegmentedControl"] button[data-selected="true"],
[data-testid="stSegmentedControl"] button[kind*="Active"],
[data-testid="stSegmentedControl"] button[data-testid*="Active"]{
  background:var(--accent)!important;color:var(--accent-ink)!important;font-weight:600!important;box-shadow:none!important;}

/* ── multipage sidebar nav → branded marker-bar rail ───────────────────── */
/* st.logo renders in BOTH the app header and the sidebar — keep only the sidebar mark. */
[data-testid="stHeaderLogo"]{display:none!important;}
[data-testid="stSidebarNavLink"]{
  border-radius:var(--r-md)!important;border-left:2px solid transparent!important;
  text-transform:uppercase;color:var(--text-dim)!important;
  font-family:var(--font-mono)!important;font-size:11px!important;font-weight:500!important;letter-spacing:.13em!important;}
/* material icons are ligatures — never uppercase them or the glyph breaks */
[data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"]{text-transform:none!important;color:var(--text-faint)!important;}
[data-testid="stSidebarNavLink"]:hover{background:var(--surface-2)!important;color:var(--text)!important;}
[data-testid="stSidebarNavLink"]:hover [data-testid="stIconMaterial"]{color:var(--text)!important;}
[data-testid="stSidebarNavLink"][aria-current="page"]{
  background:color-mix(in srgb,var(--accent) 10%,transparent)!important;
  border-left-color:var(--accent)!important;color:var(--accent)!important;}
[data-testid="stSidebarNavLink"][aria-current="page"] [data-testid="stIconMaterial"]{color:var(--accent)!important;}

/* ── responsive ────────────────────────────────────────────────────── */
@media (max-width:1080px){ .tiles{grid-template-columns:repeat(3,1fr);} }
@media (max-width:920px){
  .hero.hero-numeric{grid-template-columns:1fr;gap:var(--s4);}
  .bignum{justify-content:flex-start;} .verdict .vsub{max-width:52ch;}
}
@media (max-width:680px){
  .tiles{grid-template-columns:repeat(2,1fr);}
  .hero,.coach,.capacity,.leak,.grapple,.research{padding:var(--s5);}
  .acts{overflow-x:auto;} .acts table{min-width:560px;}
}
@media (max-width:420px){ .tiles{grid-template-columns:1fr;} }
</style>
"""

# brand mark + coach glyph (small inline SVG icons)
_PULSE = ('<svg viewBox="0 0 24 24" fill="none" stroke="#C6F23B" stroke-width="2" '
          'stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h4l2.5-7 4 14 3-9 2 2H22"/></svg>')
_SPARK = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
          'stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v6m0 0 4-3m-4 3L8 6M5 13a7 7 0 1 0 14 0"/></svg>')
_ACT_ICONS = {
    "run": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="15" cy="5" r="1.6"/><path d="M13 8l-3 3 2 3v5M13 8l3 2 3 .5M10 11l-3 1-2 4"/></svg>',
    "ride": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="17" r="3.4"/><circle cx="18" cy="17" r="3.4"/><path d="M6 17l4-7h5l-3 7M10 10l2-3h3"/></svg>',
    "swim": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="16" cy="7" r="1.5"/><path d="M5 10l5 3 4-3 3 2M2 17c2 1.5 3 1.5 5 0s3-1.5 5 0 3 1.5 5 0 3-1.5 5 0"/></svg>',
    "strength": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6M7 7v10M17 7v10M20 9v6M7 12h10"/></svg>',
    "generic": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>',
}


# ════════════════════════════════════════════════════════════════════════════
#  small helpers
# ════════════════════════════════════════════════════════════════════════════
def section_label(text: str) -> str:
    return f'<div class="section-label">{html.escape(text)}</div>'


def zone(readiness):
    """(key, css-color) for the readiness ring/verdict. None → no score."""
    if readiness is None:
        return "none", "var(--text-faint)"
    if readiness >= 70:
        return "good", "var(--accent)"
    if readiness >= 45:
        return "mid", "var(--amber)"
    return "bad", "var(--red)"


def topbar(date_str: str, sparse: bool) -> str:
    pill = "" if sparse else '<span class="pill"><span class="dot"></span>synced</span>'
    return _collapse_html(f"""
    <div class="topbar">
      <div class="brand">
        <span class="mark"></span>
        <span><span class="name">Hankø</span><br>
        <span class="sub">Recovery cockpit</span></span>
      </div>
      <span class="date tnum">{html.escape(date_str)}</span>
      <span class="spacer"></span>
      {pill}
    </div>""")


# ── readiness numeral + progress fill ────────────────────────────────────────
def _num_fill(pct) -> str:
    """Slim champagne→teal progress track whose fill grows to `pct` (0–1) on load."""
    p = max(0.0, min(1.0, pct)) * 100
    uid = _uid()
    return f"""
    <style>
      @keyframes grow_{uid} {{ from {{ width:0; }} to {{ width:{p:.1f}%; }} }}
      #fill_{uid} {{ width:{p:.1f}%; animation:grow_{uid} 1.2s cubic-bezier(.34,1.1,.4,1) forwards; }}
      @media (prefers-reduced-motion: reduce){{ #fill_{uid}{{animation:none;}} }}
    </style>
    <div class="num-track"><span class="num-fill" id="fill_{uid}"></span></div>"""


def hero(readiness, verdict, tagline, chips_html, ribbon_html="", sparse=False) -> str:
    if sparse:
        note = ('<div class="empty-note"><span class="ico">⚡</span> Not enough data yet — '
                'sync more history to unlock today\'s readiness call.</div>')
        return f"""{note}
        <div class="card hero hero-numeric" style="--ring-color:var(--text-dim)">
          <div class="num-block">
            <div class="kicker">Readiness</div>
            <div class="bignum no-score"><span class="score">—</span><span class="den">awaiting data</span></div>
            {_num_fill(0)}
          </div>
          <div class="verdict"><div class="vbig">{html.escape(verdict)}</div>
            <div class="vsub">{html.escape(tagline)}</div>
            <div class="chips">{chips_html}</div></div>
        </div>"""
    z_key, color = zone(readiness)
    score = "—" if readiness is None else str(int(round(readiness)))
    den = "/ 100" if readiness is not None else "no score"
    return f"""{ribbon_html}
    <div class="card hero hero-numeric" style="--ring-color:{color}">
      <div class="num-block">
        <div class="kicker">Readiness</div>
        <div class="bignum"><span class="score tnum">{score}</span><span class="den">{den}</span></div>
        {_num_fill((readiness or 0)/100)}
      </div>
      <div class="verdict"><div class="vbig">{html.escape(verdict)}</div>
        <div class="vsub">{html.escape(tagline)}</div>
        <div class="chips">{chips_html}</div></div>
    </div>"""


def _chip(k, arrow, word, cls):
    return (f'<span class="chip {cls}"><span class="k">{k}</span>'
            f'<span class="ar">{arrow}</span><span class="v">{word}</span></span>')


def chips(hrv_flag, rhr, rhr28, sleep_h) -> str:
    """Three status chips from real flags/values. None-safe."""
    # HRV
    if hrv_flag == "suppressed":
        c1 = _chip("HRV", "▼", "suppressed", "bad")
    elif hrv_flag == "elevated":
        c1 = _chip("HRV", "▲", "elevated", "good")
    elif hrv_flag == "balanced":
        c1 = _chip("HRV", "▲", "balanced", "good")
    else:
        c1 = _chip("HRV", "·", "—", "neutral")
    # RHR vs 28d baseline (+5% = elevated)
    if rhr is None or rhr28 is None:
        c2 = _chip("RHR", "·", "—", "neutral")
    elif rhr > rhr28 * 1.05:
        c2 = _chip("RHR", "▲", "elevated", "bad")
    else:
        c2 = _chip("RHR", "▼", "low", "good")
    # Sleep
    if sleep_h is None:
        c3 = _chip("Sleep", "·", "—", "neutral")
    elif sleep_h >= 7.5:
        c3 = _chip("Sleep", "●", "on target", "good")
    elif sleep_h >= 6.5:
        c3 = _chip("Sleep", "●", "short", "warn")
    else:
        c3 = _chip("Sleep", "▼", "deficit", "bad")
    return c1 + c2 + c3


def ribbon(message: str, amber: bool = False) -> str:
    cls = "ribbon amber" if amber else "ribbon"
    return f'<div class="{cls}"><span class="ico">⚠</span><span>{html.escape(message)}</span></div>'


# ── sparkline + tiles ────────────────────────────────────────────────────────
def _sparkline(values, color) -> str:
    vals = [v for v in values if v is not None and pd.notna(v)]
    if len(vals) < 2:
        return '<div class="spark-empty"></div>'
    w, h, pad = 120, 36, 4
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    pts = []
    n = len(vals)
    for i, v in enumerate(vals):
        x = (i / (n - 1)) * w
        y = pad + (1 - (v - lo) / span) * (h - pad * 2)
        pts.append((round(x, 2), round(y, 2)))
    line = " ".join(("M" if i == 0 else "L") + f"{x} {y}" for i, (x, y) in enumerate(pts))
    area = line + f" L{pts[-1][0]} {h} L{pts[0][0]} {h} Z"
    uid = _uid()
    lx, ly = pts[-1]
    return f"""<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none">
      <defs><linearGradient id="sf_{uid}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="{color}" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>
      <path d="{area}" fill="url(#sf_{uid})"/>
      <path d="{line}" fill="none" stroke="{color}" stroke-width="1.75" stroke-linejoin="round"
        stroke-linecap="round" vector-effect="non-scaling-stroke"/>
      <circle cx="{lx}" cy="{ly}" r="2.4" fill="{color}"/></svg>"""


def _tile(label, value, unit, spark, delta) -> str:
    unit_html = f"<u>{unit}</u>" if unit else ""
    return f"""<div class="card tile"><div class="tl">{label}</div>
      <div class="tv tnum">{value}{unit_html}</div>{spark}{delta}</div>"""


def _simple_tile(label, value, unit="") -> str:
    unit_html = f"<u>{unit}</u>" if unit else ""
    return f"""<div class="card tile"><div class="tl">{label}</div>
      <div class="tv tnum">{value}{unit_html}</div></div>"""


def _delta(today, base, direction, fmt, unit=""):
    """direction: +1 = up is good, -1 = down is good."""
    if today is None or base is None:
        return '<span class="delta flat"><span class="lbl">—</span></span>'
    d = today - base
    arrow = "▲" if d > 0.05 else "▼" if d < -0.05 else "▬"
    if direction == 1:
        tone = "good" if d > 0 else "bad" if d < 0 else "flat"
    else:
        tone = "good" if d < 0 else "bad" if d > 0 else "flat"
    return (f'<span class="delta {tone}">{arrow} {fmt(abs(d))}{unit} '
            f'<span class="lbl">vs 28d</span></span>')


def tiles(today: dict, sparks: dict, base: dict, sparse: bool) -> str:
    if sparse:
        cfg = [("HRV", "ms"), ("Resting HR", "bpm"), ("Sleep", "h"), ("ACWR", ""), ("Body Battery", ""), ("Stress", "")]
        cells = [_tile(l, '<span class="dash">—</span>', u, '<div class="spark-empty"></div>',
                       '<span class="delta flat"><span class="lbl">—</span></span>') for l, u in cfg]
        return f'<div class="tiles">{"".join(cells)}</div>'

    def g(k):
        v = today.get(k)
        return None if v is None or pd.isna(v) else float(v)

    hrv, rhr, slp, acwr, batt, stress = (
        g("hrv"), g("rhr"), g("sleep_h"), g("acwr"), g("batt"), g("stress")
    )
    r0 = lambda v: f"{v:.0f}"
    r1 = lambda v: f"{v:.1f}"
    r2 = lambda v: f"{v:.2f}"
    # ACWR delta is a sweet-spot status, not a 28d comparison
    if acwr is None:
        acwr_delta = '<span class="delta flat"><span class="lbl">—</span></span>'
    elif acwr > 1.3:
        acwr_delta = '<span class="delta bad">▲ above 1.3</span>'
    elif acwr < 0.8:
        acwr_delta = '<span class="delta bad">▼ under 0.8</span>'
    else:
        acwr_delta = '<span class="delta good">● in sweet spot</span>'
    acwr_color = ACCENT if (acwr is not None and 0.8 <= acwr <= 1.3) else AMBER

    cells = [
        _tile("HRV", "—" if hrv is None else f"{hrv:.0f}", "ms",
              _sparkline(sparks.get("hrv", []), ACCENT),
              _delta(hrv, base.get("hrv"), 1, r0)),
        _tile("Resting HR", "—" if rhr is None else f"{rhr:.0f}", "bpm",
              _sparkline(sparks.get("rhr", []), SERIES2),
              _delta(rhr, base.get("rhr"), -1, r0)),
        _tile("Sleep", "—" if slp is None else f"{slp:.1f}", "h",
              _sparkline(sparks.get("sleep_h", []), SERIES2),
              _delta(slp, base.get("sleep_h"), 1, r1, "h")),
        _tile("ACWR", "—" if acwr is None else f"{acwr:.2f}", "",
              _sparkline(sparks.get("acwr", []), acwr_color), acwr_delta),
        _simple_tile("Body Battery", "—" if batt is None else f"{batt:.0f}"),
        _simple_tile("Stress", "—" if stress is None else f"{stress:.0f}"),
    ]
    return f'<div class="tiles">{"".join(cells)}</div>'


# ── horizontal day rail ──────────────────────────────────────────────────────
def day_rail(days: pd.DataFrame, activities: pd.DataFrame, selected_day: str | None = None) -> str:
    if days is None or days.empty:
        return ('<div class="card"><div class="empty-note" style="margin:0;justify-content:center">'
                '<span class="ico">⚡</span> Sync daily metrics to build the day rail.</div></div>')

    d = days.copy()
    d["date_key"] = pd.to_datetime(d["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    d = d.dropna(subset=["date_key"]).tail(30)
    activity_map = _day_activity_map(activities)
    cards = []
    for _, row in d.sort_values("date_key", ascending=False).iterrows():
        day_key = row["date_key"]
        cards.append(_day_card(row, activity_map.get(day_key, []), selected_day == day_key))
    return f'<div class="day-rail">{"".join(cards)}</div>'


def _day_card(row: pd.Series, acts: list[dict], selected: bool) -> str:
    day_key = row.get("date_key")
    dt = pd.to_datetime(day_key, errors="coerce")
    date_label = day_key if pd.isna(dt) else f"{dt.strftime('%a')} {dt.day} {dt.strftime('%b')}"
    tone, tone_label = _day_tone(row)
    selected_cls = " selected" if selected else ""
    stats = [
        ("Sleep", _fmt_day_value(row.get("sleep_hours"), "h", 1)),
        ("HRV", _day_hrv(row)),
        ("RHR", _day_rhr(row)),
        ("Stress", _fmt_day_value(row.get("stress_avg"), "", 0)),
        ("BB", _day_body_battery(row)),
        ("Steps", _fmt_day_value(row.get("steps"), "", 0)),
    ]
    stat_html = "".join(
        f'<div class="day-stat"><span class="dl">{html.escape(label)}</span><b>{value}</b></div>'
        for label, value in stats
    )
    act_html = "".join(
        f'<span class="day-act {html.escape(a.get("class", ""))}">{html.escape(a.get("label", ""))}</span>'
        for a in acts[:3]
    )
    if len(acts) > 3:
        act_html += f'<span class="day-act">+{len(acts) - 3}</span>'
    if not act_html:
        act_html = '<span class="day-empty">No activity</span>'
    href = f"?day={html.escape(str(day_key))}"
    return f"""
      <a class="day-card {tone}{selected_cls}" href="{href}">
        <div class="day-top">
          <div class="day-date">{html.escape(date_label)}</div>
          <span class="day-flag"><i class="day-tone"></i>{html.escape(tone_label)}</span>
        </div>
        <div class="day-stats">{stat_html}</div>
        <div class="day-acts">{act_html}</div>
      </a>"""


def _day_tone(row: pd.Series) -> tuple[str, str]:
    flags = 0
    if row.get("hrv_flag") == "suppressed":
        flags += 1
    if bool(row.get("rhr_elevated")) if pd.notna(row.get("rhr_elevated")) else False:
        flags += 1
    if _num(row.get("sleep_hours")) is not None and _num(row.get("sleep_hours")) < 6.5:
        flags += 1
    if _num(row.get("body_battery_current")) is not None and _num(row.get("body_battery_current")) < 35:
        flags += 1
    if flags >= 2:
        return "bad", "Strained"
    if flags == 1:
        return "warn", "Caution"
    return "good", "Primed"


def _fmt_day_value(value, suffix="", digits=0) -> str:
    n = _num(value)
    if n is None:
        return '<span class="dash">—</span>'
    if abs(n) >= 1000:
        text = f"{n:,.0f}"
    elif digits == 0:
        text = f"{n:.0f}"
    else:
        text = f"{n:.{digits}f}"
    return f"{html.escape(text)}{html.escape(suffix)}"


def _day_hrv(row: pd.Series) -> str:
    flag = row.get("hrv_flag")
    if flag == "suppressed":
        return "low"
    if flag == "elevated":
        return "high"
    return _fmt_day_value(row.get("hrv_overnight_avg"), "", 0)


def _day_rhr(row: pd.Series) -> str:
    elevated = bool(row.get("rhr_elevated")) if pd.notna(row.get("rhr_elevated")) else False
    if elevated:
        return "up"
    return _fmt_day_value(row.get("resting_hr"), "", 0)


def _day_body_battery(row: pd.Series) -> str:
    start = _num(row.get("body_battery_start"))
    end = _num(row.get("body_battery_end"))
    current = _num(row.get("body_battery_current"))
    high = _num(row.get("body_battery_high"))
    if start is not None and end is not None:
        return f"{start:.0f}&rarr;{end:.0f}"
    if high is not None and current is not None and high != current:
        return f"{high:.0f}&rarr;{current:.0f}"
    return _fmt_day_value(current if current is not None else high, "", 0)


def _day_activity_map(activities: pd.DataFrame) -> dict[str, list[dict]]:
    if activities is None or activities.empty or "date" not in activities:
        return {}
    a = activities.copy()
    a["date_key"] = pd.to_datetime(a["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out: dict[str, list[dict]] = {}
    for _, row in a.dropna(subset=["date_key"]).iterrows():
        out.setdefault(row["date_key"], []).append(_activity_badge(row))
    return out


def _activity_badge(row: pd.Series) -> dict:
    text = f"{row.get('name') or ''} {row.get('type') or ''}".lower()
    if any(p in text for p in ("bjj", "jiu-jitsu", "jiu jitsu", "grappling", "wrestling", "martial", "combat", "submission")):
        return {"label": "BJJ", "class": "bjj"}
    if "run" in text:
        return {"label": "Run", "class": ""}
    if "walk" in text or "hike" in text:
        return {"label": "Walk", "class": ""}
    if "cycl" in text or "ride" in text or "bike" in text:
        return {"label": "Ride", "class": ""}
    if "strength" in text or "weight" in text or "gym" in text:
        return {"label": "Strength", "class": ""}
    if row.get("type"):
        return {"label": str(row.get("type")).replace("_", " ").title()[:14], "class": ""}
    return {"label": "Activity", "class": ""}


def _num(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── AI coach card ────────────────────────────────────────────────────────────
def _json_html(obj) -> str:
    s = json.dumps(obj, indent=2)
    s = s.replace("&", "&amp;").replace("<", "&lt;")
    s = re.sub(r'"([^"]+)":', r'<span class="k">"\1"</span>:', s)
    s = re.sub(r": (-?\d+\.?\d*)", r': <span class="n">\1</span>', s)
    s = re.sub(r': (".*?")', r': <span class="s">\1</span>', s)
    return s


def _md_sections(md: str) -> str:
    """Turn ai.analyze() markdown (## headers + bullets/numbers) into coach HTML."""
    blocks = re.split(r"(?m)^##\s+", md.strip())
    out = []
    for blk in blocks:
        blk = blk.strip()
        if not blk:
            continue
        head, *rest = blk.split("\n")
        head = head.strip()
        body_lines = [l.rstrip() for l in rest if l.strip()]
        low = head.lower()
        bullets = [re.sub(r"^[-*]\s+", "", l) for l in body_lines if re.match(r"^[-*]\s+", l)]
        numbered = [re.sub(r"^\d+\.\s+", "", l) for l in body_lines if re.match(r"^\d+\.\s+", l)]
        paras = [l for l in body_lines if not re.match(r"^([-*]|\d+\.)\s+", l)]
        esc = lambda t: html.escape(t)
        if numbered or "what to do" in low or low.startswith("do"):
            items = numbered or bullets
            lis = "".join(f"<li>{esc(x)}</li>" for x in items)
            out.append(f'<div class="coach-sec todo"><h4>{esc(head)}</h4><ol>{lis}</ol></div>')
        elif bullets or "trend" in low or "anomal" in low:
            lis = "".join(f"<li>{esc(x)}</li>" for x in (bullets or paras))
            out.append(f'<div class="coach-sec trends"><h4>{esc(head)}</h4><ul>{lis}</ul></div>')
        else:
            ptext = " ".join(esc(p) for p in paras) or esc(" ".join(body_lines))
            out.append(f'<div class="coach-sec"><h4>{esc(head)}</h4><p>{ptext}</p></div>')
    return "".join(out)


def coach_card(date_str, result, summary, sparse=False) -> str:
    head = (f'<div class="coach-head"><span class="glyph">{_SPARK}</span>'
            f'<div><h3>AI coach readout</h3><div class="meta">{html.escape(date_str)}</div></div></div>')
    if sparse:
        body = ('<div class="empty-note" style="margin:0"><span class="ico">⚡</span> '
                'Not enough data to interpret yet — the coach needs ~7 days of overnight '
                'metrics before it can read your trends.</div>')
        return f'<div class="card coach">{head}{body}</div>'

    if result:
        body = f'<div class="coach-body">{_md_sections(result)}</div>'
    else:
        body = ('<div class="prompt">Press <b>⚡ Analyse</b> above to send a compact summary of your '
                'recent metrics to Claude and get a readiness call, trend flags, and concrete next steps.</div>')
    disc = ""
    if summary is not None:
        disc = (f'<details class="disclosure"><summary><span class="caret">▶</span> '
                f'Data sent to AI · compact summary only</summary>'
                f'<pre>{_json_html(summary)}</pre></details>')
    return f'<div class="card coach">{head}{body}{disc}</div>'


def weekly_summary_card(summary_md, meta) -> str:
    head = (f'<div class="coach-head"><span class="glyph">{_SPARK}</span>'
            f'<div><h3>Weekly summary</h3>'
            f'<div class="meta">{html.escape(str(meta))}</div></div></div>')
    if not summary_md:
        body = ('<div class="empty-note" style="margin:0"><span class="ico">⚡</span> '
                'No completed week to summarize yet — sync a full Mon–Sun of data.</div>')
        return _collapse_html(f'<div class="card coach">{head}{body}</div>')
    body = f'<div class="coach-body">{_md_sections(summary_md)}</div>'
    return _collapse_html(f'<div class="card coach">{head}{body}</div>')


def coach_memory_peek(digest: dict) -> str:
    """Compact 'Coach knows' card for the main dashboard."""
    head = (f'<div class="coach-head"><span class="glyph">{_SPARK}</span>'
            f'<div><h3>Coach knows</h3>'
            f'<div class="meta">your long-term context</div></div></div>')
    if not digest:
        body = ('<div class="empty-note" style="margin:0"><span class="ico">🧠</span> '
                'Nothing remembered yet — add goals, injuries, or notes on the '
                'Coach page.</div>')
        return _collapse_html(f'<div class="card coach">{head}{body}</div>')

    chip_style = ("display:inline-block;padding:2px 8px;margin:0 6px 6px 0;"
                  "border-radius:10px;background:rgba(255,255,255,.06);"
                  "font-size:12px;opacity:.85")
    chips = "".join(
        f'<span style="{chip_style}">{html.escape(label)}: {len(digest.get(key, []))}</span>'
        for label, key in (("Goals", "goals"), ("Injuries", "injuries"),
                            ("Patterns", "patterns"), ("Coaching", "coaching"),
                            ("Notes", "notes"))
        if digest.get(key))

    lines = []
    def _memory_when(item) -> str:
        if not isinstance(item, dict):
            return ""
        date = item.get("metadata_date")
        time = item.get("metadata_time")
        if date and time:
            return f' · {html.escape(str(date))} {html.escape(str(time))}'
        if date:
            return f' · {html.escape(str(date))}'
        if item.get("created_at"):
            stamp = html.escape(str(item["created_at"]).replace("T", " ")[:16])
            return f" · added {stamp}"
        return ""

    for g in digest.get("goals", [])[:2]:
        when = (f' · {html.escape(str(g["target_date"]))}'
                if g.get("target_date") else "")
        lines.append(f'<div style="margin:2px 0">🎯 {html.escape(str(g["text"]))}{when}</div>')
    for inj in digest.get("injuries", [])[:2]:
        where = (f' ({html.escape(str(inj["body_part"]))})'
                 if inj.get("body_part") else "")
        lines.append(
            f'<div style="margin:2px 0">🩹 {html.escape(str(inj["text"]))}'
            f'{where}{_memory_when(inj)}</div>'
        )
    for note in digest.get("notes", [])[:2]:
        if isinstance(note, dict):
            text = note.get("text")
        else:
            text = note
        lines.append(
            f'<div style="margin:2px 0">📌 {html.escape(str(text))}'
            f'{_memory_when(note)}</div>'
        )

    body = (f'<div style="margin-bottom:6px">{chips}</div>'
            + "".join(lines))
    return _collapse_html(f'<div class="card coach">{head}{body}</div>')


def question_card(question: str | None, result: str | None, payload: dict | None = None) -> str:
    head = (f'<div class="coach-head"><span class="glyph">{_SPARK}</span>'
            f'<div><h3>Ask about your health</h3><div class="meta">metrics-grounded answer</div></div></div>')
    if result:
        q = html.escape(question or "")
        body = (
            f'<div class="prompt" style="margin-bottom:16px"><b>Question:</b> {q}</div>'
            f'<div class="coach-body">{_md_sections(result)}</div>'
        )
    else:
        body = ('<div class="prompt">Ask a specific question about recovery, sleep, fatigue, '
                'training load, Body Battery, or what your recent metrics suggest. The answer '
                'uses the compact summary and capacity envelope, not raw time-series.</div>')
    disc = ""
    if payload is not None:
        disc = (f'<details class="disclosure"><summary><span class="caret">▶</span> '
                f'Data sent to AI · compact question context</summary>'
                f'<pre>{_json_html(payload)}</pre></details>')
    return f'<div class="card coach">{head}{body}{disc}</div>'


# ── capacity envelope ────────────────────────────────────────────────────────
def _cap_fmt(value, unit="") -> str:
    if value is None or pd.isna(value):
        return '<span class="dash">—</span>'
    n = float(value)
    if abs(n) >= 1000:
        s = f"{n:,.0f}"
    elif n.is_integer():
        s = f"{n:.0f}"
    else:
        s = f"{n:.1f}"
    return f'{s}<u>{html.escape(unit)}</u>' if unit else s


def _cap_range(metric: dict) -> str:
    lo, hi, unit = metric.get("low"), metric.get("high"), metric.get("unit", "")
    if lo is None or hi is None:
        return "learning range"
    unit_s = f" {unit}" if unit else ""
    return f"{_cap_text_num(lo)}–{_cap_text_num(hi)}{html.escape(unit_s)} stable range"


def _cap_text_num(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    n = float(value)
    return f"{n:,.0f}" if abs(n) >= 1000 or n.is_integer() else f"{n:.1f}"


def capacity_card(model: dict) -> str:
    zone = html.escape(model.get("zone", "learning"))
    status = model.get("status", "learning")
    zone_label = "learning" if zone == "learning" else f"{zone} zone"
    learned = int(model.get("learned_days") or 0)
    min_days = int(model.get("min_days") or 14)
    stable = model.get("stable_days")
    if status == "ready":
        meta = f"{learned} days logged · {stable} stable response days"
    else:
        meta = f"{learned}/{min_days} days logged"
    head = f"""
      <div class="capacity-head">
        <div><h3>Capacity envelope</h3><div class="meta">{html.escape(meta)}</div></div>
        <span class="cap-zone {zone}">{html.escape(zone_label)}</span>
      </div>"""

    metrics_html = []
    for m in model.get("metrics", []):
        ex = m.get("excess_ratio")
        tone = "flat"
        if ex is not None:
            tone = "bad" if ex >= 0.25 else "warn" if ex >= 0.05 else "good"
        metrics_html.append(
            f"""<div class="cap-metric {tone}">
              <div class="lab">{html.escape(m.get("label", ""))}</div>
              <div class="now tnum">{_cap_fmt(m.get("current"), m.get("unit", ""))}</div>
              <div class="range">{html.escape(_cap_range(m))}</div>
            </div>"""
        )
    grid = f'<div class="cap-grid">{"".join(metrics_html)}</div>' if metrics_html else ""

    flags = model.get("flags") or []
    missing = model.get("missing") or []
    flag_html = ""
    if flags or missing:
        items = [f'<span class="cap-flag warn">{html.escape(f)}</span>' for f in flags]
        items += [f'<span class="cap-flag">{html.escape(m)}</span>' for m in missing[:3]]
        flag_html = f'<div class="cap-flags">{"".join(items)}</div>'

    msg = html.escape(model.get("message", "Add more data to learn your capacity envelope."))
    return f'<div class="card capacity">{head}<div class="cap-message">{msg}</div>{grid}{flag_html}</div>'


# ── stress leak map ──────────────────────────────────────────────────────────
def _leak_stat(label, value, sub="") -> str:
    return (f'<div class="leak-stat"><div class="lab">{html.escape(label)}</div>'
            f'<div class="val">{value}</div><div class="sub">{html.escape(sub)}</div></div>')


def stress_leak_card(model: dict) -> str:
    model = model or {}
    status = model.get("status", "no_data")
    if status == "no_data":
        message = html.escape(model.get(
            "message",
            "No intraday stress samples stored yet. Sync Garmin all-day stress to build a leak map.",
        ))
        return (f'<div class="card leak"><div class="empty-note" style="margin:0">'
                f'<span class="ico">⚡</span> {message}</div></div>')

    days = int(model.get("days_analyzed") or 0)
    sample = model.get("sample_minutes")
    sample_text = f" · {sample:g} min samples" if isinstance(sample, (int, float)) else ""
    pill_class = "ready" if status == "ready" else "learning"
    head = f"""
      <div class="leak-head">
        <div><h3>Stress leak map</h3>
        <div class="meta">{days} days analyzed{html.escape(sample_text)}</div></div>
        <span class="leak-pill {pill_class}">{html.escape(status)}</span>
      </div>"""

    message = html.escape(model.get("message", "No clear stress leak window yet."))
    top = model.get("top_leak")
    stats_html = ""
    reason_html = ""
    if top:
        freq = f"{int(top.get('days_high') or 0)}/{int(top.get('days_seen') or 0)} days"
        stats = [
            _leak_stat("Window", html.escape(str(top.get("time_range") or "—")), top.get("label") or ""),
            _leak_stat("Avg stress", _cap_text_num(top.get("avg_stress")), "0-100 Garmin stress"),
            _leak_stat("Frequency", html.escape(freq), "recurring leak days"),
            _leak_stat("High min/day", _cap_text_num(top.get("avg_high_min")), "stress >= 50"),
            _leak_stat("Impact", _cap_text_num(top.get("impact_score")), "rank score"),
        ]
        stats_html = f'<div class="leak-grid">{"".join(stats)}</div>'
        if top.get("reason"):
            reason_html = f'<div class="leak-reason">{html.escape(top.get("reason"))}</div>'

    missing = model.get("missing") or []
    flags_html = ""
    if missing:
        flags = [f'<span class="leak-flag">{html.escape(str(m))}</span>' for m in missing[:4]]
        flags_html = f'<div class="leak-flags">{"".join(flags)}</div>'

    rows = []
    for leak in model.get("leaks", [])[:5]:
        freq = f"{int(leak.get('days_high') or 0)}/{int(leak.get('days_seen') or 0)}"
        rows.append(
            f"<tr><td>{html.escape(str(leak.get('time_range') or ''))}</td>"
            f"<td>{html.escape(str(leak.get('label') or '—'))}</td>"
            f"<td>{_cap_text_num(leak.get('avg_stress'))}</td>"
            f"<td>{html.escape(freq)}</td>"
            f"<td>{_cap_text_num(leak.get('avg_high_min'))}</td>"
            f"<td>{_cap_text_num(leak.get('impact_score'))}</td></tr>"
        )
    table = ""
    if rows:
        table = f"""<table class="leak-table"><thead><tr>
          <th>Time</th><th>Pattern</th><th>Avg</th><th>Freq</th><th>High min</th><th>Impact</th>
          </tr></thead><tbody>{"".join(rows)}</tbody></table>"""

    return (
        f'<div class="card leak">{head}<div class="leak-message">{message}</div>'
        f'{stats_html}{reason_html}{flags_html}{table}</div>'
    )


# ── discovery panel ──────────────────────────────────────────────────────────
def _discovery_stat(label, value, sub="") -> str:
    return (f'<div class="discovery-stat"><div class="lab">{html.escape(label)}</div>'
            f'<div class="val">{value}</div><div class="sub">{html.escape(sub)}</div></div>')


def discovery_card(model: dict) -> str:
    model = model or {}
    status = model.get("status", "no_data")
    if status == "no_data":
        message = html.escape(model.get("message", "No discovery data available yet."))
        missing = model.get("missing") or []
        extra = f" {' · '.join(str(m) for m in missing[:2])}" if missing else ""
        return (f'<div class="card discovery"><div class="empty-note" style="margin:0">'
                f'<span class="ico">⚡</span> {message}{html.escape(extra)}</div></div>')

    days = int(model.get("days_analyzed") or 0)
    pill_class = "ready" if status == "ready" else "learning"
    min_pairs = int(model.get("min_pairs") or 0)
    head = f"""
      <div class="discovery-head">
        <div><h3>Correlation discovery</h3>
        <div class="meta">{days} days scanned · minimum {min_pairs} paired days</div></div>
        <span class="discovery-pill {pill_class}">{html.escape(status)}</span>
      </div>"""

    relationships = model.get("relationships") or []
    sleep_rel = next((r for r in relationships if r.get("y_col") in ("sleep_score", "sleep_hours")), {})
    load_rel = next((r for r in relationships if r.get("x_col") == "cardio_load"), {})
    top_rel = relationships[0] if relationships else {}
    top_label = top_rel.get("x_label") or "Metric"
    top_unit = top_rel.get("x_unit") or ""
    stats = [
        _discovery_stat(top_label, _cap_text_num(top_rel.get("median_x")), f"median {top_unit} split".strip()),
        _discovery_stat("Sleep pairs", _cap_text_num(sleep_rel.get("pairs")), sleep_rel.get("confidence") or "not enough data"),
        _discovery_stat("Load pairs", _cap_text_num(load_rel.get("pairs")), load_rel.get("confidence") or "not enough data"),
        _discovery_stat("Top r", _corr_text(top_rel.get("correlation")), "Pearson association"),
    ]
    grid = f'<div class="discovery-grid">{"".join(stats)}</div>'

    items = []
    for rel in relationships:
        corr = _corr_text(rel.get("correlation"))
        delta = _signed_text(rel.get("high_vs_low_delta"), rel.get("y_unit") or "pts")
        items.append(
            f'<div class="discovery-item"><b>{html.escape(rel.get("label", "Pattern"))}</b><br>'
            f'{html.escape(rel.get("summary", ""))} '
            f'<span class="tnum">High-vs-low split: {html.escape(delta)} · {html.escape(corr)}</span></div>'
        )
    list_html = f'<div class="discovery-list">{"".join(items)}</div>' if items else ""

    missing = model.get("missing") or []
    flags_html = ""
    if missing:
        flags = [f'<span class="leak-flag">{html.escape(str(m))}</span>' for m in missing[:4]]
        flags_html = f'<div class="leak-flags">{"".join(flags)}</div>'

    message = html.escape(model.get("message", "Learning pre-sleep heart-rate patterns."))
    return f'<div class="card discovery">{head}<div class="discovery-message">{message}</div>{grid}{list_html}{flags_html}</div>'


def _corr_text(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):+.2f}"


def _signed_text(value, unit="pts") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):+.1f} {unit}".strip()


# ── research health panels ──────────────────────────────────────────────────
def _collapse_html(markup: str) -> str:
    """Flatten multi-line HTML into a single line for ``st.markdown``.

    Streamlit runs ``unsafe_allow_html`` content through a Markdown processor.
    A whitespace-only line (e.g. an empty ``{flag_html}`` placeholder) is read
    as a blank line that closes the raw-HTML block, after which the remaining
    >=4-space-indented HTML renders as a literal code block. Stripping each line
    and dropping the empties removes both triggers. Every text node lives on its
    own line here, so joining without a separator can't merge words."""
    return "".join(line.strip() for line in markup.splitlines())


def _research_stat_value(stat: dict) -> str:
    value = stat.get("value")
    if value is None or pd.isna(value):
        return '<span class="dash">—</span>'
    digits = int(stat.get("digits") or 0)
    signed = bool(stat.get("signed"))
    n = float(value)
    if digits == 0:
        text = f"{n:+.0f}" if signed else f"{n:.0f}"
    else:
        text = f"{n:+.{digits}f}" if signed else f"{n:.{digits}f}"
    unit = stat.get("unit") or ""
    return f'{html.escape(text)}<u>{html.escape(unit)}</u>' if unit else html.escape(text)


def _research_panel_html(panel: dict) -> str:
    panel = panel or {}
    title = panel.get("title") or "Panel"
    zone_name = panel.get("zone") or panel.get("status") or "learning"
    stats = []
    for stat in (panel.get("stats") or [])[:6]:
        stats.append(
            f"""<div class="research-stat">
              <div class="lab">{html.escape(str(stat.get("label") or ""))}</div>
              <div class="val tnum">{_research_stat_value(stat)}</div>
              <div class="sub">{html.escape(str(stat.get("sub") or ""))}</div>
            </div>"""
        )
    flags = panel.get("flags") or []
    flag_html = ""
    if flags:
        flag_html = '<div class="research-flags">' + "".join(
            f'<span class="leak-flag">{html.escape(str(flag))}</span>' for flag in flags[:4]
        ) + "</div>"
    return f"""
      <div class="research-panel">
        <div class="research-panel-head">
          <h4>{html.escape(str(title))}</h4>
          <span class="research-pill {html.escape(str(zone_name))}">{html.escape(str(zone_name))}</span>
        </div>
        <p>{html.escape(str(panel.get("message") or ""))}</p>
        <div class="research-stats">{"".join(stats)}</div>
        {flag_html}
      </div>"""


def health_research_card(model: dict) -> str:
    model = model or {}
    status = model.get("status", "no_data")
    if status == "no_data":
        message = html.escape(model.get(
            "message",
            "Sync daily Garmin metrics to build research-grade health panels.",
        ))
        return (f'<div class="card research"><div class="empty-note" style="margin:0">'
                f'<span class="ico">⚡</span> {message}</div></div>')

    days = int(model.get("days_analyzed") or 0)
    min_days = int(model.get("min_days") or 14)
    meta = f"{days} days analyzed · {min_days} day baseline target"
    head = f"""
      <div class="research-head">
        <div><h3>Health Lab</h3><div class="meta">{html.escape(meta)}</div></div>
        <span class="research-pill {html.escape(str(status))}">{html.escape(str(status))}</span>
      </div>"""
    panels = [
        model.get("recovery"),
        model.get("sleep_regularity"),
        model.get("respiratory"),
        model.get("fitness"),
    ]
    panel_html = f'<div class="research-panels">{"".join(_research_panel_html(p) for p in panels)}</div>'
    quality = model.get("data_quality") or {}
    quality_items = []
    for item in (quality.get("coverage") or [])[:7]:
        quality_items.append(
            f'<span class="leak-flag">{html.escape(str(item.get("label") or ""))}: '
            f'{int(item.get("days") or 0)}d / {int(item.get("pct") or 0)}%</span>'
        )
    for missing in (quality.get("missing") or [])[:3]:
        quality_items.append(f'<span class="leak-flag">{html.escape(str(missing))}</span>')
    quality_html = f'<div class="research-quality">{"".join(quality_items)}</div>' if quality_items else ""
    message = html.escape(str(model.get("message") or ""))
    return _collapse_html(
        f'<div class="card research">{head}<div class="research-message">{message}</div>{panel_html}{quality_html}</div>'
    )


# ── grappling mode ───────────────────────────────────────────────────────────
def _gval(value, suffix="", blank="—") -> str:
    if value is None or pd.isna(value):
        return blank
    if isinstance(value, float) and not value.is_integer():
        text = f"{value:.1f}"
    else:
        text = f"{float(value):.0f}" if isinstance(value, (int, float)) else str(value)
    return f"{html.escape(text)}{html.escape(suffix)}"


def _gstat(label, value, sub="") -> str:
    return (f'<div class="grapple-stat"><div class="lab">{html.escape(label)}</div>'
            f'<div class="val">{value}</div><div class="sub">{html.escape(sub)}</div></div>')


def grappling_card(sessions: list[dict]) -> str:
    if not sessions:
        return ('<div class="card grapple"><div class="empty-note" style="margin:0">'
                '<span class="ico">⚡</span> No grappling sessions found yet. Name Garmin '
                'activities with BJJ, grappling, jiu-jitsu, wrestling, martial, combat, or '
                'submission so the analyzer can pick them up.</div></div>')

    latest = sessions[0]
    cls = latest.get("classification") or "unknown"
    confidence = latest.get("classification_confidence") or "low"
    threshold_source = "Garmin zones" if latest.get("threshold_source") == "garmin_zones" else "estimated HR threshold"
    round_count = latest.get("round_count")
    round_text = "—" if round_count is None else str(round_count)
    warning = latest.get("warning")
    warn_html = f'<div class="grapple-warning">{html.escape(warning)}</div>' if warning else ""
    next_day = latest.get("next_day") or {}
    note = next_day.get("message") or "No next-day recovery data yet."
    if latest.get("round_detection") == "unavailable":
        note += " Round detection needs activity HR detail from Garmin."

    head = f"""
      <div class="grapple-head">
        <div><h3>{html.escape(latest.get("name") or "Grappling session")}</h3>
        <div class="meta">{html.escape(latest.get("date") or "")} · {html.escape(confidence)} confidence</div></div>
        <span class="grapple-pill">{html.escape(cls)}</span>
      </div>"""
    stats = [
        _gstat("Mat stress", _gval(latest.get("mat_stress_cost")), "0-100 cost"),
        _gstat("Peak HR", _gval(latest.get("peak_hr"), " bpm"), "session max"),
        _gstat("High zone", _gval(latest.get("high_zone_min"), " min"), threshold_source),
        _gstat("Rounds", html.escape(round_text), latest.get("recovery_quality") or ""),
        _gstat("Poor recovery", _gval(latest.get("poor_recovery_rounds")), "round gaps"),
        _gstat("HR drop", _gval(latest.get("avg_recovery_drop"), " bpm"), "avg between rounds"),
    ]

    rows = []
    for s in sessions[:8]:
        rows.append(
            f"<tr><td>{html.escape(str(s.get('date') or ''))}</td>"
            f"<td>{html.escape(str(s.get('classification') or '—'))}</td>"
            f"<td>{_gval(s.get('mat_stress_cost'))}</td>"
            f"<td>{_gval(s.get('peak_hr'), ' bpm')}</td>"
            f"<td>{_gval(s.get('high_zone_min'), ' min')}</td>"
            f"<td>{'—' if s.get('round_count') is None else html.escape(str(s.get('round_count')))}</td>"
            f"<td>{html.escape(str(s.get('recovery_quality') or '—'))}</td></tr>"
        )
    table = f"""<table class="grapple-table"><thead><tr>
      <th>Date</th><th>Class</th><th>Cost</th><th>Peak</th><th>High zone</th><th>Rounds</th><th>Recovery</th>
      </tr></thead><tbody>{"".join(rows)}</tbody></table>"""
    return (
        f'<div class="card grapple">{head}{warn_html}'
        f'<div class="grapple-grid">{"".join(stats)}</div>'
        f'<div class="grapple-note">{html.escape(note)}</div>{table}</div>'
    )


# ── activities table ─────────────────────────────────────────────────────────
def _act_icon(type_str: str) -> str:
    t = (type_str or "").lower()
    if "run" in t:
        key = "run"
    elif "cycl" in t or "ride" in t or "bik" in t:
        key = "ride"
    elif "swim" in t:
        key = "swim"
    elif "strength" in t or "weight" in t or "gym" in t:
        key = "strength"
    else:
        key = "generic"
    return _ACT_ICONS[key]


def activities_table(acts: pd.DataFrame, sparse=False) -> str:
    if sparse or acts is None or acts.empty:
        return ('<div class="card"><div class="empty-note" style="margin:0;justify-content:center">'
                '<span class="ico">⚡</span> No activities synced yet.</div></div>')
    t = acts.copy()
    t = t.sort_values("date", ascending=False).head(12)
    rows = []
    for _, a in t.iterrows():
        typ = a.get("type") or "—"
        name = a.get("name") or ""
        dur = a.get("duration_s")
        dist = a.get("distance_m")
        ahr, mhr = a.get("avg_hr"), a.get("max_hr")
        load = a.get("training_load")
        te = a.get("aerobic_te")
        dur_s = "—" if pd.isna(dur) else f"{dur/60:.0f} min"
        dist_s = '<span class="muted">—</span>' if pd.isna(dist) else f"{dist/1000:.1f} km"
        hr_s = ("—" if pd.isna(ahr) else f"{ahr:.0f}") + (
            "" if pd.isna(mhr) else f' <span class="muted">/ {mhr:.0f}</span>')
        load_s = "—" if pd.isna(load) else f"{load:.0f}"
        if pd.isna(te):
            te_s = '<span class="muted">—</span>'
        else:
            cls = "hi" if te >= 3.5 else "mid" if te >= 2.5 else ""
            te_s = f'<span class="te-badge {cls}">{te:.1f}</span>'
        date_s = str(a.get("date"))[:10]
        label = html.escape(str(typ)) + (f' <span class="muted">{html.escape(str(name))}</span>' if name else "")
        rows.append(
            f'<tr><td><span class="act-type"><span class="act-ico">{_act_icon(str(typ))}</span>{label}</span></td>'
            f'<td class="muted">{date_s}</td><td>{dur_s}</td><td>{dist_s}</td>'
            f'<td>{hr_s}</td><td>{load_s}</td><td>{te_s}</td></tr>')
    return f"""<div class="card acts"><table>
      <thead><tr><th>Activity</th><th>Date</th><th>Duration</th><th>Distance</th>
      <th>Avg / Max HR</th><th>Load</th><th>Aerobic TE</th></tr></thead>
      <tbody>{"".join(rows)}</tbody></table></div>"""


# ════════════════════════════════════════════════════════════════════════════
#  TREND CHARTS  (dark Plotly per the bundle's port notes)
# ════════════════════════════════════════════════════════════════════════════
def _dark(fig: go.Figure, height: int, legend=True) -> go.Figure:
    mono = "JetBrains Mono, monospace"
    fig.update_layout(
        height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Archivo, sans-serif", color=TEXT_FAINT, size=11),
        margin=dict(t=34, b=24, l=44, r=16), hovermode="x unified",
        showlegend=legend,
        legend=dict(orientation="h", y=1.18, x=0, font=dict(family=mono, color=TEXT_DIM, size=10.5),
                    bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, showline=False,
                     tickfont=dict(family=mono, color=TEXT_FAINT, size=10))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, showline=False,
                     tickfont=dict(family=mono, color=TEXT_FAINT, size=10))
    return fig


def _glow_line(fig, x, y, color, name, width=2, **kw):
    """Primary line with a soft translucent underlay to fake the neon glow."""
    vals = pd.Series(y).dropna()
    mode = "lines+markers" if len(vals) <= 2 else "lines"
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=color, width=width*4),
                             opacity=0.12, hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=x, y=y, name=name, mode=mode,
        line=dict(color=color, width=width, shape="spline"),
        marker=dict(color=color, size=7, line=dict(color=BG, width=1)),
        **kw
    ))


def _clamp_x_to_data(fig, view, cols) -> None:
    """Clamp the x-axis to the date span where any of `cols` actually has data,
    so leading/trailing no-data days don't leave a dead zone (and squash the
    plot) on short or sparse history."""
    if view is None or view.empty or "date" not in view:
        return
    mask = pd.Series(False, index=view.index)
    for col in cols:
        if col in view:
            mask = mask | pd.to_numeric(view[col], errors="coerce").notna()
    have = pd.to_datetime(view.loc[mask, "date"], errors="coerce").dropna()
    if not have.empty:
        pad = pd.Timedelta(hours=12)
        fig.update_xaxes(range=[have.min() - pad, have.max() + pad])


def chart_hrv(view: pd.DataFrame, band) -> go.Figure:
    x = view["date"]
    fig = go.Figure()
    lo, hi = band
    if lo is not None and hi is not None:
        fig.add_hrect(y0=lo, y1=hi, fillcolor=GOOD, opacity=0.10, line_width=0)
        fig.add_hline(y=hi, line=dict(color=GOOD, width=1, dash="dot"), opacity=0.4)
        fig.add_hline(y=lo, line=dict(color=GOOD, width=1, dash="dot"), opacity=0.4)
    if "hrv_7d" in view:
        fig.add_trace(go.Scatter(x=x, y=view["hrv_7d"], name="7-day avg", mode="lines",
                                 line=dict(color=TEXT_DIM, width=1.5, dash="dot")))
    _glow_line(fig, x, view["hrv_overnight_avg"], ACCENT, "HRV")
    return _dark(fig, 230)


def chart_rhr(view: pd.DataFrame) -> go.Figure:
    x = view["date"]
    fig = go.Figure()
    if "rhr_28d" in view:
        fig.add_trace(go.Scatter(x=x, y=view["rhr_28d"], name="28-day", mode="lines",
                                 line=dict(color=TEXT_FAINT, width=1.5, dash="dash")))
    if "rhr_7d" in view:
        fig.add_trace(go.Scatter(x=x, y=view["rhr_7d"], name="7-day", mode="lines",
                                 line=dict(color=TEXT_DIM, width=1.5, dash="dot")))
    _glow_line(fig, x, view["resting_hr"], SERIES2, "RHR")
    fig = _dark(fig, 230)
    _clamp_x_to_data(fig, view, ["resting_hr"])
    return fig


def chart_sleeping_hr(view: pd.DataFrame) -> go.Figure:
    """Sleeping HR: lowest-overnight (primary) + 7-day avg + faint bedtime line."""
    x = view["date"]
    fig = go.Figure()
    if "hr_overnight_low_7d" in view:
        fig.add_trace(go.Scatter(x=x, y=view["hr_overnight_low_7d"], name="7-day", mode="lines",
                                 line=dict(color=TEXT_DIM, width=1.5, dash="dot")))
    if "hr_bedtime" in view and view["hr_bedtime"].notna().any():
        fig.add_trace(go.Scatter(x=x, y=view["hr_bedtime"], name="At bedtime", mode="lines",
                                 line=dict(color=TEXT_FAINT, width=1.5)))
    _glow_line(fig, x, view["hr_overnight_low"], SERIES2, "Lowest overnight")
    return _dark(fig, 230)


def chart_bedtime_hr(view: pd.DataFrame) -> go.Figure:
    """Pre-sleep heart-rate median derived from samples before sleep start."""
    x = view["date"]
    fig = go.Figure()
    if "hr_bedtime_7d" in view:
        fig.add_trace(go.Scatter(x=x, y=view["hr_bedtime_7d"], name="7-day", mode="lines",
                                 line=dict(color=TEXT_DIM, width=1.5, dash="dot")))
    y = pd.to_numeric(view["hr_bedtime"], errors="coerce")
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines", line=dict(color=AMBER, width=8, shape="linear"),
        opacity=0.10, hoverinfo="skip", showlegend=False, connectgaps=False,
    ))
    fig.add_trace(go.Scatter(
        x=x, y=y, name="10m median", mode="lines+markers",
        line=dict(color=AMBER, width=2, shape="linear"),
        marker=dict(color=AMBER, size=7, line=dict(color=BG, width=1)),
        connectgaps=False,
    ))
    _clamp_x_to_data(fig, view, ["hr_bedtime"])
    return _dark(fig, 230)


def chart_sleep(view: pd.DataFrame, target=8.0) -> go.Figure:
    x = view["date"]
    h = view["sleep_hours"]
    colors = [ACCENT if (v is not None and pd.notna(v) and v >= 7) else SERIES2 for v in h]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=h, name="Sleep", marker_color=colors, marker_line_width=0))
    fig.add_hline(y=target, line=dict(color=TEXT_DIM, width=1.5, dash="dash"),
                  annotation_text=f"{target:.1f} h", annotation_font_color=TEXT_FAINT)
    return _dark(fig, 230, legend=False)


def chart_early_waking(model: dict) -> go.Figure:
    from plotly.subplots import make_subplots

    rows = pd.DataFrame((model or {}).get("rows") or [])
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if rows.empty or "date" not in rows:
        return _dark(fig, 260)

    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows["early_waking_minutes"] = pd.to_numeric(rows.get("early_waking_minutes"), errors="coerce")
    rows["body_battery_at_sleep_start"] = pd.to_numeric(
        rows.get("body_battery_at_sleep_start"), errors="coerce"
    )
    if "pattern" not in rows:
        rows["pattern"] = "unclear"
    if "confidence" not in rows:
        rows["confidence"] = ""
    rows = rows.dropna(subset=["date"]).sort_values("date")
    if rows.empty:
        return _dark(fig, 260)

    colors = []
    for v in rows["early_waking_minutes"]:
        if pd.isna(v) or v < 20:
            colors.append(TEXT_FAINT)
        elif v < 45:
            colors.append(SERIES2)
        elif v < 90:
            colors.append(AMBER)
        else:
            colors.append(RED)

    fig.add_hrect(y0=45, y1=90, fillcolor=AMBER, opacity=0.06, line_width=0, secondary_y=False)
    fig.add_hrect(y0=90, y1=180, fillcolor=RED, opacity=0.05, line_width=0, secondary_y=False)
    fig.add_hline(y=45, line=dict(color=TEXT_FAINT, width=1, dash="dot"), opacity=0.5, secondary_y=False)
    custom = rows[["pattern", "confidence"]].fillna("").to_numpy()
    fig.add_trace(go.Bar(
        x=rows["date"], y=rows["early_waking_minutes"], name="Early for recovery",
        marker_color=colors, marker_line_width=0, opacity=0.78,
        customdata=custom,
        hovertemplate=(
            "%{x|%b %-d}<br>%{y:.0f} min early for recovery"
            "<br>%{customdata[0]}<br>%{customdata[1]} confidence<extra></extra>"
        ),
    ), secondary_y=False)

    if rows["body_battery_at_sleep_start"].notna().any():
        fig.add_trace(go.Scatter(
            x=rows["date"], y=rows["body_battery_at_sleep_start"],
            name="BB at sleep start", mode="lines+markers",
            line=dict(color=ACCENT, width=2, shape="spline"),
            marker=dict(color=ACCENT, size=6, line=dict(color=BG, width=1)),
            connectgaps=False,
        ), secondary_y=True)
        fig.update_yaxes(title_text="BB at sleep start", range=[0, 100], secondary_y=True)
    else:
        fig.update_yaxes(visible=False, secondary_y=True)

    ymax = rows["early_waking_minutes"].dropna().max()
    upper = 120 if pd.isna(ymax) else max(60, min(180, float(ymax) + 20))
    fig.update_yaxes(title_text="min early for recovery", range=[0, upper], secondary_y=False)
    fig.update_xaxes(tickformat="%b %-d")
    _clamp_x_to_data(fig, rows, ["early_waking_minutes", "body_battery_at_sleep_start"])
    return _dark(fig, 260)


def chart_sleep_comp(view: pd.DataFrame) -> go.Figure:
    s = view.tail(21)
    x = s["date"]
    fig = go.Figure()
    layers = [("deep_seconds", "Deep", "#5A8F1E", 0.95), ("rem_seconds", "REM", ACCENT, 0.92),
              ("light_seconds", "Light", SERIES2, 0.85), ("awake_seconds", "Awake", "#3A3F47", 0.55)]
    for col, name, color, op in layers:
        if col in s:
            fig.add_trace(go.Bar(x=x, y=s[col] / 3600.0, name=name, marker_color=color,
                                 marker_line_width=0, opacity=op))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title_text="hours")
    return _dark(fig, 230)


def chart_body_battery_daily(day: pd.DataFrame) -> go.Figure:
    s = day.dropna(subset=["timestamp", "value"]).sort_values("timestamp")
    x = s["timestamp"]
    y = s["value"]
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=25, fillcolor=RED, opacity=0.07, line_width=0)
    fig.add_hrect(y0=25, y1=50, fillcolor=AMBER, opacity=0.07, line_width=0)
    fig.add_hrect(y0=50, y1=100, fillcolor=GOOD, opacity=0.06, line_width=0)
    fig.add_trace(go.Scatter(
        x=x, y=y, name="Body Battery", mode="lines",
        line=dict(color=ACCENT, width=2.5, shape="spline"),
        fill="tozeroy", fillcolor="rgba(198,242,59,0.12)",
    ))
    if not y.empty:
        fig.add_trace(go.Scatter(
            x=[x.iloc[0], x.iloc[-1]], y=[y.iloc[0], y.iloc[-1]],
            name="Start / latest", mode="markers",
            marker=dict(size=7, color=[SERIES2, ACCENT], line=dict(width=0)),
        ))
    fig.update_yaxes(range=[0, 100], title_text="score")
    return _dark(fig, 240)


def chart_stress_daily(day: pd.DataFrame) -> go.Figure:
    s = day.dropna(subset=["timestamp", "value"]).sort_values("timestamp")
    x = s["timestamp"]
    y = s["value"]
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=25, fillcolor=GOOD, opacity=0.06, line_width=0)
    fig.add_hrect(y0=25, y1=50, fillcolor=AMBER, opacity=0.06, line_width=0)
    fig.add_hrect(y0=50, y1=100, fillcolor=RED, opacity=0.07, line_width=0)
    fig.add_trace(go.Scatter(
        x=x, y=y, name="Stress", mode="lines",
        line=dict(color=AMBER, width=2, shape="spline"),
        fill="tozeroy", fillcolor="rgba(255,255,255,0.12)",
    ))
    fig.update_yaxes(range=[0, 100], title_text="level")
    return _dark(fig, 240, legend=False)


def chart_weekly_stress_overview(model: dict) -> go.Figure:
    rows = pd.DataFrame((model or {}).get("rows") or [])
    fig = go.Figure()
    if rows.empty or "date" not in rows:
        return _dark(fig, 260)

    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    if "stress_avg" not in rows:
        rows["stress_avg"] = np.nan
    rows["stress_avg"] = pd.to_numeric(rows["stress_avg"], errors="coerce")
    rows = rows.dropna(subset=["date"]).sort_values("date")
    if rows.empty:
        return _dark(fig, 260)

    mean = model.get("mean")
    std = model.get("std")
    if mean is not None and std is not None and std > 0:
        fig.add_hrect(
            y0=model.get("band_2sd_low"), y1=model.get("band_2sd_high"),
            fillcolor=SERIES2, opacity=0.045, line_width=0,
        )
        fig.add_hrect(
            y0=model.get("band_1sd_low"), y1=model.get("band_1sd_high"),
            fillcolor=SERIES2, opacity=0.12, line_width=0,
        )
        fig.add_hline(y=mean, line=dict(color=TEXT_DIM, width=1.2, dash="dot"), opacity=0.72)

    x = rows["date"]
    y = rows["stress_avg"]
    colors = [
        TEXT_FAINT if pd.isna(v) else GOOD if v < 25 else AMBER if v < 50 else RED
        for v in y
    ]
    fig.add_trace(go.Bar(
        x=x, y=y, name="Daily avg", marker_color=colors, marker_line_width=0,
        opacity=0.72,
    ))
    fig.add_trace(go.Scatter(
        x=x, y=y, name="Daily avg line", mode="lines+markers",
        line=dict(color=TEXT, width=1.8, shape="spline"),
        marker=dict(size=7, color=TEXT, line=dict(color=BG, width=1)),
        connectgaps=False,
    ))
    if mean is not None:
        fig.add_trace(go.Scatter(
            x=x, y=[mean] * len(rows), name="Week avg", mode="lines",
            line=dict(color=TEXT_DIM, width=1.2, dash="dot"),
            hoverinfo="skip",
        ))

    y_values = y.dropna()
    ymax = float(y_values.max()) if not y_values.empty else 50.0
    band_high = model.get("band_2sd_high") if model.get("band_2sd_high") is not None else ymax
    upper = min(100, max(50, ymax + 10, float(band_high) + 5))
    fig.update_yaxes(range=[0, upper], title_text="avg stress")
    fig.update_xaxes(tickformat="%a")
    return _dark(fig, 260)


def chart_acwr(view: pd.DataFrame) -> go.Figure:
    from plotly.subplots import make_subplots
    x = view["date"]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if "acute_load" in view:
        fig.add_trace(go.Bar(x=x, y=view["acute_load"], name="Acute load (7d)",
                             marker_color="rgba(255,255,255,0.18)", marker_line_width=0),
                      secondary_y=False)
    if "chronic_load" in view:
        fig.add_trace(go.Scatter(x=x, y=view["chronic_load"], name="Chronic (wkly)",
                                 line=dict(color=TEXT_DIM, width=1.5)), secondary_y=False)
    fig.add_hrect(y0=0.8, y1=1.3, fillcolor=GOOD, opacity=0.10, line_width=0, secondary_y=True)
    fig.add_trace(go.Scatter(x=x, y=view["acwr"], name="ACWR", mode="lines",
                             line=dict(color=ACCENT, width=2.5)), secondary_y=True)
    fig.update_yaxes(title_text="Load", secondary_y=False, gridcolor=GRID,
                     tickfont=dict(color=TEXT_FAINT, size=10.5))
    fig.update_yaxes(title_text="ACWR", secondary_y=True, range=[0.5, 2.0],
                     gridcolor="rgba(0,0,0,0)", tickfont=dict(color=TEXT_FAINT, size=10.5))
    return _dark(fig, 260)


def chart_vo2(view: pd.DataFrame) -> go.Figure:
    x = view["date"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=view["vo2max"], name="VO₂max", mode="lines+markers",
                             line=dict(color=SERIES2, width=2),
                             marker=dict(size=4, color=SERIES2),
                             fill="tozeroy", fillcolor="rgba(255,255,255,0.12)"))
    ys = view["vo2max"].dropna()
    if not ys.empty:
        fig.update_yaxes(range=[ys.min() - 0.6, ys.max() + 0.6])
    return _dark(fig, 220, legend=False)


def chart_recovery_deviation(view: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if view is None or view.empty or "date" not in view:
        return _dark(fig, 250)
    x = view["date"]
    fig.add_hrect(y0=-4, y1=-1, fillcolor=RED, opacity=0.08, line_width=0)
    fig.add_hrect(y0=1, y1=4, fillcolor=AMBER, opacity=0.06, line_width=0)
    fig.add_hline(y=0, line=dict(color=TEXT_FAINT, width=1, dash="dot"), opacity=0.5)
    specs = [
        ("hrv_z", "HRV z", ACCENT),
        ("rhr_z", "RHR z", SERIES2),
        ("sleep_z", "Sleep z", AMBER),
        ("stress_z", "Stress z", RED),
    ]
    for col, name, color in specs:
        if col in view and pd.to_numeric(view[col], errors="coerce").notna().any():
            _glow_line(fig, x, pd.to_numeric(view[col], errors="coerce"), color, name, width=1.8)
    fig.update_yaxes(title_text="z-score vs prior 28d", range=[-3.2, 3.2])
    _clamp_x_to_data(fig, view, [c for c, _, _ in specs])
    return _dark(fig, 260)


def chart_sleep_regularity(view: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if view is None or view.empty or "date" not in view:
        return _dark(fig, 250)
    x = view["date"]
    fig.add_hrect(y0=60, y1=240, fillcolor=AMBER, opacity=0.06, line_width=0)
    fig.add_hline(y=60, line=dict(color=TEXT_FAINT, width=1, dash="dot"), opacity=0.5)
    specs = [
        ("sleep_midpoint_variability_7d", "Midpoint SD", ACCENT),
        ("bedtime_variability_7d", "Bedtime SD", SERIES2),
        ("wake_time_variability_7d", "Wake SD", AMBER),
    ]
    for col, name, color in specs:
        if col in view and pd.to_numeric(view[col], errors="coerce").notna().any():
            _glow_line(fig, x, pd.to_numeric(view[col], errors="coerce"), color, name, width=1.8)
    fig.update_yaxes(title_text="minutes")
    _clamp_x_to_data(fig, view, [c for c, _, _ in specs])
    return _dark(fig, 260)


def chart_respiratory_watchlist(view: pd.DataFrame) -> go.Figure:
    from plotly.subplots import make_subplots
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if view is None or view.empty or "date" not in view:
        return _dark(fig, 260)
    x = view["date"]
    if "spo2_avg" in view and pd.to_numeric(view["spo2_avg"], errors="coerce").notna().any():
        fig.add_hline(y=94, line=dict(color=AMBER, width=1, dash="dot"), opacity=0.55, secondary_y=False)
        fig.add_trace(go.Scatter(
            x=x, y=pd.to_numeric(view["spo2_avg"], errors="coerce"),
            name="SpO₂", mode="lines+markers",
            line=dict(color=ACCENT, width=2, shape="spline"),
            marker=dict(color=ACCENT, size=5),
        ), secondary_y=False)
    if "respiration_avg" in view and pd.to_numeric(view["respiration_avg"], errors="coerce").notna().any():
        fig.add_trace(go.Scatter(
            x=x, y=pd.to_numeric(view["respiration_avg"], errors="coerce"),
            name="Respiration", mode="lines+markers",
            line=dict(color=SERIES2, width=2, shape="spline"),
            marker=dict(color=SERIES2, size=5),
        ), secondary_y=True)
    fig.update_yaxes(title_text="SpO₂ %", secondary_y=False, gridcolor=GRID,
                     tickfont=dict(color=TEXT_FAINT, size=10.5))
    fig.update_yaxes(title_text="breaths/min", secondary_y=True,
                     gridcolor="rgba(0,0,0,0)", tickfont=dict(color=TEXT_FAINT, size=10.5))
    _clamp_x_to_data(fig, view, ["spo2_avg", "respiration_avg"])
    return _dark(fig, 260)


def chart_foot_pace(model: dict) -> go.Figure:
    from plotly.subplots import make_subplots
    rows = pd.DataFrame(((model or {}).get("fitness") or {}).get("activity", {}).get("rows") or [])
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if rows.empty:
        return _dark(fig, 260)
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows["pace_min_km"] = pd.to_numeric(rows["pace_min_km"], errors="coerce")
    rows["avg_hr"] = pd.to_numeric(rows.get("avg_hr"), errors="coerce")
    rows = rows.dropna(subset=["date", "pace_min_km"]).sort_values("date")
    if rows.empty:
        return _dark(fig, 260)
    fig.add_trace(go.Scatter(
        x=rows["date"], y=rows["pace_min_km"], name="Pace",
        mode="lines+markers", line=dict(color=ACCENT, width=2, shape="spline"),
        marker=dict(color=ACCENT, size=6),
        text=rows.get("name"),
        hovertemplate="%{y:.2f} min/km<br>%{text}<extra></extra>",
    ), secondary_y=False)
    if rows["avg_hr"].notna().any():
        fig.add_trace(go.Bar(
            x=rows["date"], y=rows["avg_hr"], name="Avg HR",
            marker_color="rgba(255,255,255,0.18)", marker_line_width=0,
        ), secondary_y=True)
    fig.update_yaxes(title_text="min/km", autorange="reversed", secondary_y=False,
                     gridcolor=GRID, tickfont=dict(color=TEXT_FAINT, size=10.5))
    fig.update_yaxes(title_text="avg HR", secondary_y=True,
                     gridcolor="rgba(0,0,0,0)", tickfont=dict(color=TEXT_FAINT, size=10.5))
    return _dark(fig, 260)


def chart_prebed_relationship(model: dict, y_col: str, x_col: str | None = None) -> go.Figure:
    rel = _relationship_for(model, y_col, x_col)
    rows = pd.DataFrame(rel.get("rows") or [])
    fig = go.Figure()
    if rows.empty:
        return _dark(fig, 240, legend=False)

    rows["x"] = pd.to_numeric(rows["x"] if "x" in rows else rows.get("prebed_hr"), errors="coerce")
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    rows = rows.dropna(subset=["x", "value"])
    fig.add_trace(go.Scatter(
        x=rows["x"],
        y=rows["value"],
        name=rel.get("y_label") or "Value",
        mode="markers",
        marker=dict(size=8, color=ACCENT if y_col != "next_day_stress" else AMBER,
                    opacity=0.82, line=dict(color=BG, width=1)),
        text=rows.get("date"),
        hovertemplate=f"{html.escape(rel.get('x_label') or 'Metric')} %{{x:.1f}} {html.escape(rel.get('x_unit') or '')}<br>%{{y:.1f}}<br>%{{text}}<extra></extra>",
    ))
    if len(rows) >= 3 and rows["x"].nunique() > 1:
        xs = rows["x"].astype(float)
        ys = rows["value"].astype(float)
        slope, intercept = np.polyfit(xs, ys, 1)
        line_x = pd.Series([xs.min(), xs.max()])
        fig.add_trace(go.Scatter(
            x=line_x,
            y=slope * line_x + intercept,
            name="fit",
            mode="lines",
            line=dict(color=TEXT_DIM, width=1.5, dash="dash"),
            hoverinfo="skip",
        ))
    x_unit = rel.get("x_unit") or ""
    fig.update_xaxes(title_text=f"{rel.get('x_label') or 'Metric'} {x_unit}".strip())
    if rel.get("bucket_labels"):
        labels = rel.get("bucket_labels") or []
        fig.update_xaxes(tickmode="array", tickvals=list(range(len(labels))), ticktext=labels)
    unit = rel.get("y_unit") or ""
    title = rel.get("y_label") or "Value"
    fig.update_yaxes(title_text=f"{title} {unit}".strip())
    return _dark(fig, 260, legend=False)


def _relationship_for(model: dict, y_col: str, x_col: str | None = None) -> dict:
    for rel in (model or {}).get("relationships") or []:
        if rel.get("y_col") == y_col and (x_col is None or rel.get("x_col") == x_col):
            return rel
    return {}


# ── Strength logger render helpers ────────────────────────────────────────────
def _fmt(value, suffix="", dash="—"):
    if value is None:
        return dash
    try:
        if pd.isna(value):
            return dash
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        return f"{value:,.0f}{suffix}"
    return f"{html.escape(str(value))}{suffix}"


def strength_readiness_badge(snapshot: dict) -> str:
    """Compact readiness badge for a session, from its stored snapshot dict."""
    snapshot = snapshot or {}
    score = _fmt(snapshot.get("readiness_score"))
    level = _fmt(snapshot.get("readiness_level"))
    hrv = _fmt(snapshot.get("hrv_status"))
    bb = _fmt(snapshot.get("body_battery_start"))
    return (
        f"<div style='display:flex;gap:14px;align-items:center;"
        f"background:{SURFACE};border-radius:10px;padding:8px 14px;"
        f"font-family:JetBrains Mono,monospace;color:{TEXT_DIM};font-size:12px'>"
        f"<span style='color:{ACCENT};font-size:18px;font-weight:600'>{score}</span>"
        f"<span>{level}</span><span>HRV {hrv}</span><span>BB {bb}</span></div>"
    )


def strength_session_card(session: dict, summary: dict) -> str:
    """Header card for one logged session."""
    session = session or {}
    summary = summary or {}
    name = html.escape(str(session.get("name") or "Workout"))
    day = html.escape(str(session.get("date") or ""))
    vol = _fmt(summary.get("total_volume_kg"), " kg")
    sets = _fmt(summary.get("working_sets"))
    top = _fmt(summary.get("top_est_1rm_kg"), " kg")
    return (
        f"<div style='background:{SURFACE};border-radius:12px;padding:14px 18px;"
        f"color:{TEXT};font-family:Archivo,sans-serif'>"
        f"<div style='font-size:18px;font-weight:600'>{name}"
        f"<span style='color:{TEXT_DIM};font-weight:400;font-size:13px'> · {day}</span></div>"
        f"<div style='color:{TEXT_DIM};font-size:13px;margin-top:6px'>"
        f"Volume <b style='color:{TEXT}'>{vol}</b> · "
        f"Sets <b style='color:{TEXT}'>{sets}</b> · "
        f"Top est-1RM <b style='color:{SERIES2}'>{top}</b></div></div>"
    )


def strength_onerm_trend(df, exercise_name: str):
    """Plotly line of best est-1RM over time, PRs marked. df: date,
    best_est_1rm_kg, is_pr."""
    fig = go.Figure()
    if df is not None and not df.empty:
        d = df.sort_values("date")
        fig.add_trace(go.Scatter(
            x=list(d["date"]), y=list(d["best_est_1rm_kg"]),
            mode="lines+markers", line=dict(color=ACCENT, width=2),
            marker=dict(size=6, color=ACCENT), name="est 1RM",
        ))
        prs = d[d["is_pr"] == True]  # noqa: E712
        if not prs.empty:
            fig.add_trace(go.Scatter(
                x=list(prs["date"]), y=list(prs["best_est_1rm_kg"]),
                mode="markers", marker=dict(size=11, color=SERIES2,
                                            symbol="star"), name="PR",
            ))
    fig.update_layout(
        title=f"{exercise_name} — estimated 1RM",
        paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=TEXT),
        margin=dict(l=40, r=20, t=40, b=30), height=300,
        showlegend=False,
    )
    return fig


# ── Strength Insights panels (Phase 2) ────────────────────────────────────────
def strength_standards_panel(standards: dict) -> str:
    """HTML for the standards panel. Accepts the compute_strength_standards dict."""
    standards = standards or {}
    status = standards.get("status")
    if status == "need_profile":
        miss = ", ".join(standards.get("missing", [])) or "profile data"
        return (f"<div style='color:{TEXT_DIM};font-family:Archivo,sans-serif;"
                f"font-size:14px'>Set your {html.escape(miss)} to grade your lifts "
                f"against population standards.</div>")
    if status != "ok" or not standards.get("lifts"):
        return (f"<div style='color:{TEXT_DIM};font-family:Archivo,sans-serif;"
                f"font-size:14px'>Log the main lifts (squat, bench, deadlift, OHP, row) "
                f"to see strength standards.</div>")
    ov = standards.get("overall") or {}
    rows = [
        f"<div style='background:{SURFACE};border-radius:12px;padding:14px 18px;"
        f"color:{TEXT};font-family:Archivo,sans-serif;margin-bottom:10px'>"
        f"<span style='color:{TEXT_DIM};font-size:13px'>Overall</span> "
        f"<b style='color:{ACCENT};font-size:18px'>{_fmt(ov.get('level'))}</b> "
        f"<span style='color:{TEXT_DIM}'>(~{_fmt(ov.get('percentile'))} pct)</span>"
        f"<div style='color:{TEXT_FAINT};font-size:11px;margin-top:4px'>"
        f"approximate, bodyweight-relative</div></div>"
    ]
    for l in standards["lifts"]:
        pct = l.get("percentile") or 0
        rows.append(
            f"<div style='margin:6px 0;font-family:Archivo,sans-serif;color:{TEXT}'>"
            f"<div style='display:flex;justify-content:space-between;font-size:14px'>"
            f"<span>{html.escape(str(l['name']))}</span>"
            f"<span style='color:{SERIES2}'>{_fmt(l['level'])} · {_fmt(l.get('est_1rm_kg'),' kg')}</span></div>"
            f"<div style='background:{SURFACE};border-radius:6px;height:8px;margin-top:4px'>"
            f"<div style='background:{ACCENT};height:8px;border-radius:6px;width:{min(100,max(2,pct)):.0f}%'></div>"
            f"</div></div>")
    return "".join(rows)


def strength_balance_panel(balance: dict) -> str:
    """HTML for the muscle-balance panel."""
    balance = balance or {}
    ratios = balance.get("ratios", [])
    lr = balance.get("left_right", [])
    if not ratios and not lr:
        return (f"<div style='color:{TEXT_DIM};font-family:Archivo,sans-serif;"
                f"font-size:14px'>Log more of the main lifts (and unilateral lifts per "
                f"side) to see balance.</div>")
    chip = {"ok": SERIES2, "under": ACCENT, "over": AMBER}
    out = []
    for r in ratios:
        color = chip.get(r["status"], TEXT_DIM)
        note = "" if r["status"] == "ok" else f" — weak: {html.escape(str(r.get('weak_side') or ''))}"
        out.append(
            f"<div style='margin:6px 0;font-family:Archivo,sans-serif;color:{TEXT};font-size:14px'>"
            f"<span>{html.escape(r['label'])}</span> "
            f"<b style='color:{color}'>{_fmt(r['ratio'])}</b> "
            f"<span style='color:{TEXT_DIM};font-size:12px'>(target {r['low']}–{r['high']})</span>"
            f"<span style='color:{color};font-size:12px'>{note}</span></div>")
    if lr:
        out.append(f"<div style='color:{TEXT_DIM};font-size:12px;margin-top:10px'>Left / right</div>")
        for e in lr:
            color = ACCENT if e.get("flagged") else SERIES2
            out.append(
                f"<div style='margin:4px 0;font-family:Archivo,sans-serif;color:{TEXT};font-size:14px'>"
                f"{html.escape(str(e['name']))}: L {_fmt(e.get('left_1rm_kg'))} / R {_fmt(e.get('right_1rm_kg'))} "
                f"<b style='color:{color}'>Δ{_fmt(e.get('diff_pct'))}%</b>"
                f"{' ⚠' if e.get('flagged') else ''}</div>")
    return "".join(out)


def _exp_num(v):
    return "—" if v is None else f"{v:g}"


def _exp_signed(v):
    return "—" if v is None else (f"+{v:g}" if v >= 0 else f"{v:g}")


_VERDICT_TONE = {
    "likely helped": ("✅", "#C6F23B"),
    "likely hurt": ("⚠️", "#FF5A4D"),
    "no clear effect": ("•", "#8E959C"),
    "insufficient_data": ("…", "#8E959C"),
}


def experiment_result_card(result: dict) -> str:
    """Render one experiment's per-metric before/after result. Pure HTML."""
    name = html.escape(str(result.get("name", "Experiment")))
    bw = result.get("baseline_window") or [None, None]
    iw = result.get("intervention_window") or [None, None]
    meta = f"baseline {bw[0]}–{bw[1]} · intervention {iw[0]}–{iw[1]}"
    head = (f'<div class="coach-head"><span class="glyph">{_SPARK}</span>'
            f'<div><h3>{name}</h3>'
            f'<div class="meta">{html.escape(meta)}</div></div></div>')
    metrics = result.get("metrics") or {}
    if not metrics:
        body = ('<div class="empty-note" style="margin:0"><span class="ico">🧪</span> '
                'No metrics selected for this experiment.</div>')
        return _collapse_html(f'<div class="card coach">{head}{body}</div>')
    rows = []
    for key, m in metrics.items():
        verdict = str(m.get("verdict", ""))
        icon, color = _VERDICT_TONE.get(verdict, ("•", "#8E959C"))
        label = html.escape(str(m.get("label", key)))
        if verdict == "insufficient_data" or m.get("delta") is None:
            detail = (f'<span style="opacity:.7">not enough data '
                      f'({m.get("n_before", 0)}/{m.get("n_after", 0)} days)</span>')
        else:
            detail = (f'{_exp_num(m.get("mean_before"))} → {_exp_num(m.get("mean_after"))} '
                      f'(Δ {_exp_signed(m.get("delta"))}, 95% CI '
                      f'{_exp_num(m.get("ci_low"))}…{_exp_num(m.get("ci_high"))})')
        rows.append(
            f'<div style="margin:4px 0">'
            f'<span style="color:{color}">{icon}</span> <b>{label}</b> — '
            f'<span style="color:{color}">{html.escape(verdict)}</span><br>'
            f'<span style="font-size:12px;opacity:.85">{detail}</span></div>')
    notes = result.get("notes") or []
    note_html = ""
    if notes:
        note_html = ('<div style="font-size:11px;opacity:.6;margin-top:6px">'
                     + html.escape(" ".join(str(n) for n in notes)) + "</div>")
    body = "".join(rows) + note_html
    return _collapse_html(f'<div class="card coach">{head}{body}</div>')


def strength_correlation_panel(corr: dict):
    """Plotly bar (readiness bucket vs avg relative performance) when ok, else a
    string message."""
    corr = corr or {}
    if corr.get("status") != "ok":
        need = corr.get("need", 8)
        have = corr.get("have", 0)
        return (f"Log ~{max(0, int(need) - int(have))} more sessions to unlock the "
                f"readiness-vs-performance view (have {have}, need {need}).")
    buckets = corr.get("buckets", {})
    order = [b for b in ("Low", "Med", "High") if b in buckets]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=order, y=[buckets[b]["avg_rel_perf"] for b in order],
        marker_color=ACCENT,
        text=[f"n={buckets[b]['n']}" for b in order], textposition="outside",
    ))
    fig.update_layout(
        title=f"Readiness vs lifting (r={_fmt(corr.get('correlation'))})",
        paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=TEXT),
        yaxis=dict(title="avg rel. performance", range=[0, 1.1]),
        margin=dict(l=40, r=20, t=40, b=30), height=300, showlegend=False,
    )
    return fig
