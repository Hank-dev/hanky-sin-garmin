"""Strength logger — Strong-style live workout logging on its own page.

Live state lives in st.session_state["active"] until you press Finish, which
persists the session + sets and stamps the readiness snapshot for the day.
"""
import html
import uuid
import importlib
from datetime import datetime, date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
import db
import analysis
import cockpit
import strength_catalog
import ai

config = importlib.reload(config)
db = importlib.reload(db)
analysis = importlib.reload(analysis)
cockpit = importlib.reload(cockpit)
strength_catalog = importlib.reload(strength_catalog)
ai = importlib.reload(ai)

st.markdown("""
<style>
.strength-page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin:4px 0 18px;}
.strength-page-title{font-family:var(--font-serif);font-size:34px;line-height:1.05;color:var(--text);font-weight:400;}
.strength-page-sub{color:var(--text-faint);font-size:13px;margin-top:4px;}
.strength-overview{display:grid;gap:14px;container-type:inline-size;}
.strength-hero{
  border:1px solid var(--border);border-top-color:var(--brass);border-radius:8px;
  background:linear-gradient(180deg,var(--surface-2),var(--surface) 64%,#0F0D11);
  width:100%;box-sizing:border-box;overflow:hidden;
  padding:18px 20px;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);
  gap:18px;align-items:stretch;
}
.strength-hero > div{min-width:0;}
.strength-hero h2{font-family:var(--font-serif);font-size:31px;font-weight:400;line-height:1.05;margin:0;color:var(--text);}
.strength-hero .meta{font-family:var(--font-mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);margin-bottom:8px;}
.strength-hero .sub{color:var(--text-dim);font-size:13px;margin-top:8px;}
.strength-kpi-grid{display:grid;grid-template-columns:repeat(2,minmax(132px,1fr));gap:10px;width:100%;min-width:0;}
.strength-kpi{min-width:0;overflow:hidden;background:var(--surface-2);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:11px 12px;min-height:86px;}
.strength-kpi *{word-break:normal;overflow-wrap:normal;hyphens:manual;}
.strength-kpi .lab{font-family:var(--font-mono);font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:var(--text-faint);white-space:nowrap;}
.strength-kpi .val{margin-top:7px;font-size:22px;color:var(--text);font-weight:750;font-variant-numeric:tabular-nums;line-height:1.08;white-space:nowrap;}
.strength-kpi .sub{margin-top:5px;font-size:11px;color:var(--text-faint);line-height:1.25;}
.strength-panel{
  border:1px solid var(--border);border-radius:8px;background:var(--surface);padding:14px 16px;
}
.strength-panel h3{font-family:var(--font-serif);font-size:22px;font-weight:400;margin:0 0 10px;color:var(--text);}
.strength-table{display:grid;gap:7px;}
.strength-row{display:grid;grid-template-columns:minmax(0,1.7fr) .7fr .9fr .9fr .55fr;gap:10px;align-items:center;
  padding:9px 0;border-bottom:1px solid rgba(255,255,255,.05);}
.strength-row:last-child{border-bottom:0;}
.strength-row.head{font-family:var(--font-mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);padding-top:0;}
.strength-row .name{font-weight:700;color:var(--text);min-width:0;}
.strength-row .num{font-family:var(--font-mono);font-size:13px;color:var(--text-dim);font-variant-numeric:tabular-nums;}
.strength-pr{display:inline-flex;align-items:center;border:1px solid color-mix(in srgb,var(--accent) 45%,transparent);
  color:var(--accent);border-radius:999px;padding:3px 8px;font-family:var(--font-mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;}
.strength-history-rollup{display:grid;gap:0;margin:8px 0 10px;border:1px solid rgba(255,255,255,.06);border-radius:8px;overflow:hidden;}
.strength-history-row{display:grid;grid-template-columns:minmax(0,1.5fr) .55fr .8fr .78fr .78fr .45fr;gap:10px;align-items:center;
  padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.05);background:rgba(255,255,255,.018);}
.strength-history-row:last-child{border-bottom:0;}
.strength-history-row.head{background:rgba(255,255,255,.035);font-family:var(--font-mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);}
.strength-history-row .name{font-weight:700;color:var(--text);min-width:0;}
.strength-history-row .num{font-family:var(--font-mono);font-size:12px;color:var(--text-dim);font-variant-numeric:tabular-nums;}
.strength-momentum-counts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:2px 0 12px;}
.strength-momentum-count{background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:9px 10px;}
.strength-momentum-count .lab{font-family:var(--font-mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);}
.strength-momentum-count .val{margin-top:4px;font-size:21px;font-weight:800;color:var(--text);font-variant-numeric:tabular-nums;}
.strength-momentum-section{margin-top:10px;}
.strength-momentum-title{font-family:var(--font-mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);margin-bottom:4px;}
.strength-momentum-row{display:grid;grid-template-columns:minmax(0,1.25fr) .65fr .55fr minmax(0,1.4fr);gap:10px;align-items:center;
  padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05);}
.strength-momentum-row:last-child{border-bottom:0;}
.strength-momentum-row .name{font-weight:700;color:var(--text);min-width:0;}
.strength-momentum-row .num{font-family:var(--font-mono);font-size:12px;color:var(--text-dim);font-variant-numeric:tabular-nums;}
.strength-momentum-row .note{color:var(--text-faint);font-size:12px;line-height:1.3;}
.strength-leaderboard{display:grid;gap:0;margin-top:8px;border:1px solid rgba(255,255,255,.06);border-radius:8px;overflow:hidden;}
.strength-leaderboard-row{display:grid;grid-template-columns:.36fr minmax(0,1.2fr) .72fr .86fr .82fr .78fr .7fr;gap:10px;align-items:center;
  padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.05);background:rgba(255,255,255,.018);}
.strength-leaderboard-row:last-child{border-bottom:0;}
.strength-leaderboard-row.head{background:rgba(255,255,255,.035);font-family:var(--font-mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);}
.strength-leaderboard-row .rank{font-family:var(--font-mono);font-size:12px;color:var(--text-faint);font-variant-numeric:tabular-nums;}
.strength-leaderboard-row .name{font-weight:750;color:var(--text);min-width:0;}
.strength-leaderboard-row .num{font-family:var(--font-mono);font-size:12px;color:var(--text-dim);font-variant-numeric:tabular-nums;}
.st-key-strength_trend_card,
.st-key-strength_pr_card{min-height:450px!important;box-sizing:border-box;}
.st-key-strength_trend_card [data-testid="stVerticalBlockBorderWrapper"],
.st-key-strength_pr_card [data-testid="stVerticalBlockBorderWrapper"]{min-height:450px;padding:18px 18px 16px!important;}
.st-key-strength_trend_card [data-testid="stVerticalBlock"],
.st-key-strength_pr_card [data-testid="stVerticalBlock"]{gap:.45rem!important;}
.strength-pr-list{display:grid;gap:0;margin-top:4px;}
.strength-pr-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;align-items:baseline;
  padding:10px 0;border-bottom:1px solid rgba(255,255,255,.055);}
.strength-pr-row:last-child{border-bottom:0;}
.strength-pr-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text);font-weight:750;font-size:14.5px;}
.strength-pr-value{white-space:nowrap;color:var(--text);font-size:14px;font-variant-numeric:tabular-nums;}
.strength-pr-date{grid-column:1/-1;color:var(--text-faint);font-size:11.5px;font-variant-numeric:tabular-nums;}
.strength-ai-title{font-family:var(--font-serif);font-size:22px;font-weight:400;color:var(--text);line-height:1.05;}
.strength-ai-meta{font-family:var(--font-mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);margin-top:4px;}
.strength-feedback-empty{color:var(--text-dim);font-size:13.5px;line-height:1.45;margin-top:4px;}
.strength-feedback-preview{color:var(--text);line-height:1.55;margin-top:8px;max-width:92ch;}
.strength-feedback{color:var(--text);line-height:1.55;}
.st-key-strength_ai_feedback{container-type:inline-size;margin-top:12px!important;}
.st-key-strength_ai_feedback [data-testid="stVerticalBlockBorderWrapper"]{padding:16px 18px 18px!important;}
.st-key-strength_ai_feedback [data-testid="stVerticalBlock"]{gap:.28rem!important;}
.st-key-strength_ai_header [data-testid="stHorizontalBlock"]{
  display:grid!important;grid-template-columns:minmax(0,1fr) max-content max-content!important;
  gap:12px!important;align-items:center!important;
}
.st-key-strength_ai_header [data-testid="column"]{width:auto!important;min-width:0!important;}
.st-key-strength_ai_header [data-testid="stButton"]{display:flex!important;justify-content:flex-end!important;}
.st-key-strength_ai_header div.stButton>button{
  width:104px!important;min-width:104px!important;max-width:104px!important;
  min-height:36px!important;height:36px!important;padding:7px 10px!important;
  border-radius:8px!important;font-size:12.5px!important;line-height:1!important;
  background:var(--surface-2)!important;color:var(--text)!important;
  border:1px solid var(--border-2)!important;box-shadow:inset 0 1px 0 var(--inset-hi)!important;
  filter:none!important;
}
.st-key-strength_ai_header div.stButton>button:hover{
  background:color-mix(in srgb,var(--accent) 10%,var(--surface-2))!important;
  border-color:color-mix(in srgb,var(--accent) 38%,transparent)!important;color:var(--text)!important;
}
.st-key-strength_ai_header div.stButton>button p{margin:0!important;line-height:1!important;white-space:nowrap!important;}
.st-key-strength_ai_header div.stButton>button [data-testid="stIconMaterial"]{font-size:16px!important;margin-right:5px!important;color:var(--accent)!important;}
@container (max-width:900px){
  .strength-hero{grid-template-columns:1fr;}
}
@media (max-width:820px){
  .strength-hero{grid-template-columns:1fr;}
  .strength-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
  .strength-row{grid-template-columns:minmax(0,1.4fr) .6fr .8fr .8fr .45fr;gap:6px;}
  .strength-history-row{grid-template-columns:minmax(0,1.4fr) .45fr .7fr .7fr .72fr .42fr;gap:6px;}
  .strength-momentum-counts{grid-template-columns:repeat(2,minmax(0,1fr));}
  .strength-momentum-row{grid-template-columns:minmax(0,1.1fr) .6fr .5fr minmax(0,1fr);gap:6px;}
  .strength-leaderboard-row{grid-template-columns:.3fr minmax(0,1.1fr) .64fr .74fr .7fr .7fr .58fr;gap:6px;}
}
@media (max-width:560px){
  .strength-hero{padding:14px;}
  .strength-kpi-grid{grid-template-columns:1fr 1fr;}
  .strength-kpi{padding:10px;min-height:82px;}
  .strength-kpi .val{font-size:20px;}
  .strength-row{font-size:13px;}
  .strength-row .num{font-size:11px;}
  .strength-history-row{font-size:12px;padding:7px 8px;}
  .strength-history-row .num{font-size:10px;}
  .strength-momentum-row{font-size:12px;}
  .strength-momentum-row .num,.strength-momentum-row .note{font-size:10px;}
  .strength-leaderboard-row{font-size:11px;padding:7px 8px;}
  .strength-leaderboard-row .num,.strength-leaderboard-row .rank{font-size:10px;}
}
.st-key-strong_logger{
  max-width:720px;margin:0 auto 22px!important;padding:0 22px 18px!important;background:var(--surface);
  border:1px solid rgba(255,255,255,.06);border-radius:8px;overflow:hidden;
  box-shadow:0 22px 70px -36px rgba(0,0,0,.9);
}
.st-key-strong_logger [data-testid="stVerticalBlock"]{gap:.45rem;}
.st-key-strong_topbar{
  position:sticky;top:0;z-index:10;margin:0 -22px 8px!important;
  padding:10px 18px!important;background:var(--surface-2);
  border-bottom:1px solid rgba(255,255,255,.04);
}
.strong-top{
  position:sticky;top:0;z-index:10;display:grid;grid-template-columns:64px 64px 1fr 104px;
  align-items:center;gap:8px;padding:10px 18px;background:var(--surface-2);
  border-bottom:1px solid rgba(255,255,255,.04);
}
.strong-top-cell{
  min-height:44px;display:flex;align-items:center;justify-content:center;
  background:var(--surface-2);color:var(--text);
}
.strong-top .icon{
  min-height:44px;display:grid;place-items:center;color:var(--text);font-size:28px;line-height:1;
}
.strong-top-cell.icon{font-size:28px;line-height:1;}
.strong-top .timer,.strong-top-cell.timer{
  text-align:center;color:var(--text-dim);font-size:22px;font-variant-numeric:tabular-nums;
}
.strong-finish{
  color:var(--accent);text-align:right;font-size:20px;font-weight:700;letter-spacing:.16em;
}
.strong-head{padding:26px 22px 16px;}
.strong-title{font-size:28px;line-height:1.08;font-weight:800;color:var(--text);letter-spacing:-.01em;}
.strong-duration{margin-top:14px;color:var(--text-dim);font-size:24px;font-variant-numeric:tabular-nums;}
.strong-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:0 22px 18px;}
.strong-stat{background:var(--surface-2);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:9px 11px;}
.strong-stat .lab{font-family:var(--font-mono);font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--text-faint);}
.strong-stat .val{margin-top:3px;font-size:18px;color:var(--text);font-weight:750;font-variant-numeric:tabular-nums;}
.strong-section{padding:0 22px 18px;}
.strong-ex-head{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:12px;margin-top:18px;}
.strong-ex-title{color:var(--accent);font-size:22px;font-weight:800;letter-spacing:.01em;}
.strong-ex-tools{display:flex;align-items:center;gap:8px;color:var(--accent);font-weight:800;}
.strong-note{
  margin:12px 0 10px;padding:11px 14px;background:rgba(232,194,106,.14);color:var(--text);
  font-size:17px;line-height:1.25;border-radius:0;
}
.strong-col-head{
  display:grid;grid-template-columns:.72fr 1.55fr 1fr 1fr .72fr;gap:10px;
  padding:8px 2px 6px;font-family:var(--font-mono);font-size:12px;font-weight:800;
  letter-spacing:.22em;color:var(--text);text-transform:uppercase;
}
.strong-row-label{
  display:flex;align-items:center;min-height:42px;font-size:20px;font-weight:800;
}
.strong-row-label.warm{color:var(--amber);}
.strong-row-label.done{color:var(--text);}
.strong-prev{
  min-height:42px;display:flex;align-items:center;color:var(--text-faint);font-size:18px;
  font-variant-numeric:tabular-nums;white-space:nowrap;
}
.st-key-strong_logger [class*="st-key-strong_setrow_"]{
  padding:2px 0!important;
}
.st-key-strong_logger [class*="st-key-strong_setrow_"] [data-testid="stHorizontalBlock"]{
  flex-wrap:nowrap!important;align-items:center!important;
}
.st-key-strong_logger [class*="st-key-strong_setrow_"] [data-testid="stHorizontalBlock"] > div{
  flex:0 0 auto!important;width:auto!important;min-width:0!important;
}
.st-key-strong_logger [class*="st-key-strong_setrow_"] .strong-prev{
  min-width:86px;
}
.st-key-strong_logger [class*="st-key-strong_setrow_"] div[data-testid="stTextInput"]{
  width:74px!important;min-width:58px!important;
}
.st-key-strong_logger [class*="st-key-kg_txt_"],
.st-key-strong_logger [class*="st-key-reps_txt_"]{
  width:74px!important;min-width:58px!important;flex:0 0 74px!important;
}
.st-key-strong_logger [class*="st-key-strong_setrow_"] div.stButton > button{
  min-width:40px!important;padding-left:0!important;padding-right:0!important;
}
.strong-done-strip{
  height:5px;margin:-2px 0 6px;border-radius:999px;background:rgba(128,203,196,.45);
}
.strong-rest{
  display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);
  align-items:center;gap:12px;margin:4px 0 10px;color:var(--accent);
  font-size:20px;font-variant-numeric:tabular-nums;
}
.strong-rest::before,.strong-rest::after{
  content:"";height:4px;border-radius:999px;background:rgba(128,203,196,.20);
}
.strong-rest.active::before{background:var(--accent);}
.strong-help{color:var(--text-faint);font-size:12px;margin-top:4px;}
.strong-actions{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:0 22px 22px;}
.st-key-strong_logger div[data-testid="stNumberInput"] input{
  background:var(--surface-3);color:var(--text);border:0;border-radius:8px;min-height:42px;
  text-align:center;font-size:22px;font-weight:650;font-variant-numeric:tabular-nums;
}
.st-key-strong_logger div[data-testid="stTextInput"] input{
  background:var(--surface-3);color:var(--text);border:1px solid rgba(255,255,255,.08);border-radius:8px;
}
.st-key-strong_logger div.stButton > button{
  min-height:42px;border-radius:10px;border-color:rgba(255,255,255,.08);
  background:var(--surface-3);color:var(--accent);font-weight:800;
}
.st-key-strong_logger div.stButton > button[kind="primary"]{
  background:var(--accent);border-color:var(--accent);color:var(--accent-ink);
}
@media (max-width:640px){
  .block-container{padding-left:.45rem;padding-right:.45rem;}
  .st-key-strong_logger{border-left:0;border-right:0;border-radius:0;margin-left:-.45rem!important;margin-right:-.45rem!important;padding-left:14px!important;padding-right:14px!important;}
  .st-key-strong_topbar{margin-left:-14px!important;margin-right:-14px!important;padding:8px 12px!important;}
  .strong-top{grid-template-columns:42px 48px 1fr 92px;padding:8px 12px;}
  .strong-top .timer{font-size:18px}.strong-finish{font-size:17px}
  .strong-head,.strong-section{padding-left:14px;padding-right:14px;}
  .strong-stats{padding-left:14px;padding-right:14px;}
  .strong-title{font-size:25px}.strong-duration{font-size:22px}
  .strong-ex-title{font-size:20px}
  .strong-col-head{grid-template-columns:.62fr 1.4fr .86fr .86fr .62fr;gap:6px;font-size:10px;}
  .strong-prev{font-size:15px}.strong-row-label{font-size:18px}
  .st-key-strong_logger div[data-testid="stNumberInput"] input{font-size:19px;min-height:40px;}
  .st-key-strong_logger [class*="st-key-strong_setrow_"] .strong-prev{min-width:28px;font-size:13px;}
  .st-key-strong_logger [class*="st-key-strong_setrow_"] div[data-testid="stTextInput"]{width:44px!important;min-width:44px!important;}
  .st-key-strong_logger [class*="st-key-kg_txt_"],
  .st-key-strong_logger [class*="st-key-reps_txt_"]{width:44px!important;min-width:44px!important;flex-basis:44px!important;}
  .st-key-strong_logger [class*="st-key-strong_setrow_"] div.stButton > button{min-width:36px!important;width:36px!important;}
}
</style>
""", unsafe_allow_html=True)

db.init_db()


@st.cache_data(ttl=60)
def load_catalog():
    return db.load_exercises_df()


def coach_memory_digest():
    return analysis.build_coach_memory_digest(db.load_memory_df())


def today_str():
    return date.today().isoformat()


def parse_dt(value):
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return datetime.now()


def duration_label(started_at: str) -> str:
    seconds = max(0, int((datetime.now() - parse_dt(started_at)).total_seconds()))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def render_live_timer_js():
    """Tick every `[data-stopwatch]` element in the main document once a second,
    entirely client-side, so the workout clock stays live without server reruns.
    Runs in a 0-height component iframe but updates the parent DOM (same origin)."""
    st.components.v1.html(
        """
        <script>
        (function(){
          const doc = window.parent.document;
          const pad = n => String(n).padStart(2, '0');
          function fmt(s){
            s = Math.max(0, Math.floor(s));
            const h = Math.floor(s / 3600);
            const m = Math.floor((s % 3600) / 60);
            const sec = s % 60;
            return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
          }
          function tick(){
            doc.querySelectorAll('[data-stopwatch]').forEach(el => {
              const start = parseInt(el.getAttribute('data-start'), 10);
              if (!start) return;
              el.textContent = fmt((Date.now() - start) / 1000);
            });
          }
          // Clear any interval from a prior rerun so they don't stack.
          if (window.parent.__strongTimer) clearInterval(window.parent.__strongTimer);
          window.parent.__strongTimer = setInterval(tick, 1000);
          tick();
        })();
        </script>
        """,
        height=0,
    )


def set_previous_label(prev: list[dict], index: int) -> str:
    if index >= len(prev):
        return "—"
    p = prev[index]
    try:
        weight = float(p["weight_kg"])
        reps = int(p["reps"])
    except (KeyError, TypeError, ValueError):
        return "—"
    return f"{weight:g} kg × {reps}"


def ensure_active_shape(active: dict):
    """Backfill active workout state as the UI evolves across reruns."""
    active.setdefault("started_at", datetime.now().isoformat(timespec="seconds"))
    active.setdefault("source", "app")
    active.setdefault("workout_type", "strength")
    active.setdefault("session_rpe", None)
    active.setdefault("exercises", [])
    for pos, ex in enumerate(active["exercises"]):
        ex.setdefault("position", pos)
        ex.setdefault("sets", [])
        ex.setdefault("note", "")
        for idx, stt in enumerate(ex["sets"]):
            stt.setdefault("set_id", str(uuid.uuid4()))
            stt.setdefault("set_index", idx + 1)
            stt.setdefault("side", "left" if ex.get("is_unilateral") else "both")
            stt.setdefault("reps", 5)
            stt.setdefault("weight_kg", 20.0)
            stt.setdefault("rpe", None)
            stt.setdefault("is_warmup", 0)
            stt.setdefault("completed", 0)


def mark_rest_started(active: dict, set_id: str):
    st.session_state["strong_rest"] = {
        "session_id": active["session_id"],
        "set_id": set_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "target_s": 120,
    }


def rest_state(active: dict) -> dict | None:
    rest = st.session_state.get("strong_rest")
    if not rest or rest.get("session_id") != active.get("session_id"):
        return None
    elapsed = max(0, int((datetime.now() - parse_dt(rest.get("started_at"))).total_seconds()))
    target = int(rest.get("target_s") or 120)
    remaining = max(0, target - elapsed)
    rest["elapsed_s"] = elapsed
    rest["remaining_s"] = remaining
    rest["progress"] = min(1.0, elapsed / target) if target else 0.0
    return rest


def rest_label(seconds: int) -> str:
    minutes, sec = divmod(max(0, int(seconds)), 60)
    return f"{minutes}:{sec:02d}"


def finish_active_workout(active: dict):
    snap = todays_readiness_snapshot(active["date"])
    _verdict, _readiness = todays_recovery_verdict(active["date"])
    db.upsert_strength_session({
        "session_id": active["session_id"], "date": active["date"],
        "started_at": active["started_at"],
        "ended_at": datetime.now().isoformat(timespec="seconds"),
        "name": active["name"], "bodyweight_kg": active.get("bodyweight_kg"),
        "routine_id": active.get("routine_id"),
        "source": active.get("source") or "app",
        "workout_type": active.get("workout_type") or "strength",
        "session_rpe": active.get("session_rpe"),
        "recovery_score": _readiness.get("value"),
        "recovery_zone": _readiness.get("zone"),
        **snap,
        "garmin_readiness_score": snap.get("garmin_readiness_score") or snap.get("readiness_score"),
    })
    for ex in active["exercises"]:
        for stt in ex["sets"]:
            db.upsert_strength_set({
                "set_id": stt["set_id"], "session_id": active["session_id"],
                "exercise_id": ex["exercise_id"], "position": ex["position"],
                "set_index": stt["set_index"], "side": stt["side"],
                "reps": stt["reps"], "weight_kg": stt["weight_kg"],
                "rpe": stt.get("rpe"), "is_warmup": stt["is_warmup"],
                "completed": stt["completed"],
            })
    st.session_state.pop("active", None)
    st.session_state.pop("strong_rest", None)


def workout_completion_status(active: dict) -> dict:
    working = 0
    completed = 0
    for ex in active.get("exercises", []):
        for stt in ex.get("sets", []):
            if stt.get("is_warmup"):
                continue
            working += 1
            completed += int(bool(int(stt.get("completed") or 0)))
    return {
        "working_sets": working,
        "completed_working_sets": completed,
        "pending_working_sets": max(0, working - completed),
    }


def resolve_bodyweight(day: str):
    """Bodyweight for `day` from body_metrics, forward-filled from the most
    recent prior weigh-in."""
    bm = db.load_body_metrics_df()
    if bm.empty:
        return None
    bm = bm.copy()
    bm["date"] = bm["date"].astype(str).str[:10]
    bm = bm[bm["date"] <= day].sort_values("date")
    if bm.empty:
        return None
    val = bm.iloc[-1]["weight_kg"]
    return None if pd.isna(val) else float(val)


def todays_readiness_snapshot(day: str) -> dict:
    daily = analysis.enrich_daily(db.load_daily_df())
    if not daily.empty:
        daily = analysis.compute_acwr(db.load_activities_df(), daily)
    if daily.empty:
        return analysis.readiness_snapshot_from_daily(None)
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    match = daily[daily["date"].dt.strftime("%Y-%m-%d") == day]
    row = match.iloc[-1] if not match.empty else None
    return analysis.readiness_snapshot_from_daily(row)


def todays_recovery_verdict(day: str) -> tuple[dict, dict]:
    daily = analysis.enrich_daily(db.load_daily_df())
    readiness = analysis.recovery_readiness(daily, as_of=day)
    return analysis.readiness_verdict(readiness), readiness


@st.cache_data(ttl=30)
def load_strength_sessions_with_context():
    sessions = db.load_strength_sessions_df()
    if sessions.empty:
        return sessions
    acts = db.load_activities_df()
    daily = analysis.enrich_daily(db.load_daily_df())
    if not daily.empty:
        daily = analysis.compute_acwr(acts, daily)
    merged = analysis.merge_strength_session_context(sessions, acts, daily)
    persist_strength_session_context(sessions, merged)
    return merged


def _missing_context_value(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


def persist_strength_session_context(original, merged):
    """Persist compact Garmin/daily context discovered during merge.

    This only fills missing session columns; user/import-provided values win.
    """
    if original is None or merged is None or original.empty or merged.empty:
        return
    if "session_id" not in original or "session_id" not in merged:
        return
    backfill_cols = [
        "garmin_activity_id", "garmin_readiness_score",
        "readiness_score", "readiness_level", "hrv_status",
        "hrv_overnight_avg", "body_battery_start", "sleep_score",
        "resting_hr", "acwr", "recovery_score", "recovery_zone",
    ]
    original_by_session = {
        row["session_id"]: row
        for _, row in original.iterrows()
        if not _missing_context_value(row.get("session_id"))
    }
    for _, row in merged.iterrows():
        sid = row.get("session_id")
        if _missing_context_value(sid):
            continue
        prior = original_by_session.get(sid)
        if prior is None:
            continue
        record = {"session_id": sid}
        for col in backfill_cols:
            if col not in merged:
                continue
            value = row.get(col)
            if _missing_context_value(value):
                continue
            if col in original and not _missing_context_value(prior.get(col)):
                continue
            record[col] = value.item() if hasattr(value, "item") else value
        if len(record) > 1:
            db.upsert_strength_session(record)


@st.cache_data(ttl=30)
def hist_sessions_for_note():
    return load_strength_sessions_with_context()


@st.cache_data(ttl=30)
def hist_sets_for_note():
    return db.load_strength_sets_df()


def active_to_frames(active: dict):
    """Build (sessions_df, sets_df) from in-memory active state for live totals."""
    sessions = pd.DataFrame([{
        "session_id": active["session_id"], "date": active["date"],
        "bodyweight_kg": active.get("bodyweight_kg") or 0.0,
    }])
    rows = []
    for ex in active["exercises"]:
        for s in ex["sets"]:
            rows.append({
                "set_id": s["set_id"], "session_id": active["session_id"],
                "exercise_id": ex["exercise_id"], "position": ex["position"],
                "set_index": s["set_index"], "side": s["side"],
                "reps": s["reps"], "weight_kg": s["weight_kg"],
                "rpe": s.get("rpe"), "is_warmup": s["is_warmup"],
                "completed": s["completed"],
            })
    sets = pd.DataFrame(rows)
    return sessions, sets


def routine_to_exercises(routine_id: str):
    """Build active-state exercise entries from a saved routine."""
    rex = db.load_routine_exercises_df()
    rex = rex[rex["routine_id"] == routine_id].sort_values("position")
    cat = db.load_exercises_df()
    out = []
    for pos, (_, r) in enumerate(rex.iterrows()):
        m = cat[cat["exercise_id"] == r["exercise_id"]]
        if m.empty:
            continue
        ex = m.iloc[0]
        sets = []
        target_sets = r.get("target_sets")
        try:
            target_sets = int(target_sets) if pd.notna(target_sets) else 0
        except (TypeError, ValueError):
            target_sets = 0
        target_reps = r.get("target_reps")
        target_weight = r.get("target_weight")
        for idx in range(max(0, target_sets)):
            sets.append({
                "set_id": str(uuid.uuid4()),
                "set_index": idx + 1,
                "side": "left" if int(ex["is_unilateral"]) else "both",
                "reps": int(target_reps) if pd.notna(target_reps) else 5,
                "weight_kg": float(target_weight) if pd.notna(target_weight) else 20.0,
                "rpe": None,
                "is_warmup": 0,
                "completed": 0,
            })
        out.append({
            "position": pos,
            "exercise_id": ex["exercise_id"],
            "name": ex["name"],
            "is_unilateral": int(ex["is_unilateral"]),
            "is_bodyweight": int(ex["is_bodyweight"]),
            "sets": sets,
        })
    return out


def save_active_as_routine(active: dict, routine_name: str) -> str:
    """Persist the active workout's exercises as a reusable routine."""
    rid = str(uuid.uuid4())
    db.upsert_routine({"routine_id": rid, "name": routine_name})
    for pos, ex in enumerate(active["exercises"]):
        work = [s for s in ex["sets"] if not s["is_warmup"]]
        first = work[0] if work else (ex["sets"][0] if ex["sets"] else None)
        db.upsert_routine_exercise({
            "routine_id": rid, "position": pos,
            "exercise_id": ex["exercise_id"],
            "target_sets": (len(work) or len(ex["sets"]) or None),
            "target_reps": (first["reps"] if first else None),
            "target_weight": (first["weight_kg"] if first else None),
        })
    return rid


def fmt_num(value, digits: int = 0, suffix: str = "") -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "-"
        n = float(value)
    except (TypeError, ValueError):
        return "-"
    text = f"{n:,.0f}" if digits == 0 else f"{n:,.{digits}f}"
    return f"{text}{suffix}"


def fmt_signed(value, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "-"
        n = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{n:+.{digits}f}{suffix}"


def fmt_recovery_label(value) -> str:
    text = "" if value is None else str(value).strip()
    if not text or text.lower() in {"nan", "none", "not tagged"}:
        return "Not tagged"
    return text.replace("_", " ").title()


def strength_kpi(label: str, value: str, sub: str = "") -> str:
    title = f"{label}: {value}"
    if sub:
        title = f"{title} ({sub})"
    return (
        f"<div class='strength-kpi' title='{html.escape(title, quote=True)}'>"
        f"<div class='lab'>{html.escape(label)}</div>"
        f"<div class='val'>{html.escape(value)}</div>"
        f"<div class='sub'>{html.escape(sub)}</div></div>"
    )


def strength_trend_chart(rows: list[dict]) -> go.Figure:
    fig = go.Figure()
    data = pd.DataFrame(rows or [])
    if data.empty:
        return fig
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date"]).sort_values("date")
    if data.empty:
        return fig
    data = data.reset_index(drop=True)
    data["x_pos"] = list(range(len(data)))
    date_label_fmt = "%b %-d '%y" if data["date"].dt.year.nunique() > 1 else "%b %-d"
    data["date_label"] = data["date"].dt.strftime(date_label_fmt)
    data["date_full"] = data["date"].dt.strftime("%Y-%m-%d")
    data["name"] = data.get("name", "Workout")
    custom = data[["date_full", "name"]].fillna("").to_numpy()
    x_range = [-0.5, max(0.5, len(data) - 0.5)]
    fig.add_trace(go.Bar(
        x=data["x_pos"],
        y=pd.to_numeric(data["total_volume_kg"], errors="coerce"),
        name="Volume",
        marker_color=cockpit.ACCENT,
        opacity=0.68,
        width=0.42,
        yaxis="y",
        customdata=custom,
        hovertemplate="%{customdata[0]}<br>%{customdata[1]}<br>Volume %{y:,.0f} kg<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=data["x_pos"],
        y=pd.to_numeric(data["top_est_1rm_kg"], errors="coerce"),
        name="Top est 1RM",
        mode="lines+markers",
        line=dict(color=cockpit.SERIES2, width=2),
        marker=dict(size=7, color=cockpit.SERIES2, line=dict(width=1, color=cockpit.BG)),
        yaxis="y2",
        connectgaps=False,
        customdata=custom,
        hovertemplate="%{customdata[0]}<br>%{customdata[1]}<br>Top est 1RM %{y:.1f} kg<extra></extra>",
    ))
    fig.update_layout(
        height=340,
        margin=dict(l=44, r=44, t=44, b=34),
        paper_bgcolor=cockpit.BG,
        plot_bgcolor=cockpit.BG,
        font=dict(family="Archivo, sans-serif", color=cockpit.TEXT),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.04, xanchor="center", x=0.5,
            bgcolor="rgba(0,0,0,0)", font=dict(size=12)
        ),
        xaxis=dict(
            tickmode="array", tickvals=list(data["x_pos"]), ticktext=list(data["date_label"]),
            range=x_range, gridcolor="rgba(255,255,255,.04)",
            tickfont=dict(color=cockpit.TEXT_FAINT, size=10), fixedrange=True,
        ),
        yaxis=dict(
            title=None, gridcolor="rgba(255,255,255,.06)",
            tickfont=dict(color=cockpit.TEXT_FAINT, size=10), fixedrange=True,
        ),
        yaxis2=dict(
            title=None, overlaying="y", side="right", showgrid=False,
            tickfont=dict(color=cockpit.TEXT_FAINT, size=10), fixedrange=True,
        ),
    )
    return fig


def weekly_strength_load_chart(rows, metric: str = "total_volume_kg") -> go.Figure:
    fig = go.Figure()
    data = pd.DataFrame(rows or [])
    if data.empty:
        return fig
    data["week_start"] = pd.to_datetime(data["week_start"], errors="coerce")
    data = data.dropna(subset=["week_start"]).sort_values(["week_start", "group"])
    if data.empty:
        return fig
    metric = metric if metric in data.columns else "total_volume_kg"
    data[metric] = pd.to_numeric(data[metric], errors="coerce").fillna(0)
    preferred = ["Push", "Pull", "Squat", "Hinge", "Core", "Other"]
    groups = [g for g in preferred if g in set(data["group"])]
    groups.extend(sorted(g for g in data["group"].dropna().unique() if g not in groups))
    colors = {
        "Push": cockpit.ACCENT,
        "Pull": cockpit.SERIES2,
        "Squat": cockpit.AMBER,
        "Hinge": "#8FA7FF",
        "Core": "#D98BD2",
        "Other": cockpit.TEXT_FAINT,
    }
    fallback = ["#B7C3D0", "#73BBA3", "#E2A6A1", "#C7A7F2", "#D7C27C", "#9FB6D8"]
    for idx, group in enumerate(groups):
        sub = data[data["group"] == group]
        fig.add_trace(go.Bar(
            x=sub["week_start"],
            y=sub[metric],
            name=str(group),
            marker_color=colors.get(group, fallback[idx % len(fallback)]),
            hovertemplate="%{x|%b %d}<br>%{y:,.0f}<extra>" + html.escape(str(group)) + "</extra>",
        ))
    ytitle = "kg volume" if metric == "total_volume_kg" else "working sets"
    fig.update_layout(
        height=320,
        barmode="stack",
        margin=dict(l=42, r=20, t=18, b=36),
        paper_bgcolor=cockpit.BG,
        plot_bgcolor=cockpit.BG,
        font=dict(family="Archivo, sans-serif", color=cockpit.TEXT),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor="rgba(255,255,255,.04)", tickfont=dict(color=cockpit.TEXT_FAINT, size=10)),
        yaxis=dict(title=ytitle, gridcolor="rgba(255,255,255,.06)", tickfont=dict(color=cockpit.TEXT_FAINT, size=10)),
    )
    return fig


def strength_feedback_context(overview: dict, strength_summary: dict) -> dict:
    latest = dict((overview or {}).get("latest_session") or {})
    latest.pop("session_id", None)
    latest.pop("garmin_activity_id", None)
    latest_summary = dict((overview or {}).get("latest_summary") or {})
    latest_summary.pop("session_id", None)
    exercise_rows = []
    for row in (overview or {}).get("exercise_rows") or []:
        item = dict(row)
        item.pop("exercise_id", None)
        exercise_rows.append(item)
    trend_rows = []
    for row in (overview or {}).get("trend_rows") or []:
        item = dict(row)
        item.pop("session_id", None)
        trend_rows.append(item)
    return {
        "latest_session": latest,
        "latest_summary": latest_summary,
        "latest_exercises": exercise_rows,
        "trend": (overview or {}).get("trend") or {},
        "trend_rows": trend_rows,
        "recent_prs": (overview or {}).get("recent_prs") or [],
        "strength_summary": strength_summary or {},
    }


def strength_memory_context(
    sessions,
    sets,
    catalog,
    bodyweight,
    verdict=None,
    overview: dict | None = None,
    strength_summary: dict | None = None,
) -> dict:
    overview = overview or analysis.compute_strength_recent_overview(
        sessions, sets, catalog, config.ONE_RM_FORMULA
    )
    strength_summary = strength_summary or analysis.summarize_strength(
        sessions,
        sets,
        catalog,
        db.load_profile(),
        bodyweight,
        formula=config.ONE_RM_FORMULA,
        verdict=verdict,
    )
    momentum = analysis.compute_strength_momentum_flags(
        sessions, sets, catalog, formula=config.ONE_RM_FORMULA
    )
    leaderboard = analysis.compute_strength_best_set_leaderboard(
        sessions, sets, catalog, formula=config.ONE_RM_FORMULA
    )
    weekly = analysis.compute_weekly_strength_load(
        sessions, sets, catalog, formula=config.ONE_RM_FORMULA, weeks=8
    )
    leaders = []
    if not leaderboard.empty:
        for row in leaderboard.head(8).to_dict("records"):
            item = dict(row)
            item.pop("exercise_id", None)
            leaders.append(item)
    return {
        "strength_summary": strength_summary or {},
        "recent_session": strength_feedback_context(overview, strength_summary),
        "momentum": _compact_strength_momentum(momentum),
        "best_set_leaders": leaders,
        "weekly_load": weekly.to_dict("records") if not weekly.empty else [],
    }


def _compact_strength_momentum(momentum: dict) -> dict:
    out = {
        "status": (momentum or {}).get("status"),
        "as_of": (momentum or {}).get("as_of"),
        "summary": (momentum or {}).get("summary") or {},
        "categories": {},
    }
    for key, rows in ((momentum or {}).get("categories") or {}).items():
        compact = []
        for row in (rows or [])[:6]:
            item = dict(row)
            item.pop("exercise_id", None)
            compact.append(item)
        out["categories"][key] = compact
    return out


def strength_feedback_preview(feedback: str, max_chars: int = 420) -> str:
    text = str(feedback or "").strip()
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines()]
    body = []
    for line in lines:
        if not line:
            if body:
                break
            continue
        if line.startswith("## "):
            if body:
                break
            continue
        body.append(line.lstrip("- ").strip())
        if len(" ".join(body)) >= max_chars:
            break
    preview = " ".join(body).strip() or text
    if len(preview) > max_chars:
        preview = preview[: max_chars - 1].rstrip() + "..."
    return preview


def render_strength_ai_feedback(overview: dict, strength_summary: dict, coach_memory: dict | None = None):
    latest = (overview or {}).get("latest_session") or {}
    feedback_key = f"strength_feedback_{latest.get('session_id')}"
    with st.container(key="strength_ai_feedback", border=True):
        with st.container(key="strength_ai_header"):
            head, action_1, action_2 = st.columns([6, 1.15, 1.15], vertical_alignment="center")
            with head:
                st.markdown(
                    "<div class='strength-ai-title'>AI strength feedback</div>"
                    "<div class='strength-ai-meta'>latest session overview</div>",
                    unsafe_allow_html=True,
                )
            generate = action_1.button(
                "Generate",
                icon=":material/auto_awesome:",
                disabled=not bool(config.ANTHROPIC_API_KEY),
                key=f"{feedback_key}_generate",
                width="content",
            )
            refresh = action_2.button(
                "Refresh",
                icon=":material/refresh:",
                disabled=not bool(config.ANTHROPIC_API_KEY),
                key=f"{feedback_key}_refresh",
                width="content",
            )
        if refresh:
            st.session_state.pop(feedback_key, None)
            generate = True
        if not config.ANTHROPIC_API_KEY:
            st.caption("Set `ANTHROPIC_API_KEY` in .env to generate strength feedback.")
        elif generate:
            with st.spinner("Generating strength feedback..."):
                st.session_state[feedback_key] = ai.strength_overview_feedback(
                    strength_feedback_context(overview, strength_summary),
                    coach_memory=coach_memory,
                )
        feedback = st.session_state.get(feedback_key)
        if feedback:
            preview = html.escape(strength_feedback_preview(feedback))
            st.markdown(
                f"<div class='strength-feedback-preview'>{preview}</div>",
                unsafe_allow_html=True,
            )
            with st.expander("Read full AI feedback"):
                st.markdown(feedback)
        elif config.ANTHROPIC_API_KEY:
            st.markdown(
                "<div class='strength-feedback-empty'>Click Generate to create feedback for this session.</div>",
                unsafe_allow_html=True,
            )


def render_strength_memory_panel(strength_context: dict, existing_memory: dict | None = None):
    with st.container(border=True):
        head, action = st.columns([5, 1.4], vertical_alignment="center")
        with head:
            st.markdown(
                "<div class='strength-ai-title'>Coach memory</div>"
                "<div class='strength-ai-meta'>strength patterns worth remembering</div>",
                unsafe_allow_html=True,
            )
        suggest = action.button(
            "Suggest",
            disabled=not bool(config.ANTHROPIC_API_KEY),
            key="strength_memory_suggest",
            width="stretch",
        )
        if not config.ANTHROPIC_API_KEY:
            st.caption("Set `ANTHROPIC_API_KEY` in .env to suggest strength memories.")
            return
        if suggest:
            with st.spinner("Looking for durable strength memories..."):
                st.session_state["strength_mem_candidates"] = ai.suggest_memories(
                    {},
                    strength_context,
                    existing_memory or {},
                )
        candidates = st.session_state.get("strength_mem_candidates", [])
        if not candidates:
            st.caption("Click Suggest to find strength facts the coach should remember.")
            return
        for idx, cand in enumerate(candidates):
            with st.container(border=True):
                st.markdown(f"**{cand['category']}** - {cand['text']}")
                if cand.get("rationale"):
                    st.caption(cand["rationale"])
                cols = st.columns([1, 1, 4])
                with cols[0]:
                    if st.button("Approve", key=f"strength_mem_approve_{idx}", width="stretch"):
                        rec = {"category": cand["category"], "text": cand["text"], "source": "ai"}
                        for key in ("confidence", "target_date", "body_part"):
                            if cand.get(key):
                                rec[key] = cand[key]
                        db.add_memory(rec)
                        st.session_state["strength_mem_candidates"] = [
                            c for j, c in enumerate(candidates) if j != idx
                        ]
                        st.rerun()
                with cols[1]:
                    if st.button("Reject", key=f"strength_mem_reject_{idx}", width="stretch"):
                        st.session_state["strength_mem_candidates"] = [
                            c for j, c in enumerate(candidates) if j != idx
                        ]
                        st.rerun()


def render_strength_overview(overview: dict, strength_summary: dict, coach_memory: dict | None = None):
    if (overview or {}).get("status") != "ok":
        st.info("Log a strength workout to build the recent-session cockpit.")
        return

    latest = overview["latest_session"]
    summ = overview.get("latest_summary") or {}
    trend = overview.get("trend") or {}
    exercises = overview.get("exercise_rows") or []
    prs = overview.get("recent_prs") or []
    name = html.escape(latest.get("name") or "Workout")
    date_txt = html.escape(latest.get("date") or "")
    duration = fmt_num(latest.get("duration_min"), 0, " min") if latest.get("duration_min") is not None else "-"
    recovery = fmt_recovery_label(latest.get("recovery_zone") or latest.get("readiness_level"))
    recovery_score = fmt_num(latest.get("recovery_score"), 0)
    recovery_sub = f"score {recovery_score}" if recovery_score != "-" else "no score"
    kpis = [
        strength_kpi("Volume", fmt_num(summ.get("total_volume_kg"), 0, " kg"), fmt_signed(trend.get("volume_delta_pct"), 1, "% vs prior")),
        strength_kpi("Working sets", fmt_num(summ.get("working_sets"), 0), fmt_signed(trend.get("working_sets_delta"), 1, " sets")),
        strength_kpi("Top est 1RM", fmt_num(summ.get("top_est_1rm_kg"), 1, " kg"), fmt_signed(trend.get("top_est_1rm_delta_kg"), 1, " kg")),
        strength_kpi("Recovery", recovery, recovery_sub),
    ]

    st.markdown(
        f"""
        <div class='strength-overview'>
          <div class='strength-hero'>
            <div>
              <div class='meta'>Latest completed session</div>
              <h2>{name}</h2>
              <div class='sub'>{date_txt} · {html.escape(duration)} · {len(exercises)} exercises tracked</div>
            </div>
            <div class='strength-kpi-grid'>{''.join(kpis)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_strength_ai_feedback(overview, strength_summary, coach_memory=coach_memory)

    left, right = st.columns([1, 1], gap="medium")
    with left:
        with st.container(key="strength_trend_card", border=True):
            st.markdown("#### Session trend")
            rows = overview.get("trend_rows") or []
            if rows:
                st.plotly_chart(strength_trend_chart(rows), width="stretch")
                basis = trend.get("basis")
                if basis:
                    st.caption(basis)
            else:
                st.caption("Log a few sessions to see volume and top-estimated-1RM trends.")

        with st.container(border=True):
            st.markdown("#### Latest exercises")
            if not exercises:
                st.caption("No completed working sets were saved for the latest session.")
            else:
                table_rows = [
                    "<div class='strength-row head'><span>Exercise</span><span>Sets</span><span>Volume</span><span>Best</span><span>PR</span></div>"
                ]
                for row in exercises[:8]:
                    pr = "<span class='strength-pr'>PR</span>" if row.get("is_pr") else ""
                    table_rows.append(
                        "<div class='strength-row'>"
                        f"<span class='name'>{html.escape(str(row.get('name') or 'Exercise'))}</span>"
                        f"<span class='num'>{fmt_num(row.get('working_sets'), 0)}</span>"
                        f"<span class='num'>{fmt_num(row.get('volume_kg'), 0, ' kg')}</span>"
                        f"<span class='num'>{html.escape(str(row.get('best_set') or '-'))}</span>"
                        f"<span>{pr}</span></div>"
                    )
                st.markdown("<div class='strength-table'>" + "".join(table_rows) + "</div>", unsafe_allow_html=True)

    with right:
        with st.container(key="strength_pr_card", border=True):
            st.markdown("#### Recent PRs")
            latest_prs = [p for p in prs if p.get("latest_session")]
            visible_prs = latest_prs or prs[-5:]
            if visible_prs:
                pr_rows = []
                for pr in reversed(visible_prs[-5:]):
                    marker = "latest" if pr.get("latest_session") else pr.get("date")
                    exercise = str(pr.get("exercise") or "Exercise")
                    pr_rows.append(
                        "<div class='strength-pr-row'>"
                        f"<div class='strength-pr-name' title='{html.escape(exercise, quote=True)}'>{html.escape(exercise)}</div>"
                        f"<div class='strength-pr-value'>{fmt_num(pr.get('est_1rm_kg'), 1, ' kg')}</div>"
                        f"<div class='strength-pr-date'>{html.escape(str(marker))}</div>"
                        "</div>"
                    )
                st.markdown("<div class='strength-pr-list'>" + "".join(pr_rows) + "</div>", unsafe_allow_html=True)
            else:
                st.caption("No PRs detected yet.")

        with st.container(border=True):
            st.markdown("#### Strength profile")
            standards = (strength_summary or {}).get("standards") or {}
            recent = (strength_summary or {}).get("recent") or {}
            readiness = (strength_summary or {}).get("readiness_link") or {}
            if standards.get("overall"):
                st.metric("Standards", standards["overall"].get("level"), f"~{standards['overall'].get('percentile')} pct")
            else:
                st.caption(f"Standards: {standards.get('status', 'learning')}")
            st.metric("28d tonnage", fmt_num(recent.get("tonnage_kg"), 0, " kg"), f"{recent.get('sessions_per_week', 0)} sessions/wk")
            st.caption(readiness.get("insight") or f"Readiness link: {readiness.get('status', 'learning')}")


def render_history_exercise_rollup(rows):
    if rows is None or len(rows) == 0:
        st.caption("No completed working sets for this session.")
        return
    table_rows = [
        "<div class='strength-history-row head'>"
        "<span>Exercise</span><span>Sets</span><span>Volume</span>"
        "<span>Best</span><span>Est 1RM</span><span>PR</span></div>"
    ]
    for row in rows:
        pr = "<span class='strength-pr'>PR</span>" if row.get("is_pr") else ""
        table_rows.append(
            "<div class='strength-history-row'>"
            f"<span class='name'>{html.escape(str(row.get('name') or 'Exercise'))}</span>"
            f"<span class='num'>{fmt_num(row.get('working_sets'), 0)}</span>"
            f"<span class='num'>{fmt_num(row.get('volume_kg'), 0, ' kg')}</span>"
            f"<span class='num'>{html.escape(str(row.get('best_set') or '-'))}</span>"
            f"<span class='num'>{fmt_num(row.get('best_est_1rm_kg'), 1, ' kg')}</span>"
            f"<span>{pr}</span></div>"
        )
    st.markdown(
        "<div class='strength-history-rollup'>" + "".join(table_rows) + "</div>",
        unsafe_allow_html=True,
    )


def render_strength_momentum_panel(momentum: dict):
    momentum = momentum or {}
    if momentum.get("status") in (None, "no_data"):
        st.caption("Log completed working sets to classify exercise momentum.")
        return
    categories = momentum.get("categories") or {}
    summary = momentum.get("summary") or {}
    order = [
        ("progressing", "Progressing", cockpit.SERIES2),
        ("flat", "Flat", cockpit.AMBER),
        ("regressing", "Regressing", cockpit.RED),
        ("undertrained", "Undertrained areas", cockpit.TEXT_FAINT),
    ]
    count_html = []
    for key, label, color in order:
        count_html.append(
            "<div class='strength-momentum-count'>"
            f"<div class='lab' style='color:{color}'>{html.escape(label)}</div>"
            f"<div class='val'>{int(summary.get(key) or 0)}</div></div>"
        )
    st.markdown(
        "<div class='strength-momentum-counts'>" + "".join(count_html) + "</div>",
        unsafe_allow_html=True,
    )
    if momentum.get("status") == "learning":
        st.caption("No clear momentum flags yet.")
        return
    for key, label, color in order:
        items = categories.get(key) or []
        if not items:
            continue
        rows = [
            f"<div class='strength-momentum-title' style='color:{color}'>{html.escape(label)}</div>"
        ]
        for item in items[:6]:
            if key == "undertrained":
                change = f"{int(item.get('days_since') or 0)}d"
                metric = f"{int(item.get('recent_working_sets') or 0)} sets"
            elif key == "flat":
                change = fmt_num(item.get("delta_pct"), 1, "%")
                metric = fmt_num(item.get("last_best_est_1rm_kg"), 1, " kg")
            else:
                change = fmt_signed(item.get("delta_pct"), 1, "%")
                metric = fmt_num(item.get("last_best_est_1rm_kg"), 1, " kg")
            rows.append(
                "<div class='strength-momentum-row'>"
                f"<span class='name'>{html.escape(str(item.get('name') or 'Exercise'))}</span>"
                f"<span class='num'>{html.escape(metric)}</span>"
                f"<span class='num' style='color:{color}'>{html.escape(change)}</span>"
                f"<span class='note'>{html.escape(str(item.get('note') or ''))}</span>"
                "</div>"
            )
        st.markdown(
            "<div class='strength-momentum-section'>" + "".join(rows) + "</div>",
            unsafe_allow_html=True,
        )
    if momentum.get("as_of"):
        st.caption(f"Momentum as of {momentum['as_of']}.")


def render_best_set_leaderboard(rows, limit: int = 12):
    if rows is None or len(rows) == 0:
        st.caption("Log completed working sets to build the best-set leaderboard.")
        return
    visible = list(rows)[:max(1, int(limit or 12))]
    table_rows = [
        "<div class='strength-leaderboard-row head'>"
        "<span>#</span><span>Exercise</span><span>Top 1RM</span>"
        "<span>Best set</span><span>Heaviest</span><span>Recent</span><span>Last PR</span></div>"
    ]
    for idx, row in enumerate(visible, start=1):
        table_rows.append(
            "<div class='strength-leaderboard-row'>"
            f"<span class='rank'>{idx}</span>"
            f"<span class='name'>{html.escape(str(row.get('name') or 'Exercise'))}</span>"
            f"<span class='num'>{fmt_num(row.get('best_est_1rm_kg'), 1, ' kg')}</span>"
            f"<span class='num'>{html.escape(str(row.get('best_est_1rm_set') or '-'))}</span>"
            f"<span class='num'>{html.escape(str(row.get('heaviest_set') or '-'))}</span>"
            f"<span class='num'>{fmt_num(row.get('recent_best_est_1rm_kg'), 1, ' kg')}</span>"
            f"<span class='num'>{html.escape(str(row.get('last_pr_date') or '-'))}</span>"
            "</div>"
        )
    st.markdown(
        "<div class='strength-leaderboard'>" + "".join(table_rows) + "</div>",
        unsafe_allow_html=True,
    )


# ── page ──────────────────────────────────────────────────────────────────────
st.markdown(
    "<div class='strength-page-head'><div><div class='strength-page-title'>Strength</div>"
    "<div class='strength-page-sub'>Recent session, trends, recovery context, and coach feedback.</div></div></div>",
    unsafe_allow_html=True,
)

catalog = load_catalog()

tab_overview, tab_log, tab_history, tab_insights, tab_body = st.tabs(
    ["Overview", "Log workout", "History", "Insights", "Bodyweight"])

with tab_overview:
    sessions = load_strength_sessions_with_context()
    sets = db.load_strength_sets_df()
    if not sessions.empty:
        bodyweight = resolve_bodyweight(today_str())
        verdict, _readiness = todays_recovery_verdict(today_str())
        overview = analysis.compute_strength_recent_overview(
            sessions, sets, catalog, config.ONE_RM_FORMULA
        )
        strength_summary = analysis.summarize_strength(
            sessions, sets, catalog, db.load_profile(), bodyweight,
            formula=config.ONE_RM_FORMULA, verdict=verdict,
        )
        memory_digest = coach_memory_digest()
        render_strength_overview(
            overview, strength_summary, coach_memory=memory_digest)
        render_strength_memory_panel(
            strength_memory_context(
                sessions,
                sets,
                catalog,
                bodyweight,
                verdict=verdict,
                overview=overview,
                strength_summary=strength_summary,
            ),
            existing_memory=memory_digest,
        )
    else:
        st.info("No completed strength sessions yet. Start a workout from the Log workout tab.")

with tab_history:
    st.subheader("History")
    sessions = load_strength_sessions_with_context()
    sets = db.load_strength_sets_df()
    if sessions.empty:
        st.info("No workouts logged yet.")
    else:
        date_values = pd.to_datetime(sessions.get("date"), errors="coerce").dropna()
        start_filter = end_filter = None
        workout_filter = None
        exercise_filter = None
        query_filter = ""
        pr_only = False

        with st.container(border=True):
            dcol, wcol, ecol = st.columns([1.25, 1, 1], gap="medium")
            if not date_values.empty:
                min_day = date_values.min().date()
                max_day = date_values.max().date()
                picked = dcol.date_input(
                    "Date range",
                    value=(min_day, max_day),
                    min_value=min_day,
                    max_value=max_day,
                    key="strength_history_date_range",
                )
                if isinstance(picked, (list, tuple)):
                    if len(picked) >= 2:
                        start_filter, end_filter = picked[0], picked[1]
                    elif len(picked) == 1:
                        start_filter = end_filter = picked[0]
                elif picked:
                    start_filter = end_filter = picked
            else:
                dcol.caption("No valid session dates.")

            workout_names = []
            if "name" in sessions.columns:
                workout_names = sorted({
                    str(name).strip()
                    for name in sessions["name"].dropna()
                    if str(name).strip()
                })
            workout_label = wcol.selectbox(
                "Workout",
                ["All workouts"] + workout_names,
                key="strength_history_workout_filter",
            )
            if workout_label != "All workouts":
                workout_filter = workout_label

            name_map = (
                dict(zip(catalog["exercise_id"], catalog["name"]))
                if catalog is not None and not catalog.empty and "name" in catalog.columns
                else {}
            )
            used_ids = []
            if sets is not None and not sets.empty and "exercise_id" in sets.columns:
                used_ids = [ex_id for ex_id in sets["exercise_id"].dropna().unique()]
            exercise_options = {"All exercises": None}
            for ex_id in sorted(used_ids, key=lambda value: str(name_map.get(value, value)).lower()):
                exercise_options[str(name_map.get(ex_id, ex_id))] = ex_id
            exercise_label = ecol.selectbox(
                "Exercise",
                list(exercise_options.keys()),
                key="strength_history_exercise_filter",
            )
            exercise_filter = exercise_options.get(exercise_label)

            qcol, pcol = st.columns([3, 1], gap="medium")
            query_filter = qcol.text_input(
                "Search",
                placeholder="Workout, date, or exercise",
                key="strength_history_search",
            )
            pr_only = pcol.checkbox("PR only", key="strength_history_pr_only")

        filtered_sessions = analysis.filter_strength_history_sessions(
            sessions,
            sets,
            catalog,
            start_date=start_filter,
            end_date=end_filter,
            exercise_id=exercise_filter,
            workout_name=workout_filter,
            query=query_filter,
            pr_only=pr_only,
            formula=config.ONE_RM_FORMULA,
        )
        if filtered_sessions.empty:
            st.info("No strength sessions match the current filters.")
        else:
            st.caption(f"Showing {len(filtered_sessions)} of {len(sessions)} sessions.")

            summaries = analysis.summarize_sessions(sessions, sets, catalog,
                                                    config.ONE_RM_FORMULA)
            sm = {r["session_id"]: r for _, r in summaries.iterrows()}
            exercise_rollups = analysis.summarize_session_exercises(
                sessions, sets, catalog, config.ONE_RM_FORMULA
            )
            rollups_by_session = {}
            if not exercise_rollups.empty:
                for sid, grp in exercise_rollups.groupby("session_id", sort=False):
                    rollups_by_session[str(sid)] = grp.to_dict("records")
            for _, sess in filtered_sessions.sort_values("date", ascending=False).iterrows():
                session_id = str(sess["session_id"])
                summ = sm.get(sess["session_id"], {})
                st.markdown(cockpit.strength_session_card(dict(sess), dict(summ)),
                            unsafe_allow_html=True)
                snap = {k: sess.get(k) for k in (
                    "readiness_score", "garmin_readiness_score",
                    "readiness_level", "hrv_status", "hrv_overnight_avg",
                    "resting_hr", "body_battery_start")}
                st.markdown(cockpit.strength_readiness_badge(snap),
                            unsafe_allow_html=True)
                render_history_exercise_rollup(rollups_by_session.get(session_id, []))
                with st.expander("Raw sets"):
                    ssets = sets[sets["session_id"] == sess["session_id"]]
                    if ssets.empty:
                        st.caption("No sets.")
                    else:
                        named = ssets.merge(
                            catalog[["exercise_id", "name"]], on="exercise_id",
                            how="left")
                        st.table(named[["name", "set_index", "side", "reps",
                                        "weight_kg", "rpe", "is_warmup",
                                        "completed"]])
                with st.expander("Delete workout"):
                    st.caption("This removes the saved workout and all of its sets.")
                    label = f"{sess.get('date')} — {sess.get('name') or 'Workout'}"
                    confirmed = st.checkbox(
                        f"Delete {label}",
                        key=f"confirm_delete_workout_{session_id}",
                    )
                    if st.button(
                        "Delete workout",
                        key=f"delete_workout_{session_id}",
                        disabled=not confirmed,
                    ):
                        db.delete_strength_session(session_id)
                        st.cache_data.clear()
                        st.success("Workout deleted.")
                        st.rerun()
                st.write("")

            st.divider()
            st.subheader("Estimated 1RM progress")
            prs = analysis.compute_pr_timeline(sets, sessions, catalog,
                                               config.ONE_RM_FORMULA)
            if prs.empty:
                st.caption("Log a few working sets to see 1RM trends.")
            else:
                id_to_name = dict(zip(catalog["exercise_id"], catalog["name"])) \
                    if not catalog.empty else {}
                ex_ids = list(prs["exercise_id"].unique())
                choices = {id_to_name.get(i, i): i for i in ex_ids}
                label = st.selectbox("Exercise", list(choices.keys()))
                ex_id = choices[label]
                fig = cockpit.strength_onerm_trend(
                    prs[prs["exercise_id"] == ex_id], label)
                st.plotly_chart(fig, width="stretch")

with tab_insights:
    st.subheader("Insights")
    sessions = load_strength_sessions_with_context()
    sets = db.load_strength_sets_df()
    if sessions.empty:
        st.info("Log a few workouts (especially the main lifts) to unlock standards, balance, and readiness insights.")
    else:
        profile = db.load_profile()
        bodyweight = resolve_bodyweight(today_str())
        prs = analysis.compute_pr_timeline(sets, sessions, catalog, config.ONE_RM_FORMULA)
        best_map = (prs.groupby("exercise_id")["best_est_1rm_kg"].max().to_dict()
                    if not prs.empty else {})

        st.markdown("##### Weekly strength load")
        with st.container(border=True):
            lcol, mcol, wcol = st.columns([1.25, 1, 0.75], gap="medium")
            group_label = lcol.selectbox(
                "Group by",
                ["Training pattern", "Primary muscle"],
                key="strength_weekly_load_group",
            )
            metric_label = mcol.selectbox(
                "Metric",
                ["Volume", "Working sets"],
                key="strength_weekly_load_metric",
            )
            weeks = wcol.selectbox(
                "Weeks",
                [8, 12, 16, 24],
                index=1,
                key="strength_weekly_load_weeks",
            )
            group_mode = "muscle" if group_label == "Primary muscle" else "pattern"
            metric = "working_sets" if metric_label == "Working sets" else "total_volume_kg"
            load_rows = analysis.compute_weekly_strength_load(
                sessions,
                sets,
                catalog,
                formula=config.ONE_RM_FORMULA,
                weeks=int(weeks),
                group_by=group_mode,
            )
            if load_rows.empty:
                st.caption("Log completed working sets to see weekly strength load.")
            else:
                st.plotly_chart(
                    weekly_strength_load_chart(load_rows.to_dict("records"), metric),
                    width="stretch",
                )
                latest_week = load_rows["week_start"].max()
                recent_load = load_rows[load_rows["week_start"] == latest_week].copy()
                if not recent_load.empty:
                    total = recent_load[metric].sum()
                    top = recent_load.sort_values(metric, ascending=False).iloc[0]
                    unit = "sets" if metric == "working_sets" else "kg"
                    st.caption(
                        f"Latest week {latest_week}: {fmt_num(total, 0, ' ' + unit)} total, "
                        f"largest bucket {top['group']}."
                    )

        st.divider()
        st.markdown("##### Plateau and momentum")
        with st.container(border=True):
            momentum = analysis.compute_strength_momentum_flags(
                sessions,
                sets,
                catalog,
                formula=config.ONE_RM_FORMULA,
            )
            render_strength_momentum_panel(momentum)

        st.divider()
        st.markdown("##### Best set leaderboard")
        with st.container(border=True):
            sort_col, limit_col = st.columns([1.4, .7], gap="medium")
            sort_label = sort_col.selectbox(
                "Rank by",
                ["Estimated 1RM", "Heaviest load", "Set volume", "Recent 90d 1RM"],
                key="strength_best_set_rank_by",
            )
            limit_label = limit_col.selectbox(
                "Rows",
                [10, 20, 50],
                key="strength_best_set_limit",
            )
            leaderboard = analysis.compute_strength_best_set_leaderboard(
                sessions,
                sets,
                catalog,
                formula=config.ONE_RM_FORMULA,
                recent_days=90,
            )
            if leaderboard.empty:
                st.caption("Log completed working sets to build the best-set leaderboard.")
            else:
                sort_map = {
                    "Estimated 1RM": "best_est_1rm_kg",
                    "Heaviest load": "heaviest_load_kg",
                    "Set volume": "best_volume_kg",
                    "Recent 90d 1RM": "recent_best_est_1rm_kg",
                }
                metric = sort_map.get(sort_label, "best_est_1rm_kg")
                leaderboard = leaderboard.copy()
                leaderboard[metric] = pd.to_numeric(leaderboard[metric], errors="coerce")
                leaderboard = leaderboard.sort_values(metric, ascending=False, na_position="last")
                render_best_set_leaderboard(leaderboard.to_dict("records"), int(limit_label))

        st.divider()
        st.markdown("##### Strength standards")
        standards = analysis.compute_strength_standards(best_map, profile, bodyweight)
        st.markdown(cockpit.strength_standards_panel(standards), unsafe_allow_html=True)

        st.divider()
        st.markdown("##### Muscle balance")
        balance = analysis.compute_balance(best_map, sets, catalog, config.ONE_RM_FORMULA)
        st.markdown(cockpit.strength_balance_panel(balance), unsafe_allow_html=True)

        st.divider()
        st.markdown("##### Readiness vs performance")
        corr = analysis.compute_readiness_performance(sessions, sets, catalog,
                                                      formula=config.ONE_RM_FORMULA)
        panel = cockpit.strength_correlation_panel(corr)
        if isinstance(panel, str):
            st.caption(panel)
        else:
            st.plotly_chart(panel, width="stretch")
            if corr.get("insight"):
                st.caption(corr["insight"])

        st.divider()
        st.markdown("##### Recovery-sensitive lifts")
        sens = analysis.compute_lift_recovery_sensitivity(
            sessions, sets, catalog, formula=config.ONE_RM_FORMULA)
        st.markdown(cockpit.strength_recovery_sensitivity_panel(sens),
                    unsafe_allow_html=True)

with tab_body:
    st.subheader("Bodyweight")
    day = today_str()
    current = resolve_bodyweight(day)
    st.caption("Synced from Garmin weigh-ins; override manually below if needed.")
    st.metric("Current bodyweight", f"{current:.1f} kg" if current else "—")
    with st.form("bw_form"):
        manual = st.number_input("Manual bodyweight (kg)", min_value=0.0,
                                 max_value=400.0, step=0.1,
                                 value=float(current or 0.0))
        if st.form_submit_button("Save manual weight") and manual > 0:
            db.upsert_body_metric({"date": day, "weight_kg": float(manual),
                                   "source": "manual"})
            st.success(f"Saved {manual:.1f} kg for {day}.")
            st.rerun()

with tab_log:
    active = st.session_state.get("active")

    if active is None:
        st.subheader("Start a workout")
        name = st.text_input("Workout name", value="Workout")
        routines = db.load_routines_df()
        routine_names = routines["name"].tolist() if not routines.empty else []
        chosen = st.selectbox("From routine (optional)",
                              ["— blank —"] + routine_names)
        if st.button("▶ Start", type="primary"):
            exercises, routine_id, start_name = [], None, (name or "Workout")
            if chosen != "— blank —" and not routines.empty:
                rrow = routines[routines["name"] == chosen].iloc[0]
                routine_id = rrow["routine_id"]
                start_name = chosen
                exercises = routine_to_exercises(routine_id)
            st.session_state["active"] = {
                "session_id": str(uuid.uuid4()),
                "name": start_name,
                "date": today_str(),
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "source": "app",
                "workout_type": "strength",
                "session_rpe": None,
                "bodyweight_kg": resolve_bodyweight(today_str()),
                "routine_id": routine_id,
                "exercises": exercises,
            }
            st.rerun()
        st.stop()

    # ── active workout ──
    ensure_active_shape(active)
    elapsed = duration_label(active["started_at"])
    start_epoch_ms = int(parse_dt(active["started_at"]).timestamp() * 1000)
    rest = rest_state(active)
    finish_requested = False

    with st.container(key="strong_logger"):
        with st.container(
            key="strong_topbar",
            horizontal=True,
            horizontal_alignment="center",
            vertical_alignment="center",
            gap="small",
        ):
            st.markdown("<div class='strong-top-cell icon'>⌄</div>",
                        unsafe_allow_html=True)
            if st.button("↻", key="strong_rest_reset", help="Restart rest timer"):
                st.session_state["strong_rest"] = {
                    "session_id": active["session_id"],
                    "set_id": None,
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                    "target_s": 120,
                }
                st.rerun()
            st.markdown(
                f"<div class='strong-top-cell timer'>"
                f"<span data-stopwatch data-start='{start_epoch_ms}'>{elapsed}</span></div>",
                unsafe_allow_html=True)
            if st.button("FINISH", key="finish_top", help="Finish and save workout"):
                finish_requested = True

        sessions_df, sets_df = active_to_frames(active)
        summary = analysis.summarize_sessions(sessions_df, sets_df, catalog,
                                              config.ONE_RM_FORMULA)
        s = summary.iloc[0] if not summary.empty else {}
        top_1rm = s.get("top_est_1rm_kg")
        workout_name_html = html.escape(str(active.get("name") or "Workout"))
        volume_html = f"{(s.get('total_volume_kg') or 0):,.0f} kg"
        sets_html = str(int(s.get("working_sets") or 0))
        top_html = f"{top_1rm:,.0f} kg" if top_1rm else "—"
        st.markdown(
            f"""
            <div class='strong-head'>
              <div class='strong-title'>{workout_name_html}</div>
              <div class='strong-duration'><span data-stopwatch data-start='{start_epoch_ms}'>{elapsed}</span></div>
            </div>
            <div class='strong-stats'>
              <div class='strong-stat'><div class='lab'>Volume</div><div class='val'>{volume_html}</div></div>
              <div class='strong-stat'><div class='lab'>Sets</div><div class='val'>{sets_html}</div></div>
              <div class='strong-stat'><div class='lab'>Top 1RM</div><div class='val'>{top_html}</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_live_timer_js()

        verdict, _readiness = todays_recovery_verdict(active["date"])
        st.markdown(cockpit.strength_recovery_chip(verdict), unsafe_allow_html=True)

        note_key = f"coach_note_{active['session_id']}"
        cols = st.columns([6, 1], vertical_alignment="center")
        if cols[1].button("↻", key="coach_note_refresh", help="Refresh coach note"):
            st.session_state.pop(note_key, None)
        if note_key not in st.session_state:
            plan = []
            for ex in active["exercises"]:
                sug = analysis.compute_progression_suggestion(
                    ex["exercise_id"], hist_sessions_for_note(), hist_sets_for_note(),
                    catalog, config.ONE_RM_FORMULA)
                if sug:
                    plan.append({"exercise": ex["name"], **sug})
            strength_summary = analysis.summarize_strength(
                load_strength_sessions_with_context(), db.load_strength_sets_df(), catalog,
                db.load_profile(), resolve_bodyweight(active["date"]),
                formula=config.ONE_RM_FORMULA, verdict=verdict)
            st.session_state[note_key] = ai.coach_session_note(
                strength_summary,
                verdict,
                plan,
                coach_memory=coach_memory_digest(),
            )
        if st.session_state.get(note_key):
            cols[0].caption("🧠 " + st.session_state[note_key])

        names = catalog["name"].tolist() if not catalog.empty else []
        pick = st.selectbox("Add exercise", [""] + names)
        if st.button("➕ Add to workout") and pick:
            ex_row = catalog[catalog["name"] == pick].iloc[0]
            sug = analysis.compute_progression_suggestion(
                ex_row["exercise_id"], load_strength_sessions_with_context(),
                db.load_strength_sets_df(), catalog, config.ONE_RM_FORMULA)
            seed_sets = []
            if sug:
                seed_sets = [{
                    "set_id": str(uuid.uuid4()), "set_index": 1,
                    "side": "left" if int(ex_row["is_unilateral"]) else "both",
                    "reps": int(sug["target_reps"]), "weight_kg": float(sug["suggested_weight_kg"]),
                    "rpe": None, "is_warmup": 0, "completed": 0,
                }]
            active["exercises"].append({
                "position": len(active["exercises"]),
                "exercise_id": ex_row["exercise_id"],
                "name": ex_row["name"],
                "is_unilateral": int(ex_row["is_unilateral"]),
                "is_bodyweight": int(ex_row["is_bodyweight"]),
                "sets": seed_sets,
            })
            st.rerun()

        with st.expander("➕ New custom exercise"):
            cx_name = st.text_input("Name", key="cx_name")
            cx_cat = st.selectbox(
                "Category",
                ["barbell", "dumbbell", "machine", "cable", "bodyweight"],
                key="cx_cat")
            cx_pat = st.selectbox("Movement pattern",
                                  list(strength_catalog.MOVEMENT_PATTERNS),
                                  key="cx_pat")
            cx_muscle = st.text_input("Primary muscle", key="cx_muscle")
            cx_uni = st.checkbox("Unilateral (log left/right)", key="cx_uni")
            cx_bw = st.checkbox("Bodyweight exercise", key="cx_bw")
            if st.button("Create exercise") and cx_name.strip():
                slug = "custom-" + "".join(
                    c if c.isalnum() else "-" for c in cx_name.strip().lower()
                ).strip("-")
                db.upsert_exercise({
                    "exercise_id": slug, "name": cx_name.strip(),
                    "category": cx_cat, "movement_pattern": cx_pat,
                    "primary_muscle": cx_muscle.strip(),
                    "is_unilateral": int(cx_uni),
                    "is_bodyweight": int(cx_bw),
                    "is_main_lift": 0, "is_custom": 1,
                })
                load_catalog.clear()
                st.success(f"Added {cx_name.strip()}.")
                st.rerun()

        hist_sessions = load_strength_sessions_with_context()
        hist_sets = db.load_strength_sets_df()

        for ei, ex in enumerate(active["exercises"]):
            ex_name_html = html.escape(str(ex.get("name") or "Exercise"))
            st.markdown(
                f"""
                <div class='strong-ex-head'>
                  <div class='strong-ex-title'>{ex_name_html}</div>
                  <div class='strong-ex-tools'>•••</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            suggestion = analysis.compute_progression_suggestion(
                ex["exercise_id"], hist_sessions, hist_sets, catalog, config.ONE_RM_FORMULA)
            if suggestion:
                hcols = st.columns([6, 1])
                hcols[0].markdown(cockpit.strength_suggestion_hint(suggestion),
                                  unsafe_allow_html=True)
                if hcols[1].button("Apply", key=f"apply_sug_{ei}"):
                    w = float(suggestion["suggested_weight_kg"])
                    r = int(suggestion["target_reps"])
                    if not ex["sets"]:
                        ex["sets"] = [{
                            "set_id": str(uuid.uuid4()), "set_index": 1,
                            "side": "left" if ex["is_unilateral"] else "both",
                            "reps": r, "weight_kg": w, "rpe": None,
                            "is_warmup": 0, "completed": 0,
                        }]
                    else:
                        for stt in ex["sets"]:
                            if not stt["is_warmup"]:
                                stt["weight_kg"] = w
                                stt["reps"] = r
                    st.rerun()

            note_key = f"note_{active['session_id']}_{ex['exercise_id']}_{ei}"
            ex["note"] = st.text_input(
                "Exercise note",
                value=str(ex.get("note") or ""),
                key=note_key,
                placeholder="Exercise note",
                label_visibility="collapsed",
            )
            if str(ex.get("note") or "").strip():
                note_html = html.escape(str(ex.get("note") or ""))
                st.markdown(f"<div class='strong-note'>{note_html}</div>",
                            unsafe_allow_html=True)

            uni = bool(ex["is_unilateral"])
            prev = analysis.last_session_sets(
                ex["exercise_id"], hist_sessions, hist_sets)
            st.markdown(
                "<div class='strong-col-head'><span>Set</span><span>Previous</span>"
                "<span>Kg</span><span>Reps</span><span>✓</span></div>",
                unsafe_allow_html=True,
            )

            work_n = 0
            for si, stt in enumerate(ex["sets"]):
                completed = bool(int(stt.get("completed") or 0))
                if stt["is_warmup"]:
                    badge = "W"
                    badge_class = "warm"
                    prev_label = "—"
                else:
                    work_n += 1
                    badge = str(work_n)
                    badge_class = "done" if completed else "work"
                    prev_label = set_previous_label(prev, work_n - 1)
                with st.container(
                    key=f"strong_setrow_{stt['set_id']}",
                    horizontal=True,
                    vertical_alignment="center",
                    gap="small",
                ):
                    if st.button(badge, key=f"badge_{stt['set_id']}",
                                 help="Tap to toggle warmup"):
                        stt["is_warmup"] = 0 if stt["is_warmup"] else 1
                        st.rerun()
                    st.markdown(f"<div class='strong-prev'>{prev_label}</div>",
                                unsafe_allow_html=True)
                    kg_raw = st.text_input(
                        "kg", value=f"{float(stt['weight_kg']):g}",
                        key=f"kg_txt_{stt['set_id']}",
                        label_visibility="collapsed")
                    reps_raw = st.text_input(
                        "reps", value=str(int(stt["reps"])),
                        key=f"reps_txt_{stt['set_id']}",
                        label_visibility="collapsed")
                    try:
                        stt["weight_kg"] = max(
                            0.0, float(kg_raw.replace(",", ".")))
                    except (TypeError, ValueError):
                        pass
                    try:
                        stt["reps"] = max(
                            0, int(float(reps_raw.replace(",", "."))))
                    except (TypeError, ValueError):
                        pass
                    check_label = "✓" if completed else "○"
                    check_type = "primary" if completed else "secondary"
                    if st.button(check_label, key=f"done_{stt['set_id']}",
                                 type=check_type, help="Toggle completed"):
                        stt["completed"] = 0 if completed else 1
                        if stt["completed"]:
                            mark_rest_started(active, stt["set_id"])
                        st.rerun()
                if completed:
                    st.markdown("<div class='strong-done-strip'></div>",
                                unsafe_allow_html=True)
                if rest and rest.get("set_id") == stt["set_id"]:
                    st.markdown(
                        f"<div class='strong-rest active'><span>{rest_label(rest['remaining_s'])}</span></div>",
                        unsafe_allow_html=True,
                    )

            if st.button("➕ Add Set", key=f"addset_{ei}"):
                last = ex["sets"][-1] if ex["sets"] else None
                work_count = len(
                    [s for s in ex["sets"] if not s.get("is_warmup")])
                next_prev = prev[work_count] if len(prev) > work_count else None
                reps = 5
                weight = 20.0
                if last:
                    reps = int(last["reps"])
                    weight = float(last["weight_kg"])
                elif next_prev:
                    reps = int(next_prev["reps"])
                    weight = float(next_prev["weight_kg"])
                ex["sets"].append({
                    "set_id": str(uuid.uuid4()),
                    "set_index": len(ex["sets"]) + 1,
                    "side": (last["side"] if last else ("left" if uni else "both")),
                    "reps": reps,
                    "weight_kg": weight,
                    "rpe": None, "is_warmup": 0, "completed": 0,
                })
                st.rerun()

            with st.expander("Set details"):
                for si, stt in enumerate(ex["sets"]):
                    drow = st.columns([0.7, 1.0, 1.0, 0.7])
                    drow[0].caption(f"Set {si + 1}")
                    rpe_val = drow[1].number_input(
                        "RPE", min_value=0.0, max_value=10.0, step=0.5,
                        value=float(stt.get("rpe") or 0.0),
                        key=f"rpe_{stt['set_id']}")
                    stt["rpe"] = rpe_val or None
                    if uni:
                        stt["side"] = drow[2].selectbox(
                            "Side", ["left", "right"],
                            index=(1 if stt.get("side") == "right" else 0),
                            key=f"side_{stt['set_id']}")
                    else:
                        drow[2].caption("Both sides")
                    if drow[3].button("Remove", key=f"del_{stt['set_id']}"):
                        ex["sets"].pop(si)
                        for j, t in enumerate(ex["sets"]):
                            t["set_index"] = j + 1
                        st.rerun()

        st.divider()
        with st.expander("💾 Save this workout as a routine"):
            rname = st.text_input("Routine name", value=active["name"],
                                  key="save_rt")
            if st.button("Save routine") and active["exercises"] and rname.strip():
                save_active_as_routine(active, rname.strip())
                st.success(f"Saved routine '{rname.strip()}'.")

        with st.expander("Session details"):
            workout_types = [
                "strength", "hypertrophy", "heavy", "deload",
                "rehab", "bjj_support",
            ]
            current_type = str(active.get("workout_type") or "strength")
            type_index = workout_types.index(current_type) if current_type in workout_types else 0
            active["workout_type"] = st.selectbox(
                "Workout type",
                workout_types,
                index=type_index,
                format_func=lambda value: str(value).replace("_", " ").title(),
                key=f"session_workout_type_{active['session_id']}",
            )
            session_rpe = st.number_input(
                "Session RPE",
                min_value=0.0,
                max_value=10.0,
                step=0.5,
                value=float(active.get("session_rpe") or 0.0),
                key=f"session_rpe_{active['session_id']}",
            )
            active["session_rpe"] = session_rpe or None

        completion = workout_completion_status(active)
        confirm_pending = True
        if completion["pending_working_sets"]:
            st.warning(
                f"{completion['pending_working_sets']} working set(s) are still "
                "unchecked. They will save as incomplete and will not count in "
                "volume or PR analytics."
            )
            confirm_pending = st.checkbox(
                "Save unchecked sets as incomplete",
                key="confirm_finish_pending",
            )

        fcol1, fcol2 = st.columns(2)
        if fcol1.button("✅ Finish & save", type="primary"):
            finish_requested = True
        has_content = any(ex.get("sets") for ex in active["exercises"])
        discard_ok = True
        if has_content:
            discard_ok = st.checkbox("Confirm discard",
                                     key="confirm_discard_active")
        if fcol2.button("🗑 Discard", disabled=has_content and not discard_ok):
            del st.session_state["active"]
            st.session_state.pop("strong_rest", None)
            st.rerun()
        if finish_requested:
            if confirm_pending:
                finish_active_workout(active)
                st.success("Workout saved.")
                st.rerun()
            else:
                st.warning("Check off the pending sets or confirm incomplete save.")
