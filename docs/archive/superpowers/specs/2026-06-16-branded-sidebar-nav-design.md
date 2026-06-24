# Branded sidebar navigation — design

- **Date:** 2026-06-16
- **Status:** Approved (pending spec review)
- **Topic:** Re-skin the multipage navigation to match the "Graphite Voltage" design language.

## Problem

The app is a Streamlit multipage app: `app.py` (the Recovery Cockpit, also the
entry script) plus `pages/01_Strength.py`, `pages/02_Coach.py`,
`pages/03_Experiments.py`. Streamlit auto-generates the sidebar nav from those
filenames. The result is stock chrome that clashes with the heavily-customized
dark "Graphite Voltage" UI:

- The entry page shows as a lowercase **"app"**.
- No icons (the `page_icon` in each `set_page_config` only sets the browser
  favicon, not the nav).
- Default typography / spacing / active-state — none of the app's mono labels,
  lime accent, or brand treatment.

## Goal

Replace the auto nav with a branded sidebar that matches the app: brand mark at
the top, mono uppercase labels, per-page icons, and a lime "marker bar" active
state — with the entry page properly titled **"Cockpit"**.

## Non-goals

- No changes to analytics, charts, data flow, or page content.
- No new pages, no palette changes, no mobile redesign beyond Streamlit's default
  sidebar collapse behavior.
- Not moving the nav to a top bar (the left sidebar form was chosen).

## Decisions locked during brainstorming

- **Form:** re-skinned **left sidebar** (not a top nav).
- **Treatment:** **Marker bar** — active page = soft lime tint + 2px lime left
  edge bar; inactive = dim grey. (Chosen over a filled lime pill and a
  minimal glow-dot variant.)
- **Entry page label:** **Cockpit**.
- **Icons:** material icons — Cockpit `:material/monitor_heart:`, Strength
  `:material/exercise:`, Coach `:material/psychology:`, Experiments
  `:material/science:`.
- **Browser tab title:** collapse to a single "Hankø Fitness Hub" (per-page
  titles can be re-added later if wanted).

Mockups from the session are saved under `.superpowers/brainstorm/` (gitignored).

## Approach

Migrate from the magic `pages/` convention to the modern **`st.navigation` +
`st.Page`** API (supported in the installed Streamlit 1.58).

Why this over a CSS-only reskin of the existing auto nav:

- Only `st.navigation` gives clean control over the entry page's label
  ("app" → "Cockpit") and real material icons.
- It targets one supported nav container instead of leaning on Streamlit-internal
  DOM selectors. (A stale internal selector is exactly what just broke the `30d`
  popover styling, so reducing that surface is deliberate.)

Verified API (Streamlit 1.58):

```
st.navigation(pages, *, position='sidebar', expanded=False) -> StreamlitPage
st.Page(page, *, title=None, icon=None, url_path=None, default=False,
        visibility='visible') -> StreamlitPage
```

## Detailed design

### File structure

`st.navigation` and the magic `pages/` directory conflict (both would populate
the nav, double-listing every page), so the views move out of `pages/`:

| Now | After |
|---|---|
| `app.py` (entry **and** cockpit body) | `app.py` = thin **router** |
| *(cockpit body lives in `app.py`)* | `views/cockpit.py` |
| `pages/01_Strength.py` | `views/strength.py` |
| `pages/02_Coach.py` | `views/coach.py` |
| `pages/03_Experiments.py` | `views/experiments.py` |

The `pages/` directory is removed once empty.

### Router (`app.py`)

Runs once per interaction, before any page body:

1. `st.set_page_config(page_title="Hankø Fitness Hub", page_icon="🏃", layout="wide")`
2. `st.markdown(cockpit.CSS, unsafe_allow_html=True)` — injected once here.
   Because `nav.run()` executes the selected view *inline within this same
   script run*, the CSS applies to whichever page renders.
3. Render the brand block at the top of the sidebar (see Sidebar visual).
4. Build and run the nav:

```python
pages = [
    st.Page("views/cockpit.py",      title="Cockpit",     icon=":material/monitor_heart:", default=True),
    st.Page("views/strength.py",     title="Strength",    icon=":material/exercise:"),
    st.Page("views/coach.py",        title="Coach",       icon=":material/psychology:"),
    st.Page("views/experiments.py",  title="Experiments", icon=":material/science:"),
]
st.navigation(pages).run()
```

### Views

Each moved view keeps its `importlib.reload(...)` block and its full body. From
each view, **delete** its own `st.set_page_config(...)` and
`st.markdown(cockpit.CSS, ...)` — the router now owns both. (Single source for
page config avoids the "set_page_config called twice" edge case.)

### Sidebar visual — Marker bar

- **Brand block** pinned at the top of the sidebar, above the nav list: lime
  diamond mark + **HANKØ** wordmark + `FITNESS HUB` mono kicker. Implementation
  is a plan-level choice between `st.logo` (SVG mark) and a `st.sidebar` markdown
  block ordered above `[data-testid="stSidebarNav"]` via CSS — both are viable;
  pick whichever renders the diamond + wordmark cleanly.
- **Nav CSS** added as a new block in `cockpit.CSS`, targeting
  `[data-testid="stSidebarNav"]` and its links:
  - mono uppercase labels with the app's letter-spacing;
  - inactive = `--text-dim`, hover lifts to `--text`;
  - **active** = soft lime tint background (`rgba(accent,.10)`) + a 2px lime
    left edge bar + lime label/icon.
  - Because all pages load `cockpit.CSS`, the styling is app-wide automatically.

### Cross-page link

[app.py:361](app.py#L361) currently calls
`st.page_link("pages/02_Coach.py", label="Manage everything the coach knows →")`.
That call moves into `views/cockpit.py` and is re-pointed at the new Coach page
(`views/coach.py`, or the Coach `st.Page` object / its `url_path`).

## Edge cases & risks

- **Double nav:** leaving any view inside `pages/` would re-introduce the auto
  nav alongside `st.navigation`. Mitigation: remove `pages/` entirely.
- **`set_page_config` twice:** only the router calls it; views must not.
- **CSS selector drift:** `[data-testid="stSidebarNav"]` is the one internal hook
  used; if a Streamlit upgrade renames it, only the nav skin (not navigation
  itself) degrades — a strictly smaller blast radius than today's auto nav.
- **Browser tab titles** become uniform (accepted).

## Unchanged

All analytics (`analysis.py`), AI (`ai.py`), data/ingest, charts, and the actual
per-page content render exactly as before. This change is entry-structure +
nav skin only.

## Verification

- `streamlit run app.py` launches; sidebar shows the brand block + four items
  (Cockpit / Strength / Coach / Experiments) with icons and mono labels.
- The active page shows the lime marker bar; switching pages moves it.
- Each page renders its previous content unchanged; the Cockpit → Coach
  "Manage everything the coach knows" link still navigates.
- No duplicate nav entries; no `set_page_config` errors in the console.
